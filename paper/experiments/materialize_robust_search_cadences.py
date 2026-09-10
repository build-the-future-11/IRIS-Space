"""Materialize the exact frozen cadence inputs for robust-search v2.

This command creates input data only.  It does not evaluate any search statistic
or generate development/calibration/locked results.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from siderea.research.robust_protocol import materialize_cadence_manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path(__file__).with_name("robust_search_protocol.v2.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("robust_search_cadences.v2.json"),
    )
    args = parser.parse_args()
    print(materialize_cadence_manifest(args.protocol, args.output))
