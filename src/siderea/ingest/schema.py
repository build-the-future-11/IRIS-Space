"""Strict schema resolution and canonicalization for photometry tables."""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from .base import CANONICAL_COLUMNS, IngestionError

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "source_id": ("source_id", "candidate_id", "object_id", "objectid", "oid", "name"),
    "ra_deg": ("ra_deg", "ra", "meanra", "ramean", "candidate_ra"),
    "dec_deg": ("dec_deg", "dec", "declination", "meandec", "decmean", "candidate_dec"),
    "mjd": ("mjd", "jd", "time", "observation_time"),
    "band": ("band", "filter", "fid", "filtercode", "bandname", "band_name"),
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
    "flux": ("flux", "difference_flux", "forcediffimflux", "fluxpsf", "psfflux"),
    "flux_error": (
        "flux_error",
        "fluxerr",
        "sigma_flux",
        "forcediffimfluxunc",
        "psffluxerr",
    ),
    "survey": ("survey", "instrument", "facility", "telescope"),
    "observation_id": ("observation_id", "alert_id", "candid", "measurement_id"),
    "quality": ("quality", "quality_ok", "is_good", "good_quality", "catflags", "flags"),
}

_LOGICAL_ALIASES = {
    "ra": "ra_deg",
    "dec": "dec_deg",
    "time": "mjd",
    "filter": "band",
    "detected": "is_detection",
}

_REQUIRED = ("source_id", "ra_deg", "dec_deg", "mjd", "band")
_NUMERIC = (
    "ra_deg",
    "dec_deg",
    "mjd",
    "magnitude",
    "magnitude_error",
    "limiting_magnitude",
    "flux",
    "flux_error",
)


