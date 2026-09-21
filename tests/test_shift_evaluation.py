from __future__ import annotations

import math

import pytest

from siderea.shift_evaluation import (
    DetectionEvent,
    population_transfer_report,
    time_to_detection_report,
)


def test_population_transfer_requires_frozen_complete_assignment() -> None:
    with pytest.raises(ValueError, match="lack a frozen split role"):
        population_transfer_report(
            [1, 0, 1],
            [0.9, 0.2, 0.8],
            ["A", "A", "B"],
            in_population=["A"],
            held_population=["C"],
        )


def test_population_transfer_rejects_overlap() -> None:
    with pytest.raises(ValueError, match="overlap"):
        population_transfer_report(
            [1, 0, 1, 0],
            [0.9, 0.1, 0.8, 0.2],
            ["A", "A", "B", "B"],
            in_population=["A", "B"],
            held_population=["B"],
        )


def test_population_transfer_reports_degradation() -> None:
    report = population_transfer_report(
        [1, 0, 1, 0, 1, 0, 1, 0],
        [0.9, 0.1, 0.8, 0.2, 0.55, 0.45, 0.4, 0.6],
        ["train", "train", "train", "train", "held", "held", "held", "held"],
        in_population=["train"],
        held_population=["held"],
    )
    macro = report["macro"]
    assert macro["in_population_auroc"] == 1.0
    assert macro["held_population_auroc"] == 0.25
    assert macro["auroc_delta_held_minus_in"] == -0.75


def test_population_transfer_excludes_undefined_ap_from_macro() -> None:
    report = population_transfer_report(
        [1, 0, 0, 0, 1, 0],
        [0.9, 0.1, 0.8, 0.2, 0.9, 0.1],
        ["in", "in", "held-empty", "held-empty", "held-valid", "held-valid"],
        in_population=["in"],
        held_population=["held-empty", "held-valid"],
    )
    per_population = {row["population"]: row for row in report["per_population"]}
    assert per_population["held-empty"]["positives"] == 0
    assert per_population["held-empty"]["average_precision"] is None
    assert per_population["held-valid"]["average_precision"] == 1.0
    assert report["macro"]["held_population_average_precision"] == 1.0
    assert report["macro"]["average_precision_delta_held_minus_in"] == 0.0


def test_auroc_is_tie_aware() -> None:
    report = population_transfer_report(
        [1, 0, 1, 0],
        [0.5, 0.5, 0.5, 0.5],
        ["A", "A", "B", "B"],
        in_population=["A"],
        held_population=["B"],
    )
    for row in report["per_population"]:
        assert row["auroc"] == 0.5


def test_calibration_is_opt_in() -> None:
    report = population_transfer_report(
        [1, 0, 1, 0],
        [0.9, 0.1, 0.8, 0.2],
        ["A", "A", "B", "B"],
        in_population=["A"],
        held_population=["B"],
    )
    assert all(item["brier_score"] is None for item in report["per_population"])


def test_detection_report_keeps_undetected_separate() -> None:
    report = time_to_detection_report(
        [
            DetectionEvent("a", "Ia", 100.0, 101.0),
            DetectionEvent("b", "Ia", 100.0, None),
            DetectionEvent("c", "II", 200.0, 205.0),
        ]
    )
    overall = report["overall"]
    assert overall["n_annotated"] == 3
    assert overall["n_detected"] == 2
    assert overall["n_undetected"] == 1
    assert math.isclose(overall["detection_rate"], 2 / 3)
    assert overall["signed_delay_median"] == 3.0


def test_detection_report_preserves_pre_onset_alerts() -> None:
    report = time_to_detection_report(
        [
            DetectionEvent("a", "Ia", 100.0, 99.0),
            DetectionEvent("b", "Ia", 100.0, 102.0),
        ]
    )
    overall = report["overall"]
    assert overall["pre_onset_detection_count"] == 1
    assert overall["signed_delay_median"] == 0.5
    assert overall["post_onset_delay_median"] == 2.0


def test_duplicate_detection_object_rejected() -> None:
    event = DetectionEvent("dup", "Ia", 100.0, 101.0)
    with pytest.raises(ValueError, match="duplicate object_id"):
        time_to_detection_report([event, event])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_detection_event_rejects_nonfinite_onset(bad: float) -> None:
    with pytest.raises(ValueError, match="onset_time"):
        DetectionEvent("a", "Ia", bad, None)


def test_population_transfer_rejects_nonfinite_scores() -> None:
    with pytest.raises(ValueError, match="finite"):
        population_transfer_report(
            [1, 0],
            [0.9, float("nan")],
            ["A", "B"],
            in_population=["A"],
            held_population=["B"],
        )


@pytest.mark.parametrize("bad", ["1", 1.0, object()])
def test_population_transfer_rejects_non_typed_binary_labels(bad: object) -> None:
    with pytest.raises(ValueError, match="typed integer/boolean"):
        population_transfer_report(
            [bad, 0],
            [0.9, 0.1],
            ["A", "B"],
            in_population=["A"],
            held_population=["B"],
        )


@pytest.mark.parametrize(
    ("in_population", "held_population"),
    [
        ([1], ["B"]),
        (["A "], ["B"]),
        (["A", "A"], ["B"]),
        (["A"], ["B", "B"]),
    ],
)
def test_population_transfer_rejects_malformed_population_declarations(
    in_population: list[object], held_population: list[object]
) -> None:
    with pytest.raises(ValueError):
        population_transfer_report(
            [1, 0],
            [0.9, 0.1],
            ["A", "B"],
            in_population=in_population,  # type: ignore[arg-type]
            held_population=held_population,  # type: ignore[arg-type]
        )
