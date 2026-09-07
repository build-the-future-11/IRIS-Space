"""Self-verifying scientific candidate records.

Candidate versions are useful only when a consumer can independently rebuild
the version from the evidence it is about to show a reviewer.  This module is
kept free of pipeline and UI dependencies so both producers and importers use
the same canonical contract.
"""

from __future__ import annotations

import hmac
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from iris.evidence_context import serialized_verification_context
from iris.provenance import CheckProvenance, CheckStatus, digest_value
from iris.validation.binding import EvidenceBindingContext, bind_completed_checks, preflight_digest
from iris.validation.gates import MANDATORY_SERVICES, GateDecision

CANDIDATE_EVIDENCE_SCHEMA = "iris.candidate_evidence.v2"
CANDIDATE_OBSERVATIONS_SCHEMA = "iris.candidate_observations.v1"
CANDIDATE_RECORD_SCHEMA = "iris.candidate_record.v1"
CANDIDATE_RUN_BINDING_SCHEMA = "iris.candidate_run_binding.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def candidate_observations_digest(observations: Sequence[Mapping[str, Any]]) -> str:
    """Hash the exact ordered, JSON-safe observations shown to a reviewer."""

    if isinstance(observations, (str, bytes)) or not isinstance(observations, Sequence):
        raise TypeError("candidate observations must be a sequence of mappings")
    if any(not isinstance(item, Mapping) for item in observations):
        raise TypeError("every candidate observation must be a mapping")
    return digest_value(
        {
            "schema": CANDIDATE_OBSERVATIONS_SCHEMA,
            "observations": [dict(item) for item in observations],
        }
    )


def canonical_check_payloads(
    checks: Iterable[CheckProvenance | Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return check payloads with volatile unfinished-attempt timing removed."""

    payloads: list[dict[str, Any]] = []
    for raw in checks:
        payload = raw.to_dict() if isinstance(raw, CheckProvenance) else dict(raw)
        if payload.get("status") not in {CheckStatus.CLEAR.value, CheckStatus.MATCH.value}:
            payload["checked_at"] = None
            payload["expires_at"] = None
            payload["latency_ms"] = None
        payloads.append(payload)
    return payloads


def candidate_version_basis(
    *,
    pipeline_version: str,
    candidate_id: str,
    campaign: str,
    observations_digest: str,
    position: Mapping[str, Any],
    quality: Mapping[str, Any],
    features: Mapping[str, Any],
    score: Mapping[str, Any],
    external_checks: Iterable[CheckProvenance | Mapping[str, Any]],
    manual_review_required: bool,
    automated_gate: Mapping[str, Any],
    evidence_binding: Mapping[str, Any],
    reporting_preflight_digest: str,
    scientific_config: Mapping[str, Any],
    verification_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical evidence basis for one immutable candidate version."""

    reference_mjds = evidence_binding.get("skybot_reference_mjds", ())
    if isinstance(reference_mjds, (str, bytes)) or not isinstance(reference_mjds, Sequence):
        raise ValueError("candidate evidence binding has invalid SkyBoT reference epochs")
    context_evidence = serialized_verification_context(
        verification_context,
        manual_review_required=manual_review_required,
        expected_skybot_reference_mjds=reference_mjds,
    )

    return {
        "schema": CANDIDATE_EVIDENCE_SCHEMA,
        "pipeline_version": pipeline_version,
        "candidate_id": candidate_id,
        "campaign": campaign,
        "observations_digest": observations_digest,
        "position": dict(position),
        "quality": {
            "passed": quality.get("passed"),
            "reasons": list(quality.get("reasons", ())),
        },
        "features": dict(features),
        "score": dict(score),
        "external_checks": canonical_check_payloads(external_checks),
        "manual_review_required": manual_review_required,
        "verification_context": context_evidence,
        "automated_gate": {
            "decision": automated_gate.get("decision"),
            "reasons": list(automated_gate.get("reasons", ())),
            "missing_services": list(automated_gate.get("missing_services", ())),
            "matched_services": list(automated_gate.get("matched_services", ())),
        },
        "evidence_binding": dict(evidence_binding),
        "reporting_preflight_digest": reporting_preflight_digest,
        "scientific_config": dict(scientific_config),
    }


def candidate_record_digest(record: Mapping[str, Any]) -> str:
    """Hash a complete serialized review record, excluding its digest field."""

    payload = dict(record)
    payload.pop("candidate_record_digest", None)
    # Run identity has a separate, explicit binding so scientifically
    # identical candidate records remain stable across deterministic reruns.
    # Keep scientific_fingerprint here: a changed scientific configuration
    # must still produce a different candidate-record digest.
    payload.pop("run_id", None)
    payload.pop("candidate_run_binding_digest", None)
    # The wall-clock evaluation instant is operational provenance recorded in
    # the run manifest.  The actual automated-gate outcome and every input to
    # it are already hashed into candidate_version; excluding this timestamp
    # preserves byte-stable rankings while the scientific decision is stable.
    payload.pop("gate_evaluated_at", None)
    checks = payload.get("external_checks")
    if isinstance(checks, Sequence) and not isinstance(checks, (str, bytes)):
        payload["external_checks"] = canonical_check_payloads(checks)
    return digest_value({"schema": CANDIDATE_RECORD_SCHEMA, "candidate": payload})


def _mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"candidate record has invalid {field}")
    return value


def _required_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"candidate record has invalid {field}")
    return value


