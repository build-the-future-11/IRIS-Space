"""Build portable, evidence-bound nightly review sets.

A review set is decision support, not reporting authorization.  It packages the
exact candidate/ranking inputs, an explicit finite-capacity selection policy, and
one immutable dossier for every selected candidate.  Random audit selections
retain their logged inclusion propensity so downstream evaluation can recover an
unbiased denominator.
"""

from __future__ import annotations

import json
import math
import shutil
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from iris.integrity import verify_candidate_record
from iris.provenance import digest_file, digest_value
from iris.ranking import NightlyQueue, QueueCandidate, build_nightly_queue

from .dossier import write_candidate_dossier

REVIEW_SET_SCHEMA = "iris.review_set.v1"
ELIGIBILITY_POLICIES = frozenset({"triage", "gate-clear"})
_KNOWN_GATE_DECISIONS = frozenset(
    {
        "reportable",
        "needs_manual_review",
        "block_incomplete_evidence",
        "reject_known_object",
        "reject_quality",
    }
)


@dataclass(frozen=True, slots=True)
class ReviewSetResult:
    review_set_id: str
    output_dir: Path
    queue_path: Path
    manifest_path: Path
    dossier_paths: tuple[Path, ...]
    selected_count: int


def _boolean(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n", "", "nan", "none", "<na>"}:
        return False
    raise ValueError(f"cannot interpret {field} boolean value {value!r}")


def _queue_candidates_from_frame(
    frame: pd.DataFrame,
    *,
    eligibility_policy: str,
) -> tuple[QueueCandidate, ...]:
    """Apply a named review-eligibility policy to one snapshotted frame.

    ``triage`` admits quality-passing candidates whose external evidence is still
    incomplete. ``gate-clear`` admits only candidates whose automated evidence
    gate is clear or requires scientific catalogue-context adjudication. Neither
    policy admits known-object or failed-quality vetoes.
    """

    policy = eligibility_policy.strip().casefold()
    if policy not in ELIGIBILITY_POLICIES:
        raise ValueError(
            "eligibility_policy must be one of " + ", ".join(sorted(ELIGIBILITY_POLICIES))
        )
    required = {"candidate_id", "priority_score"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"queue input is missing columns: {sorted(missing)}")

    candidates: list[QueueCandidate] = []
    for row_number, (_, row) in enumerate(frame.iterrows(), start=2):
        raw_id = row["candidate_id"]
        candidate_id = "" if pd.isna(raw_id) else str(raw_id).strip()
        if not candidate_id:
            raise ValueError(f"queue input row {row_number} has an empty candidate_id")
        if "eligible" in frame:
            eligible = _boolean(row["eligible"], field="eligible")
        elif "review_queue_eligible" in frame:
            eligible = _boolean(row["review_queue_eligible"], field="review_queue_eligible")
        else:
            eligible = True

        exclusion_reasons: list[str] = []
        if "quality_passed" in frame:
            quality_passed = _boolean(row["quality_passed"], field="quality_passed")
            eligible = eligible and quality_passed
            if not quality_passed:
                exclusion_reasons.append("quality gate failed")

        if "gate_decision" in frame:
            raw_gate = row["gate_decision"]
            gate_decision = "" if pd.isna(raw_gate) else str(raw_gate).strip().casefold()
            if gate_decision not in _KNOWN_GATE_DECISIONS:
                gate_eligible = False
                exclusion_reasons.append(f"evidence gate is unknown ({gate_decision or 'missing'})")
            elif policy == "gate-clear":
                gate_eligible = gate_decision in {"reportable", "needs_manual_review"}
            else:
                gate_eligible = gate_decision not in {
                    "reject_known_object",
                    "reject_quality",
                }
            eligible = eligible and gate_eligible
            if not gate_eligible and gate_decision in _KNOWN_GATE_DECISIONS:
                exclusion_reasons.append(f"evidence gate is {gate_decision}")

        reason: str | None = None
        if not eligible:
            raw_reason = row.get("ineligibility_reason")
            supplied_reason = "" if pd.isna(raw_reason) else str(raw_reason).strip()
            reason = supplied_reason or "; ".join(
                exclusion_reasons or ["candidate is marked ineligible"]
            )

        raw_anomaly = row.get("anomaly_score", 0.0)
        anomaly = 0.0 if pd.isna(raw_anomaly) else float(raw_anomaly)
        candidates.append(
            QueueCandidate(
                candidate_id=candidate_id,
                priority_score=float(row["priority_score"]),
                anomaly_score=anomaly,
                eligible=eligible,
                ineligibility_reason=reason,
            )
        )
    return tuple(candidates)


def load_queue_candidates(
    path: str | Path,
    *,
    eligibility_policy: str = "triage",
) -> tuple[QueueCandidate, ...]:
    """Read a ranking CSV and apply a named review-eligibility policy."""

    source = Path(path).expanduser().resolve()
    source_bytes = source.read_bytes()
    frame = pd.read_csv(BytesIO(source_bytes), dtype={"candidate_id": "string"})
    return _queue_candidates_from_frame(frame, eligibility_policy=eligibility_policy)


def queue_from_csv(
    path: str | Path,
    *,
    budget: int,
    anomaly_slots: int = 0,
    anomaly_threshold: float = 0.8,
    audit_slots: int = 0,
    audit_seed: str | None = None,
    eligibility_policy: str = "triage",
) -> NightlyQueue:
    """Load candidate rows and allocate one versioned nightly queue."""

    candidates = load_queue_candidates(path, eligibility_policy=eligibility_policy)
    return build_nightly_queue(
        candidates,
        budget=budget,
        anomaly_slots=anomaly_slots,
        anomaly_threshold=anomaly_threshold,
        audit_slots=audit_slots,
        audit_seed=audit_seed,
        selection_policy=f"{eligibility_policy}_v1",
    )


def _candidate_records(payload: Any) -> tuple[str, str, str, dict[str, dict[str, Any]]]:
    if not isinstance(payload, Mapping) or payload.get("schema") != "iris.candidates.v1":
        raise ValueError("candidate evidence must use schema 'iris.candidates.v1'")
    run_id = payload.get("run_id")
    scientific_fingerprint = payload.get("scientific_fingerprint")
    pipeline_version = payload.get("pipeline_version")
    records = payload.get("candidates")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("candidate evidence has no valid run_id")
    if not isinstance(pipeline_version, str) or not pipeline_version.strip():
        raise ValueError("candidate evidence has no valid pipeline_version")
    if not isinstance(scientific_fingerprint, str) or not scientific_fingerprint.strip():
        raise ValueError("candidate evidence has no valid scientific_fingerprint")
    if not isinstance(records, list) or any(not isinstance(item, Mapping) for item in records):
        raise ValueError("candidate evidence does not contain a candidates array")
    by_id: dict[str, dict[str, Any]] = {}
    for item in records:
        candidate_id = str(item.get("candidate_id", "")).strip()
        candidate_version = str(item.get("candidate_version", "")).strip()
        if not candidate_id or not candidate_version:
            raise ValueError("every candidate needs candidate_id and candidate_version")
        if candidate_id in by_id:
            raise ValueError(f"duplicate candidate evidence for {candidate_id!r}")
        record = dict(item)
        verify_candidate_record(record, pipeline_version=pipeline_version.strip())
        if record.get("run_id") != run_id.strip():
            raise ValueError(f"candidate {candidate_id!r} belongs to another run")
        if record.get("scientific_fingerprint") != scientific_fingerprint.strip():
            raise ValueError(
                f"candidate {candidate_id!r} belongs to another scientific fingerprint"
            )
        by_id[candidate_id] = record
    return (
        run_id.strip(),
        scientific_fingerprint.strip(),
        pipeline_version.strip(),
        by_id,
    )


def _record_boolean(value: Any, *, candidate_id: str, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"candidate {candidate_id!r} has invalid {field}")
    return value


def _record_score(value: Any, *, candidate_id: str, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"candidate {candidate_id!r} has invalid {field}")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"candidate {candidate_id!r} has invalid {field}") from exc
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ValueError(f"candidate {candidate_id!r} has invalid {field}")
    return score


