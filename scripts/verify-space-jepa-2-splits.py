#!/usr/bin/env python3
"""Verify Space JEPA 2 prepared split provenance without model execution."""

import argparse
import json
import sys

from siderea.research.space_jepa_v2_split_integrity import verify_prepared_splits


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared")
    parser.add_argument("source")
    parser.add_argument("protocol")
    args = parser.parse_args(argv)
    try:
        report = verify_prepared_splits(args.prepared, args.source, args.protocol)
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
