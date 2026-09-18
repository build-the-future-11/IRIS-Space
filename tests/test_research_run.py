from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from siderea.research.run import (
    inspect_jepa_dataset_contract,
    load_shadow_run_spec,
    run_shadow_pilot,
)


def _spec(root: Path, **selection_overrides: object) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "raw.csv").write_text("fixture\n", encoding="utf-8")
    record = {
        "object_id": "object",
        "entity_id": "entity",
        "prediction_cutoff_mjd": 61000.0,
        "times": [1.0, 2.0],
        "values": [1.0, 2.0],
        "errors": [0.1, 0.1],
        "bands": ["g", "g"],
        "detections": [True, True],
        "value_kind": "flux",
        "survey": "survey",
        "time_scale": "utc",
        "flux_unit": "uJy",
        "flux_kind": "forced_difference",
        "calibration": "release-v1",
        "coordinate_frame": "icrs",
        "survey_release": "survey-v1",
    }
    entities = {
        "train.jsonl": "train",
        "validation.jsonl": "validation",
        "reference.jsonl": "train",
    }
    for name, entity in entities.items():
        value = {**record, "object_id": f"object-{entity}", "entity_id": entity}
        (root / name).write_text(json.dumps(value) + "\n", encoding="utf-8")
    (root / "config.toml").write_text("fixture\n", encoding="utf-8")
    selection = {
        "budget": 4,
        "detector_slots": 1,
        "jepa_slots": 1,
        "audit_slots": 1,
        "jepa_threshold": 0.8,
        "audit_seed": "fixed",
        "reference_selection_policy": "training-only controls",
        **selection_overrides,
    }
    path = root / "run.toml"
    path.write_text(
        """
[inputs]
raw_photometry = "raw.csv"
train_jsonl = "train.jsonl"
validation_jsonl = "validation.jsonl"
reference_jsonl = "reference.jsonl"

[measurement]
prediction_cutoff_mjd = 61000.0
survey = "survey"
time_scale = "utc"
flux_unit = "uJy"
flux_kind = "forced_difference"
calibration = "release-v1"
coordinate_frame = "icrs"
survey_release = "survey-v1"
entity_column = "physical_entity_id"
detection_column = "detected"

[experiment]
siderea_config = "config.toml"
epochs = 1
evaluation_masks = 2
device = "cpu"
null_trials = 99
null_method = "gaussian"
wild_block_size = 1
seed = 7
survey_object_count = 100
planned_looks = 2
look_index = 1

[selection]
budget = {budget}
detector_slots = {detector_slots}
jepa_slots = {jepa_slots}
audit_slots = {audit_slots}
jepa_threshold = {jepa_threshold}
audit_seed = "{audit_seed}"
reference_selection_policy = "{reference_selection_policy}"
""".format(**selection).lstrip(),
        encoding="utf-8",
    )
    return path


def test_load_shadow_run_spec_resolves_and_validates(tmp_path: Path) -> None:
    spec = load_shadow_run_spec(_spec(tmp_path))
    assert spec["schema"] == "siderea.shadow_run_spec.v1"
    assert spec["inputs"]["raw_photometry"] == (tmp_path / "raw.csv")
    assert spec["measurement"]["flux_kind"] == "forced_difference"
    assert spec["experiment"]["evaluation_masks"] == 2

    with pytest.raises(ValueError, match="route slots"):
        load_shadow_run_spec(_spec(tmp_path / "bad", budget=2, detector_slots=2, jepa_slots=1))


def test_shadow_spec_rejects_entity_leakage(tmp_path: Path) -> None:
    spec_path = _spec(tmp_path)
    train = (tmp_path / "train.jsonl").read_text(encoding="utf-8")
    (tmp_path / "validation.jsonl").write_text(train, encoding="utf-8")
    with pytest.raises(ValueError, match="share physical entities"):
        load_shadow_run_spec(spec_path)


def test_shadow_spec_requires_training_only_reference(tmp_path: Path) -> None:
    spec_path = _spec(tmp_path)
    reference = json.loads((tmp_path / "reference.jsonl").read_text(encoding="utf-8"))
    reference["entity_id"] = "external-reference"
    (tmp_path / "reference.jsonl").write_text(json.dumps(reference) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="subset of training"):
        load_shadow_run_spec(spec_path)


def test_jepa_contract_rejects_misaligned_arrays(tmp_path: Path) -> None:
    _spec(tmp_path)
    record = json.loads((tmp_path / "train.jsonl").read_text(encoding="utf-8"))
    record["errors"] = [0.1]
    path = tmp_path / "misaligned.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="misaligned"):
        inspect_jepa_dataset_contract(path)


def test_shadow_run_retains_failed_stage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    spec = _spec(tmp_path / "spec")

    class Failed:
        returncode = 9
        stdout = ""

    monkeypatch.setattr("siderea.research.run.subprocess.run", lambda *args, **kwargs: Failed())
    output = tmp_path / "failed-run"
    with pytest.raises(RuntimeError, match="doctor"):
        run_shadow_pilot(spec, output)
    status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["stage"] == "doctor"
    assert (output / "doctor.log").is_file()


def test_shadow_run_refuses_existing_output(tmp_path: Path) -> None:
    spec = _spec(tmp_path / "spec")
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError, match="already exists"):
        run_shadow_pilot(spec, output)


def test_shadow_run_preserves_virtualenv_interpreter_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spec = _spec(tmp_path / "spec")
    interpreter = tmp_path / "environment" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(Path(sys.executable))
    seen: list[list[str]] = []

    class Failed:
        returncode = 9
        stdout = ""

    def fail(command, **kwargs):
        seen.append(command)
        return Failed()

    monkeypatch.setattr("siderea.research.run.subprocess.run", fail)
    with pytest.raises(RuntimeError):
        run_shadow_pilot(spec, tmp_path / "run", python_bin=interpreter)
    siderea_command = next(command for command in seen if "-m" in command)
    assert siderea_command[0] == str(interpreter)
