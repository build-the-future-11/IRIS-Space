"""Professor-guided shift and transient-detection evaluation.

Two deliberately separate questions live here:

1. Source-population transfer, following Steven Dillmann's recommendation to
   prioritize a change in source population as the primary astronomy shift.
2. Time-to-detection relative to annotated transient onset, following Umaa
   Rebbapragada's recommendation to complement ranking/ROC/PR metrics with an
   operational detection-timing endpoint.

Population membership and onset annotations are inputs. This module never
chooses a "hard" population from model outcomes and never rewrites onset times.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from statistics import median

import numpy as np
from numpy.typing import NDArray

from siderea.evaluation import ranking_metrics

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]


def _float_vector(values: Iterable[float], name: str) -> FloatArray:
    raw = list(values)
    if any(isinstance(value, (bool, np.bool_)) for value in raw):
        raise ValueError(f"{name} must contain finite numeric values, not booleans")
    try:
        out = np.asarray(raw, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain finite numeric values") from exc
    if out.ndim != 1 or len(out) == 0 or not np.isfinite(out).all():
        raise ValueError(f"{name} must be a finite non-empty one-dimensional vector")
    return out


def _binary_vector(values: Iterable[int | bool], name: str) -> IntArray:
    raw = np.asarray(list(values))
    try:
        numeric = raw.astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain only 0/1 values") from exc
    if numeric.ndim != 1 or len(numeric) == 0 or not np.isfinite(numeric).all():
        raise ValueError(f"{name} must be a finite non-empty one-dimensional vector")
    if not np.isin(numeric, [0.0, 1.0]).all():
        raise ValueError(f"{name} must contain only 0/1 values")
    return numeric.astype(np.int64)


def _population_vector(values: Iterable[str], *, n: int) -> tuple[str, ...]:
    raw = tuple(values)
    if len(raw) != n:
        raise ValueError("populations must have the same length as labels/scores")
    out: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("population labels must be non-empty strings")
        normalized = value.strip()
        if len(normalized) > 128 or any(ord(ch) < 32 for ch in normalized):
            raise ValueError("population labels must be bounded printable strings")
        out.append(normalized)
    return tuple(out)


def _auroc(labels: IntArray, scores: FloatArray) -> float | None:
    """Tie-aware empirical AUROC via pairwise probability of correct ranking."""
    positive_scores = scores[labels == 1]
    negative_scores = scores[labels == 0]
    if len(positive_scores) == 0 or len(negative_scores) == 0:
        return None
    # Chunking avoids an accidental O(P*N) memory spike for larger evaluation sets.
    wins = 0.0
    comparisons = 0
    chunk = 4096
    for start in range(0, len(positive_scores), chunk):
        pos = positive_scores[start : start + chunk, None]
        wins += float(np.sum(pos > negative_scores))
        wins += 0.5 * float(np.sum(pos == negative_scores))
        comparisons += len(pos) * len(negative_scores)
    return wins / comparisons


@dataclass(frozen=True)
class PopulationMetrics:
    population: str
    split_role: str
    n: int
    positives: int
    positive_rate: float
    auroc: float | None
    average_precision: float | None
    brier_score: float | None
    expected_calibration_error: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "population": self.population,
            "split_role": self.split_role,
            "n": self.n,
            "positives": self.positives,
            "positive_rate": self.positive_rate,
            "auroc": self.auroc,
            "average_precision": self.average_precision,
            "brier_score": self.brier_score,
            "expected_calibration_error": self.expected_calibration_error,
        }


def population_transfer_report(
    labels: Iterable[int | bool],
    scores: Iterable[float],
    populations: Iterable[str],
    *,
    in_population: Sequence[str],
    held_population: Sequence[str],
    calibrated_probabilities: bool = False,
    calibration_bins: int = 10,
) -> dict[str, object]:
    """Evaluate one frozen model across declared source-population groups.

    Group membership is supplied explicitly. The function refuses overlapping
    in/held sets and refuses unassigned observed populations, preventing a
    post-outcome "pick the hardest group" workflow.
    """

    y = _binary_vector(labels, "labels")
    p = _float_vector(scores, "scores")
    if y.shape != p.shape:
        raise ValueError("labels and scores must be equally sized")
    pop = _population_vector(populations, n=len(y))

    in_set = {value.strip() for value in in_population}
    held_set = {value.strip() for value in held_population}
    if not in_set or not held_set:
        raise ValueError("in_population and held_population must both be non-empty")
    if "" in in_set or "" in held_set:
        raise ValueError("population declarations must be non-empty")
    overlap = in_set & held_set
    if overlap:
        raise ValueError(f"in/held populations overlap: {', '.join(sorted(overlap))}")

    observed = set(pop)
    declared = in_set | held_set
    undeclared = observed - declared
    absent = declared - observed
    if undeclared:
        raise ValueError(
            f"observed populations lack a frozen split role: {', '.join(sorted(undeclared))}"
        )
    if absent:
        raise ValueError(
            f"declared populations are absent from evaluation rows: {', '.join(sorted(absent))}"
        )

    per_population: list[PopulationMetrics] = []
    for name in sorted(observed):
        mask = np.asarray([value == name for value in pop], dtype=bool)
        local_y = y[mask]
        local_p = p[mask]
        local_positives = int(local_y.sum())
        metrics = ranking_metrics(
            local_y.tolist(),
            local_p.tolist(),
            review_budget=len(local_y),
            calibration_bins=calibration_bins,
            calibrated_probabilities=calibrated_probabilities,
        )
        per_population.append(
            PopulationMetrics(
                population=name,
                split_role="in_population" if name in in_set else "held_population",
                n=len(local_y),
                positives=local_positives,
                positive_rate=float(local_y.mean()),
                auroc=_auroc(local_y, local_p),
                average_precision=(
                    metrics.average_precision if local_positives > 0 else None
                ),
                brier_score=metrics.brier_score,
                expected_calibration_error=metrics.expected_calibration_error,
            )
        )

    def _macro(role: str, field: str) -> float | None:
        values = [
            getattr(item, field)
            for item in per_population
            if item.split_role == role and getattr(item, field) is not None
        ]
        return float(np.mean(values)) if values else None

    in_ap = _macro("in_population", "average_precision")
    held_ap = _macro("held_population", "average_precision")
    in_auc = _macro("in_population", "auroc")
    held_auc = _macro("held_population", "auroc")

    return {
        "protocol": "source_population_transfer_v1",
        "population_assignment": {
            "in_population": sorted(in_set),
            "held_population": sorted(held_set),
        },
        "per_population": [item.to_dict() for item in per_population],
        "macro": {
            "in_population_average_precision": in_ap,
            "held_population_average_precision": held_ap,
            "average_precision_delta_held_minus_in": (
                held_ap - in_ap if held_ap is not None and in_ap is not None else None
            ),
            "in_population_auroc": in_auc,
            "held_population_auroc": held_auc,
            "auroc_delta_held_minus_in": (
                held_auc - in_auc if held_auc is not None and in_auc is not None else None
            ),
        },
        "claim_guard": (
            "Population groups must be defined from scientific metadata/class definitions "
            "before outcome inspection. A held-population degradation is a transfer result, "
            "not evidence that the held population was intrinsically harder. Average "
            "precision is unavailable for populations with no positive examples and those "
            "groups are excluded from macro AP rather than treated as zero performance."
        ),
    }


@dataclass(frozen=True)
class DetectionEvent:
    """One annotated transient with an optional first qualifying detection."""

    object_id: str
    population: str
    onset_time: float
    first_detection_time: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.object_id, str) or not self.object_id.strip():
            raise ValueError("object_id must be a non-empty string")
        if not isinstance(self.population, str) or not self.population.strip():
            raise ValueError("population must be a non-empty string")
        onset = float(self.onset_time)
        if not math.isfinite(onset):
            raise ValueError("onset_time must be finite")
        detection = self.first_detection_time
        if detection is not None:
            detection_value = float(detection)
            if not math.isfinite(detection_value):
                raise ValueError("first_detection_time must be finite or null")
            object.__setattr__(self, "first_detection_time", detection_value)
        object.__setattr__(self, "onset_time", onset)
        object.__setattr__(self, "object_id", self.object_id.strip())
        object.__setattr__(self, "population", self.population.strip())

    @property
    def delay(self) -> float | None:
        if self.first_detection_time is None:
            return None
        return self.first_detection_time - self.onset_time


def _percentile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    return float(np.percentile(np.asarray(values, dtype=float), q, method="linear"))


def _detection_group(events: Sequence[DetectionEvent]) -> dict[str, object]:
    detected = [event for event in events if event.delay is not None]
    delays = [float(event.delay) for event in detected if event.delay is not None]
    nonnegative = [delay for delay in delays if delay >= 0]
    pre_onset = [delay for delay in delays if delay < 0]
    report: dict[str, object] = {
        "n_annotated": len(events),
        "n_detected": len(detected),
        "n_undetected": len(events) - len(detected),
        "detection_rate": len(detected) / len(events) if events else None,
        "pre_onset_detection_count": len(pre_onset),
        "conditional_delay_note": (
            "Delay summaries condition on detected events; undetected events are reported "
            "separately and are never imputed as an arbitrary large delay."
        ),
    }
    if delays:
        report["signed_delay_median"] = float(median(delays))
        report["signed_delay_p90"] = _percentile(delays, 90)
    if nonnegative:
        report["post_onset_delay_median"] = float(median(nonnegative))
        report["post_onset_delay_p90"] = _percentile(nonnegative, 90)
    return report


def time_to_detection_report(events: Iterable[DetectionEvent]) -> dict[str, object]:
    """Report detection probability and timing without hiding censoring.

    The clock units are inherited from ``onset_time`` / ``first_detection_time``;
    callers must use one consistent time basis (e.g. MJD days or seconds).
    Negative signed delays are preserved and counted rather than silently
    clamped to zero, because they can reveal annotation/alarm semantics issues.
    """

    rows = tuple(events)
    if not rows:
        raise ValueError("at least one detection event is required")
    seen: set[str] = set()
    for event in rows:
        if event.object_id in seen:
            raise ValueError(f"duplicate object_id: {event.object_id}")
        seen.add(event.object_id)

    by_population: dict[str, list[DetectionEvent]] = defaultdict(list)
    for event in rows:
        by_population[event.population].append(event)

    return {
        "protocol": "annotated_onset_time_to_detection_v1",
        "overall": _detection_group(rows),
        "by_population": {
            population: _detection_group(group)
            for population, group in sorted(by_population.items())
        },
        "interpretation_guard": (
            "Always report detection rate alongside conditional delay. A method that is fast "
            "only on the subset it detects must not be described as globally earlier."
        ),
    }
