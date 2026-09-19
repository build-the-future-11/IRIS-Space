from __future__ import annotations

import pandas as pd
import pytest

from siderea.provenance import digest_value
from siderea.research.space_jepa_v2_benchmark import (
    extrapolation_forecast,
    run_space_jepa_v2_benchmark,
    verify_complete_grid,
)
from siderea.research.space_jepa_v2_pipeline import assemble_space_jepa_v2_shadow_evidence


def test_extrapolation_baselines_degrade_with_short_history() -> None:
    target = [3.0, 4.0]
    assert extrapolation_forecast([0.0], [5.0], target, degree=2) == [5.0, 5.0]
    assert extrapolation_forecast([0.0, 1.0], [0.0, 2.0], [2.0], degree=1) == pytest.approx([4.0])


def test_complete_grid_requires_failure_receipts() -> None:
    rows = [{"model": "a", "seed": 1, "fold": "f", "horizon_days": 1.0, "status": "failed"}]
    assert (
        verify_complete_grid(rows, models=["a"], seeds=[1], folds=["f"], horizons_days=[1.0])[
            "failed_cells"
        ]
        == 1
    )
    with pytest.raises(ValueError, match="missing"):
        verify_complete_grid(rows, models=["a", "b"], seeds=[1], folds=["f"], horizons_days=[1.0])


def test_fixed_budget_benchmark_and_pipeline_join() -> None:
    frame = pd.DataFrame(
        {
            "entity": [f"e{i}" for i in range(8)],
            "label": [1, 0, 1, 0, 1, 0, 0, 0],
            "incumbent": [8, 7, 6, 5, 4, 3, 2, 1],
            "aqpm": [8, 1, 7, 2, 6, 5, 4, 3],
        }
    )
    result = run_space_jepa_v2_benchmark(
        frame,
        entity_column="entity",
        label_column="label",
        score_columns=["incumbent", "aqpm"],
        review_budget=3,
        bootstrap_repeats=100,
    )
    assert result["metrics"]["aqpm"]["recall"] == 1.0

    candidates = {
        "schema": "siderea.candidates.v1",
        "candidates": [{"candidate_id": "a"}],
    }
    evaluation_identity = {
        "schema": "siderea.space_jepa_v2_evaluation.v1",
        "rows": [{"example_id": "a", "mean_absolute_latent_error": [1.0, 2.0]}],
    }
    evaluation = {
        **evaluation_identity,
        "result_digest": digest_value(evaluation_identity),
    }
    evidence = assemble_space_jepa_v2_shadow_evidence(candidates, evaluation)
    assert evidence["reporting_authorized"] is False
    assert evidence["rows"][0]["review_priority"] == 2.0
