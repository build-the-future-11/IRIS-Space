from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from siderea.ml.episodic_memory import EpisodicResidualMemory, MemoryEntry


def _entry(name: str = "training-1", *, population: str = "A") -> MemoryEntry:
    return MemoryEntry(
        name, np.zeros((2, 4)), np.ones((2, 4)), "training", 1.0, population, "cal-v1"
    )


def _retrieve(memory: EpisodicResidualMemory, **overrides: Any) -> Any:
    options: dict[str, Any] = {
        "query_source_group": "held-out",
        "query_cutoff_mjd": 2.0,
        "population": "A",
        "calibration": "cal-v1",
    }
    options.update(overrides)
    return memory.retrieve(np.zeros((2, 4)), np.zeros((2, 4)), **options)


@pytest.mark.parametrize("field", ["key", "residual"])
def test_entry_buffers_cannot_change_after_identity_is_recorded(field: str) -> None:
    memory = EpisodicResidualMemory([_entry()])
    before = _retrieve(memory)
    digest = memory.digest
    array = getattr(memory.entries[0], field)
    with pytest.raises(ValueError):
        array[0, 0] = 10.0
    with pytest.raises(ValueError):
        array.setflags(write=True)
    with pytest.raises(ValueError):
        array.view().setflags(write=True)
    assert memory.digest == digest
    np.testing.assert_array_equal(_retrieve(memory).corrected, before.corrected)


def test_entry_owns_an_immutable_snapshot_of_caller_arrays() -> None:
    key = np.zeros((2, 4))
    residual = np.ones((2, 4))
    entry = MemoryEntry("id", key, residual, "training", 1.0, "A", "cal-v1")
    key[:] = 5.0
    residual[:] = 9.0
    np.testing.assert_array_equal(entry.key, np.zeros((2, 4)))
    np.testing.assert_array_equal(entry.residual, np.ones((2, 4)))


@pytest.mark.parametrize(
    ("field", "replacement"),
    [("entries", ()), ("temperature", 2.0), ("maximum_neighbors", 1), ("digest", "fake")],
)
def test_bank_configuration_cannot_diverge_from_its_digest(field: str, replacement: Any) -> None:
    memory = EpisodicResidualMemory([_entry()])
    with pytest.raises(FrozenInstanceError):
        setattr(memory, field, replacement)


def test_metric_buffer_cannot_be_mutated_or_made_writable() -> None:
    memory = EpisodicResidualMemory([_entry()])
    with pytest.raises(ValueError):
        memory.metric_weights[0] = 5.0
    with pytest.raises(ValueError):
        memory.metric_weights.setflags(write=True)


def test_array_metadata_changes_cannot_change_memory_identity() -> None:
    memory = EpisodicResidualMemory([_entry()])
    original = _retrieve(memory)
    key = memory.entries[0].key
    key.shape = (1, 8)
    residual = memory.entries[0].residual
    residual.dtype = np.uint8
    metric = memory.metric_weights
    metric.shape = (1, 2)
    assert memory.entries[0].key.shape == (2, 4)
    assert memory.entries[0].residual.dtype == np.dtype(np.float64)
    assert memory.metric_weights.shape == (2,)
    np.testing.assert_array_equal(_retrieve(memory).corrected, original.corrected)


def test_repeated_entry_ids_do_not_create_ambiguous_neighbor_evidence() -> None:
    with pytest.raises(ValueError, match="unique"):
        EpisodicResidualMemory([_entry(), _entry()])


@pytest.mark.parametrize("value", [True, 1.5, "2", np.nan])
def test_neighbor_count_is_an_integer_before_retrieval(value: Any) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        EpisodicResidualMemory([_entry()], maximum_neighbors=value)


@pytest.mark.parametrize("value", [True, "1", np.nan, np.inf])
def test_temperature_rejects_ambiguous_or_nonfinite_values(value: Any) -> None:
    with pytest.raises(ValueError, match="temperature"):
        EpisodicResidualMemory([_entry()], temperature=value)


@pytest.mark.parametrize("value", [True, "2", np.nan, np.inf])
def test_query_cutoff_is_a_finite_real_value(value: Any) -> None:
    with pytest.raises(ValueError, match="query_cutoff_mjd"):
        _retrieve(EpisodicResidualMemory([_entry()]), query_cutoff_mjd=value)


@pytest.mark.parametrize("flag", ["false", 0, 1, None])
def test_cross_population_control_cannot_be_enabled_by_truthiness(flag: Any) -> None:
    memory = EpisodicResidualMemory([_entry(population="B")])
    with pytest.raises(ValueError, match="allow_cross_population"):
        _retrieve(memory, allow_cross_population=flag)
    assert not _retrieve(memory).supported
    assert _retrieve(memory, allow_cross_population=True).supported


@pytest.mark.parametrize("gate", [True, "0", -1.0, np.nan, np.inf])
def test_forced_gate_is_checked_even_when_the_bank_has_no_support(gate: Any) -> None:
    memory = EpisodicResidualMemory([_entry(population="B")])
    with pytest.raises(ValueError, match="force_gate"):
        _retrieve(memory, force_gate=gate)


