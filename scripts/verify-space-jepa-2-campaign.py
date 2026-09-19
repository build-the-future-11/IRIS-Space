#!/usr/bin/env python3
"""Verify a Space JEPA 2 campaign root."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from siderea.research.space_jepa_v2_campaign import verify_space_jepa_v2_campaign


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    args = parser.parse_args()
    result = verify_space_jepa_v2_campaign(args.campaign)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
