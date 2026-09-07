# Archived historical source: legacy TNS draft builder

This file preserves the retired implementation for provenance and migration
review. It is intentionally Markdown, not an executable Python module. The
implementation predates current-version IRIS candidate binding, independent
review enforcement, and `reporting_preflight`; it must not be restored or used
to prepare a report.

```python
#!/usr/bin/env python3
"""
Build a TNS submission draft package for a verified candidate.

Outputs:
- Markdown report with suggested TNS fields
- JSON draft payload (human-editable structure, not direct API payload)
- Recent photometry CSV excerpt

Bulk mode (--bulk --candidates ID[:AT_TYPE] ...):
- Single multi-object at_report JSON in the TNS bulk-report API format,
  attributed to a reporting group (default: I Spy, group 204)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from alerce.core import Alerce
from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.time import Time


@dataclass
class CandidateContext:
    source_id: str
    ra: float
    dec: float
    decision: str
    skybot_match: bool
    tns_match: bool
    tns_checked: bool
    tns_query_ok: bool
    rank_score: float
    classification: str


# TNS API value-table IDs, verified against https://www.wis-tns.org/api/get/values on 2026-07-10.
TNS_GROUP_ID_I_SPY = 204
TNS_DATA_SOURCE_ID_ZTF = 48
TNS_INSTRUMENT_ID_ZTF_CAM = 196
TNS_FILTER_IDS = {1: 110, 2: 111, 3: 112}  # fid -> g-ZTF, r-ZTF, i-ZTF
TNS_FLUX_UNITS_ABMAG = 1
TNS_AT_TYPES = {"Other": 0, "PSN": 1, "PNV": 2, "AGN": 3, "NUC": 4, "FRB": 5}
ZTF_EXPTIME_SEC = "30"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TNS report draft files for a candidate.")
    parser.add_argument("--candidate-id", help="Candidate/source ID (e.g., ZTF26aascgfc)")
    parser.add_argument("--bulk", action="store_true", help="Build a multi-object at_report JSON for the TNS bulk-report API")
    parser.add_argument(
        "--candidates",
        nargs="+",
        default=[],
        metavar="ID[:AT_TYPE]",
        help="Bulk-mode candidates, e.g. ZTF26abbkkey:PSN ZTF26abboood:NUC (AT_TYPE defaults to PSN)",
    )
    parser.add_argument("--group-id", type=int, default=TNS_GROUP_ID_I_SPY, help="TNS reporting group ID (default: I Spy, 204)")
    parser.add_argument("--data-source-id", type=int, default=TNS_DATA_SOURCE_ID_ZTF, help="TNS discovery data source group ID (default: ZTF, 48)")
    parser.add_argument(
        "--verification-csv",
        type=Path,
        default=Path("astronomy/verification/final_tns_checked_20260414/verification_report.csv"),
        help="Path to verification_report.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("astronomy/reports"),
        help="Directory to write report files",
    )
    parser.add_argument("--reporter", default="", help="Reporter name for draft header")
    parser.add_argument("--affiliation", default="", help="Affiliation for draft header")
    parser.add_argument(
        "--instrument",
        default="ZTF (brokered via ALeRCE)",
        help="Discovery instrument/survey label for draft",
    )
    parser.add_argument(
        "--photometry-points",
        type=int,
        default=20,
        help="How many most-recent detections to include in photometry CSV",
    )
    return parser.parse_args()


def as_float(value: object, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return default


def load_context(verification_csv: Path, candidate_id: str) -> CandidateContext:
    df = pd.read_csv(verification_csv)
    row = df[df["source_id"] == candidate_id]
    if row.empty:
        raise ValueError(f"Candidate {candidate_id} not found in {verification_csv}")
    r = row.iloc[0]
    return CandidateContext(
        source_id=str(r["source_id"]),
        ra=as_float(r["ra"]),
        dec=as_float(r["dec"]),
        decision=str(r.get("decision", "")),
        skybot_match=as_bool(r.get("skybot_match", False)),
        tns_match=as_bool(r.get("tns_match", False)),
        tns_checked=as_bool(r.get("tns_checked", False)),
        tns_query_ok=as_bool(r.get("tns_query_ok", False)),
        rank_score=as_float(r.get("rank_score", 0.0)),
        classification=str(r.get("classification", "")),
    )


def fid_to_filter(fid: object) -> str:
    try:
        i = int(fid)
    except Exception:
        return str(fid)
    return {1: "g", 2: "r", 3: "i"}.get(i, str(i))


def fetch_alerce_series(candidate_id: str) -> Dict[str, object]:
    client = Alerce()
    obj = client.query_object(candidate_id, format="json")
    lc = client.query_lightcurve(candidate_id, format="json")
    det = pd.DataFrame(lc.get("detections", []))
    ndet = pd.DataFrame(lc.get("non_detections", []))
    if not det.empty:
        det = det.sort_values("mjd").reset_index(drop=True)
        det["filter_name"] = det["fid"].apply(fid_to_filter) if "fid" in det.columns else "unknown"
    if not ndet.empty:
        ndet = ndet.sort_values("mjd").reset_index(drop=True)
    return {"object": obj, "detections": det, "non_detections": ndet}


def mjd_to_iso(mjd_value: float) -> str:
    try:
        return Time(float(mjd_value), format="mjd", scale="utc").isot
    except Exception:
        return ""


def build_markdown(
    ctx: CandidateContext,
    obj: Dict[str, object],
    det: pd.DataFrame,
    ndet: pd.DataFrame,
    reporter: str,
    affiliation: str,
    instrument: str,
) -> str:
    first_mjd = as_float(obj.get("firstmjd"), float(det["mjd"].min()) if not det.empty else 0.0)
    last_mjd = as_float(obj.get("lastmjd"), float(det["mjd"].max()) if not det.empty else 0.0)
    first_iso = mjd_to_iso(first_mjd)
    last_iso = mjd_to_iso(last_mjd)

    peak_mag = None
    peak_mjd = None
    peak_filter = ""
    if not det.empty and "magpsf" in det.columns:
        i = int(det["magpsf"].astype(float).idxmin())
        peak_mag = as_float(det.loc[i, "magpsf"])
        peak_mjd = as_float(det.loc[i, "mjd"])
        peak_filter = str(det.loc[i, "filter_name"])

    pre_nd = pd.DataFrame()
    if not ndet.empty and not det.empty:
        pre_nd = ndet[ndet["mjd"] < det["mjd"].min()]

    coord = SkyCoord(ra=ctx.ra * u.deg, dec=ctx.dec * u.deg, frame="icrs")
    ra_hms = coord.ra.to_string(unit=u.hour, sep=":", precision=3, pad=True)
    dec_dms = coord.dec.to_string(sep=":", precision=2, alwayssign=True, pad=True)

    lines = [
        f"# TNS Draft Report: {ctx.source_id}",
        "",
        "## Candidate",
        f"- Source ID: `{ctx.source_id}`",
        f"- RA/Dec (deg): `{ctx.ra:.9f}`, `{ctx.dec:.9f}`",
        f"- RA/Dec (sexagesimal): `{ra_hms}`, `{dec_dms}`",
        f"- Internal pipeline class: `{ctx.classification}`",
        f"- Rank score: `{ctx.rank_score:.3f}`",
        "",
        "## Verification Status",
        f"- SkyBoT moving-object match: `{ctx.skybot_match}`",
        f"- TNS checked: `{ctx.tns_checked}`",
        f"- TNS query OK: `{ctx.tns_query_ok}`",
        f"- TNS matched known object: `{ctx.tns_match}`",
        f"- Decision: `{ctx.decision}`",
        "",
        "## Discovery/Lightcurve Summary",
        f"- Instrument/survey: `{instrument}`",
        f"- First detection: `MJD {first_mjd:.6f}` (`{first_iso}` UTC)",
        f"- Last detection: `MJD {last_mjd:.6f}` (`{last_iso}` UTC)",
        f"- Number of detections: `{len(det)}`",
        f"- Number of pre-detection non-detections: `{len(pre_nd)}`",
    ]
    if not pre_nd.empty and "diffmaglim" in pre_nd.columns:
        lines.append(f"- Best pre-detection limiting magnitude: `{pre_nd['diffmaglim'].max():.3f}`")
    if peak_mag is not None and peak_mjd is not None:
        lines.append(
            f"- Brightest detection: `mag {peak_mag:.3f}` in `{peak_filter}` at `MJD {peak_mjd:.6f}` (`{mjd_to_iso(peak_mjd)}` UTC)"
        )

    lines.extend(
        [
            "",
            "## Suggested TNS Form Entries",
            f"- Reporter: `{reporter or '<fill reporter name>'}`",
            f"- Affiliation: `{affiliation or '<fill affiliation>'}`",
            f"- Discovery internal name: `{ctx.source_id}`",
            "- Discovery type: `AT`",
            f"- Discovery date (UTC): `{first_iso}`",
            f"- Discovery RA/Dec (J2000): `{ctx.ra:.9f}`, `{ctx.dec:.9f}`",
            "- Discovery mag/filter: use photometry CSV file generated in this report package.",
            "",
            "## Notes",
            "- This is an auto-generated draft for manual review before TNS submission.",
            "- Confirm timestamps, magnitudes, and instrument attribution before submitting.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_json_draft(
    ctx: CandidateContext,
    obj: Dict[str, object],
    det: pd.DataFrame,
    reporter: str,
    affiliation: str,
    instrument: str,
) -> Dict[str, object]:
    first_mjd = as_float(obj.get("firstmjd"), float(det["mjd"].min()) if not det.empty else 0.0)
    first_iso = mjd_to_iso(first_mjd)
    payload: Dict[str, object] = {
        "draft_type": "tns_manual_submission_draft",
        "candidate_id": ctx.source_id,
        "reporter": reporter,
        "affiliation": affiliation,
        "instrument": instrument,
        "verification": {
            "decision": ctx.decision,
            "skybot_match": ctx.skybot_match,
            "tns_checked": ctx.tns_checked,
            "tns_query_ok": ctx.tns_query_ok,
            "tns_match": ctx.tns_match,
        },
        "tns_form_suggestion": {
            "object_type": "AT",
            "internal_name": ctx.source_id,
            "ra_deg_j2000": ctx.ra,
            "dec_deg_j2000": ctx.dec,
            "discovery_datetime_utc": first_iso,
            "discovery_filter": "",
            "discovery_magnitude": "",
            "remarks": "Automated draft from local verification pipeline. Review manually before submission.",
        },
    }
    return payload


def mjd_to_tns_datetime(mjd_value: float) -> str:
    iso = mjd_to_iso(mjd_value)
    return iso.replace("T", " ")[:19] if iso else ""


def parse_bulk_candidates(specs: List[str]) -> List[Tuple[str, str]]:
    parsed = []
    for spec in specs:
        candidate_id, _, at_type = spec.partition(":")
        at_type = at_type or "PSN"
        if at_type not in TNS_AT_TYPES:
            raise ValueError(f"Unknown AT type {at_type!r} in {spec!r}; choose from {sorted(TNS_AT_TYPES)}")
        parsed.append((candidate_id, at_type))
    return parsed


def photometry_entry(row: pd.Series) -> Dict[str, object]:
    return {
        "obsdate": mjd_to_tns_datetime(as_float(row["mjd"])),
        "flux": f"{as_float(row['magpsf']):.3f}",
        "flux_error": f"{as_float(row['sigmapsf']):.3f}",
        "limiting_flux": "",
        "flux_units": str(TNS_FLUX_UNITS_ABMAG),
        "filter_value": str(TNS_FILTER_IDS.get(int(row["fid"]), "")),
        "instrument_value": str(TNS_INSTRUMENT_ID_ZTF_CAM),
        "exptime": ZTF_EXPTIME_SEC,
        "observer": "Robot",
        "comments": "",
    }


def build_at_report_object(
    ctx: CandidateContext,
    obj: Dict[str, object],
    det: pd.DataFrame,
    ndet: pd.DataFrame,
    at_type: str,
    reporter: str,
    group_id: int,
    data_source_id: int,
) -> Dict[str, object]:
    first_mjd = as_float(obj.get("firstmjd"), float(det["mjd"].min()) if not det.empty else 0.0)

    # Discovery photometry plus the brightest and latest epochs (deduplicated, time-ordered).
    picks = pd.DataFrame()
    if not det.empty and "magpsf" in det.columns:
        idx = {int(det["mjd"].astype(float).idxmin()), int(det["magpsf"].astype(float).idxmin()), int(det["mjd"].astype(float).idxmax())}
        picks = det.loc[sorted(idx)].sort_values("mjd")
    photometry = {str(i): photometry_entry(row) for i, (_, row) in enumerate(picks.iterrows())}

    # TNS requires either a last pre-discovery non-detection or an archival remark.
    non_detection: Dict[str, object]
    pre_nd = pd.DataFrame()
    if not ndet.empty and "diffmaglim" in ndet.columns:
        pre_nd = ndet[ndet["mjd"] < first_mjd]
    if not pre_nd.empty:
        last_nd = pre_nd.sort_values("mjd").iloc[-1]
        non_detection = {
            "obsdate": mjd_to_tns_datetime(as_float(last_nd["mjd"])),
            "limiting_flux": f"{as_float(last_nd['diffmaglim']):.3f}",
            "flux_units": str(TNS_FLUX_UNITS_ABMAG),
            "filter_value": str(TNS_FILTER_IDS.get(int(last_nd["fid"]), "")),
            "instrument_value": str(TNS_INSTRUMENT_ID_ZTF_CAM),
            "exptime": ZTF_EXPTIME_SEC,
            "observer": "Robot",
            "comments": "Last ZTF non-detection before discovery",
        }
    else:
        non_detection = {"archiveid": "0", "archival_remarks": "ZTF"}

    remarks = "Detected in ZTF public alert stream (brokered via ALeRCE); candidate vetting via light-curve, SkyBoT, and TNS cross-checks."
    if at_type == "NUC":
        remarks += " Position consistent with host galaxy nucleus; possible nuclear transient."

    return {
        "ra": {"value": f"{ctx.ra:.6f}", "error": "", "units": "arcsec"},
        "dec": {"value": f"{ctx.dec:.6f}", "error": "", "units": "arcsec"},
        "reporting_group_id": str(group_id),
        "discovery_data_source_id": str(data_source_id),
        "reporter": reporter,
        "discovery_datetime": mjd_to_tns_datetime(first_mjd),
        "at_type": str(TNS_AT_TYPES[at_type]),
        "host_name": "",
        "host_redshift": "",
        "transient_redshift": "",
        "internal_name": ctx.source_id,
        "remarks": remarks,
        "proprietary_period_groups": [str(group_id)],
        "proprietary_period": {"proprietary_period_value": "0", "proprietary_period_units": "days"},
        "non_detection": non_detection,
        "photometry": {"photometry_group": photometry},
    }


def run_bulk(args: argparse.Namespace) -> None:
    candidates = parse_bulk_candidates(args.candidates)
    if not candidates:
        raise SystemExit("--bulk requires --candidates ID[:AT_TYPE] ...")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.output_dir / f"bulk_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    at_report: Dict[str, object] = {}
    summary_lines = [f"# TNS Bulk Report Draft ({stamp})", "", f"- Reporting group ID: `{args.group_id}`", f"- Reporter: `{args.reporter or '<fill reporter names>'}`", ""]
    for i, (candidate_id, at_type) in enumerate(candidates):
        ctx = load_context(args.verification_csv, candidate_id)
        series = fetch_alerce_series(candidate_id)
        det: pd.DataFrame = series["detections"]  # type: ignore[assignment]
        ndet: pd.DataFrame = series["non_detections"]  # type: ignore[assignment]
        at_report[str(i)] = build_at_report_object(
            ctx=ctx,
            obj=series["object"],  # type: ignore[arg-type]
            det=det,
            ndet=ndet,
            at_type=at_type,
            reporter=args.reporter,
            group_id=args.group_id,
            data_source_id=args.data_source_id,
        )
        summary_lines.append(f"- `{candidate_id}` as `{at_type}`: {len(det)} detections, decision `{ctx.decision}`, tns_match `{ctx.tns_match}`")

    json_path = out_dir / "at_report_bulk.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"at_report": at_report}, f, indent=2)

    summary_lines.extend(
        [
            "",
            "Review reporter strings, AT types, and remarks in the JSON before submission.",
            "Submit via the TNS bulk-report API (data: api_key + the JSON) or paste into the bulk-report web form.",
        ]
    )
    (out_dir / "bulk_report_summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print("TNS bulk report draft created.")
    print(f"Objects: {', '.join(f'{cid} ({t})' for cid, t in candidates)}")
    print(f"JSON payload: {json_path}")
    print(f"Summary: {out_dir / 'bulk_report_summary.md'}")


def main() -> None:
    args = parse_args()
    if args.bulk:
        run_bulk(args)
        return
    if not args.candidate_id:
        raise SystemExit("--candidate-id is required (or use --bulk with --candidates)")
    ctx = load_context(args.verification_csv, args.candidate_id)
    series = fetch_alerce_series(args.candidate_id)
    obj = series["object"]
    det: pd.DataFrame = series["detections"]  # type: ignore[assignment]
    ndet: pd.DataFrame = series["non_detections"]  # type: ignore[assignment]

    out_dir = args.output_dir / args.candidate_id
    out_dir.mkdir(parents=True, exist_ok=True)

    phot_csv = out_dir / "photometry_recent.csv"
    if not det.empty:
        keep_cols = [c for c in ["mjd", "fid", "filter_name", "magpsf", "sigmapsf", "diffmaglim"] if c in det.columns]
        det.tail(args.photometry_points)[keep_cols].to_csv(phot_csv, index=False)
    else:
        pd.DataFrame().to_csv(phot_csv, index=False)

    md_text = build_markdown(
        ctx=ctx,
        obj=obj,  # type: ignore[arg-type]
        det=det,
        ndet=ndet,
        reporter=args.reporter,
        affiliation=args.affiliation,
        instrument=args.instrument,
    )
    md_path = out_dir / "tns_report_draft.md"
    md_path.write_text(md_text, encoding="utf-8")

    json_draft = build_json_draft(
        ctx=ctx,
        obj=obj,  # type: ignore[arg-type]
        det=det,
        reporter=args.reporter,
        affiliation=args.affiliation,
        instrument=args.instrument,
    )
    json_path = out_dir / "tns_report_draft.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_draft, f, indent=2)

    print("TNS report draft package created.")
    print(f"Candidate: {args.candidate_id}")
    print(f"Output directory: {out_dir}")
    print(f"Markdown draft: {md_path}")
    print(f"JSON draft: {json_path}")
    print(f"Photometry CSV: {phot_csv}")


if __name__ == "__main__":
    main()
```
