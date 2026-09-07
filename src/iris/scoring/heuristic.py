"""A bounded, inspectable heuristic priority for transient candidates.

This module intentionally does not call its result a probability.  The score is
a smooth relative-priority index intended as a reproducible baseline until IRIS
has enough outcome data to train and validate a calibrated model.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HeuristicScoreConfig:
    """Scales and weights for the v2 scientific-priority baseline."""

    amplitude_scale_mag: float = 0.8
    fractional_flux_scale: float = 1.0
    significance_midpoint_sigma: float = 4.0
    significance_width_sigma: float = 1.5
    rate_scale_mag_per_day: float = 0.5
    normalized_flux_rate_scale_per_day: float = 0.5
    nondetection_contrast_scale_mag: float = 1.0
    nondetection_flux_significance_scale_sigma: float = 3.0
    nondetection_recency_scale_days: float = 7.0
    sampling_scale_detections: float = 8.0
    amplitude_weight: float = 0.24
    significance_weight: float = 0.22
    temporal_weight: float = 0.15
    nondetection_weight: float = 0.12
    sampling_weight: float = 0.12
    quality_weight: float = 0.15
    minimum_preferred_detections: int = 3

    def __post_init__(self) -> None:
        if (
            isinstance(self.significance_midpoint_sigma, bool)
            or not math.isfinite(self.significance_midpoint_sigma)
            or self.significance_midpoint_sigma < 0
        ):
            raise ValueError("significance_midpoint_sigma must be finite and non-negative")
        positive = {
            "amplitude_scale_mag": self.amplitude_scale_mag,
            "fractional_flux_scale": self.fractional_flux_scale,
            "significance_width_sigma": self.significance_width_sigma,
            "rate_scale_mag_per_day": self.rate_scale_mag_per_day,
            "normalized_flux_rate_scale_per_day": self.normalized_flux_rate_scale_per_day,
            "nondetection_contrast_scale_mag": self.nondetection_contrast_scale_mag,
            "nondetection_flux_significance_scale_sigma": (
                self.nondetection_flux_significance_scale_sigma
            ),
            "nondetection_recency_scale_days": self.nondetection_recency_scale_days,
            "sampling_scale_detections": self.sampling_scale_detections,
        }
        bad = [
            name
            for name, value in positive.items()
            if isinstance(value, bool) or not math.isfinite(value) or value <= 0
        ]
        if bad:
            raise ValueError(f"Score scales must be positive: {bad}")
        weights = self.weights
        if any(
            isinstance(weight, bool) or not math.isfinite(weight) or weight < 0
            for weight in weights.values()
        ):
            raise ValueError("Score weights must be finite and non-negative")
        if not math.isclose(sum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1.0e-9):
            raise ValueError("Score weights must sum to 1.0")
        if (
            isinstance(self.minimum_preferred_detections, bool)
            or not isinstance(self.minimum_preferred_detections, int)
            or self.minimum_preferred_detections < 1
        ):
            raise ValueError("minimum_preferred_detections must be a positive integer")

    @property
    def weights(self) -> dict[str, float]:
        return {
            "amplitude": self.amplitude_weight,
            "significance": self.significance_weight,
            "temporal_shape": self.temporal_weight,
            "prior_nondetection": self.nondetection_weight,
            "sampling": self.sampling_weight,
            "data_quality": self.quality_weight,
        }


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _unit_interval(value: Any, default: float = 0.0) -> float:
    number = _number(value)
    if number is None:
        return default
    return min(1.0, max(0.0, number))


def _soft_positive(value: float | None, scale: float) -> float:
    if value is None or value <= 0:
        return 0.0
    return -math.expm1(-value / scale)


def _sigmoid(value: float | None, midpoint: float, width: float) -> float:
    if value is None:
        return 0.0
    exponent = min(60.0, max(-60.0, -(value - midpoint) / width))
    return 1.0 / (1.0 + math.exp(exponent))


def _component(score: float, weight: float, inputs: Mapping[str, Any]) -> dict[str, Any]:
    bounded = min(1.0, max(0.0, score))
    return {
        "score": round(bounded, 6),
        "weight": weight,
        "weighted_contribution": round(bounded * weight, 6),
        "inputs": dict(inputs),
    }


def score_photometry_candidate(
    features: Mapping[str, Any],
    *,
    config: HeuristicScoreConfig | None = None,
) -> dict[str, Any]:
    """Return transparent component scores and a bounded relative priority.

    ``priority_score`` is useful for ordering candidates evaluated with the same
    configuration.  It is explicitly *not* a probability, confidence, or trained
    calibration and must not be presented as one.
    """

    cfg = config or HeuristicScoreConfig()
    weights = cfg.weights
    warnings = list(features.get("warnings", []))

    amplitude = _number(features.get("max_peak_brightening_mag"))
    robust_amplitude = _number(features.get("median_band_amplitude_mag"))
    flux_amplitude = _number(features.get("max_fractional_flux_excursion"))
    robust_flux_amplitude = _number(features.get("median_fractional_flux_excursion"))
    amplitude_inputs = [value for value in (amplitude, robust_amplitude) if value is not None]
    if amplitude_inputs:
        # The maximum catches a fast event while the median quantile amplitude
        # makes a single deviant point insufficient by itself.
        amplitude_score = (
            0.6 * _soft_positive(max(amplitude_inputs), cfg.amplitude_scale_mag)
            + 0.4 * _soft_positive(robust_amplitude, cfg.amplitude_scale_mag)
            if robust_amplitude is not None
            else 0.6 * _soft_positive(max(amplitude_inputs), cfg.amplitude_scale_mag)
        )
        amplitude_basis = "magnitude"
    elif flux_amplitude is not None or robust_flux_amplitude is not None:
        flux_amplitude_inputs = [
            value for value in (flux_amplitude, robust_flux_amplitude) if value is not None
        ]
        amplitude_score = 0.6 * _soft_positive(
            max(flux_amplitude_inputs), cfg.fractional_flux_scale
        )
        if robust_flux_amplitude is not None:
            amplitude_score += 0.4 * _soft_positive(
                robust_flux_amplitude, cfg.fractional_flux_scale
            )
        amplitude_basis = "forced_flux"
        warnings.append("magnitude_amplitude_missing_using_flux")
    else:
        amplitude_score = 0.0
        amplitude_basis = "missing"
        warnings.append("amplitude_evidence_missing")

    magnitude_significance = _number(features.get("max_peak_significance"))
    flux_significance = _number(features.get("max_flux_peak_significance"))
    significance = _number(features.get("max_detection_significance"))
    if significance is None:
        candidates = [
            value for value in (magnitude_significance, flux_significance) if value is not None
        ]
        significance = max(candidates) if candidates else None
    significance_score = _sigmoid(
        significance,
        cfg.significance_midpoint_sigma,
        cfg.significance_width_sigma,
    )
    if significance is None:
        warnings.append("significance_evidence_missing")
    elif magnitude_significance is None and flux_significance is not None:
        warnings.append("magnitude_significance_missing_using_flux")

    rise_rate = _number(features.get("max_rise_rate_mag_per_day"))
    fade_rate = _number(features.get("max_fade_rate_mag_per_day"))
    flux_rise_rate = _number(features.get("max_normalized_flux_rise_rate_per_day"))
    flux_fade_rate = _number(features.get("max_normalized_flux_fade_rate_per_day"))
    positive_rates = [max(0.0, value) for value in (rise_rate, fade_rate) if value is not None]
    positive_flux_rates = [
        max(0.0, value) for value in (flux_rise_rate, flux_fade_rate) if value is not None
    ]
    if positive_rates:
        temporal_score = _soft_positive(max(positive_rates), cfg.rate_scale_mag_per_day)
        temporal_basis = "magnitude"
    elif positive_flux_rates:
        temporal_score = _soft_positive(
            max(positive_flux_rates), cfg.normalized_flux_rate_scale_per_day
        )
        temporal_basis = "forced_flux"
        warnings.append("magnitude_temporal_shape_missing_using_flux")
    else:
        temporal_score = 0.0
        temporal_basis = "missing"
        warnings.append("temporal_shape_evidence_missing")

    has_prior_nondetection = bool(features.get("has_prior_nondetection", False))
    nondetection_gap = _number(features.get("prior_nondetection_gap_days"))
    nondetection_contrast = _number(features.get("prior_nondetection_contrast_mag"))
    nondetection_flux_significance = _number(
        features.get("prior_forced_flux_contrast_significance")
    )
    if has_prior_nondetection:
        magnitude_contrast_score = _soft_positive(
            max(0.0, nondetection_contrast or 0.0), cfg.nondetection_contrast_scale_mag
        )
        flux_contrast_score = _soft_positive(
            max(0.0, nondetection_flux_significance or 0.0),
            cfg.nondetection_flux_significance_scale_sigma,
        )
        contrast_score = max(magnitude_contrast_score, flux_contrast_score)
        recency_score = (
            math.exp(-max(0.0, nondetection_gap) / cfg.nondetection_recency_scale_days)
            if nondetection_gap is not None
            else 0.0
        )
        nondetection_score = 0.65 * contrast_score + 0.35 * recency_score
    else:
        contrast_score = 0.0
        recency_score = 0.0
        nondetection_score = 0.0

    n_detections = max(0.0, _number(features.get("n_detections")) or 0.0)
    n_bands = max(0.0, _number(features.get("n_bands")) or 0.0)
    significant_points = max(
        0.0,
        _number(
            features.get(
                "n_significant_measurements",
                features.get("n_significant_bright_points"),
            )
        )
        or 0.0,
    )
    count_score = _soft_positive(n_detections, cfg.sampling_scale_detections)
    band_score = _soft_positive(n_bands, 2.0)
    repeat_score = _soft_positive(significant_points, 2.0)
    sampling_score = 0.50 * count_score + 0.20 * band_score + 0.30 * repeat_score

    missing_fraction = _unit_interval(features.get("missing_critical_fraction"), default=1.0)
    quality_rejected = _unit_interval(features.get("quality_rejected_fraction"))
    uncertainty_missing = _unit_interval(
        features.get(
            "measurement_error_missing_fraction",
            features.get("magnitude_error_missing_fraction"),
        )
    )
    detection_rejected = _unit_interval(features.get("rejected_detection_fraction"))
    data_quality_score = (
        1.0
        - 0.40 * missing_fraction
        - 0.25 * quality_rejected
        - 0.20 * uncertainty_missing
        - 0.15 * detection_rejected
    )
    data_quality_score = min(1.0, max(0.0, data_quality_score))

    scores = {
        "amplitude": amplitude_score,
        "significance": significance_score,
        "temporal_shape": temporal_score,
        "prior_nondetection": nondetection_score,
        "sampling": sampling_score,
        "data_quality": data_quality_score,
    }
    raw_score = sum(weights[name] * score for name, score in scores.items())

    # Sparse and highly incomplete records should retain their component evidence
    # but rank below candidates supported by repeat observations.  Smooth factors
    # avoid the threshold saturation of the legacy score.
    sparse_factor = 1.0
    if n_detections < cfg.minimum_preferred_detections:
        sparse_factor = 0.65 + 0.35 * (n_detections / cfg.minimum_preferred_detections)
        warnings.append("sparse_detection_history")
    integrity_factor = 0.75 + 0.25 * data_quality_score
    priority = raw_score * sparse_factor * integrity_factor
    priority = min(0.999999, max(0.0, priority))

    components = {
        "amplitude": _component(
            amplitude_score,
            weights["amplitude"],
            {
                "max_peak_brightening_mag": amplitude,
                "median_band_amplitude_mag": robust_amplitude,
                "max_fractional_flux_excursion": flux_amplitude,
                "median_fractional_flux_excursion": robust_flux_amplitude,
                "basis": amplitude_basis,
            },
        ),
        "significance": _component(
            significance_score,
            weights["significance"],
            {
                "max_detection_significance": significance,
                "max_peak_significance": magnitude_significance,
                "max_flux_peak_significance": flux_significance,
            },
        ),
        "temporal_shape": _component(
            temporal_score,
            weights["temporal_shape"],
            {
                "max_rise_rate_mag_per_day": rise_rate,
                "max_fade_rate_mag_per_day": fade_rate,
                "max_normalized_flux_rise_rate_per_day": flux_rise_rate,
                "max_normalized_flux_fade_rate_per_day": flux_fade_rate,
                "basis": temporal_basis,
            },
        ),
        "prior_nondetection": _component(
            nondetection_score,
            weights["prior_nondetection"],
            {
                "has_prior_nondetection": has_prior_nondetection,
                "contrast_mag": nondetection_contrast,
                "forced_flux_contrast_significance": nondetection_flux_significance,
                "gap_days": nondetection_gap,
                "contrast_subscore": round(contrast_score, 6),
                "recency_subscore": round(recency_score, 6),
            },
        ),
        "sampling": _component(
            sampling_score,
            weights["sampling"],
            {
                "n_detections": int(n_detections),
                "n_bands": int(n_bands),
                "n_significant_measurements": int(significant_points),
            },
        ),
        "data_quality": _component(
            data_quality_score,
            weights["data_quality"],
            {
                "missing_critical_fraction": missing_fraction,
                "quality_rejected_fraction": quality_rejected,
                "measurement_error_missing_fraction": uncertainty_missing,
                "rejected_detection_fraction": detection_rejected,
            },
        ),
    }
    return {
        "score_version": "iris.heuristic_priority.v2",
        "score_kind": "bounded_heuristic_priority",
        "is_probability": False,
        "priority_score": round(priority, 6),
        "raw_weighted_score": round(raw_score, 6),
        "components": components,
        "adjustments": {
            "sparse_history_factor": round(sparse_factor, 6),
            "data_integrity_factor": round(integrity_factor, 6),
        },
        "warnings": sorted(set(warnings)),
        "interpretation": (
            "Relative heuristic review priority only; not a probability, "
            "confidence estimate, or trained calibration."
        ),
    }
