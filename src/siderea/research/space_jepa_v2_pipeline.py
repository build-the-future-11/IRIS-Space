"""Bind AQPM evidence to the incumbent transient candidate artifact."""

from __future__ import annotations

import hmac
import math
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


def _identities(rows: list[Any], key: str, name: str) -> list[str]:
    identities: list[str] = []
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} identities must be non-empty strings and unique")
        identities.append(value)
    if len(set(identities)) != len(identities):
        raise ValueError(f"{name} identities must be non-empty strings and unique")
    return identities


def _numeric_list(value: Any, name: str, *, positive: bool = False) -> list[float]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty array of finite numbers")
    result = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{name} must contain finite numeric values without coercion")
        try:
            number = float(item)
        except OverflowError as exc:
            raise ValueError(f"{name} exceeds the finite numeric range") from exc
        if not math.isfinite(number) or number < 0 or (positive and number == 0):
            boundary = "positive" if positive else "nonnegative"
            raise ValueError(f"{name} must contain finite {boundary} numbers")
        result.append(number)
    return result


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
    row_count = verified_evaluation.get("row_count")
    if type(row_count) is not int or row_count != len(evaluation_rows):
        raise ValueError("AQPM evaluation row_count must equal the number of evidence rows")
    evaluation_ids = _identities(evaluation_rows, "example_id", "evaluation")
    candidate_ids = _identities(records, "candidate_id", "candidate")
    # Validate identity before indexing: a dictionary alone silently discards
    # repeated rows, including conflicting evidence for the same candidate.
    by_id = dict(zip(evaluation_ids, evaluation_rows, strict=True))
    missing = sorted(set(candidate_ids) - set(by_id))
    extra = sorted(set(by_id) - set(candidate_ids))
    if missing or extra:
        raise ValueError(
            f"candidate/AQPM cohorts differ; missing={missing[:10]}, extra={extra[:10]}"
        )
    rows = []
    for candidate in records:
        candidate_id = candidate["candidate_id"]
        aqpm = by_id[candidate_id]
        horizons = _numeric_list(aqpm.get("horizons_days"), "AQPM horizons", positive=True)
        if len(set(horizons)) != len(horizons):
            raise ValueError("AQPM horizons must be unique")
        errors = _numeric_list(aqpm.get("mean_absolute_latent_error"), "AQPM horizon errors")
        if len(errors) != len(horizons):
            raise ValueError("AQPM horizon errors must contain exactly one value per horizon")
        rows.append(
            {
                "candidate_id": candidate_id,
                "review_priority": max(errors),
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
