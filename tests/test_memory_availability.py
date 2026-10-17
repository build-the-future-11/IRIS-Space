from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from siderea.cli import main
from siderea.ml.episodic_memory import (
    MEMORY_CONTRACT_VERSION,
    EpisodicResidualMemory,
    MemoryEntry,
)


def _entry(**changes):
    values = {
        "entry_id": "delayed-target",
        "key": np.zeros((2, 4)),
        "residual": np.ones((2, 4)),
        "source_group": "training-source",
        "cutoff_mjd": 10.0,
        "available_at_mjd": 20.0,
        "population": "A",
        "calibration": "v1",
    }
    values.update(changes)
    return MemoryEntry(**values)


def _retrieve(memory, cutoff):
    return memory.retrieve(
        np.zeros((2, 4)),
        np.zeros((2, 4)),
        query_source_group="query-source",
        query_cutoff_mjd=cutoff,
        population="A",
        calibration="v1",
        force_gate=1.0,
    )


@pytest.mark.parametrize(
    "cutoff,eligible", [(15.0, False), (19.999, False), (20.0, True), (21.0, True)]
)
def test_residual_cannot_be_retrieved_until_its_complete_target_is_available(cutoff, eligible):
    result = _retrieve(EpisodicResidualMemory([_entry()]), cutoff)
    assert result.supported is eligible
    assert result.neighbor_ids == (("delayed-target",) if eligible else ())
    np.testing.assert_array_equal(result.corrected, np.full((2, 4), int(eligible)))


def test_unavailable_nearest_entry_does_not_evict_available_neighbor():
    late = _entry(residual=np.full((2, 4), 1000.0))
    ready = _entry(entry_id="ready", available_at_mjd=12.0, key=np.ones((2, 4)))
    result = _retrieve(EpisodicResidualMemory([late, ready], maximum_neighbors=1), 15.0)
    assert result.neighbor_ids == ("ready",)
    np.testing.assert_array_equal(result.corrected, np.ones((2, 4)))


@pytest.mark.parametrize("bad", [None, True, "20", np.nan, np.inf, -np.inf, 9.0])
def test_missing_ambiguous_nonfinite_or_earlier_availability_is_rejected(bad):
    with pytest.raises(ValueError, match="available_at_mjd"):
        _entry(available_at_mjd=bad)


def test_mapping_cannot_infer_residual_availability_from_prefix_cutoff():
    item = _entry().to_mapping()
    del item["available_at_mjd"]
    with pytest.raises(ValueError, match="explicit residual"):
        MemoryEntry.from_mapping(item)


@pytest.mark.parametrize("weights", [None, [0.2, 1.7], [1e308, 1e308]])
def test_memory_payload_roundtrip_preserves_digest_and_predictions(weights):
    memory = EpisodicResidualMemory([_entry()], metric_weights=weights)
    restored = EpisodicResidualMemory.from_payload(json.loads(json.dumps(memory.to_payload())))
    assert restored.digest == memory.digest
    assert restored.to_payload() == memory.to_payload()
    np.testing.assert_array_equal(
        _retrieve(restored, 21.0).corrected, _retrieve(memory, 21.0).corrected
    )


def test_availability_is_bound_into_memory_identity():
    entry = _entry()
    first = EpisodicResidualMemory([entry])
    second = EpisodicResidualMemory([replace(entry, available_at_mjd=30.0)])
    assert first.digest != second.digest


@pytest.mark.parametrize("field", ["available_at_mjd", "cutoff_mjd", "residual", "key"])
def test_replayed_memory_rejects_tampered_entry_before_retrieval(field):
    payload = EpisodicResidualMemory([_entry()]).to_payload()
    if field in ("key", "residual"):
        payload["entries"][0][field][0][0] += 1.0
    else:
        payload["entries"][0][field] += 1.0
    with pytest.raises(ValueError, match="digest mismatch"):
        EpisodicResidualMemory.from_payload(payload)


