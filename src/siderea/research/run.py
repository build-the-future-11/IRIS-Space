"""Strict one-command orchestration for the JEPA-integrated shadow pipeline."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from siderea.atomic import atomic_write_text
from siderea.manifest import _git_state, _source_digest
from siderea.provenance import digest_file, digest_value, stable_json, utc_now

SHADOW_RUN_SPEC_SCHEMA = "siderea.shadow_run_spec.v1"
SHADOW_RUN_MANIFEST_SCHEMA = "siderea.shadow_run_manifest.v1"

_TOP_LEVEL = frozenset({"inputs", "measurement", "experiment", "selection"})
_INPUT_FIELDS = frozenset({"raw_photometry", "train_jsonl", "validation_jsonl", "reference_jsonl"})
_MEASUREMENT_FIELDS = frozenset(
    {
        "prediction_cutoff_mjd",
        "survey",
        "time_scale",
        "flux_unit",
        "flux_kind",
        "calibration",
        "coordinate_frame",
        "survey_release",
        "entity_column",
        "detection_column",
    }
)
_EXPERIMENT_FIELDS = frozenset(
    {
        "siderea_config",
        "epochs",
        "evaluation_masks",
        "device",
        "null_trials",
        "null_method",
        "wild_block_size",
        "seed",
        "survey_object_count",
        "planned_looks",
        "look_index",
    }
)
_SELECTION_FIELDS = frozenset(
    {
        "budget",
        "detector_slots",
        "jepa_slots",
        "audit_slots",
        "jepa_threshold",
        "audit_seed",
        "reference_selection_policy",
    }
)


def _section(
    payload: Mapping[str, Any],
    name: str,
    expected: frozenset[str],
) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, Mapping):
        raise ValueError(f"shadow run spec section {name!r} must be a table")
    result = dict(value)
    missing = sorted(expected - set(result))
    unknown = sorted(set(result) - expected)
    if missing or unknown:
        raise ValueError(
            f"shadow run spec section {name!r} has missing={missing}, unknown={unknown}"
        )
    return result


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _integer(value: Any, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _input_file(value: Any, name: str, *, base: Path) -> Path:
    path = (base / _text(value, name)).resolve()
    if not path.is_file():
        raise ValueError(f"{name} is not a readable file: {path}")
    return path


def inspect_jepa_dataset_contract(path: str | Path) -> dict[str, Any]:
    """Validate point-in-time JEPA records and return their shared physical contract."""

    source = Path(path).expanduser().resolve()
    required_metadata = (
        "survey",
        "time_scale",
        "flux_unit",
        "flux_kind",
        "calibration",
        "coordinate_frame",
        "survey_release",
    )
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {source} line {line_number}") from exc
        if not isinstance(value, Mapping):
            raise ValueError(f"JEPA record in {source} line {line_number} must be an object")
        records.append(dict(value))
    if not records:
        raise ValueError(f"JEPA dataset is empty: {source}")
    entities: set[str] = set()
    contracts: list[dict[str, str]] = []
    for index, record in enumerate(records, start=1):
        _text(record.get("object_id"), f"{source} record {index} object_id")
        entity = _text(record.get("entity_id"), f"{source} record {index} entity_id")
        canonical_entity = " ".join(entity.casefold().split())
        if canonical_entity in entities:
            raise ValueError(f"JEPA dataset repeats entity {entity!r}: {source}")
        entities.add(canonical_entity)
        arrays: dict[str, list[Any]] = {}
        for field in ("times", "values", "errors", "bands", "detections"):
            value = record.get(field)
            if isinstance(value, (str, bytes)) or not isinstance(value, list) or not value:
                raise ValueError(f"JEPA record {entity!r} requires a non-empty {field} array")
            arrays[field] = value
        lengths = {len(value) for value in arrays.values()}
        if len(lengths) != 1:
            raise ValueError(
                f"JEPA record {entity!r} has misaligned times, values, errors, bands, "
                "and detections"
            )
        if _text(record.get("value_kind"), f"{source} record {index} value_kind") != "flux":
            raise ValueError(f"JEPA record {entity!r} must use value_kind='flux'")
        try:
            times = [float(value) for value in arrays["times"]]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"JEPA record {entity!r} has nonnumeric times") from exc
        if not all(math.isfinite(value) for value in times):
            raise ValueError(f"JEPA record {entity!r} has non-finite times")
        for position, (value, error, band, detected) in enumerate(
            zip(
                arrays["values"],
                arrays["errors"],
                arrays["bands"],
                arrays["detections"],
                strict=True,
            )
        ):
            if not isinstance(detected, bool):
                raise ValueError(f"JEPA record {entity!r} detection {position} must be boolean")
            if not isinstance(band, str) or not band.strip():
                raise ValueError(f"JEPA record {entity!r} band {position} must be non-empty")
            if value is not None:
                _number(value, f"JEPA record {entity!r} value {position}")
            if error is not None:
                numeric_error = _number(error, f"JEPA record {entity!r} error {position}")
                if numeric_error <= 0:
                    raise ValueError(f"JEPA record {entity!r} error {position} must be positive")
            if detected and (value is None or error is None):
                raise ValueError(
                    f"JEPA record {entity!r} detected point {position} requires value and error"
                )
        cutoff = _number(
            record.get("prediction_cutoff_mjd"),
            f"{source} record {index} prediction_cutoff_mjd",
        )
        if max(times) > cutoff:
            raise ValueError(f"JEPA record {entity!r} contains post-cutoff observations")
        contract = {
            field: _text(record.get(field), f"{source} record {index} {field}").casefold()
            for field in required_metadata
        }
        if contract["time_scale"] not in {"utc", "tai", "tdb"}:
            raise ValueError(f"JEPA record {entity!r} has unsupported time_scale")
        if contract["flux_kind"] not in {
            "difference",
            "forced_difference",
            "forced_total",
            "total",
        }:
            raise ValueError(f"JEPA record {entity!r} has unsupported flux_kind")
        if contract["coordinate_frame"] not in {"icrs", "fk5"}:
            raise ValueError(f"JEPA record {entity!r} has unsupported coordinate_frame")
        contracts.append(contract)
    first = contracts[0]
    if any(contract != first for contract in contracts[1:]):
        raise ValueError(f"JEPA dataset mixes physical measurement contracts: {source}")
    return {
        "path": source,
        "sha256": digest_file(source),
        "record_count": len(records),
        "entity_count": len(entities),
        "canonical_entity_ids": sorted(entities),
        "entity_id_digest": digest_value(sorted(entities)),
        "measurement_contract": first,
        "measurement_contract_digest": digest_value(first),
    }


def load_shadow_run_spec(path: str | Path) -> dict[str, Any]:
    """Load a complete, strict TOML specification and resolve its input paths."""

    source = Path(path).expanduser().resolve()
    try:
        raw = tomllib.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"cannot read shadow run spec: {source}") from exc
    if set(raw) != _TOP_LEVEL:
        raise ValueError(
            "shadow run spec top level must contain exactly inputs, measurement, "
            "experiment, and selection"
        )
    inputs = _section(raw, "inputs", _INPUT_FIELDS)
    measurement = _section(raw, "measurement", _MEASUREMENT_FIELDS)
    experiment = _section(raw, "experiment", _EXPERIMENT_FIELDS)
    selection = _section(raw, "selection", _SELECTION_FIELDS)
    base = source.parent

    resolved_inputs = {
        name: _input_file(value, f"inputs.{name}", base=base) for name, value in inputs.items()
    }
    config = _input_file(
        experiment["siderea_config"],
        "experiment.siderea_config",
        base=base,
    )
    time_scale = _text(measurement["time_scale"], "measurement.time_scale").casefold()
    if time_scale not in {"utc", "tai", "tdb"}:
        raise ValueError("measurement.time_scale must be utc, tai, or tdb")
    flux_kind = _text(measurement["flux_kind"], "measurement.flux_kind").casefold()
    if flux_kind not in {"difference", "forced_difference", "forced_total", "total"}:
        raise ValueError(
            "measurement.flux_kind must be difference, forced_difference, forced_total, or total"
        )
    coordinate_frame = _text(
        measurement["coordinate_frame"], "measurement.coordinate_frame"
    ).casefold()
    if coordinate_frame not in {"icrs", "fk5"}:
        raise ValueError("measurement.coordinate_frame must be icrs or fk5")
    prediction_cutoff = _number(
        measurement["prediction_cutoff_mjd"], "measurement.prediction_cutoff_mjd"
    )
    normalized_measurement = {
        "prediction_cutoff_mjd": prediction_cutoff,
        "survey": _text(measurement["survey"], "measurement.survey").casefold(),
        "time_scale": time_scale,
        "flux_unit": _text(measurement["flux_unit"], "measurement.flux_unit"),
        "flux_kind": flux_kind,
        "calibration": _text(measurement["calibration"], "measurement.calibration"),
        "coordinate_frame": coordinate_frame,
        "survey_release": _text(measurement["survey_release"], "measurement.survey_release"),
        "entity_column": _text(measurement["entity_column"], "measurement.entity_column"),
        "detection_column": _text(measurement["detection_column"], "measurement.detection_column"),
    }

    null_method = _text(experiment["null_method"], "experiment.null_method").casefold()
    if null_method not in {"gaussian", "wild_residual"}:
        raise ValueError("experiment.null_method must be gaussian or wild_residual")
    device = _text(experiment["device"], "experiment.device")
    planned_looks = _integer(experiment["planned_looks"], "experiment.planned_looks", minimum=1)
    look_index = _integer(experiment["look_index"], "experiment.look_index", minimum=1)
    if look_index > planned_looks:
        raise ValueError("experiment.look_index cannot exceed experiment.planned_looks")
    normalized_experiment: dict[str, Any] = {
        "siderea_config": config,
        "epochs": _integer(experiment["epochs"], "experiment.epochs", minimum=1),
        "evaluation_masks": _integer(
            experiment["evaluation_masks"], "experiment.evaluation_masks", minimum=2
        ),
        "device": device,
        "null_trials": _integer(experiment["null_trials"], "experiment.null_trials", minimum=1),
        "null_method": null_method,
        "wild_block_size": _integer(
            experiment["wild_block_size"], "experiment.wild_block_size", minimum=1
        ),
        "seed": _integer(experiment["seed"], "experiment.seed", minimum=0),
        "survey_object_count": _integer(
            experiment["survey_object_count"],
            "experiment.survey_object_count",
            minimum=1,
        ),
        "planned_looks": planned_looks,
        "look_index": look_index,
    }

    budget = _integer(selection["budget"], "selection.budget", minimum=1)
    detector_slots = _integer(selection["detector_slots"], "selection.detector_slots", minimum=0)
    jepa_slots = _integer(selection["jepa_slots"], "selection.jepa_slots", minimum=0)
    audit_slots = _integer(selection["audit_slots"], "selection.audit_slots", minimum=0)
    if detector_slots + jepa_slots + audit_slots > budget:
        raise ValueError("selection route slots cannot exceed selection.budget")
    threshold = _number(selection["jepa_threshold"], "selection.jepa_threshold")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("selection.jepa_threshold must be within [0, 1]")
    normalized_selection = {
        "budget": budget,
        "detector_slots": detector_slots,
        "jepa_slots": jepa_slots,
        "audit_slots": audit_slots,
        "jepa_threshold": threshold,
        "audit_seed": _text(selection["audit_seed"], "selection.audit_seed"),
        "reference_selection_policy": _text(
            selection["reference_selection_policy"],
            "selection.reference_selection_policy",
        ),
    }
    expected_contract = {
        field: str(normalized_measurement[field]).casefold()
        for field in (
            "survey",
            "time_scale",
            "flux_unit",
            "flux_kind",
            "calibration",
            "coordinate_frame",
            "survey_release",
        )
    }
    dataset_contracts: dict[str, Any] = {}
    for name in ("train_jsonl", "validation_jsonl", "reference_jsonl"):
        summary = inspect_jepa_dataset_contract(resolved_inputs[name])
        if summary["measurement_contract"] != expected_contract:
            raise ValueError(
                f"inputs.{name} measurement contract differs from the declared run contract"
            )
        dataset_contracts[name] = summary
    train_entities = set(dataset_contracts["train_jsonl"]["canonical_entity_ids"])
    validation_entities = set(dataset_contracts["validation_jsonl"]["canonical_entity_ids"])
    reference_entities = set(dataset_contracts["reference_jsonl"]["canonical_entity_ids"])
    overlap = sorted(train_entities & validation_entities)
    if overlap:
        raise ValueError(
            "training and validation datasets share physical entities: " + ", ".join(overlap)
        )
    if not reference_entities <= train_entities:
        raise ValueError("reference entities must be a subset of training entities")
    return {
        "schema": SHADOW_RUN_SPEC_SCHEMA,
        "source": source,
        "inputs": resolved_inputs,
        "measurement": normalized_measurement,
        "experiment": normalized_experiment,
        "selection": normalized_selection,
        "dataset_contracts": dataset_contracts,
    }


def _status(
    destination: Path,
    *,
    run_id: str,
    status: str,
    stage: str,
    started_at: str,
    error: str | None = None,
) -> None:
    payload = {
        "schema": "siderea.shadow_run_status.v1",
        "run_id": run_id,
        "status": status,
        "stage": stage,
        "started_at": started_at,
        "updated_at": utc_now(),
        "error": error,
    }
    atomic_write_text(destination / "status.json", stable_json(payload) + "\n")


def run_shadow_pilot(
    spec_path: str | Path,
    output: str | Path,
    *,
    python_bin: str | Path | None = None,
) -> dict[str, Any]:
    """Run every shadow stage and publish a content-addressed terminal manifest."""

    spec = load_shadow_run_spec(spec_path)
    destination = Path(output).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"shadow run output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700)
    run_id = destination.name
    # Keep the virtual-environment entry path intact. Resolving its symlink to the
    # base interpreter discards Python's venv discovery for child commands.
    executable = Path(os.path.abspath(os.path.expanduser(str(python_bin or sys.executable))))
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError(f"Python executable is unavailable: {executable}")
    project_root = Path(__file__).resolve().parents[3]
    package_root = Path(__file__).resolve().parents[1]
    code_revision, code_worktree_dirty = _git_state(project_root)
    code_source_digest = _source_digest(project_root, package_root=package_root)
    frozen_spec_digest = digest_file(spec["source"])
    frozen_config_digest = digest_file(spec["experiment"]["siderea_config"])
    frozen_input_digests = {name: digest_file(path) for name, path in spec["inputs"].items()}
    started_at = utc_now()
    commands: list[dict[str, Any]] = []
    current_stage = "initialization"

    def run(stage: str, *arguments: str) -> None:
        nonlocal current_stage
        current_stage = stage
        _status(
            destination,
            run_id=run_id,
            status="running",
            stage=stage,
            started_at=started_at,
        )
        command = [str(executable), "-m", "siderea", *arguments]
        receipt = destination / f"{stage}.log"
        with receipt.open("xb") as handle:
            completed = subprocess.run(
                command,
                cwd=project_root,
                stdout=handle,
                stderr=subprocess.STDOUT,
                check=False,
            )
            handle.flush()
            os.fsync(handle.fileno())
        commands.append(
            {
                "stage": stage,
                "argv": command,
                "returncode": completed.returncode,
                "receipt": receipt.name,
                "receipt_sha256": digest_file(receipt),
            }
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"shadow stage {stage!r} failed with exit code {completed.returncode}; "
                f"inspect {receipt}"
            )

    inputs = spec["inputs"]
    measurement = spec["measurement"]
    experiment = spec["experiment"]
    selection = spec["selection"]
    config = str(experiment["siderea_config"])
    prepared = destination / "prepared"
    pipeline = destination / "pipeline"
    model = destination / "jepa-model"
    try:
        run("doctor", "doctor", "--config", config, "--json")
        run(
            "prepare",
            "pilot-prepare",
            str(inputs["raw_photometry"]),
            str(prepared),
            "--prediction-cutoff-mjd",
            str(measurement["prediction_cutoff_mjd"]),
            "--flux-unit",
            measurement["flux_unit"],
            "--flux-kind",
            measurement["flux_kind"],
            "--calibration",
            measurement["calibration"],
            "--time-scale",
            measurement["time_scale"],
            "--coordinate-frame",
            measurement["coordinate_frame"],
            "--survey-release",
            measurement["survey_release"],
            "--expected-survey",
            measurement["survey"],
            "--entity-column",
            measurement["entity_column"],
            "--detection-column",
            measurement["detection_column"],
            "--require-pipeline-view",
        )
        current_stage = "candidate-contract"
        _status(
            destination,
            run_id=run_id,
            status="running",
            stage=current_stage,
            started_at=started_at,
        )
        candidate_contract = inspect_jepa_dataset_contract(prepared / "jepa.jsonl")
        expected_contract = spec["dataset_contracts"]["train_jsonl"]["measurement_contract"]
        if candidate_contract["measurement_contract"] != expected_contract:
            raise ValueError("prepared candidates differ from the training measurement contract")
        historical_entities = set()
        for summary in spec["dataset_contracts"].values():
            historical_entities.update(summary["canonical_entity_ids"])
        leaked_entities = sorted(
            historical_entities & set(candidate_contract["canonical_entity_ids"])
        )
        if leaked_entities:
            raise ValueError(
                "prepared candidates overlap historical JEPA entities: "
                + ", ".join(leaked_entities)
            )
        spec["dataset_contracts"]["candidate_jsonl"] = candidate_contract
        run(
            "analyze",
            "analyze",
            str(prepared / "pipeline_photometry.csv"),
            "--config",
            config,
            "--output-dir",
            str(pipeline),
            "--ledger",
            str(destination / "outcomes.sqlite"),
            "--run-id",
            run_id,
        )
        run(
            "jepa-train",
            "jepa-train",
            str(inputs["train_jsonl"]),
            str(inputs["validation_jsonl"]),
            str(model),
            "--config",
            config,
            "--require-prediction-cutoffs",
            "--epochs",
            str(experiment["epochs"]),
            "--evaluation-masks",
            str(experiment["evaluation_masks"]),
            "--device",
            experiment["device"],
        )
        run(
            "reference-freeze",
            "jepa-reference-freeze",
            str(inputs["reference_jsonl"]),
            str(destination / "reference-cohort.json"),
            "--cohort-id",
            f"{run_id}-reference",
            "--selection-policy",
            selection["reference_selection_policy"],
        )
        run(
            "transient-search",
            "transient-search",
            str(prepared / "detector_flux.csv"),
            str(destination / "transient.json"),
            "--prediction-cutoff-mjd",
            str(measurement["prediction_cutoff_mjd"]),
            "--null-trials",
            str(experiment["null_trials"]),
            "--null-method",
            experiment["null_method"],
            "--wild-block-size",
            str(experiment["wild_block_size"]),
            "--seed",
            str(experiment["seed"]),
            "--survey-object-count",
            str(experiment["survey_object_count"]),
            "--planned-looks",
            str(experiment["planned_looks"]),
            "--look-index",
            str(experiment["look_index"]),
        )
        run(
            "reference-embed",
            "jepa-embed",
            str(model / "checkpoint.pt"),
            str(inputs["reference_jsonl"]),
            str(destination / "reference-embeddings.json"),
            "--reference-cohort",
            str(destination / "reference-cohort.json"),
            "--device",
            experiment["device"],
        )
        run(
            "candidate-embed",
            "jepa-embed",
            str(model / "checkpoint.pt"),
            str(prepared / "jepa.jsonl"),
            str(destination / "candidate-embeddings.json"),
            "--device",
            experiment["device"],
        )
        run(
            "shadow-assemble",
            "shadow-assemble",
            str(destination / "transient.json"),
            str(destination / "candidate-embeddings.json"),
            str(destination / "reference-embeddings.json"),
            str(destination / "shadow-evidence.json"),
            "--pipeline-candidates",
            str(pipeline / run_id / "candidates.json"),
            "--pipeline-manifest",
            str(pipeline / run_id / "manifest.json"),
            "--pilot-manifest",
            str(prepared / "manifest.json"),
            "--reference-cohort",
            str(destination / "reference-cohort.json"),
        )
        run(
            "shadow-rank",
            "shadow-rank",
            str(destination / "shadow-evidence.json"),
            str(destination / "shadow-queue.json"),
            "--budget",
            str(selection["budget"]),
            "--detector-slots",
            str(selection["detector_slots"]),
            "--jepa-slots",
            str(selection["jepa_slots"]),
            "--jepa-threshold",
            str(selection["jepa_threshold"]),
            "--audit-slots",
            str(selection["audit_slots"]),
            "--audit-seed",
            selection["audit_seed"],
        )
        current_stage = "finalize"
        _status(
            destination,
            run_id=run_id,
            status="running",
            stage=current_stage,
            started_at=started_at,
        )
        current_bindings = {
            "spec": digest_file(spec["source"]),
            "config": digest_file(experiment["siderea_config"]),
            **{f"input:{name}": digest_file(path) for name, path in inputs.items()},
            "code": _source_digest(project_root, package_root=package_root),
        }
        frozen_bindings = {
            "spec": frozen_spec_digest,
            "config": frozen_config_digest,
            **{f"input:{name}": digest for name, digest in frozen_input_digests.items()},
            "code": code_source_digest,
        }
        changed = sorted(
            name for name, digest in current_bindings.items() if digest != frozen_bindings[name]
        )
        if changed:
            raise RuntimeError(
                "run inputs or source changed during execution: " + ", ".join(changed)
            )
        artifacts = []
        for path in sorted(destination.rglob("*")):
            if path.is_file() and path.name not in {"status.json", "run-manifest.json"}:
                artifacts.append(
                    {
                        "path": str(path.relative_to(destination)),
                        "sha256": digest_file(path),
                        "bytes": path.stat().st_size,
                    }
                )
        input_digests = {
            name: {"path": str(path), "sha256": frozen_input_digests[name]}
            for name, path in inputs.items()
        }
        manifest: dict[str, Any] = {
            "schema": SHADOW_RUN_MANIFEST_SCHEMA,
            "run_id": run_id,
            "status": "completed",
            "scope": "shadow_research_only_not_reportability_or_real_sky_validation",
            "started_at": started_at,
            "completed_at": utc_now(),
            "code_revision": code_revision,
            "code_source_digest": code_source_digest,
            "code_worktree_dirty": code_worktree_dirty,
            "spec_path": str(spec["source"]),
            "spec_sha256": frozen_spec_digest,
            "measurement_contract": measurement,
            "experiment": {
                **{key: value for key, value in experiment.items() if key != "siderea_config"},
                "siderea_config": str(experiment["siderea_config"]),
                "siderea_config_sha256": frozen_config_digest,
            },
            "selection": selection,
            "input_artifacts": input_digests,
            "dataset_contracts": {
                name: {
                    **{
                        key: value
                        for key, value in summary.items()
                        if key not in {"path", "canonical_entity_ids"}
                    },
                    "path": str(summary["path"]),
                }
                for name, summary in spec["dataset_contracts"].items()
            },
            "commands": commands,
            "artifacts": artifacts,
        }
        manifest["manifest_digest"] = digest_value(manifest)
        atomic_write_text(destination / "run-manifest.json", stable_json(manifest) + "\n")
        _status(
            destination,
            run_id=run_id,
            status="completed",
            stage="complete",
            started_at=started_at,
        )
        return {
            "schema": SHADOW_RUN_MANIFEST_SCHEMA,
            "run_id": run_id,
            "status": "completed",
            "output": str(destination),
            "manifest": str(destination / "run-manifest.json"),
            "queue": str(destination / "shadow-queue.json"),
            "manifest_digest": manifest["manifest_digest"],
        }
    except BaseException as exc:
        _status(
            destination,
            run_id=run_id,
            status="failed",
            stage=current_stage,
            started_at=started_at,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise


__all__ = [
    "SHADOW_RUN_MANIFEST_SCHEMA",
    "SHADOW_RUN_SPEC_SCHEMA",
    "load_shadow_run_spec",
    "inspect_jepa_dataset_contract",
    "run_shadow_pilot",
]
