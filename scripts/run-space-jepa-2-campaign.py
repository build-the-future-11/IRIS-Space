#!/usr/bin/env python3
"""Run the fail-closed Space JEPA 2 predictive-core campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from siderea.research.space_jepa_v2_campaign import run_space_jepa_v2_campaign


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--tns-input", required=True, type=Path)
    parser.add_argument("--survey-input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--device", choices=("cpu", "mps", "cuda"), default="cpu")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    result = run_space_jepa_v2_campaign(
        protocol_path=args.protocol,
        tns_input=args.tns_input,
        survey_input=args.survey_input,
        output=args.output,
        resume=args.resume,
        epochs=args.epochs,
        batch_size=args.batch_size,
        device=args.device,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] in {"COMPLETED", "COMPLETED_NEGATIVE"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
