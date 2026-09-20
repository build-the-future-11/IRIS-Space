from __future__ import annotations

from pathlib import Path

import pytest

from siderea.research.robust_compound_plan import (
    EXPECTED_PLAN_SHA256,
    EXPECTED_PROBE_COUNTS,
    EXPECTED_TOTAL_TRIALS,
    canonical_compound_trial_key,
    compound_plan_digest,
    iter_compound_trial_plan,
    summarize_compound_trial_plan,
    verify_frozen_compound_extension,
    verify_frozen_compound_plan_lock,
)

EXTENSION = Path("paper/experiments/robust_search_compound_nuisance_extension.v2.json")
PLAN_LOCK = Path("paper/experiments/robust_search_compound_trial_plan_lock.v2.json")


def test_compound_extension_and_plan_lock_reproduce_exactly() -> None:
    extension = verify_frozen_compound_extension(EXTENSION)
    summary = summarize_compound_trial_plan(extension)
    lock = verify_frozen_compound_plan_lock(PLAN_LOCK, extension)

    assert summary["probe_counts"] == EXPECTED_PROBE_COUNTS
    assert summary["total_canonical_trial_keys"] == EXPECTED_TOTAL_TRIALS
    assert summary["unique_canonical_trial_keys"] == EXPECTED_TOTAL_TRIALS
    assert summary["duplicate_canonical_trial_keys"] == 0
    assert summary["sha256"] == EXPECTED_PLAN_SHA256
    assert lock["digest"]["sha256"] == EXPECTED_PLAN_SHA256


def test_compound_trial_identity_is_canonical_and_local() -> None:
    key = canonical_compound_trial_key(
        probe_id="seasonal_gap_x_ar1_rho_0_7",
        cadence_id="seasonal_gap_01",
        trial_index=0,
    )
    assert key == (
        '{"cadence_id":"seasonal_gap_01",'
        '"probe_id":"seasonal_gap_x_ar1_rho_0_7",'
        '"schema":"siderea.robust_search_compound_trial_rng.v1",'
        '"trial_index":0}'
    )

    with pytest.raises(ValueError, match="trial_index"):
        canonical_compound_trial_key(
            probe_id="seasonal_gap_x_ar1_rho_0_7",
            cadence_id="seasonal_gap_01",
            trial_index=-1,
        )


def test_compound_plan_digest_is_enumeration_order_independent() -> None:
    extension = verify_frozen_compound_extension(EXTENSION)
    keys = list(iter_compound_trial_plan(extension))
    forward = compound_plan_digest(keys)
    reverse = compound_plan_digest(reversed(keys))
    assert forward == reverse
    assert forward == (EXPECTED_PLAN_SHA256, EXPECTED_TOTAL_TRIALS, 0)


def test_duplicate_compound_key_fails_closed() -> None:
    key = canonical_compound_trial_key(
        probe_id="seasonal_gap_x_ar1_rho_0_7",
        cadence_id="seasonal_gap_01",
        trial_index=0,
    )
    with pytest.raises(ValueError, match="duplicate"):
        compound_plan_digest([key, key])


def test_extension_byte_mutation_fails_closed(tmp_path: Path) -> None:
    mutated = tmp_path / EXTENSION.name
    mutated.write_bytes(
        EXTENSION.read_bytes().replace(
            b'"extension_seed": 2026091105',
            b'"extension_seed": 2026091106',
        )
    )
    with pytest.raises(RuntimeError, match="frozen pre-outcome artifact"):
        verify_frozen_compound_extension(mutated)


def test_plan_lock_byte_mutation_fails_closed(tmp_path: Path) -> None:
    extension = verify_frozen_compound_extension(EXTENSION)
    mutated = tmp_path / PLAN_LOCK.name
    mutated.write_bytes(
        PLAN_LOCK.read_bytes().replace(
            b'"extension_seed": 2026091105',
            b'"extension_seed": 2026091106',
        )
    )
    with pytest.raises(RuntimeError, match="frozen pre-outcome artifact"):
        verify_frozen_compound_plan_lock(mutated, extension)
