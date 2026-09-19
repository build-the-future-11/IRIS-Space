from __future__ import annotations

import numpy as np

from siderea.ml.episodic_memory import EpisodicResidualMemory, MemoryEntry


def _entry(
    name: str, value: float, group: str, cutoff: float, population: str = "A"
) -> MemoryEntry:
    key = np.full((2, 4), value)
    residual = np.full((2, 4), value / 10.0)
    return MemoryEntry(name, key, residual, group, cutoff, population, "cal-v1")


def test_memory_excludes_same_source_future_and_wrong_population() -> None:
    memory = EpisodicResidualMemory(
        [
            _entry("self", 0.0, "source-a", 1.0),
            _entry("good", 0.1, "source-b", 1.0),
            _entry("future", 0.0, "source-c", 20.0),
            _entry("wrong", 0.0, "source-d", 1.0, "B"),
        ]
    )
    result = memory.retrieve(
        np.zeros((2, 4)),
        np.zeros((2, 4)),
        query_source_group="source-a",
        query_cutoff_mjd=10.0,
        population="A",
        calibration="cal-v1",
    )
    assert result.neighbor_ids == ("good",)
    assert result.supported


def test_memory_returns_base_when_no_support() -> None:
    memory = EpisodicResidualMemory([_entry("only", 0.0, "source-a", 1.0)])
    base = np.ones((2, 4))
    result = memory.retrieve(
        np.zeros((2, 4)),
        base,
        query_source_group="source-a",
        query_cutoff_mjd=10.0,
        population="A",
        calibration="cal-v1",
    )
    assert not result.supported
    assert result.gate == 0.0
    assert np.array_equal(result.corrected, base)


def test_forced_gate_controls_correction() -> None:
    memory = EpisodicResidualMemory([_entry("other", 0.0, "source-b", 1.0)])
    base = np.ones((2, 4))
    closed = memory.retrieve(
        np.zeros((2, 4)),
        base,
        query_source_group="source-a",
        query_cutoff_mjd=10.0,
        population="A",
        calibration="cal-v1",
        force_gate=0.0,
    )
    assert np.array_equal(closed.corrected, base)
