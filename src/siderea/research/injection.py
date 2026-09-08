"""Deterministic, explicitly simulated light-curve injection/recovery experiments."""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from siderea.provenance import digest_value

INJECTION_RECOVERY_SCHEMA = "siderea.injection_recovery.v1"


def _numeric(frame: pd.DataFrame, column: str, *, positive: bool = False) -> np.ndarray[Any, Any]:
    if column not in frame:
        raise ValueError(f"injection input is missing column {column!r}")
    try:
        values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"injection column {column!r} must be numeric") from exc
    if not np.isfinite(values).all() or (positive and (values <= 0).any()):
        qualifier = "finite and positive" if positive else "finite"
        raise ValueError(f"injection column {column!r} must be {qualifier}")
    return values


def _wilson_interval(successes: int, total: int, confidence: float) -> list[float]:
    if total == 0:
        return [0.0, 0.0]
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    rate = successes / total
    denominator = 1.0 + z * z / total
    center = (rate + z * z / (2.0 * total)) / denominator
    half = z * math.sqrt(rate * (1.0 - rate) / total + z * z / (4.0 * total * total)) / denominator
    return [max(0.0, center - half), min(1.0, center + half)]


def run_injection_recovery(
    frame: pd.DataFrame,
    *,
    source_column: str = "source_id",
    time_column: str = "time",
    flux_column: str = "flux",
    error_column: str = "flux_error",
    amplitudes_sigma: Sequence[float] = (3.0, 5.0, 8.0, 12.0),
    width_days: float = 1.0,
    recovery_threshold_sigma: float = 5.0,
    trials_per_amplitude: int = 200,
    confidence_level: float = 0.95,
    seed: int = 0,
) -> dict[str, Any]:
    """Measure known-location matched-filter recovery on supplied flux curves.

    This is a software/selection-function experiment, not a claim that the
    injected Gaussian pulse is a complete astrophysical population model.
    Existing finite flux is treated as background after subtracting each
    curve's inverse-variance weighted constant baseline.
    """

    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError("injection frame must be a non-empty pandas DataFrame")
    for name, integer_value in (
        ("trials_per_amplitude", trials_per_amplitude),
        ("seed", seed),
    ):
        minimum = 1 if name == "trials_per_amplitude" else 0
        if (
            isinstance(integer_value, bool)
            or not isinstance(integer_value, int)
            or integer_value < minimum
        ):
            raise ValueError(f"{name} must be an integer >= {minimum}")
    for name, numeric_value in (
        ("width_days", width_days),
        ("recovery_threshold_sigma", recovery_threshold_sigma),
    ):
        if isinstance(numeric_value, bool) or not isinstance(numeric_value, (int, float)):
            raise ValueError(f"{name} must be finite and positive")
        if not math.isfinite(float(numeric_value)) or float(numeric_value) <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if isinstance(confidence_level, bool) or not isinstance(confidence_level, (int, float)):
        raise ValueError("confidence_level must be within (0, 1)")
    confidence = float(confidence_level)
    if not math.isfinite(confidence) or not 0.0 < confidence < 1.0:
        raise ValueError("confidence_level must be within (0, 1)")
    if isinstance(amplitudes_sigma, (str, bytes)) or not amplitudes_sigma:
        raise ValueError("amplitudes_sigma must contain at least one value")
    amplitudes: list[float] = []
    for amplitude_value in amplitudes_sigma:
        if isinstance(amplitude_value, bool) or not isinstance(amplitude_value, (int, float)):
            raise ValueError("injection amplitudes must be finite and positive")
        numeric = float(amplitude_value)
        if not math.isfinite(numeric) or numeric <= 0:
            raise ValueError("injection amplitudes must be finite and positive")
        amplitudes.append(numeric)
    if len(set(amplitudes)) != len(amplitudes):
        raise ValueError("injection amplitudes must be unique")

    if source_column not in frame:
        raise ValueError(f"injection input is missing column {source_column!r}")
    if frame[source_column].isna().any():
        raise ValueError("injection source identifiers must not be missing")
    sources = frame[source_column].astype("string").str.strip()
    if sources.eq("").any():
        raise ValueError("injection source identifiers must not be empty")
    for channel in ("survey", "band"):
        if channel in frame and (frame.groupby(sources)[channel].nunique(dropna=False) > 1).any():
            raise ValueError("injection requires one survey/band channel per source")
    times = _numeric(frame, time_column)
    fluxes = _numeric(frame, flux_column)
    errors = _numeric(frame, error_column, positive=True)
    working = pd.DataFrame({"source": sources, "time": times, "flux": fluxes, "error": errors})
    curves: dict[str, tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any]]] = {}
    for source, group in working.groupby("source", sort=True):
        ordered = group.sort_values("time", kind="stable")
        if ordered["time"].nunique() < 3:
            continue
        curve_time = ordered["time"].to_numpy(dtype=float)
        curve_flux = ordered["flux"].to_numpy(dtype=float)
        curve_error = ordered["error"].to_numpy(dtype=float)
        weights = 1.0 / np.square(curve_error)
        baseline = float(np.sum(curve_flux * weights) / np.sum(weights))
        curves[str(source)] = (curve_time, curve_flux - baseline, curve_error)
    if not curves:
        raise ValueError("injection requires at least one source with three distinct epochs")

    rng = np.random.default_rng(seed)
    source_ids = tuple(curves)
    results: list[dict[str, Any]] = []
    for amplitude_sigma in amplitudes:
        recovered = 0
        measured_significances: list[float] = []
        for _ in range(trials_per_amplitude):
            source = source_ids[int(rng.integers(0, len(source_ids)))]
            curve_time, residual_flux, curve_error = curves[source]
            center = float(rng.uniform(float(curve_time.min()), float(curve_time.max())))
            template = np.exp(-0.5 * np.square((curve_time - center) / float(width_days)))
            typical_error = float(np.median(curve_error))
            injected = residual_flux + amplitude_sigma * typical_error * template
            inverse_variance = 1.0 / np.square(curve_error)
            denominator = float(np.sum(np.square(template) * inverse_variance))
            if not math.isfinite(denominator) or denominator <= 0:
                measured_significances.append(0.0)
                continue
            fitted_amplitude = float(np.sum(template * injected * inverse_variance) / denominator)
            significance = fitted_amplitude * math.sqrt(denominator)
            measured_significances.append(significance)
            recovered += int(significance >= float(recovery_threshold_sigma))
        results.append(
            {
                "amplitude_sigma": amplitude_sigma,
                "trials": trials_per_amplitude,
                "recovered": recovered,
                "recovery_fraction": recovered / trials_per_amplitude,
                "confidence_interval": _wilson_interval(
                    recovered, trials_per_amplitude, confidence
                ),
                "median_measured_significance": float(np.median(measured_significances)),
            }
        )

    identity = {
        "schema": INJECTION_RECOVERY_SCHEMA,
        "source_column": source_column,
        "time_column": time_column,
        "flux_column": flux_column,
        "error_column": error_column,
        "amplitudes_sigma": amplitudes,
        "width_days": float(width_days),
        "recovery_threshold_sigma": float(recovery_threshold_sigma),
        "trials_per_amplitude": trials_per_amplitude,
        "confidence_level": confidence,
        "seed": seed,
        "rows": working.to_dict(orient="records"),
    }
    payload = {
        "schema": INJECTION_RECOVERY_SCHEMA,
        "experiment_digest": digest_value(identity),
        "method": "known_location_gaussian_matched_filter_on_constant_baseline_residuals",
        "simulation_scope": (
            "software selection-function diagnostic; not an astrophysical population model"
        ),
        "qualifies_pipeline_completeness": False,
        "source_count": len(curves),
        "row_count": len(working),
        "width_days": float(width_days),
        "recovery_threshold_sigma": float(recovery_threshold_sigma),
        "confidence_level": confidence,
        "seed": seed,
        "results": results,
    }
    payload["result_digest"] = digest_value(payload)
    return payload


__all__ = ["INJECTION_RECOVERY_SCHEMA", "run_injection_recovery"]
