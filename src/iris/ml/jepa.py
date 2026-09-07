"""A compact irregular-time Joint-Embedding Predictive Architecture.

This is a research path, not a reporting gate.  The online/context encoder sees
light-curve context with a contiguous temporal block hidden; a predictor learns
the latent representation produced for that block by an exponential-moving-
average target encoder.  Raw target values never enter the online encoder.
"""

from __future__ import annotations

import math
import re
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from .dataset import (
    BAND_INDEX,
    DELTA_TIME_INDEX,
    DETECTION_INDEX,
    ERROR_INDEX,
    TOKEN_DIM,
    VALUE_INDEX,
    VALUE_PRESENT_INDEX,
    require_torch,
)

try:  # Optional dependency: the rest of IRIS must remain importable without it.
    import torch
    from torch import nn
    from torch.nn import functional as F
except ImportError as exc:  # pragma: no cover - exercised in torch-free installs.
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR: ImportError | None = exc
else:
    _TORCH_IMPORT_ERROR = None


def _normalize_token_contract_digest(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise ValueError("token-contract digest must be a 64-character SHA-256 or None")
    return value.casefold()


def make_contiguous_target_mask(
    padding_mask: Any,
    *,
    target_fraction: float = 0.25,
    min_target: int = 1,
    generator: Any | None = None,
) -> Any:
    """Sample one contiguous target block per usable sequence.

    At least one observation remains as context.  Rows shorter than two valid
    observations receive no targets and are ignored by the loss; a batch with no
    usable target observations is rejected by :class:`TSJEPA`.
    """

    require_torch()
    if padding_mask.ndim != 2 or padding_mask.dtype != torch.bool:
        raise ValueError("padding_mask must be a boolean tensor shaped [batch, time]")
    if (
        isinstance(target_fraction, bool)
        or not math.isfinite(target_fraction)
        or not 0.0 < target_fraction < 1.0
    ):
        raise ValueError("target_fraction must be finite and between zero and one")
    if isinstance(min_target, bool) or not isinstance(min_target, int) or min_target < 1:
        raise ValueError("min_target must be a positive integer")

    target_mask = torch.zeros_like(padding_mask)
    for batch_index in range(padding_mask.shape[0]):
        valid_indices = torch.nonzero(padding_mask[batch_index], as_tuple=False).flatten()
        length = int(valid_indices.numel())
        if length < 2:
            continue
        target_count = max(min_target, int(round(length * target_fraction)))
        target_count = min(target_count, length - 1)
        last_start = length - target_count
        if last_start == 0:
            start = 0
        else:
            # Sampling on CPU keeps a caller-supplied CPU generator valid even
            # when training tensors live on an accelerator.
            start = int(torch.randint(last_start + 1, (1,), generator=generator).item())
        selected = valid_indices[start : start + target_count]
        target_mask[batch_index, selected] = True
    return target_mask


def _representation_diagnostics_from_moments(
    vector_count: int,
    feature_sum: Any,
    feature_outer_sum: Any,
    *,
    collapse_threshold: float = 0.05,
) -> dict[str, float | int | bool]:
    """Summarize exact first/second moments without retaining every vector."""

    require_torch()
    if (
        isinstance(collapse_threshold, bool)
        or not math.isfinite(collapse_threshold)
        or collapse_threshold < 0
    ):
        raise ValueError("collapse_threshold must be finite and non-negative")
    feature_count = int(feature_sum.numel())
    if vector_count == 0:
        return {
            "num_vectors": 0,
            "mean_feature_std": 0.0,
            "minimum_feature_std": 0.0,
            "collapsed_feature_fraction": 1.0,
            "representation_rms": 0.0,
            "effective_rank": 0.0,
            "effective_rank_fraction": 0.0,
            "maximum_resolvable_rank": 0,
            "is_collapsed": True,
        }
    if feature_sum.ndim != 1 or tuple(feature_outer_sum.shape) != (
        feature_count,
        feature_count,
    ):
        raise ValueError("representation moments have inconsistent dimensions")
    if not bool(torch.isfinite(feature_sum).all()) or not bool(
        torch.isfinite(feature_outer_sum).all()
    ):
        raise ValueError("representation moments must be finite")

    mean = feature_sum / vector_count
    covariance = feature_outer_sum / vector_count - torch.outer(mean, mean)
    covariance = (covariance + covariance.transpose(0, 1)) * 0.5
    feature_variance = covariance.diagonal().clamp_min(0.0)
    feature_std = feature_variance.sqrt()
    collapsed_fraction = (feature_std < collapse_threshold).float().mean()
    mean_std = feature_std.mean()

    eigenvalues = torch.linalg.eigvalsh(covariance).clamp_min(0.0)
    total_variance = eigenvalues.sum()
    maximum_rank = min(feature_count, max(vector_count - 1, 0))
    if maximum_rank and float(total_variance) > 0.0:
        probabilities = eigenvalues / total_variance
        positive = probabilities[probabilities > 0]
        effective_rank = float(torch.exp(-(positive * positive.log()).sum()).item())
        effective_rank_fraction = min(1.0, effective_rank / maximum_rank)
    else:
        effective_rank = 0.0
        effective_rank_fraction = 0.0

    mean_square = feature_outer_sum.diagonal().sum() / (vector_count * feature_count)
    return {
        "num_vectors": vector_count,
        "mean_feature_std": float(mean_std.item()),
        "minimum_feature_std": float(feature_std.min().item()),
        "collapsed_feature_fraction": float(collapsed_fraction.item()),
        "representation_rms": float(mean_square.clamp_min(0.0).sqrt().item()),
        "effective_rank": effective_rank,
        "effective_rank_fraction": effective_rank_fraction,
        "maximum_resolvable_rank": maximum_rank,
        # Preserve the original amplitude-collapse contract. Effective rank is
        # reported separately because a defensible rank threshold is dataset-
        # and representation-dimension-specific.
        "is_collapsed": bool(mean_std.item() < collapse_threshold),
    }


def representation_diagnostics(
    representations: Any,
    mask: Any | None = None,
    *,
    collapse_threshold: float = 0.05,
) -> dict[str, float | int | bool]:
    """Summarize amplitude and covariance-rank collapse diagnostics.

    ``is_collapsed`` retains the historical amplitude threshold. The effective
    rank fields expose correlated/low-rank collapse without pretending that one
    universal effective-rank threshold is scientifically justified.
    """

    require_torch()
    if representations.ndim < 2:
        raise ValueError("representations must end with a feature dimension")
    if (
        isinstance(collapse_threshold, bool)
        or not math.isfinite(collapse_threshold)
        or collapse_threshold < 0
    ):
        raise ValueError("collapse_threshold must be finite and non-negative")
    if not bool(torch.isfinite(representations).all()):
        raise ValueError("representations must be finite")
    feature_count = int(representations.shape[-1])
    if feature_count < 1:
        raise ValueError("representations must have a non-empty feature dimension")
    flat = representations.reshape(-1, feature_count)
    if mask is not None:
        if tuple(mask.shape) != tuple(representations.shape[:-1]):
            raise ValueError("diagnostic mask must match non-feature dimensions")
        if mask.dtype != torch.bool:
            raise ValueError("diagnostic mask must be boolean")
        flat = flat[mask.reshape(-1).to(device=flat.device)]
    # CPU float64 moments keep covariance/effective-rank diagnostics stable and
    # avoid backend-specific low-precision eigendecompositions.
    detached = flat.detach().to(device="cpu", dtype=torch.float64)
    return _representation_diagnostics_from_moments(
        int(detached.shape[0]),
        detached.sum(dim=0),
        detached.transpose(0, 1) @ detached,
        collapse_threshold=collapse_threshold,
    )


def _context_rebased_tokens(tokens: Any, padding_mask: Any, target_mask: Any) -> Any:
    """Rebase all values using context-only statistics to prevent target leakage.

    Tokenization uses a per-curve affine normalization for numerical stability.
    Without this second affine transform, those full-curve statistics can leak
    information about a masked target into visible context values.  Computing
    the second transform only from unmasked context cancels that dependency.
    """

    rebased = tokens.clone()
    for row in range(tokens.shape[0]):
        valid = padding_mask[row]
        context = valid & ~target_mask[row]
        if not bool(context.any()):
            continue
        value_present = tokens[row, :, VALUE_PRESENT_INDEX].gt(0.5)
        measured_context = context & value_present
        detected_context = measured_context & tokens[row, :, DETECTION_INDEX].gt(0.5)
        basis = detected_context if bool(detected_context.any()) else measured_context
        # Timing/band-only context is valid.  With no visible measured value
        # there is no leakage-free affine basis to estimate, so leave measured
        # targets in their tokenizer scale while keeping absent context content
        # at its neutral sentinel.
        if not bool(basis.any()):
            missing = valid & ~value_present
            rebased[row, missing, VALUE_INDEX] = 0.0
            rebased[row, missing, ERROR_INDEX] = 0.0
            continue
        values = tokens[row, basis, VALUE_INDEX]
        center = values.median()
        scale = (values - center).abs().median() * 1.4826
        if not bool(torch.isfinite(scale)) or float(scale) <= 0.0:
            scale = values.std(unbiased=False)
        if not bool(torch.isfinite(scale)) or float(scale) <= 0.0:
            errors = tokens[row, basis, ERROR_INDEX]
            positive_errors = errors[errors > 0]
            scale = positive_errors.median() if positive_errors.numel() else scale.new_tensor(1.0)
        if not bool(torch.isfinite(scale)) or float(scale) <= 0.0:
            scale = scale.new_tensor(1.0)
        measured = valid & value_present
        missing = valid & ~value_present
        rebased[row, measured, VALUE_INDEX] = (tokens[row, measured, VALUE_INDEX] - center) / scale
        rebased[row, measured, ERROR_INDEX] = tokens[row, measured, ERROR_INDEX] / scale
        rebased[row, missing, VALUE_INDEX] = 0.0
        rebased[row, missing, ERROR_INDEX] = 0.0
    return rebased


if nn is not None:

    class IrregularTimeEncoder(nn.Module):
        """Transformer encoder with explicit cadence, elapsed-time, and band inputs."""

        def __init__(
            self,
            *,
            token_dim: int = TOKEN_DIM,
            d_model: int = 64,
            num_bands: int = 7,
            n_heads: int = 4,
            num_layers: int = 2,
            ff_multiplier: int = 4,
            dropout: float = 0.1,
        ) -> None:
            super().__init__()
            integer_fields = {
                "token_dim": token_dim,
                "d_model": d_model,
                "num_bands": num_bands,
                "n_heads": n_heads,
                "num_layers": num_layers,
                "ff_multiplier": ff_multiplier,
            }
            if any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in integer_fields.values()
            ):
                raise ValueError("encoder dimensions and layer counts must be integers")
            if token_dim != TOKEN_DIM:
                raise ValueError(f"IRIS light-curve tokens currently require token_dim={TOKEN_DIM}")
            if n_heads < 1 or d_model < 4 or d_model % n_heads:
                raise ValueError("d_model must be at least four and divisible by n_heads")
            if num_bands < 1 or num_layers < 1 or ff_multiplier < 1:
                raise ValueError("num_bands, num_layers, and ff_multiplier must be positive")
            if isinstance(dropout, bool) or not math.isfinite(dropout) or not 0.0 <= dropout < 1.0:
                raise ValueError("dropout must be finite and within [0, 1)")

            self.token_dim = token_dim
            self.d_model = d_model
            self.num_bands = num_bands
            self.content_projection = nn.Linear(4, d_model)
            self.time_projection = nn.Sequential(
                nn.Linear(2, d_model),
                nn.GELU(),
                nn.Linear(d_model, d_model),
            )
            self.band_embedding = nn.Embedding(num_bands, d_model)
            self.mask_token = nn.Parameter(torch.zeros(1, 1, d_model))
            nn.init.normal_(self.mask_token, std=0.02)
            self.input_norm = nn.LayerNorm(d_model)
            layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=n_heads,
                dim_feedforward=d_model * ff_multiplier,
                dropout=dropout,
                activation="gelu",
                batch_first=True,
                norm_first=True,
            )
            self.transformer = nn.TransformerEncoder(
                layer,
                num_layers=num_layers,
                norm=nn.LayerNorm(d_model),
                enable_nested_tensor=False,
            )

        def embed_tokens(self, tokens: Any, target_mask: Any | None = None) -> Any:
            """Embed token content while retaining time and band at masked epochs."""

            delta = tokens[..., DELTA_TIME_INDEX].clamp_min(0.0)
            # A direct float32 cumulative sum can overflow even when every
            # individual delta is finite. log-cumulative-exp computes
            # log(1 + sum(delta)) stably without requiring accelerator-hostile
            # float64 tensors.
            negative_infinity = torch.full_like(delta, -torch.inf)
            log_delta = torch.where(delta > 0, torch.log(delta), negative_infinity)
            log_elapsed = torch.logaddexp(
                torch.zeros_like(delta),
                torch.logcumsumexp(log_delta, dim=1),
            )
            timing = torch.stack((torch.log1p(delta), log_elapsed), dim=-1)
            time_embedding = self.time_projection(timing)

            content_fields = tokens[
                ...,
                [VALUE_INDEX, ERROR_INDEX, DETECTION_INDEX, VALUE_PRESENT_INDEX],
            ]
            content_embedding = self.content_projection(content_fields)
            if target_mask is not None:
                content_embedding = torch.where(
                    target_mask.unsqueeze(-1),
                    self.mask_token.expand_as(content_embedding),
                    content_embedding,
                )

            band_ids = tokens[..., BAND_INDEX].round().long()
            return self.input_norm(
                content_embedding + time_embedding + self.band_embedding(band_ids)
            )

        def forward(
            self,
            tokens: Any,
            padding_mask: Any,
            *,
            target_mask: Any | None = None,
        ) -> Any:
            if tokens.ndim != 3 or tokens.shape[-1] != self.token_dim:
                raise ValueError(f"tokens must have shape [batch, time, {self.token_dim}]")
            if padding_mask.shape != tokens.shape[:2] or padding_mask.dtype != torch.bool:
                raise ValueError("padding_mask must be boolean and match [batch, time]")
            if not bool(padding_mask.any(dim=1).all()):
                raise ValueError("each sequence must contain at least one valid observation")
            expected_padding = torch.arange(tokens.shape[1], device=padding_mask.device).unsqueeze(
                0
            ) < padding_mask.sum(dim=1, keepdim=True)
            if not bool(torch.equal(padding_mask, expected_padding)):
                raise ValueError("valid observations must be packed before trailing padding")
            if not bool(torch.isfinite(tokens).all()):
                raise ValueError("tokens must be finite")
            valid_tokens = tokens[padding_mask]
            if bool((valid_tokens[:, DELTA_TIME_INDEX] < 0).any()):
                raise ValueError("delta times must be non-negative")
            if bool((valid_tokens[:, ERROR_INDEX] < 0).any()):
                raise ValueError("normalized errors must be non-negative")
            band_values = valid_tokens[:, BAND_INDEX]
            if bool((band_values != band_values.round()).any()) or bool(
                ((band_values < 0) | (band_values >= self.num_bands)).any()
            ):
                raise ValueError("band IDs must be integral and within the model vocabulary")
            detection_values = valid_tokens[:, DETECTION_INDEX]
            if bool(((detection_values != 0) & (detection_values != 1)).any()):
                raise ValueError("detection indicators must be zero or one")
            value_presence = valid_tokens[:, VALUE_PRESENT_INDEX]
            if bool(((value_presence != 0) & (value_presence != 1)).any()):
                raise ValueError("value-presence indicators must be zero or one")
            if bool(((detection_values == 1) & (value_presence == 0)).any()):
                raise ValueError("detected observations must contain a measured value")
            missing_values = value_presence == 0
            if bool((valid_tokens[missing_values, VALUE_INDEX] != 0).any()) or bool(
                (valid_tokens[missing_values, ERROR_INDEX] != 0).any()
            ):
                raise ValueError("missing observations must have neutral zero value/error content")
            if target_mask is not None:
                if target_mask.shape != padding_mask.shape or target_mask.dtype != torch.bool:
                    raise ValueError("target_mask must be boolean and match padding_mask")
                if bool((target_mask & ~padding_mask).any()):
                    raise ValueError("target_mask cannot select padding")

            embedded = self.embed_tokens(tokens, target_mask=target_mask)
            return self.transformer(embedded, src_key_padding_mask=~padding_mask)

    class TSJEPA(nn.Module):
        """Irregular-time latent prediction model with an EMA target encoder."""

        FORMAT_VERSION = 3

        def __init__(
            self,
            *,
            token_dim: int = TOKEN_DIM,
            d_model: int = 64,
            num_bands: int = 7,
            n_heads: int = 4,
            num_layers: int = 2,
            ff_multiplier: int = 4,
            predictor_hidden: int | None = None,
            dropout: float = 0.1,
            ema_momentum: float = 0.996,
        ) -> None:
            super().__init__()
            if (
                isinstance(ema_momentum, bool)
                or not math.isfinite(ema_momentum)
                or not 0.0 <= ema_momentum < 1.0
            ):
                raise ValueError("ema_momentum must be finite and in [0, 1)")
            if predictor_hidden is None:
                predictor_hidden = d_model * 2
            if (
                isinstance(predictor_hidden, bool)
                or not isinstance(predictor_hidden, int)
                or predictor_hidden < 1
            ):
                raise ValueError("predictor_hidden must be a positive integer")

            self.model_config: dict[str, Any] = {
                "token_dim": token_dim,
                "d_model": d_model,
                "num_bands": num_bands,
                "n_heads": n_heads,
                "num_layers": num_layers,
                "ff_multiplier": ff_multiplier,
                "predictor_hidden": predictor_hidden,
                "dropout": dropout,
                "ema_momentum": ema_momentum,
            }
            self.ema_momentum = float(ema_momentum)
            self._token_contract_bound = False
            self._token_contract_sha256: str | None = None
            self.context_encoder = IrregularTimeEncoder(
                token_dim=token_dim,
                d_model=d_model,
                num_bands=num_bands,
                n_heads=n_heads,
                num_layers=num_layers,
                ff_multiplier=ff_multiplier,
                dropout=dropout,
            )
            self.target_encoder = deepcopy(self.context_encoder)
            self.target_encoder.requires_grad_(False)
            self.target_encoder.eval()
            self.predictor = nn.Sequential(
                nn.LayerNorm(d_model),
                nn.Linear(d_model, predictor_hidden),
                nn.GELU(),
                nn.Linear(predictor_hidden, d_model),
            )

        @classmethod
        def from_config(cls, config: dict[str, Any]) -> TSJEPA:
            """Construct a model from checkpoint-safe primitive metadata."""

            return cls(**dict(config))

        def get_config(self) -> dict[str, Any]:
            return dict(self.model_config)

        @property
        def token_contract_bound(self) -> bool:
            """Whether this model has been bound to a tokenization contract."""

            return self._token_contract_bound

        @property
        def token_contract_sha256(self) -> str | None:
            """Bound contract digest, or ``None`` for an unprovenanced tensor contract."""

            return self._token_contract_sha256

        def bind_token_contract(self, digest: str | None) -> None:
            """Bind once and reject cross-contract training/evaluation thereafter."""

            normalized = _normalize_token_contract_digest(digest)
            if self._token_contract_bound and normalized != self._token_contract_sha256:
                raise ValueError("TSJEPA is already bound to a different tokenization contract")
            self._token_contract_sha256 = normalized
            self._token_contract_bound = True

        def train(self, mode: bool = True) -> TSJEPA:
            super().train(mode)
            # Targets must be stable: EMA parameters and deterministic inference.
            self.target_encoder.eval()
            return self

        @torch.no_grad()
        def update_target_encoder(self, momentum: float | None = None) -> None:
            """Move target parameters toward the context encoder after a step."""

            raw_value = self.ema_momentum if momentum is None else momentum
            if isinstance(raw_value, bool):
                raise ValueError("EMA momentum must be finite and in [0, 1)")
            value = float(raw_value)
            if not math.isfinite(value) or not 0.0 <= value < 1.0:
                raise ValueError("EMA momentum must be finite and in [0, 1)")
            for target_parameter, context_parameter in zip(
                self.target_encoder.parameters(), self.context_encoder.parameters(), strict=True
            ):
                target_parameter.mul_(value).add_(context_parameter.detach(), alpha=1.0 - value)
            for target_buffer, context_buffer in zip(
                self.target_encoder.buffers(), self.context_encoder.buffers(), strict=True
            ):
                target_buffer.copy_(context_buffer)

        def encode(self, tokens: Any, padding_mask: Any) -> Any:
            """Return online sequence representations without temporal masking."""

            return self.context_encoder(tokens, padding_mask)

        def forward(
            self,
            tokens: Any,
            padding_mask: Any,
            *,
            target_mask: Any | None = None,
            target_fraction: float = 0.25,
            min_target: int = 1,
            generator: Any | None = None,
        ) -> dict[str, Any]:
            if target_mask is None:
                target_mask = make_contiguous_target_mask(
                    padding_mask,
                    target_fraction=target_fraction,
                    min_target=min_target,
                    generator=generator,
                )
            if target_mask.shape != padding_mask.shape or target_mask.dtype != torch.bool:
                raise ValueError("target_mask must be boolean and match padding_mask")
            if bool((target_mask & ~padding_mask).any()):
                raise ValueError("target_mask cannot select padding")
            active_targets = target_mask & padding_mask
            if not bool(active_targets.any()):
                raise ValueError(
                    "the batch needs at least one sequence with two valid observations"
                )
            targeted_rows = active_targets.any(dim=1)
            has_context = (padding_mask & ~active_targets).any(dim=1)
            if bool((targeted_rows & ~has_context).any()):
                raise ValueError("every targeted sequence must retain at least one context token")

            model_tokens = _context_rebased_tokens(tokens, padding_mask, active_targets)

            context_representations = self.context_encoder(
                model_tokens,
                padding_mask,
                target_mask=active_targets,
            )
            predictions = self.predictor(context_representations)
            with torch.no_grad():
                target_representations = self.target_encoder(model_tokens, padding_mask)
                # Per-token normalization removes an arbitrary target scale while
                # preserving the direction and inter-observation structure.
                target_representations = F.layer_norm(
                    target_representations,
                    (target_representations.shape[-1],),
                )

            selected_predictions = predictions[active_targets]
            selected_targets = target_representations[active_targets]
            loss = F.smooth_l1_loss(selected_predictions, selected_targets)
            diagnostics = representation_diagnostics(selected_targets)
            return {
                "loss": loss,
                "predictions": predictions,
                "targets": target_representations,
                "target_mask": active_targets,
                "diagnostics": diagnostics,
            }


elif not TYPE_CHECKING:

    class IrregularTimeEncoder:  # pragma: no cover - torch-free compatibility shim.
        def __init__(self, *_: Any, **__: Any) -> None:
            require_torch()

    class TSJEPA:  # pragma: no cover - torch-free compatibility shim.
        def __init__(self, *_: Any, **__: Any) -> None:
            require_torch()


__all__ = [
    "IrregularTimeEncoder",
    "TSJEPA",
    "make_contiguous_target_mask",
    "representation_diagnostics",
]
