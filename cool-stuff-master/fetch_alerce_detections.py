#!/usr/bin/env python3
"""
Fetch live ALeRCE ZTF detections into a CSV usable by optical_transient_pipeline.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from alerce.core import Alerce


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch ALeRCE detections for transient-like objects.")
    parser.add_argument("--classifier", default="lc_classifier_BHRF_forced_phot_transient")
    parser.add_argument("--class-name", default="SNIa")
    parser.add_argument("--probability", type=float, default=0.5)
    parser.add_argument("--page-size", type=int, default=12)
    parser.add_argument("--order-by", default="lastmjd")
    parser.add_argument("--order-mode", default="DESC")
    parser.add_argument("--output-csv", type=Path, default=Path("astronomy/live_alerce_detections.csv"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    client = Alerce()
    objects = client.query_objects(
        classifier=args.classifier,
        class_name=args.class_name,
        probability=args.probability,
        page_size=args.page_size,
        order_by=args.order_by,
        order_mode=args.order_mode,
        format="pandas",
    )

    rows = []
    for _, obj in objects.iterrows():
        oid = obj["oid"]
        ra = float(obj["meanra"])
        dec = float(obj["meandec"])
        lightcurve = client.query_lightcurve(oid, format="json")
        for det in lightcurve.get("detections", []):
            mag = det.get("magpsf_corr", det.get("magpsf"))
            mag_err = det.get("sigmapsf_corr", det.get("sigmapsf"))
            mjd = det.get("mjd")
            fid = det.get("fid")
            if mag is None or mag_err is None or mjd is None:
                continue
            rows.append(
                {
                    "source_id": oid,
                    "ra": ra,
                    "dec": dec,
                    "mjd": float(mjd),
                    "mag": float(mag),
                    "magerr": float(mag_err),
                    "filter": int(fid) if fid is not None else None,
                    "catflags": 0,
                }
            )

    frame = pd.DataFrame(rows)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output_csv, index=False)

    print(f"Objects fetched: {len(objects)}")
    print(f"Detection rows written: {len(frame)}")
    print(f"Output CSV: {args.output_csv}")


if __name__ == "__main__":
    main()
