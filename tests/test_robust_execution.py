from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from siderea.research.robust_execution import (
    EFFECTIVE_CANDIDATES,
    FROZEN_REPORTED_ERRORS_MANIFEST_SHA256,
    build_reported_error_manifest,
    reported_error_manifest_bytes,
    verify_frozen_amendment,
    verify_materialized_reported_errors,
    verify_predevelopment_inputs,
)

PROTOCOL = Path("paper/experiments/robust_search_protocol.v2.json")
AMENDMENT = Path("paper/experiments/robust_search_amendment.v2.0.1.json")
REPORTED_ERRORS = Path("paper/experiments/robust_search_reported_errors.v2.json")


def test_frozen_amendment_and_effective_candidate_set_are_locked() -> None:
    _, amendment = verify_frozen_amendment(AMENDMENT, PROTOCOL)
    candidates = amendment["changes"]["candidate_statistics"]["effective_candidates"]
    assert tuple(candidates) == EFFECTIVE_CANDIDATES


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


def test_committed_reported_error_artifact_matches_generator_exactly() -> None:
    protocol, amendment = verify_frozen_amendment(AMENDMENT, PROTOCOL)
    digest = verify_materialized_reported_errors(REPORTED_ERRORS, protocol, amendment)
    assert digest == FROZEN_REPORTED_ERRORS_MANIFEST_SHA256


def test_amendment_mutation_fails_closed(tmp_path: Path) -> None:
    changed = tmp_path / "amendment.json"
    changed.write_bytes(AMENDMENT.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="versioned amendment"):
        verify_frozen_amendment(changed, PROTOCOL)


def test_reported_error_artifact_mutation_fails_closed(tmp_path: Path) -> None:
    protocol, amendment = verify_frozen_amendment(AMENDMENT, PROTOCOL)
    changed = tmp_path / "reported-errors.json"
    changed.write_bytes(REPORTED_ERRORS.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="differ from the frozen manifest"):
        verify_materialized_reported_errors(changed, protocol, amendment)


def test_predevelopment_gate_returns_only_input_receipts() -> None:
    receipt = verify_predevelopment_inputs(PROTOCOL, AMENDMENT, REPORTED_ERRORS)
    assert receipt["status"] == "PASS_PREDEVELOPMENT_INPUT_LOCKS_NO_PERFORMANCE_STATISTICS"
    assert receipt["reported_errors_sha256"] == FROZEN_REPORTED_ERRORS_MANIFEST_SHA256
    assert "threshold" not in receipt
    assert "false_alarm" not in receipt
    assert "recovery" not in receipt
