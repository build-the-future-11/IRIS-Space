"""Causal APENic Quaternion Predictive-Memory JEPA core.

This module implements the predictive engine only. Episodic memory, physics and
pipeline ranking remain separately inspectable components.
"""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from .quaternion import (
    QuaternionCausalAttention,
    QuaternionGate,
    QuaternionLinear,
    QuaternionRMSNorm,
    hamilton_product,
    require_quaternion_torch,
)

try:
    import torch
    from torch import nn
    from torch.nn import functional as F
except ImportError as exc:  # pragma: no cover - depends on installation profile.
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR: ImportError | None = exc
else:
    _TORCH_IMPORT_ERROR = None

SPACE_JEPA_V2_CHECKPOINT_SCHEMA = "siderea.space_jepa_v2_checkpoint.v1"


@dataclass(frozen=True)
class SpaceJEPA2Config:
    input_dim: int
    quaternion_width: int = 64
    encoder_blocks: int = 6
    attention_heads: int = 8
    predictor_blocks: int = 3
    dropout: float = 0.1
    horizons_days: tuple[float, ...] = (1.0, 3.0, 7.0, 14.0)
    use_continuous_flow: bool = True
    flow_steps: int = 4

    def __post_init__(self) -> None:
        for name in (
            "input_dim",
            "quaternion_width",
            "encoder_blocks",
            "attention_heads",
            "predictor_blocks",
            "flow_steps",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.quaternion_width % self.attention_heads:
            raise ValueError("quaternion_width must be divisible by attention_heads")
        if not math.isfinite(self.dropout) or not 0.0 <= self.dropout < 1.0:
            raise ValueError("dropout must be within [0, 1)")
        if not self.horizons_days or any(
            not math.isfinite(value) or value <= 0.0 for value in self.horizons_days
        ):
            raise ValueError("horizons_days must contain positive finite values")
        if tuple(sorted(self.horizons_days)) != self.horizons_days:
            raise ValueError("horizons_days must be strictly increasing")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["horizons_days"] = list(self.horizons_days)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SpaceJEPA2Config:
        values = dict(payload)
        values["horizons_days"] = tuple(float(item) for item in values["horizons_days"])
        return cls(**values)


if nn is not None:

    class QuaternionEncoderBlock(nn.Module):
        def __init__(self, channels: int, heads: int, dropout: float) -> None:
            super().__init__()
            self.norm_attention = QuaternionRMSNorm(channels)
            self.attention = QuaternionCausalAttention(channels, heads, dropout=dropout)
            self.norm_feedforward = QuaternionRMSNorm(channels)
            self.feedforward_in = QuaternionLinear(channels, channels * 2)
            self.gate = QuaternionGate(channels * 2)
            self.feedforward_out = QuaternionLinear(channels * 2, channels)
            self.dropout = nn.Dropout(dropout)

        def forward(self, value: Any, valid_mask: Any) -> Any:
            attended = self.attention(self.norm_attention(value), valid_mask)
            value = value + self.dropout(attended)
            hidden = self.gate(self.feedforward_in(self.norm_feedforward(value)))
            value = value + self.dropout(self.feedforward_out(hidden))
            return value * valid_mask[:, :, None, None]

    class QuaternionEncoder(nn.Module):
        def __init__(self, config: SpaceJEPA2Config) -> None:
            super().__init__()
            self.config = config
            self.input_projection = nn.Linear(config.input_dim, config.quaternion_width * 4)
            self.blocks = nn.ModuleList(
                QuaternionEncoderBlock(
                    config.quaternion_width, config.attention_heads, config.dropout
                )
                for _ in range(config.encoder_blocks)
            )
            self.output_norm = QuaternionRMSNorm(config.quaternion_width)

        def forward(self, tokens: Any, valid_mask: Any) -> tuple[Any, Any]:
            if tokens.ndim != 3 or tokens.shape[-1] != self.config.input_dim:
                raise ValueError("tokens must have shape [batch, time, input_dim]")
            if valid_mask.shape != tokens.shape[:2] or valid_mask.dtype != torch.bool:
                raise ValueError("valid_mask must be boolean with shape [batch, time]")
            if bool((valid_mask.sum(dim=1) < 1).any()):
                raise ValueError("every sequence needs at least one valid token")
            value = self.input_projection(tokens).reshape(
                tokens.shape[0], tokens.shape[1], self.config.quaternion_width, 4
            )
            value = value * valid_mask[:, :, None, None]
            for block in self.blocks:
                value = block(value, valid_mask)
            value = self.output_norm(value) * valid_mask[:, :, None, None]
            indices = valid_mask.sum(dim=1) - 1
            summary = value[torch.arange(tokens.shape[0], device=tokens.device), indices]
            return value, summary

    class QuaternionJumpFlow(nn.Module):
        """Euler-integrated left/right quaternion flow between observations."""

        def __init__(self, channels: int, steps: int) -> None:
            super().__init__()
            self.channels = channels
            self.steps = steps
            scale = 1.0 / math.sqrt(channels * 4)
            self.left = nn.Parameter(torch.empty(channels, channels, 4))
            self.right = nn.Parameter(torch.empty(channels, channels, 4))
            self.drive = nn.Parameter(torch.zeros(channels, 4))
            nn.init.uniform_(self.left, -scale, scale)
            nn.init.uniform_(self.right, -scale, scale)

        def derivative(self, state: Any) -> Any:
            left_terms = hamilton_product(self.left, state.unsqueeze(-3)).sum(dim=-2)
            right_terms = hamilton_product(state.unsqueeze(-2), self.right.transpose(0, 1)).sum(
                dim=-3
            )
            return torch.tanh(left_terms + right_terms + self.drive)

        def forward(self, state: Any, delta_days: float) -> Any:
            if not math.isfinite(delta_days) or delta_days <= 0.0:
                raise ValueError("delta_days must be positive and finite")
            step = min(delta_days, 30.0) / (30.0 * self.steps)
            value = state
            for _ in range(self.steps):
                value = value + step * self.derivative(value)
            return value

    class QuaternionPredictor(nn.Module):
        def __init__(self, config: SpaceJEPA2Config) -> None:
            super().__init__()
            self.config = config
            self.horizon_embedding = nn.Parameter(
                torch.zeros(len(config.horizons_days), config.quaternion_width, 4)
            )
            nn.init.normal_(self.horizon_embedding, mean=0.0, std=0.02)
            self.flow = (
                QuaternionJumpFlow(config.quaternion_width, config.flow_steps)
                if config.use_continuous_flow
                else None
            )
            self.layers = nn.ModuleList(
                QuaternionLinear(config.quaternion_width, config.quaternion_width)
                for _ in range(config.predictor_blocks)
            )
            self.gates = nn.ModuleList(
                QuaternionGate(config.quaternion_width) for _ in range(config.predictor_blocks)
            )
            self.norm = QuaternionRMSNorm(config.quaternion_width)

        def forward(self, summary: Any) -> Any:
            outputs = []
            for index, horizon in enumerate(self.config.horizons_days):
                value = summary
                if self.flow is not None:
                    value = self.flow(value, horizon)
                value = value + self.horizon_embedding[index]
                for layer, gate in zip(self.layers, self.gates, strict=True):
                    value = value + gate(layer(self.norm(value)))
                outputs.append(self.norm(value))
            return torch.stack(outputs, dim=1)

    class AQPMJEPA(nn.Module):
        """No-memory predictive core with an EMA target encoder."""

        def __init__(self, config: SpaceJEPA2Config) -> None:
            super().__init__()
            self.config = config
            self.context_encoder = QuaternionEncoder(config)
            self.target_encoder = deepcopy(self.context_encoder)
            for parameter in self.target_encoder.parameters():
                parameter.requires_grad_(False)
            self.predictor = QuaternionPredictor(config)
            self.target_encoder.eval()

        def train(self, mode: bool = True) -> AQPMJEPA:
            super().train(mode)
            self.target_encoder.eval()
            return self

        def forward(self, context_tokens: Any, context_mask: Any) -> dict[str, Any]:
            sequence, summary = self.context_encoder(context_tokens, context_mask)
            return {
                "sequence": sequence,
                "summary": summary,
                "base_forecast": self.predictor(summary),
            }

        @torch.no_grad()
        def encode_targets(self, target_tokens: Any, target_mask: Any) -> Any:
            if target_tokens.ndim != 4:
                raise ValueError("target_tokens must have shape [batch, horizon, time, input_dim]")
            if target_mask.shape != target_tokens.shape[:3]:
                raise ValueError("target_mask must match target batch/horizon/time")
            batch, horizons, steps, features = target_tokens.shape
            if horizons != len(self.config.horizons_days):
                raise ValueError("target horizon count differs from configuration")
            flattened_tokens = target_tokens.reshape(batch * horizons, steps, features)
            flattened_mask = target_mask.reshape(batch * horizons, steps)
            _, summary = self.target_encoder(flattened_tokens, flattened_mask)
            return summary.reshape(batch, horizons, self.config.quaternion_width, 4)

        @torch.no_grad()
        def update_target(self, momentum: float) -> None:
            if not math.isfinite(momentum) or not 0.0 <= momentum < 1.0:
                raise ValueError("momentum must lie within [0, 1)")
            for target, online in zip(
                self.target_encoder.parameters(),
                self.context_encoder.parameters(),
                strict=True,
            ):
                target.mul_(momentum).add_(online, alpha=1.0 - momentum)

    def aqpm_jepa_loss(
        prediction: Any,
        target: Any,
        *,
        variance_floor: float = 0.1,
        covariance_weight: float = 0.01,
        variance_weight: float = 0.1,
    ) -> dict[str, Any]:
        if prediction.shape != target.shape or prediction.ndim != 4 or prediction.shape[-1] != 4:
            raise ValueError("prediction and target must be equal [batch, horizon, channels, 4]")
        predicted = prediction.reshape(prediction.shape[0], prediction.shape[1], -1)
        expected = target.detach().reshape(target.shape[0], target.shape[1], -1)
        predicted = F.normalize(predicted, dim=-1)
        expected = F.normalize(expected, dim=-1)
        jepa = F.smooth_l1_loss(predicted, expected)
        flat = prediction.reshape(-1, prediction.shape[-2] * 4)
        standard_deviation = torch.sqrt(flat.var(dim=0, unbiased=False) + 1e-6)
        variance = torch.relu(variance_floor - standard_deviation).square().mean()
        centered = flat - flat.mean(dim=0, keepdim=True)
        denominator = max(flat.shape[0] - 1, 1)
        covariance = centered.transpose(0, 1) @ centered / denominator
        off_diagonal = covariance - torch.diag(torch.diagonal(covariance))
        covariance_loss = off_diagonal.square().sum() / flat.shape[1]
        total = jepa + variance_weight * variance + covariance_weight * covariance_loss
        return {
            "loss": total,
            "jepa_loss": jepa,
            "variance_loss": variance,
            "covariance_loss": covariance_loss,
        }


elif not TYPE_CHECKING:

    class AQPMJEPA:  # pragma: no cover - torch-free compatibility shim.
        def __init__(self, *_: Any, **__: Any) -> None:
            require_quaternion_torch()

    class QuaternionEncoder:  # pragma: no cover
        def __init__(self, *_: Any, **__: Any) -> None:
            require_quaternion_torch()

    class QuaternionJumpFlow:  # pragma: no cover
        def __init__(self, *_: Any, **__: Any) -> None:
            require_quaternion_torch()

    class QuaternionPredictor:  # pragma: no cover
        def __init__(self, *_: Any, **__: Any) -> None:
            require_quaternion_torch()

    def aqpm_jepa_loss(*_: Any, **__: Any) -> dict[str, Any]:  # pragma: no cover
        require_quaternion_torch()
        return {}


__all__ = [
    "AQPMJEPA",
    "SPACE_JEPA_V2_CHECKPOINT_SCHEMA",
    "QuaternionEncoder",
    "QuaternionJumpFlow",
    "QuaternionPredictor",
    "SpaceJEPA2Config",
    "aqpm_jepa_loss",
]