def _validate_ranking_binding(
    frame: pd.DataFrame,
    candidate_records: Mapping[str, Mapping[str, Any]],
    *,
    scientific_fingerprint: str,
    pipeline_version: str,
) -> None:
    required = {
        "candidate_id",
        "candidate_version",
        "candidate_record_digest",
        "scientific_fingerprint",
        "pipeline_version",
        "campaign",
        "priority_score",
        "quality_passed",
        "gate_decision",
        "review_queue_eligible",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"review-set ranking input is missing columns: {sorted(missing)}")
    ranking_versions: dict[str, str] = {}
    for row_number, (_, row) in enumerate(frame.iterrows(), start=2):
        candidate_id = "" if pd.isna(row["candidate_id"]) else str(row["candidate_id"]).strip()
        version = "" if pd.isna(row["candidate_version"]) else str(row["candidate_version"]).strip()
        if not candidate_id or not version:
            raise ValueError(f"ranking row {row_number} lacks candidate identity/version")
        if candidate_id in ranking_versions:
            raise ValueError(f"duplicate ranking row for {candidate_id!r}")
        ranking_versions[candidate_id] = version
        record = candidate_records.get(candidate_id)
        if record is None:
            continue
        if str(row["scientific_fingerprint"]).strip() != scientific_fingerprint:
            raise ValueError(
                f"ranking scientific_fingerprint differs from evidence for {candidate_id!r}"
            )
        if str(row["pipeline_version"]).strip() != pipeline_version:
            raise ValueError(f"ranking pipeline_version differs from evidence for {candidate_id!r}")
        if str(row["candidate_record_digest"]).strip() != str(record["candidate_record_digest"]):
            raise ValueError(
                f"ranking candidate_record_digest differs from evidence for {candidate_id!r}"
            )
        campaign = str(record.get("campaign", "")).strip()
        if not campaign or str(row["campaign"]).strip() != campaign:
            raise ValueError(f"ranking campaign differs from evidence for {candidate_id!r}")
        score = record.get("score")
        quality = record.get("quality")
        gate = record.get("gate")
        if not isinstance(score, Mapping):
            raise ValueError(f"candidate {candidate_id!r} has invalid score evidence")
        if not isinstance(quality, Mapping):
            raise ValueError(f"candidate {candidate_id!r} has invalid quality evidence")
        if not isinstance(gate, Mapping):
            raise ValueError(f"candidate {candidate_id!r} has invalid gate evidence")
        expected_priority = _record_score(
            score.get("priority_score"),
            candidate_id=candidate_id,
            field="priority score",
        )
        ranking_priority = _record_score(
            row["priority_score"],
            candidate_id=candidate_id,
            field="ranking priority score",
        )
        if not math.isclose(
            ranking_priority,
            expected_priority,
            rel_tol=1.0e-12,
            abs_tol=1.0e-15,
        ):
            raise ValueError(f"ranking priority differs from evidence for {candidate_id!r}")
        expected_quality = _record_boolean(
            quality.get("passed"),
            candidate_id=candidate_id,
            field="quality verdict",
        )
        ranking_quality = _boolean(row["quality_passed"], field="quality_passed")
        if ranking_quality != expected_quality:
            raise ValueError(f"ranking quality differs from evidence for {candidate_id!r}")
        expected_gate = str(gate.get("decision", "")).strip().casefold()
        ranking_gate = str(row["gate_decision"]).strip().casefold()
        if expected_gate not in _KNOWN_GATE_DECISIONS or ranking_gate != expected_gate:
            raise ValueError(f"ranking gate differs from evidence for {candidate_id!r}")
        expected_triage = expected_quality and expected_gate not in {
            "reject_known_object",
            "reject_quality",
        }
        ranking_triage = _boolean(
            row["review_queue_eligible"],
            field="review_queue_eligible",
        )
        if ranking_triage != expected_triage:
            raise ValueError(f"ranking eligibility differs from evidence for {candidate_id!r}")
        if "anomaly_score" in frame.columns:
            anomaly_evidence = record.get("anomaly_score")
            if anomaly_evidence is None:
                raise ValueError(
                    f"ranking anomaly score has no bound evidence for {candidate_id!r}"
                )
            expected_anomaly = _record_score(
                anomaly_evidence,
                candidate_id=candidate_id,
                field="anomaly score",
            )
            ranking_anomaly = _record_score(
                row["anomaly_score"],
                candidate_id=candidate_id,
                field="ranking anomaly score",
            )
            if not math.isclose(
                ranking_anomaly,
                expected_anomaly,
                rel_tol=1.0e-12,
                abs_tol=1.0e-15,
            ):
                raise ValueError(f"ranking anomaly differs from evidence for {candidate_id!r}")
    if set(ranking_versions) != set(candidate_records):
        raise ValueError("ranking and candidate evidence contain different candidate ID sets")
    for candidate_id, version in ranking_versions.items():
        if version != str(candidate_records[candidate_id]["candidate_version"]):
            raise ValueError(f"ranking and evidence versions differ for {candidate_id!r}")


