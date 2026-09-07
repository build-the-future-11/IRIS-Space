#!/usr/bin/env python3
"""
Run a medium ALeRCE/ZTF transient-candidate sweep.

This is a thin wrapper around ai_candidate_hunter.py with safer defaults for
~350-object runs: moderate pagination, previous-run exclusion, local cache use,
fresh-object preference, and stricter early vetoes for long-lived
variables/AGN-like sources.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch a 350-object non-overlapping ALeRCE/ZTF candidate hunt."
    )
    parser.add_argument("--max-objects", type=int, default=350)
    parser.add_argument("--probability", type=float, default=0.25)
    parser.add_argument("--page-size", type=int, default=75)
    parser.add_argument("--max-pages-per-class", type=int, default=10)
    parser.add_argument("--class-names", default="SNIa,SNII,SNIbc,SLSN")
    parser.add_argument(
        "--fresh-days",
        type=float,
        default=60.0,
        help="Prefer objects whose broker first detection is within this many days of the newest fetched object.",
    )
    parser.add_argument(
        "--discovered-within-days",
        type=float,
        default=45.0,
        help="Query-level filter: only fetch objects first detected within this many days of now. 0 disables it.",
    )
    parser.add_argument(
        "--max-history-points",
        type=int,
        default=60,
        help="Prefer objects with no more than this many broker alert detections.",
    )
    parser.add_argument("--early-veto-age-days", type=float, default=45.0)
    parser.add_argument("--early-veto-detections", type=float, default=40.0)
    parser.add_argument("--early-veto-baseline-days", type=float, default=90.0)
    parser.add_argument("--per-object-timeout-sec", type=float, default=8.0)
    parser.add_argument("--cache-dir", type=Path, default=Path("astronomy/cache/alerce_lightcurves"))
    parser.add_argument("--output-dir", type=Path, default=Path("astronomy/ai_hunter_runs"))
    parser.add_argument(
        "--include-previous-runs",
        action="store_true",
        help="Do not skip objects already present in earlier broker_objects.csv files.",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Force fresh ALeRCE light-curve downloads even when local cache files exist.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the command that would run without contacting ALeRCE.",
    )
    return parser.parse_args()


def build_command(args: argparse.Namespace) -> list[str]:
    hunter = Path(__file__).resolve().with_name("ai_candidate_hunter.py")
    command = [
        sys.executable,
        str(hunter),
        "--class-names",
        args.class_names,
        "--probability",
        str(args.probability),
        "--page-size",
        str(args.page_size),
        "--max-objects",
        str(args.max_objects),
        "--max-pages-per-class",
        str(args.max_pages_per_class),
        "--fresh-days",
        str(args.fresh_days),
        "--discovered-within-days",
        str(args.discovered_within_days),
        "--max-history-points",
        str(args.max_history_points),
        "--cache-dir",
        str(args.cache_dir),
        "--early-veto-age-days",
        str(args.early_veto_age_days),
        "--early-veto-detections",
        str(args.early_veto_detections),
        "--early-veto-baseline-days",
        str(args.early_veto_baseline_days),
        "--per-object-timeout-sec",
        str(args.per_object_timeout_sec),
        "--output-dir",
        str(args.output_dir),
    ]

    if not args.include_previous_runs:
        command.append("--exclude-previous-runs")
    if args.refresh_cache:
        command.append("--refresh-cache")

    return command


def main() -> None:
    args = parse_args()
    command = build_command(args)
    print("Large candidate hunt command:")
    print(" ".join(command))

    if args.dry_run:
        return

    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
