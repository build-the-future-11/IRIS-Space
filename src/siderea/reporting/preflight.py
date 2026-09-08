"""Preflight checks that must pass before any report draft is considered ready."""

from __future__ import annotations

import hmac
import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from siderea.integrity import verify_candidate_record, verify_candidate_version_payload
from siderea.ledger import OutcomeLedger
from siderea.manifest import RUN_MANIFEST_SCHEMA
from siderea.provenance import CheckProvenance, digest_value
from siderea.validation.binding import (
    EvidenceBindingContext,
    bind_completed_checks,
    preflight_digest,
)
from siderea.validation.gates import evaluate_reportability


@dataclass(frozen=True)
class PreflightResult:
    ready: bool
    reasons: tuple[str, ...]


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _finite_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _candidate_binding_payload(
    ledger: OutcomeLedger,
    candidate_id: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any], str, str]:
    candidate = ledger.candidate(candidate_id)
    if not candidate:
        return {}, {}, "", ""
    payload = candidate.get("payload", {})
    if not isinstance(payload, Mapping):
        return {}, {}, "", ""
    binding = payload.get("evidence_binding", {})
    version = str(candidate.get("version_digest", "")).strip()
    campaign = str(candidate.get("campaign", "")).strip()
    return payload, binding if isinstance(binding, Mapping) else {}, version, campaign


