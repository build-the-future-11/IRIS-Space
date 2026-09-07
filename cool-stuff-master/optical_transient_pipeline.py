#!/usr/bin/env python3
"""
End-to-end optical transient pipeline.

What this script does:
1. Fetches ZTF light-curve points from IRSA (or reads a local CSV).
2. Standardizes columns and cleans photometry.
3. Scores each source for transient-like behavior.
4. Crossmatches candidates against known transients (Open Astronomy Catalog API).
5. Crossmatches candidates against moving Solar System objects (SkyBoT).
6. Writes ranked outputs plus light-curve plots.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import requests
from astropy.coordinates import SkyCoord
from astropy.stats import sigma_clipped_stats
from astropy.time import Time
from astropy.timeseries import LombScargle
import astropy.units as u

try:
    from astroquery.imcce import Skybot
except Exception:  # pragma: no cover - optional at runtime
    Skybot = None

ZTF_LIGHTCURVE_URL = "https://irsa.ipac.caltech.edu/cgi-bin/ZTF/nph_light_curves"
OAC_SNE_URL = "https://api.astrocats.space/catalog/sne"


@dataclass
class Thresholds:
    min_points: int
    min_amp_mag: float
    min_peak_snr: float
    min_significant_points: int
    sigma_threshold: float
    periodic_fap: float
    min_period_days: float
    max_period_days: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find optical-transient candidates from ZTF photometric data."
    )
    parser.add_argument("--input-csv", type=Path, help="Use local CSV instead of fetching ZTF.")
    parser.add_argument("--ra", type=float, help="RA (deg) for ZTF cone search.")
    parser.add_argument("--dec", type=float, help="Dec (deg) for ZTF cone search.")
    parser.add_argument(
        "--radius-deg",
        type=float,
        default=0.02,
        help="Cone-search radius in degrees for ZTF query (default: 0.02).",
    )
    parser.add_argument(
        "--bands",
        type=str,
        default="g,r,i",
        help="Comma-separated filters for ZTF query (default: g,r,i).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("astronomy/outputs"),
        help="Directory for result files.",
    )
    parser.add_argument("--timeout-sec", type=float, default=45.0, help="HTTP timeout.")
    parser.add_argument("--min-points", type=int, default=8)
    parser.add_argument("--min-amp-mag", type=float, default=0.7)
    parser.add_argument("--min-peak-snr", type=float, default=5.0)
    parser.add_argument("--min-significant-points", type=int, default=3)
    parser.add_argument("--sigma-threshold", type=float, default=3.0)
    parser.add_argument("--periodic-fap", type=float, default=1e-3)
    parser.add_argument("--min-period-days", type=float, default=0.1)
    parser.add_argument("--max-period-days", type=float, default=200.0)
    parser.add_argument("--max-mag-err", type=float, default=1.0)
    parser.add_argument("--max-catflags", type=int, default=0)
    parser.add_argument("--disable-oac", action="store_true", help="Skip OAC known-SN crossmatch.")
    parser.add_argument("--disable-skybot", action="store_true", help="Skip SkyBoT moving-object crossmatch.")
    parser.add_argument("--oac-radius-arcsec", type=float, default=3.0)
    parser.add_argument("--skybot-radius-arcsec", type=float, default=10.0)
    parser.add_argument("--max-crossmatch", type=int, default=200)
    parser.add_argument("--max-plots", type=int, default=30)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="[%(levelname)s] %(message)s",
    )


def normalize_band_list(text: str) -> List[str]:
    bands = [b.strip().lower() for b in text.split(",") if b.strip()]
    valid = {"g", "r", "i"}
    result = [b for b in bands if b in valid]
    return result or ["g", "r", "i"]


def fetch_ztf_lightcurves(
    ra: float,
    dec: float,
    radius_deg: float,
    bands: Sequence[str],
    timeout_sec: float,
) -> pd.DataFrame:
    params: List[Tuple[str, str]] = [
        ("POS", f"CIRCLE {ra:.8f} {dec:.8f} {radius_deg:.8f}"),
        ("FORMAT", "csv"),
    ]
    for band in bands:
        params.append(("BANDNAME", band))

    logging.info("Requesting ZTF light curves from IRSA.")
    errors: List[str] = []
    try:
        resp = requests.get(ZTF_LIGHTCURVE_URL, params=params, timeout=timeout_sec)
        resp.raise_for_status()
        df = parse_csv_payload(resp.text)
        if not df.empty:
            return df
    except requests.RequestException as exc:
        errors.append(str(exc))

    # Fallback pattern for servers that expect comma-delimited BANDNAME values.
    fallback_params = {
        "POS": f"CIRCLE {ra:.8f} {dec:.8f} {radius_deg:.8f}",
        "FORMAT": "csv",
        "BANDNAME": ",".join(bands),
    }
    try:
        resp2 = requests.get(ZTF_LIGHTCURVE_URL, params=fallback_params, timeout=timeout_sec)
        resp2.raise_for_status()
        return parse_csv_payload(resp2.text)
    except requests.RequestException as exc:
        errors.append(str(exc))
        raise RuntimeError(
            "ZTF request failed. Check network access to irsa.ipac.caltech.edu, "
            "or run with --input-csv using local light-curve data. "
            f"Request errors: {errors}"
        ) from exc


def parse_csv_payload(payload: str) -> pd.DataFrame:
    text = payload.strip()
    if not text:
        return pd.DataFrame()
    lowered = text.lower()
    if "no records found" in lowered or "no matching rows" in lowered:
        return pd.DataFrame()

    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        if "," in clean:
            header_idx = i
            break

    if header_idx is None:
        return pd.DataFrame()

    csv_text = "\n".join(lines[header_idx:])
    df = pd.read_csv(io.StringIO(csv_text))
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]
    return df


def find_column(df: pd.DataFrame, aliases: Iterable[str]) -> Optional[str]:
    by_lower = {c.lower(): c for c in df.columns}
    for alias in aliases:
        if alias.lower() in by_lower:
            return by_lower[alias.lower()]
    return None


def standardize_ztf_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=["source_id", "ra", "dec", "mjd", "mag", "mag_err", "filter", "catflags"]
        )

    col_source = find_column(df, ["source_id", "oid", "objectid", "objid", "id"])
    col_ra = find_column(df, ["ra", "objra", "meanra", "ra_deg"])
    col_dec = find_column(df, ["dec", "objdec", "meandec", "dec_deg"])
    col_mjd = find_column(df, ["mjd", "hmjd", "obsmjd", "jd", "hjd", "obsjd"])
    col_mag = find_column(df, ["mag", "magpsf", "psfmag", "magnitude"])
    col_magerr = find_column(df, ["magerr", "sigmapsf", "magpsferr", "e_mag", "e_magnitude"])
    col_filter = find_column(df, ["filter", "filtercode", "fid", "band", "bandname"])
    col_catflags = find_column(df, ["catflags", "cat_flag", "flags", "flag"])

    required = {"ra": col_ra, "dec": col_dec, "mjd_or_jd": col_mjd, "mag": col_mag, "mag_err": col_magerr}
    missing = [name for name, col in required.items() if col is None]
    if missing:
        raise ValueError(
            "Cannot standardize input columns. Missing: "
            + ", ".join(missing)
            + f". Available columns: {list(df.columns)}"
        )

    out = pd.DataFrame()
    out["source_id"] = (
        df[col_source].astype(str)
        if col_source is not None
        else (
            df[col_ra].astype(float).round(5).astype(str)
            + "_"
            + df[col_dec].astype(float).round(5).astype(str)
        )
    )
    out["ra"] = pd.to_numeric(df[col_ra], errors="coerce")
    out["dec"] = pd.to_numeric(df[col_dec], errors="coerce")
    out["mjd"] = pd.to_numeric(df[col_mjd], errors="coerce")
    out["mag"] = pd.to_numeric(df[col_mag], errors="coerce")
    out["mag_err"] = pd.to_numeric(df[col_magerr], errors="coerce")

    if out["mjd"].median(skipna=True) > 2400000:
        out["mjd"] = out["mjd"] - 2400000.5

    if col_filter is None:
        out["filter"] = "unknown"
    else:
        out["filter"] = normalize_filter_series(df[col_filter])

    if col_catflags is None:
        out["catflags"] = np.nan
    else:
        out["catflags"] = pd.to_numeric(df[col_catflags], errors="coerce")

    out = out.dropna(subset=["source_id", "ra", "dec", "mjd", "mag", "mag_err"])
    out = out.sort_values(["source_id", "mjd"]).reset_index(drop=True)
    return out


def normalize_filter_series(series: pd.Series) -> pd.Series:
    out = series.astype(str).str.strip().str.lower()
    numeric_mask = out.str.fullmatch(r"\d+")
    if numeric_mask.any():
        num_map = {"1": "g", "2": "r", "3": "i"}
        out.loc[numeric_mask] = out.loc[numeric_mask].map(num_map).fillna(out.loc[numeric_mask])
    out = out.str.replace("ztf", "", regex=False)
    out = out.str.replace("_", "", regex=False)
    out = out.replace({"zg": "g", "zr": "r", "zi": "i"})
    return out


def clean_photometry(df: pd.DataFrame, max_mag_err: float, max_catflags: int) -> pd.DataFrame:
    clean = df.copy()
    clean = clean[np.isfinite(clean["mag"]) & np.isfinite(clean["mag_err"]) & np.isfinite(clean["mjd"])]
    clean = clean[(clean["mag_err"] > 0) & (clean["mag_err"] <= max_mag_err)]
    if clean["catflags"].notna().any():
        clean = clean[(clean["catflags"].isna()) | (clean["catflags"] <= max_catflags)]
    clean = clean.sort_values(["source_id", "mjd"]).reset_index(drop=True)
    return clean


def detect_periodicity(
    times: np.ndarray,
    mags: np.ndarray,
    mag_errs: np.ndarray,
    thresholds: Thresholds,
) -> Tuple[bool, float, float]:
    if len(times) < 10 or (times.max() - times.min()) < 2.0:
        return False, np.nan, np.nan
    try:
        ls = LombScargle(times, mags, mag_errs)
        freq, power = ls.autopower(
            minimum_frequency=1.0 / thresholds.max_period_days,
            maximum_frequency=1.0 / thresholds.min_period_days,
            samples_per_peak=5,
        )
        if len(freq) == 0:
            return False, np.nan, np.nan
        i_best = int(np.nanargmax(power))
        best_freq = float(freq[i_best])
        best_period = 1.0 / best_freq if best_freq > 0 else np.nan
        fap = float(ls.false_alarm_probability(float(power[i_best])))
        periodic = bool(np.isfinite(fap) and fap < thresholds.periodic_fap)
        return periodic, best_period, fap
    except Exception:
        return False, np.nan, np.nan


def source_features(group: pd.DataFrame, thresholds: Thresholds) -> pd.Series:
    mags = group["mag"].to_numpy(dtype=float)
    mag_errs = group["mag_err"].to_numpy(dtype=float)
    times = group["mjd"].to_numpy(dtype=float)
    n_points = len(group)
    ra = float(group["ra"].median())
    dec = float(group["dec"].median())

    if n_points < thresholds.min_points:
        return pd.Series(
            {
                "ra": ra,
                "dec": dec,
                "n_points": n_points,
                "is_candidate": False,
                "rejection_reason": "too_few_points",
            }
        )

    _, baseline_med, baseline_std = sigma_clipped_stats(mags, sigma=3.0, maxiters=5)
    if not np.isfinite(baseline_std) or baseline_std <= 1e-4:
        baseline_std = float(np.nanstd(mags))
    if not np.isfinite(baseline_std) or baseline_std <= 1e-6:
        return pd.Series(
            {
                "ra": ra,
                "dec": dec,
                "n_points": n_points,
                "is_candidate": False,
                "rejection_reason": "insufficient_variability",
            }
        )

    idx_peak = int(np.nanargmin(mags))
    peak_mag = float(mags[idx_peak])
    peak_mag_err = float(mag_errs[idx_peak])
    peak_mjd = float(times[idx_peak])
    amp_mag = float(baseline_med - peak_mag)
    peak_snr = float(amp_mag / np.sqrt((baseline_std**2) + (peak_mag_err**2)))
    n_sig = int(np.sum(mags <= (baseline_med - thresholds.sigma_threshold * baseline_std)))

    periodic, best_period, fap = detect_periodicity(times, mags, mag_errs, thresholds)

    is_candidate = bool(
        (amp_mag >= thresholds.min_amp_mag)
        and (peak_snr >= thresholds.min_peak_snr)
        and (n_sig >= thresholds.min_significant_points)
        and (not periodic)
    )

    rejection_reason = ""
    if not is_candidate:
        if periodic:
            rejection_reason = "periodic_variable"
        elif amp_mag < thresholds.min_amp_mag:
            rejection_reason = "low_amplitude"
        elif peak_snr < thresholds.min_peak_snr:
            rejection_reason = "low_peak_snr"
        elif n_sig < thresholds.min_significant_points:
            rejection_reason = "too_few_significant_points"
        else:
            rejection_reason = "failed_thresholds"

    transient_score = (
        min(1.0, amp_mag / max(thresholds.min_amp_mag, 1e-6)) * 0.45
        + min(1.0, peak_snr / max(thresholds.min_peak_snr, 1e-6)) * 0.35
        + min(1.0, n_sig / max(thresholds.min_significant_points, 1)) * 0.20
    )

    return pd.Series(
        {
            "ra": ra,
            "dec": dec,
            "n_points": n_points,
            "baseline_med_mag": float(baseline_med),
            "baseline_std_mag": float(baseline_std),
            "peak_mag": peak_mag,
            "peak_mag_err": peak_mag_err,
            "peak_mjd": peak_mjd,
            "amp_mag": amp_mag,
            "peak_snr": peak_snr,
            "n_significant_points": n_sig,
            "periodic": periodic,
            "best_period_days": best_period,
            "period_fap": fap,
            "transient_score": transient_score,
            "is_candidate": is_candidate,
            "rejection_reason": rejection_reason,
        }
    )


def classify_candidate(row: pd.Series) -> str:
    if bool(row.get("moving_object_match", False)):
        return "moving_solar_system_body"
    if bool(row.get("known_transient_match", False)):
        return "known_transient"
    if bool(row.get("is_candidate", False)):
        return "new_transient_candidate"
    return "not_transient"


def crossmatch_oac(
    candidates: pd.DataFrame,
    radius_arcsec: float,
    timeout_sec: float,
    max_crossmatch: int,
) -> pd.DataFrame:
    if candidates.empty:
        candidates["known_transient_match"] = []
        return candidates

    out = candidates.copy()
    out["known_transient_match"] = False
    out["known_transient_names"] = ""
    out["known_transient_count"] = 0

    cache: Dict[Tuple[float, float], Tuple[bool, str, int]] = {}
    n = min(len(out), max_crossmatch)
    logging.info("Crossmatching %d candidates with Open Astronomy Catalog.", n)

    for idx in out.index[:n]:
        ra = float(out.at[idx, "ra"])
        dec = float(out.at[idx, "dec"])
        key = (round(ra, 5), round(dec, 5))
        if key in cache:
            matched, names, count = cache[key]
        else:
            matched, names, count = query_oac_cone(ra, dec, radius_arcsec, timeout_sec)
            cache[key] = (matched, names, count)
        out.at[idx, "known_transient_match"] = matched
        out.at[idx, "known_transient_names"] = names
        out.at[idx, "known_transient_count"] = count

    return out


def query_oac_cone(ra: float, dec: float, radius_arcsec: float, timeout_sec: float) -> Tuple[bool, str, int]:
    params = {"ra": ra, "dec": dec, "radius": radius_arcsec}
    try:
        resp = requests.get(OAC_SNE_URL, params=params, timeout=timeout_sec)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return False, "", 0

    names: List[str] = []
    if isinstance(payload, dict):
        for key in payload.keys():
            lower = str(key).lower()
            if lower in {"catalog", "response", "status", "message"}:
                continue
            if not str(key).startswith("_"):
                names.append(str(key))
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                nm = item.get("name") or item.get("alias")
                if nm:
                    names.append(str(nm))
            elif isinstance(item, str):
                names.append(item)

    names = sorted(set(names))
    return (len(names) > 0), ",".join(names[:10]), len(names)


def crossmatch_skybot(
    candidates: pd.DataFrame,
    radius_arcsec: float,
    max_crossmatch: int,
) -> pd.DataFrame:
    if candidates.empty:
        candidates["moving_object_match"] = []
        return candidates

    out = candidates.copy()
    out["moving_object_match"] = False
    out["moving_object_names"] = ""
    out["moving_object_count"] = 0

    if Skybot is None:
        logging.warning("astroquery.imcce.Skybot is unavailable; skipping moving-object crossmatch.")
        return out

    cache: Dict[Tuple[float, float, float], Tuple[bool, str, int]] = {}
    n = min(len(out), max_crossmatch)
    logging.info("Crossmatching %d candidates with SkyBoT.", n)

    for idx in out.index[:n]:
        ra = float(out.at[idx, "ra"])
        dec = float(out.at[idx, "dec"])
        peak_mjd = float(out.at[idx, "peak_mjd"]) if np.isfinite(out.at[idx, "peak_mjd"]) else float(out.at[idx, "mjd_med"])
        key = (round(ra, 5), round(dec, 5), round(peak_mjd, 3))
        if key in cache:
            matched, names, count = cache[key]
        else:
            matched, names, count = query_skybot_cone(ra, dec, peak_mjd, radius_arcsec)
            cache[key] = (matched, names, count)
        out.at[idx, "moving_object_match"] = matched
        out.at[idx, "moving_object_names"] = names
        out.at[idx, "moving_object_count"] = count

    return out


def query_skybot_cone(
    ra: float,
    dec: float,
    mjd: float,
    radius_arcsec: float,
) -> Tuple[bool, str, int]:
    try:
        field = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
        epoch = Time(mjd, format="mjd")
        result = Skybot.cone_search(field, radius_arcsec * u.arcsec, epoch)
        if result is None or len(result) == 0:
            return False, "", 0

        name_col = None
        for cand in ["Name", "name", "Num", "number"]:
            if cand in result.colnames:
                name_col = cand
                break
        names: List[str] = []
        if name_col is not None:
            names = [str(x) for x in result[name_col][:10]]
        return True, ",".join(names), int(len(result))
    except Exception:
        return False, "", 0


def save_lightcurve_plots(
    clean_df: pd.DataFrame,
    ranked_df: pd.DataFrame,
    plots_dir: Path,
    max_plots: int,
) -> None:
    if ranked_df.empty:
        return

    if "MPLCONFIGDIR" not in os.environ:
        mpl_dir = plots_dir.parent / ".mplconfig"
        mpl_dir.mkdir(parents=True, exist_ok=True)
        os.environ["MPLCONFIGDIR"] = str(mpl_dir)

    import matplotlib.pyplot as plt

    plots_dir.mkdir(parents=True, exist_ok=True)

    top = ranked_df.head(max_plots)
    color_map = {"g": "tab:green", "r": "tab:red", "i": "tab:orange", "unknown": "tab:blue"}

    for _, row in top.iterrows():
        source_id = str(row["source_id"])
        g = clean_df[clean_df["source_id"] == source_id]
        if g.empty:
            continue

        fig, ax = plt.subplots(figsize=(8, 4.8))
        for flt, sub in g.groupby("filter"):
            ax.errorbar(
                sub["mjd"],
                sub["mag"],
                yerr=sub["mag_err"],
                fmt="o",
                markersize=3,
                alpha=0.75,
                color=color_map.get(str(flt), "tab:blue"),
                label=str(flt),
            )
        ax.invert_yaxis()
        ax.set_xlabel("MJD")
        ax.set_ylabel("Magnitude")
        ax.set_title(
            f"{source_id} | class={row['classification']} | score={row['rank_score']:.3f}"
        )
        ax.legend(loc="best", fontsize=8)
        ax.grid(alpha=0.2)
        fig.tight_layout()
        safe_name = source_id.replace("/", "_")
        fig.savefig(plots_dir / f"{safe_name}.png", dpi=130)
        plt.close(fig)


def run_pipeline(args: argparse.Namespace) -> Dict[str, object]:
    bands = normalize_band_list(args.bands)
    if args.input_csv is None and (args.ra is None or args.dec is None):
        raise ValueError("Provide --input-csv, or provide both --ra and --dec.")

    thresholds = Thresholds(
        min_points=args.min_points,
        min_amp_mag=args.min_amp_mag,
        min_peak_snr=args.min_peak_snr,
        min_significant_points=args.min_significant_points,
        sigma_threshold=args.sigma_threshold,
        periodic_fap=args.periodic_fap,
        min_period_days=args.min_period_days,
        max_period_days=args.max_period_days,
    )

    if args.input_csv is not None:
        logging.info("Reading input CSV: %s", args.input_csv)
        raw_df = pd.read_csv(args.input_csv)
    else:
        raw_df = fetch_ztf_lightcurves(
            ra=args.ra,
            dec=args.dec,
            radius_deg=args.radius_deg,
            bands=bands,
            timeout_sec=args.timeout_sec,
        )
    if raw_df.empty:
        return {
            "raw_df": raw_df,
            "clean_df": pd.DataFrame(),
            "features_df": pd.DataFrame(),
            "ranked_df": pd.DataFrame(),
            "summary": {
                "raw_rows": 0,
                "clean_rows": 0,
                "sources": 0,
                "candidates": 0,
                "novel_candidates": 0,
                "known_transient_matches": 0,
                "moving_object_matches": 0,
            },
        }

    std_df = standardize_ztf_frame(raw_df)
    clean_df = clean_photometry(std_df, max_mag_err=args.max_mag_err, max_catflags=args.max_catflags)
    if clean_df.empty:
        return {
            "raw_df": raw_df,
            "clean_df": clean_df,
            "features_df": pd.DataFrame(),
            "ranked_df": pd.DataFrame(),
            "summary": {
                "raw_rows": int(len(raw_df)),
                "clean_rows": 0,
                "sources": 0,
                "candidates": 0,
                "novel_candidates": 0,
                "known_transient_matches": 0,
                "moving_object_matches": 0,
            },
        }

    # Pandas may return a Series with a two-level index here; normalize to a flat DataFrame.
    features_obj = clean_df.groupby("source_id").apply(
        source_features,
        thresholds=thresholds,
        include_groups=False,
    )
    if isinstance(features_obj, pd.Series):
        features_df = features_obj.unstack().reset_index()
    else:
        features_df = features_obj.reset_index()
    mjd_stats = clean_df.groupby("source_id")["mjd"].median().rename("mjd_med")
    features_df = features_df.merge(mjd_stats, on="source_id", how="left")

    candidates_df = features_df[features_df["is_candidate"]].copy()
    if not args.disable_oac and not candidates_df.empty:
        candidates_df = crossmatch_oac(
            candidates_df,
            radius_arcsec=args.oac_radius_arcsec,
            timeout_sec=args.timeout_sec,
            max_crossmatch=args.max_crossmatch,
        )
    else:
        candidates_df["known_transient_match"] = False
        candidates_df["known_transient_names"] = ""
        candidates_df["known_transient_count"] = 0

    if not args.disable_skybot and not candidates_df.empty:
        candidates_df = crossmatch_skybot(
            candidates_df,
            radius_arcsec=args.skybot_radius_arcsec,
            max_crossmatch=args.max_crossmatch,
        )
    else:
        candidates_df["moving_object_match"] = False
        candidates_df["moving_object_names"] = ""
        candidates_df["moving_object_count"] = 0

    merged = features_df.merge(
        candidates_df[
            [
                "source_id",
                "known_transient_match",
                "known_transient_names",
                "known_transient_count",
                "moving_object_match",
                "moving_object_names",
                "moving_object_count",
            ]
        ],
        on="source_id",
        how="left",
    )
    merged["known_transient_match"] = merged["known_transient_match"].eq(True)
    merged["known_transient_names"] = merged["known_transient_names"].fillna("")
    merged["known_transient_count"] = pd.to_numeric(merged["known_transient_count"], errors="coerce").fillna(0).astype(int)
    merged["moving_object_match"] = merged["moving_object_match"].eq(True)
    merged["moving_object_names"] = merged["moving_object_names"].fillna("")
    merged["moving_object_count"] = pd.to_numeric(merged["moving_object_count"], errors="coerce").fillna(0).astype(int)
    merged["classification"] = merged.apply(classify_candidate, axis=1)

    # Ranking: prefer strong transient score, penalize known and moving objects.
    merged["rank_score"] = merged["transient_score"].fillna(0.0)
    merged.loc[merged["known_transient_match"], "rank_score"] -= 0.30
    merged.loc[merged["moving_object_match"], "rank_score"] -= 0.45
    merged["rank_score"] = merged["rank_score"].clip(lower=0.0)

    ranked_df = merged.sort_values(["is_candidate", "rank_score"], ascending=[False, False]).reset_index(drop=True)

    summary = {
        "raw_rows": int(len(raw_df)),
        "clean_rows": int(len(clean_df)),
        "sources": int(clean_df["source_id"].nunique()),
        "candidates": int(ranked_df["is_candidate"].sum()),
        "novel_candidates": int(
            (
                ranked_df["is_candidate"]
                & (~ranked_df["known_transient_match"])
                & (~ranked_df["moving_object_match"])
            ).sum()
        ),
        "known_transient_matches": int((ranked_df["known_transient_match"]).sum()),
        "moving_object_matches": int((ranked_df["moving_object_match"]).sum()),
    }
    return {
        "raw_df": raw_df,
        "clean_df": clean_df,
        "features_df": features_df,
        "ranked_df": ranked_df,
        "summary": summary,
    }


def write_outputs(
    output_root: Path,
    results: Dict[str, object],
    max_plots: int,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_root / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    raw_df: pd.DataFrame = results["raw_df"]  # type: ignore[assignment]
    clean_df: pd.DataFrame = results["clean_df"]  # type: ignore[assignment]
    features_df: pd.DataFrame = results["features_df"]  # type: ignore[assignment]
    ranked_df: pd.DataFrame = results["ranked_df"]  # type: ignore[assignment]
    summary: Dict[str, object] = results["summary"]  # type: ignore[assignment]

    raw_df.to_csv(run_dir / "raw_ztf.csv", index=False)
    clean_df.to_csv(run_dir / "clean_lightcurves.csv", index=False)
    features_df.to_csv(run_dir / "source_features.csv", index=False)
    ranked_df.to_csv(run_dir / "ranked_candidates.csv", index=False)
    with open(run_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    plots_dir = run_dir / "plots"
    save_lightcurve_plots(clean_df, ranked_df[ranked_df["is_candidate"]], plots_dir, max_plots=max_plots)
    return run_dir


def print_summary(summary: Dict[str, object], run_dir: Path) -> None:
    print("Pipeline complete.")
    print(f"Output directory: {run_dir}")
    print(f"Raw rows: {summary['raw_rows']}")
    print(f"Clean rows: {summary['clean_rows']}")
    print(f"Unique sources: {summary['sources']}")
    print(f"Transient candidates: {summary['candidates']}")
    print(f"Novel candidates: {summary['novel_candidates']}")
    print(f"Known transient matches: {summary['known_transient_matches']}")
    print(f"Moving-object matches: {summary['moving_object_matches']}")


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)
    try:
        results = run_pipeline(args)
        run_dir = write_outputs(args.output_dir, results, max_plots=args.max_plots)
        print_summary(results["summary"], run_dir)  # type: ignore[arg-type]
    except Exception as exc:
        logging.error(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