def _finite_coordinate(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"candidate record has invalid {field}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"candidate record has invalid {field}")
    return number


def _sequence_of_mappings(value: Any, *, field: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"candidate record has invalid {field}")
    if any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"candidate record has invalid {field}")
    return list(value)


def _string_sequence(value: Any, *, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"candidate record has invalid {field}")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"candidate record has invalid {field}")
    return tuple(value)


def candidate_run_binding_digest(record: Mapping[str, Any]) -> str:
    """Bind one stable candidate record to its concrete producing run."""

    run_id = _required_string(record.get("run_id"), field="run_id")
    scientific_fingerprint = _required_string(
        record.get("scientific_fingerprint"),
        field="scientific_fingerprint",
    )
    candidate_id = _required_string(record.get("candidate_id"), field="candidate_id")
    candidate_version = _required_string(
        record.get("candidate_version"),
        field="candidate_version",
    )
    record_digest = _required_string(
        record.get("candidate_record_digest"),
        field="candidate_record_digest",
    )
    for field, value in (
        ("candidate_version", candidate_version),
        ("candidate_record_digest", record_digest),
    ):
        if not _SHA256.fullmatch(value):
            raise ValueError(f"candidate {candidate_id!r} has invalid {field}")
    return digest_value(
        {
            "schema": CANDIDATE_RUN_BINDING_SCHEMA,
            "run_id": run_id,
            "scientific_fingerprint": scientific_fingerprint,
            "candidate_id": candidate_id,
            "candidate_version": candidate_version,
            "candidate_record_digest": record_digest,
        }
    )


def verify_candidate_run_binding(record: Mapping[str, Any]) -> str:
    """Verify that a stable candidate record belongs to its asserted run."""

    candidate_id = record.get("candidate_id")
    stored = record.get("candidate_run_binding_digest")
    if not isinstance(stored, str) or not _SHA256.fullmatch(stored):
        raise ValueError(f"candidate {candidate_id!r} has invalid candidate_run_binding_digest")
    computed = candidate_run_binding_digest(record)
    if not hmac.compare_digest(computed, stored):
        raise ValueError(f"candidate {candidate_id!r} run binding differs from its digest")
    return computed


