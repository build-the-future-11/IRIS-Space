"""Constructed global chronology checks; no training or protected observations."""

from __future__ import annotations

import csv
import importlib.util
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from siderea.ml import space_jepa_population_v1 as population
from siderea.provenance import digest_value

_DEMO_PATH = Path(__file__).parents[1] / "scripts/demo_space_jepa_population_v1.py"
_SPEC = importlib.util.spec_from_file_location("population_as_of_demo", _DEMO_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_DEMO = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_DEMO)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def inputs(tmp_path: Path) -> tuple[Path, Path]:
    paths: tuple[Path, Path] = _DEMO.write_generated_inputs(tmp_path / "inputs")
    rows = read_csv(paths[0])
    for row in rows:
        if row["survey"] == "source_B":
            for key in ("observed_at_mjd", "available_at_mjd"):
                row[key] = str(float(row[key]) + 100.0)
    write_csv(paths[0], rows)
    return paths


def prepare(
    inputs: tuple[Path, Path], directory: Path, fit: Any = 125.0, selection: Any = 135.0
) -> dict[str, Any]:
    return population.prepare_population_batches(
        *inputs,
        directory,
        horizons_days=(1.0, 3.0),
        batch_size=4,
        fit_available_through_mjd=fit,
        selection_available_through_mjd=selection,
    )


def rows(directory: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (directory / "rows.jsonl").read_text().splitlines()]


def admission(directory: Path, split: str) -> dict[str, Any]:
    return json.loads((directory / f"{split}-as-of-admission.json").read_text())


