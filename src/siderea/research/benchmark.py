"""Rolling-origin, finite-budget comparisons for precomputed ranking signals."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
import pandas as pd

from siderea.evaluation import RankingMetrics, ranking_metrics
from siderea.provenance import digest_value

ROLLING_BENCHMARK_SCHEMA = "siderea.rolling_origin_benchmark.v1"


def _integer(value: int, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _finite_column(frame: pd.DataFrame, name: str) -> np.ndarray[Any, np.dtype[np.float64]]:
    if name not in frame:
        raise ValueError(f"benchmark input is missing column {name!r}")
    try:
        values = pd.to_numeric(frame[name], errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"benchmark column {name!r} must be numeric") from exc
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError(f"benchmark column {name!r} must contain only finite values")
    return values


def _metric_payload(metric: RankingMetrics) -> dict[str, Any]:
    return {
        "precision_at_budget": metric.precision_at_k,
        "recall_at_budget": metric.recall_at_k,
        "average_precision": metric.average_precision,
        "positives": metric.positives,
        "reviewed": metric.reviewed,
        "score_semantics": metric.score_semantics,
        "boundary_tie_policy": metric.boundary_tie_policy,
    }


def _average(values: Sequence[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=float))) if values else 0.0


def run_rolling_origin_benchmark(
    frame: pd.DataFrame,
    *,
    entity_column: str,
    time_column: str,
    label_column: str,
    score_columns: Sequence[str],
    review_budget: int,
    minimum_history_blocks: int = 2,
    bootstrap_repeats: int = 1000,
    confidence_level: float = 0.95,
    seed: int = 0,
    time_block_days: float | None = None,
) -> dict[str, Any]:
    """Evaluate fixed ranking signals on every future time block.

    The input must contain one row per physical entity. This prevents aliases or
    repeated observations from crossing rolling-origin folds. Scores are treated
    only as rankings; this function never reports calibration metrics.
    """

    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("benchmark frame must be a non-empty pandas DataFrame")
    if isinstance(score_columns, (str, bytes)) or not score_columns:
        raise ValueError("score_columns must contain at least one column name")
    normalized_scores = tuple(str(column).strip() for column in score_columns)
    if any(not column for column in normalized_scores):
        raise ValueError("score column names must not be empty")
    if len(set(normalized_scores)) != len(normalized_scores):
        raise ValueError("score column names must be unique")
    _integer(review_budget, "review_budget", minimum=1)
    _integer(minimum_history_blocks, "minimum_history_blocks", minimum=1)
    _integer(bootstrap_repeats, "bootstrap_repeats", minimum=100)
    _integer(seed, "seed", minimum=0)
    if isinstance(confidence_level, bool) or not isinstance(confidence_level, (int, float)):
        raise ValueError("confidence_level must be a finite number within (0, 1)")
    confidence = float(confidence_level)
    if not math.isfinite(confidence) or not 0.0 < confidence < 1.0:
        raise ValueError("confidence_level must be a finite number within (0, 1)")

    required = {entity_column, time_column, label_column, *normalized_scores}
    if len(required) != len(normalized_scores) + 3:
        raise ValueError("entity, time, label and score columns must be distinct")
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"benchmark input is missing columns: {missing}")
    raw_entities = frame[entity_column]
    if raw_entities.isna().any():
        raise ValueError("entity identifiers must not be missing")
    entities = raw_entities.astype("string").str.strip().str.casefold()
    if entities.eq("").any() or entities.duplicated().any():
        raise ValueError("benchmark requires one non-empty row per physical entity")
    times = _finite_column(frame, time_column)
    if time_block_days is not None:
        if (
            isinstance(time_block_days, bool)
            or not isinstance(time_block_days, (int, float))
            or not math.isfinite(time_block_days)
            or time_block_days <= 0
        ):
            raise ValueError("time_block_days must be finite and positive")
        times = np.floor(times / time_block_days) * time_block_days
    raw_labels = _finite_column(frame, label_column)
    if not np.isin(raw_labels, (0.0, 1.0)).all():
        raise ValueError("benchmark labels must contain only 0 and 1")
    labels = raw_labels.astype(np.int64)
    score_values = {column: _finite_column(frame, column) for column in normalized_scores}

    time_blocks = np.unique(times)
    if len(time_blocks) <= minimum_history_blocks:
        raise ValueError("benchmark needs a future time block after the minimum history")
    folds: list[dict[str, Any]] = []
    fold_indices: list[np.ndarray[Any, np.dtype[np.intp]]] = []
    for origin_index in range(minimum_history_blocks, len(time_blocks)):
        test_time = float(time_blocks[origin_index])
        train_mask = times < test_time
        test_indices = np.flatnonzero(times == test_time)
        if not train_mask.any() or len(test_indices) == 0:
            continue
        if len(test_indices) < 2:
            raise ValueError(
                "benchmark time blocks must contain at least two entities; "
                "supply explicit session times or time_block_days"
            )
        fold_indices.append(test_indices)
        fold_models: dict[str, Any] = {}
        for column in normalized_scores:
            metric = ranking_metrics(
                labels[test_indices],
                score_values[column][test_indices],
                review_budget=review_budget,
            )
            fold_models[column] = _metric_payload(metric)
        folds.append(
            {
                "fold": len(folds) + 1,
                "origin_time": test_time,
                "history_rows": int(train_mask.sum()),
                "test_rows": len(test_indices),
                "models": fold_models,
            }
        )
    if not folds:
        raise ValueError("rolling-origin benchmark produced no evaluable folds")

    metric_names = ("precision_at_budget", "recall_at_budget", "average_precision")
    point_estimates: dict[str, dict[str, float]] = {}
    for column in normalized_scores:
        point_estimates[column] = {
            metric_name: _average([float(fold["models"][column][metric_name]) for fold in folds])
            for metric_name in metric_names
        }

    rng = np.random.default_rng(seed)
    bootstrap: dict[str, dict[str, list[float]]] = {
        column: {metric_name: [] for metric_name in metric_names} for column in normalized_scores
    }
    for _ in range(bootstrap_repeats):
        sampled_fold_metrics: dict[str, dict[str, list[float]]] = {
            column: {metric_name: [] for metric_name in metric_names}
            for column in normalized_scores
        }
        for indices in fold_indices:
            sampled = rng.choice(indices, size=len(indices), replace=True)
            for column in normalized_scores:
                bootstrap_metric = _metric_payload(
                    ranking_metrics(
                        labels[sampled],
                        score_values[column][sampled],
                        review_budget=review_budget,
                    )
                )
                for metric_name in metric_names:
                    sampled_fold_metrics[column][metric_name].append(
                        float(bootstrap_metric[metric_name])
                    )
        for column in normalized_scores:
            for metric_name in metric_names:
                bootstrap[column][metric_name].append(
                    _average(sampled_fold_metrics[column][metric_name])
                )

    alpha = (1.0 - confidence) / 2.0
    summary: dict[str, Any] = {}
    reference = normalized_scores[0]
    for column in normalized_scores:
        metrics: dict[str, Any] = {}
        for metric_name in metric_names:
            draws = np.asarray(bootstrap[column][metric_name], dtype=float)
            metrics[metric_name] = {
                "estimate": point_estimates[column][metric_name],
                "confidence_interval": [
                    float(np.quantile(draws, alpha)),
                    float(np.quantile(draws, 1.0 - alpha)),
                ],
            }
            if column != reference:
                deltas = draws - np.asarray(bootstrap[reference][metric_name], dtype=float)
                metrics[metric_name]["delta_vs_reference"] = (
                    point_estimates[column][metric_name] - point_estimates[reference][metric_name]
                )
                metrics[metric_name]["delta_confidence_interval"] = [
                    float(np.quantile(deltas, alpha)),
                    float(np.quantile(deltas, 1.0 - alpha)),
                ]
        summary[column] = metrics

    identity = {
        "schema": ROLLING_BENCHMARK_SCHEMA,
        "entity_column": entity_column,
        "time_column": time_column,
        "label_column": label_column,
        "score_columns": list(normalized_scores),
        "review_budget": review_budget,
        "minimum_history_blocks": minimum_history_blocks,
        "bootstrap_repeats": bootstrap_repeats,
        "confidence_level": confidence,
        "seed": seed,
        "time_block_days": time_block_days,
        "entity_ids": entities.tolist(),
        "times": times.tolist(),
        "labels": labels.tolist(),
        "scores": {column: values.tolist() for column, values in score_values.items()},
    }
    payload = {
        "schema": ROLLING_BENCHMARK_SCHEMA,
        "benchmark_digest": digest_value(identity),
        "reference_score": reference,
        "score_semantics": "ranking_score_not_probability",
        "split_policy": "one_row_per_entity_strict_rolling_time_block",
        "review_budget": review_budget,
        "confidence_level": confidence,
        "bootstrap_repeats": bootstrap_repeats,
        "seed": seed,
        "evaluation_inputs": identity,
        "evaluation_scope": "fixed_precomputed_scores_by_time_block_not_model_refitting",
        "folds": folds,
        "summary": summary,
    }
    payload["result_digest"] = digest_value(payload)
    return payload


__all__ = ["ROLLING_BENCHMARK_SCHEMA", "run_rolling_origin_benchmark"]
