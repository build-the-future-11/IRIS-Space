from __future__ import annotations

import json
from pathlib import Path

from siderea.research.robust_predevelopment import verify_all_predevelopment_inputs


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "paper/experiments/robust_search_protocol.v2.json"
CADENCES = ROOT / "paper/experiments/robust_search_cadences.v2.json"
AMENDMENT = ROOT / "paper/experiments/robust_search_amendment.v2.0.1.json"
EXECUTION_AMENDMENT = ROOT / "paper/experiments/robust_search_amendment.v2.0.2.json"
IDENTIFIER_ERRATUM = ROOT / "paper/experiments/robust_search_amendment.v2.0.3.json"
TRIAL_RNG_AMENDMENT = ROOT / "paper/experiments/robust_search_amendment.v2.0.4.json"
TRIAL_PLAN_AMENDMENT = ROOT / "paper/experiments/robust_search_amendment.v2.0.5.json"
TRIAL_PLAN_LOCK = ROOT / "paper/experiments/robust_trial_plan_lock.v2.json"
REPORTED_ERRORS = ROOT / "paper/experiments/robust_search_reported_errors.v2.json"


def main() -> None:
    receipt = verify_all_predevelopment_inputs(
        PROTOCOL,
        CADENCES,
        AMENDMENT,
        EXECUTION_AMENDMENT,
        IDENTIFIER_ERRATUM,
        TRIAL_RNG_AMENDMENT,
        TRIAL_PLAN_AMENDMENT,
        TRIAL_PLAN_LOCK,
        REPORTED_ERRORS,
    )
    print(json.dumps(receipt, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
