"""Cross-artifact scientific bindings for local study evidence.

These checks establish consistency inside a trusted local archive. They do not
authenticate upstream observations or establish scientific deployment readiness.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import pandas as pd

from siderea.provenance import digest_value
from siderea.research.benchmark import run_rolling_origin_benchmark
from siderea.research.preregistration import Preregistration


def verify_digest(payload: Mapping[str, Any], field: str) -> str:
    basis = dict(payload)
    stored = basis.pop(field, None)
    if not isinstance(stored, str) or stored != digest_value(basis):
        raise ValueError(f"{field} does not match content")
    return stored


def _instant(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("study time must be an ISO timestamp")
    instant = datetime.fromisoformat(value)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("study time must include timezone")
    return instant


def cohort_labels(
    cohort: Mapping[str, Any],
    preregistration: Preregistration,
) -> dict[str, tuple[str, int]]:
    """Validate maturity and extract explicit, evidence-backed binary labels.

    Outcome evidence must explicitly carry binary_label. No taxonomy strings are
    guessed to be positives/negatives. Missing outcomes follow the frozen policy.
    """

    preregistration = preregistration.validated()
    verify_digest(cohort, "cohort_digest")
    if cohort.get("schema") != "siderea.matured_cohort.v1":
        raise ValueError("unsupported cohort schema")
    if cohort.get("protocol_digest") != preregistration.protocol_digest:
        raise ValueError("cohort belongs to another protocol")
    if cohort.get("study_id") != preregistration.study_id:
        raise ValueError("cohort belongs to another study")
    policy = preregistration.protocol
    as_of = _instant(cohort.get("as_of"))
    if as_of < _instant(policy["cohort"]["matures_at"]):
        raise ValueError("cohort has not matured")
    missing_policy = policy["analysis"]["missing_outcome_policy"]
    if cohort.get("missing_outcome_policy") != missing_policy:
        raise ValueError("cohort missing-outcome policy differs from preregistration")
    records = cohort.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("cohort records must be non-empty")
    if type(cohort.get("enrollment_count")) is not int or cohort["enrollment_count"] != len(
        records
    ):
        raise ValueError("cohort enrollment count differs from records")
    labels: dict[str, tuple[str, int]] = {}
    seen: set[str] = set()
    missing = 0
    selected = 0
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("cohort records must be objects")
        identifier = record.get("candidate_id")
        version = record.get("candidate_version")
        if (
            not isinstance(identifier, str)
            or not identifier.strip()
            or not isinstance(version, str)
            or len(version) != 64
            or any(character not in "0123456789abcdef" for character in version)
        ):
            raise ValueError("cohort candidate identity/version is invalid")
        key = identifier.strip().casefold()
        if key in seen:
            raise ValueError("cohort repeats a physical entity")
        seen.add(key)
        if record.get("protocol_digest") != preregistration.protocol_digest:
            raise ValueError("cohort record belongs to another protocol")
        if type(record.get("selected")) is not bool or type(record.get("eligible")) is not bool:
            raise ValueError("cohort selection flags must be boolean")
        if record["selected"] and not record["eligible"]:
            raise ValueError("cohort selected an ineligible candidate")
        selected += int(record["selected"])
        instant = _instant(record.get("enrolled_at"))
        if (
            not _instant(policy["cohort"]["opens_at"])
            <= instant
            <= _instant(policy["cohort"]["closes_at"])
        ):
            raise ValueError("enrollment is outside the cohort window")
        outcomes = record.get("outcomes")
        if not isinstance(outcomes, list):
            raise ValueError("cohort outcomes must be an array")
        for outcome in outcomes:
            if not isinstance(outcome, Mapping):
                raise ValueError("outcome must be an object")
            if (
                outcome.get("candidate_version") != version
                or outcome.get("candidate_id") != identifier
            ):
                raise ValueError("outcome is bound to another candidate version")
            if _instant(outcome.get("recorded_at")) > as_of:
                raise ValueError("outcome was recorded after the analysis cutoff")
            if not isinstance(outcome.get("evidence"), Mapping):
                raise ValueError("outcome evidence must be an object")
            if outcome.get("evidence_digest") != digest_value(outcome.get("evidence")):
                raise ValueError("outcome evidence digest differs")
        if not outcomes:
            missing += 1
            if missing_policy == "count_as_negative":
                labels[key] = (version, 0)
            elif missing_policy == "censor":
                raise ValueError("binary benchmark cannot implement censored unresolved outcomes")
            continue
        latest = max(outcomes, key=lambda outcome: _instant(outcome["recorded_at"]))
        label = latest.get("evidence", {}).get("binary_label")
        if type(label) is not int or label not in {0, 1}:
            raise ValueError("latest outcome evidence requires explicit binary_label 0 or 1")
        labels[key] = (version, label)
    if cohort.get("missing_outcome_count") != missing or cohort.get("selected_count") != selected:
        raise ValueError("cohort summary counts differ from records")
    if not labels:
        raise ValueError("cohort has no evaluable binary outcomes")
    return labels


def bind_benchmark(
    benchmark: Mapping[str, Any],
    cohort: Mapping[str, Any],
    preregistration: Preregistration,
) -> dict[str, Any]:
    preregistration = preregistration.validated()
    labels = cohort_labels(cohort, preregistration)
    verify_digest(benchmark, "result_digest")
    inputs = benchmark.get("evaluation_inputs")
    if not isinstance(inputs, Mapping):
        raise ValueError("benchmark lacks reconstructable evaluation inputs")
    if benchmark.get("benchmark_digest") != digest_value(inputs):
        raise ValueError("benchmark input digest differs")
    try:
        frame = pd.DataFrame(
            {
                inputs["entity_column"]: inputs["entity_ids"],
                inputs["time_column"]: inputs["times"],
                inputs["label_column"]: inputs["labels"],
                **inputs["scores"],
            }
        )
        recomputed = run_rolling_origin_benchmark(
            frame,
            entity_column=inputs["entity_column"],
            time_column=inputs["time_column"],
            label_column=inputs["label_column"],
            score_columns=inputs["score_columns"],
            review_budget=inputs["review_budget"],
            minimum_history_blocks=inputs["minimum_history_blocks"],
            bootstrap_repeats=inputs["bootstrap_repeats"],
            confidence_level=inputs["confidence_level"],
            seed=inputs["seed"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("benchmark inputs cannot be reproduced") from exc
    if any(
        benchmark.get(field) != recomputed[field]
        for field in ("folds", "summary", "reference_score")
    ):
        raise ValueError("benchmark results differ from recomputed evaluation inputs")
    entities, values = inputs.get("entity_ids"), inputs.get("labels")
    if (
        not isinstance(entities, list)
        or not isinstance(values, list)
        or len(entities) != len(values)
    ):
        raise ValueError("benchmark entity/label arrays are invalid")
    expected = {key: value[1] for key, value in labels.items()}
    if len(entities) != len(expected) or dict(zip(entities, values, strict=True)) != expected:
        raise ValueError("benchmark entities/labels differ from matured cohort outcomes")
    policy = preregistration.protocol
    analysis, selection = policy["analysis"], policy["selection"]
    for key, value in {
        "review_budget": selection["review_budget"],
        "confidence_level": analysis["confidence_level"],
        "bootstrap_repeats": analysis["bootstrap_repeats"],
        "seed": analysis["random_seed"],
    }.items():
        if benchmark.get(key) != value or inputs.get(key) != value:
            raise ValueError(f"benchmark {key} differs from preregistration")
    reference = analysis.get("reference_score")
    if not isinstance(reference, str) or benchmark.get("reference_score") != reference:
        raise ValueError("preregistration must name the exact reference_score")
    if analysis["comparison"] == reference or analysis["comparison"] not in inputs.get(
        "score_columns", []
    ):
        raise ValueError("benchmark comparison must differ from the reference")
    result = dict(benchmark)
    result.update(
        study_id=preregistration.study_id,
        protocol_digest=preregistration.protocol_digest,
        cohort_digest=cohort["cohort_digest"],
        outcome_binding_digest=digest_value(labels),
    )
    result.pop("result_digest", None)
    result["result_digest"] = digest_value(result)
    return result


def valid_interval(value: Any, *, lower: float, upper: float) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(type(item) in {int, float} and math.isfinite(item) for item in value)
        and lower <= value[0] <= value[1] <= upper
    )
