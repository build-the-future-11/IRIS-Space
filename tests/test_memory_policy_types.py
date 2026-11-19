"""Malformed policy flags cannot broaden the eligible residual population."""

import numpy as np
import pytest

from siderea.ml.episodic_memory import EpisodicResidualMemory, MemoryEntry


def memory():
    return EpisodicResidualMemory(
        [MemoryEntry("a", np.zeros((1, 4)), np.ones((1, 4)), "training", 1.0, "other", "v1", 2.0)]
    )


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None])
def test_cross_population_override_requires_explicit_boolean(value):
    with pytest.raises(ValueError, match="allow_cross_population"):
        memory().retrieve(
            np.zeros((1, 4)),
            np.zeros((1, 4)),
            query_source_group="query",
            query_cutoff_mjd=3.0,
            population="query_population",
            calibration="v1",
            allow_cross_population=value,
        )


@pytest.mark.parametrize("value", [True, "0.5", np.nan, -0.1, 1.1])
@pytest.mark.parametrize("eligible", [True, False])
def test_invalid_forced_gate_rejected_independently_of_eligibility(value, eligible):
    with pytest.raises(ValueError, match="force_gate"):
        memory().retrieve(
            np.zeros((1, 4)),
            np.zeros((1, 4)),
            query_source_group="query",
            query_cutoff_mjd=3.0,
            population="other" if eligible else "absent",
            calibration="v1",
            force_gate=value,
        )


def test_explicit_override_preserves_the_declared_population_control():
    args = dict(
        query_source_group="query",
        query_cutoff_mjd=3.0,
        population="query_population",
        calibration="v1",
    )
    assert not memory().retrieve(np.zeros((1, 4)), np.zeros((1, 4)), **args).supported
    assert (
        memory()
        .retrieve(np.zeros((1, 4)), np.zeros((1, 4)), allow_cross_population=True, **args)
        .supported
    )
