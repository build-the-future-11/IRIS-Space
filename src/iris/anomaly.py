"""Interpretable robust anomaly baseline with optional Isolation Forest."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Integral
from typing import Protocol

import numpy as np
from numpy.typing import ArrayLike, NDArray

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
_NORMALIZED_ABS_CLIP = 1.0e6


class _IsolationModel(Protocol):
    """Typed surface used from scikit-learn's optional estimator."""

    def score_samples(self, values: FloatArray) -> FloatArray: ...


@dataclass(frozen=True)
class AnomalyScores:
    """Anomaly diagnostics with explicit feature-coverage validity.

    ``score_valid`` is false when no fitted feature is observed or when the
    configured minimum coverage is not met. Invalid rows receive a zero
    ``combined_score`` and cannot gain priority merely through imputation.
    """

    robust_score: FloatArray
    isolation_score: FloatArray | None
    combined_score: FloatArray
    observed_fraction: FloatArray
    supported_feature_fraction: float
    score_valid: BoolArray
    score_semantics: str = "heuristic_anomaly_rank_not_probability"


class RobustAnomalyDetector:
    def __init__(
        self,
        *,
        use_isolation_forest: bool = True,
        random_state: int = 17,
        minimum_observed_fraction: float = 0.0,
    ) -> None:
        """Create a detector with an optional fail-closed coverage threshold.

        A zero threshold still requires at least one feature that was supported
        during fitting. Increase it when operational anomaly scores must be
        based on a specified fraction of the fitted feature contract.
        """

        if not isinstance(use_isolation_forest, bool):
            raise ValueError("use_isolation_forest must be boolean")
        if (
            isinstance(random_state, bool)
            or not isinstance(random_state, Integral)
            or random_state < 0
        ):
            raise ValueError("random_state must be a non-negative integer")
        if (
            isinstance(minimum_observed_fraction, bool)
            or not math.isfinite(minimum_observed_fraction)
            or not 0.0 <= minimum_observed_fraction <= 1.0
        ):
            raise ValueError("minimum_observed_fraction must be finite and within [0, 1]")
        self.use_isolation_forest: bool = use_isolation_forest
        self.random_state: int = int(random_state)
        self.minimum_observed_fraction: float = float(minimum_observed_fraction)
        self.median_: FloatArray | None = None
        self.scale_: FloatArray | None = None
        self.model_: _IsolationModel | None = None
        self.isolation_range_: tuple[float, float] | None = None
        self.feature_count_: int | None = None
        self.supported_: BoolArray | None = None

    def fit(self, values: ArrayLike) -> RobustAnomalyDetector:
        matrix: FloatArray = np.asarray(values, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[0] < 2 or matrix.shape[1] < 1:
            raise ValueError("anomaly detector requires at least two 2D rows")
        if np.isinf(matrix).any():
            raise ValueError("anomaly features may be missing (NaN), but not infinite")
        finite = np.isfinite(matrix)
        medians: list[float] = []
        scales: list[float] = []
        supported: list[bool] = []
        for column in range(matrix.shape[1]):
            observed = matrix[finite[:, column], column]
            column_supported = observed.size >= 2
            supported.append(column_supported)
            if not column_supported:
                medians.append(0.0)
                scales.append(1.0)
                continue
            # Compute location/scale after max-absolute rescaling.  Direct
            # reductions such as std([-1e308, 1e308]) overflow even though a
            # perfectly usable robust normalization exists.
            magnitude = float(np.max(np.abs(observed)))
            scaled_observed = observed / magnitude if magnitude > 0.0 else observed
            scaled_center = float(np.median(scaled_observed))
            center = scaled_center * magnitude if magnitude > 0.0 else scaled_center
            mad_scaled = float(np.median(np.abs(scaled_observed - scaled_center))) * 1.4826
            fallback_scaled = float(np.std(scaled_observed))
            scale_fraction = (
                mad_scaled if np.isfinite(mad_scaled) and mad_scaled > 0.0 else fallback_scaled
            )
            column_scale = scale_fraction * magnitude if magnitude > 0.0 else scale_fraction
            if not np.isfinite(column_scale) and magnitude > 0.0:
                column_scale = magnitude
            medians.append(center)
            scales.append(
                column_scale if np.isfinite(column_scale) and column_scale > 1e-9 else 1.0
            )
        median_array: FloatArray = np.asarray(medians, dtype=np.float64)
        scale_array: FloatArray = np.asarray(scales, dtype=np.float64)
        supported_mask: BoolArray = np.asarray(supported, dtype=np.bool_)
        if not supported_mask.any():
            raise ValueError(
                "anomaly fitting needs at least one feature with two finite measurements"
            )
        model: _IsolationModel | None = None
        isolation_range: tuple[float, float] | None = None
        isolation_fit_rows = finite[:, supported_mask].any(axis=1)
        if self.use_isolation_forest and int(isolation_fit_rows.sum()) >= 2:
            try:
                from sklearn.ensemble import IsolationForest  # type: ignore[import-untyped]

                filled: FloatArray = np.where(np.isfinite(matrix), matrix, median_array)
                with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                    standardized = (filled - median_array) / scale_array
                normalized: FloatArray = np.nan_to_num(
                    standardized[:, supported_mask],
                    nan=0.0,
                    posinf=_NORMALIZED_ABS_CLIP,
                    neginf=-_NORMALIZED_ABS_CLIP,
                )
                np.clip(
                    normalized,
                    -_NORMALIZED_ABS_CLIP,
                    _NORMALIZED_ABS_CLIP,
                    out=normalized,
                )
                fit_normalized = normalized[isolation_fit_rows]
                model = IsolationForest(
                    n_estimators=200,
                    contamination="auto",
                    random_state=self.random_state,
                ).fit(fit_normalized)
                raw = -model.score_samples(fit_normalized)
                low, high = (float(value) for value in np.quantile(raw, [0.05, 0.95]))
                if not np.isfinite(low) or not np.isfinite(high) or high <= low:
                    low, high = float(np.min(raw)), float(np.max(raw))
                isolation_range = (
                    low,
                    high if high > low else low + 1.0,
                )
            except ImportError:
                pass
        self.feature_count_ = matrix.shape[1]
        self.median_ = median_array
        self.scale_ = scale_array
        self.supported_ = supported_mask
        self.model_ = model
        self.isolation_range_ = isolation_range
        return self

    def _normalized(self, values: ArrayLike) -> FloatArray:
        if self.median_ is None or self.scale_ is None or self.supported_ is None:
            raise RuntimeError("fit the anomaly detector first")
        matrix: FloatArray = np.asarray(values, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != self.feature_count_:
            raise ValueError(f"values must have shape [rows, {self.feature_count_}] after fitting")
        filled = np.where(np.isfinite(matrix), matrix, self.median_)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            standardized = (filled - self.median_) / self.scale_
        # Values beyond this point are already saturated by the robust anomaly
        # transform and lie outside meaningful floating-point resolution.  A
        # finite cap also keeps the optional tree model and squared distances
        # numerically defined for adversarial-but-finite inputs.
        normalized: FloatArray = np.nan_to_num(
            standardized[:, self.supported_],
            nan=0.0,
            posinf=_NORMALIZED_ABS_CLIP,
            neginf=-_NORMALIZED_ABS_CLIP,
        )
        np.clip(
            normalized,
            -_NORMALIZED_ABS_CLIP,
            _NORMALIZED_ABS_CLIP,
            out=normalized,
        )
        return normalized

    def score(self, values: ArrayLike) -> AnomalyScores:
        matrix: FloatArray = np.asarray(values, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[0] < 1:
            raise ValueError("anomaly scoring requires at least one 2D row")
        if np.isinf(matrix).any():
            raise ValueError("anomaly features may be missing (NaN), but not infinite")
        normalized = self._normalized(matrix)
        supported = self.supported_
        if supported is None:
            raise RuntimeError("anomaly detector lost its fitted feature mask")
        observed = np.isfinite(matrix) & supported[None, :]
        observed_count = observed.sum(axis=1)
        distance: FloatArray = np.sqrt(
            np.divide(
                np.sum(np.square(normalized) * observed[:, supported], axis=1),
                observed_count,
                out=np.zeros(matrix.shape[0], dtype=np.float64),
                where=observed_count > 0,
            )
        )
        robust = 1.0 - np.exp(-np.maximum(distance, 0.0) / 3.0)
        supported_count = int(supported.sum())
        observed_fraction = (
            observed_count / supported_count
            if supported_count
            else np.zeros(matrix.shape[0], dtype=float)
        )
        score_valid = (observed_count > 0) & (observed_fraction >= self.minimum_observed_fraction)
        isolation: FloatArray | None = None
        if self.model_ is not None and self.isolation_range_ is not None:
            raw = -self.model_.score_samples(normalized)
            low, high = self.isolation_range_
            isolation = np.clip((raw - low) / (high - low), 0.0, 1.0)
            isolation[~score_valid] = 0.0
        combined = robust if isolation is None else (0.55 * robust + 0.45 * isolation)
        combined = np.asarray(combined, dtype=np.float64)
        combined[~score_valid] = 0.0
        return AnomalyScores(
            robust,
            isolation,
            np.clip(combined, 0.0, 1.0),
            observed_fraction,
            supported_count / matrix.shape[1],
            score_valid,
        )
