#!/usr/bin/env python3
"""
Search for black-hole-related optical candidates.

This script looks for TDE/AGN-flare-like behavior in public ZTF/ALeRCE data.
It ranks candidates for follow-up; it does not confirm black holes.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from alerce.core import Alerce
from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u

try:
    from astroquery.ipac.ned import Ned
except Exception:  # pragma: no cover - optional runtime dependency
    Ned = None

try:
    from astroquery.simbad import Simbad
except Exception:  # pragma: no cover - optional runtime dependency
    Simbad = None

try:
    from astroquery.vizier import Vizier
except Exception:  # pragma: no cover - optional runtime dependency
    Vizier = None

from optical_transient_pipeline import clean_photometry, normalize_filter_series, standardize_ztf_frame


DEFAULT_CLASSES = "AGN,QSO,Blazar,TDE,SLSN"


@dataclass
class CatalogContext:
    simbad_main_id: str = ""
    simbad_otype: str = ""
    simbad_count: int = 0
    ned_name: str = ""
    ned_type: str = ""
    ned_redshift: str = ""
    ned_count: int = 0
    wise_w1_w2: float = np.nan
    wise_w2_w3: float = np.nan
    catalog_error: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rank optical candidates that may be related to TDEs or AGN flares."
    )
    parser.add_argument("--classifier", default="lc_classifier_BHRF_forced_phot_transient")
    parser.add_argument("--class-names", default=DEFAULT_CLASSES)
    parser.add_argument("--probability", type=float, default=0.25)
    parser.add_argument("--page-size", type=int, default=40)
    parser.add_argument("--max-objects", type=int, default=120)
    parser.add_argument("--object-ids", default="", help="Comma-separated ZTF IDs to inspect directly.")
    parser.add_argument("--input-csv", type=Path, help="Optional local detection CSV.")
    parser.add_argument("--output-dir", type=Path, default=Path("astronomy/blackhole_hunter_runs"))
    parser.add_argument("--max-mag-err", type=float, default=1.0)
    parser.add_argument("--max-catflags", type=int, default=0)
    parser.add_argument("--min-points", type=int, default=5)
    parser.add_argument("--min-duration-days", type=float, default=10.0)
    parser.add_argument("--max-duration-days", type=float, default=365.0)
    parser.add_argument("--fresh-days", type=float, default=180.0)
    parser.add_argument("--min-shortlist-score", type=float, default=0.55)
    parser.add_argument("--max-catalog-checks", type=int, default=25)
    parser.add_argument("--disable-catalogs", action="store_true")
    parser.add_argument("--enable-wise", action="store_true", help="Query AllWISE through Vizier.")
    return parser.parse_args()


def fid_to_filter(fid: object) -> str:
    try:
        return {1: "g", 2: "r", 3: "i"}.get(int(fid), str(fid))
    except Exception:
        return str(fid)


def object_probability(row: pd.Series) -> float:
    for col in ["probability", "class_probability", "prob", "classifier_probability"]:
        if col in row and pd.notna(row[col]):
            try:
                return float(row[col])
            except Exception:
                continue
    return 0.0


def fetch_broker_objects(args: argparse.Namespace, client: Alerce) -> Tuple[pd.DataFrame, List[str]]:
    warnings: List[str] = []
    object_ids = [x.strip() for x in args.object_ids.split(",") if x.strip()]
    if object_ids:
        return pd.DataFrame({"oid": object_ids, "broker_query_class": "manual"}), warnings

    frames: List[pd.DataFrame] = []
    class_names = [x.strip() for x in args.class_names.split(",") if x.strip()]
    for class_name in class_names:
        try:
            objects = client.query_objects(
                classifier=args.classifier,
                class_name=class_name,
                probability=args.probability,
                page_size=args.page_size,
                order_by="lastmjd",
                order_mode="DESC",
                format="pandas",
            )
        except Exception as exc:
            warnings.append(f"{class_name}: {exc}")
            continue

        if objects is None or objects.empty:
            warnings.append(f"{class_name}: no objects returned")
            continue
        objects = objects.copy()
        objects["broker_query_class"] = class_name
        frames.append(objects)

    if not frames:
        return pd.DataFrame(), warnings

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates("oid", keep="first")
    sort_col = "lastmjd" if "lastmjd" in merged.columns else "oid"
    merged = merged.sort_values(sort_col, ascending=False).head(args.max_objects).reset_index(drop=True)
    return merged, warnings


def fetch_lightcurve_rows(client: Alerce, objects: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    detections: List[Dict[str, object]] = []
    summaries: List[Dict[str, object]] = []

    for _, obj in objects.iterrows():
        oid = str(obj["oid"])
        try:
            lightcurve = client.query_lightcurve(oid, format="json")
        except Exception as exc:
            summaries.append({"source_id": oid, "fetch_error": str(exc)})
            continue

        dets = lightcurve.get("detections", []) if isinstance(lightcurve, dict) else []
        summaries.append(
            {
                "source_id": oid,
                "broker_query_class": obj.get("broker_query_class", ""),
                "broker_probability": object_probability(obj),
                "meanra": obj.get("meanra", np.nan),
                "meandec": obj.get("meandec", np.nan),
                "firstmjd": obj.get("firstmjd", np.nan),
                "lastmjd": obj.get("lastmjd", np.nan),
                "ndetections": len(dets),
                "fetch_error": "",
            }
        )

        for det in dets:
            mag = det.get("magpsf_corr", det.get("magpsf"))
            mag_err = det.get("sigmapsf_corr", det.get("sigmapsf"))
            mjd = det.get("mjd")
            fid = det.get("fid")
            if mag is None or mag_err is None or mjd is None:
                continue
            detections.append(
                {
                    "source_id": oid,
                    "ra": det.get("ra", obj.get("meanra")),
                    "dec": det.get("dec", obj.get("meandec")),
                    "mjd": mjd,
                    "mag": mag,
                    "magerr": mag_err,
                    "filter": fid,
                    "catflags": 0,
                    "distnr": det.get("distnr", np.nan),
                    "rb": det.get("rb", np.nan),
                    "drb": det.get("drb", np.nan),
                }
            )

    return pd.DataFrame(detections), pd.DataFrame(summaries)


def load_input_csv(path: Path) -> Tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(path)
    meta = pd.DataFrame({"source_id": sorted(raw["source_id"].astype(str).unique())})
    return raw, meta


def robust_slope(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 2:
        return 0.0
    x0 = x - np.nanmedian(x)
    try:
        slope, _ = np.polyfit(x0, y, 1)
        return float(slope)
    except Exception:
        return 0.0


def monotonic_score(times: np.ndarray, mags: np.ndarray) -> float:
    if len(times) < 4:
        return 0.0
    order = np.argsort(times)
    y = -mags[order]  # brighter means larger signal
    diffs = np.diff(y)
    if len(diffs) == 0:
        return 0.0
    same_direction = max(np.mean(diffs >= 0), np.mean(diffs <= 0))
    return float(np.clip(same_direction, 0.0, 1.0))


def source_blackhole_features(group: pd.DataFrame, min_duration_days: float) -> pd.Series:
    times = group["mjd"].to_numpy(dtype=float)
    mags = group["mag"].to_numpy(dtype=float)
    mag_err = group["mag_err"].to_numpy(dtype=float)
    n_points = len(group)
    ra = float(group["ra"].median())
    dec = float(group["dec"].median())
    duration = float(np.nanmax(times) - np.nanmin(times)) if n_points else 0.0
    amp = float(np.nanmax(mags) - np.nanmin(mags)) if n_points else 0.0
    idx_peak = int(np.nanargmin(mags)) if n_points else 0
    peak_mag = float(mags[idx_peak]) if n_points else np.nan
    peak_mjd = float(times[idx_peak]) if n_points else np.nan
    med_err = float(np.nanmedian(mag_err)) if n_points else np.nan
    signal_to_noise = amp / max(med_err, 1e-3) if np.isfinite(med_err) else 0.0
    slope_mag_per_day = robust_slope(times, mags)
    smoothness = monotonic_score(times, mags)
    duration_score = float(np.clip(duration / max(min_duration_days, 1.0), 0.0, 1.0))
    amp_score = float(np.clip(amp / 1.5, 0.0, 1.0))
    snr_score = float(np.clip(signal_to_noise / 10.0, 0.0, 1.0))
    distnr_med = float(group["distnr"].median()) if "distnr" in group and group["distnr"].notna().any() else np.nan
    rb_med = float(group["rb"].median()) if "rb" in group and group["rb"].notna().any() else np.nan
    drb_med = float(group["drb"].median()) if "drb" in group and group["drb"].notna().any() else np.nan

    return pd.Series(
        {
            "ra": ra,
            "dec": dec,
            "n_points": n_points,
            "first_mjd": float(np.nanmin(times)) if n_points else np.nan,
            "last_mjd": float(np.nanmax(times)) if n_points else np.nan,
            "duration_days": duration,
            "amp_mag": amp,
            "peak_mag": peak_mag,
            "peak_mjd": peak_mjd,
            "median_mag_err": med_err,
            "amplitude_snr": signal_to_noise,
            "slope_mag_per_day": slope_mag_per_day,
            "smoothness_score": smoothness,
            "duration_score": duration_score,
            "amp_score": amp_score,
            "snr_score": snr_score,
            "distnr_median_arcsec": distnr_med,
            "rb_median": rb_med,
            "drb_median": drb_med,
        }
    )


def query_simbad(coord: SkyCoord, radius_arcsec: float) -> Tuple[str, str, int]:
    if Simbad is None:
        return "", "", 0
    try:
        custom = Simbad()
        custom.add_votable_fields("otype")
        result = custom.query_region(coord, radius=radius_arcsec * u.arcsec)
        if result is None or len(result) == 0:
            return "", "", 0
        main_id = str(result["MAIN_ID"][0])
        otype = str(result["OTYPE"][0]) if "OTYPE" in result.colnames else ""
        return main_id, otype, int(len(result))
    except Exception:
        return "", "", 0


def query_ned(coord: SkyCoord, radius_arcsec: float) -> Tuple[str, str, str, int]:
    if Ned is None:
        return "", "", "", 0
    try:
        result = Ned.query_region(coord, radius=radius_arcsec * u.arcsec)
        if result is None or len(result) == 0:
            return "", "", "", 0
        name = str(result["Object Name"][0]) if "Object Name" in result.colnames else ""
        obj_type = str(result["Type"][0]) if "Type" in result.colnames else ""
        redshift = str(result["Redshift"][0]) if "Redshift" in result.colnames else ""
        return name, obj_type, redshift, int(len(result))
    except Exception:
        return "", "", "", 0


def query_wise(coord: SkyCoord, radius_arcsec: float) -> Tuple[float, float]:
    if Vizier is None:
        return np.nan, np.nan
    try:
        vizier = Vizier(columns=["W1mag", "W2mag", "W3mag"], row_limit=1)
        tables = vizier.query_region(coord, radius=radius_arcsec * u.arcsec, catalog="II/328/allwise")
        if not tables:
            return np.nan, np.nan
        row = tables[0][0]
        w1 = float(row["W1mag"])
        w2 = float(row["W2mag"])
        w3 = float(row["W3mag"])
        return w1 - w2, w2 - w3
    except Exception:
        return np.nan, np.nan


def catalog_context(ra: float, dec: float, enable_wise: bool) -> CatalogContext:
    coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
    ctx = CatalogContext()
    ctx.simbad_main_id, ctx.simbad_otype, ctx.simbad_count = query_simbad(coord, 3.0)
    ctx.ned_name, ctx.ned_type, ctx.ned_redshift, ctx.ned_count = query_ned(coord, 5.0)
    if enable_wise:
        ctx.wise_w1_w2, ctx.wise_w2_w3 = query_wise(coord, 3.0)
    return ctx


def add_catalogs(features: pd.DataFrame, max_checks: int, enable_wise: bool) -> pd.DataFrame:
    out = features.copy()
    catalog_rows: List[Dict[str, object]] = []
    for _, row in out.head(max_checks).iterrows():
        ctx = catalog_context(float(row["ra"]), float(row["dec"]), enable_wise)
        catalog_rows.append({"source_id": row["source_id"], **ctx.__dict__})
    catalog_df = pd.DataFrame(catalog_rows)
    if catalog_df.empty:
        for col in CatalogContext().__dict__.keys():
            out[col] = ""
        return out
    return out.merge(catalog_df, on="source_id", how="left")


def classify_bh_candidate(row: pd.Series) -> str:
    otype = str(row.get("simbad_otype", "")).lower()
    ned_type = str(row.get("ned_type", "")).lower()
    w1_w2 = row.get("wise_w1_w2", np.nan)
    known_agn = any(x in otype or x in ned_type for x in ["agn", "qso", "quasar", "seyfert", "blazar"])
    redshift_known = str(row.get("ned_redshift", "")).strip() not in {"", "nan", "--"}
    agn_wise = pd.notna(w1_w2) and float(w1_w2) >= 0.8
    smooth = float(row.get("smoothness_score", 0.0)) >= 0.65
    long = float(row.get("duration_days", 0.0)) >= 10.0
    brightening = float(row.get("slope_mag_per_day", 0.0)) < 0.0
    very_long = float(row.get("duration_days", 0.0)) > 365.0

    if very_long and not known_agn:
        return "long_running_variable_or_unclear"
    if known_agn or agn_wise:
        return "possible_agn_flare"
    if redshift_known and smooth and long:
        return "possible_tde_candidate"
    if smooth and long and brightening:
        return "nuclear_flare_candidate_needs_host_check"
    return "low_priority_blackhole_related"


def score_candidates(
    features: pd.DataFrame,
    broker_meta: pd.DataFrame,
    fresh_days: float,
    max_duration_days: float,
    min_shortlist_score: float,
) -> pd.DataFrame:
    out = features.merge(broker_meta, on="source_id", how="left")
    out["broker_probability"] = pd.to_numeric(out["broker_probability"], errors="coerce").fillna(0.0)
    out["last_mjd"] = pd.to_numeric(out["last_mjd"], errors="coerce")
    out["first_mjd"] = pd.to_numeric(out["first_mjd"], errors="coerce")
    newest = float(out["last_mjd"].max()) if out["last_mjd"].notna().any() else 0.0
    recency = 1.0 - ((newest - out["last_mjd"].fillna(newest)).clip(lower=0.0) / 30.0)
    out["recency_score"] = recency.clip(lower=0.0, upper=1.0)
    out["candidate_age_days"] = (newest - out["first_mjd"]).clip(lower=0.0)
    out["days_since_last_detection"] = (newest - out["last_mjd"]).clip(lower=0.0)
    duration_penalty = (out["duration_days"].fillna(0.0) / max(max_duration_days, 1.0)).clip(0.0, 1.0)
    out["bh_related_score"] = (
        0.25 * out["smoothness_score"].fillna(0.0)
        + 0.20 * out["duration_score"].fillna(0.0)
        + 0.20 * out["amp_score"].fillna(0.0)
        + 0.15 * out["snr_score"].fillna(0.0)
        + 0.10 * out["broker_probability"].clip(0.0, 1.0)
        + 0.10 * out["recency_score"].fillna(0.0)
    )
    out["bh_related_score"] = out["bh_related_score"] - (0.10 * duration_penalty)
    out["bh_related_score"] = out["bh_related_score"].clip(lower=0.0)
    out["bh_classification"] = out.apply(classify_bh_candidate, axis=1)
    out["review_tier"] = "review_later"
    high_priority = (
        (out["bh_related_score"] >= min_shortlist_score)
        & (out["candidate_age_days"] <= fresh_days)
        & (out["duration_days"] <= max_duration_days)
        & (~out["bh_classification"].eq("long_running_variable_or_unclear"))
    )
    out.loc[high_priority, "review_tier"] = "high_priority"
    out.loc[out["duration_days"] > max_duration_days, "review_tier"] = "long_running_source"
    out = out.sort_values("bh_related_score", ascending=False).reset_index(drop=True)
    return out


def write_plots(clean: pd.DataFrame, ranked: pd.DataFrame, plots_dir: Path, max_plots: int = 25) -> None:
    if clean.empty or ranked.empty:
        return
    import matplotlib.pyplot as plt

    plots_dir.mkdir(parents=True, exist_ok=True)
    colors = {"g": "tab:green", "r": "tab:red", "i": "tab:orange"}
    for _, row in ranked.head(max_plots).iterrows():
        oid = str(row["source_id"])
        sub = clean[clean["source_id"] == oid]
        if sub.empty:
            continue
        fig, ax = plt.subplots(figsize=(8, 4.8))
        for flt, group in sub.groupby("filter"):
            ax.errorbar(
                group["mjd"],
                group["mag"],
                yerr=group["mag_err"],
                fmt="o",
                markersize=3,
                color=colors.get(str(flt), "tab:blue"),
                label=str(flt),
                alpha=0.8,
            )
        ax.invert_yaxis()
        ax.grid(alpha=0.2)
        ax.legend(loc="best", fontsize=8)
        ax.set_xlabel("MJD")
        ax.set_ylabel("Magnitude")
        ax.set_title(f"{oid} | {row['bh_classification']} | score={row['bh_related_score']:.3f}")
        fig.tight_layout()
        fig.savefig(plots_dir / f"{oid}.png", dpi=130)
        plt.close(fig)


def run(args: argparse.Namespace) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output_dir / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    if args.input_csv:
        raw, broker_meta = load_input_csv(args.input_csv)
        warnings: List[str] = []
        objects = pd.DataFrame()
    else:
        client = Alerce()
        objects, warnings = fetch_broker_objects(args, client)
        raw, broker_meta = fetch_lightcurve_rows(client, objects)

    objects.to_csv(run_dir / "broker_objects.csv", index=False)
    raw.to_csv(run_dir / "raw_detections.csv", index=False)
    broker_meta.to_csv(run_dir / "broker_object_summary.csv", index=False)

    if raw.empty:
        summary = {"objects": int(len(objects)), "raw_rows": 0, "warnings": warnings}
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return run_dir

    std = standardize_ztf_frame(raw)
    if "filter" in raw.columns:
        std["filter"] = normalize_filter_series(raw["filter"])
    clean = clean_photometry(std, args.max_mag_err, args.max_catflags)
    clean.to_csv(run_dir / "clean_lightcurves.csv", index=False)

    clean = clean.groupby("source_id").filter(lambda g: len(g) >= args.min_points)
    features = clean.groupby("source_id").apply(
        source_blackhole_features,
        min_duration_days=args.min_duration_days,
        include_groups=False,
    )
    features = features.unstack().reset_index() if isinstance(features, pd.Series) else features.reset_index()
    features = features.sort_values("last_mjd", ascending=False).reset_index(drop=True)
    features.to_csv(run_dir / "bh_features.csv", index=False)

    if not args.disable_catalogs and not features.empty:
        features = add_catalogs(features, args.max_catalog_checks, args.enable_wise)

    ranked = score_candidates(
        features,
        broker_meta,
        fresh_days=args.fresh_days,
        max_duration_days=args.max_duration_days,
        min_shortlist_score=args.min_shortlist_score,
    )
    ranked.to_csv(run_dir / "blackhole_ranked_candidates.csv", index=False)
    shortlist = ranked[ranked["review_tier"] == "high_priority"].copy()
    shortlist.to_csv(run_dir / "blackhole_shortlist.csv", index=False)
    write_plots(clean, ranked, run_dir / "plots")

    summary = {
        "objects": int(len(objects)) if not args.input_csv else int(broker_meta["source_id"].nunique()),
        "raw_rows": int(len(raw)),
        "clean_rows": int(len(clean)),
        "sources": int(clean["source_id"].nunique()) if not clean.empty else 0,
        "shortlist": int(len(shortlist)),
        "warnings": warnings,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return run_dir


def main() -> None:
    args = parse_args()
    try:
        run_dir = run(args)
    except Exception as exc:
        print(f"Black-hole candidate hunter failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print("Black-hole-related candidate hunt complete.")
    print(f"Output directory: {run_dir}")
    print(f"Shortlist: {run_dir / 'blackhole_shortlist.csv'}")
    print(f"Ranked candidates: {run_dir / 'blackhole_ranked_candidates.csv'}")


if __name__ == "__main__":
    main()
