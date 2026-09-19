"""Complete-grid, fixed-budget evaluation for Space JEPA 2."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from siderea.provenance import digest_value

SPACE_JEPA_V2_BENCHMARK_SCHEMA = "siderea.space_jepa_v2_benchmark.v1"


def extrapolation_forecast(
    times: Sequence[float],
    values: Sequence[float],
    target_times: Sequence[float],
    *,
    degree: int,
) -> list[float]:
    """Persistence/linear/quadratic baseline with deterministic degradation."""

    observed_times = np.asarray(times, dtype=np.float64)
    observed_values = np.asarray(values, dtype=np.float64)
    targets = np.asarray(target_times, dtype=np.float64)
    if (
        observed_times.ndim != 1
        or observed_values.shape != observed_times.shape
        or not len(observed_times)
        or np.any(~np.isfinite(observed_times))
        or np.any(~np.isfinite(observed_values))
        or np.any(~np.isfinite(targets))
    ):
        raise ValueError("forecast arrays must be finite and observations non-empty")
    if degree not in {0, 1, 2}:
        raise ValueError("degree must be 0, 1 or 2")
    effective_degree = min(degree, len(observed_times) - 1)
    if effective_degree == 0:
        return [float(observed_values[-1])] * len(targets)
    centered = observed_times - observed_times[-1]
    coefficients = np.polyfit(centered, observed_values, effective_degree)
    predicted = np.polyval(coefficients, targets - observed_times[-1]).astype(float)
    return [float(value) for value in predicted]


def verify_complete_grid(
    rows: Sequence[Mapping[str, Any]],
    *,
    models: Sequence[str],
    seeds: Sequence[int],
    folds: Sequence[str],
    horizons_days: Sequence[float],
) -> dict[str, int]:
    """Require one uniquely identified success/failure receipt per planned cell."""

    expected = {
        (str(model), int(seed), str(fold), float(horizon))
        for model in models
        for seed in seeds
        for fold in folds
        for horizon in horizons_days
    }
    observed: set[tuple[str, int, str, float]] = set()
    failed = 0
    for row in rows:
        key = (
            str(row.get("model", "")),
            int(row.get("seed", -1)),
            str(row.get("fold", "")),
            float(row.get("horizon_days", math.nan)),
        )
        if key in observed:
            raise ValueError(f"benchmark grid contains duplicate cell {key!r}")
        observed.add(key)
        status = row.get("status")
        if status not in {"success", "failed"}:
            raise ValueError(f"benchmark cell {key!r} has invalid status")
        failed += int(status == "failed")
    missing = sorted(expected - observed)
    unexpected = sorted(observed - expected)
    if missing or unexpected:
        raise ValueError(
            f"benchmark grid differs from protocol; missing={missing[:10]}, "
            f"unexpected={unexpected[:10]}"
        )
    return {"planned_cells": len(expected), "observed_cells": len(observed), "failed_cells": failed}


def _average_precision(
    labels: np.ndarray[Any, np.dtype[np.int64]],
    scores: np.ndarray[Any, np.dtype[np.float64]],
) -> float:
    order = np.argsort(-scores, kind="stable")
    ordered = labels[order]
    positives = int(ordered.sum())
    if positives == 0:
        return 0.0
    cumulative = np.cumsum(ordered)
    precision = cumulative / np.arange(1, len(ordered) + 1)
    return float(np.sum(precision * ordered) / positives)


def _budget_metrics(
    labels: np.ndarray[Any, np.dtype[np.int64]],
    scores: np.ndarray[Any, np.dtype[np.float64]],
    budget: int,
) -> dict[str, float | int]:
    selected = np.argsort(-scores, kind="stable")[: min(budget, len(scores))]
    true_positive = int(labels[selected].sum())
    positives = int(labels.sum())
    return {
        "budget": min(budget, len(scores)),
        "true_positive": true_positive,
        "precision": true_positive / len(selected) if len(selected) else 0.0,
        "recall": true_positive / positives if positives else 0.0,
        "average_precision": _average_precision(labels, scores),
    }


def _bootstrap_budget_recall(
    labels: np.ndarray[Any, np.dtype[np.int64]],
    scores: np.ndarray[Any, np.dtype[np.float64]],
    indices: np.ndarray[Any, np.dtype[np.int64]],
    budget: int,
) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Vectorized fixed-budget recall for one chunk of bootstrap samples."""

    sampled_labels = labels[indices]
    sampled_scores = scores[indices]
    order = np.argsort(-sampled_scores, axis=1, kind="stable")
    selected_order = order[:, : min(budget, scores.shape[0])]
    selected_labels = np.take_along_axis(sampled_labels, selected_order, axis=1)
    true_positives = selected_labels.sum(axis=1, dtype=np.int64)
    positives = sampled_labels.sum(axis=1, dtype=np.int64)
    recall = np.zeros(len(indices), dtype=np.float64)
    np.divide(true_positives, positives, out=recall, where=positives > 0)
    return recall


