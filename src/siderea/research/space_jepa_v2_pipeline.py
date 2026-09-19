"""Bind AQPM evidence to the incumbent transient candidate artifact."""

from __future__ import annotations

import hmac
from collections.abc import Mapping
from typing import Any

from siderea.provenance import digest_value

SPACE_JEPA_V2_EVIDENCE_SCHEMA = "siderea.space_jepa_v2_shadow_evidence.v1"


def _verified(payload: Mapping[str, Any], schema: str, name: str) -> dict[str, Any]:
    materialized = dict(payload)
    if materialized.get("schema") != schema:
        raise ValueError(f"{name} must use schema {schema!r}")
    stored = str(materialized.pop("result_digest", ""))
    if not hmac.compare_digest(stored, digest_value(materialized)):
        raise ValueError(f"{name} result digest differs from content")
    materialized["result_digest"] = stored
    return materialized


def assemble_space_jepa_v2_shadow_evidence(
    candidates: Mapping[str, Any],
    evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    """Join complete candidate and AQPM evidence without creating probabilities."""

    if candidates.get("schema") != "siderea.candidates.v1":
        raise ValueError("candidates must use schema 'siderea.candidates.v1'")
    records = candidates.get("candidates")
    if not isinstance(records, list) or any(not isinstance(row, Mapping) for row in records):
        raise ValueError("candidates must contain candidate objects")
    verified_evaluation = _verified(
        evaluation, "siderea.space_jepa_v2_evaluation.v1", "AQPM evaluation"
    )
    evaluation_rows = verified_evaluation.get("rows")
    if not isinstance(evaluation_rows, list) or any(
        not isinstance(row, Mapping) for row in evaluation_rows
    ):
        raise ValueError("AQPM evaluation lacks row evidence")
    by_id = {str(row.get("example_id", "")): row for row in evaluation_rows}
    candidate_ids = [str(row.get("candidate_id", "")) for row in records]
    if any(not value for value in candidate_ids) or len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("candidate identities must be non-empty and unique")
    missing = sorted(set(candidate_ids) - set(by_id))
    extra = sorted(set(by_id) - set(candidate_ids))
    if missing or extra:
        raise ValueError(
            f"candidate/AQPM cohorts differ; missing={missing[:10]}, extra={extra[:10]}"
        )
    rows = []
    for candidate in records:
        candidate_id = str(candidate["candidate_id"])
        aqpm = by_id[candidate_id]
        errors = aqpm.get("mean_absolute_latent_error")
        if not isinstance(errors, list) or not errors:
            raise ValueError(f"AQPM evidence for {candidate_id!r} lacks horizon errors")
        rows.append(
            {
                "candidate_id": candidate_id,
                "review_priority": float(max(float(value) for value in errors)),
                "priority_semantics": "aqpm_predictive_surprise_not_probability",
                "aqpm": dict(aqpm),
                "incumbent": dict(candidate),
            }
        )
    identity = {
        "schema": SPACE_JEPA_V2_EVIDENCE_SCHEMA,
        "mode": "shadow_only",
        "candidate_count": len(rows),
        "candidate_artifact_digest": digest_value(candidates),
        "evaluation_result_digest": verified_evaluation["result_digest"],
        "rows": rows,
        "reporting_authorized": False,
    }
    return {**identity, "result_digest": digest_value(identity)}


__all__ = ["SPACE_JEPA_V2_EVIDENCE_SCHEMA", "assemble_space_jepa_v2_shadow_evidence"]
