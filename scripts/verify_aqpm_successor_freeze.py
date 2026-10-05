#!/usr/bin/env python3
"""Fail-closed verifier for the Space-JEPA 2 / AQPM-JEPA successor freeze.

This verifier does not run a model and does not inspect outcomes. It only allows
a successor protocol to be described as frozen when the pre-outcome identities,
ablation matrix, selection rules, evaluation axes, and resource ceilings are
fully bound to retained repository artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

FULL_FACTORIAL = {
    "matched_capacity_non_aqpm": {
        "quaternion": False,
        "jump_flow": False,
        "residual_memory": False,
    },
    "quaternion_only": {
        "quaternion": True,
        "jump_flow": False,
        "residual_memory": False,
    },
    "jump_flow_only": {
        "quaternion": False,
        "jump_flow": True,
        "residual_memory": False,
    },
    "residual_memory_only": {
        "quaternion": False,
        "jump_flow": False,
        "residual_memory": True,
    },
    "quaternion_jump_flow": {
        "quaternion": True,
        "jump_flow": True,
        "residual_memory": False,
    },
    "quaternion_residual_memory": {
        "quaternion": True,
        "jump_flow": False,
        "residual_memory": True,
    },
    "jump_flow_residual_memory": {
        "quaternion": False,
        "jump_flow": True,
        "residual_memory": True,
    },
    "aqpm_full": {
        "quaternion": True,
        "jump_flow": True,
        "residual_memory": True,
    },
}

REQUIRED_ROBUSTNESS_AXES = {"cadence", "missingness", "population_shift"}


class FreezeError(ValueError):
    """Raised when a claimed successor freeze is incomplete or inconsistent."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FreezeError(message)


def _mapping(value: Any, location: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{location} must be an object")
    return value


def _nonempty_string(value: Any, location: str) -> str:
    _require(isinstance(value, str) and value.strip() == value and bool(value), (
        f"{location} must be a nonempty, unpadded string"
    ))
    return value


def _sha256_text(value: Any, location: str) -> str:
    text = _nonempty_string(value, location)
    _require(bool(HEX64.fullmatch(text)), f"{location} must be lowercase SHA-256")
    return text


def _commit_sha(value: Any, location: str) -> str:
    text = _nonempty_string(value, location)
    _require(bool(HEX40.fullmatch(text)), f"{location} must be a lowercase 40-hex commit")
    return text


def _positive_number(value: Any, location: str) -> float:
    _require(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) > 0,
        f"{location} must be finite and positive",
    )
    return float(value)


def _repo_file(root: Path, relative_path: str) -> Path:
    rel = Path(_nonempty_string(relative_path, "artifact.path"))
    _require(not rel.is_absolute(), "artifact paths must be repository-relative")
    resolved_root = root.resolve()
    resolved = (resolved_root / rel).resolve()
    _require(
        resolved == resolved_root or resolved_root in resolved.parents,
        f"artifact path escapes repository root: {relative_path}",
    )
    _require(resolved.is_file(), f"bound artifact is missing: {relative_path}")
    return resolved


def _verify_bound_files(root: Path, records: Any, location: str) -> list[dict[str, str]]:
    _require(isinstance(records, list) and records, f"{location} must be a nonempty list")
    seen: set[str] = set()
    verified: list[dict[str, str]] = []
    for index, raw in enumerate(records):
        item = _mapping(raw, f"{location}[{index}]")
        path = _nonempty_string(item.get("path"), f"{location}[{index}].path")
        expected = _sha256_text(item.get("sha256"), f"{location}[{index}].sha256")
        _require(path not in seen, f"duplicate bound path: {path}")
        seen.add(path)
        actual = hashlib.sha256(_repo_file(root, path).read_bytes()).hexdigest()
        _require(actual == expected, f"SHA-256 mismatch for {path}")
        verified.append({"path": path, "sha256": actual})
    return verified


