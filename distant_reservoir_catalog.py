#!/usr/bin/env python3
"""
Build a known-object catalog for distant comet reservoirs.

This uses JPL SBDB orbital elements to rank known Kuiper Belt/TNO, Centaur,
and Oort-like long-period comet candidates. It does not discover new objects
from images; it prepares a vetted target/crossmatch table for follow-up.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

try:
    from astroquery.jplhorizons import Horizons
except Exception:  # pragma: no cover - optional runtime dependency
    Horizons = None


SBDB_QUERY_URL = "https://ssd-api.jpl.nasa.gov/sbdb_query.api"
OUTPUT_FIELDS = [
    "spkid",
    "full_name",
    "pdes",
    "name",
    "prefix",
    "kind",
    "class",
    "epoch",
    "e",
    "a",
    "q",
    "i",
    "om",
    "w",
    "ma",
    "tp_cal",
    "per_y",
    "ad",
    "t_jup",
    "condition_code",
    "data_arc",
    "n_obs_used",
    "H",
    "M1",
    "K1",
    "first_obs",
    "last_obs",
    "soln_date",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch and rank known distant-reservoir small bodies from JPL SBDB."
    )
    parser.add_argument(
        "--reservoir",
        choices=["all", "kuiper", "centaur", "oort"],
        default="all",
        help="Object reservoir subset to fetch.",
    )
    parser.add_argument("--limit", type=int, default=200, help="Maximum rows per reservoir query.")
    parser.add_argument("--timeout-sec", type=float, default=60.0)
    parser.add_argument(
        "--ephemeris-top",
        type=int,
        default=25,
        help="Fetch JPL Horizons RA/Dec for the top N ranked objects (default: 25).",
    )
    parser.add_argument(
        "--ephemeris-date",
        default="",
        help="UTC date for ephemerides as YYYY-MM-DD; defaults to current UTC date.",
    )
    parser.add_argument(
        "--horizons-center",
        default="500@399",
        help="Horizons observer center, default geocentric Earth (500@399).",
    )
    parser.add_argument("--disable-ephemerides", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("astronomy/distant_reservoir_runs"))
    return parser.parse_args()


def sbdb_query(params: Dict[str, object], timeout_sec: float) -> pd.DataFrame:
    query_params = {
        "fields": ",".join(OUTPUT_FIELDS),
        "full-prec": "true",
        **params,
    }
    response = requests.get(SBDB_QUERY_URL, params=query_params, timeout=timeout_sec)
    response.raise_for_status()
    payload = response.json()
    fields = payload.get("fields", [])
    rows = payload.get("data", [])
    if not fields or not rows:
        return pd.DataFrame(columns=OUTPUT_FIELDS)
    return pd.DataFrame(rows, columns=fields)


def reservoir_queries(reservoir: str, limit: int) -> List[Tuple[str, Dict[str, object]]]:
    queries: List[Tuple[str, Dict[str, object]]] = []
    if reservoir in {"all", "kuiper"}:
        queries.append(
            (
                "kuiper",
                {
                    "sb-kind": "a",
                    "sb-class": "TNO",
                    "sort": "-q,-a",
                    "limit": limit,
                },
            )
        )
    if reservoir in {"all", "centaur"}:
        queries.append(
            (
                "centaur",
                {
                    "sb-class": "CEN",
                    "sort": "-q,-a",
                    "limit": limit,
                },
            )
        )
    if reservoir in {"all", "oort"}:
        cdata = json.dumps(
            {
                "OR": [
                    "a|GT|100",
                    "ad|GT|100",
                    "e|GE|0.98",
                ]
            },
            separators=(",", ":"),
        )
        queries.append(
            (
                "oort",
                {
                    "sb-kind": "c",
                    "sb-class": "HTC,PAR,HYP,COM",
                    "sb-xfrag": "true",
                    "sb-cdata": cdata,
                    "sort": "-q,-a",
                    "limit": limit,
                },
            )
        )
    return queries


def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def clip01(series: pd.Series) -> pd.Series:
    return series.clip(lower=0.0, upper=1.0)


def log_score(series: pd.Series, scale: float) -> pd.Series:
    numeric = to_number(series).fillna(0.0).clip(lower=0.0)
    return clip01(np.log1p(numeric) / np.log1p(scale))


def add_scores(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    out = frame.copy()
    for column in ["e", "a", "q", "i", "per_y", "ad", "condition_code", "data_arc", "n_obs_used", "H", "M1", "K1"]:
        if column in out.columns:
            out[column] = to_number(out[column])

    object_class = out["class"].astype(str)
    kind = out["kind"].astype(str)
    is_tno = object_class.eq("TNO")
    is_centaur = object_class.eq("CEN")
    is_oort_like = (
        kind.str.startswith("c")
        & (
            object_class.isin(["PAR", "HYP"])
            | (out["a"].fillna(0.0) >= 100.0)
            | (out["ad"].fillna(0.0) >= 100.0)
            | (out["e"].fillna(0.0) >= 0.98)
        )
    )

    out["reservoir_classification"] = "other_distant_object"
    out.loc[is_tno, "reservoir_classification"] = "kuiper_belt_tno"
    out.loc[is_centaur, "reservoir_classification"] = "centaur_transition_object"
    out.loc[is_oort_like, "reservoir_classification"] = "oort_cloud_like_comet"

    tno_distance_score = clip01((out["q"].fillna(0.0) - 30.1) / 20.0)
    tno_axis_score = clip01((out["a"].fillna(0.0) - 30.1) / 100.0)
    tno_score = clip01((0.60 * tno_distance_score) + (0.40 * tno_axis_score))

    centaur_score = clip01((out["a"].fillna(0.0) - 5.5) / (30.1 - 5.5))

    comet_a_score = log_score(out["a"], 1000.0)
    comet_ad_score = log_score(out["ad"], 5000.0)
    comet_period_score = log_score(out["per_y"], 10000.0)
    comet_e_score = clip01((out["e"].fillna(0.0) - 0.90) / 0.10)
    comet_class_bonus = object_class.isin(["PAR", "HYP"]).astype(float)
    oort_score = clip01(
        0.30 * comet_a_score
        + 0.25 * comet_ad_score
        + 0.20 * comet_period_score
        + 0.15 * comet_e_score
        + 0.10 * comet_class_bonus
    )

    condition_raw = out["condition_code"]
    condition = condition_raw.fillna(4.5)
    orbit_quality = clip01(1.0 - (condition / 9.0))
    support_score = clip01(
        0.55 * log_score(out["data_arc"], 3650.0)
        + 0.45 * log_score(out["n_obs_used"], 1000.0)
    )

    out["reservoir_signal_score"] = 0.0
    out.loc[is_tno, "reservoir_signal_score"] = tno_score[is_tno]
    out.loc[is_centaur, "reservoir_signal_score"] = centaur_score[is_centaur]
    out.loc[is_oort_like, "reservoir_signal_score"] = oort_score[is_oort_like]

    out["orbit_quality_score"] = orbit_quality
    out["observation_support_score"] = support_score
    out["reservoir_score"] = clip01(
        0.65 * out["reservoir_signal_score"]
        + 0.25 * out["orbit_quality_score"]
        + 0.10 * out["observation_support_score"]
    )

    out["review_note"] = ""
    out.loc[is_tno, "review_note"] = "Known TNO/Kuiper Belt object; useful for distant-object targeting."
    out.loc[is_centaur, "review_note"] = "Centaur object; transition population between Kuiper Belt and inner Solar System."
    out.loc[is_oort_like, "review_note"] = "Known long-period/parabolic/hyperbolic comet; Oort-cloud-like candidate."
    out.loc[condition_raw.notna() & (condition_raw >= 7), "review_note"] += " Orbit uncertainty is high."

    return out.sort_values("reservoir_score", ascending=False).reset_index(drop=True)


def ephemeris_start_date(date_text: str) -> str:
    if not date_text:
        return datetime.now(timezone.utc).date().isoformat()
    try:
        return datetime.fromisoformat(date_text).date().isoformat()
    except ValueError as exc:
        raise ValueError("--ephemeris-date must be formatted as YYYY-MM-DD") from exc


def ephemeris_stop_date(start_date: str) -> str:
    parsed = datetime.fromisoformat(start_date).date()
    return (parsed + timedelta(days=1)).isoformat()


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "--", "masked"}:
        return ""
    return text


def safe_float(value: object) -> float:
    text = clean_text(value)
    if not text:
        return np.nan
    try:
        return float(text)
    except Exception:
        return np.nan


def ephemeris_value(row: object, column: str, default: object = np.nan) -> object:
    if column not in row.colnames:
        return default
    value = row[column]
    text = clean_text(value)
    if not text:
        return default
    return value


def ephemeris_number(row: object, column: str) -> float:
    return safe_float(ephemeris_value(row, column, np.nan))


def horizons_identifiers(row: pd.Series) -> List[str]:
    pdes = clean_text(row.get("pdes", ""))
    prefix = clean_text(row.get("prefix", ""))
    full_name = clean_text(row.get("full_name", ""))
    spkid = clean_text(row.get("spkid", ""))

    identifiers: List[str] = []
    if pdes:
        identifiers.append(pdes)
    if prefix and pdes:
        identifiers.append(f"{prefix}/{pdes}")
    if full_name:
        identifiers.append(full_name)
    if spkid:
        identifiers.append(spkid)

    unique: List[str] = []
    for identifier in identifiers:
        if identifier not in unique:
            unique.append(identifier)
    return unique


def query_horizons_ephemeris(
    catalog_row: pd.Series,
    start_date: str,
    center: str,
) -> Dict[str, object]:
    if Horizons is None:
        raise RuntimeError("astroquery is unavailable; install astronomy/requirements.txt")

    stop_date = ephemeris_stop_date(start_date)
    errors: List[str] = []
    for identifier in horizons_identifiers(catalog_row):
        try:
            ephemerides = Horizons(
                id=identifier,
                id_type="smallbody",
                location=center,
                epochs={"start": start_date, "stop": stop_date, "step": "1d"},
            ).ephemerides()
        except Exception as exc:
            errors.append(f"{identifier}: {exc}")
            continue

        if len(ephemerides) == 0:
            errors.append(f"{identifier}: no ephemeris rows")
            continue

        row = ephemerides[0]
        visual_mag = ephemeris_number(row, "V")
        mag_column = "V"
        if not np.isfinite(visual_mag):
            visual_mag = ephemeris_number(row, "Tmag")
            mag_column = "Tmag"
        if not np.isfinite(visual_mag):
            visual_mag = ephemeris_number(row, "Nmag")
            mag_column = "Nmag"

        return {
            "spkid": clean_text(catalog_row.get("spkid", "")),
            "horizons_query_id": identifier,
            "horizons_targetname": clean_text(ephemeris_value(row, "targetname", "")),
            "ephemeris_datetime": clean_text(ephemeris_value(row, "datetime_str", "")),
            "ephemeris_center": center,
            "ra_deg": ephemeris_number(row, "RA"),
            "dec_deg": ephemeris_number(row, "DEC"),
            "ra_app_deg": ephemeris_number(row, "RA_app"),
            "dec_app_deg": ephemeris_number(row, "DEC_app"),
            "ra_rate_arcsec_per_hour": ephemeris_number(row, "RA_rate"),
            "dec_rate_arcsec_per_hour": ephemeris_number(row, "DEC_rate"),
            "visual_mag": visual_mag,
            "visual_mag_source": mag_column if np.isfinite(visual_mag) else "",
            "heliocentric_distance_au": ephemeris_number(row, "r"),
            "observer_distance_au": ephemeris_number(row, "delta"),
            "solar_elongation_deg": ephemeris_number(row, "elong"),
            "phase_angle_deg": ephemeris_number(row, "alpha"),
            "constellation": clean_text(ephemeris_value(row, "constellation", "")),
            "solar_presence": clean_text(ephemeris_value(row, "solar_presence", "")),
            "lunar_presence": clean_text(ephemeris_value(row, "lunar_presence", "")),
            "horizons_error": "",
        }

    return {
        "spkid": clean_text(catalog_row.get("spkid", "")),
        "horizons_query_id": "",
        "horizons_targetname": "",
        "ephemeris_datetime": "",
        "ephemeris_center": center,
        "ra_deg": np.nan,
        "dec_deg": np.nan,
        "ra_app_deg": np.nan,
        "dec_app_deg": np.nan,
        "ra_rate_arcsec_per_hour": np.nan,
        "dec_rate_arcsec_per_hour": np.nan,
        "visual_mag": np.nan,
        "visual_mag_source": "",
        "heliocentric_distance_au": np.nan,
        "observer_distance_au": np.nan,
        "solar_elongation_deg": np.nan,
        "phase_angle_deg": np.nan,
        "constellation": "",
        "solar_presence": "",
        "lunar_presence": "",
        "horizons_error": " | ".join(errors[:3]),
    }


def fetch_ephemerides(
    ranked: pd.DataFrame,
    top_n: int,
    start_date: str,
    center: str,
    warnings: List[str],
) -> pd.DataFrame:
    if ranked.empty or top_n <= 0:
        return pd.DataFrame()
    if Horizons is None:
        warnings.append("Horizons ephemerides skipped: astroquery is unavailable.")
        return pd.DataFrame()

    rows: List[Dict[str, object]] = []
    for _, row in ranked.head(top_n).iterrows():
        try:
            rows.append(query_horizons_ephemeris(row, start_date, center))
        except Exception as exc:
            rows.append(
                {
                    "spkid": clean_text(row.get("spkid", "")),
                    "horizons_query_id": "",
                    "horizons_targetname": "",
                    "ephemeris_datetime": "",
                    "ephemeris_center": center,
                    "ra_deg": np.nan,
                    "dec_deg": np.nan,
                    "ra_app_deg": np.nan,
                    "dec_app_deg": np.nan,
                    "ra_rate_arcsec_per_hour": np.nan,
                    "dec_rate_arcsec_per_hour": np.nan,
                    "visual_mag": np.nan,
                    "visual_mag_source": "",
                    "heliocentric_distance_au": np.nan,
                    "observer_distance_au": np.nan,
                    "solar_elongation_deg": np.nan,
                    "phase_angle_deg": np.nan,
                    "constellation": "",
                    "solar_presence": "",
                    "lunar_presence": "",
                    "horizons_error": str(exc),
                }
            )
    return pd.DataFrame(rows)


def run(args: argparse.Namespace) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.output_dir / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    frames: List[pd.DataFrame] = []
    warnings: List[str] = []
    for label, params in reservoir_queries(args.reservoir, args.limit):
        try:
            frame = sbdb_query(params, args.timeout_sec)
        except Exception as exc:
            warnings.append(f"{label}: {exc}")
            continue
        frame["query_reservoir"] = label
        frames.append(frame)

    raw = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=OUTPUT_FIELDS)
    if not raw.empty:
        raw = raw.drop_duplicates("spkid", keep="first")
    raw.to_csv(run_dir / "sbdb_raw.csv", index=False)

    ranked = add_scores(raw)
    if "spkid" in ranked.columns:
        ranked["spkid"] = ranked["spkid"].map(clean_text)
    ephemeris_date = ephemeris_start_date(args.ephemeris_date)
    ephemerides = pd.DataFrame()
    if not args.disable_ephemerides:
        ephemerides = fetch_ephemerides(
            ranked=ranked,
            top_n=args.ephemeris_top,
            start_date=ephemeris_date,
            center=args.horizons_center,
            warnings=warnings,
        )
    ephemerides.to_csv(run_dir / "horizons_ephemerides.csv", index=False)

    ranked_with_ephemerides = ranked
    if not ephemerides.empty:
        ephemerides["spkid"] = ephemerides["spkid"].map(clean_text)
        ranked_with_ephemerides = ranked.merge(ephemerides, on="spkid", how="left")

    ranked_with_ephemerides.to_csv(run_dir / "distant_reservoir_ranked.csv", index=False)
    ranked_with_ephemerides[ranked_with_ephemerides["reservoir_classification"].eq("kuiper_belt_tno")].to_csv(
        run_dir / "kuiper_belt_objects.csv",
        index=False,
    )
    ranked_with_ephemerides[ranked_with_ephemerides["reservoir_classification"].eq("oort_cloud_like_comet")].to_csv(
        run_dir / "oort_cloud_like_comets.csv",
        index=False,
    )
    ranked_with_ephemerides[ranked_with_ephemerides["reservoir_classification"].eq("centaur_transition_object")].to_csv(
        run_dir / "centaur_objects.csv",
        index=False,
    )

    summary = {
        "raw_rows": int(len(raw)),
        "ranked_rows": int(len(ranked)),
        "kuiper_belt_tno": int((ranked.get("reservoir_classification") == "kuiper_belt_tno").sum()) if not ranked.empty else 0,
        "centaur_transition_object": int((ranked.get("reservoir_classification") == "centaur_transition_object").sum()) if not ranked.empty else 0,
        "oort_cloud_like_comet": int((ranked.get("reservoir_classification") == "oort_cloud_like_comet").sum()) if not ranked.empty else 0,
        "ephemeris_date_utc": ephemeris_date,
        "ephemeris_center": args.horizons_center,
        "ephemeris_rows": int(len(ephemerides)),
        "ephemeris_successes": int((ephemerides.get("horizons_error", pd.Series(dtype=str)).fillna("") == "").sum()) if not ephemerides.empty else 0,
        "warnings": warnings,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return run_dir


def main() -> None:
    args = parse_args()
    try:
        run_dir = run(args)
    except Exception as exc:
        print(f"Distant reservoir catalog failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("Distant reservoir catalog complete.")
    print(f"Output directory: {run_dir}")
    print(f"Ranked objects: {run_dir / 'distant_reservoir_ranked.csv'}")
    print(f"Oort-like comets: {run_dir / 'oort_cloud_like_comets.csv'}")
    print(f"Kuiper Belt/TNOs: {run_dir / 'kuiper_belt_objects.csv'}")


if __name__ == "__main__":
    main()
