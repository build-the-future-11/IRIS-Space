"""Evidence-preserving inference for the Space JEPA 2 predictive core."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from siderea.provenance import digest_value

from .quaternion import require_quaternion_torch
from .space_jepa_v2 import AQPMJEPA, aqpm_jepa_loss

try:
    import torch
except ImportError as exc:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR: ImportError | None = exc
else:
    _TORCH_IMPORT_ERROR = None


@torch.no_grad() if torch is not None else (lambda function: function)
def evaluate_space_jepa_v2(
    model: AQPMJEPA,
    batches: Sequence[Mapping[str, Any]],
    *,
    device: str = "cpu",
) -> dict[str, Any]:
    require_quaternion_torch()
    if not batches:
        raise ValueError("evaluation requires at least one batch")
    model.to(device).eval()
    rows: list[dict[str, Any]] = []
    losses: list[float] = []
    for batch_index, batch in enumerate(batches):
        required = ("context_tokens", "context_mask", "target_tokens", "target_mask")
        missing = [name for name in required if name not in batch]
        if missing:
            raise ValueError(f"evaluation batch is missing fields: {missing}")
        context = batch["context_tokens"].to(device)
        context_mask = batch["context_mask"].to(device)
        target_tokens = batch["target_tokens"].to(device)
        target_mask = batch["target_mask"].to(device)
        output = model(context, context_mask)
        target = model.encode_targets(target_tokens, target_mask)
        loss = aqpm_jepa_loss(output["base_forecast"], target)
        losses.append(float(loss["loss"].item()))
        identifiers = batch.get("example_ids")
        if identifiers is None:
            identifiers = [f"batch-{batch_index}-row-{index}" for index in range(len(context))]
        if len(identifiers) != len(context):
            raise ValueError("example_ids length differs from evaluation batch")
        for row_index, identifier in enumerate(identifiers):
            prediction = output["base_forecast"][row_index].detach().cpu().double().numpy()
            expected = target[row_index].detach().cpu().double().numpy()
            per_horizon = np.mean(np.abs(prediction - expected), axis=(1, 2))
            rows.append(
                {
                    "example_id": str(identifier),
                    "horizons_days": list(model.config.horizons_days),
                    "base_forecast": prediction.tolist(),
                    "target_latent": expected.tolist(),
                    "mean_absolute_latent_error": per_horizon.tolist(),
                    "memory_status": "not_applied",
                    "physics_status": "not_applied",
                }
            )
    identity = {
        "schema": "siderea.space_jepa_v2_evaluation.v1",
        "model_config": model.config.to_dict(),
        "batch_count": len(batches),
        "row_count": len(rows),
        "mean_loss": float(np.mean(losses)),
        "rows": rows,
    }
    return {**identity, "result_digest": digest_value(identity)}


__all__ = ["evaluate_space_jepa_v2"]
