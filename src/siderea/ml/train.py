"""Small, reproducible training and checkpoint APIs for the SIDEREA TS-JEPA."""

from __future__ import annotations

import json
import math
import random
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from siderea.atomic import atomic_create_binary

from .dataset import (
    LightCurveBatch,
    batch_token_contract_digest,
    collate_light_curves,
    require_torch,
)
from .jepa import (
    TSJEPA,
    _representation_diagnostics_from_moments,
    make_contiguous_target_mask,
)

try:  # Optional dependency; public functions fail with a focused message.
    import torch
    from torch.utils.data import DataLoader
except ImportError:  # pragma: no cover - exercised only in torch-free installs.
    torch = None  # type: ignore[assignment]
    DataLoader = None  # type: ignore[assignment,misc]


_UNSET_TOKEN_CONTRACT = object()


def _json_safe_mapping(values: Mapping[str, Any] | None, name: str) -> dict[str, Any]:
    """Normalize transparent checkpoint metadata to weights-only-safe primitives."""

    candidate = dict(values or {})

    def validate_keys(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                if not isinstance(key, str):
                    raise ValueError(f"{path} keys must be strings")
                validate_keys(nested, f"{path}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, nested in enumerate(value):
                validate_keys(nested, f"{path}[{index}]")

    validate_keys(candidate, name)
    try:
        encoded = json.dumps(candidate, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain only finite JSON-compatible values") from exc
    decoded: Any = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise RuntimeError("JSON checkpoint metadata did not decode to an object")
    return dict(decoded)


@dataclass(frozen=True)
class TrainingConfig:
    """Conservative defaults suitable for a first local research run."""

    epochs: int = 10
    batch_size: int = 32
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    target_fraction: float = 0.25
    min_target: int = 1
    grad_clip: float = 1.0
    ema_momentum: float | None = None
    seed: int = 17
    device: str = "cpu"
    num_workers: int = 0
    shuffle: bool = True
    deterministic_algorithms: bool = True

    def __post_init__(self) -> None:
        integer_fields = {
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "min_target": self.min_target,
            "seed": self.seed,
            "num_workers": self.num_workers,
        }
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in integer_fields.values()
        ):
            raise ValueError(
                "epochs, batch_size, min_target, seed, and num_workers must be integers"
            )
        if self.epochs < 1 or self.batch_size < 1:
            raise ValueError("epochs and batch_size must be positive")
        if (
            isinstance(self.learning_rate, bool)
            or not math.isfinite(self.learning_rate)
            or self.learning_rate <= 0
        ):
            raise ValueError("learning_rate must be finite and positive")
        if (
            isinstance(self.weight_decay, bool)
            or not math.isfinite(self.weight_decay)
            or self.weight_decay < 0
        ):
            raise ValueError("weight_decay must be finite and non-negative")
        if (
            isinstance(self.target_fraction, bool)
            or not math.isfinite(self.target_fraction)
            or not 0.0 < self.target_fraction < 1.0
        ):
            raise ValueError("target_fraction must be finite and between zero and one")
        if isinstance(self.grad_clip, bool) or (
            self.min_target < 1
            or self.seed < 0
            or not math.isfinite(self.grad_clip)
            or self.grad_clip < 0
            or self.num_workers < 0
        ):
            raise ValueError(
                "min_target must be positive; seed, grad_clip, and num_workers non-negative"
            )
        if not isinstance(self.shuffle, bool):
            raise ValueError("shuffle must be boolean")
        if not isinstance(self.deterministic_algorithms, bool):
            raise ValueError("deterministic_algorithms must be boolean")
        if self.ema_momentum is not None and (
            isinstance(self.ema_momentum, bool)
            or not math.isfinite(self.ema_momentum)
            or not 0.0 <= self.ema_momentum < 1.0
        ):
            raise ValueError("ema_momentum must be finite and in [0, 1)")


def _seed_everything(seed: int, *, deterministic_algorithms: bool) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(deterministic_algorithms)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = deterministic_algorithms


def _make_loader(
    data: Any,
    *,
    batch_size: int,
    shuffle: bool,
    num_workers: int,
    generator: Any | None = None,
) -> Iterable[Any]:
    if isinstance(data, DataLoader):
        return data
    return DataLoader(
        data,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        collate_fn=collate_light_curves,
        generator=generator,
    )


def batch_tensors(batch: Any, device: Any) -> tuple[Any, Any]:
    """Extract tokens and padding masks from SIDEREA or mapping-style batches."""

    require_torch()
    if isinstance(batch, LightCurveBatch):
        return batch.tokens.to(device), batch.padding_mask.to(device)
    if isinstance(batch, Mapping):
        try:
            return batch["tokens"].to(device), batch["padding_mask"].to(device)
        except KeyError as exc:
            raise KeyError("a mapping batch requires 'tokens' and 'padding_mask'") from exc
    if isinstance(batch, (tuple, list)) and len(batch) >= 2:
        return batch[0].to(device), batch[1].to(device)
    raise TypeError("expected LightCurveBatch, mapping, or (tokens, padding_mask) batch")


def train_jepa(
    model: TSJEPA,
    data: Any,
    config: TrainingConfig | None = None,
    *,
    optimizer: Any | None = None,
) -> dict[str, Any]:
    """Train ``model`` and return JSON-serializable epoch history.

    ``data`` may be a PyTorch ``DataLoader`` or any dataset/sequence whose items
    are ``TokenizedLightCurve`` objects.  The target encoder is updated only
    after a successful optimizer step.
    """

    require_torch()
    config = config or TrainingConfig()
    _seed_everything(
        config.seed,
        deterministic_algorithms=config.deterministic_algorithms,
    )
    device = torch.device(config.device)
    model.to(device)
    model.train()
    optimizer_supplied_by_caller = optimizer is not None
    if optimizer is None:
        optimizer = torch.optim.AdamW(
            (parameter for parameter in model.parameters() if parameter.requires_grad),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
        )

    loader_generator = torch.Generator(device="cpu").manual_seed(config.seed)
    mask_generator = torch.Generator(device="cpu").manual_seed(config.seed + 1)
    loader = _make_loader(
        data,
        batch_size=config.batch_size,
        shuffle=config.shuffle,
        num_workers=config.num_workers,
        generator=loader_generator,
    )

    history: list[dict[str, Any]] = []
    total_steps = 0
    run_contract: object = _UNSET_TOKEN_CONTRACT
    for epoch in range(config.epochs):
        weighted_loss = 0.0
        target_count = 0
        collapsed_steps = 0
        epoch_steps = 0
        feature_sum: Any | None = None
        feature_outer_sum: Any | None = None
        for batch in loader:
            contract_digest = batch_token_contract_digest(batch)
            try:
                model.bind_token_contract(contract_digest)
            except ValueError as exc:
                raise ValueError(
                    "JEPA training cannot mix different or previously bound token contracts"
                ) from exc
            if run_contract is _UNSET_TOKEN_CONTRACT:
                run_contract = contract_digest
            elif contract_digest != run_contract:
                raise ValueError(
                    "JEPA training cannot mix different or unprovenanced token contracts"
                )
            tokens, padding_mask = batch_tensors(batch, device)
            target_mask = make_contiguous_target_mask(
                padding_mask,
                target_fraction=config.target_fraction,
                min_target=config.min_target,
                generator=mask_generator,
            )
            if not bool(target_mask.any()):
                continue

            optimizer.zero_grad(set_to_none=True)
            output = model(tokens, padding_mask, target_mask=target_mask)
            loss = output["loss"]
            if not bool(torch.isfinite(loss)):
                raise FloatingPointError("non-finite JEPA loss; inspect token normalization")
            loss.backward()
            if config.grad_clip:
                torch.nn.utils.clip_grad_norm_(
                    (parameter for parameter in model.parameters() if parameter.requires_grad),
                    config.grad_clip,
                    error_if_nonfinite=True,
                )
            optimizer.step()
            model.update_target_encoder(config.ema_momentum)

            count = int(output["target_mask"].sum().item())
            diagnostics = output["diagnostics"]
            selected_targets = (
                output["targets"][output["target_mask"]]
                .detach()
                .to(device="cpu", dtype=torch.float64)
            )
            if feature_sum is None:
                feature_sum = torch.zeros(selected_targets.shape[1], dtype=torch.float64)
                feature_outer_sum = torch.zeros(
                    (selected_targets.shape[1], selected_targets.shape[1]),
                    dtype=torch.float64,
                )
            feature_sum += selected_targets.sum(dim=0)
            feature_outer_sum += selected_targets.transpose(0, 1) @ selected_targets
            weighted_loss += float(loss.detach().item()) * count
            target_count += count
            collapsed_steps += int(bool(diagnostics["is_collapsed"]))
            epoch_steps += 1
            total_steps += 1

        if epoch_steps == 0:
            raise ValueError(
                "training data contain no sequence with at least two valid observations"
            )
        if feature_sum is None or feature_outer_sum is None:
            raise RuntimeError("JEPA training target moments were not accumulated")
        representation_summary = _representation_diagnostics_from_moments(
            target_count,
            feature_sum,
            feature_outer_sum,
        )
        history.append(
            {
                "epoch": epoch + 1,
                "loss": weighted_loss / target_count,
                "mean_target_feature_std": representation_summary["mean_feature_std"],
                "target_representation_diagnostics": representation_summary,
                "representation_diagnostic_scope": "all_target_tokens_in_epoch",
                "target_tokens": target_count,
                "steps": epoch_steps,
                "collapsed_step_fraction": collapsed_steps / epoch_steps,
                "collapsed_step_fraction_is_batch_dependent": True,
            }
        )

    external_loader = isinstance(data, DataLoader)
    loader_metadata: dict[str, Any] = {
        "source": "caller_dataloader" if external_loader else "siderea_constructed_dataloader",
        "training_config_loader_fields_applied": not external_loader,
    }
    if external_loader:
        loader_metadata.update(
            {
                "batch_size": data.batch_size,
                "drop_last": bool(data.drop_last),
                "sampler_class": type(data.sampler).__name__,
                "num_workers": int(data.num_workers),
            }
        )
    return {
        "format_version": 1,
        "model_config": model.get_config(),
        "training_config": asdict(config),
        "data_loader": loader_metadata,
        "optimizer_class": f"{type(optimizer).__module__}.{type(optimizer).__qualname__}",
        "optimizer_supplied_by_caller": optimizer_supplied_by_caller,
        "token_contract_sha256": (None if run_contract is _UNSET_TOKEN_CONTRACT else run_contract),
        "epochs": history,
        "total_steps": total_steps,
    }


def save_checkpoint(
    path: str | Path,
    model: TSJEPA,
    *,
    optimizer: Any | None = None,
    training_state: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a versioned checkpoint with explicit scientific provenance slots."""

    require_torch()
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_metadata: dict[str, Any] = {
        "format_version": TSJEPA.FORMAT_VERSION,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "torch_version": str(torch.__version__),
        "model_class": "TSJEPA",
        "model_config": model.get_config(),
        "token_contract_bound": model.token_contract_bound,
        "token_contract_sha256": model.token_contract_sha256,
        "user_metadata": _json_safe_mapping(metadata, "metadata"),
    }
    payload: dict[str, Any] = {
        "metadata": checkpoint_metadata,
        "model_state_dict": model.state_dict(),
        "training_state": _json_safe_mapping(training_state, "training_state"),
    }
    if optimizer is not None:
        payload["optimizer_state_dict"] = optimizer.state_dict()
    atomic_create_binary(destination, lambda handle: torch.save(payload, handle))
    return checkpoint_metadata


def load_checkpoint(
    path: str | Path,
    *,
    model: TSJEPA | None = None,
    optimizer: Any | None = None,
    map_location: str | Any = "cpu",
    strict: bool = True,
) -> tuple[TSJEPA, dict[str, Any]]:
    """Load a checkpoint, constructing the recorded model when needed."""

    require_torch()
    payload = torch.load(Path(path), map_location=map_location, weights_only=True)
    if (
        not isinstance(payload, dict)
        or "metadata" not in payload
        or "model_state_dict" not in payload
    ):
        raise ValueError("not an SIDEREA TS-JEPA checkpoint")
    metadata = payload["metadata"]
    if not isinstance(metadata, Mapping):
        raise ValueError("checkpoint metadata must be a mapping")
    if metadata.get("format_version") != TSJEPA.FORMAT_VERSION:
        raise ValueError("unsupported SIDEREA TS-JEPA checkpoint format version")
    if metadata.get("model_class") != "TSJEPA" or not isinstance(
        metadata.get("model_config"), Mapping
    ):
        raise ValueError("checkpoint metadata does not describe a TSJEPA model")
    recorded_config = dict(metadata["model_config"])
    if model is None:
        model = TSJEPA.from_config(recorded_config)
    elif model.get_config() != recorded_config:
        raise ValueError("supplied TSJEPA model config does not match checkpoint metadata")
    contract_bound = metadata.get("token_contract_bound")
    contract_digest = metadata.get("token_contract_sha256")
    if not isinstance(contract_bound, bool):
        raise ValueError("checkpoint token-contract binding metadata is invalid")
    if contract_digest is not None and not isinstance(contract_digest, str):
        raise ValueError("checkpoint token-contract digest is invalid")
    if contract_bound:
        model.bind_token_contract(contract_digest)
    elif contract_digest is not None or model.token_contract_bound:
        raise ValueError("checkpoint token-contract binding metadata is inconsistent")
    model.load_state_dict(payload["model_state_dict"], strict=strict)
    model.to(map_location)
    if optimizer is not None and "optimizer_state_dict" in payload:
        optimizer.load_state_dict(payload["optimizer_state_dict"])
    return model, payload


__all__ = [
    "TrainingConfig",
    "batch_tensors",
    "load_checkpoint",
    "save_checkpoint",
    "train_jepa",
]
