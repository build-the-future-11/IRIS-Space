from __future__ import annotations

from pathlib import Path

from siderea.research.robust_protocol import verify_frozen_protocol
from siderea.research.robust_trial_plan import (
    EXPECTED_PHASE_COUNTS,
    EXPECTED_PLAN_SHA256,
    EXPECTED_ROLE_COUNTS,
    EXPECTED_TOTAL_TRIALS,
    verify_frozen_trial_plan_amendment,
    verify_frozen_trial_plan_lock,
)

PROTOCOL = Path("paper/experiments/robust_search_protocol.v2.json")
AMENDMENT = Path("paper/experiments/robust_search_amendment.v2.0.5.json")
LOCK = Path("paper/experiments/robust_trial_plan_lock.v2.json")


def test_complete_semantic_trial_plan_reproduces_before_development() -> None:
    protocol = verify_frozen_protocol(PROTOCOL)
    amendment = verify_frozen_trial_plan_amendment(AMENDMENT)
    lock = verify_frozen_trial_plan_lock(LOCK, protocol)

    assert amendment["changes"]["total_stochastic_data_generation_identities"] == (
        EXPECTED_TOTAL_TRIALS
    )
    assert lock["role_counts"] == EXPECTED_ROLE_COUNTS
    assert lock["phase_counts"] == EXPECTED_PHASE_COUNTS
    assert lock["total_canonical_trial_keys"] == EXPECTED_TOTAL_TRIALS == 415_375
    assert lock["unique_canonical_trial_keys"] == EXPECTED_TOTAL_TRIALS
    assert lock["duplicate_canonical_trial_keys"] == 0
    assert lock["digest"]["sha256"] == EXPECTED_PLAN_SHA256
    assert lock["locked_signal_allocation_checks"] == {
        "family_amplitude_noise_cells": 48,
        "width_specific_global_cells": 144,
        "global_width_counts": {
            "cells_with_334_trials": 48,
            "cells_with_333_trials": 96,
        },
        "final_semantic_cells": 3600,
        "local_trial_index_cell_counts": {
            "cells_with_14_trials": 1200,
            "cells_with_13_trials": 2400,
        },
        "candidate_id": None,
    }
