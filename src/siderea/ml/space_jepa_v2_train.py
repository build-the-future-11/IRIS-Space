"""Deterministic training and checkpointing for the Space JEPA 2 core."""

from __future__ import annotations

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np

from siderea.atomic import atomic_create_binary
from siderea.provenance import digest_value, utc_now

from .quaternion import require_quaternion_torch
from .space_jepa_v2 import (
    AQPMJEPA,
    SPACE_JEPA_V2_CHECKPOINT_SCHEMA,
    SpaceJEPA2Config,
    aqpm_jepa_loss,
)

try:
    import torch
except ImportError as exc:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR: ImportError | None = exc
else:
    _TORCH_IMPORT_ERROR = None


@dataclass(frozen=True)
class SpaceJEPA2TrainingConfig:
    epochs: int = 10
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    gradient_clip: float = 1.0
    ema_start: float = 0.996
    ema_end: float = 0.9999
    seed: int = 17
    deterministic_algorithms: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.epochs, bool) or self.epochs < 1:
            raise ValueError("epochs must be a positive integer")
        for name in ("learning_rate", "weight_decay", "gradient_clip"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be positive and finite")
        if not 0.0 < self.ema_start <= self.ema_end < 1.0:
            raise ValueError("EMA values must satisfy 0 < start <= end < 1")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")


def _seed_everything(seed: int, deterministic: bool) -> None:
    require_quaternion_torch()
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(deterministic)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.benchmark = False


def _ema_momentum(step: int, total_steps: int, start: float, end: float) -> float:
    if total_steps <= 1:
        return end
    progress = step / (total_steps - 1)
    return end - (end - start) * (math.cos(math.pi * progress) + 1.0) / 2.0


def _batch(batch: Mapping[str, Any], device: Any) -> tuple[Any, Any, Any, Any]:
    required = ("context_tokens", "context_mask", "target_tokens", "target_mask")
    missing = [name for name in required if name not in batch]
    if missing:
        raise ValueError(f"training batch is missing fields: {missing}")
    context = batch["context_tokens"].to(device)
    context_mask = batch["context_mask"].to(device)
    target = batch["target_tokens"].to(device)
    target_mask = batch["target_mask"].to(device)
    return context, context_mask, target, target_mask


@torch.no_grad() if torch is not None else (lambda function: function)
def evaluate_space_jepa_v2_loss(
    model: AQPMJEPA, batches: Sequence[Mapping[str, Any]], *, device: str = "cpu"
) -> float:
    require_quaternion_torch()
    if not batches:
        raise ValueError("evaluation requires at least one batch")
    model.eval()
    losses = []
    for raw_batch in batches:
        context, context_mask, target, target_mask = _batch(raw_batch, device)
        prediction = model(context, context_mask)["base_forecast"]
        target_latent = model.encode_targets(target, target_mask)
        losses.append(float(aqpm_jepa_loss(prediction, target_latent)["loss"].item()))
    return float(np.mean(losses))


def train_space_jepa_v2(
    model: AQPMJEPA,
    train_batches: Sequence[Mapping[str, Any]],
    validation_batches: Sequence[Mapping[str, Any]],
    config: SpaceJEPA2TrainingConfig,
    *,
    device: str = "cpu",
) -> dict[str, Any]:
    """Train the no-memory predictor and retain every epoch metric."""

    require_quaternion_torch()
    if not train_batches or not validation_batches:
        raise ValueError("training and validation each require at least one batch")
    _seed_everything(config.seed, config.deterministic_algorithms)
    model.to(device)
    trainable_parameters = tuple(model.context_encoder.parameters()) + tuple(
        model.predictor.parameters()
    )
    optimizer = torch.optim.AdamW(
        trainable_parameters,
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    total_steps = config.epochs * len(train_batches)
    global_step = 0
    history: list[dict[str, float | int]] = []
    for epoch in range(config.epochs):
        model.train()
        epoch_losses: list[float] = []
        for raw_batch in train_batches:
            context, context_mask, target, target_mask = _batch(raw_batch, device)
            optimizer.zero_grad(set_to_none=True)
            prediction = model(context, context_mask)["base_forecast"]
            target_latent = model.encode_targets(target, target_mask)
            losses = aqpm_jepa_loss(prediction, target_latent)
            losses["loss"].backward()
            torch.nn.utils.clip_grad_norm_(
                trainable_parameters,
                config.gradient_clip,
            )
            optimizer.step()
            momentum = _ema_momentum(global_step, total_steps, config.ema_start, config.ema_end)
            model.update_target(momentum)
            epoch_losses.append(float(losses["loss"].detach().item()))
            global_step += 1
        validation_loss = evaluate_space_jepa_v2_loss(model, validation_batches, device=device)
        history.append(
            {
                "epoch": epoch + 1,
                "train_loss": float(np.mean(epoch_losses)),
                "validation_loss": validation_loss,
                "ema_momentum": momentum,
            }
        )
    return {
        "schema": "siderea.space_jepa_v2_training.v1",
        "seed": config.seed,
        "epochs": config.epochs,
        "global_steps": global_step,
        "history": history,
        "final_validation_loss": history[-1]["validation_loss"],
    }


def save_space_jepa_v2_checkpoint(
    path: str | Path,
    model: AQPMJEPA,
    *,
    training_config: SpaceJEPA2TrainingConfig,
    training_result: Mapping[str, Any],
    protocol_digest: str,
    data_digest: str,
) -> Path:
    require_quaternion_torch()
    for name, value in (("protocol_digest", protocol_digest), ("data_digest", data_digest)):
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    metadata = {
        "schema": SPACE_JEPA_V2_CHECKPOINT_SCHEMA,
        "created_at": utc_now(),
        "model_config": model.config.to_dict(),
        "training_config": asdict(training_config),
        "training_result": dict(training_result),
        "protocol_digest": protocol_digest,
        "data_digest": data_digest,
    }
    metadata["metadata_digest"] = digest_value(metadata)
    payload = {
        "metadata": metadata,
        "model_state": model.state_dict(),
        "torch_rng_state": torch.get_rng_state(),
        "numpy_random_state": np.random.get_state(),
        "python_random_state": random.getstate(),
    }

    def _write(handle: BinaryIO) -> None:
        torch.save(payload, handle)

    return atomic_create_binary(path, _write)


def load_space_jepa_v2_checkpoint(
    path: str | Path, *, device: str = "cpu"
) -> tuple[AQPMJEPA, dict[str, Any]]:
    require_quaternion_torch()
    try:
        payload = torch.load(Path(path), map_location=device, weights_only=False)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise ValueError(f"cannot load Space JEPA 2 checkpoint: {exc}") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("metadata"), Mapping):
        raise ValueError("Space JEPA 2 checkpoint lacks metadata")
    metadata = dict(payload["metadata"])
    if metadata.get("schema") != SPACE_JEPA_V2_CHECKPOINT_SCHEMA:
        raise ValueError("Space JEPA 2 checkpoint schema differs")
    stored_digest = metadata.pop("metadata_digest", None)
    if stored_digest != digest_value(metadata):
        raise ValueError("Space JEPA 2 checkpoint metadata digest differs")
    metadata["metadata_digest"] = stored_digest
    raw_config = metadata.get("model_config")
    if not isinstance(raw_config, Mapping):
        raise ValueError("Space JEPA 2 checkpoint lacks model configuration")
    model = AQPMJEPA(SpaceJEPA2Config.from_dict(dict(raw_config)))
    model.load_state_dict(payload["model_state"], strict=True)
    model.to(device)
    return model, metadata


__all__ = [
    "SpaceJEPA2TrainingConfig",
    "evaluate_space_jepa_v2_loss",
    "load_space_jepa_v2_checkpoint",
    "save_space_jepa_v2_checkpoint",
    "train_space_jepa_v2",
]
