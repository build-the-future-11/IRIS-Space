"""Discriminating generated checks of population isolation and physical identity."""

from __future__ import annotations

import csv
import importlib.util
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
import torch

from siderea.ml import space_jepa_population_v1 as population
from siderea.ml.space_jepa_v2 import AQPMJEPA, SpaceJEPA2Config
from siderea.provenance import digest_value

_DEMO_PATH = Path(__file__).parents[1] / "scripts/demo_space_jepa_population_v1.py"
_SPEC = importlib.util.spec_from_file_location("population_demo", _DEMO_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_DEMO = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_DEMO)


@pytest.fixture
def inputs(tmp_path: Path) -> tuple[Path, Path]:
    return _DEMO.write_generated_inputs(tmp_path / "inputs")  # type: ignore[no-any-return]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def prepare(inputs: tuple[Path, Path], output: Path, **kwargs: Any) -> dict[str, Any]:
    return population.prepare_population_batches(
        *inputs, output, horizons_days=(1.0, 3.0), batch_size=4, **kwargs
    )


def load_batches(directory: Path, split: str) -> list[dict[str, Any]]:
    return torch.load(directory / f"{split}.pt", weights_only=True, map_location="cpu")  # type: ignore[no-any-return]


def receipts(directory: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (directory / "rows.jsonl").read_text().splitlines()]


