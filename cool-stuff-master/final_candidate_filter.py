#!/usr/bin/env python3
"""
Build the final reportable transient shortlist.

This is the last safety gate before any manual TNS/reporting workflow. A
candidate is only marked reportable if:

1) verify_candidates.py marked it likely_new_candidate, which requires a
   successful TNS check with no known match.
2) catalog_validation_engine.py found no VSX/SIMBAD catalog rejection.
3) It survives additional freshness/variability vetoes that reject common
   AGN/QSO/long-lived variable patterns seen in broker candidates.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Set, Tuple

import pandas as pd


REQUIRED_COLUMNS = {"source_id", "decision", "catalog_decision"}


def parse_label_set(raw: str) -> Set[str]:
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a final reportable shortlist from a catalog validation report."
    )
    parser.add_argument(
        "--catalog-report",
        type=Path,
        required=True,
        help="catalog_validation_report.csv from catalog_validation_engine.py",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("astronomy/final_shortlists/latest"),
    )
    parser.add_argument(
        "--max-candidate-age-days",
        type=float,
        default=60.0,
        help="Reject objects whose first detection is older than this many days.",
    )
    parser.add_argument(
        "--max-detections",
        type=float,
        default=50.0,
        help="Reject objects with more than this many detections.",
    )
    parser.add_argument(
        "--max-baseline-days",
        type=float,
        default=120.0,
        help="Reject objects whose first-to-last detection baseline exceeds this many days.",
    )
    parser.add_argument(
        "--veto-transient-classes",
        default="QSO,AGN",
        help="Comma-separated ALeRCE transient classes that should be vetoed.",
    )
    parser.add_argument(
        "--veto-stamp-classes",
        default="VS,AGN,BOGUS",
        help="Comma-separated ALeRCE stamp classes that should be vetoed.",
    )
    return parser.parse_args()


def as_float(value: object) -> float | None:
    try:
        if pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def veto_reason(
    row: pd.Series,
    *,
    max_candidate_age_days: float,
    max_detections: float,
    max_baseline_days: float,
    veto_transient_classes: Set[str],
    veto_stamp_classes: Set[str],
) -> str:
    transient_class = str(row.get("alerce_top_transient_class", "")).strip().upper()
    stamp_class = str(row.get("alerce_top_stamp_class", "")).strip().upper()
    candidate_age_days = as_float(row.get("candidate_age_days"))
    ndetections = as_float(row.get("ndetections"))
    firstmjd = as_float(row.get("firstmjd"))
    lastmjd = as_float(row.get("lastmjd"))

    if transient_class and transient_class in veto_transient_classes:
        return f"ALeRCE transient class {transient_class} is vetoed as likely AGN/QSO-like variability"
    if stamp_class and stamp_class in veto_stamp_classes:
        return f"ALeRCE stamp class {stamp_class} is vetoed as likely stellar/AGN/artifact behavior"
    if candidate_age_days is not None and candidate_age_days > max_candidate_age_days:
        return (
            f"First detection is too old ({candidate_age_days:.1f} days; limit {max_candidate_age_days:.1f})"
        )
    if ndetections is not None and ndetections > max_detections:
        return f"Detection count is too high ({ndetections:.0f}; limit {max_detections:.0f})"
    if firstmjd is not None and lastmjd is not None:
        baseline_days = max(0.0, lastmjd - firstmjd)
        if baseline_days > max_baseline_days:
            return (
                f"Detection baseline is too long ({baseline_days:.1f} days; limit {max_baseline_days:.1f})"
            )
    return ""


def row_final_decision(
    row: pd.Series,
    *,
    max_candidate_age_days: float,
    max_detections: float,
    max_baseline_days: float,
    veto_transient_classes: Set[str],
    veto_stamp_classes: Set[str],
) -> Tuple[str, str]:
    verification_decision = str(row.get("decision", "")).strip()
    catalog_decision = str(row.get("catalog_decision", "")).strip()
    tns_names = str(row.get("tns_names", "")).strip()
    skybot_names = str(row.get("skybot_names", "")).strip()
    catalog_reason = str(row.get("catalog_reason", "")).strip()

    if verification_decision == "reject_known_tns_object":
        suffix = f": {tns_names}" if tns_names else ""
        return "reject_known_tns_object", f"TNS already has this object{suffix}"
    if verification_decision == "reject_moving_object":
        suffix = f": {skybot_names}" if skybot_names else ""
        return "reject_moving_object", f"SkyBoT moving-object match{suffix}"

    if catalog_decision == "reject_known_variable":
        return "reject_known_variable", catalog_reason or "VSX/SIMBAD variable-star match"
    if catalog_decision.startswith("needs_review"):
        return "needs_manual_catalog_review", catalog_reason or catalog_decision
    if catalog_decision == "possible_host_or_extragalactic_source":
        return "needs_manual_host_review", catalog_reason or catalog_decision

    if verification_decision == "needs_tns_check_before_reporting":
        return "block_pending_tns_check", "TNS was not successfully checked; do not report yet."
    if verification_decision != "likely_new_candidate":
        return "reject_verification_status", f"Verification decision is {verification_decision or 'missing'}"
    if catalog_decision != "pass_catalog_checks":
        return "reject_catalog_status", f"Catalog decision is {catalog_decision or 'missing'}"

    veto = veto_reason(
        row,
        max_candidate_age_days=max_candidate_age_days,
        max_detections=max_detections,
        max_baseline_days=max_baseline_days,
        veto_transient_classes=veto_transient_classes,
        veto_stamp_classes=veto_stamp_classes,
    )
    if veto:
        return "reject_freshness_veto", veto

    return "reportable_candidate", "Passed TNS, SkyBoT, VSX, and SIMBAD gates."


def build_final_shortlist(report: pd.DataFrame, args: argparse.Namespace) -> Dict[str, pd.DataFrame | Dict[str, int]]:
    missing = REQUIRED_COLUMNS - set(report.columns)
    if missing:
        missing_cols = ", ".join(sorted(missing))
        raise ValueError(f"Missing required columns in catalog report: {missing_cols}")

    out = report.copy()
    veto_transient_classes = parse_label_set(args.veto_transient_classes)
    veto_stamp_classes = parse_label_set(args.veto_stamp_classes)
    decisions = out.apply(
        row_final_decision,
        axis=1,
        result_type="expand",
        max_candidate_age_days=float(args.max_candidate_age_days),
        max_detections=float(args.max_detections),
        max_baseline_days=float(args.max_baseline_days),
        veto_transient_classes=veto_transient_classes,
        veto_stamp_classes=veto_stamp_classes,
    )
    out["final_decision"] = decisions[0]
    out["final_reason"] = decisions[1]

    sort_cols = [col for col in ["ai_score", "rank_score", "source_id"] if col in out.columns]
    ascending = [False if col in {"ai_score", "rank_score"} else True for col in sort_cols]
    if sort_cols:
        out = out.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)

    reportable = out[out["final_decision"].eq("reportable_candidate")].copy()
    needs_review = out[out["final_decision"].str.startswith("needs_", na=False)].copy()
    blocked_or_rejected = out[~out["final_decision"].eq("reportable_candidate")].copy()
    summary = {
        "checked": int(len(out)),
        "reportable": int(len(reportable)),
        "pending_tns_check": int(out["final_decision"].eq("block_pending_tns_check").sum()),
        "rejected_known_tns": int(out["final_decision"].eq("reject_known_tns_object").sum()),
        "rejected_moving": int(out["final_decision"].eq("reject_moving_object").sum()),
        "rejected_known_variable": int(out["final_decision"].eq("reject_known_variable").sum()),
        "rejected_freshness_veto": int(out["final_decision"].eq("reject_freshness_veto").sum()),
        "needs_manual_review": int(len(needs_review)),
    }
    return {
        "report": out,
        "reportable": reportable,
        "needs_review": needs_review,
        "blocked_or_rejected": blocked_or_rejected,
        "summary": summary,
    }


def write_outputs(output_dir: Path, result: Dict[str, pd.DataFrame | Dict[str, int]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result["report"].to_csv(output_dir / "final_candidate_report.csv", index=False)  # type: ignore[union-attr]
    result["reportable"].to_csv(output_dir / "reportable_candidates.csv", index=False)  # type: ignore[union-attr]
    result["needs_review"].to_csv(output_dir / "needs_manual_review.csv", index=False)  # type: ignore[union-attr]
    result["blocked_or_rejected"].to_csv(output_dir / "blocked_or_rejected_candidates.csv", index=False)  # type: ignore[union-attr]
    with open(output_dir / "final_summary.json", "w", encoding="utf-8") as f:
        json.dump(result["summary"], f, indent=2)


def main() -> None:
    args = parse_args()
    report = pd.read_csv(args.catalog_report)
    result = build_final_shortlist(report, args)
    write_outputs(args.output_dir, result)

    summary = result["summary"]
    print("Final candidate filter complete.")
    print(f"Checked: {summary['checked']}")
    print(f"Reportable: {summary['reportable']}")
    print(f"Pending TNS check: {summary['pending_tns_check']}")
    print(f"Rejected known TNS: {summary['rejected_known_tns']}")
    print(f"Rejected moving: {summary['rejected_moving']}")
    print(f"Rejected known variables: {summary['rejected_known_variable']}")
    print(f"Rejected freshness veto: {summary['rejected_freshness_veto']}")
    print(f"Needs manual review: {summary['needs_manual_review']}")
    print(f"Output dir: {args.output_dir}")


if __name__ == "__main__":
    main()
