"""Strict assembly of detector and JEPA evidence for shadow pilot runs."""

from __future__ import annotations

import hmac
import math
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

import numpy as np
from numpy.typing import NDArray

from siderea.anomaly import RobustAnomalyDetector
from siderea.provenance import digest_value

JEPA_EMBEDDINGS_SCHEMA = "siderea.jepa_embeddings.v1"
SHADOW_EVIDENCE_SCHEMA = "siderea.shadow_evidence.v2"
SHADOW_QUEUE_SCHEMA = "siderea.integrated_shadow_queue.v1"


def _verified_payload(payload: Mapping[str, Any], schema: str, name: str) -> dict[str, Any]:
    materialized = dict(payload)
    if materialized.get("schema") != schema:
        raise ValueError(f"{name} must use schema {schema!r}")
    stored = materialized.pop("result_digest", None)
    if not isinstance(stored, str) or not hmac.compare_digest(stored, digest_value(materialized)):
        raise ValueError(f"{name} result digest differs from its content")
    return dict(payload)


def _canonical_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return " ".join(value.casefold().split())


def _embedding_rows(
    payload: Mapping[str, Any], name: str
) -> tuple[dict[str, Any], NDArray[np.float64]]:
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{name} must contain non-empty embedding rows")
    identities: dict[str, Any] = {}
    vectors: list[list[float]] = []
    width: int | None = None
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError(f"{name} embedding rows must be objects")
        entity = _canonical_id(row.get("entity_id"), f"{name} entity_id")
        if entity in identities:
            raise ValueError(f"{name} contains duplicate canonical entity_id {entity!r}")
        raw = row.get("embedding")
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ValueError(f"{name} embedding must be an array")
        try:
            vector = [float(value) for value in raw]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} embedding values must be numeric") from exc
        if not vector or not all(math.isfinite(value) for value in vector):
            raise ValueError(f"{name} embeddings must be finite and non-empty")
        if width is None:
            width = len(vector)
        elif len(vector) != width:
            raise ValueError(f"{name} embeddings must have one fixed width")
        identities[entity] = dict(row)
        vectors.append(vector)
    return identities, np.asarray(vectors, dtype=np.float64)


