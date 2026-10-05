"""Tests for the fail-closed AQPM / Space-JEPA 2 successor freeze gate."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_aqpm_successor_freeze.py"


def _module():
    spec = importlib.util.spec_from_file_location("aqpm_freeze", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(root: Path, relative: str, content: str) -> dict[str, str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": relative, "sha256": _sha(path)}


def _valid_payload(tmp_path: Path) -> dict:
    implementation = _write(tmp_path, "src/aqpm.py", "MODEL = 'aqpm'\n")
    config = _write(tmp_path, "configs/aqpm.json", '{"version": 1}\n')
    manifest = _write(tmp_path, "data/manifest.json", '{"objects": 10}\n')
    split_manifest = _write(tmp_path, "data/splits.json", '{"entity_disjoint": true}\n')

    factorial = {
        "matched_capacity_non_aqpm": (False, False, False),
        "quaternion_only": (True, False, False),
        "jump_flow_only": (False, True, False),
        "residual_memory_only": (False, False, True),
        "quaternion_jump_flow": (True, True, False),
        "quaternion_residual_memory": (True, False, True),
        "jump_flow_residual_memory": (False, True, True),
        "aqpm_full": (True, True, True),
    }
    ablations = {
        name: {
            "config_id": f"aqpm-{name}",
            "max_parameter_count": 1000,
            "switches": {
                "quaternion": switches[0],
                "jump_flow": switches[1],
                "residual_memory": switches[2],
            },
        }
        for name, switches in factorial.items()
    }

    return {
        "schema_version": 1,
        "status": "FROZEN_BEFORE_OUTCOMES",
        "protected_outcomes_opened": False,
        "scientific_execution_authorized": False,
        "source": {
            "commit_sha": "1" * 40,
            "base_reference": {
                "name": "base-space-jepa-time-aware",
                "commit_sha": "2" * 40,
            },
            "implementation_files": [implementation],
            "config_files": [config],
        },
        "mechanisms": {
            "quaternion": "Quaternion latent transport increment over the base lane.",
            "jump_flow": "Jump-flow transition increment over the base lane.",
            "residual_memory": "Residual-memory increment over the base lane.",
        },
        "data": {
            "manifest": manifest,
            "split_manifest": split_manifest,
            "entity_disjoint": True,
            "chronological": True,
            "entity_key": "object_id",
            "time_key": "mjd",
            "split_identity": {
                "train_sha256": "a" * 64,
                "validation_sha256": "b" * 64,
                "test_sha256": "c" * 64,
                "entity_disjoint_sha256": "d" * 64,
                "chronological_sha256": "e" * 64,
            },
        },
        "ablations": ablations,
        "selection": {
            "development_only": True,
            "readout": "fixed linear transient readout",
            "selection_metric": "development average precision",
            "test_access_rule": "test outcomes remain sealed until the freeze receipt passes",
            "test_access_before_freeze": False,
        },
        "evaluation": {
            "primary_transient_metric": "average_precision",
            "calibration_metric": "expected_calibration_error",
            "false_alert_metric": "false_alerts_per_1000_events",
            "robustness_axes": ["cadence", "missingness", "population_shift"],
        },
        "cost_budget": {
            "max_parameter_count": 1000,
            "max_training_gpu_hours": 10,
            "max_inference_milliseconds_per_alert": 25,
            "max_human_review_minutes_per_1000_alerts": 120,
        },
        "integration": {"siderea_separate_from_model_ranking": True},
        "claim_boundary": {
            "transfer_prior_space_jepa_evidence": False,
            "transfer_iris_pipeline_evidence": False,
            "rescue_tuning_after_gate_failure": False,
        },
    }


def test_complete_preoutcome_freeze_verifies_bound_files(tmp_path):
    module = _module()
    receipt = module.verify_freeze(_valid_payload(tmp_path), tmp_path)

    assert receipt["status"] == "VERIFIED_PRE_OUTCOME_FREEZE"
    assert receipt["protected_outcomes_opened"] is False
    assert receipt["scientific_execution_authorized"] is False
    assert len(receipt["verified_ablation_cells"]) == 8


def test_not_frozen_status_is_rejected(tmp_path):
    module = _module()
    payload = _valid_payload(tmp_path)
    payload["status"] = "PROTOCOL_NOT_FROZEN"

    with pytest.raises(module.FreezeError, match="FROZEN_BEFORE_OUTCOMES"):
        module.verify_freeze(payload, tmp_path)


def test_protected_outcome_access_is_rejected(tmp_path):
    module = _module()
    payload = _valid_payload(tmp_path)
    payload["protected_outcomes_opened"] = True

    with pytest.raises(module.FreezeError, match="protected_outcomes_opened"):
        module.verify_freeze(payload, tmp_path)


def test_missing_factorial_cell_is_rejected(tmp_path):
    module = _module()
    payload = _valid_payload(tmp_path)
    del payload["ablations"]["quaternion_residual_memory"]

    with pytest.raises(module.FreezeError, match="2\^3 AQPM mechanism factorial"):
        module.verify_freeze(payload, tmp_path)


def test_tampered_bound_source_file_is_rejected(tmp_path):
    module = _module()
    payload = _valid_payload(tmp_path)
    (tmp_path / "src" / "aqpm.py").write_text("MODEL = 'tampered'\n", encoding="utf-8")

    with pytest.raises(module.FreezeError, match="SHA-256 mismatch"):
        module.verify_freeze(payload, tmp_path)


def test_non_entity_safe_split_is_rejected(tmp_path):
    module = _module()
    payload = _valid_payload(tmp_path)
    payload["data"]["entity_disjoint"] = False

    with pytest.raises(module.FreezeError, match="entity_disjoint"):
        module.verify_freeze(payload, tmp_path)


def test_rescue_tuning_permission_is_rejected(tmp_path):
    module = _module()
    payload = _valid_payload(tmp_path)
    payload["claim_boundary"]["rescue_tuning_after_gate_failure"] = True

    with pytest.raises(module.FreezeError, match="rescue tuning"):
        module.verify_freeze(payload, tmp_path)