def verify_freeze(payload: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Validate a fully populated pre-outcome successor freeze."""
    _require(payload.get("schema_version") == 1, "schema_version must be 1")
    _require(
        payload.get("status") == "FROZEN_BEFORE_OUTCOMES",
        "status must be FROZEN_BEFORE_OUTCOMES",
    )
    _require(payload.get("protected_outcomes_opened") is False, (
        "protected_outcomes_opened must be false at freeze time"
    ))
    _require(payload.get("scientific_execution_authorized") is False, (
        "freeze artifact itself must not authorize scientific execution"
    ))

    source = _mapping(payload.get("source"), "source")
    commit = _commit_sha(source.get("commit_sha"), "source.commit_sha")
    base = _mapping(source.get("base_reference"), "source.base_reference")
    _nonempty_string(base.get("name"), "source.base_reference.name")
    _commit_sha(base.get("commit_sha"), "source.base_reference.commit_sha")
    implementation = _verify_bound_files(
        repo_root, source.get("implementation_files"), "source.implementation_files"
    )
    configs = _verify_bound_files(
        repo_root, source.get("config_files"), "source.config_files"
    )

    mechanisms = _mapping(payload.get("mechanisms"), "mechanisms")
    for name in ("quaternion", "jump_flow", "residual_memory"):
        _nonempty_string(mechanisms.get(name), f"mechanisms.{name}")

    data = _mapping(payload.get("data"), "data")
    manifests = _verify_bound_files(
        repo_root,
        [data.get("manifest"), data.get("split_manifest")],
        "data.bound_manifests",
    )
    _require(data.get("entity_disjoint") is True, "data.entity_disjoint must be true")
    _require(data.get("chronological") is True, "data.chronological must be true")
    _nonempty_string(data.get("entity_key"), "data.entity_key")
    _nonempty_string(data.get("time_key"), "data.time_key")

    split_identity = _mapping(data.get("split_identity"), "data.split_identity")
    split_hashes = {}
    for name in (
        "train_sha256",
        "validation_sha256",
        "test_sha256",
        "entity_disjoint_sha256",
        "chronological_sha256",
    ):
        split_hashes[name] = _sha256_text(
            split_identity.get(name), f"data.split_identity.{name}"
        )
    _require(
        len({
            split_hashes["train_sha256"],
            split_hashes["validation_sha256"],
            split_hashes["test_sha256"],
        }) == 3,
        "train/validation/test split hashes must be distinct",
    )

    ablations = _mapping(payload.get("ablations"), "ablations")
    _require(
        set(ablations) == set(FULL_FACTORIAL),
        "ablations must contain the exact 2^3 AQPM mechanism factorial",
    )
    for name, expected_switches in FULL_FACTORIAL.items():
        cell = _mapping(ablations[name], f"ablations.{name}")
        switches = _mapping(cell.get("switches"), f"ablations.{name}.switches")
        _require(
            switches == expected_switches,
            f"ablations.{name}.switches do not match the frozen factorial cell",
        )
        _nonempty_string(cell.get("config_id"), f"ablations.{name}.config_id")
        _positive_number(
            cell.get("max_parameter_count"), f"ablations.{name}.max_parameter_count"
        )

    selection = _mapping(payload.get("selection"), "selection")
    _require(selection.get("development_only") is True, (
        "selection.development_only must be true"
    ))
    _nonempty_string(selection.get("readout"), "selection.readout")
    _nonempty_string(selection.get("selection_metric"), "selection.selection_metric")
    _nonempty_string(selection.get("test_access_rule"), "selection.test_access_rule")
    _require(selection.get("test_access_before_freeze") is False, (
        "test_access_before_freeze must be false"
    ))

    evaluation = _mapping(payload.get("evaluation"), "evaluation")
    _nonempty_string(
        evaluation.get("primary_transient_metric"),
        "evaluation.primary_transient_metric",
    )
    _nonempty_string(
        evaluation.get("calibration_metric"), "evaluation.calibration_metric"
    )
    _nonempty_string(
        evaluation.get("false_alert_metric"), "evaluation.false_alert_metric"
    )
    robustness = evaluation.get("robustness_axes")
    _require(
        isinstance(robustness, list)
        and set(robustness) == REQUIRED_ROBUSTNESS_AXES
        and len(robustness) == len(REQUIRED_ROBUSTNESS_AXES),
        "evaluation.robustness_axes must be exactly cadence, missingness, population_shift",
    )

    costs = _mapping(payload.get("cost_budget"), "cost_budget")
    for name in (
        "max_parameter_count",
        "max_training_gpu_hours",
        "max_inference_milliseconds_per_alert",
        "max_human_review_minutes_per_1000_alerts",
    ):
        _positive_number(costs.get(name), f"cost_budget.{name}")

    integration = _mapping(payload.get("integration"), "integration")
    _require(
        integration.get("siderea_separate_from_model_ranking") is True,
        "SIDEREA integration must be separated from model-ranking evidence",
    )

    boundary = _mapping(payload.get("claim_boundary"), "claim_boundary")
    _require(
        boundary.get("transfer_prior_space_jepa_evidence") is False,
        "prior Space-JEPA evidence transfer must be disabled",
    )
    _require(
        boundary.get("transfer_iris_pipeline_evidence") is False,
        "IRIS pipeline evidence transfer must be disabled",
    )
    _require(
        boundary.get("rescue_tuning_after_gate_failure") is False,
        "rescue tuning after a frozen-gate failure must be disabled",
    )

    return {
        "status": "VERIFIED_PRE_OUTCOME_FREEZE",
        "source_commit_sha": commit,
        "verified_implementation_files": implementation,
        "verified_config_files": configs,
        "verified_data_manifests": manifests,
        "verified_ablation_cells": list(FULL_FACTORIAL),
        "protected_outcomes_opened": False,
        "scientific_execution_authorized": False,
        "claim_boundary": (
            "This receipt verifies the pre-outcome successor contract only. "
            "It does not establish model efficacy and does not authorize a result."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("freeze", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    raw = json.loads(args.freeze.read_text(encoding="utf-8"))
    payload = _mapping(raw, "freeze")
    receipt = verify_freeze(payload, args.repo_root)
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.receipt is not None:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
