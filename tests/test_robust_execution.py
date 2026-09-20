from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from siderea.research.robust_execution import (
    EFFECTIVE_CANDIDATES,
    FROZEN_EXECUTION_AMENDMENT_GIT_BLOB_SHA1,
    FROZEN_IDENTIFIER_ERRATUM_GIT_BLOB_SHA1,
    FROZEN_REPORTED_ERRORS_MANIFEST_SHA256,
    build_reported_error_manifest,
    reported_error_manifest_bytes,
    verify_frozen_amendment,
    verify_frozen_execution_amendment,
    verify_frozen_identifier_erratum,
    verify_predevelopment_inputs,
    verify_reported_error_lock,
)

PROTOCOL = Path("paper/experiments/robust_search_protocol.v2.json")
AMENDMENT = Path("paper/experiments/robust_search_amendment.v2.0.1.json")
EXECUTION_AMENDMENT = Path("paper/experiments/robust_search_amendment.v2.0.2.json")
IDENTIFIER_ERRATUM = Path("paper/experiments/robust_search_amendment.v2.0.3.json")
REPORTED_ERROR_LOCK = Path("paper/experiments/robust_search_reported_errors.v2.json")


def test_frozen_amendment_and_effective_candidate_set_are_locked() -> None:
    _, amendment = verify_frozen_amendment(AMENDMENT, PROTOCOL)
    candidates = amendment["changes"]["candidate_statistics"]["effective_candidates"]
    assert tuple(candidates) == EFFECTIVE_CANDIDATES


def test_execution_amendment_is_bound_to_prior_frozen_artifacts() -> None:
    _, _, execution = verify_frozen_execution_amendment(
        EXECUTION_AMENDMENT,
        AMENDMENT,
        PROTOCOL,
    )
    assert execution["previous_amendment_git_blob_sha1"]
    assert len(FROZEN_EXECUTION_AMENDMENT_GIT_BLOB_SHA1) == 40
    assert execution["changes"]["paired_bootstrap"]["replicates"] == 10000
    assert execution["changes"]["generalization_probe_allocation"]["trials_per_probe"] == 5000


def test_identifier_erratum_matches_the_frozen_cadence_generator() -> None:
    _, _, _, erratum = verify_frozen_identifier_erratum(
        IDENTIFIER_ERRATUM,
        EXECUTION_AMENDMENT,
        AMENDMENT,
        PROTOCOL,
    )
    identifiers = erratum["changes"]["cadence_identifier_erratum"]
    assert identifiers["canonical_ordinary_ids"] == [
        f"irregular_{index:02d}" for index in range(1, 21)
    ]
    assert identifiers["canonical_seasonal_gap_ids"] == [
        f"seasonal_gap_{index:02d}" for index in range(1, 6)
    ]
    assert len(FROZEN_IDENTIFIER_ERRATUM_GIT_BLOB_SHA1) == 40


def test_reported_error_vectors_are_precommitted_and_disjoint_from_cadence_children() -> None:
    protocol, amendment = verify_frozen_amendment(AMENDMENT, PROTOCOL)
    payload = build_reported_error_manifest(protocol, amendment)
    encoded = reported_error_manifest_bytes(protocol, amendment)

    assert hashlib.sha256(encoded).hexdigest() == FROZEN_REPORTED_ERRORS_MANIFEST_SHA256
    rows = payload["reported_error_vectors"]
    assert len(rows) == 25
    assert [row["seed_spawn_index"] for row in rows] == list(range(25, 50))
    assert [row["cadence_index"] for row in rows] == list(range(25))
    assert all(len(row["reported_errors"]) == 64 for row in rows)
    assert all(0.7 <= value <= 1.3 for row in rows for value in row["reported_errors"])


def test_committed_reported_error_lock_binds_generator_digest() -> None:
    protocol, amendment = verify_frozen_amendment(AMENDMENT, PROTOCOL)
    digest = verify_reported_error_lock(REPORTED_ERROR_LOCK, protocol, amendment)
    assert digest == FROZEN_REPORTED_ERRORS_MANIFEST_SHA256


def test_amendment_mutation_fails_closed(tmp_path: Path) -> None:
    changed = tmp_path / "amendment.json"
    changed.write_bytes(AMENDMENT.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="versioned amendment"):
        verify_frozen_amendment(changed, PROTOCOL)


def test_execution_amendment_mutation_fails_closed(tmp_path: Path) -> None:
    changed = tmp_path / "execution-amendment.json"
    changed.write_bytes(EXECUTION_AMENDMENT.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="versioned amendment"):
        verify_frozen_execution_amendment(changed, AMENDMENT, PROTOCOL)


def test_identifier_erratum_mutation_fails_closed(tmp_path: Path) -> None:
    changed = tmp_path / "identifier-erratum.json"
    changed.write_bytes(IDENTIFIER_ERRATUM.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="versioned amendment"):
        verify_frozen_identifier_erratum(
            changed,
            EXECUTION_AMENDMENT,
            AMENDMENT,
            PROTOCOL,
        )


def test_reported_error_lock_mutation_fails_closed(tmp_path: Path) -> None:
    protocol, amendment = verify_frozen_amendment(AMENDMENT, PROTOCOL)
    lock = json.loads(REPORTED_ERROR_LOCK.read_text(encoding="utf-8"))
    lock["canonical_generated_manifest_sha256"] = "0" * 64
    changed = tmp_path / "reported-errors-lock.json"
    changed.write_text(json.dumps(lock), encoding="utf-8")
    with pytest.raises(RuntimeError, match="precommitment field"):
        verify_reported_error_lock(changed, protocol, amendment)


def test_predevelopment_gate_returns_only_input_receipts() -> None:
    receipt = verify_predevelopment_inputs(
        PROTOCOL,
        AMENDMENT,
        EXECUTION_AMENDMENT,
        IDENTIFIER_ERRATUM,
        REPORTED_ERROR_LOCK,
    )
    assert receipt["status"] == "PASS_PREDEVELOPMENT_INPUT_LOCKS_NO_PERFORMANCE_STATISTICS"
    assert receipt["reported_errors_sha256"] == FROZEN_REPORTED_ERRORS_MANIFEST_SHA256
    assert receipt["execution_amendment_git_blob_sha1"] == (
        FROZEN_EXECUTION_AMENDMENT_GIT_BLOB_SHA1
    )
    assert receipt["identifier_erratum_git_blob_sha1"] == (FROZEN_IDENTIFIER_ERRATUM_GIT_BLOB_SHA1)
    assert "threshold" not in receipt
    assert "false_alarm" not in receipt
    assert "recovery" not in receipt
