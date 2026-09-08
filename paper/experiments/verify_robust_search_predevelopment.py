from __future__ import annotations

import json
from pathlib import Path

from siderea.research.robust_execution import verify_predevelopment_inputs


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "paper/experiments/robust_search_protocol.v2.json"
AMENDMENT = ROOT / "paper/experiments/robust_search_amendment.v2.0.1.json"
REPORTED_ERRORS = ROOT / "paper/experiments/robust_search_reported_errors.v2.json"


def main() -> None:
    receipt = verify_predevelopment_inputs(PROTOCOL, AMENDMENT, REPORTED_ERRORS)
    print(json.dumps(receipt, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
