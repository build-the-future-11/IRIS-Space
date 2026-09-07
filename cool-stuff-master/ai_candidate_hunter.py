#!/usr/bin/env python3
"""
AI-assisted multi-object transient hunter.

This runner uses ALeRCE broker classifications as the machine-learning intake,
then applies the local light-curve feature pipeline to rank multiple objects.
It is meant for candidate discovery/triage, not final confirmation.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Set, Tuple

import numpy as np
import pandas as pd
from alerce.core import Alerce

from optical_transient_pipeline import (
    Thresholds,
    clean_photometry,
    save_lightcurve_plots,
    source_features,
    standardize_ztf_frame,
)


DEFAULT_CLASSES = "SNIa,SNII,SNIbc,SLSN"
DEFAULT_EARLY_VETO_CLASSES = "QSO,AGN"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find and rank multiple optical transient candidates from ALeRCE/ZTF."
    )
    parser.add_argument("--classifier", default="lc_classifier_BHRF_forced_phot_transient")
    parser.add_argument("--class-names", default=DEFAULT_CLASSES)
    parser.add_argument("--probability", type=float, default=0.35)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--max-objects", type=int, default=150)
    parser.add_argument(
        "--max-pages-per-class",
        type=int,
        default=5,
        help="Maximum ALeRCE result pages to scan per class when filling max objects.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("astronomy/ai_hunter_runs"))
    parser.add_argument(
        "--exclude-objects-csv",
        type=Path,
        action="append",
        default=[],
        help="CSV containing oid or source_id values to skip. Can be repeated.",
    )
    parser.add_argument(
        "--exclude-previous-runs",
        action="store_true",
        help="Skip all object IDs found in previous run broker_objects.csv files under output-dir.",
    )
    parser.add_argument("--max-mag-err", type=float, default=1.0)
    parser.add_argument("--max-catflags", type=int, default=0)
    parser.add_argument("--min-points", type=int, default=3)
    parser.add_argument("--min-amp-mag", type=float, default=0.2)
    parser.add_argument("--min-peak-snr", type=float, default=0.8)
    parser.add_argument("--min-significant-points", type=int, default=1)
    parser.add_argument("--sigma-threshold", type=float, default=1.5)
    parser.add_argument(
        "--fresh-days",
        type=float,
        default=90.0,
        help="Prefer objects whose broker first detection is within this many days of the newest object.",
    )
    parser.add_argument(
        "--discovered-within-days",
        type=float,
        default=0.0,
        help="Query-level filter: only fetch objects whose broker first detection is within this many days of now. 0 disables the filter.",
    )
    parser.add_argument(
        "--max-history-points",
        type=int,
        default=80,
        help="Prefer objects with no more than this many alert detections.",
    )
    parser.add_argument("--min-ai-score", type=float, default=0.60)
    parser.add_argument("--max-plots", type=int, default=40)
    parser.add_argument(
        "--early-veto-age-days",
        type=float,
        default=60.0,
        help="Mark candidates as likely long-lived variability if first detection is older than this many days.",
    )
    parser.add_argument(
        "--early-veto-detections",
        type=float,
        default=50.0,
        help="Mark candidates as likely long-lived variability if they exceed this many detections.",
    )
    parser.add_argument(
        "--early-veto-baseline-days",
        type=float,
        default=120.0,
        help="Mark candidates as likely long-lived variability if the first-to-last detection span exceeds this many days.",
    )
    parser.add_argument(
        "--early-veto-classes",
        default=DEFAULT_EARLY_VETO_CLASSES,
        help="Comma-separated broker classes to down-rank early as likely AGN/QSO-like variability.",
    )
    parser.add_argument(
        "--per-object-timeout-sec",
        type=float,
        default=20.0,
        help="Skip an object if its light-curve fetch takes longer than this many seconds.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("astronomy/cache/alerce_lightcurves"),
        help="Directory for cached ALeRCE light-curve JSON files.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Fetch light curves from ALeRCE even when a cached copy exists.",
    )
    return parser.parse_args()


class ObjectFetchTimeout(TimeoutError):
    pass


@contextmanager
def per_object_timeout(seconds: float):
    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return

    previous_handler = signal.getsignal(signal.SIGALRM)

    def timeout_handler(_signum, _frame):
        raise ObjectFetchTimeout(f"timed out after {seconds:.1f} seconds")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def install_request_timeout(client: Alerce, timeout_sec: float) -> None:
    if timeout_sec <= 0:
        return

    session = getattr(client, "session", None)
    original_request = getattr(session, "request", None)
    if original_request is None or getattr(session, "_helio_timeout_installed", False):
        return

    def request_with_timeout(method, url, **kwargs):
        kwargs.setdefault("timeout", timeout_sec)
        return original_request(method, url, **kwargs)

    session.request = request_with_timeout
    session._helio_timeout_installed = True


def fetch_objects(
    client: Alerce,
    classifier: str,
    class_names: List[str],
    probability: float,
    page_size: int,
    max_objects: int,
    max_pages_per_class: int,
    excluded_oids: Set[str],
    firstmjd_range: List[float] | None = None,
) -> Tuple[pd.DataFrame, List[str]]:
    frames: List[pd.DataFrame] = []
    warnings: List[str] = []

    query_extra: Dict[str, List[float]] = {}
    if firstmjd_range is not None:
        query_extra["firstmjd"] = firstmjd_range

    for class_name in class_names:
        for page in range(1, max_pages_per_class + 1):
            try:
                objects = client.query_objects(
                    classifier=classifier,
                    class_name=class_name,
                    probability=probability,
                    page=page,
                    page_size=page_size,
                    order_by="lastmjd",
                    order_mode="DESC",
                    format="pandas",
                    **query_extra,
                )
            except Exception as exc:
                warnings.append(f"{class_name} page {page}: {exc}")
                break

            if objects is None or objects.empty:
                break
            objects = objects.copy()
            objects["broker_query_class"] = class_name
            frames.append(objects)

            collected = pd.concat(frames, ignore_index=True)
            if "oid" in collected.columns:
                collected = collected[~collected["oid"].astype(str).isin(excluded_oids)]
                if collected["oid"].nunique() >= max_objects:
                    break

    if not frames:
        return pd.DataFrame(), warnings

    merged = pd.concat(frames, ignore_index=True)
    if "oid" not in merged.columns:
        return pd.DataFrame(), warnings + ["ALeRCE response did not include oid."]

    if excluded_oids:
        merged = merged[~merged["oid"].astype(str).isin(excluded_oids)].copy()

    sort_col = "lastmjd" if "lastmjd" in merged.columns else "oid"
    merged = merged.sort_values(sort_col, ascending=False)
    merged = merged.drop_duplicates("oid", keep="first").head(max_objects).reset_index(drop=True)
    return merged, warnings


def read_oid_csv(path: Path) -> Set[str]:
    try:
        df = pd.read_csv(path, usecols=lambda col: col in {"oid", "source_id"})
    except Exception:
        return set()

    values: Set[str] = set()
    for col in ["oid", "source_id"]:
        if col in df.columns:
            values.update(str(value).strip() for value in df[col].dropna() if str(value).strip())
    return values


def load_excluded_oids(args: argparse.Namespace) -> Set[str]:
    excluded: Set[str] = set()
    for csv_path in args.exclude_objects_csv:
        excluded.update(read_oid_csv(csv_path))

    if args.exclude_previous_runs:
        for csv_path in sorted(args.output_dir.glob("run_*/broker_objects.csv")):
            excluded.update(read_oid_csv(csv_path))

    return excluded


def object_probability(row: pd.Series) -> float:
    for col in ["probability", "class_probability", "prob", "classifier_probability"]:
        if col in row and pd.notna(row[col]):
            try:
                return float(row[col])
            except Exception:
                pass
    return 0.0


def cache_path(cache_dir: Path, oid: str) -> Path:
    return cache_dir / f"{oid}.json"


def load_cached_lightcurve(cache_dir: Path, oid: str) -> Dict[str, object] | None:
    path = cache_path(cache_dir, oid)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def save_cached_lightcurve(cache_dir: Path, oid: str, lightcurve: Dict[str, object]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_path(cache_dir, oid), "w", encoding="utf-8") as f:
        json.dump(lightcurve, f)


def fetch_detection_rows(
    client: Alerce,
    objects: pd.DataFrame,
    per_object_timeout_sec: float,
    cache_dir: Path,
    refresh_cache: bool,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    rows: List[Dict[str, object]] = []
    object_rows: List[Dict[str, object]] = []

    for _, obj in objects.iterrows():
        oid = str(obj["oid"])
        cache_status = "miss"
        try:
            lightcurve = None if refresh_cache else load_cached_lightcurve(cache_dir, oid)
            if lightcurve is not None:
                cache_status = "hit"
            else:
                with per_object_timeout(per_object_timeout_sec):
                    lightcurve = client.query_lightcurve(oid, format="json")
                cache_status = "refreshed" if refresh_cache else "miss"
                if isinstance(lightcurve, dict):
                    save_cached_lightcurve(cache_dir, oid, lightcurve)
        except Exception as exc:
            object_rows.append(
                {
                    "source_id": oid,
                    "broker_query_class": obj.get("broker_query_class", ""),
                    "broker_probability": object_probability(obj),
                    "cache_status": cache_status,
                    "fetch_error": str(exc),
                }
            )
            continue

        dets = lightcurve.get("detections", []) if isinstance(lightcurve, dict) else []
        object_rows.append(
            {
                "source_id": oid,
                "broker_query_class": obj.get("broker_query_class", ""),
                "broker_object_class": obj.get("class", ""),
                "broker_probability": object_probability(obj),
                "meanra": obj.get("meanra", np.nan),
                "meandec": obj.get("meandec", np.nan),
                "firstmjd": obj.get("firstmjd", np.nan),
                "lastmjd": obj.get("lastmjd", np.nan),
                "ndetections": len(dets),
                "cache_status": cache_status,
                "fetch_error": "",
            }
        )

        for det in dets:
            mag = det.get("magpsf_corr", det.get("magpsf"))
            mag_err = det.get("sigmapsf_corr", det.get("sigmapsf"))
            mjd = det.get("mjd")
            fid = det.get("fid")
            ra = det.get("ra", obj.get("meanra"))
            dec = det.get("dec", obj.get("meandec"))
            if mag is None or mag_err is None or mjd is None:
                continue
            rows.append(
                {
                    "source_id": oid,
                    "ra": ra,
                    "dec": dec,
                    "mjd": mjd,
                    "mag": mag,
                    "magerr": mag_err,
                    "filter": fid,
                    "catflags": 0,
                }
            )

    return pd.DataFrame(rows), pd.DataFrame(object_rows)


def parse_label_set(raw: str) -> set[str]:
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def add_ai_scores(
    ranked: pd.DataFrame,
    broker_meta: pd.DataFrame,
    fresh_days: float,
    max_history_points: int,
    min_ai_score: float,
    early_veto_age_days: float,
    early_veto_detections: float,
    early_veto_baseline_days: float,
    early_veto_classes: set[str],
) -> pd.DataFrame:
    out = ranked.merge(broker_meta, on="source_id", how="left")
    out["broker_probability"] = pd.to_numeric(out["broker_probability"], errors="coerce").fillna(0.0)
    out["lastmjd"] = pd.to_numeric(out["lastmjd"], errors="coerce")
    out["firstmjd"] = pd.to_numeric(out["firstmjd"], errors="coerce")
    out["n_points"] = pd.to_numeric(out["n_points"], errors="coerce").fillna(0)
    out["ndetections"] = pd.to_numeric(out["ndetections"], errors="coerce")
    newest = float(out["lastmjd"].max()) if out["lastmjd"].notna().any() else 0.0
    recency = 1.0 - ((newest - out["lastmjd"].fillna(newest)).clip(lower=0.0) / 30.0)
    out["recency_score"] = recency.clip(lower=0.0, upper=1.0)
    out["candidate_age_days"] = (newest - out["firstmjd"]).clip(lower=0.0)
    out["detection_baseline_days"] = (out["lastmjd"] - out["firstmjd"]).clip(lower=0.0)
    age_score = 1.0 - (out["candidate_age_days"].fillna(fresh_days) / max(fresh_days, 1.0))
    out["freshness_score"] = age_score.clip(lower=0.0, upper=1.0)
    history_penalty = (out["n_points"] / max(max_history_points, 1)).clip(lower=0.0, upper=1.0)
    out["ai_score"] = (
        0.45 * out["transient_score"].fillna(0.0)
        + 0.25 * out["broker_probability"].clip(0.0, 1.0)
        + 0.15 * out["recency_score"].fillna(0.0)
        + 0.15 * out["freshness_score"].fillna(0.0)
    )
    out["ai_score"] = out["ai_score"] - (0.10 * history_penalty)
    out.loc[out["classification"] != "new_transient_candidate", "ai_score"] *= 0.5
    if "broker_object_class" in out.columns:
        broker_class = out["broker_object_class"]
    elif "broker_query_class" in out.columns:
        broker_class = out["broker_query_class"]
    else:
        broker_class = pd.Series("", index=out.index, dtype=object)
    broker_class = broker_class.fillna("").astype(str).str.upper().str.strip()
    broker_veto = broker_class.isin(early_veto_classes)
    old_veto = out["candidate_age_days"].fillna(early_veto_age_days + 1) > early_veto_age_days
    detection_veto = out["ndetections"].fillna(0) > early_veto_detections
    baseline_veto = out["detection_baseline_days"].fillna(0) > early_veto_baseline_days
    early_veto = broker_veto | old_veto | detection_veto | baseline_veto
    out["early_veto"] = early_veto
    out["early_veto_reason"] = ""
    out.loc[broker_veto, "early_veto_reason"] = "broker_class_veto"
    out.loc[(out["early_veto_reason"] == "") & old_veto, "early_veto_reason"] = "old_first_detection"
    out.loc[(out["early_veto_reason"] == "") & detection_veto, "early_veto_reason"] = "too_many_detections"
    out.loc[(out["early_veto_reason"] == "") & baseline_veto, "early_veto_reason"] = "long_detection_baseline"
    out.loc[early_veto, "ai_score"] = out.loc[early_veto, "ai_score"] * 0.35
    out["review_tier"] = "review_later"
    high_priority = (
        (out["classification"] == "new_transient_candidate")
        & (out["ai_score"] >= min_ai_score)
        & (out["candidate_age_days"] <= fresh_days)
        & (out["n_points"] <= max_history_points)
        & ~early_veto
    )
    out.loc[high_priority, "review_tier"] = "high_priority"
    old_or_dense = (out["candidate_age_days"] > fresh_days) | (out["n_points"] > max_history_points)
    out.loc[(out["classification"] == "new_transient_candidate") & old_or_dense, "review_tier"] = "possible_variable_or_known_object"
    out.loc[(out["classification"] == "new_transient_candidate") & early_veto, "review_tier"] = "early_veto_long_lived_or_agn"
    out = out.sort_values(["classification", "ai_score"], ascending=[True, False])
    out = out.sort_values("ai_score", ascending=False).reset_index(drop=True)
    return out


def run_hunter(args: argparse.Namespace) -> Path:
    client = Alerce()
    install_request_timeout(client, args.per_object_timeout_sec)
    class_names = [x.strip() for x in args.class_names.split(",") if x.strip()]
    excluded_oids = load_excluded_oids(args)
    firstmjd_range = None
    if args.discovered_within_days > 0:
        now_mjd = datetime.now(timezone.utc).timestamp() / 86400.0 + 40587.0
        firstmjd_range = [now_mjd - args.discovered_within_days, now_mjd + 1.0]
    objects, warnings = fetch_objects(
        client=client,
        classifier=args.classifier,
        class_names=class_names,
        probability=args.probability,
        page_size=args.page_size,
        max_objects=args.max_objects,
        max_pages_per_class=args.max_pages_per_class,
        excluded_oids=excluded_oids,
        firstmjd_range=firstmjd_range,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output_dir / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    objects.to_csv(run_dir / "broker_objects.csv", index=False)
    raw_rows, broker_meta = fetch_detection_rows(
        client=client,
        objects=objects,
        per_object_timeout_sec=args.per_object_timeout_sec,
        cache_dir=args.cache_dir,
        refresh_cache=args.refresh_cache,
    )
    raw_rows.to_csv(run_dir / "raw_alerce_detections.csv", index=False)
    broker_meta.to_csv(run_dir / "broker_object_summary.csv", index=False)

    thresholds = Thresholds(
        min_points=args.min_points,
        min_amp_mag=args.min_amp_mag,
        min_peak_snr=args.min_peak_snr,
        min_significant_points=args.min_significant_points,
        sigma_threshold=args.sigma_threshold,
        periodic_fap=1e-3,
        min_period_days=0.1,
        max_period_days=200.0,
    )

    if raw_rows.empty:
        summary = {
            "broker_objects": int(len(objects)),
            "excluded_oids": int(len(excluded_oids)),
            "detection_rows": 0,
            "ranked_candidates": 0,
            "cache_hits": int((broker_meta.get("cache_status", pd.Series(dtype=str)) == "hit").sum()),
            "cache_misses": int((broker_meta.get("cache_status", pd.Series(dtype=str)) == "miss").sum()),
            "cache_refreshes": int((broker_meta.get("cache_status", pd.Series(dtype=str)) == "refreshed").sum()),
            "warnings": warnings,
        }
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return run_dir

    std = standardize_ztf_frame(raw_rows)
    clean = clean_photometry(std, max_mag_err=args.max_mag_err, max_catflags=args.max_catflags)
    clean.to_csv(run_dir / "clean_lightcurves.csv", index=False)

    features_obj = clean.groupby("source_id").apply(
        source_features,
        thresholds=thresholds,
        include_groups=False,
    )
    features = features_obj.unstack().reset_index() if isinstance(features_obj, pd.Series) else features_obj.reset_index()
    mjd_stats = clean.groupby("source_id")["mjd"].median().rename("mjd_med")
    features = features.merge(mjd_stats, on="source_id", how="left")

    features["known_transient_match"] = False
    features["known_transient_names"] = ""
    features["known_transient_count"] = 0
    features["moving_object_match"] = False
    features["moving_object_names"] = ""
    features["moving_object_count"] = 0
    features["classification"] = np.where(features["is_candidate"], "new_transient_candidate", "not_transient")
    features["rank_score"] = features["transient_score"].fillna(0.0)

    ranked = add_ai_scores(
        features,
        broker_meta,
        fresh_days=args.fresh_days,
        max_history_points=args.max_history_points,
        min_ai_score=args.min_ai_score,
        early_veto_age_days=args.early_veto_age_days,
        early_veto_detections=args.early_veto_detections,
        early_veto_baseline_days=args.early_veto_baseline_days,
        early_veto_classes=parse_label_set(args.early_veto_classes),
    )
    ranked.to_csv(run_dir / "ai_ranked_candidates.csv", index=False)
    ranked[ranked["classification"] == "new_transient_candidate"].to_csv(
        run_dir / "ai_shortlist.csv", index=False
    )
    ranked[ranked["early_veto"]].to_csv(run_dir / "early_veto_rejected.csv", index=False)
    ranked[
        (ranked["classification"] == "new_transient_candidate") & ~ranked["early_veto"]
    ].to_csv(run_dir / "fresh_shortlist.csv", index=False)
    high_priority = ranked[ranked["review_tier"] == "high_priority"].copy()
    high_priority.to_csv(run_dir / "high_priority_shortlist.csv", index=False)

    save_lightcurve_plots(
        clean_df=clean,
        ranked_df=ranked[ranked["classification"] == "new_transient_candidate"],
        plots_dir=run_dir / "plots",
        max_plots=args.max_plots,
    )

    summary = {
        "broker_objects": int(len(objects)),
        "excluded_oids": int(len(excluded_oids)),
        "detection_rows": int(len(raw_rows)),
        "clean_rows": int(len(clean)),
        "sources": int(clean["source_id"].nunique()),
        "ranked_candidates": int((ranked["classification"] == "new_transient_candidate").sum()),
        "early_veto_rejected": int(ranked["early_veto"].sum()),
        "fresh_shortlist": int(
            ((ranked["classification"] == "new_transient_candidate") & ~ranked["early_veto"]).sum()
        ),
        "high_priority": int(len(high_priority)),
        "cache_hits": int((broker_meta.get("cache_status", pd.Series(dtype=str)) == "hit").sum()),
        "cache_misses": int((broker_meta.get("cache_status", pd.Series(dtype=str)) == "miss").sum()),
        "cache_refreshes": int((broker_meta.get("cache_status", pd.Series(dtype=str)) == "refreshed").sum()),
        "warnings": warnings,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return run_dir


def main() -> None:
    args = parse_args()
    try:
        run_dir = run_hunter(args)
    except Exception as exc:
        print(f"AI hunter failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("AI-assisted candidate hunt complete.")
    print(f"Output directory: {run_dir}")
    print(f"Shortlist: {run_dir / 'ai_shortlist.csv'}")
    print(f"Fresh shortlist: {run_dir / 'fresh_shortlist.csv'}")
    print(f"Early veto rejected: {run_dir / 'early_veto_rejected.csv'}")
    print(f"High priority: {run_dir / 'high_priority_shortlist.csv'}")
    print(f"Ranked candidates: {run_dir / 'ai_ranked_candidates.csv'}")


if __name__ == "__main__":
    main()