@pytest.mark.parametrize(
    "field,value",
    [("entry_count", 99), ("entry_count", True), ("maximum_neighbors", 1.5), ("temperature", True)],
)
def test_replayed_memory_rejects_inconsistent_metadata(field, value):
    payload = EpisodicResidualMemory([_entry()]).to_payload()
    payload[field] = value
    with pytest.raises(ValueError):
        EpisodicResidualMemory.from_payload(payload)


def test_legacy_v1_memory_requires_explicit_regeneration():
    payload = EpisodicResidualMemory([_entry()]).to_payload()
    payload["schema"] = "siderea.space_jepa_v2_memory.v1"
    with pytest.raises(ValueError, match="rebuild"):
        EpisodicResidualMemory.from_payload(payload)


def test_duplicate_entry_ids_are_rejected_before_weighting():
    with pytest.raises(ValueError, match="unique"):
        EpisodicResidualMemory([_entry(), _entry(source_group="another-training-source")])


@pytest.mark.parametrize("field", ["key", "residual"])
def test_hashed_entry_arrays_cannot_be_mutated_or_reenabled_for_writing(field):
    entry = _entry()
    array = getattr(entry, field)
    with pytest.raises(ValueError):
        array[0, 0] = 9.0
    with pytest.raises(ValueError):
        array.setflags(write=True)


def test_memory_snapshots_the_caller_arrays_and_metric_weights():
    key = np.zeros((2, 4))
    weights = np.array([1.0, 2.0])
    memory = EpisodicResidualMemory([_entry(key=key)], metric_weights=weights)
    original = memory.to_payload()
    key[:] = 99.0
    weights[:] = 99.0
    assert memory.to_payload() == original
    with pytest.raises(ValueError):
        memory.metric_weights.setflags(write=True)


def _routing_input() -> dict:
    return {
        "base_forecast": [[[0.0, 0.0, 0.0, 0.0]], [[0.0, 0.0, 0.0, 0.0]]],
        "observed_target": [[[0.0, 0.0, 0.0, 0.0]], [[0.0, 0.0, 0.0, 0.0]]],
        "covariance": np.eye(8).tolist(),
        "memory_query": np.zeros((2, 4)).tolist(),
        "query_source_group": "query-source",
        "query_cutoff_mjd": 15.0,
        "population": "A",
        "calibration": "v1",
        "physics_status": "unavailable",
    }


def test_cli_excludes_delayed_residual_and_binds_memory_identity(tmp_path: Path):
    entries = tmp_path / "entries.json"
    bank = tmp_path / "memory.json"
    request = tmp_path / "query.json"
    output = tmp_path / "route.json"
    entries.write_text(json.dumps([_entry().to_mapping()]))
    request.write_text(json.dumps(_routing_input()))
    assert main(["space-jepa-2-memory-build", str(entries), str(bank)]) == 0
    saved = json.loads(bank.read_text())
    assert saved["schema"] == MEMORY_CONTRACT_VERSION
    assert main(["space-jepa-2-route", str(request), str(output), "--memory", str(bank)]) == 0
    result = json.loads(output.read_text())
    assert result["schema"] == "siderea.space_jepa_v2_dual_route.v2"
    assert result["memory_route"]["status"] == "unsupported"
    assert result["memory_route"]["memory_digest"] == saved["memory_digest"]
    assert result["memory_route"]["eligibility"]["query_cutoff_mjd"] == 15.0
    assert result["corrected_forecast"] == result["base_forecast"]


def test_cli_rejects_tampered_availability_without_publishing(tmp_path: Path):
    memory = EpisodicResidualMemory([_entry()])
    payload = deepcopy(memory.to_payload())
    payload["entries"][0]["available_at_mjd"] = 11.0
    bank, request, output = (tmp_path / name for name in ("bank.json", "query.json", "out.json"))
    bank.write_text(json.dumps(payload))
    before = bank.read_bytes()
    request.write_text(json.dumps(_routing_input()))
    assert main(["space-jepa-2-route", str(request), str(output), "--memory", str(bank)]) != 0
    assert not output.exists()
    assert bank.read_bytes() == before
