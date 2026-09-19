"""Evidence-preserving anomaly components for Space JEPA 2."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def _vector(value: Any, name: str) -> FloatArray:
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 1 or np.any(~np.isfinite(array)):
        raise ValueError(f"{name} must be a finite vector")
    return array


def fit_training_covariance(residuals: Any, *, ridge: float = 1e-6) -> FloatArray:
    matrix = np.asarray(residuals, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] < 2 or np.any(~np.isfinite(matrix)):
        raise ValueError("residuals must be a finite matrix with at least two rows")
    if not math.isfinite(ridge) or ridge <= 0.0:
        raise ValueError("ridge must be positive and finite")
    median = np.median(matrix, axis=0)
    centered = matrix - median
    scale = np.median(np.abs(centered), axis=0) * 1.4826
    scale = np.maximum(scale, math.sqrt(ridge))
    clipped = np.clip(centered, -5.0 * scale, 5.0 * scale)
    covariance = np.cov(clipped, rowvar=False)
    covariance = np.atleast_2d(covariance).astype(np.float64)
    return covariance + np.eye(covariance.shape[0], dtype=np.float64) * ridge


def mahalanobis_surprise(residual: Any, covariance: Any) -> float:
    vector = _vector(residual, "residual")
    matrix = np.asarray(covariance, dtype=np.float64)
    if matrix.shape != (len(vector), len(vector)) or np.any(~np.isfinite(matrix)):
        raise ValueError("covariance must be finite and square for the residual")
    solved = np.linalg.solve(matrix, vector)
    return float(vector @ solved)


def quaternion_disagreement(target: Any, prediction: Any) -> tuple[float, float]:
    target_array = np.asarray(target, dtype=np.float64)
    prediction_array = np.asarray(prediction, dtype=np.float64)
    if (
        target_array.ndim != 2
        or target_array.shape[1] != 4
        or prediction_array.shape != target_array.shape
        or np.any(~np.isfinite(target_array))
        or np.any(~np.isfinite(prediction_array))
    ):
        raise ValueError("target and prediction must be finite [channels, 4] arrays")
    dot = float(np.sum(target_array * prediction_array))
    denominator = float(np.linalg.norm(target_array) * np.linalg.norm(prediction_array))
    angular = 1.0 - dot / max(denominator, np.finfo(float).eps)
    target_vector = target_array[:, 1:]
    prediction_vector = prediction_array[:, 1:]
    wedge = float(np.linalg.norm(np.sum(np.cross(target_vector, prediction_vector), axis=0)))
    return angular, wedge


@dataclass(frozen=True)
class AnomalyComponents:
    predictive_surprise: float
    corrected_surprise: float
    angular_disagreement: float
    spectral_wedge: float
    memory_distance: float
    memory_entropy: float
    route_disagreement: float
    physics_residual: float


def anomaly_components(
    *,
    target: Any,
    base_prediction: Any,
    corrected_prediction: Any,
    covariance: Any,
    memory_distance: float,
    memory_entropy: float,
    physics_residual: float,
) -> AnomalyComponents:
    target_array = np.asarray(target, dtype=np.float64)
    base = np.asarray(base_prediction, dtype=np.float64)
    corrected = np.asarray(corrected_prediction, dtype=np.float64)
    if target_array.shape != base.shape or corrected.shape != base.shape:
        raise ValueError("target, base and corrected predictions must have equal shapes")
    base_error = (target_array - base).reshape(-1)
    corrected_error = (target_array - corrected).reshape(-1)
    angular, wedge = quaternion_disagreement(target_array, base)
    scalars = (memory_distance, memory_entropy, physics_residual)
    if any(not math.isfinite(value) or value < 0.0 for value in scalars):
        raise ValueError("memory and physics diagnostics must be finite and non-negative")
    return AnomalyComponents(
        predictive_surprise=mahalanobis_surprise(base_error, covariance),
        corrected_surprise=mahalanobis_surprise(corrected_error, covariance),
        angular_disagreement=angular,
        spectral_wedge=wedge,
        memory_distance=memory_distance,
        memory_entropy=memory_entropy,
        route_disagreement=float(np.linalg.norm(corrected - base)),
        physics_residual=physics_residual,
    )


def summarize_anomaly_trace(
    times_mjd: Sequence[float], scores: Sequence[float], *, threshold: float
) -> Mapping[str, float | int | None]:
    times = np.asarray(times_mjd, dtype=np.float64)
    values = np.asarray(scores, dtype=np.float64)
    if times.ndim != 1 or values.shape != times.shape or not len(times):
        raise ValueError("times and scores must be non-empty equal vectors")
    if np.any(~np.isfinite(times)) or np.any(~np.isfinite(values)) or np.any(np.diff(times) < 0.0):
        raise ValueError("times and scores must be finite and times sorted")
    if not math.isfinite(threshold):
        raise ValueError("threshold must be finite")
    longest = current = 0
    first_crossing: float | None = None
    for time, value in zip(times, values, strict=True):
        if value >= threshold:
            current += 1
            longest = max(longest, current)
            if first_crossing is None:
                first_crossing = float(time)
        else:
            current = 0
    area = float(np.trapezoid(values, times)) if len(times) > 1 else 0.0
    return {
        "maximum": float(values.max()),
        "quantile_95": float(np.quantile(values, 0.95)),
        "time_integral": area,
        "consecutive_run_length": longest,
        "first_threshold_crossing_mjd": first_crossing,
    }


__all__ = [
    "AnomalyComponents",
    "anomaly_components",
    "fit_training_covariance",
    "mahalanobis_surprise",
    "quaternion_disagreement",
    "summarize_anomaly_trace",
]
