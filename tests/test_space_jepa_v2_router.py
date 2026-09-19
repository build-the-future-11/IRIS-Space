from __future__ import annotations

import numpy as np

from siderea.ml.episodic_memory import EpisodicResidualMemory, MemoryEntry
from siderea.ml.space_jepa_v2_router import route_space_jepa_v2_evidence


def test_dual_router_keeps_prediction_anomaly_memory_and_physics_inspectable() -> None:
    base = np.zeros((2, 1, 4))
    target = np.ones((2, 1, 4)) * 0.25
    key = np.zeros((2, 4))
    memory = EpisodicResidualMemory(
        [
            MemoryEntry(
                entry_id="training-neighbor",
                key=key,
                residual=np.ones((2, 4)) * 0.1,
                source_group="training-object",
                cutoff_mjd=59_000.0,
                population="A",
                calibration="cal-v1",
            )
        ]
    )
    result = route_space_jepa_v2_evidence(
        base_forecast=base,
        observed_target=target,
        covariance=np.eye(8),
        memory=memory,
        memory_query=key,
        query_source_group="held-out-object",
        query_cutoff_mjd=60_000.0,
        population="A",
        calibration="cal-v1",
        physics_residual=0.2,
        physics_status="physics_identifiable",
        score_weights={"corrected_surprise": 1.0, "physics_residual": 0.5},
    )
    assert result["memory_route"]["status"] == "applied"
    assert result["anomaly_route"]["status"] == "evaluated"
    assert result["physics_route"]["status"] == "physics_identifiable"
    assert result["ranking_score"] is not None
    assert result["reporting_authorized"] is False


def test_dual_router_memory_off_is_explicit() -> None:
    base = np.zeros((1, 1, 4))
    result = route_space_jepa_v2_evidence(
        base_forecast=base,
        observed_target=base,
        covariance=np.eye(4),
        memory=None,
        memory_query=None,
        query_source_group="object",
        query_cutoff_mjd=60_000.0,
        population="A",
        calibration="cal-v1",
        physics_residual=None,
        physics_status="physics_not_identifiable",
    )
    assert result["memory_route"]["status"] == "memory_off"
    assert result["ranking_score"] is None
