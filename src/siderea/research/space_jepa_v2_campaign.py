"""Resumable, fail-closed campaign shell for Space JEPA 2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from siderea.atomic import atomic_write_text
from siderea.ingest.tns_data import audit_tns_input, inspect_tns_asset
from siderea.provenance import digest_file, digest_value, stable_json, utc_now
from siderea.research.space_jepa_v2_protocol import load_space_jepa_v2_protocol

SPACE_JEPA_V2_CAMPAIGN_SCHEMA = "siderea.space_jepa_v2_campaign.v1"
SPACE_JEPA_V2_TERMINAL_STATES = frozenset(
    {
        "COMPLETED",
        "COMPLETED_NEGATIVE",
        "PARTIAL_FAILED",
        "BLOCKED_INPUT",
        "BLOCKED_VALIDATION",
        "INTERRUPTED",
    }
)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, stable_json(payload) + "\n")


def _source_digest(root: Path) -> str:
    files = sorted((root / "src/siderea").rglob("*.py"))
    return digest_value(
        [{"path": str(path.relative_to(root)), "sha256": digest_file(path)} for path in files]
    )


def run_space_jepa_v2_campaign(
    *,
    protocol_path: str | Path,
    tns_input: str | Path,
    survey_input: str | Path,
    output: str | Path,
    resume: bool = False,
    epochs: int = 10,
    batch_size: int = 32,
    device: str = "cpu",
) -> dict[str, Any]:
    """Run causal preparation, multi-seed AQPM training and held-out inference."""

    if isinstance(epochs, bool) or epochs < 1:
        raise ValueError("epochs must be a positive integer")
    if isinstance(batch_size, bool) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")

    root = Path(output).expanduser().resolve()
    if root.exists() and not resume:
        raise FileExistsError("campaign output exists; pass resume to verify and continue")
    root.mkdir(parents=True, exist_ok=True)
    for name in (
        "protocol",
        "data",
        "checkpoints",
        "memory",
        "forecasts",
        "anomaly",
        "benchmarks",
        "shadow",
        "review",
        "promotion",
        "logs",
        "failures",
    ):
        (root / name).mkdir(exist_ok=True)

    protocol = load_space_jepa_v2_protocol(protocol_path)
    existing_status = root / "status.json"
    if resume and existing_status.exists():
        previous = json.loads(existing_status.read_text(encoding="utf-8"))
        if previous.get("protocol_digest") != protocol.protocol_digest:
            raise ValueError("resume protocol digest differs from the campaign")

    status: dict[str, Any] = {
        "schema": SPACE_JEPA_V2_CAMPAIGN_SCHEMA,
        "state": "RUNNING",
        "updated_at": utc_now(),
        "protocol_digest": protocol.protocol_digest,
        "phases": {},
        "blockers": [],
        "evidence_tier": "development",
        "tns_reporting_authorized": False,
        "scientific_promotion_authorized": False,
    }
    _write_json(existing_status, status)

    canonical_protocol = {
        "protocol": dict(protocol.payload),
        "protocol_digest": protocol.protocol_digest,
    }
    _write_json(root / "protocol/protocol.json", canonical_protocol)
    tns_inventory = audit_tns_input(tns_input)
    survey_asset = inspect_tns_asset(survey_input)
    inventory = {
        "tns": tns_inventory,
        "survey": survey_asset,
        "tns_input_digest": digest_value(tns_inventory),
        "survey_input_sha256": survey_asset["sha256"],
    }
    _write_json(root / "data/inventory.json", inventory)
    status["phases"] = {
        "protocol": "passed",
        "tns_inventory": "passed",
        "survey_inventory": ("passed" if survey_asset["parse_status"] == "parsed" else "failed"),
    }
    photometry_assets = [
        Path(str(asset["path"]))
        for asset in tns_inventory["assets"]
        if asset["parse_status"] == "parsed" and asset["classification"] == "photometry"
    ]
    if survey_asset["parse_status"] == "parsed" and survey_asset["classification"] == "photometry":
        photometry_source = Path(str(survey_asset["path"]))
    elif photometry_assets:
        photometry_source = photometry_assets[0]
    else:
        photometry_source = None
    if photometry_source is None:
        status["state"] = "BLOCKED_INPUT"
        status["blockers"] = ["no model-ready time/band/measurement photometry was identified"]
    else:
        try:
            from siderea.ml.space_jepa_v2 import AQPMJEPA, SpaceJEPA2Config
            from siderea.ml.space_jepa_v2_data import (
                SPACE_JEPA_V2_INPUT_DIM,
                prepare_space_jepa_v2_batches,
            )
            from siderea.ml.space_jepa_v2_evaluate import evaluate_space_jepa_v2
            from siderea.ml.space_jepa_v2_train import (
                SpaceJEPA2TrainingConfig,
                load_space_jepa_v2_checkpoint,
                save_space_jepa_v2_checkpoint,
                train_space_jepa_v2,
            )

            try:
                import torch
            except ImportError as exc:  # pragma: no cover - depends on installation profile.
                raise RuntimeError("Space JEPA 2 campaign requires the 'ml' extra") from exc

            split = protocol.payload["split"]
            model_settings = protocol.payload["model"]
            if not isinstance(split, dict) or not isinstance(model_settings, dict):
                raise ValueError("protocol split or model settings are invalid")
            prepared = root / "data/prepared"
            prepared_manifest_path = prepared / "manifest.json"
            if prepared_manifest_path.exists():
                prepared_manifest = json.loads(prepared_manifest_path.read_text(encoding="utf-8"))
                if prepared_manifest.get("input_sha256") != digest_file(photometry_source):
                    raise ValueError("prepared data input digest differs on resume")
                prepared_identity = dict(prepared_manifest)
                stored_prepared_digest = prepared_identity.pop("result_digest", None)
                if stored_prepared_digest != digest_value(prepared_identity):
                    raise ValueError("prepared data manifest digest differs")
            else:
                prepared_manifest = prepare_space_jepa_v2_batches(
                    photometry_source,
                    prepared,
                    horizons_days=protocol.horizons_days,
                    train_fraction=float(split["train_fraction"]),
                    validation_fraction=float(split["validation_fraction"]),
                    test_fraction=float(split["test_fraction"]),
                    batch_size=batch_size,
                )
            status["phases"]["causal_preparation"] = "passed"

            def _load_batches(path: Path) -> list[dict[str, Any]]:
                value = torch.load(path, map_location="cpu", weights_only=True)
                if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
                    raise ValueError(f"prepared batch file is invalid: {path}")
                return value

            train_batches = _load_batches(prepared / "train.pt")
            validation_batches = _load_batches(prepared / "validation.pt")
            test_batches = _load_batches(prepared / "test.pt")
            data_digest = str(prepared_manifest["result_digest"])
            work_cells: list[dict[str, Any]] = []
            for seed in protocol.seeds:
                checkpoint = root / f"checkpoints/seed-{seed}.pt"
                if checkpoint.exists():
                    model, checkpoint_metadata = load_space_jepa_v2_checkpoint(
                        checkpoint, device=device
                    )
                    if checkpoint_metadata["protocol_digest"] != protocol.protocol_digest:
                        raise ValueError(f"checkpoint protocol digest differs for seed {seed}")
                    if checkpoint_metadata["data_digest"] != data_digest:
                        raise ValueError(f"checkpoint data digest differs for seed {seed}")
                    training_result = checkpoint_metadata["training_result"]
                else:
                    model_config = SpaceJEPA2Config(
                        input_dim=SPACE_JEPA_V2_INPUT_DIM,
                        quaternion_width=int(model_settings["quaternion_width"]),
                        encoder_blocks=int(model_settings["encoder_blocks"]),
                        attention_heads=int(model_settings["attention_heads"]),
                        predictor_blocks=int(model_settings["predictor_blocks"]),
                        dropout=float(model_settings["dropout"]),
                        horizons_days=protocol.horizons_days,
                    )
                    training_config = SpaceJEPA2TrainingConfig(
                        epochs=epochs,
                        learning_rate=float(model_settings["learning_rate"]),
                        weight_decay=float(model_settings["weight_decay"]),
                        gradient_clip=float(model_settings["gradient_clip"]),
                        ema_start=float(model_settings["ema_start"]),
                        ema_end=float(model_settings["ema_end"]),
                        seed=seed,
                    )
                    model = AQPMJEPA(model_config)
                    training_result = train_space_jepa_v2(
                        model,
                        train_batches,
                        validation_batches,
                        training_config,
                        device=device,
                    )
                    save_space_jepa_v2_checkpoint(
                        checkpoint,
                        model,
                        training_config=training_config,
                        training_result=training_result,
                        protocol_digest=protocol.protocol_digest,
                        data_digest=data_digest,
                    )
                validation_evaluation = evaluate_space_jepa_v2(
                    model, validation_batches, device=device
                )
                test_evaluation = evaluate_space_jepa_v2(model, test_batches, device=device)
                validation_path = root / f"forecasts/validation-seed-{seed}.json"
                test_path = root / f"forecasts/test-seed-{seed}.json"
                _write_json(validation_path, validation_evaluation)
                _write_json(test_path, test_evaluation)
                work_cells.append(
                    {
                        "seed": seed,
                        "checkpoint_sha256": digest_file(checkpoint),
                        "training": training_result,
                        "validation_result_digest": validation_evaluation["result_digest"],
                        "test_result_digest": test_evaluation["result_digest"],
                    }
                )
            _write_json(
                root / "forecasts/work-cells.json",
                {
                    "schema": "siderea.space_jepa_v2_work_cells.v1",
                    "protocol_digest": protocol.protocol_digest,
                    "data_digest": data_digest,
                    "cells": work_cells,
                },
            )
            status["phases"]["multi_seed_training"] = "passed"
            status["phases"]["validation_inference"] = "passed"
            status["phases"]["test_inference"] = "passed"
            status["state"] = "COMPLETED"
            status["completed_work_cells"] = len(work_cells)
            status["limitations"] = [
                "completion covers the predictive-core campaign only",
                "promotion remains locked until the frozen baseline, memory-control, calibration, "
                "rare-family and human-review grids pass",
            ]
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            status["state"] = "BLOCKED_VALIDATION"
            status["phases"]["predictive_core"] = "failed"
            status["blockers"] = [f"{type(exc).__name__}: {exc}"]
            _write_json(
                root / "failures/predictive-core.json",
                {
                    "schema": "siderea.space_jepa_v2_failure.v1",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
    status["updated_at"] = utc_now()
    status_identity = dict(status)
    status["status_digest"] = digest_value(status_identity)
    _write_json(existing_status, status)

    repository_root = Path(__file__).resolve().parents[3]
    manifest_identity = {
        "schema": "siderea.space_jepa_v2_run_manifest.v1",
        "protocol_digest": protocol.protocol_digest,
        "tns_inventory_digest": tns_inventory["inventory_digest"],
        "survey_input_sha256": survey_asset["sha256"],
        "code_source_digest": _source_digest(repository_root),
        "status_digest": status["status_digest"],
    }
    manifest = {**manifest_identity, "manifest_digest": digest_value(manifest_identity)}
    _write_json(root / "run-manifest.json", manifest)
    return status


def verify_space_jepa_v2_campaign(path: str | Path) -> dict[str, Any]:
    root = Path(path).expanduser().resolve()
    status_path = root / "status.json"
    manifest_path = root / "run-manifest.json"
    if not status_path.is_file() or not manifest_path.is_file():
        raise ValueError("campaign lacks status.json or run-manifest.json")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if status.get("schema") != SPACE_JEPA_V2_CAMPAIGN_SCHEMA:
        raise ValueError("campaign status schema differs")
    status_identity = dict(status)
    stored_status_digest = status_identity.pop("status_digest", None)
    if stored_status_digest != digest_value(status_identity):
        raise ValueError("campaign status digest differs")
    manifest_identity = dict(manifest)
    stored_manifest_digest = manifest_identity.pop("manifest_digest", None)
    if stored_manifest_digest != digest_value(manifest_identity):
        raise ValueError("campaign manifest digest differs")
    if manifest.get("status_digest") != stored_status_digest:
        raise ValueError("campaign manifest is bound to a different status")
    state = str(status.get("state", ""))
    if state not in SPACE_JEPA_V2_TERMINAL_STATES and state != "RUNNING":
        raise ValueError("campaign state is unrecognized")
    return {
        "schema": "siderea.space_jepa_v2_campaign_verification.v1",
        "valid": True,
        "state": state,
        "protocol_digest": status["protocol_digest"],
        "manifest_digest": stored_manifest_digest,
    }


__all__ = [
    "SPACE_JEPA_V2_CAMPAIGN_SCHEMA",
    "SPACE_JEPA_V2_TERMINAL_STATES",
    "run_space_jepa_v2_campaign",
    "verify_space_jepa_v2_campaign",
]
