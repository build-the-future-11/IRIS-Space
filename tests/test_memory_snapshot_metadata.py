"""Array metadata must not mutate an already digested memory snapshot."""

import numpy as np
import pytest

from siderea.ml.episodic_memory import EpisodicResidualMemory, MemoryEntry


def _array(memory, name):
    if name in {"key", "residual"}:
        return getattr(memory.entries[0], name)
    return getattr(memory, name)


@pytest.mark.parametrize(
    "name", ["key", "residual", "metric_weights", "_metric_input", "_keys", "_residuals"]
)
@pytest.mark.parametrize("mutation", ["shape", "dtype"])
def test_exposed_array_metadata_cannot_change_digest_bound_retrieval(name, mutation):
    memory = EpisodicResidualMemory(
        [
            MemoryEntry(
                "x",
                np.ones((2, 4)),
                np.ones((2, 4)),
                "other",
                1.0,
                "A",
                "cal",
                available_at_mjd=2.0,
            )
        ]
    )

    def retrieve():
        return memory.retrieve(
            np.zeros((2, 4)),
            np.zeros((2, 4)),
            query_source_group="query",
            query_cutoff_mjd=10.0,
            population="A",
            calibration="cal",
        )

    before = retrieve()
    digest = memory.digest
    payload = memory.to_payload()
    exposed = _array(memory, name)
    expected_shape = exposed.shape
    if mutation == "shape":
        exposed.shape = (1, exposed.size)
    else:
        exposed.dtype = np.uint64

    fresh = _array(memory, name)
    assert fresh.shape == expected_shape
    assert fresh.dtype == np.dtype(np.float64)
    after = retrieve()
    assert memory.digest == digest
    assert memory.to_payload() == payload
    assert EpisodicResidualMemory.from_payload(payload).digest == digest
    assert after.nearest_distance == before.nearest_distance
    assert after.neighbor_ids == before.neighbor_ids
    np.testing.assert_array_equal(after.corrected, before.corrected)


def test_metadata_views_do_not_remove_read_only_buffer_protection():
    entry = MemoryEntry(
        "x", np.ones((2, 4)), np.ones((2, 4)), "other", 1.0, "A", "cal", available_at_mjd=2.0
    )
    memory = EpisodicResidualMemory([entry])
    for name in ("key", "residual", "metric_weights", "_metric_input", "_keys", "_residuals"):
        with pytest.raises(ValueError):
            _array(memory, name).setflags(write=True)