def _binding_context(payload: Mapping[str, Any]) -> EvidenceBindingContext:
    required = {
        "candidate_id",
        "ra_deg",
        "dec_deg",
        "max_ttl_hours",
        "required_radii_arcsec",
        "skybot_reference_mjds",
        "position_tolerance_arcsec",
        "skybot_epoch_tolerance_days",
    }
    if set(payload) != required:
        raise ValueError("candidate record has an incomplete or unknown evidence-binding policy")
    try:
        return EvidenceBindingContext(
            candidate_id=payload["candidate_id"],
            ra_deg=payload["ra_deg"],
            dec_deg=payload["dec_deg"],
            max_ttl_hours=payload["max_ttl_hours"],
            required_radii_arcsec=payload["required_radii_arcsec"],
            skybot_reference_mjds=tuple(payload["skybot_reference_mjds"]),
            position_tolerance_arcsec=payload["position_tolerance_arcsec"],
            skybot_epoch_tolerance_days=payload["skybot_epoch_tolerance_days"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("candidate record has an invalid evidence-binding policy") from exc


def verify_candidate_version_payload(
    record: Mapping[str, Any],
    *,
    pipeline_version: str,
    expected_candidate_id: str | None = None,
    expected_campaign: str | None = None,
    expected_version: str | None = None,
) -> str:
    """Rebuild and validate the scientific version in a record or ledger payload."""

    candidate_id = _required_string(record.get("candidate_id"), field="candidate_id")
    campaign = _required_string(record.get("campaign"), field="campaign")
    record_pipeline = _required_string(record.get("pipeline_version"), field="pipeline_version")
    version = _required_string(record.get("candidate_version"), field="candidate_version")
    observations_digest = _required_string(
        record.get("observations_digest"), field="observations_digest"
    )
    stored_preflight_digest = _required_string(
        record.get("preflight_digest"), field="preflight_digest"
    )
    if record_pipeline != pipeline_version:
        raise ValueError(f"candidate {candidate_id!r} has inconsistent pipeline_version")
    if expected_candidate_id is not None and candidate_id != expected_candidate_id:
        raise ValueError("candidate payload identity differs from its ledger key")
    if expected_campaign is not None and campaign != expected_campaign:
        raise ValueError(f"candidate {candidate_id!r} campaign differs from its ledger record")
    if expected_version is not None and version != expected_version:
        raise ValueError(f"candidate {candidate_id!r} version differs from its ledger record")
    for field, value in (
        ("candidate_version", version),
        ("observations_digest", observations_digest),
        ("preflight_digest", stored_preflight_digest),
    ):
        if not _SHA256.fullmatch(value):
            raise ValueError(f"candidate {candidate_id!r} has invalid {field}")

    observations = _sequence_of_mappings(record.get("observations"), field="observations")
    if not observations:
        raise ValueError(f"candidate {candidate_id!r} has no observations")
    if any(observation.get("source_id") != candidate_id for observation in observations):
        raise ValueError(f"candidate {candidate_id!r} observations have inconsistent identity")
    computed_observations = candidate_observations_digest(observations)
    if not hmac.compare_digest(computed_observations, observations_digest):
        raise ValueError(f"candidate {candidate_id!r} observations differ from their digest")

    quality = _mapping(record.get("quality"), field="quality")
    quality_passed = quality.get("passed")
    if not isinstance(quality_passed, bool):
        raise ValueError(f"candidate {candidate_id!r} has an invalid quality verdict")
    _string_sequence(quality.get("reasons"), field="quality reasons")
    features = _mapping(record.get("features"), field="features")
    score = _mapping(record.get("score"), field="score")
    gate = _mapping(record.get("automated_gate"), field="automated_gate")
    binding_payload = _mapping(record.get("evidence_binding"), field="evidence_binding")
    scientific_config = _mapping(record.get("scientific_config"), field="scientific_config")
    verification_context = _mapping(
        record.get("verification_context"), field="verification_context"
    )
    position = _mapping(record.get("position"), field="position")
    checks_payload = _sequence_of_mappings(record.get("external_checks"), field="external_checks")
    manual_review_required = record.get("manual_review_required")
    if not isinstance(manual_review_required, bool):
        raise ValueError(f"candidate {candidate_id!r} has invalid manual_review_required")

    position_ra = _finite_coordinate(position.get("ra_deg"), field="position.ra_deg")
    position_dec = _finite_coordinate(position.get("dec_deg"), field="position.dec_deg")
    if not 0 <= position_ra < 360 or not -90 <= position_dec <= 90:
        raise ValueError(f"candidate {candidate_id!r} has invalid sky coordinates")
    context = _binding_context(binding_payload)
    if context.candidate_id != candidate_id:
        raise ValueError(
            f"candidate {candidate_id!r} evidence binding identifies another candidate"
        )
    if position_ra != context.ra_deg or position_dec != context.dec_deg:
        raise ValueError(f"candidate {candidate_id!r} evidence binding uses another sky position")

    basis = candidate_version_basis(
        pipeline_version=pipeline_version,
        candidate_id=candidate_id,
        campaign=campaign,
        observations_digest=observations_digest,
        position=position,
        quality=quality,
        features=features,
        score=score,
        external_checks=checks_payload,
        manual_review_required=manual_review_required,
        automated_gate=gate,
        evidence_binding=binding_payload,
        reporting_preflight_digest=stored_preflight_digest,
        scientific_config=scientific_config,
        verification_context=verification_context,
    )
    computed_version = digest_value(basis)
    if not hmac.compare_digest(computed_version, version):
        raise ValueError(f"candidate {candidate_id!r} evidence differs from candidate_version")

    validation = _mapping(scientific_config.get("validation"), field="validation policy")
    review = _mapping(scientific_config.get("review"), field="review policy")
    stored_review_policy = _mapping(record.get("review_policy"), field="review_policy")
    expected_review_policy = {
        "required_reviewers": review.get("required_reviewers"),
        "require_human_approval": review.get("require_human_approval"),
        "allow_self_approval": review.get("allow_self_approval"),
    }
    if dict(stored_review_policy) != expected_review_policy:
        raise ValueError(f"candidate {candidate_id!r} review policy is inconsistent")
    required_reviewers = review.get("required_reviewers")
    if (
        isinstance(required_reviewers, bool)
        or not isinstance(required_reviewers, int)
        or required_reviewers < 1
    ):
        raise ValueError(f"candidate {candidate_id!r} has invalid reviewer policy")
    if review.get("require_human_approval") is not True:
        raise ValueError(f"candidate {candidate_id!r} disables mandatory human approval")
    if review.get("allow_self_approval") is not False:
        raise ValueError(f"candidate {candidate_id!r} permits unsafe self-approval")
    required_checks = validation.get("required_checks")
    if isinstance(required_checks, (str, bytes)) or not isinstance(required_checks, Sequence):
        raise ValueError(f"candidate {candidate_id!r} has invalid required-check policy")
    if any(not isinstance(service, str) or not service.strip() for service in required_checks):
        raise ValueError(f"candidate {candidate_id!r} has invalid required-check policy")
    normalized_required_checks = tuple(service.strip().casefold() for service in required_checks)
    if not normalized_required_checks:
        raise ValueError(f"candidate {candidate_id!r} has an empty required-check policy")
    if len(set(normalized_required_checks)) != len(normalized_required_checks):
        raise ValueError(f"candidate {candidate_id!r} has duplicate required checks")
    if set(normalized_required_checks) - set(MANDATORY_SERVICES):
        raise ValueError(f"candidate {candidate_id!r} has unsupported required checks")
    try:
        checks = tuple(CheckProvenance.from_dict(payload) for payload in checks_payload)
        bound_checks = bind_completed_checks(checks, context)
        if tuple(check.to_dict() for check in checks) != tuple(
            check.to_dict() for check in bound_checks
        ):
            raise ValueError("external checks are not valid for the bound candidate and policy")
        if manual_review_required:
            simbad_checks = tuple(check for check in checks if check.service == "simbad")
            if (
                "simbad" not in normalized_required_checks
                or len(simbad_checks) != 1
                or simbad_checks[0].status is not CheckStatus.CLEAR
            ):
                raise ValueError("manual review is not backed by one relevant clear SIMBAD check")
        raw_gate_decision = gate.get("decision")
        if not isinstance(raw_gate_decision, str):
            raise ValueError("automated gate has an invalid decision")
        try:
            gate_decision = GateDecision(raw_gate_decision)
        except (TypeError, ValueError) as exc:
            raise ValueError("automated gate has an invalid decision") from exc
        for field in ("reasons", "missing_services", "matched_services"):
            _string_sequence(gate.get(field), field=f"automated gate {field}")
        if "reportable" in gate:
            gate_reportable = gate["reportable"]
            if not isinstance(gate_reportable, bool) or gate_reportable != (
                gate_decision is GateDecision.REPORTABLE
            ):
                raise ValueError("automated gate has an inconsistent reportable flag")
        required_evidence = {
            service: tuple(check for check in checks if check.service == service)
            for service in normalized_required_checks
        }
        if gate_decision is GateDecision.REPORTABLE:
            if not quality_passed or manual_review_required:
                raise ValueError("reportable gate contradicts quality or manual-review evidence")
            if any(
                len(service_checks) != 1
                or service_checks[0].status is not CheckStatus.CLEAR
                or service_checks[0].clear_integrity_error is not None
                for service_checks in required_evidence.values()
            ):
                raise ValueError("reportable gate lacks one clear record per required service")
        if (
            any(
                check.status is CheckStatus.MATCH
                for service_checks in required_evidence.values()
                for check in service_checks
            )
            and gate_decision is not GateDecision.REJECT_KNOWN_OBJECT
        ):
            raise ValueError("automated gate ignores a known-object match")
        computed_preflight = preflight_digest(
            context=context,
            checks=bound_checks,
            quality_passed=quality_passed,
            manual_review_required=manual_review_required,
            mandatory_services=normalized_required_checks,
            required_reviewers=required_reviewers,
            verification_context=verification_context,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"candidate {candidate_id!r} has invalid preflight evidence") from exc
    if not hmac.compare_digest(computed_preflight, stored_preflight_digest):
        raise ValueError(f"candidate {candidate_id!r} preflight evidence differs from its digest")
    return version


def verify_candidate_record(
    record: Mapping[str, Any],
    *,
    pipeline_version: str,
) -> str:
    """Verify observation, version, preflight, and whole-record integrity.

    The returned value is the verified complete-record digest.  Any mismatch is
    rejected instead of trusting self-asserted digest strings in imported JSON.
    """

    candidate_id = _required_string(record.get("candidate_id"), field="candidate_id")
    _required_string(record.get("run_id"), field="run_id")
    _required_string(record.get("scientific_fingerprint"), field="scientific_fingerprint")
    verify_candidate_version_payload(record, pipeline_version=pipeline_version)
    stored_record_digest = record.get("candidate_record_digest")
    if not isinstance(stored_record_digest, str) or not _SHA256.fullmatch(stored_record_digest):
        raise ValueError(f"candidate {candidate_id!r} has invalid candidate_record_digest")

    computed_record_digest = candidate_record_digest(record)
    if not hmac.compare_digest(computed_record_digest, stored_record_digest):
        raise ValueError(f"candidate {candidate_id!r} record differs from its digest")
    verify_candidate_run_binding(record)
    return computed_record_digest


__all__ = [
    "CANDIDATE_EVIDENCE_SCHEMA",
    "CANDIDATE_OBSERVATIONS_SCHEMA",
    "CANDIDATE_RECORD_SCHEMA",
    "CANDIDATE_RUN_BINDING_SCHEMA",
    "candidate_observations_digest",
    "candidate_record_digest",
    "candidate_run_binding_digest",
    "candidate_version_basis",
    "canonical_check_payloads",
    "verify_candidate_record",
    "verify_candidate_run_binding",
    "verify_candidate_version_payload",
]
