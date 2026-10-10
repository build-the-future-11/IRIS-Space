"""Exact generated-array checks for the retrieval kernel and its snapshot identity."""

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from siderea.ml.episodic_memory import EpisodicResidualMemory, MemoryEntry


def _entry(name="first", key=None, residual=None):
    return MemoryEntry(
        name,
        np.zeros((2, 4)) if key is None else key,
        np.ones((2, 4)) if residual is None else residual,
        "other-source",
        1.0,
        "A",
        "cal-v1",
    )


def _retrieve(memory, query=None, **kwargs):
    return memory.retrieve(
        np.zeros((2, 4)) if query is None else query,
        np.zeros((2, 4)),
        query_source_group="query-source",
        query_cutoff_mjd=10.0,
        population="A",
        calibration="cal-v1",
        **kwargs,
    )


def test_caller_and_exposed_arrays_cannot_change_digest_bound_prediction():
    key, residual = np.zeros((2, 4)), np.ones((2, 4))
    memory = EpisodicResidualMemory([_entry(key=key, residual=residual)])
    before = _retrieve(memory)
    digest = memory.digest
    key[:] = 9.0
    residual[:] = -99.0
    for array in (memory.entries[0].key, memory.entries[0].residual, memory.metric_weights):
        with pytest.raises(ValueError):
            array.flat[0] = 42.0
        with pytest.raises(ValueError):
            array.setflags(write=True)
    with pytest.raises(FrozenInstanceError):
        memory.temperature = 17.0
    with pytest.raises(FrozenInstanceError):
        memory.entries = ()
    after = _retrieve(memory)
    assert memory.digest == digest
    np.testing.assert_array_equal(after.corrected, before.corrected)


def test_vectorized_kernel_matches_independent_scalar_calculation():
    rng = np.random.default_rng(4)
    entries = [_entry(str(i), rng.normal(size=(2, 4)), rng.normal(size=(2, 4))) for i in range(31)]
    query = rng.normal(size=(2, 4))
    metric = np.array([0.25, 1.75])
    temperature = 0.7
    memory = EpisodicResidualMemory(
        entries, metric_weights=metric, temperature=temperature, maximum_neighbors=5
    )
    got = _retrieve(memory, query, force_gate=0.25)
    distances = [
        sum(
            metric[c] * sum((query[c, q] - entry.key[c, q]) ** 2 for q in range(4))
            for c in range(2)
        )
        / 2
        for entry in entries
    ]
    selected = sorted(range(len(entries)), key=lambda i: (distances[i], entries[i].entry_id))[:5]
    weights = np.exp(-(np.array([distances[i] for i in selected]) - min(distances)) / temperature)
    weights /= weights.sum()
    expected = sum(
        weight * entries[i].residual for weight, i in zip(weights, selected, strict=True)
    )
    assert got.neighbor_ids == tuple(entries[i].entry_id for i in selected)
    np.testing.assert_allclose(got.weights, weights, rtol=1e-13, atol=1e-15)
    np.testing.assert_allclose(got.corrected, 0.25 * expected, rtol=1e-13, atol=1e-15)


def test_equal_distances_use_stable_entry_identity_at_cutoff():
    entries = [_entry(name) for name in ["c", "a", "b"]]
    first = EpisodicResidualMemory(entries, maximum_neighbors=2)
    second = EpisodicResidualMemory(reversed(entries), maximum_neighbors=2)
    assert _retrieve(first).neighbor_ids == _retrieve(second).neighbor_ids == ("a", "b")


def test_large_metric_weights_preserve_the_same_distance_geometry():
    entry = _entry(key=np.ones((2, 4)))
    normal = _retrieve(EpisodicResidualMemory([entry], metric_weights=[1.0, 1.0]))
    large = _retrieve(EpisodicResidualMemory([entry], metric_weights=[1e308, 1e308]))
    assert large.nearest_distance == normal.nearest_distance == 4.0
    np.testing.assert_array_equal(large.corrected, normal.corrected)


@pytest.mark.parametrize("neighbors", [1.1, 0, -1, True, np.bool_(True), "2"])
def test_neighbor_count_rejects_lossy_or_ambiguous_values(neighbors):
    with pytest.raises(ValueError, match="positive integer"):
        EpisodicResidualMemory([_entry()], maximum_neighbors=neighbors)


def test_numpy_integer_neighbor_count_is_serializable():
    memory = EpisodicResidualMemory([_entry()], maximum_neighbors=np.int64(2))
    assert len(memory.digest) == 64
    assert _retrieve(memory).supported


@pytest.mark.parametrize(
    "value", [np.empty((0, 4)), np.ones((2, 4), dtype=complex), np.ones((2, 4), dtype=bool)]
)
def test_empty_or_lossily_cast_quaternion_inputs_are_rejected(value):
    with pytest.raises(ValueError):
        _entry(key=value, residual=value)


def test_duplicate_entry_identity_is_rejected():
    with pytest.raises(ValueError, match="unique"):
        EpisodicResidualMemory([_entry(), _entry()])


def test_overflowing_distance_is_reported_instead_of_nan_retrieval():
    memory = EpisodicResidualMemory([_entry(key=np.full((2, 4), 1e308))])
    with pytest.raises(ValueError, match="distance exceeds"):
        _retrieve(memory)


def test_gate_validation_does_not_depend_on_whether_support_exists():
    memory = EpisodicResidualMemory(
        [MemoryEntry("x", np.zeros((2, 4)), np.zeros((2, 4)), "query-source", 1.0, "A", "cal-v1")]
    )
    with pytest.raises(ValueError, match="force_gate"):
        _retrieve(memory, force_gate=float("nan"))