def _candidate_artifact_error(
    manifest: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    manifest_path: Path,
) -> str | None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or any(not isinstance(item, Mapping) for item in artifacts):
        return "candidate run manifest has invalid artifacts"
    candidate_artifacts = [item for item in artifacts if item.get("role") == "candidate-evidence"]
    if len(candidate_artifacts) != 1:
        return "candidate run manifest does not identify exactly one candidate-evidence artifact"
    artifact = candidate_artifacts[0]
    artifact_path = artifact.get("path")
    artifact_digest = artifact.get("sha256")
    artifact_size = artifact.get("size_bytes")
    if (
        not isinstance(artifact_path, str)
        or not Path(artifact_path).is_absolute()
        or not isinstance(artifact_digest, str)
        or not _SHA256.fullmatch(artifact_digest)
        or isinstance(artifact_size, bool)
        or not isinstance(artifact_size, int)
        or artifact_size < 0
    ):
        return "candidate-evidence artifact metadata is invalid"
    resolved_artifact_path = Path(artifact_path).resolve()
    if resolved_artifact_path.parent != manifest_path.resolve().parent:
        return "candidate-evidence artifact is outside its published run directory"
    try:
        evidence_bytes = resolved_artifact_path.read_bytes()
        evidence = json.loads(evidence_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "candidate-evidence artifact is unavailable or unreadable"
    if len(evidence_bytes) != artifact_size or not hmac.compare_digest(
        sha256(evidence_bytes).hexdigest(), artifact_digest
    ):
        return "candidate-evidence artifact differs from its run manifest"
    if (
        not isinstance(evidence, Mapping)
        or evidence.get("schema") != "siderea.candidates.v1"
        or evidence.get("run_id") != payload.get("run_id")
        or evidence.get("scientific_fingerprint") != payload.get("scientific_fingerprint")
        or evidence.get("pipeline_version") != payload.get("pipeline_version")
    ):
        return "candidate-evidence artifact has inconsistent run provenance"
    candidates = evidence.get("candidates")
    if not isinstance(candidates, list) or any(
        not isinstance(item, Mapping) for item in candidates
    ):
        return "candidate-evidence artifact has an invalid candidate collection"
    candidate_id = payload.get("candidate_id")
    matches = [item for item in candidates if item.get("candidate_id") == candidate_id]
    if len(matches) != 1:
        return "candidate-evidence artifact does not contain exactly one matching candidate"
    record = matches[0]
    if record.get("candidate_version") != payload.get("candidate_version") or record.get(
        "candidate_record_digest"
    ) != payload.get("candidate_record_digest"):
        return "ledger candidate differs from its published candidate artifact"
    pipeline_version = payload.get("pipeline_version")
    if not isinstance(pipeline_version, str):
        return "candidate pipeline version is invalid"
    try:
        verify_candidate_record(record, pipeline_version=pipeline_version)
    except (TypeError, ValueError):
        return "published candidate record fails self-verification"
    return None


def _publication_error(payload: Mapping[str, Any]) -> str | None:
    """Verify the durable run manifest referenced by a pipeline ledger payload."""

    if "pipeline_version" not in payload:
        return None
    publication = payload.get("publication")
    if not isinstance(publication, Mapping):
        return "candidate has no completed run-publication record"
    required = {"schema", "run_id", "manifest_path", "manifest_sha256", "status"}
    if set(publication) != required:
        return "candidate run-publication record is incomplete or unknown"
    if (
        publication.get("schema") != "siderea.run_publication.v1"
        or publication.get("status") != "completed"
        or publication.get("run_id") != payload.get("run_id")
    ):
        return "candidate run-publication record is inconsistent"
    raw_path = publication.get("manifest_path")
    expected_digest = publication.get("manifest_sha256")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return "candidate run manifest path is invalid"
    if not isinstance(expected_digest, str) or not _SHA256.fullmatch(expected_digest):
        return "candidate run manifest digest is invalid"
    manifest_path = Path(raw_path).expanduser()
    if not manifest_path.is_absolute():
        return "candidate run manifest path is invalid"
    try:
        manifest_bytes = manifest_path.read_bytes()
        actual_digest = sha256(manifest_bytes).hexdigest()
        manifest = json.loads(manifest_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "candidate run manifest is unavailable or unreadable"
    if not hmac.compare_digest(actual_digest, expected_digest):
        return "candidate run manifest differs from its publication digest"
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("schema") != RUN_MANIFEST_SCHEMA
        or manifest.get("status") != "completed"
    ):
        return "candidate run manifest is not completed"
    if manifest.get("run_id") != payload.get("run_id"):
        return "candidate run manifest identifies another run"
    configuration = manifest.get("configuration")
    configuration_digest = manifest.get("configuration_digest")
    code_source_digest = manifest.get("code_source_digest")
    if (
        not isinstance(configuration, Mapping)
        or not isinstance(configuration_digest, str)
        or not _SHA256.fullmatch(configuration_digest)
        or not hmac.compare_digest(digest_value(dict(configuration)), configuration_digest)
        or not isinstance(code_source_digest, str)
        or not _SHA256.fullmatch(code_source_digest)
        or configuration.get("scientific_fingerprint") != payload.get("scientific_fingerprint")
        or configuration.get("pipeline_version") != payload.get("pipeline_version")
    ):
        return "candidate run manifest has inconsistent scientific provenance"
    return _candidate_artifact_error(manifest, payload, manifest_path=manifest_path)


def _stored_coordinate(
    payload: Mapping[str, Any],
    binding: Mapping[str, Any],
    name: str,
) -> float | None:
    for source in (binding, payload):
        value = _finite_number(source.get(name))
        if value is not None:
            return value
    position = payload.get("position", {})
    if isinstance(position, Mapping):
        return _finite_number(position.get(name))
    return None


def reporting_preflight(
    candidate_id: str,
    *,
    checks: Iterable[CheckProvenance],
    quality_passed: bool,
    manual_review_required: bool,
    ledger: OutcomeLedger,
    required_reviewers: int | None = None,
    candidate_version: str | None = None,
    ra_deg: float | None = None,
    dec_deg: float | None = None,
    evidence_ttl_hours: float | None = None,
    required_radii_arcsec: Mapping[str, float] | None = None,
    skybot_reference_mjds: Iterable[float] | None = None,
    mandatory_services: Iterable[str] | None = None,
) -> PreflightResult:
    """Check bound external evidence and current-version human approvals.

    Binding context is normally recovered from the candidate payload written by
    the analysis pipeline.  Explicit values support callers migrating older
    ledger records.  If neither source supplies enough context, preflight fails
    closed before considering a ``CLEAR`` result.
    """

    if not isinstance(quality_passed, bool) or not isinstance(manual_review_required, bool):
        return PreflightResult(False, ("quality and manual-review flags must be boolean",))

    try:
        payload, stored_binding, stored_version, stored_campaign = _candidate_binding_payload(
            ledger, candidate_id
        )
    except (TypeError, ValueError):
        return PreflightResult(False, ("candidate ledger payload fails integrity validation",))
    requested_version = (
        candidate_version.strip() if candidate_version is not None else stored_version
    )
    payload_version = str(payload.get("candidate_version", "")).strip()
    if (
        not stored_version
        or not requested_version
        or requested_version != stored_version
        or payload_version != stored_version
    ):
        return PreflightResult(
            False,
            ("candidate version is missing, stale, or inconsistent with its evidence payload",),
        )
    pipeline_version = payload.get("pipeline_version")
    if not isinstance(pipeline_version, str) or not pipeline_version.strip():
        return PreflightResult(
            False,
            ("legacy candidate payload is non-authoritative and cannot pass reporting preflight",),
        )
    try:
        verify_candidate_version_payload(
            payload,
            pipeline_version=pipeline_version,
            expected_candidate_id=candidate_id,
            expected_campaign=stored_campaign,
            expected_version=stored_version,
        )
    except (TypeError, ValueError):
        return PreflightResult(
            False,
            ("candidate scientific payload fails immutable-version verification",),
        )
    publication_error = _publication_error(payload)
    if publication_error is not None:
        return PreflightResult(False, (publication_error,))
    stored_review_policy = payload.get("review_policy")
    if not isinstance(stored_review_policy, Mapping):
        return PreflightResult(False, ("review authorization policy is unavailable",))
    stored_required_reviewers = stored_review_policy.get("required_reviewers")
    if (
        isinstance(stored_required_reviewers, bool)
        or not isinstance(stored_required_reviewers, int)
        or stored_required_reviewers < 1
    ):
        return PreflightResult(False, ("stored review authorization policy is invalid",))
    if (
        stored_review_policy.get("require_human_approval") is not True
        or stored_review_policy.get("allow_self_approval") is not False
    ):
        return PreflightResult(False, ("stored review authorization policy is unsafe",))
    if required_reviewers is not None:
        if (
            isinstance(required_reviewers, bool)
            or not isinstance(required_reviewers, int)
            or required_reviewers < 1
        ):
            return PreflightResult(False, ("required_reviewers must be a positive integer",))
        if required_reviewers != stored_required_reviewers:
            return PreflightResult(
                False,
                ("requested reviewer policy differs from the immutable candidate version",),
            )
    effective_ra = (
        ra_deg if ra_deg is not None else _stored_coordinate(payload, stored_binding, "ra_deg")
    )
    effective_dec = (
        dec_deg if dec_deg is not None else _stored_coordinate(payload, stored_binding, "dec_deg")
    )
    effective_ttl = (
        evidence_ttl_hours
        if evidence_ttl_hours is not None
        else _finite_number(stored_binding.get("max_ttl_hours"))
    )
    effective_radii: object = (
        required_radii_arcsec
        if required_radii_arcsec is not None
        else stored_binding.get("required_radii_arcsec")
    )
    effective_references: object = (
        skybot_reference_mjds
        if skybot_reference_mjds is not None
        else stored_binding.get("skybot_reference_mjds", ())
    )
    if effective_ra is None or effective_dec is None:
        return PreflightResult(
            False,
            ("candidate sky position is unavailable for evidence binding",),
        )
    if effective_ttl is None:
        return PreflightResult(False, ("evidence TTL policy is unavailable for evidence binding",))
    if not isinstance(effective_radii, Mapping):
        return PreflightResult(False, ("query-radius policy is unavailable for evidence binding",))
    if isinstance(effective_references, (str, bytes)) or not isinstance(
        effective_references, Iterable
    ):
        return PreflightResult(False, ("SkyBoT reference epochs are invalid",))
    effective_position_tolerance = _finite_number(stored_binding.get("position_tolerance_arcsec"))
    effective_epoch_tolerance = _finite_number(stored_binding.get("skybot_epoch_tolerance_days"))
    if effective_position_tolerance is None or effective_epoch_tolerance is None:
        return PreflightResult(False, ("evidence-binding tolerance policy is unavailable",))

    try:
        context = EvidenceBindingContext(
            candidate_id=candidate_id,
            ra_deg=effective_ra,
            dec_deg=effective_dec,
            max_ttl_hours=effective_ttl,
            required_radii_arcsec=effective_radii,
            skybot_reference_mjds=tuple(effective_references),
            position_tolerance_arcsec=effective_position_tolerance,
            skybot_epoch_tolerance_days=effective_epoch_tolerance,
        )
    except (TypeError, ValueError) as exc:
        return PreflightResult(False, (f"invalid evidence binding context: {exc}",))

    scientific_config = payload.get("scientific_config")
    validation_policy = (
        scientific_config.get("validation") if isinstance(scientific_config, Mapping) else None
    )
    stored_services = (
        validation_policy.get("required_checks") if isinstance(validation_policy, Mapping) else None
    )
    if isinstance(stored_services, (str, bytes)) or not isinstance(stored_services, Iterable):
        return PreflightResult(False, ("stored mandatory-service policy is invalid",))
    required = tuple(str(service).strip().casefold() for service in stored_services)
    if mandatory_services is not None:
        requested_services = tuple(
            str(service).strip().casefold() for service in mandatory_services
        )
        if requested_services != required:
            return PreflightResult(
                False,
                ("requested service policy differs from the immutable candidate version",),
            )
    bound_checks = bind_completed_checks(checks, context)
    stored_digest = str(payload.get("preflight_digest", "")).strip()
    current_digest = preflight_digest(
        context=context,
        checks=bound_checks,
        quality_passed=quality_passed,
        manual_review_required=manual_review_required,
        mandatory_services=required,
        required_reviewers=stored_required_reviewers,
        verification_context=payload.get("verification_context"),
    )
    if not stored_digest or not hmac.compare_digest(stored_digest, current_digest):
        return PreflightResult(
            False,
            ("preflight evidence differs from the immutable reviewed candidate version",),
        )
    if manual_review_required:
        adjudicated, adjudication_reason = ledger.manual_adjudication(
            candidate_id,
            candidate_version=requested_version,
        )
        if not adjudicated:
            return PreflightResult(False, (adjudication_reason,))
    gate_evaluated_at = datetime.now(UTC)
    gate = evaluate_reportability(
        bound_checks,
        quality_passed=quality_passed,
        manual_review_required=False,
        mandatory_services=required,
        at=gate_evaluated_at,
    )
    if not gate.reportable:
        return PreflightResult(False, gate.reasons)
    approved, reason = ledger.independent_approval(
        candidate_id,
        required_reviewers=stored_required_reviewers,
        candidate_version=requested_version,
    )
    if not approved:
        return PreflightResult(False, (reason,))
    return PreflightResult(True, ("scientific gates and independent review complete",))
