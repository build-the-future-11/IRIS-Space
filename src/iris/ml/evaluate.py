"""Evaluation and embedding extraction for the optional IRIS TS-JEPA path."""

from __future__ import annotations

import math
from typing import Any

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
from .train import batch_tensors

try:  # Optional dependency; functions below provide the actionable failure.
    import torch
    from torch.utils.data import DataLoader, RandomSampler
except ImportError:  # pragma: no cover - exercised only in torch-free installs.
    torch = None  # type: ignore[assignment]
    DataLoader = None  # type: ignore[assignment,misc]
    RandomSampler = None  # type: ignore[assignment,misc]


_T_CRITICAL_95 = (
    12.706,
    4.303,
    3.182,
    2.776,
    2.571,
    2.447,
    2.365,
    2.306,
    2.262,
    2.228,
    2.201,
    2.179,
    2.160,
    2.145,
    2.131,
    2.120,
    2.110,
    2.101,
    2.093,
    2.086,
    2.080,
    2.074,
    2.069,
    2.064,
    2.060,
    2.056,
    2.052,
    2.048,
    2.045,
    2.042,
)

_UNSET_TOKEN_CONTRACT = object()


def _observe_run_contract(
    current: object,
    batch: Any,
    *,
    operation: str,
    model: TSJEPA,
) -> object:
    digest = batch_token_contract_digest(batch)
    model.bind_token_contract(digest)
    if current is _UNSET_TOKEN_CONTRACT:
        return digest
    if digest != current:
        raise ValueError(f"JEPA {operation} cannot mix different or unprovenanced token contracts")
    return current


def _t_critical_95(degrees_of_freedom: int) -> float:
    if degrees_of_freedom <= len(_T_CRITICAL_95):
        return _T_CRITICAL_95[degrees_of_freedom - 1]
    # Conservative steps toward the asymptotic normal critical value.
    if degrees_of_freedom <= 60:
        return 2.042
    if degrees_of_freedom <= 120:
        return 2.000
    return 1.980 if degrees_of_freedom <= 1_000 else 1.960


class _RepresentationMoments:
    """Exact streaming first/second moments on CPU for global diagnostics."""

    def __init__(self) -> None:
        self.count = 0
        self.feature_sum: Any | None = None
        self.feature_outer_sum: Any | None = None

    def update(self, values: Any) -> None:
        matrix = (
            values.detach()
            .reshape(-1, values.shape[-1])
            .to(
                device="cpu",
                dtype=torch.float64,
            )
        )
        if not bool(torch.isfinite(matrix).all()):
            raise FloatingPointError("non-finite JEPA representations during evaluation")
        if self.feature_sum is None:
            self.feature_sum = torch.zeros(matrix.shape[1], dtype=torch.float64)
            self.feature_outer_sum = torch.zeros(
                (matrix.shape[1], matrix.shape[1]), dtype=torch.float64
            )
        elif int(self.feature_sum.numel()) != int(matrix.shape[1]):
            raise RuntimeError("JEPA representation width changed during evaluation")
        self.count += int(matrix.shape[0])
        self.feature_sum += matrix.sum(dim=0)
        self.feature_outer_sum += matrix.transpose(0, 1) @ matrix

    def diagnostics(self) -> dict[str, float | int | bool]:
        if self.feature_sum is None or self.feature_outer_sum is None:
            raise ValueError("cannot diagnose an empty representation stream")
        return _representation_diagnostics_from_moments(
            self.count,
            self.feature_sum,
            self.feature_outer_sum,
        )


def _evaluation_loader(data: Any, batch_size: int) -> Any:
    if isinstance(data, DataLoader):
        if data.drop_last:
            raise ValueError("evaluation DataLoader must not drop the final partial batch")
        if isinstance(data.sampler, RandomSampler):
            raise ValueError("evaluation DataLoader must use deterministic non-random row ordering")
        return data
    return DataLoader(
        data,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        collate_fn=collate_light_curves,
    )


