"""Deterministic local IRIS analysis pipeline.

This stage performs only evidence-preserving local work: schema validation,
band-aware feature extraction, transparent heuristic ranking, durable run
products, and ledger updates.  It never treats an unavailable external check
as a clear result and never makes a candidate reportable without independent
human approval.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from iris.atomic import atomic_write_bytes, atomic_write_text
from iris.config import IRISConfig, config_to_dict
from iris.data import create_snapshot
from iris.domain import CandidateState
from iris.evidence_context import serialized_verification_context
from iris.features import compute_photometry_features, flatten_photometry_features
from iris.ingest import IngestionBatch, ingest_csv, representative_coordinates
from iris.integrity import (
    candidate_observations_digest,
    candidate_record_digest,
    candidate_run_binding_digest,
    candidate_version_basis,
    canonical_check_payloads,
)
from iris.ledger import OutcomeLedger
from iris.manifest import RunManifest
from iris.provenance import CheckProvenance, CheckStatus, digest_file, digest_value
from iris.scoring import HeuristicScoreConfig, score_photometry_candidate
from iris.validation.binding import (
    EvidenceBindingContext,
    bind_completed_check,
    preflight_digest,
)
from iris.validation.gates import GateDecision, GateOutcome, evaluate_reportability

PIPELINE_VERSION = "iris.local_analysis.v4"
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True, slots=True)
class AnalysisRunResult:
    """Paths and high-level counts produced by a completed local run."""

    run_id: str
    scientific_fingerprint: str
    run_dir: Path
    normalized_photometry_path: Path
    features_path: Path
    ranked_candidates_path: Path
    candidates_path: Path
    snapshot_path: Path
    manifest_path: Path
    ledger_path: Path
    candidate_count: int
    reportable_count: int
    blocked_count: int


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is pd.NA:
        return None
    return value


def _atomic_text(path: Path, content: str) -> None:
    atomic_write_text(path, content)


def _atomic_bytes(path: Path, content: bytes) -> None:
    atomic_write_bytes(path, content)


def _atomic_json(path: Path, value: Any) -> None:
    content = json.dumps(_json_value(value), indent=2, sort_keys=True, allow_nan=False)
    _atomic_text(path, content + "\n")


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    content = frame.to_csv(index=False, lineterminator="\n", float_format="%.17g")
    _atomic_text(path, content)


def _register_existing_artifacts(
    manifest: RunManifest,
    artifacts: Iterable[tuple[Path, str]],
) -> None:
    """Best-effort inventory of finalized files after a failed/interrupted run."""

    registered = {artifact.path for artifact in manifest.artifacts}
    for path, role in artifacts:
        resolved = str(path.resolve())
        if resolved in registered or not path.is_file():
            continue
        try:
            manifest.add_artifact(path, role)
        except OSError as exc:
            manifest.warnings.append(
                f"could not hash partial artifact {path.name}: {type(exc).__name__}: {exc}"
            )


def _scientific_config(config: IRISConfig) -> dict[str, Any]:
    payload = config_to_dict(config)
    payload.pop("storage", None)
    payload.pop("source_path", None)
    return payload


def _scientific_source_provenance(provenance: Mapping[str, Any]) -> dict[str, Any]:
    """Remove storage/time metadata that cannot change scientific results."""

    volatile = {
        "path",
        "size_bytes",
        "source_modified_at",
        "retrieved_at",
        "sidecar_sha256",
    }

    def clean(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): clean(item) for key, item in value.items() if str(key) not in volatile
            }
        if isinstance(value, (list, tuple)):
            return [clean(item) for item in value]
        return _json_value(value)

    cleaned = clean(provenance)
    if not isinstance(cleaned, dict):
        raise TypeError("source provenance must remain a mapping")
    return cleaned


def _frame_digest(frame: pd.DataFrame) -> str:
    stable = frame.to_csv(index=False, lineterminator="\n", float_format="%.17g")
    return digest_value({"schema": list(frame.columns), "csv": stable})


def _checks_payload(
    checks_by_candidate: Mapping[str, Iterable[CheckProvenance]] | None,
) -> dict[str, list[dict[str, Any]]]:
    if not checks_by_candidate:
        return {}
    materialized = _materialize_checks(checks_by_candidate)
    return {
        candidate_id: canonical_check_payloads(checks)
        for candidate_id, checks in sorted(materialized.items())
    }


def _materialize_checks(
    values: Mapping[str, Iterable[CheckProvenance]] | None,
) -> dict[str, tuple[CheckProvenance, ...]]:
    materialized: dict[str, tuple[CheckProvenance, ...]] = {}
    for raw_candidate_id, raw_checks in (values or {}).items():
        candidate_id = str(raw_candidate_id).strip()
        if not candidate_id:
            raise ValueError("external-check candidate IDs must be non-empty")
        if candidate_id in materialized:
            raise ValueError(f"duplicate normalized external-check candidate ID: {candidate_id!r}")
        checks = tuple(raw_checks)
        if any(not isinstance(check, CheckProvenance) for check in checks):
            raise TypeError("external checks must be CheckProvenance records")
        materialized[candidate_id] = checks
    return materialized


def _manual_review_flags(
    values: Mapping[str, bool] | None,
) -> dict[str, bool]:
    flags: dict[str, bool] = {}
    for raw_candidate_id, required in (values or {}).items():
        candidate_id = str(raw_candidate_id).strip()
        if not candidate_id:
            raise ValueError("manual-review candidate IDs must be non-empty")
        if not isinstance(required, bool):
            raise TypeError("manual-review flags must be boolean")
        if candidate_id in flags:
            raise ValueError(f"duplicate normalized manual-review candidate ID: {candidate_id!r}")
        flags[candidate_id] = required
    return flags


def _verification_contexts(
    frame: pd.DataFrame,
    values: Mapping[str, Mapping[str, Any]] | None,
    manual_flags: Mapping[str, bool],
) -> dict[str, dict[str, list[str]]]:
    supplied: dict[str, Mapping[str, Any]] = {}
    for raw_candidate_id, context in (values or {}).items():
        candidate_id = str(raw_candidate_id).strip()
        if not candidate_id:
            raise ValueError("verification-context candidate IDs must be non-empty")
        if candidate_id in supplied:
            raise ValueError(
                f"duplicate normalized verification-context candidate ID: {candidate_id!r}"
            )
        if not isinstance(context, Mapping):
            raise TypeError("verification contexts must be mappings")
        supplied[candidate_id] = context
    known_ids = set(frame["source_id"].astype(str))
    unknown = sorted((set(supplied) | set(manual_flags)) - known_ids)
    if unknown:
        raise ValueError(
            "manual/context evidence supplied for candidates absent from this batch: "
            + ", ".join(unknown)
        )
    contexts: dict[str, dict[str, list[str]]] = {}
    for grouped_candidate_id, group in frame.groupby("source_id", sort=True):
        source_id = str(grouped_candidate_id)
        contexts[source_id] = serialized_verification_context(
            supplied.get(source_id),
            manual_review_required=manual_flags.get(source_id, False),
            expected_skybot_reference_mjds=_skybot_reference_mjds(group),
        )
    return contexts


def deterministic_run_id(
    batch: IngestionBatch,
    config: IRISConfig,
    *,
    checks_by_candidate: Mapping[str, Iterable[CheckProvenance]] | None = None,
    manual_review_by_candidate: Mapping[str, bool] | None = None,
    context_by_candidate: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """Derive a stable run identity from scientific inputs, not output paths."""

    manual_flags = _manual_review_flags(manual_review_by_candidate)
    contexts = _verification_contexts(batch.observations, context_by_candidate, manual_flags)
    fingerprint = digest_value(
        {
            "pipeline_version": PIPELINE_VERSION,
            "observations": _frame_digest(batch.observations),
            "source_provenance": _scientific_source_provenance(batch.provenance),
            "config": _scientific_config(config),
            "checks": _checks_payload(checks_by_candidate),
            "manual_review": dict(sorted(manual_flags.items())),
            "verification_context": dict(sorted(contexts.items())),
        }
    )
    return f"analysis-{fingerprint[:16]}"


def _validated_run_id(value: str) -> str:
    if not _RUN_ID.fullmatch(value):
        raise ValueError(
            "run_id must contain only letters, digits, dots, underscores, or hyphens "
            "and cannot exceed 128 characters"
        )
    return value


def _candidate_checks(
    context: EvidenceBindingContext,
    *,
    required: tuple[str, ...],
    provided: Iterable[CheckProvenance] | None,
    checked_at: str,
) -> tuple[CheckProvenance, ...]:
    by_service: dict[str, CheckProvenance] = {}
    for raw in provided or ():
        check = bind_completed_check(raw, context)
        if check.service in by_service:
            raise ValueError(
                f"candidate {context.candidate_id!r} has duplicate {check.service!r} checks"
            )
        by_service[check.service] = check

    try:
        checked = datetime.fromisoformat(checked_at)
    except ValueError:
        checked = datetime.now(UTC)
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=UTC)
    expiry = (checked + timedelta(hours=context.max_ttl_hours)).isoformat()
    for service in required:
        if service not in by_service:
            by_service[service] = CheckProvenance(
                service=service,
                status=CheckStatus.PENDING,
                checked_at=checked.isoformat(),
                expires_at=expiry,
                query={
                    "candidate_id": context.candidate_id,
                    "ra_deg": context.ra_deg,
                    "dec_deg": context.dec_deg,
                },
                attempts=0,
            )
    ordered = [by_service.pop(service) for service in required]
    ordered.extend(by_service[name] for name in sorted(by_service))
    return tuple(ordered)


def _feature_input(
    group: pd.DataFrame,
    *,
    quality_column_supplied: bool,
) -> pd.DataFrame:
    observations = group.drop(columns=["source_id", "ra_deg", "dec_deg"])
    if (
        "quality" in observations
        and observations["quality"].isna().all()
        and not quality_column_supplied
    ):
        observations = observations.drop(columns=["quality"])
    return observations


def _quality_column_supplied(batch: IngestionBatch) -> bool:
    column_map = batch.provenance.get("column_map")
    return isinstance(column_map, Mapping) and "quality" in column_map


def _quality(features: Mapping[str, Any], minimum_detections: int) -> tuple[bool, tuple[str, ...]]:
    reasons: list[str] = []
    if int(features.get("n_detections", 0)) < minimum_detections:
        reasons.append(f"fewer than {minimum_detections} valid detections")
    if int(features.get("n_bands", 0)) < 1:
        reasons.append("no passband has valid detections")
    if float(features.get("missing_critical_fraction", 1.0)) >= 1.0:
        reasons.append("all photometry is missing critical measurement fields")
    if float(features.get("measurement_error_missing_fraction", 1.0)) >= 1.0:
        reasons.append("all detection measurement uncertainties are missing or invalid")
    return not reasons, tuple(reasons)


def _candidate_version_digest(
    *,
    candidate_id: str,
    campaign: str,
    observations_digest: str,
    ra_deg: float,
    dec_deg: float,
    quality_passed: bool,
    quality_reasons: tuple[str, ...],
    features: Mapping[str, Any],
    score: Mapping[str, Any],
    checks: tuple[CheckProvenance, ...],
    manual_review_required: bool,
    verification_context: Mapping[str, Any],
    gate: GateOutcome,
    evidence_binding: EvidenceBindingContext,
    reporting_preflight_digest: str,
    scientific_config: Mapping[str, Any],
) -> str:
    basis = candidate_version_basis(
        pipeline_version=PIPELINE_VERSION,
        candidate_id=candidate_id,
        campaign=campaign,
        observations_digest=observations_digest,
        position={"ra_deg": ra_deg, "dec_deg": dec_deg},
        quality={"passed": quality_passed, "reasons": quality_reasons},
        features=features,
        score=score,
        external_checks=checks,
        manual_review_required=manual_review_required,
        verification_context=verification_context,
        automated_gate={
            "decision": gate.decision.value,
            "reasons": gate.reasons,
            "missing_services": gate.missing_services,
            "matched_services": gate.matched_services,
        },
        evidence_binding=evidence_binding.to_dict(),
        reporting_preflight_digest=reporting_preflight_digest,
        scientific_config=scientific_config,
    )
    return digest_value(_json_value(basis))


def _skybot_reference_mjds(group: pd.DataFrame) -> tuple[float, ...]:
    """Return every distinct usable detection epoch requiring moving-object clearance."""

    detections = group["is_detection"].astype(bool)
    quality = group["quality"]
    usable_quality = quality.isna() | quality.astype("boolean").fillna(False)
    values = pd.to_numeric(group.loc[detections & usable_quality, "mjd"], errors="coerce")
    return tuple(sorted({float(value) for value in values if math.isfinite(float(value))}))


def _candidate_state(gate: GateDecision, *, approved: bool) -> CandidateState:
    if gate in {GateDecision.REJECT_KNOWN_OBJECT, GateDecision.REJECT_QUALITY}:
        return CandidateState.REJECTED
    if approved:
        return CandidateState.APPROVED
    return CandidateState.NEEDS_REVIEW


def analyze_batch(
    batch: IngestionBatch,
    config: IRISConfig,
    *,
    output_dir: str | Path | None = None,
    ledger: OutcomeLedger | None = None,
    ledger_path: str | Path | None = None,
    checks_by_candidate: Mapping[str, Iterable[CheckProvenance]] | None = None,
    manual_review_by_candidate: Mapping[str, bool] | None = None,
    context_by_candidate: Mapping[str, Mapping[str, Any]] | None = None,
    run_id: str | None = None,
) -> AnalysisRunResult:
    """Analyze one canonical ingestion batch and persist auditable products.

    ``checks_by_candidate`` is the only route by which completed external
    evidence enters this local stage.  Missing checks are materialized as
    ``pending`` and block reportability.  Even all-clear checks require the
    independent approvals recorded in the outcome ledger.
    """

    if ledger is not None and ledger_path is not None:
        raise ValueError("pass either ledger or ledger_path, not both")
    frame = batch.to_frame()
    if frame.empty:
        raise ValueError("analysis batch is empty")
    materialized_checks = _materialize_checks(checks_by_candidate)
    manual_flags = _manual_review_flags(manual_review_by_candidate)
    verification_contexts = _verification_contexts(frame, context_by_candidate, manual_flags)
    scientific_fingerprint = deterministic_run_id(
        batch,
        config,
        checks_by_candidate=materialized_checks,
        manual_review_by_candidate=manual_flags,
        context_by_candidate=verification_contexts,
    )
    config_payload = config_to_dict(config)
    candidate_scientific_config: dict[str, Any] = {
        name: config_payload[name]
        for name in ("hunt", "validation", "ranking", "review")
        if name in config_payload
    }
    gate_evaluated_at = datetime.now(UTC)
    manifest = RunManifest.create(
        {
            "pipeline_version": PIPELINE_VERSION,
            "scientific_fingerprint": scientific_fingerprint,
            "gate_evaluated_at": gate_evaluated_at.isoformat(),
            "iris": config_payload,
            "ingestion": _json_value(batch.provenance),
        },
        command=["iris", "analyze", batch.source],
        project_root=Path(__file__).resolve().parents[2],
    )
    selected_run_id = _validated_run_id(run_id or manifest.run_id)
    manifest.run_id = selected_run_id
    runs_root = Path(output_dir).expanduser().resolve() if output_dir else config.storage.runs_dir
    run_dir = runs_root / selected_run_id
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_dir.mkdir()
    except FileExistsError as exc:
        raise FileExistsError(
            f"run directory already exists and will not be overwritten: {run_dir}"
        ) from exc

    normalized_path = run_dir / "photometry.normalized.csv"
    features_path = run_dir / "features.csv"
    ranked_path = run_dir / "ranked_candidates.csv"
    candidates_path = run_dir / "candidates.json"
    snapshot_path = run_dir / "dataset.snapshot.json"
    manifest_path = run_dir / "manifest.json"
    source_snapshot_path = (
        run_dir / "source.input.csv" if batch.source_content is not None else None
    )
    artifact_roles: list[tuple[Path, str]] = [
        (normalized_path, "normalized-photometry"),
        (features_path, "band-aware-features"),
        (ranked_path, "review-ranking"),
        (candidates_path, "candidate-evidence"),
        (snapshot_path, "dataset-snapshot"),
    ]
    if source_snapshot_path is not None:
        artifact_roles.append((source_snapshot_path, "source-input-snapshot"))

    effective_ledger = ledger or OutcomeLedger(
        Path(ledger_path).expanduser().resolve()
        if ledger_path is not None
        else config.storage.root / "outcomes.sqlite"
    )
    manifest.warnings.extend(batch.warnings)

    try:
        if source_snapshot_path is not None:
            _atomic_bytes(source_snapshot_path, batch.source_content or b"")
        _atomic_csv(normalized_path, frame)
        snapshot = create_snapshot(
            f"{selected_run_id}-photometry",
            [normalized_path],
            label_policy="unlabelled candidate photometry; outcomes live in the ledger",
            split_policy="not-applicable-local-analysis",
        )
        _atomic_json(snapshot_path, asdict(snapshot))

        feature_rows: list[dict[str, Any]] = []
        ranking_rows: list[dict[str, Any]] = []
        candidate_records: list[dict[str, Any]] = []
        ledger_updates: list[dict[str, Any]] = []
        known_ids = set(frame["source_id"].astype(str))
        supplied_ids = set(materialized_checks)
        ignored_ids = sorted(str(item) for item in supplied_ids - known_ids)
        if ignored_ids:
            manifest.warnings.append(
                "checks supplied for candidates absent from this batch: " + ", ".join(ignored_ids)
            )

        required = tuple(config.validation.required_checks)
        required_radii = {
            "tns": config.validation.tns_radius_arcsec,
            "skybot": config.validation.skybot_radius_arcsec,
            "simbad": config.validation.catalog_radius_arcsec,
            "vsx": config.validation.catalog_radius_arcsec,
        }
        score_config = HeuristicScoreConfig(
            amplitude_weight=config.ranking.amplitude_weight,
            significance_weight=config.ranking.significance_weight,
            temporal_weight=config.ranking.temporal_weight,
            nondetection_weight=config.ranking.nondetection_weight,
            sampling_weight=config.ranking.sampling_weight,
            quality_weight=config.ranking.quality_weight,
        )
        quality_column_supplied = _quality_column_supplied(batch)
        for candidate_id, group in frame.groupby("source_id", sort=True):
            source_id = str(candidate_id)
            observation_records = _json_value(group.to_dict(orient="records"))
            observations_digest = candidate_observations_digest(observation_records)
            ra_deg, dec_deg = representative_coordinates(group)
            features = compute_photometry_features(
                _feature_input(
                    group,
                    quality_column_supplied=quality_column_supplied,
                )
            )
            score = score_photometry_candidate(features, config=score_config)
            quality_passed, quality_reasons = _quality(features, config.hunt.min_detections)
            binding_context = EvidenceBindingContext(
                candidate_id=source_id,
                ra_deg=ra_deg,
                dec_deg=dec_deg,
                max_ttl_hours=config.validation.evidence_ttl_hours,
                required_radii_arcsec=required_radii,
                skybot_reference_mjds=_skybot_reference_mjds(group),
            )
            checks = _candidate_checks(
                binding_context,
                required=required,
                provided=materialized_checks.get(source_id),
                checked_at=batch.retrieved_at,
            )
            manual_required = bool(manual_flags.get(source_id, False))
            verification_context = verification_contexts[source_id]
            if manual_required:
                simbad_checks = tuple(check for check in checks if check.service == "simbad")
                if (
                    "simbad" not in required
                    or len(simbad_checks) != 1
                    or simbad_checks[0].status is not CheckStatus.CLEAR
                ):
                    raise ValueError(
                        f"candidate {source_id!r} manual review is not backed by "
                        "one relevant clear SIMBAD check"
                    )
            automated_gate = evaluate_reportability(
                checks,
                quality_passed=quality_passed,
                manual_review_required=manual_required,
                mandatory_services=required,
                at=gate_evaluated_at,
            )
            candidate_preflight_digest = preflight_digest(
                context=binding_context,
                checks=checks,
                quality_passed=quality_passed,
                manual_review_required=manual_required,
                mandatory_services=required,
                required_reviewers=config.review.required_reviewers,
                verification_context=verification_context,
            )
            automated_gate_payload = {
                "decision": automated_gate.decision.value,
                "reportable": automated_gate.reportable,
                "reasons": list(automated_gate.reasons),
                "missing_services": list(automated_gate.missing_services),
                "matched_services": list(automated_gate.matched_services),
            }
            candidate_version = _candidate_version_digest(
                candidate_id=source_id,
                campaign=config.general.campaign,
                observations_digest=observations_digest,
                ra_deg=ra_deg,
                dec_deg=dec_deg,
                quality_passed=quality_passed,
                quality_reasons=quality_reasons,
                features=features,
                score=score,
                checks=checks,
                manual_review_required=manual_required,
                verification_context=verification_context,
                gate=automated_gate,
                evidence_binding=binding_context,
                reporting_preflight_digest=candidate_preflight_digest,
                scientific_config=candidate_scientific_config,
            )

            provisional_payload = {
                "run_id": selected_run_id,
                "scientific_fingerprint": scientific_fingerprint,
                "candidate_id": source_id,
                "pipeline_version": PIPELINE_VERSION,
                "candidate_version": candidate_version,
                "preflight_digest": candidate_preflight_digest,
                "gate_evaluated_at": gate_evaluated_at.isoformat(),
                "origin": batch.source,
                "campaign": config.general.campaign,
                "observations_digest": observations_digest,
                "observations": observation_records,
                "position": {"ra_deg": ra_deg, "dec_deg": dec_deg},
                "ra_deg": ra_deg,
                "dec_deg": dec_deg,
                "priority_score": score["priority_score"],
                "gate_decision": automated_gate.decision.value,
                "quality": {
                    "passed": quality_passed,
                    "reasons": list(quality_reasons),
                },
                "features": _json_value(features),
                "score": _json_value(score),
                "external_checks": [check.to_dict() for check in checks],
                "automated_gate": automated_gate_payload,
                "manual_review_required": manual_required,
                "verification_context": verification_context,
                "review_policy": {
                    "required_reviewers": config.review.required_reviewers,
                    "require_human_approval": config.review.require_human_approval,
                    "allow_self_approval": config.review.allow_self_approval,
                },
                "evidence_binding": binding_context.to_dict(),
                "scientific_config": candidate_scientific_config,
            }
            current_candidate = effective_ledger.candidate(source_id)
            version_is_current = bool(
                current_candidate is not None
                and current_candidate.get("version_digest") == candidate_version
            )
            if manual_required and version_is_current:
                adjudicated, adjudication_reason = effective_ledger.manual_adjudication(
                    source_id,
                    candidate_version=candidate_version,
                )
            elif manual_required:
                adjudicated = False
                adjudication_reason = "ambiguous catalogue context needs scientific adjudication"
            else:
                adjudicated, adjudication_reason = True, "scientific adjudication not required"
            gate = evaluate_reportability(
                checks,
                quality_passed=quality_passed,
                manual_review_required=manual_required and not adjudicated,
                mandatory_services=required,
                at=gate_evaluated_at,
            )
            gate_payload = {
                "decision": gate.decision.value,
                "reportable": gate.reportable,
                "reasons": list(gate.reasons),
                "missing_services": list(gate.missing_services),
                "matched_services": list(gate.matched_services),
            }
            if version_is_current:
                approved, approval_reason = effective_ledger.independent_approval(
                    source_id,
                    required_reviewers=config.review.required_reviewers,
                    candidate_version=candidate_version,
                )
            else:
                approved = False
                approval_reason = "missing screener approval"
            reportable = bool(gate.reportable and approved)
            state = _candidate_state(gate.decision, approved=reportable)
            provisional_payload.update(
                {
                    "state": state.value,
                    "reportable": reportable,
                    "approval_reason": approval_reason,
                    "gate_decision": gate.decision.value,
                    "gate": gate_payload,
                    "manual_adjudication": {
                        "resolved": adjudicated,
                        "reason": adjudication_reason,
                    },
                }
            )
            ledger_updates.append(
                {
                    "candidate_id": source_id,
                    "campaign": config.general.campaign,
                    "state": state.value,
                    "payload": provisional_payload,
                    "version_digest": candidate_version,
                }
            )

            flat_features = flatten_photometry_features(features)
            feature_rows.append({"candidate_id": source_id, **flat_features})
            check_statuses = {check.service: check.status.value for check in checks}
            component_scores = {
                f"component_{name}_score": values["score"]
                for name, values in score["components"].items()
            }
            candidate_record = _json_value(
                {
                    "run_id": selected_run_id,
                    "scientific_fingerprint": scientific_fingerprint,
                    "candidate_id": source_id,
                    "pipeline_version": PIPELINE_VERSION,
                    "candidate_version": candidate_version,
                    "preflight_digest": candidate_preflight_digest,
                    "gate_evaluated_at": gate_evaluated_at.isoformat(),
                    "observations_digest": observations_digest,
                    "observations": observation_records,
                    "position": {"ra_deg": ra_deg, "dec_deg": dec_deg},
                    "origin": batch.source,
                    "campaign": config.general.campaign,
                    "state": state.value,
                    "quality": {"passed": quality_passed, "reasons": quality_reasons},
                    "features": features,
                    "score": score,
                    "external_checks": [check.to_dict() for check in checks],
                    "automated_gate": automated_gate_payload,
                    "gate": gate_payload,
                    "manual_review_required": manual_required,
                    "verification_context": verification_context,
                    "review_policy": {
                        "required_reviewers": config.review.required_reviewers,
                        "require_human_approval": config.review.require_human_approval,
                        "allow_self_approval": config.review.allow_self_approval,
                    },
                    "scientific_config": candidate_scientific_config,
                    "manual_adjudication": {
                        "resolved": adjudicated,
                        "reason": adjudication_reason,
                    },
                    "evidence_binding": binding_context.to_dict(),
                    "independent_review": {"approved": approved, "reason": approval_reason},
                    "reportable": reportable,
                }
            )
            candidate_record["candidate_record_digest"] = candidate_record_digest(candidate_record)
            candidate_record["candidate_run_binding_digest"] = candidate_run_binding_digest(
                candidate_record
            )
            provisional_payload["candidate_record_digest"] = candidate_record[
                "candidate_record_digest"
            ]
            provisional_payload["candidate_run_binding_digest"] = candidate_record[
                "candidate_run_binding_digest"
            ]
            candidate_records.append(candidate_record)
            ranking_rows.append(
                {
                    "scientific_fingerprint": scientific_fingerprint,
                    "pipeline_version": PIPELINE_VERSION,
                    "candidate_id": source_id,
                    "candidate_version": candidate_version,
                    "candidate_record_digest": candidate_record["candidate_record_digest"],
                    "ra_deg": ra_deg,
                    "dec_deg": dec_deg,
                    "campaign": config.general.campaign,
                    "priority_score": score["priority_score"],
                    "score_kind": score["score_kind"],
                    "is_probability": score["is_probability"],
                    **component_scores,
                    "quality_passed": quality_passed,
                    "gate_decision": gate.decision.value,
                    "gate_reportable": gate.reportable,
                    # Review eligibility is deliberately broader than reportability:
                    # quality-passing candidates with pending/error evidence may be
                    # triaged, but known-object and quality vetoes remain excluded.
                    "review_queue_eligible": quality_passed
                    and gate.decision
                    not in {GateDecision.REJECT_KNOWN_OBJECT, GateDecision.REJECT_QUALITY},
                    "independent_review_approved": approved,
                    "manual_adjudication_resolved": adjudicated,
                    "reportable": reportable,
                    "candidate_state": state.value,
                    **{f"check_{name}": check_statuses.get(name, "missing") for name in required},
                    "block_reasons": json.dumps(list(gate.reasons), sort_keys=True),
                    "quality_reasons": json.dumps(list(quality_reasons), sort_keys=True),
                    "score_warnings": json.dumps(score["warnings"], sort_keys=True),
                    "approval_reason": approval_reason,
                    "adjudication_reason": adjudication_reason,
                }
            )
            for check in checks:
                manifest.add_check(check)

        features_frame = pd.DataFrame.from_records(feature_rows).sort_values(
            "candidate_id", kind="stable"
        )
        ranked_frame = pd.DataFrame.from_records(ranking_rows).sort_values(
            ["priority_score", "candidate_id"], ascending=[False, True], kind="stable"
        )
        candidate_records.sort(key=lambda item: str(item["candidate_id"]))
        _atomic_csv(features_path, features_frame)
        _atomic_csv(ranked_path, ranked_frame)
        _atomic_json(
            candidates_path,
            {
                "schema": "iris.candidates.v1",
                "run_id": selected_run_id,
                "scientific_fingerprint": scientific_fingerprint,
                "pipeline_version": PIPELINE_VERSION,
                "candidates": candidate_records,
            },
        )

        for path, role in artifact_roles:
            manifest.add_artifact(path, role)
        reportable_count = sum(bool(item["reportable"]) for item in candidate_records)
        blocked_count = len(candidate_records) - reportable_count
        manifest.finish(
            status="completed",
            metrics={
                "candidate_count": len(candidate_records),
                "observation_count": len(frame),
                "reportable_count": reportable_count,
                "blocked_count": blocked_count,
                "dataset_digest": snapshot.digest,
            },
        )
        manifest.write(manifest_path)
        manifest_sha256 = digest_file(manifest_path)
        for update in ledger_updates:
            payload = update["payload"]
            if not isinstance(payload, dict):
                raise TypeError("internal candidate payload is not mutable")
            payload["publication"] = {
                "schema": "iris.run_publication.v1",
                "run_id": selected_run_id,
                "manifest_path": str(manifest_path.resolve()),
                "manifest_sha256": manifest_sha256,
                "status": "completed",
            }
        # The ledger is published only after the terminal manifest is durable.
        # A crash in the opposite window can leave a completed manifest without
        # ledger state, which is fail-closed; it can never leave an authorizable
        # ledger candidate whose claimed manifest was not written first.
        effective_ledger.upsert_candidates(ledger_updates)
    except KeyboardInterrupt:
        if manifest.status == "running":
            _register_existing_artifacts(manifest, artifact_roles)
            manifest.warnings.append("pipeline interrupted by user")
            manifest.finish(
                status="interrupted",
                metrics={"partial_artifact_count": len(manifest.artifacts)},
            )
        else:
            manifest.status = "interrupted"
            manifest.completed_at = datetime.now(UTC).isoformat()
            manifest.warnings.append("pipeline interrupted during publication")
        with suppress(OSError):
            manifest.write(manifest_path)
        raise
    except Exception as exc:
        if manifest.status == "running":
            _register_existing_artifacts(manifest, artifact_roles)
            manifest.warnings.append(f"pipeline failed: {type(exc).__name__}: {exc}")
            manifest.finish(
                status="failed",
                metrics={"partial_artifact_count": len(manifest.artifacts)},
            )
        else:
            manifest.status = "failed"
            manifest.completed_at = datetime.now(UTC).isoformat()
            manifest.warnings.append(f"pipeline publication failed: {type(exc).__name__}: {exc}")
        with suppress(OSError):
            manifest.write(manifest_path)
        raise

    return AnalysisRunResult(
        run_id=selected_run_id,
        scientific_fingerprint=scientific_fingerprint,
        run_dir=run_dir,
        normalized_photometry_path=normalized_path,
        features_path=features_path,
        ranked_candidates_path=ranked_path,
        candidates_path=candidates_path,
        snapshot_path=snapshot_path,
        manifest_path=manifest_path,
        ledger_path=effective_ledger.path,
        candidate_count=len(candidate_records),
        reportable_count=reportable_count,
        blocked_count=blocked_count,
    )


def analyze_csv(
    path: str | Path,
    config: IRISConfig,
    *,
    column_map: Mapping[str, str] | None = None,
    coordinate_tolerance_arcsec: float = 2.0,
    output_dir: str | Path | None = None,
    ledger: OutcomeLedger | None = None,
    ledger_path: str | Path | None = None,
    checks_by_candidate: Mapping[str, Iterable[CheckProvenance]] | None = None,
    manual_review_by_candidate: Mapping[str, bool] | None = None,
    context_by_candidate: Mapping[str, Mapping[str, Any]] | None = None,
    run_id: str | None = None,
) -> AnalysisRunResult:
    """Ingest a CSV and execute :func:`analyze_batch`."""

    batch = ingest_csv(
        path,
        column_map=column_map,
        coordinate_tolerance_arcsec=coordinate_tolerance_arcsec,
    )
    return analyze_batch(
        batch,
        config,
        output_dir=output_dir,
        ledger=ledger,
        ledger_path=ledger_path,
        checks_by_candidate=checks_by_candidate,
        manual_review_by_candidate=manual_review_by_candidate,
        context_by_candidate=context_by_candidate,
        run_id=run_id,
    )


__all__ = [
    "AnalysisRunResult",
    "PIPELINE_VERSION",
    "analyze_batch",
    "analyze_csv",
    "deterministic_run_id",
]
