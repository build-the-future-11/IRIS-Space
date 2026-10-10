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


def _evaluation_identities(batches: Sequence[Mapping[str, Any]]) -> list[list[str]]:
    """Validate the complete row identity set before executing the model."""
    result: list[list[str]] = []
    seen: set[str] = set()
    for batch_index, batch in enumerate(batches):
        required = ("context_tokens", "context_mask", "target_tokens", "target_mask")
        missing = [name for name in required if name not in batch]
        if missing:
            raise ValueError(f"evaluation batch is missing fields: {missing}")
        context = batch["context_tokens"]
        if not isinstance(context, torch.Tensor) or context.ndim != 3 or len(context) == 0:
            raise ValueError("context_tokens must be a nonempty [batch, time, input_dim] tensor")
        identifiers = batch.get("example_ids")
        if identifiers is None:
            identifiers = [f"batch-{batch_index}-row-{index}" for index in range(len(context))]
        if (
            isinstance(identifiers, (str, bytes))
            or not isinstance(identifiers, Sequence)
            or len(identifiers) != len(context)
            or any(not isinstance(item, str) or not item.strip() for item in identifiers)
        ):
            raise ValueError("example_ids must contain one nonblank string per evaluation row")
        for identifier in identifiers:
            if identifier in seen:
                raise ValueError(f"duplicate example_id in evaluation: {identifier!r}")
            seen.add(identifier)
        result.append(list(identifiers))
    return result


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
    batch_identifiers = _evaluation_identities(batches)
    model.to(device).eval()
    rows: list[dict[str, Any]] = []
    losses: list[float] = []
    for batch, identifiers in zip(batches, batch_identifiers, strict=True):
        context = batch["context_tokens"].to(device)
        context_mask = batch["context_mask"].to(device)
        target_tokens = batch["target_tokens"].to(device)
        target_mask = batch["target_mask"].to(device)
        output = model(context, context_mask)
        target = model.encode_targets(target_tokens, target_mask)
        if not bool(torch.isfinite(output["base_forecast"]).all() & torch.isfinite(target).all()):
            raise ValueError("evaluation forecasts and targets must be finite")
        loss = aqpm_jepa_loss(output["base_forecast"], target)
        if not bool(torch.isfinite(loss["loss"])):
            raise ValueError("evaluation loss must be finite")
        losses.append(float(loss["loss"].item()))
        for row_index, identifier in enumerate(identifiers):
            prediction = output["base_forecast"][row_index].detach().cpu().double().numpy()
            expected = target[row_index].detach().cpu().double().numpy()
            per_horizon = np.mean(np.abs(prediction - expected), axis=(1, 2))
            if not np.isfinite(per_horizon).all():
                raise ValueError("evaluation errors exceed the finite numeric range")
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
