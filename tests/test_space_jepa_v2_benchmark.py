from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from siderea.evaluation import ranking_metrics
from siderea.provenance import digest_value
from siderea.research.space_jepa_v2_benchmark import (
    _bootstrap_budget_recall,
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


def _tied_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "entity": ["d", "c", "b", "a"],
            "label": [1, 0, 1, 0],
            "incumbent": [0.5, 0.5, 0.5, 0.5],
            "candidate": [0.9, 0.2, 0.9, 0.2],
        }
    )


def _run(frame: pd.DataFrame, **options: object) -> dict:
    arguments = dict(
        entity_column="entity",
        label_column="label",
        score_columns=["incumbent", "candidate"],
        review_budget=1,
        bootstrap_repeats=100,
    )
    return run_space_jepa_v2_benchmark(frame, **(arguments | options))


def test_tied_rankings_and_bootstrap_are_invariant_to_input_order() -> None:
    frame = _tied_frame()
    result = _run(frame)
    assert result == _run(frame.iloc[::-1])
    assert result == _run(frame.sample(frac=1, random_state=17))
    assert result["metrics"]["incumbent"]["precision"] == 0.5
    assert result["metrics"]["incumbent"]["recall"] == 0.25
    assert result["metrics"]["incumbent"]["expected_true_positive"] == 0.5
    assert result["metrics"]["incumbent"]["average_precision"] == 0.5
    assert result["schema"].endswith(".v2")
    assert result["paired_recall_differences"]["candidate"]["observed_recall_difference"] == 0.25
    assert "bootstrap_mean_recall_difference" in result["paired_recall_differences"]["candidate"]


@pytest.mark.parametrize("label", [0.5, 1.5, -0.5, float("nan"), float("inf")])
def test_fractional_or_nonfinite_labels_are_rejected_before_integer_conversion(
    label: float,
) -> None:
    frame = _tied_frame().astype({"label": float})
    frame.loc[0, "label"] = label
    with pytest.raises(ValueError, match="labels"):
        _run(frame)


@pytest.mark.parametrize(
    "options",
    [
        {"review_budget": True},
        {"review_budget": 1.5},
        {"bootstrap_repeats": 100.5},
        {"bootstrap_repeats": True},
        {"seed": True},
        {"seed": -1},
        {"confidence_level": True},
        {"confidence_level": float("nan")},
        {"confidence_level": "0.95"},
    ],
)
def test_benchmark_rejects_ambiguous_integer_options(options: dict) -> None:
    with pytest.raises(ValueError):
        _run(_tied_frame(), **options)


def test_benchmark_rejects_empty_duplicate_and_boolean_score_inputs() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        _run(_tied_frame().iloc[:0])
    duplicate = _tied_frame()
    duplicate.loc[0, "entity"] = " a "
    with pytest.raises(ValueError, match="physical entity"):
        _run(duplicate)
    with pytest.raises(ValueError, match="booleans"):
        _run(_tied_frame().assign(candidate=[True, False, True, False]))
    with pytest.raises(ValueError, match="unique columns"):
        _run(pd.concat([_tied_frame(), _tied_frame()[["label"]]], axis=1))
    with pytest.raises(ValueError, match="distinct roles"):
        _run(_tied_frame(), score_columns=["label", "candidate"])


def test_numpy_integer_options_emit_a_serializable_canonical_report() -> None:
    assert _run(_tied_frame(), review_budget=np.int64(1), seed=np.int64(1701)) == _run(
        _tied_frame()
    )


@pytest.mark.parametrize("column", ["label", "candidate"])
def test_complex_observations_are_rejected_before_lossy_conversion(column: str) -> None:
    frame = _tied_frame().assign(**{column: [1 + 3j, 0j, 1 + 0j, 0j]})
    with pytest.raises(ValueError, match="complex"):
        _run(frame)


def test_vectorized_tied_bootstrap_matches_scalar_metric() -> None:
    labels = np.array([1, 0, 1, 0], dtype=np.int64)
    scores = np.array([0.8, 0.8, 0.3, 0.3], dtype=np.float64)
    indices = np.array([[0, 1, 2, 3], [0, 0, 1, 1], [1, 1, 3, 3]], dtype=np.int64)
    for budget in [1, 2, 4, 10]:
        expected = [
            ranking_metrics(labels[row], scores[row], review_budget=budget).recall_at_k
            for row in indices
        ]
        assert _bootstrap_budget_recall(labels, scores, indices, budget) == pytest.approx(expected)


def test_cohort_digest_binds_scores_and_labels_beyond_summary_metrics() -> None:
    original = _run(_tied_frame())
    changed = _run(_tied_frame().assign(incumbent=[0.6] * 4))
    assert original["metrics"] == changed["metrics"]
    assert original["cohort_digest"] != changed["cohort_digest"]