def _canonical_map(column_map: Mapping[str, str] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for logical, physical in dict(column_map or {}).items():
        canonical = _LOGICAL_ALIASES.get(str(logical), str(logical))
        if canonical not in COLUMN_ALIASES:
            raise IngestionError(f"unknown logical column {logical!r}")
        if canonical in normalized:
            raise IngestionError(f"logical column {canonical!r} was mapped more than once")
        normalized[canonical] = str(physical)
    return normalized


def resolve_columns(
    columns: list[str] | tuple[str, ...] | pd.Index,
    *,
    column_map: Mapping[str, str] | None = None,
) -> dict[str, str | None]:
    """Resolve aliases, rejecting ambiguous non-canonical matches."""

    names = [str(item) for item in columns]
    by_folded: dict[str, list[str]] = {}
    for name in names:
        by_folded.setdefault(name.casefold(), []).append(name)
    duplicate_case = [items for items in by_folded.values() if len(items) > 1]
    if duplicate_case:
        raise IngestionError(f"columns differ only by case: {duplicate_case}")

    explicit = _canonical_map(column_map)
    resolved: dict[str, str | None] = {}
    for logical, aliases in COLUMN_ALIASES.items():
        requested = explicit.get(logical)
        if requested is not None:
            actual = by_folded.get(requested.casefold(), [])
            if len(actual) != 1:
                raise IngestionError(
                    f"mapped column {requested!r} for {logical!r} is not uniquely present"
                )
            resolved[logical] = actual[0]
            continue

        canonical = by_folded.get(logical.casefold(), [])
        if canonical:
            resolved[logical] = canonical[0]
            continue
        matches = [
            by_folded[alias.casefold()][0] for alias in aliases if alias.casefold() in by_folded
        ]
        matches = list(dict.fromkeys(matches))
        if len(matches) > 1:
            raise IngestionError(f"ambiguous columns for {logical!r}: {matches}; supply column_map")
        resolved[logical] = matches[0] if matches else None

    physical_uses: dict[str, str] = {}
    for logical, physical in resolved.items():
        if physical is None:
            continue
        folded = physical.casefold()
        previous = physical_uses.get(folded)
        if previous is not None:
            raise IngestionError(
                f"physical column {physical!r} is mapped to both {previous!r} and {logical!r}"
            )
        physical_uses[folded] = logical

    missing = [name for name in _REQUIRED if resolved[name] is None]
    if missing:
        raise IngestionError(
            f"missing required logical columns {missing}; available columns are {names}"
        )
    if all(resolved[name] is None for name in ("magnitude", "limiting_magnitude", "flux")):
        raise IngestionError(
            "photometry requires magnitude, flux, or limiting-magnitude measurements"
        )
    if resolved["is_detection"] is None and resolved["magnitude"] is None:
        raise IngestionError("flux-only photometry requires an explicit is_detection column")
    return resolved


def _detection_values(series: pd.Series | None, magnitude: pd.Series) -> pd.Series:
    if series is None:
        return magnitude.notna()
    missing = series.isna() | series.astype("string").str.strip().eq("")
    if missing.any():
        rows = series.index[missing].tolist()[:10]
        raise IngestionError(f"explicit is_detection column has missing values at row(s) {rows}")
    if pd.api.types.is_bool_dtype(series.dtype):
        return series.astype(bool)
    numeric = pd.to_numeric(series, errors="coerce")
    numeric_rows = numeric.notna()
    invalid_numeric = numeric_rows & ~numeric.isin([0, 1])
    if invalid_numeric.any():
        values = sorted(set(numeric.loc[invalid_numeric].tolist()))
        raise IngestionError(f"detection values must be boolean or 0/1, got {values}")
    result = numeric.eq(1) & numeric_rows
    unresolved = numeric.isna() & series.notna()
    if unresolved.any():
        words = series.astype("string").str.strip().str.casefold()
        truthy = {"true", "t", "yes", "y", "detected", "detection", "1"}
        falsey = {"false", "f", "no", "n", "nondetection", "non-detection", "0"}
        unknown = unresolved & ~words.isin(truthy | falsey)
        if unknown.any():
            values = sorted(set(words.loc[unknown].tolist()))
            raise IngestionError(f"unrecognized detection values: {values}")
        result.loc[unresolved] = words.loc[unresolved].isin(truthy)
    return result.astype(bool)


def _quality_values(series: pd.Series, source_name: str) -> pd.Series:
    """Normalize heterogeneous quality/flag columns to True means usable."""

    name = source_name.casefold()
    # Canonical ``quality`` has positive semantics across every dtype:
    # true/non-zero means usable. Survey flag aliases use the inverse rule.
    positive_semantics = name in {"quality", "quality_ok", "is_good", "good_quality"}
    nonmissing = series.dropna()
    boolean_values = bool(len(nonmissing)) and bool(
        nonmissing.map(lambda value: isinstance(value, (bool, np.bool_))).all()
    )
    if pd.api.types.is_bool_dtype(series.dtype) or boolean_values:
        values = series.astype("boolean")
        return values if positive_semantics else ~values

    result = pd.Series(pd.NA, index=series.index, dtype="boolean")
    numeric = pd.to_numeric(series, errors="coerce")
    numeric_rows = numeric.notna()
    if positive_semantics:
        result.loc[numeric_rows] = numeric.loc[numeric_rows].gt(0)
    else:
        nonnegative = numeric_rows & numeric.ge(0)
        result.loc[nonnegative] = numeric.loc[nonnegative].eq(0)

    unresolved = series.notna() & ~numeric_rows
    if unresolved.any():
        words = series.astype("string").str.strip().str.casefold()
        good = {"good", "clean", "ok", "pass", "passed"}
        if positive_semantics:
            good |= {"true", "t", "yes", "y"}
            bad = {"bad", "reject", "rejected", "fail", "failed", "false", "f", "no", "n"}
        else:
            good |= {"false", "f", "no", "n", "clear"}
            bad = {"bad", "reject", "rejected", "fail", "failed", "true", "t", "yes", "y"}
        result.loc[unresolved & words.isin(good)] = True
        result.loc[unresolved & words.isin(bad)] = False
    return result


def _numeric_values(series: pd.Series, logical_name: str) -> pd.Series:
    """Coerce numeric input without turning malformed measurements into missing data."""

    converted = pd.to_numeric(series, errors="coerce")
    blank_text = series.astype("string").str.strip().eq("").fillna(False)
    supplied = series.notna() & ~blank_text
    invalid = supplied & ~np.isfinite(converted)
    if invalid.any():
        rows = series.index[invalid].tolist()[:10]
        raise IngestionError(f"invalid numeric values for {logical_name!r} at row(s) {rows}")
    return converted


def _angular_separation_deg(
    ra: NDArray[np.float64],
    dec: NDArray[np.float64],
    ra0: float,
    dec0: float,
) -> NDArray[np.float64]:
    ra_rad = np.deg2rad(ra)
    dec_rad = np.deg2rad(dec)
    ra0_rad = math.radians(ra0)
    dec0_rad = math.radians(dec0)
    delta_ra = (ra_rad - ra0_rad + math.pi) % (2.0 * math.pi) - math.pi
    delta_dec = dec_rad - dec0_rad
    haversine = np.sin(delta_dec / 2.0) ** 2 + (
        np.cos(dec_rad) * math.cos(dec0_rad) * np.sin(delta_ra / 2.0) ** 2
    )
    return np.asarray(
        np.rad2deg(2.0 * np.arcsin(np.sqrt(np.clip(haversine, 0.0, 1.0)))),
        dtype=np.float64,
    )


def _validate_coordinates(frame: pd.DataFrame, tolerance_arcsec: float) -> None:
    invalid_ra = ~np.isfinite(frame["ra_deg"]) | ~frame["ra_deg"].between(
        0.0, 360.0, inclusive="left"
    )
    invalid_dec = ~np.isfinite(frame["dec_deg"]) | ~frame["dec_deg"].between(-90.0, 90.0)
    if invalid_ra.any() or invalid_dec.any():
        rows = sorted(set(frame.index[invalid_ra | invalid_dec].tolist()))[:10]
        raise IngestionError(f"invalid sky coordinates at row(s) {rows}")

    limit_deg = tolerance_arcsec / 3600.0
    for source_id, group in frame.groupby("source_id", sort=False):
        ra = group["ra_deg"].to_numpy(dtype=np.float64)
        dec = group["dec_deg"].to_numpy(dtype=np.float64)
        # Checking only against the first row lets two observations on opposite
        # sides of that anchor be almost twice the configured distance apart.
        # Compare every pair, returning early on the first policy violation.
        for index in range(len(group) - 1):
            separations = _angular_separation_deg(
                ra[index + 1 :],
                dec[index + 1 :],
                float(ra[index]),
                float(dec[index]),
            )
            if bool(np.any(separations > limit_deg)):
                maximum = float(np.max(separations) * 3600.0)
                raise IngestionError(
                    f"source {source_id!r} has positions separated by {maximum:.3f} arcsec "
                    f"(limit {tolerance_arcsec:.3f})"
                )


def normalize_photometry_frame(
    frame: pd.DataFrame,
    *,
    column_map: Mapping[str, str] | None = None,
    coordinate_tolerance_arcsec: float = 2.0,
    default_survey: str = "unknown",
) -> tuple[pd.DataFrame, dict[str, str | None], tuple[str, ...]]:
    """Return a validated, canonical, deterministically ordered table."""

    if not math.isfinite(coordinate_tolerance_arcsec) or coordinate_tolerance_arcsec <= 0:
        raise ValueError("coordinate_tolerance_arcsec must be finite and positive")
    if not isinstance(default_survey, str):
        raise TypeError("default_survey must be a string")
    canonical_default_survey = " ".join(default_survey.strip().casefold().split())
    if not canonical_default_survey:
        raise ValueError("default_survey must not be empty")
    if frame.empty:
        raise IngestionError("photometry input is empty")
    resolved = resolve_columns(frame.columns, column_map=column_map)
    canonical = pd.DataFrame(index=frame.index)
    for logical in CANONICAL_COLUMNS:
        source = resolved[logical]
        canonical[logical] = frame[source] if source is not None else None

    source_ids = canonical["source_id"].astype("string").str.strip()
    invalid_source = (
        source_ids.isna()
        | source_ids.eq("")
        | source_ids.str.casefold().isin({"nan", "none", "null"})
    )
    if invalid_source.any():
        rows = canonical.index[invalid_source].tolist()[:10]
        raise IngestionError(f"missing source identifiers at row(s) {rows}")
    canonical["source_id"] = source_ids.astype(str)

    for name in _NUMERIC:
        canonical[name] = _numeric_values(canonical[name], name)

    if (
        resolved["is_detection"] is None
        and not np.isfinite(canonical["magnitude"]).any()
        and np.isfinite(canonical["flux"]).any()
    ):
        raise IngestionError("flux-only photometry requires an explicit is_detection column")

    warnings: list[str] = []
    time_source = resolved["mjd"] or ""
    finite_times = canonical["mjd"][np.isfinite(canonical["mjd"])]
    explicit_jd = time_source.casefold() == "jd"
    looks_like_jd = not finite_times.empty and bool(
        finite_times.between(2_000_000.0, 3_000_000.0, inclusive="both").all()
    )
    mixed_scale = not finite_times.empty and bool(
        (finite_times > 2_000_000.0).any() and (finite_times <= 2_000_000.0).any()
    )
    if mixed_scale:
        raise IngestionError("time column mixes JD and MJD-like values")
    if explicit_jd and not looks_like_jd:
        raise IngestionError("JD column contains values outside the supported JD range")
    if not finite_times.empty and bool((finite_times > 3_000_000.0).any()):
        raise IngestionError(
            "time values are not plausible MJD/JD days; convert Unix timestamps explicitly"
        )
    if explicit_jd or looks_like_jd:
        canonical["mjd"] = canonical["mjd"] - 2_400_000.5
        warnings.append("converted_jd_to_mjd")
    invalid_time = (
        ~np.isfinite(canonical["mjd"]) | canonical["mjd"].lt(0) | canonical["mjd"].gt(1_000_000.0)
    )
    if invalid_time.any():
        rows = canonical.index[invalid_time].tolist()[:10]
        raise IngestionError(f"invalid observation times at row(s) {rows}")

    bands = canonical["band"].astype("string").str.strip()
    invalid_band = bands.isna() | bands.eq("") | bands.str.casefold().isin({"nan", "none", "null"})
    if invalid_band.any():
        rows = canonical.index[invalid_band].tolist()[:10]
        raise IngestionError(f"missing passbands at row(s) {rows}")
    canonical["band"] = bands.astype(str)
    canonical["is_detection"] = _detection_values(
        canonical["is_detection"] if resolved["is_detection"] is not None else None,
        canonical["magnitude"],
    )
    canonical["survey"] = (
        canonical["survey"]
        .fillna(canonical_default_survey)
        .astype(str)
        .map(lambda value: " ".join(value.strip().casefold().split()))
    )
    canonical.loc[canonical["survey"].eq(""), "survey"] = canonical_default_survey
    quality_source = resolved["quality"]
    if quality_source is not None:
        canonical["quality"] = _quality_values(canonical["quality"], quality_source)
    else:
        # The canonical field records the current policy decision (usable when
        # no source flag exists), while provenance/warnings retain the crucial
        # distinction from a supplied but unreadable quality column.
        canonical["quality"] = True
        warnings.append("quality_column_not_supplied")

    _validate_coordinates(canonical, coordinate_tolerance_arcsec)

    missing_detection_measurement = canonical["is_detection"] & ~(
        np.isfinite(canonical["magnitude"]) | np.isfinite(canonical["flux"])
    )
    missing_nondetection_measurement = ~canonical["is_detection"] & ~(
        np.isfinite(canonical["limiting_magnitude"]) | np.isfinite(canonical["flux"])
    )
    if missing_detection_measurement.any():
        warnings.append("detections_with_missing_measurement")
    if missing_nondetection_measurement.any():
        warnings.append("nondetections_with_missing_limit_or_flux")
    if quality_source is not None and canonical["quality"].isna().any():
        warnings.append("missing_or_unrecognized_quality_values")

    duplicate_subset = [
        "source_id",
        "mjd",
        "band",
        "is_detection",
        "magnitude",
        "magnitude_error",
        "flux",
        "flux_error",
        "limiting_magnitude",
        "survey",
        "observation_id",
        "quality",
    ]
    duplicated = canonical.duplicated(subset=duplicate_subset, keep=False)
    if duplicated.any():
        rows = canonical.index[duplicated].tolist()[:10]
        raise IngestionError(
            f"duplicate observations would inflate candidate evidence at row(s) {rows}"
        )

    observation_ids = canonical["observation_id"].astype("string").str.strip()
    identified = observation_ids.notna() & ~observation_ids.fillna("").eq("")
    identified &= ~observation_ids.fillna("").str.casefold().isin({"nan", "none", "null"})
    repeated_ids = (
        canonical.loc[identified]
        .assign(observation_id=observation_ids.loc[identified])
        .duplicated(subset=["source_id", "survey", "observation_id"], keep=False)
    )
    if repeated_ids.any():
        rows = canonical.loc[identified].index[repeated_ids].tolist()[:10]
        raise IngestionError(
            f"conflicting rows reuse the same non-empty observation_id at row(s) {rows}"
        )
    canonical["observation_id"] = observation_ids.mask(~identified, pd.NA)

    canonical["_input_order"] = np.arange(len(canonical), dtype=int)
    canonical = canonical.sort_values(
        ["source_id", "mjd", "band", "_input_order"], kind="stable"
    ).drop(columns=["_input_order"])
    canonical = canonical.reset_index(drop=True)
    return canonical.loc[:, list(CANONICAL_COLUMNS)], resolved, tuple(sorted(set(warnings)))


def representative_coordinates(group: pd.DataFrame) -> tuple[float, float]:
    """Compute a wrap-safe spherical centroid for one already validated source."""

    ra = np.deg2rad(group["ra_deg"].to_numpy(dtype=float))
    dec = np.deg2rad(group["dec_deg"].to_numpy(dtype=float))
    x = np.mean(np.cos(dec) * np.cos(ra))
    y = np.mean(np.cos(dec) * np.sin(ra))
    z = np.mean(np.sin(dec))
    norm = math.sqrt(float(x * x + y * y + z * z))
    if norm <= 0:
        raise IngestionError("cannot determine a representative sky position")
    x, y, z = x / norm, y / norm, z / norm
    return math.degrees(math.atan2(y, x)) % 360.0, math.degrees(math.asin(z))
