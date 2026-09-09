from __future__ import annotations

from pathlib import Path

import pytest

from siderea.research.robust_authorized_plan import (
    ROLE_PHASE,
    load_authorized_trial_plan,
)
from siderea.research.robust_protocol import verify_frozen_protocol
from siderea.research.robust_trial_plan import (
    EXPECTED_PLAN_SHA256,
    EXPECTED_ROLE_COUNTS,
    EXPECTED_TOTAL_TRIALS,
)
from siderea.research.robust_trial_rng import canonical_trial_key

PROTOCOL = Path("paper/experiments/robust_search_protocol.v2.json")
TRIAL_PLAN_LOCK = Path("paper/experiments/robust_trial_plan_lock.v2.json")


@pytest.fixture(scope="module")
def authorized_plan():
    protocol = verify_frozen_protocol(PROTOCOL)
    return load_authorized_trial_plan(protocol, TRIAL_PLAN_LOCK)


def test_authorized_plan_reconstructs_exact_frozen_counts(authorized_plan) -> None:
    assert authorized_plan.full_plan_sha256 == EXPECTED_PLAN_SHA256
    assert authorized_plan.total_keys == EXPECTED_TOTAL_TRIALS
    assert (
        sum(len(subset.keys) for subset in authorized_plan.subsets)
        == EXPECTED_TOTAL_TRIALS
    )
    assert {subset.role: len(subset.keys) for subset in authorized_plan.subsets} == (
        EXPECTED_ROLE_COUNTS
    )


def test_every_frozen_role_has_exactly_one_phase(authorized_plan) -> None:
    assert {subset.role: subset.phase for subset in authorized_plan.subsets} == ROLE_PHASE
    for role, phase in ROLE_PHASE.items():
        subset = authorized_plan.subset(phase=phase, role=role)
        assert subset.role == role
        assert subset.phase == phase
        assert len(subset.digest_sha256) == 64


def test_execution_layer_rejects_structurally_valid_but_unfrozen_role(
    authorized_plan,
) -> None:
    unauthorized = canonical_trial_key(
        phase="development",
        role="null_threshold",
        cadence_id="irregular_01",
        null_regime="iid_gaussian",
        candidate_id=None,
        signal_family=None,
        signal_width_days=None,
        amplitude_sigma=None,
        noise_regime=None,
        probe_id=None,
        trial_index=0,
    )
    with pytest.raises(ValueError, match="unknown frozen v2 role"):
        authorized_plan.require_key(unauthorized)


def test_execution_layer_rejects_extra_key_inside_valid_phase_and_role(
    authorized_plan,
) -> None:
    unauthorized = canonical_trial_key(
        phase="development",
        role="development_threshold_null",
        cadence_id="irregular_01",
        null_regime="iid_gaussian",
        candidate_id=None,
        signal_family=None,
        signal_width_days=None,
        amplitude_sigma=None,
        noise_regime=None,
        probe_id=None,
        trial_index=50,
    )
    with pytest.raises(ValueError, match="not authorized"):
        authorized_plan.require_key(unauthorized)


def test_authorized_key_is_accepted_without_reconstruction(authorized_plan) -> None:
    subset = authorized_plan.subset(
        phase="development",
        role="development_threshold_null",
    )
    key = subset.keys[0]
    assert authorized_plan.require_key(key) == key
    assert subset.require_key(key) == key


def test_wrong_phase_for_frozen_role_fails_closed(authorized_plan) -> None:
    with pytest.raises(ValueError, match="belongs to phase"):
        authorized_plan.subset(
            phase="calibration",
            role="development_threshold_null",
        )