def run_space_jepa_v2_benchmark(
    frame: pd.DataFrame,
    *,
    entity_column: str,
    label_column: str,
    score_columns: Sequence[str],
    review_budget: int,
    bootstrap_repeats: int = 10000,
    confidence_level: float = 0.95,
    seed: int = 1701,
) -> dict[str, Any]:
    """Evaluate candidate priorities on one entity-level common cohort."""

    required = {entity_column, label_column, *score_columns}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"benchmark input is missing columns: {missing}")
    if not score_columns or len(set(score_columns)) != len(score_columns):
        raise ValueError("score_columns must be non-empty and unique")
    if review_budget < 1 or bootstrap_repeats < 100:
        raise ValueError("review_budget must be positive and bootstrap_repeats at least 100")
    if not 0.0 < confidence_level < 1.0:
        raise ValueError("confidence_level must lie within (0, 1)")
    entities = frame[entity_column].astype("string")
    if entities.isna().any() or entities.str.strip().eq("").any() or entities.duplicated().any():
        raise ValueError("benchmark requires one non-empty row per physical entity")
    labels = pd.to_numeric(frame[label_column], errors="raise").to_numpy(dtype=np.int64)
    if not set(labels.tolist()) <= {0, 1}:
        raise ValueError("benchmark labels must contain only 0 and 1")
    scores: dict[str, np.ndarray[Any, np.dtype[np.float64]]] = {}
    for column in score_columns:
        values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=np.float64)
        if np.any(~np.isfinite(values)):
            raise ValueError(f"benchmark score {column!r} contains non-finite values")
        scores[column] = values
    metrics = {
        column: _budget_metrics(labels, values, review_budget) for column, values in scores.items()
    }
    reference = score_columns[0]
    generator = np.random.default_rng(seed)
    comparison_columns = tuple(score_columns[1:])
    differences = {
        column: np.empty(bootstrap_repeats, dtype=np.float64) for column in comparison_columns
    }
    # Bound temporary index/score matrices while moving sorting and recall math
    # out of Python's per-resample loop.
    bootstrap_chunk_size = min(512, bootstrap_repeats)
    for start in range(0, bootstrap_repeats, bootstrap_chunk_size):
        stop = min(start + bootstrap_chunk_size, bootstrap_repeats)
        indices = generator.integers(0, len(frame), size=(stop - start, len(frame)))
        reference_recall = _bootstrap_budget_recall(
            labels, scores[reference], indices, review_budget
        )
        for column in comparison_columns:
            recall = _bootstrap_budget_recall(labels, scores[column], indices, review_budget)
            differences[column][start:stop] = recall - reference_recall
    alpha = 1.0 - confidence_level
    intervals = {
        column: {
            "mean_recall_difference": float(np.mean(values)),
            "confidence_interval": [
                float(np.quantile(values, alpha / 2.0)),
                float(np.quantile(values, 1.0 - alpha / 2.0)),
            ],
        }
        for column, values in differences.items()
    }
    identity = {
        "schema": SPACE_JEPA_V2_BENCHMARK_SCHEMA,
        "entity_column": entity_column,
        "label_column": label_column,
        "score_columns": list(score_columns),
        "reference_score": reference,
        "review_budget": min(review_budget, len(frame)),
        "entity_count": len(frame),
        "positive_count": int(labels.sum()),
        "bootstrap_repeats": bootstrap_repeats,
        "confidence_level": confidence_level,
        "seed": seed,
        "metrics": metrics,
        "paired_recall_differences": intervals,
    }
    return {**identity, "result_digest": digest_value(identity)}


__all__ = [
    "SPACE_JEPA_V2_BENCHMARK_SCHEMA",
    "extrapolation_forecast",
    "run_space_jepa_v2_benchmark",
    "verify_complete_grid",
]