def test_every_emitted_tensor_row_has_global_training_and_selection_chronology(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    output = tmp_path / "prepared"
    result = prepare(inputs, output)
    assert result["schema"] == population.AS_OF_PREPARATION_SCHEMA
    assert result["global_training_before_evaluation_established"] is True
    assert result["global_selection_before_final_evaluation_established"] is True
    assert result["chronology_scope"] == "prepared_data_only; model_fit_or_selection_not_performed"
    assert result["scientific_execution_authorized"] is False
    assert result["as_of_policy_digest"] == digest_value(result["as_of_policy"])
    assert result["result_digest"] == digest_value(
        {key: value for key, value in result.items() if key != "result_digest"}
    )
    for row in rows(output):
        cutoff = row["cutoff_mjd"]
        assert all(item["available_at_mjd"] <= cutoff for item in row["prefix"])
        if row["partition"] in ("train", "validation"):
            upper = 125.0 if row["partition"] == "train" else 135.0
            assert cutoff + 3.0 <= upper
            assert all(
                target["latest_target_available_at_mjd"] <= upper for target in row["targets"]
            )
        if row["partition"] == "validation":
            assert cutoff > 125.0
        if row["partition"] in ("test", "population_b"):
            assert cutoff > 135.0
    for split, receipt in result["splits"].items():
        policy_receipt = receipt["as_of_admission"]
        assert (
            policy_receipt["file_sha256"]
            == sha256((output / policy_receipt["receipt"]).read_bytes()).hexdigest()
        )
        assert policy_receipt["candidate_complete_cutoffs"] == (
            receipt["row_count"] + policy_receipt["excluded_complete_cutoffs"]
        )
        assert admission(output, split)["admitted_complete_cutoffs"] == receipt["row_count"]


def test_post_fit_values_and_channels_cannot_change_training_tensors_or_vocabulary(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    original = prepare(inputs, tmp_path / "original")
    data = read_csv(inputs[0])
    for row in data:
        if row["entity_id"].endswith(":2") and float(row["available_at_mjd"]) > 125.0:
            row["band"] = "future-only-band"
            row["value"] = "432.5"
    write_csv(inputs[0], list(reversed(data)))
    changed = prepare(inputs, tmp_path / "changed")
    assert original["band_to_id"] == changed["band_to_id"]
    assert all("future-only" not in band for band in changed["band_to_id"])
    assert (
        original["splits"]["train"]["tensor_content_digest"]
        == (changed["splits"]["train"]["tensor_content_digest"])
    )


def test_late_targets_are_excluded_whole_instead_of_clipped_to_pass(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    data = read_csv(inputs[0])
    for row in data:
        if row["entity_id"].endswith(":0") and row["observation_id"] == "observation-5":
            row["available_at_mjd"] = "500.0"
    write_csv(inputs[0], data)
    directory = tmp_path / "prepared"
    prepare(inputs, directory)
    excluded = admission(directory, "train")["excluded"]
    witness = next(
        item
        for item in excluded
        if item["physical_entity_id"] == "physical-0" and item["cutoff_mjd"] == 102.0
    )
    assert witness["latest_target_available_at_mjd"] == 500.0
    assert witness["reasons"] == ["target_not_available_by_boundary"]
    assert not any(row["example_id"] == witness["example_id"] for row in rows(directory))
    # The unchanged v1 mode demonstrates exactly why enrollment alone was insufficient.
    legacy = tmp_path / "legacy"
    old = population.prepare_population_batches(
        *inputs, legacy, horizons_days=(1.0, 3.0), batch_size=4
    )
    assert old["schema"] == population.PREPARATION_SCHEMA
    assert old["global_training_before_evaluation_established"] is False
    assert any(row["example_id"] == witness["example_id"] for row in rows(legacy))
    assert "as_of_policy" not in old
    assert not list(legacy.glob("*-as-of-admission.json"))


def test_unfinished_declared_horizon_is_excluded_even_when_supplied_targets_are_early(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    directory = tmp_path / "prepared"
    prepare(inputs, directory, fit=127.0, selection=137.0)
    witness = next(
        item
        for item in admission(directory, "train")["excluded"]
        if item["physical_entity_id"] == "physical-2" and item["cutoff_mjd"] == 126.0
    )
    assert witness["latest_target_available_at_mjd"] == 127.0
    assert witness["declared_horizon_end_mjd"] == 129.0
    assert witness["reasons"] == ["declared_horizon_not_complete_by_boundary"]


def test_label_upper_bound_is_inclusive_and_forecast_lower_bound_is_strict(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    output = tmp_path / "upper"
    prepare(inputs, output)
    assert any(
        row["partition"] == "train" and row["cutoff_mjd"] == 122.0 for row in rows(output)
    )  # max horizon ends at fit boundary 125
    assert any(
        row["partition"] == "validation" and row["cutoff_mjd"] == 132.0 for row in rows(output)
    )  # max horizon ends at selection boundary 135
    strict = tmp_path / "strict"
    prepare(inputs, strict, fit=132.0, selection=145.0)
    assert any(
        item["cutoff_mjd"] == 132.0 and "forecast_not_after_fit" in item["reasons"]
        for item in admission(strict, "validation")["excluded"]
    )
    assert any(
        item["cutoff_mjd"] == 145.0 and "forecast_not_after_selection" in item["reasons"]
        for item in admission(strict, "test")["excluded"]
    )


def test_b_changes_preserve_all_a_tensor_content_and_membership(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    before = prepare(inputs, tmp_path / "before")
    data = read_csv(inputs[0])
    for row in data:
        if row["survey"] == "source_B":
            row["value"] = str(float(row["value"]) ** 2)
            row["band"] = "B-only"
            for key in ("observed_at_mjd", "available_at_mjd"):
                row[key] = str(float(row[key]) + 1000.0)
    write_csv(inputs[0], data)
    after = prepare(inputs, tmp_path / "after")
    assert before["band_to_id"] == after["band_to_id"]
    for split in ("train", "validation", "test"):
        assert before["splits"][split] == after["splits"][split]


@pytest.mark.parametrize(
    "fit,selection",
    [
        (None, 135.0),
        (125.0, None),
        (True, 135.0),
        (125.0, False),
        (float("nan"), 135.0),
        (125.0, float("inf")),
        (135.0, 135.0),
        (136.0, 135.0),
        ("125", 135.0),
    ],
)
def test_invalid_policy_retains_inputs_and_failure_without_tensors(
    inputs: tuple[Path, Path], tmp_path: Path, fit: Any, selection: Any
) -> None:
    output = tmp_path / "invalid"
    with pytest.raises(ValueError):
        prepare(inputs, output, fit=fit, selection=selection)
    assert (output / "photometry-input.csv").read_bytes() == inputs[0].read_bytes()
    failure = json.loads((output / "failure.json").read_text())
    assert failure["schema"] == population.AS_OF_PREPARATION_SCHEMA
    assert failure["stage"] == "input_validation"
    assert not list(output.glob("*.pt"))
    assert not (output / "manifest.json").exists()


def test_empty_as_of_partition_retains_its_full_exclusion_receipt(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    output = tmp_path / "empty"
    with pytest.raises(ValueError, match="no admitted"):
        prepare(inputs, output, fit=105.0, selection=106.0)
    receipt = admission(output, "validation")
    assert receipt["admitted_complete_cutoffs"] == 0
    assert receipt["excluded_complete_cutoffs"] == receipt["candidate_complete_cutoffs"] > 0
    failure = (output / "failure.json").read_bytes()
    with pytest.raises(FileExistsError):
        prepare(inputs, output)
    assert failure == (output / "failure.json").read_bytes()
    assert not (output / "manifest.json").exists()


def test_cli_selects_separate_schema_only_with_explicit_boundaries(
    inputs: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "cli"
    assert (
        population.main(
            [
                "--photometry",
                str(inputs[0]),
                "--membership",
                str(inputs[1]),
                "--output",
                str(output),
                "--horizons-days",
                "1",
                "3",
                "--fit-available-through-mjd",
                "125",
                "--selection-available-through-mjd",
                "135",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "COMPLETE"
    assert json.loads((output / "manifest.json").read_text())["schema"] == (
        population.AS_OF_PREPARATION_SCHEMA
    )