def _pipeline_rows(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    from siderea.integrity import (
        candidate_record_digest,
        verify_candidate_run_binding,
        verify_candidate_version_payload,
    )
    from siderea.pipeline import PIPELINE_VERSION

    if payload.get("schema") != "siderea.candidates.v1":
        raise ValueError("pipeline candidates must use schema 'siderea.candidates.v1'")
    records = payload.get("candidates")
    if not isinstance(records, list) or not records:
        raise ValueError("pipeline candidates must contain a non-empty candidates array")
    by_entity: dict[str, dict[str, Any]] = {}
    run_ids: set[str] = set()
    fingerprints: set[str] = set()
    for raw in records:
        if not isinstance(raw, Mapping):
            raise ValueError("pipeline candidate rows must be objects")
        record = dict(raw)
        entity = _canonical_id(record.get("candidate_id"), "pipeline candidate_id")
        if entity in by_entity:
            raise ValueError(f"pipeline candidates contain duplicate entity {entity!r}")
        stored_record_digest = record.get("candidate_record_digest")
        if not isinstance(stored_record_digest, str) or not hmac.compare_digest(
            stored_record_digest, candidate_record_digest(record)
        ):
            raise ValueError(f"pipeline candidate {entity!r} differs from its record digest")
        verify_candidate_run_binding(record)
        verify_candidate_version_payload(
            record,
            pipeline_version=PIPELINE_VERSION,
            expected_candidate_id=str(record["candidate_id"]),
        )
        score = record.get("score")
        quality = record.get("quality")
        gate = record.get("gate")
        if (
            not isinstance(score, Mapping)
            or not isinstance(quality, Mapping)
            or not isinstance(gate, Mapping)
        ):
            raise ValueError(
                f"pipeline candidate {entity!r} lacks score, quality, or gate evidence"
            )
        priority = score.get("priority_score")
        if (
            isinstance(priority, bool)
            or not isinstance(priority, (int, float))
            or not math.isfinite(float(priority))
            or not 0 <= float(priority) <= 1
            or score.get("is_probability") is not False
        ):
            raise ValueError(f"pipeline candidate {entity!r} has invalid heuristic priority")
        if not isinstance(quality.get("passed"), bool) or not isinstance(gate.get("decision"), str):
            raise ValueError(f"pipeline candidate {entity!r} has invalid quality or gate state")
        run_ids.add(str(record.get("run_id")))
        fingerprints.add(str(record.get("scientific_fingerprint")))
        by_entity[entity] = record
    if len(run_ids) != 1 or len(fingerprints) != 1:
        raise ValueError("pipeline candidates must come from one analysis run and fingerprint")
    return by_entity


def assemble_shadow_evidence(
    transient_search: Mapping[str, Any],
    candidate_embeddings: Mapping[str, Any],
    reference_embeddings: Mapping[str, Any],
    *,
    pipeline_candidates: Mapping[str, Any] | None = None,
    pipeline_candidates_sha256: str | None = None,
    manifest_binding: Mapping[str, Any] | None = None,
    reference_cohort_result_digest: str | None = None,
    random_state: int = 17,
) -> dict[str, Any]:
    """Join separately inspectable shadow evidence under strict provenance contracts."""

    search = _verified_payload(transient_search, "siderea.transient_search.v1", "transient search")
    candidates = _verified_payload(
        candidate_embeddings, JEPA_EMBEDDINGS_SCHEMA, "candidate embeddings"
    )
    reference = _verified_payload(
        reference_embeddings, JEPA_EMBEDDINGS_SCHEMA, "reference embeddings"
    )
    for field in ("checkpoint_sha256", "token_contract_sha256", "code_identity_sha256"):
        left, right = candidates.get(field), reference.get(field)
        if (
            not isinstance(left, str)
            or not isinstance(right, str)
            or not hmac.compare_digest(left, right)
        ):
            raise ValueError(f"candidate/reference {field} values differ")
    search_cutoff = search.get("prediction_cutoff_mjd")
    candidate_cutoff = candidates.get("prediction_cutoff_mjd")
    if (
        isinstance(search_cutoff, bool)
        or not isinstance(search_cutoff, (int, float))
        or isinstance(candidate_cutoff, bool)
        or not isinstance(candidate_cutoff, (int, float))
        or not math.isfinite(float(search_cutoff))
        or not math.isfinite(float(candidate_cutoff))
        or float(search_cutoff) != float(candidate_cutoff)
    ):
        raise ValueError("detector and candidate JEPA prediction cutoffs must match")

    candidate_rows, candidate_matrix = _embedding_rows(candidates, "candidate embeddings")
    reference_rows, reference_matrix = _embedding_rows(reference, "reference embeddings")
    overlap = set(candidate_rows) & set(reference_rows)
    if overlap:
        raise ValueError("candidate and anomaly-reference entities must be disjoint")
    if candidate_matrix.shape[1] != reference_matrix.shape[1]:
        raise ValueError("candidate/reference embedding widths differ")

    detector_rows = search.get("objects")
    if not isinstance(detector_rows, list) or not detector_rows:
        raise ValueError("transient search contains no object summaries")
    by_entity: dict[str, Mapping[str, Any]] = {}
    for row in detector_rows:
        if not isinstance(row, Mapping):
            raise ValueError("transient-search object summaries must be objects")
        entity = _canonical_id(row.get("source_id"), "transient source_id")
        if entity in by_entity:
            raise ValueError(f"transient search contains duplicate entity {entity!r}")
        by_entity[entity] = row
    if set(by_entity) != set(candidate_rows):
        missing_detector = sorted(set(candidate_rows) - set(by_entity))
        missing_jepa = sorted(set(by_entity) - set(candidate_rows))
        raise ValueError(
            "detector/JEPA entity sets differ; "
            f"missing detector={missing_detector[:5]}, missing JEPA={missing_jepa[:5]}"
        )

    pipeline_rows = None if pipeline_candidates is None else _pipeline_rows(pipeline_candidates)
    if pipeline_rows is not None and set(pipeline_rows) != set(candidate_rows):
        missing_pipeline = sorted(set(candidate_rows) - set(pipeline_rows))
        missing_jepa = sorted(set(pipeline_rows) - set(candidate_rows))
        raise ValueError(
            "pipeline/JEPA entity sets differ; "
            f"missing pipeline={missing_pipeline[:5]}, missing JEPA={missing_jepa[:5]}"
        )
    if pipeline_candidates_sha256 is not None and (
        len(pipeline_candidates_sha256) != 64
        or any(character not in "0123456789abcdef" for character in pipeline_candidates_sha256)
    ):
        raise ValueError("pipeline_candidates_sha256 must be a lowercase SHA-256 digest")
    if (pipeline_rows is None) != (manifest_binding is None):
        raise ValueError("pipeline candidates and manifest binding must be supplied together")
    if manifest_binding is not None and not all(
        isinstance(manifest_binding.get(field), str) and manifest_binding[field]
        for field in (
            "pilot_manifest_digest",
            "pilot_manifest_sha256",
            "pipeline_manifest_sha256",
            "pipeline_configuration_digest",
            "pipeline_code_source_digest",
        )
    ):
        raise ValueError("integrated manifest binding is incomplete")
    if reference_cohort_result_digest is not None and (
        len(reference_cohort_result_digest) != 64
        or any(c not in "0123456789abcdef" for c in reference_cohort_result_digest)
    ):
        raise ValueError("reference cohort result digest must be a lowercase SHA-256 digest")

    detector = RobustAnomalyDetector(random_state=random_state).fit(reference_matrix)
    anomaly = detector.score(candidate_matrix)
    ordered_entities = list(candidate_rows)
    rows: list[dict[str, Any]] = []
    for index, entity in enumerate(ordered_entities):
        detector_row = by_entity[entity]
        pipeline_row = None if pipeline_rows is None else pipeline_rows[entity]
        pipeline_score = None if pipeline_row is None else pipeline_row["score"]
        pipeline_quality = None if pipeline_row is None else pipeline_row["quality"]
        pipeline_gate = None if pipeline_row is None else pipeline_row["gate"]
        gate_decision = None if pipeline_gate is None else pipeline_gate["decision"]
        rows.append(
            {
                "entity_id": candidate_rows[entity]["entity_id"],
                "object_id": candidate_rows[entity].get("object_id"),
                "detector_status": detector_row.get("status"),
                "detector_object_pvalue": detector_row.get("object_pvalue"),
                "detector_shadow_excess": detector_row.get("shadow_excess"),
                "detector_campaign_pvalue": detector_row.get("campaign_pvalue"),
                "detector_campaign_shadow_excess": detector_row.get("campaign_shadow_excess"),
                "pipeline_candidate_version": (
                    None if pipeline_row is None else pipeline_row["candidate_version"]
                ),
                "pipeline_priority_score": (
                    None if pipeline_score is None else float(pipeline_score["priority_score"])
                ),
                "pipeline_score_kind": (
                    None if pipeline_score is None else pipeline_score.get("score_kind")
                ),
                "pipeline_quality_passed": (
                    None if pipeline_quality is None else pipeline_quality["passed"]
                ),
                "pipeline_gate_decision": gate_decision,
                "pipeline_review_eligible": (
                    None
                    if pipeline_quality is None
                    else bool(pipeline_quality["passed"])
                    and gate_decision not in {"reject_known_object", "reject_quality"}
                ),
                "jepa_anomaly_score": float(anomaly.combined_score[index]),
                "jepa_anomaly_score_valid": bool(anomaly.score_valid[index]),
                "jepa_observed_feature_fraction": float(anomaly.observed_fraction[index]),
            }
        )
    output: dict[str, Any] = {
        "schema": SHADOW_EVIDENCE_SCHEMA,
        "mode": "shadow_only",
        "qualifies_reportability": False,
        "fusion_rule": None,
        "framework_channels": {
            "aadi_operational_heuristic": pipeline_rows is not None,
            "aadi_template_search": True,
            "jepa_representation_novelty": True,
        },
        "score_semantics": {
            "pipeline_priority_score": "inspectable_heuristic_priority_not_probability",
            "detector_object_pvalue": "finite_null_rank_within_object_corrected_only",
            "detector_campaign_pvalue": (
                "bonferroni_over_declared_object_universe_and_planned_looks"
            ),
            "jepa_anomaly_score": "training_reference_anomaly_rank_not_probability",
        },
        "transient_campaign_inference": search.get("campaign_inference"),
        "prediction_cutoff_mjd": float(search_cutoff),
        "transient_search_result_digest": search["result_digest"],
        "candidate_embeddings_result_digest": candidates["result_digest"],
        "reference_embeddings_result_digest": reference["result_digest"],
        "checkpoint_sha256": candidates["checkpoint_sha256"],
        "token_contract_sha256": candidates["token_contract_sha256"],
        "code_identity_sha256": candidates["code_identity_sha256"],
        "pipeline_candidates_sha256": pipeline_candidates_sha256,
        "pipeline_run_id": (
            None if pipeline_rows is None else next(iter(pipeline_rows.values()))["run_id"]
        ),
        "pipeline_scientific_fingerprint": (
            None
            if pipeline_rows is None
            else next(iter(pipeline_rows.values()))["scientific_fingerprint"]
        ),
        "manifest_binding": None if manifest_binding is None else dict(manifest_binding),
        "reference_cohort_result_digest": reference_cohort_result_digest,
        "reference_entity_count": len(reference_rows),
        "candidate_entity_count": len(rows),
        "anomaly_random_state": random_state,
        "rows": rows,
    }
    output["result_digest"] = digest_value(output)
    return output


def _positive_count(value: Any, name: str, *, allow_zero: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < int(not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be a {qualifier} integer")
    return value


def build_integrated_shadow_queue(
    evidence: Mapping[str, Any],
    *,
    budget: int,
    detector_slots: int,
    jepa_slots: int,
    audit_slots: int = 0,
    jepa_threshold: float = 0.8,
    audit_seed: str | None = None,
) -> dict[str, Any]:
    """Allocate explicit heuristic, detector, JEPA, and random-audit review routes."""

    payload = _verified_payload(evidence, SHADOW_EVIDENCE_SCHEMA, "shadow evidence")
    budget = _positive_count(budget, "budget")
    detector_slots = _positive_count(detector_slots, "detector_slots")
    jepa_slots = _positive_count(jepa_slots, "jepa_slots")
    audit_slots = _positive_count(audit_slots, "audit_slots")
    if detector_slots + jepa_slots + audit_slots > budget:
        raise ValueError("reserved detector, JEPA, and audit slots cannot exceed budget")
    if (
        isinstance(jepa_threshold, bool)
        or not isinstance(jepa_threshold, (int, float))
        or not math.isfinite(float(jepa_threshold))
        or not 0 <= float(jepa_threshold) <= 1
    ):
        raise ValueError("jepa_threshold must be finite and within [0, 1]")
    normalized_seed = None if audit_seed is None else audit_seed.strip()
    if audit_slots and not normalized_seed:
        raise ValueError("audit_seed is required when audit_slots is positive")
    if payload.get("framework_channels", {}).get("aadi_operational_heuristic") is not True:
        raise ValueError("integrated queue requires bound Aadi operational pipeline evidence")
    campaign_inference = payload.get("transient_campaign_inference")
    if detector_slots and (
        not isinstance(campaign_inference, Mapping)
        or campaign_inference.get("method") != "bonferroni_union_bound"
    ):
        raise ValueError("detector reserve requires declared campaign-level inference")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("shadow evidence must contain non-empty object rows")
    eligible: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        entity = _canonical_id(row.get("entity_id"), "shadow entity_id")
        priority = row.get("pipeline_priority_score")
        anomaly = row.get("jepa_anomaly_score")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0 <= float(value) <= 1
            for value in (priority, anomaly)
        ):
            raise ValueError(f"shadow entity {entity!r} has invalid priority or anomaly score")
        if row.get("pipeline_review_eligible") is True:
            row["_entity"] = entity
            eligible.append(row)

    def pipeline_key(row: Mapping[str, Any]) -> tuple[float, str]:
        return -float(row["pipeline_priority_score"]), str(row["_entity"])

    def detector_key(row: Mapping[str, Any]) -> tuple[float, float, str]:
        value = row.get("detector_campaign_pvalue")
        pvalue = (
            float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 1.0
        )
        return pvalue, -float(row["pipeline_priority_score"]), str(row["_entity"])

    def jepa_key(row: Mapping[str, Any]) -> tuple[float, float, str]:
        return (
            -float(row["jepa_anomaly_score"]),
            -float(row["pipeline_priority_score"]),
            str(row["_entity"]),
        )

    audit_count = min(audit_slots, budget, len(eligible))
    audit = sorted(
        eligible,
        key=lambda row: (
            sha256(f"{normalized_seed}\0{row['_entity']}".encode()).digest(),
            str(row["_entity"]),
        ),
    )[:audit_count]
    selected = {str(row["_entity"]) for row in audit}
    remaining_budget = budget - len(audit)
    pipeline_slots = max(0, remaining_budget - detector_slots - jepa_slots)
    pipeline = [
        row for row in sorted(eligible, key=pipeline_key) if row["_entity"] not in selected
    ][:pipeline_slots]
    selected.update(str(row["_entity"]) for row in pipeline)
    detector_pool = [
        row
        for row in eligible
        if row["_entity"] not in selected and row.get("detector_campaign_shadow_excess") is True
    ]
    detector = sorted(detector_pool, key=detector_key)[: min(detector_slots, remaining_budget)]
    selected.update(str(row["_entity"]) for row in detector)
    jepa_pool = [
        row
        for row in eligible
        if row["_entity"] not in selected
        and row.get("jepa_anomaly_score_valid") is True
        and float(row["jepa_anomaly_score"]) >= float(jepa_threshold)
    ]
    jepa = sorted(jepa_pool, key=jepa_key)[: min(jepa_slots, budget - len(selected))]
    selected.update(str(row["_entity"]) for row in jepa)
    fill = [
        row for row in sorted(eligible, key=pipeline_key) if str(row["_entity"]) not in selected
    ][: max(0, budget - len(selected))]
    routed = [
        *((row, "aadi_heuristic") for row in pipeline),
        *((row, "aadi_template_reserve") for row in detector),
        *((row, "jepa_novelty_reserve") for row in jepa),
        *((row, "aadi_heuristic_fill") for row in fill),
        *((row, "random_audit") for row in audit),
    ]
    audit_probability = audit_count / len(eligible) if audit_count and eligible else None
    entries = [
        {
            "rank": index,
            "entity_id": row["entity_id"],
            "selection_route": route,
            "pipeline_priority_score": row["pipeline_priority_score"],
            "detector_campaign_pvalue": row["detector_campaign_pvalue"],
            "jepa_anomaly_score": row["jepa_anomaly_score"],
            "selection_propensity": audit_probability if route == "random_audit" else None,
        }
        for index, (row, route) in enumerate(routed, start=1)
    ]
    output: dict[str, Any] = {
        "schema": SHADOW_QUEUE_SCHEMA,
        "mode": "shadow_only",
        "qualifies_reportability": False,
        "fusion_rule": None,
        "evidence_result_digest": evidence["result_digest"],
        "selection_policy": "separate_aadi_heuristic_template_jepa_and_random_audit_routes",
        "budget": budget,
        "eligible_entities": len(eligible),
        "excluded_entities": len(rows) - len(eligible),
        "requested_detector_slots": detector_slots,
        "used_detector_slots": len(detector),
        "requested_jepa_slots": jepa_slots,
        "used_jepa_slots": len(jepa),
        "jepa_threshold": float(jepa_threshold),
        "requested_audit_slots": audit_slots,
        "used_audit_slots": len(audit),
        "audit_seed": normalized_seed if audit_slots else None,
        "audit_selection_probability": audit_probability,
        "used_heuristic_slots": len(pipeline) + len(fill),
        "unused_slots": budget - len(entries),
        "entries": entries,
    }
    output["result_digest"] = digest_value(output)
    return output


__all__ = [
    "JEPA_EMBEDDINGS_SCHEMA",
    "SHADOW_EVIDENCE_SCHEMA",
    "SHADOW_QUEUE_SCHEMA",
    "assemble_shadow_evidence",
    "build_integrated_shadow_queue",
]
