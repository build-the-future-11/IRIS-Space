from __future__ import annotations

from pathlib import Path

import pytest

from siderea.research.robust_predevelopment import (
    load_predevelopment_authority,
    verify_all_predevelopment_inputs,
    verify_materialized_cadence_manifest,
)
from siderea.research.robust_protocol import (
    FROZEN_CADENCE_MANIFEST_SHA256,
    verify_frozen_protocol,
)
from siderea.research.robust_trial_plan import (
    EXPECTED_PLAN_SHA256,
    EXPECTED_TOTAL_TRIALS,
    FROZEN_TRIAL_PLAN_AMENDMENT_GIT_BLOB_SHA1,
    FROZEN_TRIAL_PLAN_LOCK_GIT_BLOB_SHA1,
)
from siderea.research.robust_trial_rng import (
    FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1,
)

PROTOCOL = Path("paper/experiments/robust_search_protocol.v2.json")
CADENCES = Path("paper/experiments/robust_search_cadences.v2.json")
AMENDMENT = Path("paper/experiments/robust_search_amendment.v2.0.1.json")
EXECUTION_AMENDMENT = Path("paper/experiments/robust_search_amendment.v2.0.2.json")
IDENTIFIER_ERRATUM = Path("paper/experiments/robust_search_amendment.v2.0.3.json")
TRIAL_RNG_AMENDMENT = Path("paper/experiments/robust_search_amendment.v2.0.4.json")
TRIAL_PLAN_AMENDMENT = Path("paper/experiments/robust_search_amendment.v2.0.5.json")
TRIAL_PLAN_LOCK = Path("paper/experiments/robust_trial_plan_lock.v2.json")
REPORTED_ERROR_LOCK = Path("paper/experiments/robust_search_reported_errors.v2.json")


def test_materialized_cadence_manifest_is_bound_to_frozen_generator() -> None:
    protocol = verify_frozen_protocol(PROTOCOL)
    digest = verify_materialized_cadence_manifest(CADENCES, protocol)
    assert digest == FROZEN_CADENCE_MANIFEST_SHA256


def test_materialized_cadence_mutation_fails_closed(tmp_path: Path) -> None:
    changed = tmp_path / "cadences.json"
    changed.write_bytes(CADENCES.read_bytes() + b"\n")
    protocol = verify_frozen_protocol(PROTOCOL)

    with pytest.raises(RuntimeError, match="materialized robust-search cadence manifest"):
        verify_materialized_cadence_manifest(changed, protocol)


def test_canonical_predevelopment_gate_binds_all_pre_result_identity() -> None:
    receipt = verify_all_predevelopment_inputs(
        PROTOCOL,
        CADENCES,
        AMENDMENT,
        EXECUTION_AMENDMENT,
        IDENTIFIER_ERRATUM,
        TRIAL_RNG_AMENDMENT,
        TRIAL_PLAN_AMENDMENT,
        TRIAL_PLAN_LOCK,
        REPORTED_ERROR_LOCK,
    )

    assert receipt["status"] == "PASS_PREDEVELOPMENT_INPUT_LOCKS_NO_PERFORMANCE_STATISTICS"
    assert receipt["cadence_manifest_sha256"] == FROZEN_CADENCE_MANIFEST_SHA256
    assert receipt["trial_rng_amendment_git_blob_sha1"] == FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1
    assert (
        receipt["trial_plan_amendment_git_blob_sha1"] == FROZEN_TRIAL_PLAN_AMENDMENT_GIT_BLOB_SHA1
    )
    assert receipt["trial_plan_lock_git_blob_sha1"] == FROZEN_TRIAL_PLAN_LOCK_GIT_BLOB_SHA1
    assert receipt["trial_plan_sha256"] == EXPECTED_PLAN_SHA256
    assert "threshold" not in receipt
    assert "false_alarm" not in receipt
    assert "recovery" not in receipt


def test_predevelopment_authority_couples_receipt_to_exact_authorized_plan() -> None:
    authority = load_predevelopment_authority(
        PROTOCOL,
        CADENCES,
        AMENDMENT,
        EXECUTION_AMENDMENT,
        IDENTIFIER_ERRATUM,
        TRIAL_RNG_AMENDMENT,
        TRIAL_PLAN_AMENDMENT,
        TRIAL_PLAN_LOCK,
        REPORTED_ERROR_LOCK,
    )

    assert authority.full_plan_sha256 == EXPECTED_PLAN_SHA256
    assert authority.total_keys == EXPECTED_TOTAL_TRIALS
    assert authority.receipt["trial_plan_sha256"] == authority.full_plan_sha256

    subset = authority.trial_plan.subset(
        phase="development",
        role="development_threshold_null",
    )
    assert authority.trial_plan.require_key(subset.keys[0]) == subset.keys[0]

    with pytest.raises(ValueError, match="not authorized"):
        authority.trial_plan.require_key(
            '{"phase":"development","role":"development_threshold_null","trial_index":999999}'
        )

    with pytest.raises(TypeError):
        authority.receipt["trial_plan_sha256"] = "mutated"  # type: ignore[index]
