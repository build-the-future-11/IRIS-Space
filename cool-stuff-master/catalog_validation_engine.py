#!/usr/bin/env python3
"""
Validate transient candidates against stellar and variable-star catalogs.

This is a conservative pre-reporting screen. It is designed to catch cases
where a transient-like alert is actually a known variable star or stellar source
near the candidate position.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
import astropy.units as u

try:
    from astroquery.simbad import Simbad
except Exception:  # pragma: no cover - optional runtime dependency
    Simbad = None

try:
    from astroquery.vizier import Vizier
except Exception:  # pragma: no cover - optional runtime dependency
    Vizier = None


VARIABLE_TOKENS = [
    "v*",
    "var",
    "lpv",
    "lp",
    "mira",
    "sr",
    "puls",
    "cep",
    "rr",
    "ecl",
    "rot",
]

STELLAR_TOKENS = [
    "*",
    "star",
    "stellar",
    "lp",
    "mira",
    "sr",
    "ysovar",
    "eruptive",
]

EXTRAGALACTIC_TOKENS = [
    "galaxy",
    "gal",
    "agn",
    "qso",
    "quasar",
    "seyfert",
    "blazar",
    "host",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crossmatch candidate positions against VSX and SIMBAD before reporting."
    )
    parser.add_argument(
        "--candidates-csv",
        type=Path,
        required=True,
        help="Candidate table with source_id/ra/dec columns.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("astronomy/catalog_validation"),
    )
    parser.add_argument("--radius-arcsec", type=float, default=3.0)
    parser.add_argument("--max-candidates", type=int, default=0, help="0 means all rows.")
    parser.add_argument("--disable-simbad", action="store_true")
    parser.add_argument("--disable-vsx", action="store_true")
    return parser.parse_args()


def find_column(columns: Iterable[str], aliases: Iterable[str]) -> Optional[str]:
    by_lower = {column.lower(): column for column in columns}
    for alias in aliases:
        if alias.lower() in by_lower:
            return by_lower[alias.lower()]
    return None


def required_columns(frame: pd.DataFrame) -> Tuple[str, str, str]:
    source_column = find_column(frame.columns, ["source_id", "oid", "objectid", "id", "candidate_id"])
    ra_column = find_column(frame.columns, ["ra", "meanra", "ra_deg", "ra_deg_j2000"])
    dec_column = find_column(frame.columns, ["dec", "meandec", "dec_deg", "dec_deg_j2000"])
    missing = []
    if source_column is None:
        missing.append("source_id/oid/objectid/id")
    if ra_column is None:
        missing.append("ra/meanra/ra_deg")
    if dec_column is None:
        missing.append("dec/meandec/dec_deg")
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")
    return source_column, ra_column, dec_column


def clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "--", "masked"}:
        return ""
    return text


def first_present(row: object, names: List[str]) -> str:
    for name in names:
        if name in row.colnames:
            text = clean_text(row[name])
            if text:
                return text
    return ""


def row_float(row: object, names: List[str]) -> float:
    text = first_present(row, names)
    if not text:
        return np.nan
    try:
        return float(text)
    except Exception:
        return np.nan


def token_match(text: str, tokens: List[str]) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in tokens)


def simbad_coord_from_row(row: object) -> Optional[SkyCoord]:
    if "RA" not in row.colnames or "DEC" not in row.colnames:
        return None
    try:
        return SkyCoord(clean_text(row["RA"]), clean_text(row["DEC"]), unit=(u.hourangle, u.deg))
    except Exception:
        return None


def query_simbad(coord: SkyCoord, radius_arcsec: float) -> Dict[str, object]:
    result: Dict[str, object] = {
        "simbad_checked": Simbad is not None,
        "simbad_count": 0,
        "simbad_main_id": "",
        "simbad_otype": "",
        "simbad_sep_arcsec": np.nan,
        "simbad_error": "",
    }
    if Simbad is None:
        result["simbad_error"] = "astroquery.simbad unavailable"
        return result

    try:
        custom = Simbad()
        try:
            custom.add_votable_fields("otype")
        except Exception:
            pass
        table = custom.query_region(coord, radius=radius_arcsec * u.arcsec)
    except Exception as exc:
        result["simbad_error"] = str(exc)
        return result

    if table is None or len(table) == 0:
        return result

    result["simbad_count"] = int(len(table))
    best_index = 0
    best_sep = np.nan
    separations: List[float] = []
    for row in table:
        match_coord = simbad_coord_from_row(row)
        separations.append(float(coord.separation(match_coord).arcsec) if match_coord is not None else np.nan)
    finite = [(i, sep) for i, sep in enumerate(separations) if np.isfinite(sep)]
    if finite:
        best_index, best_sep = min(finite, key=lambda item: item[1])

    best = table[best_index]
    result["simbad_main_id"] = first_present(best, ["MAIN_ID", "main_id"])
    result["simbad_otype"] = first_present(best, ["OTYPE", "otype", "OTYPE_V"])
    result["simbad_sep_arcsec"] = best_sep
    return result


def query_vsx(coord: SkyCoord, radius_arcsec: float) -> Dict[str, object]:
    result: Dict[str, object] = {
        "vsx_checked": Vizier is not None,
        "vsx_count": 0,
        "vsx_oid": "",
        "vsx_name": "",
        "vsx_type": "",
        "vsx_period_days": np.nan,
        "vsx_sep_arcsec": np.nan,
        "vsx_error": "",
    }
    if Vizier is None:
        result["vsx_error"] = "astroquery.vizier unavailable"
        return result

    try:
        vizier = Vizier(columns=["*", "+_r"], row_limit=10)
        tables = vizier.query_region(coord, radius=radius_arcsec * u.arcsec, catalog="B/vsx/vsx")
    except Exception as exc:
        result["vsx_error"] = str(exc)
        return result

    if not tables or len(tables[0]) == 0:
        return result

    table = tables[0]
    result["vsx_count"] = int(len(table))
    best_index = 0
    if "_r" in table.colnames:
        try:
            best_index = int(np.nanargmin(np.array(table["_r"], dtype=float)))
        except Exception:
            best_index = 0
    best = table[best_index]
    result["vsx_oid"] = first_present(best, ["OID", "oid"])
    result["vsx_name"] = first_present(best, ["Name", "name"])
    result["vsx_type"] = first_present(best, ["Type", "type"])
    result["vsx_period_days"] = row_float(best, ["Period", "period", "Per"])
    result["vsx_sep_arcsec"] = row_float(best, ["_r"])
    return result


def catalog_decision(record: Dict[str, object]) -> Tuple[str, str]:
    vsx_type = clean_text(record.get("vsx_type", ""))
    simbad_otype = clean_text(record.get("simbad_otype", ""))
    simbad_id = clean_text(record.get("simbad_main_id", ""))
    vsx_name = clean_text(record.get("vsx_name", ""))

    if int(record.get("vsx_count", 0) or 0) > 0:
        label = f"VSX match {vsx_name}".strip()
        if vsx_type:
            label += f" type={vsx_type}"
        return "reject_known_variable", label

    if token_match(simbad_otype, VARIABLE_TOKENS):
        label = f"SIMBAD variable-like match {simbad_id}".strip()
        if simbad_otype:
            label += f" otype={simbad_otype}"
        return "reject_known_variable", label

    if token_match(simbad_otype, STELLAR_TOKENS) and not token_match(simbad_otype, EXTRAGALACTIC_TOKENS):
        label = f"SIMBAD stellar match {simbad_id}".strip()
        if simbad_otype:
            label += f" otype={simbad_otype}"
        return "needs_review_known_stellar_source", label

    if token_match(simbad_otype, EXTRAGALACTIC_TOKENS):
        label = f"SIMBAD extragalactic/host-like match {simbad_id}".strip()
        if simbad_otype:
            label += f" otype={simbad_otype}"
        return "possible_host_or_extragalactic_source", label

    if int(record.get("simbad_count", 0) or 0) > 0:
        label = f"SIMBAD match {simbad_id}".strip()
        if simbad_otype:
            label += f" otype={simbad_otype}"
        return "needs_review_catalog_match", label

    return "pass_catalog_checks", "No VSX/SIMBAD match within radius."


def validate(args: argparse.Namespace) -> Dict[str, object]:
    frame = pd.read_csv(args.candidates_csv)
    source_column, ra_column, dec_column = required_columns(frame)
    if args.max_candidates and args.max_candidates > 0:
        frame = frame.head(args.max_candidates).copy()

    rows: List[Dict[str, object]] = []
    for _, candidate in frame.iterrows():
        source_id = clean_text(candidate[source_column])
        ra = float(candidate[ra_column])
        dec = float(candidate[dec_column])
        coord = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")

        record = candidate.to_dict()
        record["catalog_validation_source_id"] = source_id
        record["catalog_validation_ra"] = ra
        record["catalog_validation_dec"] = dec
        record["catalog_radius_arcsec"] = float(args.radius_arcsec)

        if args.disable_simbad:
            record.update(
                {
                    "simbad_checked": False,
                    "simbad_count": 0,
                    "simbad_main_id": "",
                    "simbad_otype": "",
                    "simbad_sep_arcsec": np.nan,
                    "simbad_error": "disabled",
                }
            )
        else:
            record.update(query_simbad(coord, args.radius_arcsec))

        if args.disable_vsx:
            record.update(
                {
                    "vsx_checked": False,
                    "vsx_count": 0,
                    "vsx_oid": "",
                    "vsx_name": "",
                    "vsx_type": "",
                    "vsx_period_days": np.nan,
                    "vsx_sep_arcsec": np.nan,
                    "vsx_error": "disabled",
                }
            )
        else:
            record.update(query_vsx(coord, args.radius_arcsec))

        decision, reason = catalog_decision(record)
        record["catalog_decision"] = decision
        record["catalog_reason"] = reason
        rows.append(record)

    report = pd.DataFrame(rows)
    rejected = report[report["catalog_decision"].eq("reject_known_variable")].copy()
    review = report[report["catalog_decision"].str.startswith("needs_review", na=False)].copy()
    passed = report[report["catalog_decision"].eq("pass_catalog_checks")].copy()
    summary = {
        "input_rows": int(len(frame)),
        "checked": int(len(report)),
        "rejected_known_variable": int(len(rejected)),
        "needs_review": int(len(review)),
        "passed_catalog_checks": int(len(passed)),
        "possible_host_or_extragalactic_source": int(
            report["catalog_decision"].eq("possible_host_or_extragalactic_source").sum()
        )
        if not report.empty
        else 0,
        "radius_arcsec": float(args.radius_arcsec),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "report": report,
        "rejected": rejected,
        "review": review,
        "passed": passed,
        "summary": summary,
    }


def write_outputs(output_dir: Path, result: Dict[str, object]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report: pd.DataFrame = result["report"]  # type: ignore[assignment]
    rejected: pd.DataFrame = result["rejected"]  # type: ignore[assignment]
    review: pd.DataFrame = result["review"]  # type: ignore[assignment]
    passed: pd.DataFrame = result["passed"]  # type: ignore[assignment]
    summary: Dict[str, object] = result["summary"]  # type: ignore[assignment]

    report.to_csv(output_dir / "catalog_validation_report.csv", index=False)
    rejected.to_csv(output_dir / "catalog_rejected_known_variables.csv", index=False)
    review.to_csv(output_dir / "catalog_needs_review.csv", index=False)
    passed.to_csv(output_dir / "catalog_passed.csv", index=False)
    with open(output_dir / "catalog_validation_summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)


def main() -> None:
    args = parse_args()
    result = validate(args)
    write_outputs(args.output_dir, result)

    summary: Dict[str, object] = result["summary"]  # type: ignore[assignment]
    print("Catalog validation complete.")
    print(f"Checked: {summary['checked']}")
    print(f"Rejected known variables: {summary['rejected_known_variable']}")
    print(f"Needs review: {summary['needs_review']}")
    print(f"Passed catalog checks: {summary['passed_catalog_checks']}")
    print(f"Output dir: {args.output_dir}")


if __name__ == "__main__":
    main()