@pytest.mark.parametrize(
    "array",
    [np.ones((2, 4), dtype=complex), np.ones((2, 4), dtype=bool), np.full((2, 4), "1")],
)
def test_entry_cannot_silently_drop_input_types(array: Any) -> None:
    with pytest.raises(ValueError, match="key"):
        MemoryEntry("id", array, np.ones((2, 4)), "training", 1.0, "A", "cal-v1")


def test_mixed_boolean_numeric_keys_are_rejected_before_coercion() -> None:
    with pytest.raises(ValueError, match="key"):
        MemoryEntry(
            "id", [[True, 0.0, 0.0, 0.0]], [[1.0, 1.0, 1.0, 1.0]], "training", 1.0, "A", "cal"
        )


def test_mixed_boolean_numeric_metric_is_rejected_before_coercion() -> None:
    with pytest.raises(ValueError, match="metric_weights"):
        EpisodicResidualMemory([_entry()], metric_weights=[True, 1.0])


def test_empty_channels_are_not_a_valid_memory() -> None:
    with pytest.raises(ValueError, match="key"):
        MemoryEntry("id", np.empty((0, 4)), np.empty((0, 4)), "group", 1.0, "A", "cal")


def test_large_finite_metric_weights_keep_their_relative_geometry() -> None:
    ordinary = EpisodicResidualMemory([_entry()], metric_weights=[1.0, 1.0])
    scaled = EpisodicResidualMemory([_entry()], metric_weights=[1e308, 1e308])
    np.testing.assert_array_equal(scaled.metric_weights, ordinary.metric_weights)
    assert scaled.digest == ordinary.digest


def test_unrepresentable_distance_is_rejected_before_softmax_can_emit_nan() -> None:
    memory = EpisodicResidualMemory([_entry()])
    with pytest.raises(ValueError, match="distance"):
        memory.retrieve(
            np.full((2, 4), 1e200),
            np.zeros((2, 4)),
            query_source_group="held-out",
            query_cutoff_mjd=2.0,
            population="A",
            calibration="cal-v1",
        )


def test_unrepresentable_forecast_correction_is_rejected() -> None:
    entry = MemoryEntry(
        "id", np.zeros((2, 4)), np.full((2, 4), 1e308), "training", 1.0, "A", "cal-v1"
    )
    memory = EpisodicResidualMemory([entry])
    with pytest.raises(ValueError, match="correction"):
        memory.retrieve(
            np.zeros((2, 4)),
            np.full((2, 4), 1.7e308),
            query_source_group="held-out",
            query_cutoff_mjd=2.0,
            population="A",
            calibration="cal-v1",
        )


def _artifact() -> dict[str, Any]:
    # Legacy CLI files retained raw JSON integers but hashed float cutoffs.
    entries = [
        {
            "entry_id": "training-1",
            "key": np.zeros((2, 4)).tolist(),
            "residual": np.ones((2, 4)).tolist(),
            "source_group": "training",
            "cutoff_mjd": 1,
            "population": "A",
            "calibration": "cal-v1",
        }
    ]
    return {
        "schema": "siderea.space_jepa_v2_memory.v1",
        "entry_count": 1,
        "temperature": 1.0,
        "maximum_neighbors": 16,
        "memory_digest": EpisodicResidualMemory([_entry()]).digest,
        "entries": entries,
    }


def test_valid_legacy_memory_artifact_reconstructs_its_exact_digest() -> None:
    artifact = _artifact()
    restored = EpisodicResidualMemory.from_artifact(artifact)
    assert restored.digest == artifact["memory_digest"]
    np.testing.assert_array_equal(_retrieve(restored).corrected, np.full((2, 4), 0.5))


@pytest.mark.parametrize(
    "field", ["residual", "key", "temperature", "digest", "count", "schema", "fractional_count"]
)
def test_memory_artifact_cannot_silently_ignore_tampered_identity(field: str) -> None:
    artifact = deepcopy(_artifact())
    if field in {"residual", "key"}:
        artifact["entries"][0][field][0][0] = 10.0
    elif field == "temperature":
        artifact["temperature"] = 2.0
    elif field == "digest":
        artifact["memory_digest"] = "0" * 64
    elif field == "count":
        artifact["entry_count"] = 2
    elif field == "fractional_count":
        artifact["maximum_neighbors"] = 1.5
    else:
        artifact["schema"] = "unknown"
    with pytest.raises(ValueError):
        EpisodicResidualMemory.from_artifact(artifact)


def test_cli_rejects_changed_memory_before_publishing_route(tmp_path: Path) -> None:
    from siderea.cli import main

    memory = tmp_path / "memory.json"
    artifact = _artifact()
    artifact["entries"][0]["residual"][0][0] = 99.0
    memory.write_text(json.dumps(artifact))
    inputs = tmp_path / "input.json"
    inputs.write_text("{}")
    output = tmp_path / "route.json"
    assert main(["space-jepa-2-route", str(inputs), str(output), "--memory", str(memory)]) == 2
    assert not output.exists()