def evaluate_jepa(
    model: TSJEPA,
    data: Any,
    *,
    batch_size: int = 64,
    target_fraction: float = 0.25,
    min_target: int = 1,
    seed: int = 101,
    mask_repeats: int = 5,
    device: str = "cpu",
) -> dict[str, Any]:
    """Evaluate held-out latent prediction and collapse indicators.

    Mask sampling is seeded so checkpoint comparisons use identical target
    windows.  Results are weighted by target observation count, not batch size.
    """

    require_torch()
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    if isinstance(mask_repeats, bool) or not isinstance(mask_repeats, int) or mask_repeats < 2:
        raise ValueError("mask_repeats must be an integer of at least two")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    evaluation_device = torch.device(device)
    loader = _evaluation_loader(data, batch_size)
    was_training = model.training
    model.to(evaluation_device)
    model.eval()

    weighted_loss = 0.0
    target_count = 0
    batch_count = 0
    collapsed_batches = 0
    representation_moments = _RepresentationMoments()
    repeat_losses: list[float] = []
    repeat_target_counts: list[int] = []
    run_contract: object = _UNSET_TOKEN_CONTRACT
    try:
        with torch.no_grad():
            for repeat in range(mask_repeats):
                generator = torch.Generator(device="cpu").manual_seed(seed + repeat)
                repeat_weighted_loss = 0.0
                repeat_targets = 0
                for batch in loader:
                    run_contract = _observe_run_contract(
                        run_contract,
                        batch,
                        operation="evaluation",
                        model=model,
                    )
                    tokens, padding_mask = batch_tensors(batch, evaluation_device)
                    target_mask = make_contiguous_target_mask(
                        padding_mask,
                        target_fraction=target_fraction,
                        min_target=min_target,
                        generator=generator,
                    )
                    if not bool(target_mask.any()):
                        continue
                    output = model(tokens, padding_mask, target_mask=target_mask)
                    count = int(output["target_mask"].sum().item())
                    diagnostics = output["diagnostics"]
                    loss = float(output["loss"].item())
                    weighted_loss += loss * count
                    repeat_weighted_loss += loss * count
                    representation_moments.update(output["targets"][output["target_mask"]])
                    target_count += count
                    repeat_targets += count
                    batch_count += 1
                    collapsed_batches += int(bool(diagnostics["is_collapsed"]))
                if repeat_targets == 0:
                    raise ValueError(
                        "evaluation data contain no sequence with at least two observations"
                    )
                repeat_losses.append(repeat_weighted_loss / repeat_targets)
                repeat_target_counts.append(repeat_targets)
    finally:
        model.train(was_training)

    if len(set(repeat_target_counts)) != 1:
        raise RuntimeError(
            "evaluation target counts changed across mask repeats; the data loader is not stable"
        )
    mean_repeat_loss = sum(repeat_losses) / len(repeat_losses)
    variance = sum((value - mean_repeat_loss) ** 2 for value in repeat_losses) / (
        len(repeat_losses) - 1
    )
    loss_std = variance**0.5
    loss_standard_error = loss_std / math.sqrt(mask_repeats)
    representation_summary = representation_moments.diagnostics()
    return {
        "loss": weighted_loss / target_count,
        "mean_loss_across_masks": mean_repeat_loss,
        "loss_std_across_masks": loss_std,
        "loss_standard_error_across_masks": loss_standard_error,
        "loss_ci95_half_width": _t_critical_95(mask_repeats - 1) * loss_standard_error,
        "loss_ci95_method": "student_t_over_mask_repeats",
        "loss_ci95_scope": "mask_sampling_only_conditional_on_fixed_model_and_dataset",
        "token_contract_sha256": (None if run_contract is _UNSET_TOKEN_CONTRACT else run_contract),
        "repeat_losses": repeat_losses,
        "mask_repeats": mask_repeats,
        "mask_seeds": list(range(seed, seed + mask_repeats)),
        "mean_target_feature_std": representation_summary["mean_feature_std"],
        "target_representation_diagnostics": representation_summary,
        "representation_diagnostic_scope": "all_target_tokens_across_all_mask_repeats",
        "target_tokens": target_count,
        "target_tokens_per_repeat": repeat_target_counts,
        "batches": batch_count,
        "collapsed_batch_fraction": collapsed_batches / batch_count,
        "collapsed_batch_fraction_is_batch_dependent": True,
        "target_fraction": target_fraction,
        "seed": seed,
    }


def extract_embeddings(
    model: TSJEPA,
    data: Any,
    *,
    batch_size: int = 64,
    device: str = "cpu",
) -> dict[str, Any]:
    """Mean-pool valid online representations for retrieval/downstream models."""

    require_torch()
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    evaluation_device = torch.device(device)
    loader = _evaluation_loader(data, batch_size)
    was_training = model.training
    model.to(evaluation_device)
    model.eval()
    embeddings: list[Any] = []
    object_ids: list[str | None] = []
    representation_moments = _RepresentationMoments()
    run_contract: object = _UNSET_TOKEN_CONTRACT
    try:
        with torch.no_grad():
            for batch in loader:
                run_contract = _observe_run_contract(
                    run_contract,
                    batch,
                    operation="embedding extraction",
                    model=model,
                )
                tokens, padding_mask = batch_tensors(batch, evaluation_device)
                representations = model.encode(tokens, padding_mask)
                weights = padding_mask.unsqueeze(-1).to(representations.dtype)
                pooled = (representations * weights).sum(dim=1) / weights.sum(dim=1).clamp_min(1.0)
                embeddings.append(pooled.cpu())
                representation_moments.update(representations[padding_mask])
                if isinstance(batch, LightCurveBatch):
                    object_ids.extend(batch.object_ids)
                else:
                    object_ids.extend([None] * int(tokens.shape[0]))
    finally:
        model.train(was_training)

    if not embeddings:
        raise ValueError("cannot extract embeddings from empty data")
    all_embeddings = torch.cat(embeddings, dim=0)
    return {
        "embeddings": all_embeddings,
        "object_ids": tuple(object_ids),
        "diagnostics": representation_moments.diagnostics(),
        "token_contract_sha256": (None if run_contract is _UNSET_TOKEN_CONTRACT else run_contract),
    }


__all__ = ["evaluate_jepa", "extract_embeddings"]
