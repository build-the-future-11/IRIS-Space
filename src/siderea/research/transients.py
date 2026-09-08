"""Unknown-location, constant-background-profiled transient search for shadow use.

Templates are phenomenological shapes, not physical-class likelihoods. The null
model assumes independent Gaussian flux errors; real noise requires qualification.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from siderea.provenance import digest_value

FAMILIES = ("gaussian", "exponential", "bazin", "fallback")
Array = NDArray[np.float64]


def _vector(value: Any, name: str) -> Array:
    result = np.asarray(value, dtype=float)
    if result.ndim != 1 or not len(result) or not np.isfinite(result).all():
        raise ValueError(f"{name} must be a nonempty finite one-dimensional array")
    # ``np.asarray(..., dtype=float)`` guarantees float64 at runtime.  Keep that
    # contract explicit for newer NumPy typing, which otherwise leaves ``Any``
    # in the inferred dtype.
    return cast(Array, result)


def transient_template(times: Any, *, center: float, width: float, family: str) -> Array:
    """Return a unit-peak shape with observer-frame center and timescale in days.

    Bazin has fall=width and rise=width/3, shifted to peak at center. Fallback
    has a Gaussian rise and a (1 + phase/width)^(-5/3) tail; this does not imply
    that optical luminosity traces the debris fallback rate.
    """
    t = _vector(times, "times")
    if not np.isfinite(center) or not np.isfinite(width) or width <= 0:
        raise ValueError("template center must be finite and width finite and positive")
    with np.errstate(over="ignore", invalid="ignore"):
        phase = (t - center) / width
    if not np.isfinite(phase).all():
        raise ValueError("template phase exceeds supported numeric range")
    if family == "gaussian":
        return cast(Array, np.exp(-0.5 * np.square(np.clip(phase, -40, 40))))
    if family == "exponential":
        clipped = np.clip(phase, -1e100, 1e100)
        return np.asarray(np.exp(-np.maximum(clipped, 0) + 3 * np.minimum(clipped, 0)), dtype=float)
    if family == "bazin":
        shifted = phase + np.log(2) / 3
        # logaddexp prevents overflow on the early rising branch.
        clipped = np.clip(shifted, -1e100, 1e100)
        log_shape = -clipped - np.logaddexp(0, -3 * clipped)
        log_peak = -np.log(2) / 3 - np.log(1.5)
        return np.asarray(np.exp(np.minimum(log_shape - log_peak, 0)), dtype=float)
    if family == "fallback":
        return np.asarray(
            np.exp(-0.5 * np.square(np.clip(np.minimum(phase, 0), -40, 0)))
            * (1 + np.maximum(phase, 0)) ** (-5 / 3),
            dtype=float,
        )
    raise ValueError(f"unsupported transient family: {family}")


@dataclass(frozen=True)
class TemplateSpec:
    family: str
    center: float
    width: float


class TransientBank:
    """Fixed design for positive-amplitude generalized least-squares searches."""

    def __init__(
        self,
        times: Any,
        errors: Any,
        *,
        centers: Sequence[float],
        widths: Sequence[float],
        families: Sequence[str] = FAMILIES,
        correlation: Any | None = None,
    ) -> None:
        self.times = _vector(times, "times").copy()
        self.errors = _vector(errors, "errors").copy()
        if len(self.times) != len(self.errors) or len(np.unique(self.times)) < 4:
            raise ValueError("search requires equal arrays and at least four distinct epochs")
        if (self.errors <= 0).any():
            raise ValueError("errors must be positive")
        centers_array, widths_array = _vector(centers, "centers"), _vector(widths, "widths")
        if (widths_array <= 0).any() or not families or set(families) - set(FAMILIES):
            raise ValueError("search requires positive widths and supported families")
        count = len(centers_array) * len(widths_array) * len(families)
        if count > 10000 or count * len(self.times) > 10_000_000:
            raise ValueError("template bank exceeds bounded search size")
        self.error_scale = float(self.errors.min())
        inverse_error = self.error_scale / self.errors
        if (inverse_error < 1e-12).any():
            raise ValueError("error dynamic range exceeds supported conditioning")
        self._correlation_factor: Array | None = None
        self._whitener: Array | None = None
        correlation_digest = None
        if correlation is not None:
            matrix = np.asarray(correlation, dtype=float)
            if len(self.times) > 2048:
                raise ValueError("correlated search is limited to 2048 epochs")
            if (
                matrix.shape != (len(self.times), len(self.times))
                or not np.isfinite(matrix).all()
                or not np.allclose(matrix, matrix.T, rtol=0, atol=1e-12)
                or not np.allclose(np.diag(matrix), 1, rtol=0, atol=1e-12)
            ):
                raise ValueError("correlation must be symmetric, finite and have a unit diagonal")
            try:
                self._correlation_factor = np.linalg.cholesky(matrix)
                if np.linalg.cond(matrix) > 1e10:
                    raise ValueError("correlation matrix is too ill-conditioned")
                self._whitener = np.asarray(
                    np.linalg.solve(self._correlation_factor, np.diag(inverse_error)), dtype=float
                )
            except np.linalg.LinAlgError as exc:
                raise ValueError("correlation must be positive definite") from exc
            correlation_digest = digest_value(matrix.tolist())
        white_constant = (
            inverse_error if self._whitener is None else self._whitener @ np.ones(len(self.times))
        )
        self._constant_norm = float(np.linalg.norm(white_constant))
        self._constant = white_constant / self._constant_norm
        templates: list[Array] = []
        specs: list[TemplateSpec] = []
        for family in families:
            for center in centers_array:
                for width in widths_array:
                    specs.append(TemplateSpec(family, float(center), float(width)))
                    templates.append(
                        transient_template(self.times, center=center, width=width, family=family)
                    )
        raw = np.stack(templates)
        whitened = raw * inverse_error if self._whitener is None else raw @ self._whitener.T
        projected = whitened - (whitened @ self._constant)[:, None] * self._constant
        norms = np.linalg.norm(projected, axis=1)
        valid = norms > 1e-10
        if not valid.any():
            raise ValueError("all templates are degenerate with the constant baseline")
        self.specs = tuple(spec for spec, keep in zip(specs, valid, strict=True) if keep)
        self._templates = raw[valid]
        self._norms = norms[valid]
        self._design = projected[valid] / self._norms[:, None]
        self.identity = digest_value(
            {
                "schema": "siderea.transient_bank.v1",
                "times": self.times.tolist(),
                "errors": self.errors.tolist(),
                "specs": [vars(spec) for spec in self.specs],
                "background": "profiled_constant",
                "amplitude": "nonnegative",
                "correlation_digest": correlation_digest,
            }
        )
        for array in (
            self.times,
            self.errors,
            self._constant,
            self._templates,
            self._norms,
            self._design,
        ):
            array.flags.writeable = False

    def statistics(self, flux: Any) -> Array:
        """Maximum local z over the entire bank for each input curve (not global sigma)."""
        values = np.asarray(flux, dtype=float)
        if values.ndim == 1:
            values = values[None, :]
        if values.ndim != 2 or values.shape[1] != len(self.times) or not np.isfinite(values).all():
            raise ValueError("flux must be finite curves matching the bank epochs")
        if values.shape[0] > 100_000:
            raise ValueError("too many curves for one search")
        maxima: list[Array] = []
        for start in range(0, len(values), 128):
            # Subtract a reference before whitening to avoid cancellation for large offsets.
            shifted = values[start : start + 128] - values[start : start + 128, :1]
            with np.errstate(over="ignore", invalid="ignore"):
                white = self._whiten(shifted)
            if not np.isfinite(white).all():
                raise ValueError("flux significance exceeds supported numeric range")
            maxima.append(np.maximum(0, (white @ self._design.T).max(axis=1)))
        return np.concatenate(maxima) if maxima else np.empty(0)

    def fit(self, flux: Any) -> dict[str, Any]:
        values = _vector(flux, "flux")
        self.statistics(values)  # validates numeric range and dimensions
        z = self._design @ self._whiten(values - values[0])
        index = int(np.argmax(z))
        amplitude = max(0.0, float(z[index])) * self.error_scale / self._norms[index]
        residual = values - values[0] - amplitude * self._templates[index]
        baseline = float(
            values[0]
            + self._constant @ self._whiten(residual) * self.error_scale / self._constant_norm
        )
        statistic = max(0.0, float(z[index]))
        return {
            "template": vars(self.specs[index]),
            "amplitude": float(amplitude),
            "baseline": baseline,
            "max_local_z": statistic,
            "delta_chi_square": statistic**2,
            "bank_digest": self.identity,
            "template_count": len(self.specs),
            "influence": self._influence(values, index),
        }

    def _influence(self, values: Array, index: int) -> dict[str, Any]:
        """Delete each observation analytically for the selected fixed template.

        This profiles the background again with the retained covariance marginal,
        not the original conditional precision. It is a diagnostic, not a veto or
        a recalibrated search, and does not rerun template selection after deletion.
        """
        raw = np.stack([np.ones(len(values)), self._templates[index]], axis=1)
        white = self._whiten(raw.T).T * self.error_scale
        target = self._whiten(values - values[0])
        gram, rhs = white.T @ white, white.T @ target
        if self._whitener is None:
            inverse_error = self.error_scale / self.errors
            projected_design = white.T * inverse_error
            projected_target = target * inverse_error
            diagonal = inverse_error**2
        else:
            projected_design = white.T @ self._whitener
            projected_target = self._whitener.T @ target
            diagonal = np.sum(self._whitener**2, axis=0)
        remaining: list[float | None] = []
        for i in range(len(values)):
            column = projected_design[:, i]
            reduced_gram = gram - np.outer(column, column) / diagonal[i]
            reduced_rhs = rhs - column * projected_target[i] / diagonal[i]
            baseline_weight = float(reduced_gram[0, 0])
            if baseline_weight <= 0:
                remaining.append(None)
                continue
            norm = float(reduced_gram[1, 1] - reduced_gram[1, 0] ** 2 / baseline_weight)
            if norm <= 1e-12 * max(1.0, float(gram[1, 1])):
                remaining.append(None)
                continue
            numerator = reduced_rhs[1] - reduced_gram[1, 0] * reduced_rhs[0] / baseline_weight
            remaining.append(max(0.0, float(numerator / np.sqrt(norm))))
        identifiable = [(i, z) for i, z in enumerate(remaining) if z is not None]
        critical = min(identifiable, key=lambda pair: pair[1]) if identifiable else None
        return {
            "scope": "leave_one_observation_out_selected_template_with_refitted_background",
            "changes_detection_rule": False,
            "remaining_local_z": remaining,
            "most_influential_row": None if critical is None else critical[0],
            "most_influential_mjd": None if critical is None else float(self.times[critical[0]]),
            "minimum_remaining_local_z": None if critical is None else critical[1],
            "unidentifiable_deletions": sum(value is None for value in remaining),
        }

    def _whiten(self, values: Array) -> Array:
        if self._whitener is None:
            return np.asarray(values / self.errors, dtype=float)
        return np.asarray(values @ self._whitener.T / self.error_scale, dtype=float)

    def _noise(self, standard: Array) -> Array:
        if self._correlation_factor is not None:
            standard = standard @ self._correlation_factor.T
        return np.asarray(standard * self.errors, dtype=float)

    def simulate_null(self, *, trials: int, seed: int) -> Array:
        if type(trials) is not int or not 99 <= trials <= 100_000:
            raise ValueError("null trials must be an integer in [99, 100000]")
        if type(seed) is not int or seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        rng = np.random.default_rng(seed)
        # Bound memory independently of the number of epochs/trials.
        return np.concatenate(
            [
                self.statistics(
                    self._noise(rng.normal(size=(min(128, trials - start), len(self.times))))
                )
                for start in range(0, trials, 128)
            ]
        )


def empirical_pvalue(statistic: float, null_statistics: Any) -> float:
    null = _vector(null_statistics, "null statistics")
    if not np.isfinite(statistic) or statistic < 0 or (null < 0).any():
        raise ValueError("search statistics must be finite and nonnegative")
    return float((1 + np.count_nonzero(null >= statistic)) / (len(null) + 1))


def search_flux_table(
    frame: Any,
    *,
    widths: Sequence[float] = (1.0, 3.0, 10.0),
    center_count: int = 21,
    null_trials: int = 999,
    seed: int = 0,
    alpha: float = 0.01,
    noise_timescale_days: float | None = None,
) -> dict[str, Any]:
    """Search measured flux channels independently; Bonferroni-correct within object.

    Input must contain measured (including signed difference) flux with known errors.
    Censored limits are rejected rather than treated as Gaussian flux observations.
    No p-value here corrects the number of objects in a survey or repeated monitoring.
    """
    import pandas as pd

    required = {"source_id", "survey", "band", "mjd", "flux", "flux_error"}
    if not isinstance(frame, pd.DataFrame) or frame.empty or not required <= set(frame):
        raise ValueError("search input requires source_id, survey, band, mjd, flux, flux_error")
    if type(center_count) is not int or not 2 <= center_count <= 100:
        raise ValueError("center_count must be an integer in [2, 100]")
    if type(null_trials) is not int or not 99 <= null_trials <= 100_000:
        raise ValueError("null_trials must be an integer in [99, 100000]")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if isinstance(alpha, bool) or not np.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be within (0, 1)")
    if alpha < 1 / (null_trials + 1):
        raise ValueError("too few null trials to resolve the requested alpha")
    if (_vector(widths, "widths") <= 0).any():
        raise ValueError("widths must be positive")
    if noise_timescale_days is not None and (
        isinstance(noise_timescale_days, bool)
        or not np.isfinite(noise_timescale_days)
        or noise_timescale_days <= 0
    ):
        raise ValueError("noise timescale must be finite and positive")
    data = frame.copy()
    for column in ("source_id", "survey", "band"):
        if data[column].isna().any():
            raise ValueError(f"{column} identifiers must be present")
        normalized = [str(value).strip() for value in data[column].tolist()]
        if any(not value for value in normalized):
            raise ValueError(f"{column} identifiers must be present")
        data[column] = normalized
    if "is_detection" in data and not all(
        str(value).lower() == "true" for value in data["is_detection"].tolist()
    ):
        raise ValueError("censored/non-detection rows need measured forced flux, not limits")
    for column in ("mjd", "flux", "flux_error"):
        data[column] = pd.to_numeric(data[column], errors="raise")
        _vector(data[column], column)
    if (data["flux_error"] <= 0).any():
        raise ValueError("flux errors must be positive")
    if data.duplicated(subset=sorted(required)).any():
        raise ValueError("duplicate measurements would count the same evidence more than once")
    groups = list(data.groupby(["source_id", "survey", "band"], sort=True))
    if len(groups) > 100:
        raise ValueError("search supports at most 100 channels per invocation")
    results: list[dict[str, Any]] = []
    for identity, group in groups:
        ordered = group.sort_values("mjd", kind="stable")
        source, survey, band = identity
        result: dict[str, Any] = {
            "source_id": source,
            "survey": survey,
            "band": band,
            "rows": len(group),
        }
        if ordered["mjd"].nunique() < 4:
            result.update(status="insufficient_epochs", search_pvalue=None)
        else:
            correlation = None
            if noise_timescale_days is not None:
                if len(ordered) > 2048:
                    raise ValueError("correlated search is limited to 2048 epochs")
                times = ordered["mjd"].to_numpy(dtype=float)
                # Declared OU-like component plus independent measurement noise.
                correlation = 0.8 * np.exp(-np.abs(times[:, None] - times) / noise_timescale_days)
                correlation += 0.2 * np.eye(len(times))
            bank = TransientBank(
                ordered["mjd"],
                ordered["flux_error"],
                centers=np.linspace(
                    ordered["mjd"].min(), ordered["mjd"].max(), center_count
                ).tolist(),
                widths=widths,
                correlation=correlation,
            )
            fit = bank.fit(ordered["flux"])
            null = bank.simulate_null(trials=null_trials, seed=seed)
            result.update(
                status="evaluated", **fit, search_pvalue=empirical_pvalue(fit["max_local_z"], null)
            )
        results.append(result)
    objects: list[dict[str, Any]] = []
    for source in sorted({str(item["source_id"]) for item in results}):
        channels = [item for item in results if item["source_id"] == source]
        measured = [item["search_pvalue"] for item in channels if item["search_pvalue"] is not None]
        corrected = min(1.0, min(measured) * len(channels)) if measured else None
        minimum_pvalue = min(1.0, len(channels) / (null_trials + 1))
        threshold_resolvable = minimum_pvalue <= alpha
        objects.append(
            {
                "source_id": source,
                "channel_count": len(channels),
                "evaluated_channels": len(measured),
                "status": (
                    "insufficient_epochs"
                    if not measured
                    else "insufficient_null_resolution"
                    if not threshold_resolvable
                    else "partially_evaluated"
                    if len(measured) < len(channels)
                    else "evaluated"
                ),
                "minimum_resolvable_object_pvalue": minimum_pvalue,
                "threshold_resolvable": threshold_resolvable,
                "object_pvalue": corrected,
                "shadow_excess": corrected is not None and corrected <= alpha,
            }
        )
    output = {
        "schema": "siderea.transient_search.v1",
        "mode": "shadow_only",
        "assumptions": (
            "Gaussian measured flux errors with declared correlation "
            "and constant channel background"
        ),
        "noise_timescale_days": noise_timescale_days,
        "correlated_variance_fraction": 0.0 if noise_timescale_days is None else 0.8,
        "scope": (
            "template-search and within-object channel correction; "
            "no survey-wide or repeated-look correction"
        ),
        "physical_classification": False,
        "qualifies_reportability": False,
        "seed": seed,
        "null_trials": null_trials,
        "alpha": alpha,
        "widths_days": list(widths),
        "center_count": center_count,
        "channels": results,
        "objects": objects,
    }
    output["result_digest"] = digest_value(output)
    return output