def assemble_review_set(
    ranking_csv: str | Path,
    candidates_json: str | Path,
    output_dir: str | Path,
    *,
    budget: int,
    anomaly_slots: int = 0,
    anomaly_threshold: float = 0.8,
    audit_slots: int = 0,
    audit_seed: str | None = None,
    eligibility_policy: str = "triage",
) -> ReviewSetResult:
    """Atomically create a portable queue, evidence inputs, and dossiers."""

    ranking_path = Path(ranking_csv).expanduser().resolve()
    evidence_path = Path(candidates_json).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"review-set directory already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    ranking_bytes = ranking_path.read_bytes()
    evidence_bytes = evidence_path.read_bytes()
    ranking_frame = pd.read_csv(
        BytesIO(ranking_bytes),
        dtype={"candidate_id": "string", "candidate_version": "string"},
    )
    run_id, scientific_fingerprint, pipeline_version, records = _candidate_records(
        json.loads(evidence_bytes)
    )
    _validate_ranking_binding(
        ranking_frame,
        records,
        scientific_fingerprint=scientific_fingerprint,
        pipeline_version=pipeline_version,
    )
    queue = build_nightly_queue(
        _queue_candidates_from_frame(
            ranking_frame,
            eligibility_policy=eligibility_policy,
        ),
        budget=budget,
        anomaly_slots=anomaly_slots,
        anomaly_threshold=anomaly_threshold,
        audit_slots=audit_slots,
        audit_seed=audit_seed,
        selection_policy=f"{eligibility_policy}_v1",
    )
    selected_ids = tuple(entry.candidate_id for entry in queue.entries)
    if len(set(selected_ids)) != len(selected_ids):
        raise RuntimeError("queue allocation returned duplicate candidates")

    identity_payload = {
        "schema": REVIEW_SET_SCHEMA,
        "source_run_id": run_id,
        "source_scientific_fingerprint": scientific_fingerprint,
        "source_pipeline_version": pipeline_version,
        "ranking_sha256": sha256(ranking_bytes).hexdigest(),
        "candidates_sha256": sha256(evidence_bytes).hexdigest(),
        "queue": asdict(queue),
        "selected_versions": {
            candidate_id: records[candidate_id]["candidate_version"]
            for candidate_id in selected_ids
        },
    }
    review_set_id = f"review-set-{digest_value(identity_payload)[:20]}"
    staging = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    staging.mkdir()
    dossier_paths: list[Path] = []
    try:
        inputs_dir = staging / "inputs"
        inputs_dir.mkdir()
        archived_ranking = inputs_dir / "ranked_candidates.csv"
        archived_evidence = inputs_dir / "candidates.json"
        archived_ranking.write_bytes(ranking_bytes)
        archived_evidence.write_bytes(evidence_bytes)

        queue_payload = {
            **asdict(queue),
            "review_set_id": review_set_id,
            "source_run_id": run_id,
            "ranking_sha256": identity_payload["ranking_sha256"],
            "candidates_sha256": identity_payload["candidates_sha256"],
            "safety_boundary": "review selection only; never reporting authorization",
        }
        queue_path = staging / "queue.json"
        queue_path.write_text(
            json.dumps(queue_payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        for candidate_id in selected_ids:
            record = records[candidate_id]
            features = record.get("features", {})
            checks = record.get("external_checks", [])
            if not isinstance(features, Mapping):
                raise ValueError(f"candidate {candidate_id!r} has invalid features")
            if not isinstance(checks, list) or any(
                not isinstance(item, Mapping) for item in checks
            ):
                raise ValueError(f"candidate {candidate_id!r} has invalid external checks")
            dossier_paths.append(
                write_candidate_dossier(
                    staging / "dossiers",
                    candidate=record,
                    features=dict(features),
                    checks=[dict(item) for item in checks],
                )
            )

        artifacts = []
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                artifacts.append(
                    {
                        "path": path.relative_to(staging).as_posix(),
                        "sha256": digest_file(path),
                        "size_bytes": path.stat().st_size,
                    }
                )
        manifest = {
            **identity_payload,
            "review_set_id": review_set_id,
            "created_at": datetime.now(UTC).isoformat(),
            "eligibility_policy": eligibility_policy,
            "selected_candidate_ids": list(selected_ids),
            "artifacts": artifacts,
            "safety_boundary": (
                "This package supports human triage only. Every external check, exact-version "
                "approval, and reporting preflight must still pass independently."
            ),
        }
        manifest_path = staging / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        staging.replace(destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    return ReviewSetResult(
        review_set_id=review_set_id,
        output_dir=destination,
        queue_path=destination / "queue.json",
        manifest_path=destination / "manifest.json",
        dossier_paths=tuple(destination / path.relative_to(staging) for path in dossier_paths),
        selected_count=len(selected_ids),
    )


__all__ = [
    "ELIGIBILITY_POLICIES",
    "REVIEW_SET_SCHEMA",
    "ReviewSetResult",
    "assemble_review_set",
    "load_queue_candidates",
    "queue_from_csv",
]
