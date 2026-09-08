from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from siderea.research.robust_trial_rng import (
    FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1,
    canonical_trial_key,
    trial_identity,
    trial_rng,
    trial_seed_words,
    verify_frozen_trial_rng_amendment,
)

AMENDMENT = Path("paper/experiments/robust_search_amendment.v2.0.4.json")
DEVELOPMENT_SEED = 2026091101


def _key(trial_index: int) -> str:
    return canonical_trial_key(
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
        trial_index=trial_index,
    )


def test_frozen_trial_rng_amendment_is_exact_and_pre_result() -> None:
    payload = verify_frozen_trial_rng_amendment(AMENDMENT)
    assert payload["previous_amendment_git_blob_sha1"] == (
        "dee0cb3b256e4823e784466e8b5df6041482c3b5"
    )
    assert len(FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1) == 40


def test_known_trial_identity_is_stable() -> None:
    key = _key(0)
    assert trial_seed_words(DEVELOPMENT_SEED, key) == (
        2281714158,
        1047217620,
        1845702933,
        2914420113,
    )
    draws = trial_rng(DEVELOPMENT_SEED, key).standard_normal(4)
    assert np.array_equal(
        draws,
        np.array(
            [
                0.8377605834903745,
                -0.601198019634384,
                -0.6624283873510614,
                -0.9087917874876522,
            ]
        ),
    )


def test_semantic_trial_streams_are_loop_order_independent() -> None:
    keys = [_key(index) for index in range(8)]
    forward = {key: trial_rng(DEVELOPMENT_SEED, key).integers(0, 2**31) for key in keys}
    reverse = {
        key: trial_rng(DEVELOPMENT_SEED, key).integers(0, 2**31) for key in reversed(keys)
    }
    assert forward == reverse
    assert len(set(forward.values())) == len(keys)


def test_phase_seed_and_role_separate_stream_identity() -> None:
    key = _key(0)
    calibration = trial_rng(2026091102, key).integers(0, 2**63)
    development = trial_rng(DEVELOPMENT_SEED, key).integers(0, 2**63)
    assert calibration != development

    different_role = canonical_trial_key(
        phase="development",
        role="null_feasibility",
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
    assert trial_seed_words(DEVELOPMENT_SEED, different_role) != trial_seed_words(
        DEVELOPMENT_SEED, key
    )


def test_trial_identity_is_compact_and_auditable() -> None:
    identity = trial_identity(DEVELOPMENT_SEED, _key(0))
    assert identity["bit_generator"] == "PCG64"
    assert len(identity["canonical_key_sha256"]) == 64
    assert identity["seed_words"] == [2281714158, 1047217620, 1845702933, 2914420113]


def test_noncanonical_or_invalid_keys_fail_closed() -> None:
    with pytest.raises(ValueError, match="trial_index"):
        _ = canonical_trial_key(
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
            trial_index=-1,
        )
    with pytest.raises(ValueError, match="canonical"):
        trial_seed_words(DEVELOPMENT_SEED, '{"schema":"siderea.robust_search_trial_rng.v2"}')
