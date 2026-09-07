"""Leakage-aware metrics centered on finite nightly review capacity."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]
IntegerArray = NDArray[np.int64]
IndexArray = NDArray[np.intp]


@dataclass(frozen=True)
class RankingMetrics:
    """Capacity-aware ranking diagnostics with an explicit cutoff-tie policy."""

    precision_at_k: float
    recall_at_k: float
    average_precision: float
    brier_score: float | None
    expected_calibration_error: float | None
    positives: int
    reviewed: int
    score_semantics: str
    boundary_tie_policy: str


def chronological_indices(
    timestamps: Sequence[float] | ArrayLike,
    *,
    train_fraction: float = 0.7,
    validation_fraction: float = 0.15,
) -> tuple[IndexArray, IndexArray, IndexArray]:
    if isinstance(train_fraction, bool) or isinstance(validation_fraction, bool):
        raise ValueError("split fractions must be finite numbers, not booleans")
    if not np.isfinite(train_fraction) or not np.isfinite(validation_fraction):
        raise ValueError("split fractions must be finite")
    if not 0 < train_fraction < 1 or not 0 < validation_fraction < 1:
        raise ValueError("invalid split fractions")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train plus validation fraction must be below one")
    try:
        timestamp_values = list(cast(Iterable[object], timestamps))
    except TypeError as exc:
        raise ValueError("timestamps must be an iterable of numeric values") from exc
    if any(isinstance(value, (bool, np.bool_)) for value in timestamp_values):
        raise ValueError("timestamps must be numeric values, not booleans")
    times = np.asarray(timestamp_values, dtype=float)
    if times.ndim != 1 or len(times) < 3 or not np.isfinite(times).all():
        raise ValueError("timestamps must be a finite one-dimensional vector with three rows")
    blocks = np.unique(times)
    if len(blocks) < 3:
        raise ValueError("at least three distinct timestamp blocks are required")
    train_blocks = min(max(int(np.floor(len(blocks) * train_fraction)), 1), len(blocks) - 2)
    validation_blocks = max(int(np.floor(len(blocks) * validation_fraction)), 1)
    validation_blocks = min(validation_blocks, len(blocks) - train_blocks - 1)
    train_cut = blocks[train_blocks]
    test_cut = blocks[train_blocks + validation_blocks]
    order = np.argsort(times, kind="stable")
    return (
        order[times[order] < train_cut],
        order[(times[order] >= train_cut) & (times[order] < test_cut)],
        order[times[order] >= test_cut],
    )


def _average_precision(labels: IntegerArray, scores: FloatArray) -> float:
    """Return threshold-grouped AP, invariant to row order within score ties."""

    positives = int(labels.sum())
    if positives == 0:
        return 0.0
    order = np.argsort(-scores, kind="stable")
    ranked_labels = labels[order]
    ranked_scores = scores[order]
    # A classifier cannot order examples with exactly equal scores. Treat every
    # score level as one threshold, as standard non-interpolated AP does, rather
    # than allowing arbitrary input row order to decide the metric.
    group_ends = np.r_[np.flatnonzero(np.diff(ranked_scores) != 0), len(ranked_scores) - 1]
    cumulative_positives = np.cumsum(ranked_labels)[group_ends]
    cumulative_rows = group_ends + 1
    precision = cumulative_positives / cumulative_rows
    recall = cumulative_positives / positives
    recall_increments = np.diff(np.r_[0.0, recall])
    return float(np.sum(recall_increments * precision))


def _expected_positives_at_k(labels: IntegerArray, scores: FloatArray, k: int) -> float:
    """Expected positives when a cutoff tie is sampled uniformly.

    Scores strictly above the cutoff are always selected. If the K-th position
    falls inside a tie, the remaining slots receive the tied group's positive
    rate. This makes precision/recall at K independent of input row ordering
    while stating the unavoidable ambiguity instead of inventing an ordering.
    """

    if k == 0:
        return 0.0
    cutoff = float(np.sort(scores)[::-1][k - 1])
    above = scores > cutoff
    tied = scores == cutoff
    remaining = k - int(above.sum())
    return float(labels[above].sum()) + remaining * float(labels[tied].mean())


def _ece(labels: IntegerArray, scores: FloatArray, bins: int) -> float:
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = max(len(labels), 1)
    error = 0.0
    for index in range(bins):
        right_closed = index == bins - 1
        mask = (scores >= edges[index]) & (
            (scores <= edges[index + 1]) if right_closed else (scores < edges[index + 1])
        )
        if mask.any():
            error += (
                float(mask.sum())
                / total
                * abs(float(scores[mask].mean()) - float(labels[mask].mean()))
            )
    return error


def ranking_metrics(
    labels: Iterable[int | bool],
    scores: Iterable[float],
    *,
    review_budget: int,
    calibration_bins: int = 10,
    calibrated_probabilities: bool = False,
) -> RankingMetrics:
    """Evaluate a nightly ordering without mislabeling priorities as probabilities.

    Precision/recall at budget and average precision are valid for any finite
    ranking score. If the review-budget boundary splits an equal-score group,
    precision and recall use the expectation under uniform selection within
    that group; ``boundary_tie_policy`` records this contract. Brier score and
    ECE are returned only when the caller explicitly attests that ``scores``
    are held-out calibrated probabilities.
    """

    raw_labels = np.asarray(list(labels))
    try:
        numeric_labels = raw_labels.astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("labels must contain only binary values 0 and 1") from exc
    y = numeric_labels.astype(np.int64)
    raw_scores = list(scores)
    if any(isinstance(value, (bool, np.bool_)) for value in raw_scores):
        raise ValueError("scores must be finite numeric values, not booleans")
    p = np.asarray(raw_scores, dtype=float)
    if y.shape != p.shape or y.ndim != 1 or len(y) == 0:
        raise ValueError("labels and scores must be equally sized non-empty vectors")
    if (
        not np.isfinite(numeric_labels).all()
        or not np.isin(numeric_labels, [0.0, 1.0]).all()
        or not np.isfinite(p).all()
    ):
        raise ValueError("labels must be binary and scores must be finite")
    if not isinstance(calibrated_probabilities, (bool, np.bool_)):
        raise ValueError("calibrated_probabilities must be an explicit boolean attestation")
    if calibrated_probabilities and ((p < 0) | (p > 1)).any():
        raise ValueError("calibrated probabilities must be within [0, 1]")
    if isinstance(calibration_bins, bool) or not isinstance(calibration_bins, (int, np.integer)):
        raise ValueError("calibration_bins must be an integer")
    if calibration_bins < 1:
        raise ValueError("calibration_bins must be positive")
    if isinstance(review_budget, bool) or not isinstance(review_budget, (int, np.integer)):
        raise ValueError("review_budget must be an integer")
    if review_budget < 0:
        raise ValueError("review_budget must be non-negative")
    k = min(int(review_budget), len(y))
    expected_selected = _expected_positives_at_k(y, p, k)
    positives = int(y.sum())
    return RankingMetrics(
        precision_at_k=expected_selected / k if k else 0.0,
        recall_at_k=expected_selected / positives if positives else 0.0,
        average_precision=_average_precision(y, p),
        brier_score=(float(np.mean(np.square(p - y))) if calibrated_probabilities else None),
        expected_calibration_error=(
            _ece(y, p, calibration_bins) if calibrated_probabilities else None
        ),
        positives=positives,
        reviewed=k,
        score_semantics=("calibrated_probability" if calibrated_probabilities else "ranking_score"),
        boundary_tie_policy="expected_uniform_within_equal_score_cutoff",
    )
