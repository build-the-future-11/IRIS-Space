#!/usr/bin/env python3
"""
Verify transient candidates and keep likely new objects only.

Checks performed:
1) Moving-object rejection via SkyBoT
2) Live classifier context via ALeRCE probabilities
3) Optional known-object check via TNS API (requires bot credentials)
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from alerce.core import Alerce
from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u
from astroquery.imcce import Skybot

TNS_SEARCH_URL = "https://www.wis-tns.org/api/get/search"


@dataclass
class TnsConfig:
    api_key: str
    bot_id: str
    bot_name: str
    timeout_sec: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify ranked transient candidates.")
    parser.add_argument(
        "--ranked-csv",
        type=Path,
        required=True,
        help="ranked_candidates.csv from optical_transient_pipeline.py",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("astronomy/verification"),
    )
    parser.add_argument(
        "--only-new-class",
        action="store_true",
        help="Only verify rows already labeled as new_transient_candidate.",
    )
    parser.add_argument("--skybot-radius-arcsec", type=float, default=10.0)
    parser.add_argument("--tns-radius-arcsec", type=float, default=3.0)
    parser.add_argument("--timeout-sec", type=float, default=30.0)
    parser.add_argument("--disable-skybot", action="store_true")
    parser.add_argument("--disable-alerce", action="store_true")
    parser.add_argument("--disable-tns", action="store_true")
    parser.add_argument("--tns-api-key", default=os.getenv("TNS_API_KEY", ""))
    parser.add_argument("--tns-bot-id", default=os.getenv("TNS_BOT_ID", ""))
    parser.add_argument("--tns-bot-name", default=os.getenv("TNS_BOT_NAME", ""))
    return parser.parse_args()


def maybe_tns_config(args: argparse.Namespace) -> Optional[TnsConfig]:
    if args.disable_tns:
        return None
    if not (args.tns_api_key and args.tns_bot_id and args.tns_bot_name):
        return None
    return TnsConfig(
        api_key=args.tns_api_key,
        bot_id=str(args.tns_bot_id),
        bot_name=str(args.tns_bot_name),
        timeout_sec=float(args.timeout_sec),
    )


def skybot_check(ra: float, dec: float, mjd: float, radius_arcsec: float) -> Tuple[bool, int, str]:
    try:
        field = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame="icrs")
        epoch = Time(mjd, format="mjd")
        result = Skybot.cone_search(field, radius_arcsec * u.arcsec, epoch)
        if result is None or len(result) == 0:
            return False, 0, ""
        name_col = None
        for col in ["Name", "name", "Num", "number"]:
            if col in result.colnames:
                name_col = col
                break
        names = ""
        if name_col:
            names = ",".join([str(x) for x in result[name_col][:10]])
        return True, int(len(result)), names
    except Exception:
        return False, 0, ""


def top_alerce_labels(client: Alerce, oid: str) -> Dict[str, object]:
    result = {
        "alerce_top_transient_class": "",
        "alerce_top_transient_prob": 0.0,
        "alerce_top_stamp_class": "",
        "alerce_top_stamp_prob": 0.0,
        "alerce_prob_error": "",
    }
    try:
        probs = client.query_probabilities(oid, format="pandas")
        if probs is None or len(probs) == 0:
            return result

        transient = probs[probs["classifier_name"].str.contains("transient", case=False, na=False)]
        if len(transient) > 0:
            t = transient.sort_values("probability", ascending=False).iloc[0]
            result["alerce_top_transient_class"] = str(t["class_name"])
            result["alerce_top_transient_prob"] = float(t["probability"])

        stamp = probs[probs["classifier_name"].str.contains("stamp", case=False, na=False)]
        if len(stamp) > 0:
            s = stamp.sort_values("probability", ascending=False).iloc[0]
            result["alerce_top_stamp_class"] = str(s["class_name"])
            result["alerce_top_stamp_prob"] = float(s["probability"])
    except Exception as exc:
        result["alerce_prob_error"] = str(exc)
    return result


def tns_headers(cfg: TnsConfig) -> Dict[str, str]:
    marker = f'tns_marker{{"tns_id":{cfg.bot_id},"type":"bot","name":"{cfg.bot_name}"}}'
    return {"User-Agent": marker}


def parse_tns_search_response(payload: Dict[str, object]) -> Tuple[bool, str, int]:
    data = payload.get("data", {})
    if isinstance(data, list):
        reply = data
    elif isinstance(data, dict):
        raw_reply = data.get("reply")
        if isinstance(raw_reply, list):
            reply = raw_reply
        elif "objname" in data:
            reply = [data]
        else:
            reply = None
    else:
        reply = None

    if not isinstance(reply, list) or len(reply) == 0:
        return False, "", 0

    names: List[str] = []
    for row in reply:
        if not isinstance(row, dict):
            continue
        prefix = str(row.get("prefix", "")).strip()
        objname = str(row.get("objname", "")).strip()
        full = f"{prefix} {objname}".strip()
        if full:
            names.append(full)
        elif objname:
            names.append(objname)
    names = sorted(set(names))
    return len(names) > 0, ",".join(names[:10]), len(names)


def tns_search_internal_name(cfg: TnsConfig, internal_name: str) -> Tuple[bool, str, int, str]:
    payload = {"internal_name": internal_name}
    form = {"api_key": cfg.api_key, "data": json.dumps(payload)}
    try:
        resp = requests.post(
            TNS_SEARCH_URL,
            headers=tns_headers(cfg),
            data=form,
            timeout=cfg.timeout_sec,
        )
        resp.raise_for_status()
        raw = resp.json()
        matched, names, count = parse_tns_search_response(raw)
        return matched, names, count, ""
    except Exception as exc:
        return False, "", 0, str(exc)


def tns_search_cone(cfg: TnsConfig, ra: float, dec: float, radius_arcsec: float) -> Tuple[bool, str, int, str]:
    payload = {"ra": ra, "dec": dec, "radius": radius_arcsec, "units": "arcsec"}
    form = {"api_key": cfg.api_key, "data": json.dumps(payload)}
    try:
        resp = requests.post(
            TNS_SEARCH_URL,
            headers=tns_headers(cfg),
            data=form,
            timeout=cfg.timeout_sec,
        )
        resp.raise_for_status()
        raw = resp.json()
        matched, names, count = parse_tns_search_response(raw)
        return matched, names, count, ""
    except Exception as exc:
        return False, "", 0, str(exc)


def verify(args: argparse.Namespace) -> Dict[str, object]:
    df = pd.read_csv(args.ranked_csv)
    if args.only_new_class:
        df = df[df["classification"] == "new_transient_candidate"].copy()
    if df.empty:
        return {"report": pd.DataFrame(), "likely_new": pd.DataFrame(), "summary": {"checked": 0}}

    tns_cfg = maybe_tns_config(args)
    alerce_client = None if args.disable_alerce else Alerce()

    rows = []
    for _, row in df.iterrows():
        oid = str(row["source_id"])
        ra = float(row["ra"])
        dec = float(row["dec"])
        peak_mjd = float(row["peak_mjd"]) if pd.notna(row.get("peak_mjd")) else float(row.get("mjd_med", 0.0))

        record = row.to_dict()
        record["skybot_match"] = False
        record["skybot_count"] = 0
        record["skybot_names"] = ""
        record["tns_match"] = False
        record["tns_count"] = 0
        record["tns_names"] = ""
        record["tns_error"] = ""
        record["tns_checked"] = bool(tns_cfg is not None)
        record["tns_query_ok"] = False
        record["alerce_checked"] = bool(alerce_client is not None and oid.startswith("ZTF"))
        record["alerce_top_transient_class"] = ""
        record["alerce_top_transient_prob"] = 0.0
        record["alerce_top_stamp_class"] = ""
        record["alerce_top_stamp_prob"] = 0.0
        record["alerce_prob_error"] = ""

        if not args.disable_skybot:
            sky_match, sky_count, sky_names = skybot_check(
                ra=ra, dec=dec, mjd=peak_mjd, radius_arcsec=args.skybot_radius_arcsec
            )
            record["skybot_match"] = sky_match
            record["skybot_count"] = sky_count
            record["skybot_names"] = sky_names

        if alerce_client is not None and oid.startswith("ZTF"):
            info = top_alerce_labels(alerce_client, oid)
            record.update(info)

        if tns_cfg is not None:
            tns_match, tns_names, tns_count, tns_err = tns_search_internal_name(tns_cfg, oid)
            if not tns_match and not tns_err:
                tns_match, tns_names, tns_count, tns_err = tns_search_cone(
                    tns_cfg, ra=ra, dec=dec, radius_arcsec=args.tns_radius_arcsec
                )
            record["tns_match"] = tns_match
            record["tns_names"] = tns_names
            record["tns_count"] = tns_count
            record["tns_error"] = tns_err
            record["tns_query_ok"] = (tns_err == "")

        record["known_or_moving"] = bool(record["skybot_match"] or record["tns_match"])
        if record["skybot_match"]:
            record["decision"] = "reject_moving_object"
        elif record["tns_match"]:
            record["decision"] = "reject_known_tns_object"
        elif record["tns_checked"] and not record["tns_query_ok"]:
            record["decision"] = "needs_tns_check_before_reporting"
        elif not record["tns_checked"]:
            record["decision"] = "needs_tns_check_before_reporting"
        else:
            record["decision"] = "likely_new_candidate"

        rows.append(record)

    report = pd.DataFrame(rows)
    likely_new = report[report["decision"] == "likely_new_candidate"].copy()
    summary = {
        "checked": int(len(report)),
        "likely_new": int(len(likely_new)),
        "rejected_known_tns": int((report["decision"] == "reject_known_tns_object").sum()),
        "rejected_moving": int((report["decision"] == "reject_moving_object").sum()),
        "needs_tns_check": int((report["decision"] == "needs_tns_check_before_reporting").sum()),
        "tns_query_errors": int((report["tns_checked"] & ~report["tns_query_ok"]).sum()),
    }
    return {"report": report, "likely_new": likely_new, "summary": summary}


def write_outputs(output_dir: Path, report: pd.DataFrame, likely_new: pd.DataFrame, summary: Dict[str, int]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report.to_csv(output_dir / "verification_report.csv", index=False)
    likely_new.to_csv(output_dir / "likely_new_only.csv", index=False)
    with open(output_dir / "verification_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


def main() -> None:
    args = parse_args()
    result = verify(args)
    write_outputs(args.output_dir, result["report"], result["likely_new"], result["summary"])

    summary = result["summary"]
    print("Verification complete.")
    print(f"Checked: {summary['checked']}")
    print(f"Likely new: {summary.get('likely_new', 0)}")
    print(f"Rejected known (TNS): {summary.get('rejected_known_tns', 0)}")
    print(f"Rejected moving (SkyBoT): {summary.get('rejected_moving', 0)}")
    print(f"Need TNS check: {summary.get('needs_tns_check', 0)}")
    print(f"Output dir: {args.output_dir}")


if __name__ == "__main__":
    main()
