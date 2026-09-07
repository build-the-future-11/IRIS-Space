"""Filter-aware features for irregular astronomical photometry.

Raw measurements from different survey/passband channels are never pooled.
Statistics that span channels are made only from quantities that are safe to
compare: within-channel magnitude differences, dimensionless relative fluxes,
significances, rates, and counts. Undefined measurements are represented by
``None`` rather than a fabricated zero so downstream models can distinguish
absence of evidence from negative evidence.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from iris.bands import normalize_passband

_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "time": ("mjd", "jd", "time", "observation_time", "timestamp"),
    "band": ("band", "filter", "fid", "filtercode", "bandname"),
    "magnitude": ("magnitude", "mag", "magpsf_corr", "magpsf", "psfmag"),
    "magnitude_error": (
        "magnitude_error",
        "mag_error",
        "magerr",
        "sigmapsf_corr",
        "sigmapsf",
        "e_mag",
    ),
    "is_detection": ("is_detection", "detected", "isdetection", "detection"),
    "limiting_magnitude": (
        "limiting_magnitude",
        "limiting_mag",
        "limmag",
        "diffmaglim",
        "mag_limit",
    ),
    "flux": ("flux", "difference_flux", "forcediffimflux", "fluxpsf"),
    "flux_error": ("flux_error", "fluxerr", "sigma_flux", "forcediffimfluxunc"),
    "quality": ("quality_ok", "is_good", "good_quality", "catflags", "quality", "flags"),
    "survey": ("survey", "instrument", "facility", "telescope"),
}


@dataclass(frozen=True)
class PhotometryFeatureConfig:
    """Controls validity checks without encoding a survey-specific schema."""

    max_magnitude_error: float | None = 1.0
    max_quality_flag: float = 0.0
    significance_sigma: float = 3.0
    min_rate_span_days: float = 1.0e-3
    recent_nondetection_days: float = 7.0
    map_ztf_numeric_bands: bool = True
    ztf_numeric_surveys: tuple[str, ...] = ("ztf", "alerce", "ztf/alerce")

    def __post_init__(self) -> None:
        if self.max_magnitude_error is not None and (
            isinstance(self.max_magnitude_error, bool)
            or not math.isfinite(self.max_magnitude_error)
            or self.max_magnitude_error <= 0
        ):
            raise ValueError("max_magnitude_error must be positive or None")
        if isinstance(self.max_quality_flag, bool) or not math.isfinite(self.max_quality_flag):
            raise ValueError("max_quality_flag must be finite")
        if (
            isinstance(self.significance_sigma, bool)
            or not math.isfinite(self.significance_sigma)
            or self.significance_sigma <= 0
        ):
            raise ValueError("significance_sigma must be finite and positive")
        if (
            isinstance(self.min_rate_span_days, bool)
            or not math.isfinite(self.min_rate_span_days)
            or self.min_rate_span_days <= 0
        ):
            raise ValueError("min_rate_span_days must be finite and positive")
        if (
            isinstance(self.recent_nondetection_days, bool)
            or not math.isfinite(self.recent_nondetection_days)
            or self.recent_nondetection_days < 0
        ):
            raise ValueError("recent_nondetection_days must be finite and non-negative")
        if not isinstance(self.map_ztf_numeric_bands, bool):
            raise TypeError("map_ztf_numeric_bands must be boolean")
        surveys = tuple(str(value).strip().casefold() for value in self.ztf_numeric_surveys)
        if not surveys or any(not value for value in surveys):
            raise ValueError("ztf_numeric_surveys must contain non-empty names")
        if len(set(surveys)) != len(surveys):
            raise ValueError("ztf_numeric_surveys must be unique")
        object.__setattr__(self, "ztf_numeric_surveys", surveys)


def _as_frame(observations: pd.DataFrame | Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    if isinstance(observations, pd.DataFrame):
        return observations.copy()
    if isinstance(observations, Mapping):
        try:
            return pd.DataFrame(observations)
        except ValueError:
            return pd.DataFrame.from_records([observations])
    return pd.DataFrame.from_records(list(observations))


def _resolve_columns(
    frame: pd.DataFrame,
    column_map: Mapping[str, str] | None,
) -> dict[str, str | None]:
    explicit = dict(column_map or {})
    unknown = set(explicit) - set(_COLUMN_ALIASES)
    if unknown:
        raise ValueError(f"Unknown logical columns in column_map: {sorted(unknown)}")

    by_lower: dict[str, list[str]] = {}
    for column in frame.columns:
        by_lower.setdefault(str(column).casefold(), []).append(str(column))
    duplicate_case = [matches for matches in by_lower.values() if len(matches) > 1]
    if duplicate_case:
        raise ValueError(f"Photometry columns differ only by case: {duplicate_case}")
    resolved: dict[str, str | None] = {}
    for logical, aliases in _COLUMN_ALIASES.items():
        requested = explicit.get(logical)
        if requested is not None:
            if requested not in frame.columns:
                raise ValueError(f"Mapped column {requested!r} for {logical!r} is absent")
            resolved[logical] = requested
            continue
        canonical = by_lower.get(logical.casefold(), [])
        if canonical:
            resolved[logical] = canonical[0]
            continue
        matches = [by_lower[name.casefold()][0] for name in aliases if name.casefold() in by_lower]
        matches = list(dict.fromkeys(matches))
        if len(matches) > 1:
            raise ValueError(
                f"Ambiguous photometry columns for {logical!r}: {matches}; supply column_map"
            )
        resolved[logical] = matches[0] if matches else None

    missing = [logical for logical in ("time", "band") if resolved[logical] is None]
    if missing:
        raise ValueError(
            f"Photometry is missing required logical columns {missing}; "
            f"available columns are {list(frame.columns)}"
        )
    if all(resolved[name] is None for name in ("magnitude", "limiting_magnitude", "flux")):
        raise ValueError("Photometry needs a magnitude, flux, or limiting-magnitude column")
    if resolved["is_detection"] is None and resolved["magnitude"] is None:
        raise ValueError("Flux-only photometry requires an explicit detection column")
    return resolved


def _numeric(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _coerce_detection(series: pd.Series | None, magnitude: pd.Series) -> pd.Series:
    if series is None:
        return magnitude.notna()
    missing = series.isna() | series.astype("string").str.strip().eq("")
    if missing.any():
        rows = series.index[missing].tolist()[:10]
        raise ValueError(f"Explicit detection column has missing values at row(s) {rows}")
    if pd.api.types.is_bool_dtype(series.dtype):
        return series.astype(bool)
    numeric = pd.to_numeric(series, errors="coerce")
    numeric_rows = numeric.notna()
    invalid_numeric = numeric_rows & ~numeric.isin([0, 1])
    if invalid_numeric.any():
        values = sorted(set(numeric.loc[invalid_numeric].tolist()))
        raise ValueError(f"Detection values must be boolean or 0/1, got {values}")
    result = numeric.eq(1) & numeric_rows
    unresolved = numeric.isna() & series.notna()
    if unresolved.any():
        words = series.astype(str).str.strip().str.lower()
        truthy = {"true", "t", "yes", "y", "detected", "detection", "1"}
        falsey = {"false", "f", "no", "n", "nondetection", "non-detection", "0"}
        unknown = unresolved & ~words.isin(truthy | falsey)
        if unknown.any():
            values = sorted(set(words.loc[unknown].tolist()))
            raise ValueError(f"Unrecognized detection values: {values}")
        result.loc[unresolved] = words.loc[unresolved].isin(truthy)
    return result.astype(bool)


def _normalize_band(value: Any, *, map_ztf_numeric: bool) -> str | None:
    return normalize_passband(value, map_ztf_numeric=map_ztf_numeric)


def _normalize_survey(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = " ".join(str(value).strip().casefold().split())
    return None if not text or text in {"<na>", "nan", "nat", "none", "null"} else text


def _channel_id(survey: str | None, band: str | None, *, survey_column_present: bool) -> str | None:
    if band is None:
        return None
    if not survey_column_present:
        return band
    survey_name = survey or "unspecified"
    return f"{quote(survey_name, safe='-._~')}::{quote(band, safe='-._~')}"


def _quality_mask(
    frame: pd.DataFrame,
    column: str | None,
    max_quality_flag: float,
) -> pd.Series:
    if column is None:
        return pd.Series(True, index=frame.index, dtype=bool)
    series = frame[column]
    name = str(column).lower()
    positive_semantics = name == "quality" or any(
        token in name for token in ("_ok", "is_good", "good_")
    )
    if pd.api.types.is_bool_dtype(series.dtype):
        values = series.fillna(False).astype(bool)
        return values if positive_semantics else ~values

    numeric = pd.to_numeric(series, errors="coerce")
    if positive_semantics:
        result = numeric.gt(0) & numeric.notna()
    else:
        result = numeric.ge(0) & numeric.le(max_quality_flag) & numeric.notna()
    unresolved = numeric.isna() & series.notna()
    if unresolved.any():
        words = series.astype(str).str.strip().str.lower()
        good_words = {"good", "clean", "ok", "pass", "passed", "true", "t", "yes", "y"}
        if positive_semantics:
            result.loc[unresolved] = words.loc[unresolved].isin(good_words)
        else:
            clear_words = good_words | {"false", "f", "no", "n", "clear"}
            result.loc[unresolved] = words.loc[unresolved].isin(clear_words)
    return result.fillna(False).astype(bool)


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _median_or_none(values: Iterable[Any]) -> float | None:
    array = np.asarray(
        [value for value in values if _finite_or_none(value) is not None],
        dtype=float,
    )
    return _safe_median(array) if array.size else None


def _max_or_none(values: Iterable[Any]) -> float | None:
    finite = [_finite_or_none(value) for value in values]
    kept = [value for value in finite if value is not None]
    return float(max(kept)) if kept else None


def _min_or_none(values: Iterable[Any]) -> float | None:
    finite = [_finite_or_none(value) for value in values]
    kept = [value for value in finite if value is not None]
    return float(min(kept)) if kept else None


def _difference_significance(
    first_value: float,
    second_value: float,
    first_error: float,
    second_error: float,
) -> float | None:
    """Return a finite two-point difference significance without overflow."""

    scale = max(
        abs(first_value),
        abs(second_value),
        abs(first_error),
        abs(second_error),
    )
    if scale <= 0.0:
        return None
    numerator = first_value / scale - second_value / scale
    denominator = math.hypot(first_error / scale, second_error / scale)
    if denominator <= 0.0:
        return None
    return _finite_or_none(numerator / denominator)


def _safe_median(values: NDArray[np.float64]) -> float:
    """Return a median without overflowing while averaging two finite values."""

    ordered = np.sort(values)
    middle = ordered.size // 2
    if ordered.size % 2:
        return float(ordered[middle])
    lower = float(ordered[middle - 1])
    upper = float(ordered[middle])
    if lower == upper:
        return lower
    return lower / 2.0 + upper / 2.0


def _robust_scatter(values: NDArray[np.float64]) -> float:
    if values.size < 2:
        return 0.0
    median = _safe_median(values)
    mad = _safe_median(np.abs(values - median))
    maximum = float(np.finfo(np.float64).max)
    return maximum if mad > maximum / 1.4826 else 1.4826 * mad


def _weighted_slope(
    times: NDArray[np.float64],
    values: NDArray[np.float64],
    errors: NDArray[np.float64],
) -> float | None:
    finite = np.isfinite(times) & np.isfinite(values)
    times = times[finite]
    values = values[finite]
    errors = errors[finite]
    if times.size < 2 or np.unique(times).size < 2:
        return None
    weights = np.ones_like(times, dtype=float)
    has_error = np.isfinite(errors) & (errors > 0)
    # Mixing unit-valued weights for missing errors with inverse-variance
    # weights makes the result depend on the measurement unit. Use weighted
    # regression only when every retained point has a supplied uncertainty.
    if bool(has_error.all()):
        # Relative inverse-variance weights are mathematically equivalent and
        # avoid overflow when a valid uncertainty is extremely small or large.
        reference_error = float(np.min(errors))
        weights = np.square(reference_error / errors)
    centered = times - np.average(times, weights=weights)
    denominator = float(np.sum(weights * np.square(centered)))
    if denominator <= 0:
        return None
    # Center values before averaging so a constant, very large finite signal
    # does not overflow a weighted sum merely to produce a zero slope.
    relative_values = values - float(values[0])
    numerical_scale = float(np.max(np.abs(relative_values)))
    scaled_values = relative_values / numerical_scale if numerical_scale > 0.0 else relative_values
    relative_center = np.average(scaled_values, weights=weights)
    scaled_slope = float(
        np.sum(weights * centered * (scaled_values - relative_center)) / denominator
    )
    slope = scaled_slope * numerical_scale if numerical_scale > 0.0 else scaled_slope
    return slope if math.isfinite(slope) else None


def _band_features(
    group: pd.DataFrame,
    config: PhotometryFeatureConfig,
) -> tuple[dict[str, Any], set[int]]:
    ordered = group.sort_values("_time", kind="stable")
    times = ordered["_time"].to_numpy(dtype=float)
    mags = ordered["_magnitude"].to_numpy(dtype=float)
    errors = ordered["_magnitude_error"].to_numpy(dtype=float)
    row_positions = ordered["_row_position"].to_numpy(dtype=np.int64)
    magnitude_span = float(np.max(mags)) - float(np.min(mags))
    maximum_log10 = math.log10(np.finfo(np.float64).max)
    if not math.isfinite(magnitude_span) or 0.4 * magnitude_span > maximum_log10:
        raise ValueError("magnitude dynamic range is too large for finite derived features")

    median_mag = _safe_median(mags)
    scatter = _robust_scatter(mags)
    q10, q90 = np.quantile(mags, [0.1, 0.9]) if mags.size > 1 else (mags[0], mags[0])
    peak_index = int(np.argmin(mags))
    peak_mag = float(mags[peak_index])
    peak_time = float(times[peak_index])
    peak_error = errors[peak_index]
    peak_brightening = max(0.0, median_mag - peak_mag)

    comparison = np.delete(mags, peak_index)
    comparison_errors = np.delete(errors, peak_index)
    baseline_mag = _safe_median(comparison) if comparison.size else median_mag
    baseline_scatter = _robust_scatter(comparison)
    valid_comparison_errors = comparison_errors[
        np.isfinite(comparison_errors) & (comparison_errors > 0)
    ]
    comparison_uncertainty_complete = bool(comparison.size) and (
        valid_comparison_errors.size == comparison_errors.size
    )
    baseline_error = (
        _safe_median(valid_comparison_errors) / math.sqrt(valid_comparison_errors.size)
        if comparison_uncertainty_complete
        else 0.0
    )
    peak_contrast = max(0.0, baseline_mag - peak_mag)
    peak_error_valid = math.isfinite(float(peak_error)) and peak_error > 0
    denominator = (
        math.hypot(baseline_scatter, baseline_error, float(peak_error))
        if peak_error_valid and comparison_uncertainty_complete
        else 0.0
    )
    peak_significance = peak_contrast / denominator if denominator > 0 else None

    significant = np.zeros(mags.shape, dtype=bool)
    for index, (magnitude, error) in enumerate(zip(mags, errors, strict=True)):
        other = np.delete(mags, index)
        if not other.size or not math.isfinite(float(error)) or error <= 0:
            continue
        other_errors = np.delete(errors, index)
        finite_other_errors = other_errors[np.isfinite(other_errors) & (other_errors > 0)]
        if finite_other_errors.size != other_errors.size:
            continue
        other_error = (
            _safe_median(finite_other_errors) / math.sqrt(finite_other_errors.size)
            if finite_other_errors.size
            else 0.0
        )
        point_denominator = math.hypot(float(error), _robust_scatter(other), other_error)
        contrast = float(_safe_median(other) - magnitude)
        significant[index] = (
            point_denominator > 0 and contrast / point_denominator >= config.significance_sigma
        )

    pre_peak = times <= peak_time
    post_peak = times >= peak_time
    pre_slope = _weighted_slope(times[pre_peak], mags[pre_peak], errors[pre_peak])
    post_slope = _weighted_slope(times[post_peak], mags[post_peak], errors[post_peak])
    pre_span = peak_time - float(np.min(times[pre_peak]))
    post_span = float(np.max(times[post_peak])) - peak_time
    if pre_span < config.min_rate_span_days:
        pre_slope = None
    if post_span < config.min_rate_span_days:
        post_slope = None

    cadence = np.diff(np.unique(times))
    cadence = cadence[cadence > 0]
    relative_peak_flux = float(10.0 ** (0.4 * peak_brightening))

    return {
        "n_detections": int(mags.size),
        "first_detection_time": float(np.min(times)),
        "last_detection_time": float(np.max(times)),
        "detection_baseline_days": float(np.max(times) - np.min(times)),
        "median_cadence_days": _safe_median(cadence) if cadence.size else None,
        "median_magnitude": median_mag,
        "robust_scatter_mag": scatter,
        "amplitude_p90_p10_mag": float(max(0.0, q90 - q10)),
        "peak_magnitude": peak_mag,
        "peak_time": peak_time,
        "peak_brightening_mag": peak_brightening,
        "peak_contrast_mag": peak_contrast,
        "peak_relative_flux": relative_peak_flux,
        "peak_significance": _finite_or_none(peak_significance),
        "n_significant_bright_points": int(np.sum(significant)),
        "rise_slope_mag_per_day": _finite_or_none(pre_slope),
        "rise_rate_mag_per_day": _finite_or_none(-pre_slope) if pre_slope is not None else None,
        "fade_slope_mag_per_day": _finite_or_none(post_slope),
        "fade_rate_mag_per_day": _finite_or_none(post_slope) if post_slope is not None else None,
        "median_magnitude_error": _median_or_none(errors),
        "magnitude_error_missing_fraction": float(np.mean(~np.isfinite(errors))),
    }, set(int(value) for value in row_positions[significant])


def _flux_band_features(
    group: pd.DataFrame,
    config: PhotometryFeatureConfig,
) -> tuple[dict[str, Any], set[int]]:
    """Compute unit-invariant, within-band features for forced/difference flux."""

    ordered = group.sort_values("_time", kind="stable")
    times = ordered["_time"].to_numpy(dtype=float)
    fluxes = ordered["_flux"].to_numpy(dtype=float)
    errors = ordered["_flux_error"].to_numpy(dtype=float)
    row_positions = ordered["_row_position"].to_numpy(dtype=np.int64)
    flux_span = float(np.max(fluxes)) - float(np.min(fluxes))
    if not math.isfinite(flux_span):
        raise ValueError("flux dynamic range is too large for finite derived features; rescale it")
    median_flux = _safe_median(fluxes)
    scatter = _robust_scatter(fluxes)
    q10, q90 = np.quantile(fluxes, [0.1, 0.9]) if fluxes.size > 1 else (fluxes[0], fluxes[0])
    peak_index = int(np.argmax(fluxes))
    peak_flux = float(fluxes[peak_index])
    peak_time = float(times[peak_index])
    comparison = np.delete(fluxes, peak_index)
    comparison_errors = np.delete(errors, peak_index)
    baseline = _safe_median(comparison) if comparison.size else median_flux
    baseline_scatter = _robust_scatter(comparison)
    finite_comparison_errors = comparison_errors[
        np.isfinite(comparison_errors) & (comparison_errors > 0)
    ]
    comparison_uncertainty_complete = bool(comparison.size) and (
        finite_comparison_errors.size == comparison_errors.size
    )
    baseline_error = (
        _safe_median(finite_comparison_errors) / math.sqrt(finite_comparison_errors.size)
        if comparison_uncertainty_complete
        else 0.0
    )
    peak_error = float(errors[peak_index])
    peak_error_valid = math.isfinite(peak_error) and peak_error > 0
    denominator = (
        math.hypot(baseline_scatter, baseline_error, peak_error)
        if peak_error_valid and comparison_uncertainty_complete
        else 0.0
    )
    contrast = max(0.0, peak_flux - baseline)
    significance = contrast / denominator if denominator > 0 else None
    significant = np.zeros(fluxes.shape, dtype=bool)
    for index, (flux, error) in enumerate(zip(fluxes, errors, strict=True)):
        other = np.delete(fluxes, index)
        if not other.size or not math.isfinite(float(error)) or error <= 0:
            continue
        other_errors = np.delete(errors, index)
        finite_other_errors = other_errors[np.isfinite(other_errors) & (other_errors > 0)]
        if finite_other_errors.size != other_errors.size:
            continue
        other_error = (
            _safe_median(finite_other_errors) / math.sqrt(finite_other_errors.size)
            if finite_other_errors.size
            else 0.0
        )
        point_denominator = math.hypot(float(error), _robust_scatter(other), other_error)
        point_contrast = float(flux - _safe_median(other))
        significant[index] = (
            point_denominator > 0
            and point_contrast / point_denominator >= config.significance_sigma
        )
    finite_errors = errors[np.isfinite(errors) & (errors > 0)]
    typical_error = _safe_median(finite_errors) if finite_errors.size else 0.0
    # This scale makes excursions comparable while remaining invariant under a
    # change of flux units. It is not a physical flux ratio or magnitude.
    scale = max(abs(median_flux), scatter, typical_error)
    if scale <= 0:
        scale = 1.0

    pre_peak = times <= peak_time
    post_peak = times >= peak_time
    # Fit already-normalized flux so the requested normalized rate never forms
    # an overflowing raw-flux slope only to divide it back down afterward.
    normalized_fluxes = fluxes / scale
    pre_slope = _weighted_slope(times[pre_peak], normalized_fluxes[pre_peak], errors[pre_peak])
    post_slope = _weighted_slope(times[post_peak], normalized_fluxes[post_peak], errors[post_peak])
    if peak_time - float(np.min(times[pre_peak])) < config.min_rate_span_days:
        pre_slope = None
    if float(np.max(times[post_peak])) - peak_time < config.min_rate_span_days:
        post_slope = None

    return {
        "flux_n_detections": int(fluxes.size),
        "flux_median": median_flux,
        "flux_robust_scatter": scatter,
        "flux_amplitude_p90_p10": float(max(0.0, q90 - q10)),
        "flux_peak": peak_flux,
        "flux_peak_time": peak_time,
        "flux_peak_contrast": contrast,
        "flux_scale": scale,
        "fractional_flux_excursion": contrast / scale,
        "flux_peak_significance": _finite_or_none(significance),
        "n_significant_flux_points": int(np.sum(significant)),
        "normalized_flux_rise_rate_per_day": (
            _finite_or_none(max(0.0, pre_slope)) if pre_slope is not None else None
        ),
        "normalized_flux_fade_rate_per_day": (
            _finite_or_none(max(0.0, -post_slope)) if post_slope is not None else None
        ),
        "median_flux_error": _median_or_none(errors),
        "flux_error_missing_fraction": float(np.mean(~np.isfinite(errors))),
    }, set(int(value) for value in row_positions[significant])


def compute_photometry_features(
    observations: pd.DataFrame | Iterable[Mapping[str, Any]],
    *,
    column_map: Mapping[str, str] | None = None,
    config: PhotometryFeatureConfig | None = None,
) -> dict[str, Any]:
    """Compute a JSON-serializable feature record for one astronomical source.

    Parameters
    ----------
    observations:
        A data frame or iterable of observation mappings.  Common broker aliases
        (for example ``mjd``, ``fid``, ``magpsf`` and ``diffmaglim``) are
        recognized automatically.
    column_map:
        Optional mapping from logical names such as ``time`` or ``magnitude`` to
        input column names.  This is useful for survey-specific tables.
    config:
        Validity and feature thresholds.
    """

    frame = _as_frame(observations)
    cfg = config or PhotometryFeatureConfig()
    if frame.empty:
        return {
            "feature_schema": "iris.photometry.v4",
            "n_observations": 0,
            "n_detections_raw": 0,
            "n_detections": 0,
            "n_nondetections": 0,
            "n_bands": 0,
            "bands": [],
            "n_channels": 0,
            "channels": [],
            "band_features": {},
            "missing_critical_fraction": 1.0,
            "quality_rejected_fraction": 0.0,
            "warnings": ["empty_photometry"],
        }

    columns = _resolve_columns(frame, column_map)
    normalized = pd.DataFrame(index=frame.index)
    # DataFrame indices need not be unique.  A private positional identity lets
    # magnitude and flux significance masks be unioned exactly without
    # conflating distinct observations that share an upstream index label.
    normalized["_row_position"] = np.arange(len(frame), dtype=np.int64)
    normalized["_time"] = _numeric(frame, columns["time"])
    if bool((normalized["_time"].dropna().abs() > 1_000_000.0).any()):
        raise ValueError("observation times must be MJD/relative days, not JD or Unix timestamps")
    survey_column_present = columns["survey"] is not None
    if survey_column_present:
        normalized["_survey"] = frame[columns["survey"]].map(_normalize_survey)
    else:
        normalized["_survey"] = pd.Series(None, index=frame.index, dtype=object)

    raw_bands = frame[columns["band"]]
    normalized_bands: list[str | None] = []
    for raw_band, survey in zip(raw_bands, normalized["_survey"], strict=True):
        ztf_context = not survey_column_present or survey in cfg.ztf_numeric_surveys
        normalized_bands.append(
            _normalize_band(
                raw_band,
                map_ztf_numeric=cfg.map_ztf_numeric_bands and ztf_context,
            )
        )
    normalized["_band"] = normalized_bands
    normalized["_channel"] = [
        _channel_id(survey, band, survey_column_present=survey_column_present)
        for survey, band in zip(normalized["_survey"], normalized["_band"], strict=True)
    ]
    normalized["_magnitude"] = _numeric(frame, columns["magnitude"])
    normalized["_magnitude_error"] = _numeric(frame, columns["magnitude_error"])
    normalized["_limiting_magnitude"] = _numeric(frame, columns["limiting_magnitude"])
    normalized["_flux"] = _numeric(frame, columns["flux"])
    normalized["_flux_error"] = _numeric(frame, columns["flux_error"])
    detection_series = (
        frame[columns["is_detection"]] if columns["is_detection"] is not None else None
    )
    if (
        detection_series is None
        and not np.isfinite(normalized["_magnitude"]).any()
        and np.isfinite(normalized["_flux"]).any()
    ):
        raise ValueError("Flux-only photometry requires an explicit detection column")
    normalized["_is_detection"] = _coerce_detection(detection_series, normalized["_magnitude"])
    normalized["_quality_ok"] = _quality_mask(frame, columns["quality"], cfg.max_quality_flag)

    raw_detection = normalized["_is_detection"]
    raw_nondetection = ~raw_detection
    time_ok = np.isfinite(normalized["_time"])
    band_ok = normalized["_channel"].notna()
    mag_ok = np.isfinite(normalized["_magnitude"])
    flux_ok = np.isfinite(normalized["_flux"])
    mag_error = normalized["_magnitude_error"]
    flux_error = normalized["_flux_error"]
    mag_error_valid = np.isfinite(mag_error) & mag_error.gt(0)
    flux_error_valid = np.isfinite(flux_error) & flux_error.gt(0)
    invalid_mag_error = mag_error.notna() & ~mag_error_valid
    if cfg.max_magnitude_error is not None:
        invalid_mag_error |= mag_error.notna() & mag_error.gt(cfg.max_magnitude_error)
    invalid_flux_error = flux_error.notna() & ~flux_error_valid

    common_detection = raw_detection & time_ok & band_ok & normalized["_quality_ok"]
    valid_magnitude_detection = common_detection & mag_ok & ~invalid_mag_error
    valid_flux_detection = common_detection & flux_ok & ~invalid_flux_error
    valid_detection = valid_magnitude_detection | valid_flux_detection
    nondetection_measurement_ok = np.isfinite(normalized["_limiting_magnitude"]) | flux_ok
    valid_nondetection = (
        raw_nondetection
        & time_ok
        & band_ok
        & normalized["_quality_ok"]
        & nondetection_measurement_ok
    )

    critical_ok = time_ok & band_ok
    critical_ok &= np.where(raw_detection, mag_ok | flux_ok, nondetection_measurement_ok)

    detections = normalized.loc[valid_detection].copy()
    magnitude_detections = normalized.loc[valid_magnitude_detection].copy()
    flux_detections = normalized.loc[valid_flux_detection].copy()
    nondetections = normalized.loc[valid_nondetection].copy()
    band_results: dict[str, dict[str, Any]] = {}
    channel_names = sorted(
        set(magnitude_detections["_channel"].astype(str))
        | set(flux_detections["_channel"].astype(str))
    )
    for channel in channel_names:
        values: dict[str, Any] = {}
        significant_positions: set[int] = set()
        magnitude_group = magnitude_detections[magnitude_detections["_channel"] == channel]
        flux_group = flux_detections[flux_detections["_channel"] == channel]
        metadata_group = magnitude_group if not magnitude_group.empty else flux_group
        values["survey"] = (
            _normalize_survey(metadata_group.iloc[0]["_survey"]) if survey_column_present else None
        )
        values["passband"] = str(metadata_group.iloc[0]["_band"])
        values["channel_id"] = channel
        if not magnitude_group.empty:
            magnitude_features, magnitude_significant = _band_features(magnitude_group, cfg)
            values.update(magnitude_features)
            significant_positions.update(magnitude_significant)
        if not flux_group.empty:
            flux_features, flux_significant = _flux_band_features(flux_group, cfg)
            values.update(flux_features)
            significant_positions.update(flux_significant)
        values["n_significant_measurements"] = len(significant_positions)
        band_results[channel] = values

    prior_pairs: list[dict[str, float | str]] = []
    for channel, detection_group in detections.groupby("_channel", sort=True):
        first = detection_group.sort_values("_time", kind="stable").iloc[0]
        eligible = nondetections[
            (nondetections["_channel"] == channel) & (nondetections["_time"] < first["_time"])
        ]
        if eligible.empty:
            continue
        previous = eligible.sort_values("_time", kind="stable").iloc[-1]
        pair: dict[str, float | str] = {
            "channel": str(channel),
            "band": str(first["_band"]),
            "gap_days": float(first["_time"] - previous["_time"]),
        }
        if first["_survey"] is not None:
            pair["survey"] = str(first["_survey"])
        if math.isfinite(float(previous["_limiting_magnitude"])) and math.isfinite(
            float(first["_magnitude"])
        ):
            contrast_mag = _finite_or_none(
                float(previous["_limiting_magnitude"]) - float(first["_magnitude"])
            )
            if contrast_mag is not None:
                pair["contrast_mag"] = contrast_mag
        if math.isfinite(float(previous["_flux"])):
            previous_error = float(previous["_flux_error"])
            if math.isfinite(previous_error) and previous_error > 0:
                prior_snr = _finite_or_none(abs(float(previous["_flux"]) / previous_error))
                if prior_snr is not None:
                    pair["prior_forced_flux_snr"] = prior_snr
            first_error = float(first["_flux_error"])
            if (
                math.isfinite(float(first["_flux"]))
                and math.isfinite(first_error)
                and first_error > 0
                and math.isfinite(previous_error)
                and previous_error > 0
            ):
                flux_contrast_significance = _difference_significance(
                    float(first["_flux"]),
                    float(previous["_flux"]),
                    first_error,
                    previous_error,
                )
                if flux_contrast_significance is not None:
                    pair["forced_flux_contrast_significance"] = max(
                        0.0,
                        flux_contrast_significance,
                    )
        prior_pairs.append(pair)

    band_values = list(band_results.values())
    magnitude_band_values = [band for band in band_values if "peak_brightening_mag" in band]
    flux_band_values = [band for band in band_values if "fractional_flux_excursion" in band]
    all_times = detections["_time"].to_numpy(dtype=float)
    raw_detection_count = int(raw_detection.sum())
    raw_nondetection_count = int(raw_nondetection.sum())
    quality_rejected = int((~normalized["_quality_ok"]).sum())
    raw_with_magnitude = raw_detection & mag_ok
    raw_with_flux = raw_detection & flux_ok
    missing_mag_uncertainty = raw_with_magnitude & ~mag_error_valid
    missing_flux_uncertainty = raw_with_flux & ~flux_error_valid
    has_any_valid_uncertainty = (raw_with_magnitude & mag_error_valid) | (
        raw_with_flux & flux_error_valid
    )
    missing_measurement_uncertainty = raw_detection & ~has_any_valid_uncertainty
    warnings: list[str] = []
    if detections.empty:
        warnings.append("no_valid_detections")
    if quality_rejected:
        warnings.append("quality_rejections_present")
    if bool(missing_measurement_uncertainty.any()):
        warnings.append("missing_detection_uncertainties")
    if bool(invalid_mag_error.any()):
        warnings.append("invalid_or_large_uncertainties_rejected")
    if bool(invalid_flux_error.any()):
        warnings.append("invalid_flux_uncertainties_rejected")
    if bool((~critical_ok).any()):
        warnings.append("incomplete_observations_present")
    if bool((valid_flux_detection & ~valid_magnitude_detection).any()):
        warnings.append("flux_only_detections_present")
    observed_surveys = {
        str(value) for value in normalized.loc[band_ok, "_survey"] if value is not None
    }
    if len(observed_surveys) > 1:
        warnings.append("multi_survey_channels_separated")
    if survey_column_present and normalized["_survey"].isna().any():
        warnings.append("missing_survey_identity_separated")

    magnitude_significance = _max_or_none(
        band.get("peak_significance") for band in magnitude_band_values
    )
    flux_significance = _max_or_none(
        band.get("flux_peak_significance") for band in flux_band_values
    )
    result: dict[str, Any] = {
        "feature_schema": "iris.photometry.v4",
        "n_observations": int(len(normalized)),
        "n_detections_raw": raw_detection_count,
        "n_detections": int(len(detections)),
        "n_rejected_detections": int(raw_detection_count - len(detections)),
        "n_nondetections_raw": raw_nondetection_count,
        "n_nondetections": int(len(nondetections)),
        "n_rejected_nondetections": int(raw_nondetection_count - len(nondetections)),
        "n_nondetections_with_limit": int(np.isfinite(nondetections["_limiting_magnitude"]).sum()),
        "n_nondetections_with_forced_flux": int(np.isfinite(nondetections["_flux"]).sum()),
        "n_bands": int(detections["_band"].nunique()),
        "bands": sorted(set(detections["_band"].dropna().astype(str))),
        "n_channels": int(len(band_results)),
        "channels": sorted(band_results),
        "band_features": band_results,
        "first_detection_time": float(np.min(all_times)) if all_times.size else None,
        "last_detection_time": float(np.max(all_times)) if all_times.size else None,
        "detection_baseline_days": (
            float(np.max(all_times) - np.min(all_times)) if all_times.size else None
        ),
        "median_band_amplitude_mag": _median_or_none(
            band.get("amplitude_p90_p10_mag") for band in magnitude_band_values
        ),
        "max_band_amplitude_mag": _max_or_none(
            band.get("amplitude_p90_p10_mag") for band in magnitude_band_values
        ),
        "max_peak_brightening_mag": _max_or_none(
            band.get("peak_brightening_mag") for band in magnitude_band_values
        ),
        "max_peak_relative_flux": _max_or_none(
            band.get("peak_relative_flux") for band in magnitude_band_values
        ),
        "max_peak_significance": magnitude_significance,
        "median_peak_significance": _median_or_none(
            band.get("peak_significance") for band in magnitude_band_values
        ),
        "median_fractional_flux_excursion": _median_or_none(
            band.get("fractional_flux_excursion") for band in flux_band_values
        ),
        "max_fractional_flux_excursion": _max_or_none(
            band.get("fractional_flux_excursion") for band in flux_band_values
        ),
        "max_flux_peak_significance": flux_significance,
        "max_detection_significance": _max_or_none((magnitude_significance, flux_significance)),
        "n_significant_bright_points": int(
            sum(int(band.get("n_significant_bright_points", 0)) for band in band_values)
        ),
        "n_significant_flux_points": int(
            sum(int(band.get("n_significant_flux_points", 0)) for band in band_values)
        ),
        "n_significant_measurements": int(
            sum(int(band.get("n_significant_measurements", 0)) for band in band_values)
        ),
        "max_rise_rate_mag_per_day": _max_or_none(
            max(0.0, float(band["rise_rate_mag_per_day"]))
            if band.get("rise_rate_mag_per_day") is not None
            else None
            for band in magnitude_band_values
        ),
        "max_fade_rate_mag_per_day": _max_or_none(
            max(0.0, float(band["fade_rate_mag_per_day"]))
            if band.get("fade_rate_mag_per_day") is not None
            else None
            for band in magnitude_band_values
        ),
        "max_normalized_flux_rise_rate_per_day": _max_or_none(
            band.get("normalized_flux_rise_rate_per_day") for band in flux_band_values
        ),
        "max_normalized_flux_fade_rate_per_day": _max_or_none(
            band.get("normalized_flux_fade_rate_per_day") for band in flux_band_values
        ),
        "has_prior_nondetection": bool(prior_pairs),
        "n_bands_with_prior_nondetection": len({str(pair["band"]) for pair in prior_pairs}),
        "n_channels_with_prior_nondetection": int(len(prior_pairs)),
        "prior_nondetection_gap_days": _min_or_none(pair.get("gap_days") for pair in prior_pairs),
        "prior_nondetection_contrast_mag": _max_or_none(
            pair.get("contrast_mag") for pair in prior_pairs
        ),
        "prior_forced_flux_contrast_significance": _max_or_none(
            pair.get("forced_flux_contrast_significance") for pair in prior_pairs
        ),
        "max_prior_forced_flux_snr": _max_or_none(
            pair.get("prior_forced_flux_snr") for pair in prior_pairs
        ),
        "has_recent_prior_nondetection": any(
            float(pair["gap_days"]) <= cfg.recent_nondetection_days for pair in prior_pairs
        ),
        "prior_nondetection_by_band": prior_pairs,
        "magnitude_error_missing_fraction": (
            float(missing_mag_uncertainty.sum() / raw_with_magnitude.sum())
            if bool(raw_with_magnitude.any())
            else 0.0
        ),
        "flux_error_missing_fraction": (
            float(missing_flux_uncertainty.sum() / raw_with_flux.sum())
            if bool(raw_with_flux.any())
            else 0.0
        ),
        "measurement_error_missing_fraction": (
            float(missing_measurement_uncertainty.sum() / raw_detection_count)
            if raw_detection_count
            else 0.0
        ),
        "band_missing_fraction": float(normalized["_band"].isna().mean()),
        "survey_missing_fraction": (
            float(normalized["_survey"].isna().mean()) if survey_column_present else 0.0
        ),
        "missing_critical_fraction": float((~critical_ok).mean()),
        "quality_rejected_fraction": float((~normalized["_quality_ok"]).mean()),
        "rejected_detection_fraction": (
            float((raw_detection_count - len(detections)) / raw_detection_count)
            if raw_detection_count
            else 0.0
        ),
        "warnings": warnings,
    }
    return result


def flatten_photometry_features(features: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten scalar and per-band features for tabular storage or modeling."""

    flat = {
        key: value
        for key, value in features.items()
        if key not in {"band_features", "prior_nondetection_by_band", "warnings", "bands"}
        and not isinstance(value, (dict, list, tuple, set))
    }
    safe_bands: dict[str, str] = {}
    for band, values in features.get("band_features", {}).items():
        safe_band = re.sub(r"[^a-zA-Z0-9]+", "_", str(band)).strip("_") or "unknown"
        if safe_band in safe_bands and safe_bands[safe_band] != str(band):
            raise ValueError(
                f"Passbands {safe_bands[safe_band]!r} and {str(band)!r} collide when flattened"
            )
        safe_bands[safe_band] = str(band)
        for key, value in values.items():
            flat[f"band_{safe_band}_{key}"] = value
    return flat


def compute_grouped_photometry_features(
    observations: pd.DataFrame | Iterable[Mapping[str, Any]],
    *,
    source_column: str = "source_id",
    column_map: Mapping[str, str] | None = None,
    config: PhotometryFeatureConfig | None = None,
) -> pd.DataFrame:
    """Compute one flattened feature row per source while retaining band detail."""

    frame = _as_frame(observations)
    if source_column not in frame.columns:
        raise ValueError(f"Source column {source_column!r} is absent")
    rows: list[dict[str, Any]] = []
    for source_id, group in frame.groupby(source_column, sort=False, dropna=False):
        features = compute_photometry_features(
            group.drop(columns=[source_column]),
            column_map=column_map,
            config=config,
        )
        row = {source_column: source_id, **flatten_photometry_features(features)}
        row["band_features"] = features["band_features"]
        row["feature_warnings"] = features["warnings"]
        rows.append(row)
    return pd.DataFrame.from_records(rows)
