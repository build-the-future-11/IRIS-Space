from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from siderea.research.robust_protocol import (
    FROZEN_CADENCE_MANIFEST_SHA256,
    build_cadence_manifest,
    materialize_cadence_manifest,
    verify_cadence_manifest,
    verify_frozen_protocol,
)


PROTOCOL = Path("paper/experiments/robust_search_protocol.v2.json")


def test_frozen_protocol_bytes_and_phase_seeds_are_locked() -> None:
    config = verify_frozen_protocol(PROTOCOL)
    design = config["design"]
    assert (
        len(
            {
                design["development_seed"],
                design["calibration_seed"],
                design["locked_evaluation_seed"],
            }
        )
        == 3
    )


def test_exact_cadence_manifest_is_precommitted() -> None:
    config = verify_frozen_protocol(PROTOCOL)
    encoded = verify_cadence_manifest(config)
    assert hashlib.sha256(encoded).hexdigest() == FROZEN_CADENCE_MANIFEST_SHA256

    payload = build_cadence_manifest(config)
    assert len(payload["cadences"]) == 25
    assert [row["kind"] for row in payload["cadences"]].count("irregular") == 20
    assert [row["kind"] for row in payload["cadences"]].count("seasonal_gap") == 5
    assert all(len(row["times_days"]) == 64 for row in payload["cadences"])
    assert all(
        left < right
        for row in payload["cadences"]
        for left, right in zip(
            row["times_days"][:-1], row["times_days"][1:], strict=True
        )
    )
    for row in payload["cadences"][-5:]:
        assert sum(value <= 20.0 for value in row["times_days"]) == 32
        assert sum(value >= 40.0 for value in row["times_days"]) == 32


def test_protocol_mutation_fails_closed(tmp_path: Path) -> None:
    changed = tmp_path / "protocol.json"
    changed.write_bytes(PROTOCOL.read_bytes() + b"\n")
    with pytest.raises(RuntimeError, match="versioned amendment"):
        verify_frozen_protocol(changed)


def test_materialization_refuses_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "cadences.json"
    digest = materialize_cadence_manifest(PROTOCOL, destination)
    assert digest == FROZEN_CADENCE_MANIFEST_SHA256
    assert destination.read_bytes() == verify_cadence_manifest(verify_frozen_protocol(PROTOCOL))
    with pytest.raises(FileExistsError, match="preserve the frozen artifact"):
        materialize_cadence_manifest(PROTOCOL, destination)
