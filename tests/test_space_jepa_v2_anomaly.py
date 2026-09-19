from __future__ import annotations

import numpy as np

from siderea.ml.space_jepa_v2_anomaly import (
    anomaly_components,
    fit_training_covariance,
    summarize_anomaly_trace,
)


def test_components_preserve_base_and_corrected_surprise() -> None:
    covariance = fit_training_covariance(np.eye(8))
    target = np.zeros((2, 4))
    base = np.ones((2, 4))
    corrected = np.full((2, 4), 0.5)
    result = anomaly_components(
        target=target,
        base_prediction=base,
        corrected_prediction=corrected,
        covariance=covariance,
        memory_distance=1.0,
        memory_entropy=0.2,
        physics_residual=0.3,
    )
    assert result.predictive_surprise > result.corrected_surprise
    assert result.route_disagreement > 0.0


def test_trace_summary_retains_local_peak_and_run() -> None:
    result = summarize_anomaly_trace([1.0, 2.0, 4.0, 5.0], [0.0, 10.0, 9.0, 0.0], threshold=8.0)
    assert result["maximum"] == 10.0
    assert result["consecutive_run_length"] == 2
    assert result["first_threshold_crossing_mjd"] == 2.0