def test_four_partitions_execute_real_unchanged_model(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    directory = tmp_path / "prepared"
    result = prepare(inputs, directory)
    assert tuple(result["splits"]) == population.PARTITIONS
    assert result["splits"]["train"]["physical_entities"] == [
        "physical-0",
        "physical-1",
        "physical-2",
    ]
    assert result["splits"]["population_b"]["physical_entities"] == ["physical-6", "physical-7"]
    units = [unit for item in result["splits"].values() for unit in item["physical_entities"]]
    assert len(units) == len(set(units)) == 8
    assert result["input_sha256"] == sha256(inputs[0].read_bytes()).hexdigest()
    assert result["membership_sha256"] == sha256(inputs[1].read_bytes()).hexdigest()
    assert (directory / "photometry-input.csv").read_bytes() == inputs[0].read_bytes()
    assert result["result_digest"] == digest_value(
        {k: v for k, v in result.items() if k != "result_digest"}
    )
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(7)
        model = AQPMJEPA(
            SpaceJEPA2Config(
                input_dim=7,
                quaternion_width=2,
                encoder_blocks=1,
                attention_heads=1,
                predictor_blocks=1,
                dropout=0.0,
                horizons_days=(1.0, 3.0),
                flow_steps=1,
            )
        ).eval()
    state = {key: value.clone() for key, value in model.state_dict().items()}
    with torch.no_grad():
        for split, item in result["splits"].items():
            batches = load_batches(directory, split)
            assert (
                len([key for batch in batches for key in batch["example_ids"]]) == item["row_count"]
            )
            assert item["tensor_content_digest"] == population._tensor_digest(batches)
            batch = batches[0]
            forecast = model(batch["context_tokens"], batch["context_mask"])["base_forecast"]
            target = model.encode_targets(batch["target_tokens"], batch["target_mask"])
            assert forecast.shape == target.shape
            assert bool(torch.isfinite(forecast).all()) and bool(torch.isfinite(target).all())
    assert all(torch.equal(state[key], value) for key, value in model.state_dict().items())
    rows = receipts(directory)
    assert len(rows) == sum(item["row_count"] for item in result["splits"].values())
    assert {
        row["input_alias"]
        for item in rows
        for row in item["prefix"]
        if item["physical_entity_id"] == "physical-0"
    } == {"survey:0", "catalog:0"}
    assert result["global_training_before_evaluation_established"] is False
    assert result["scientific_execution_authorized"] is False


def test_b_values_bands_times_and_order_cannot_change_a(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    before = prepare(inputs, tmp_path / "before")
    rows = read_rows(inputs[0])
    for row in rows:
        if row["survey"] == "source_B":
            row["band"] = "new-B-only-filter"
            row["value"] = str(float(row["value"]) ** 2 + 37.0)
            row["observed_at_mjd"] = str(float(row["observed_at_mjd"]) + 10000)
            row["available_at_mjd"] = str(float(row["available_at_mjd"]) + 10000)
    write_rows(inputs[0], list(reversed(rows)))
    after = prepare(inputs, tmp_path / "after")
    assert before["band_to_id"] == after["band_to_id"]
    for split in ("train", "validation", "test"):
        assert before["splits"][split] == after["splits"][split]
        for left, right in zip(
            load_batches(tmp_path / "before", split),
            load_batches(tmp_path / "after", split),
            strict=True,
        ):
            for key in ("context_tokens", "context_mask", "target_tokens", "target_mask"):
                assert torch.equal(left[key], right[key])
    assert (
        before["splits"]["population_b"]["tensor_content_digest"]
        != after["splits"]["population_b"]["tensor_content_digest"]
    )


def test_same_band_name_different_surveys_and_held_channels(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    rows = read_rows(inputs[0])
    for row in rows:
        if row["entity_id"].endswith(":1"):
            row["survey"] = "another_A_survey"
        if row["entity_id"].endswith(":3"):
            row["band"] = "validation-only"
    write_rows(inputs[0], rows)
    result = prepare(inputs, tmp_path / "prepared")
    vocabulary = result["band_to_id"]
    assert vocabulary['["source_A","g"]'] != vocabulary['["another_A_survey","g"]']
    assert not any("source_B" in name or "validation-only" in name for name in vocabulary)
    assert result["splits"]["population_b"]["unknown_channel_observations"] == 16
    assert result["splits"]["validation"]["unknown_channel_observations"] == 8


@pytest.mark.parametrize(
    "mutation",
    [
        "alias_collision",
        "canonical_collision",
        "duplicate_entity",
        "unknown_population",
        "missing_entity",
        "unused_entity",
        "duplicate_alias",
    ],
)
def test_ambiguous_membership_is_rejected_with_retained_snapshot(
    inputs: tuple[Path, Path], tmp_path: Path, mutation: str
) -> None:
    document = json.loads(inputs[1].read_text())
    entities = document["entities"]
    if mutation == "alias_collision":
        entities[-1]["aliases"].append("survey:0")
    elif mutation == "canonical_collision":
        entities[-1]["physical_entity_id"] = "survey:0"
    elif mutation == "duplicate_entity":
        entities.append(entities[0])
    elif mutation == "unknown_population":
        entities[-1]["population"] = "unknown"
    elif mutation == "missing_entity":
        entities.pop()
    elif mutation == "unused_entity":
        entities.append(
            {"physical_entity_id": "absent", "population": "source_B", "aliases": ["absent-alias"]}
        )
    else:
        entities[0]["aliases"].append(entities[0]["aliases"][0])
    inputs[1].write_text(json.dumps(document))
    output = tmp_path / "failed"
    with pytest.raises(ValueError):
        prepare(inputs, output)
    assert (output / "membership-input.json").read_bytes() == inputs[1].read_bytes()
    assert json.loads((output / "failure.json").read_text())["status"] == "FAILED"
    assert not (output / "manifest.json").exists()
    assert not list(output.glob("*.pt"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("entity_id", "undeclared"),
        ("entity_id", " survey:0"),
        ("is_detection", "False"),
        ("is_detection", "0"),
        ("value", "nan"),
        ("value_error", "inf"),
        ("available_at_mjd", "99"),
    ],
)
def test_bad_csv_is_not_coerced_or_silently_dropped(
    inputs: tuple[Path, Path], tmp_path: Path, field: str, value: str
) -> None:
    rows = read_rows(inputs[0])
    rows[0][field] = value
    write_rows(inputs[0], rows)
    with pytest.raises(ValueError):
        prepare(inputs, tmp_path / "failed")
    assert (tmp_path / "failed/failure.json").exists()


def test_duplicate_observation_through_alias_cannot_count_twice(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    rows = read_rows(inputs[0])
    rows[1]["observation_id"] = rows[0]["observation_id"]
    write_rows(inputs[0], rows)
    with pytest.raises(ValueError, match="duplicate physical-entity observation"):
        prepare(inputs, tmp_path / "failed")


def test_nondetection_and_late_target_do_not_enter_context(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    rows = read_rows(inputs[0])
    rows[3]["available_at_mjd"] = "133"
    rows[4].update(is_detection="false", value="", value_error="", limiting_value="6.5")
    write_rows(inputs[0], rows)
    directory = tmp_path / "prepared"
    prepare(inputs, directory)
    row = next(
        item
        for item in receipts(directory)
        if item["physical_entity_id"] == "physical-0" and item["cutoff_mjd"] == 104.0
    )
    assert "observation-3" not in {item["observation_id"] for item in row["prefix"]}
    assert "observation-4" in {item["observation_id"] for item in row["prefix"]}
    earlier = next(
        item
        for item in receipts(directory)
        if item["physical_entity_id"] == "physical-0" and item["cutoff_mjd"] == 102.0
    )
    assert earlier["targets"][0]["latest_target_available_at_mjd"] == 133.0
    for item in receipts(directory):
        assert all(
            obs["observed_at_mjd"] <= item["cutoff_mjd"]
            and obs["available_at_mjd"] <= item["cutoff_mjd"]
            for obs in item["prefix"]
        )
    batches = load_batches(directory, "train")
    assert any(
        bool(((batch["context_tokens"][..., 4] == 0) & batch["context_mask"]).any())
        for batch in batches
    )


def test_late_history_stays_with_enrolled_entity_and_is_disclosed(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    rows = read_rows(inputs[0])
    rows[7]["observed_at_mjd"] = rows[7]["available_at_mjd"] = "500"
    write_rows(inputs[0], rows)
    result = prepare(inputs, tmp_path / "prepared")
    assert "physical-0" in result["splits"]["train"]["physical_entities"]
    assert result["splits"]["train"]["available_at_mjd_bounds"][1] == 500
    assert result["global_training_before_evaluation_established"] is False


def test_consumed_snapshot_is_archived_even_if_input_path_changes(
    inputs: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = inputs[0].read_bytes()
    parse = population._membership

    def replace_path(raw: bytes) -> Any:
        inputs[0].write_bytes(b"changed pathname after snapshot\n")
        return parse(raw)

    monkeypatch.setattr(population, "_membership", replace_path)
    result = prepare(inputs, tmp_path / "prepared")
    assert result["input_sha256"] == sha256(original).hexdigest()
    assert (tmp_path / "prepared/photometry-input.csv").read_bytes() == original


def test_no_complete_b_rows_retains_failure_and_finished_a_files(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    rows = [
        row
        for row in read_rows(inputs[0])
        if row["survey"] != "source_B" or row["observation_id"] == "observation-0"
    ]
    write_rows(inputs[0], rows)
    output = tmp_path / "failed"
    with pytest.raises(ValueError, match="population_b.*no complete"):
        prepare(inputs, output)
    failure = json.loads((output / "failure.json").read_text())
    assert {"train.pt", "validation.pt", "test.pt"}.issubset(failure["finalized_files"])
    assert not (output / "manifest.json").exists()


def test_preparation_does_not_change_rng(inputs: tuple[Path, Path], tmp_path: Path) -> None:
    before = torch.get_rng_state().clone()
    prepare(inputs, tmp_path / "prepared")
    assert torch.equal(before, torch.get_rng_state())


def test_default_dtype_rejected_without_global_mutation(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    original = torch.get_default_dtype()
    try:
        torch.set_default_dtype(torch.float64)
        with pytest.raises(ValueError, match="CPU default device and float32"):
            prepare(inputs, tmp_path / "failed")
        assert torch.get_default_dtype() == torch.float64
    finally:
        torch.set_default_dtype(original)


def test_cli_failure_and_existing_attempt_are_preserved(
    inputs: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = [
        "--photometry",
        str(inputs[0]),
        "--membership",
        str(inputs[1]),
        "--output",
        str(tmp_path / "attempt"),
        "--horizons-days",
        "1",
        "3",
    ]
    assert population.main(args) == 0
    original = (tmp_path / "attempt/manifest.json").read_bytes()
    assert population.main(args) == 2
    assert (tmp_path / "attempt/manifest.json").read_bytes() == original
    assert "exists" in capsys.readouterr().err


def test_duplicate_json_keys_rejected(inputs: tuple[Path, Path], tmp_path: Path) -> None:
    raw = (
        inputs[1]
        .read_text()
        .replace('"purpose": "development"', '"purpose": "development", "purpose": "development"')
    )
    inputs[1].write_text(raw)
    with pytest.raises(ValueError, match="duplicate JSON key"):
        prepare(inputs, tmp_path / "failed")


def test_tensor_budget_fails_before_allocation(
    inputs: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(population, "MAX_TENSOR_VALUES", 1)
    with pytest.raises(ValueError, match="two million"):
        prepare(inputs, tmp_path / "failed")
    assert not list((tmp_path / "failed").glob("*.pt"))


def test_entity_without_complete_rows_remains_in_population_accounting(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    rows = [
        row
        for row in read_rows(inputs[0])
        if not row["entity_id"].endswith(":7") or row["observation_id"] == "observation-0"
    ]
    write_rows(inputs[0], rows)
    result = prepare(inputs, tmp_path / "prepared")
    population_b = result["splits"]["population_b"]
    assert population_b["physical_entities"] == ["physical-6", "physical-7"]
    assert population_b["entities_with_complete_rows"] == ["physical-6"]
    assert population_b["entities_without_complete_rows"] == ["physical-7"]
    assert population_b["observation_count"] == 9


def test_default_device_rejected_without_global_mutation(
    inputs: tuple[Path, Path], tmp_path: Path
) -> None:
    original = torch.get_default_device()
    try:
        torch.set_default_device("meta")
        with pytest.raises(ValueError, match="CPU default device and float32"):
            prepare(inputs, tmp_path / "failed")
        assert torch.get_default_device().type == "meta"
    finally:
        torch.set_default_device(original)
