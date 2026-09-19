"""Quaternion algebra and neural layers for the Space JEPA 2 engine.

Quaternions are stored as real tensors whose final dimension is ordered
``(scalar, i, j, k)``. All learned products use left Hamilton multiplication.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

try:  # Keep the non-ML SIDEREA installation importable.
    import torch
    from torch import nn
except ImportError as exc:  # pragma: no cover - depends on installation profile.
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR: ImportError | None = exc
else:
    _TORCH_IMPORT_ERROR = None


def require_quaternion_torch() -> None:
    if torch is None:
        raise RuntimeError(
            "Space JEPA 2 quaternion layers require the 'ml' extra"
        ) from _TORCH_IMPORT_ERROR


def _check_quaternion(value: Any, name: str) -> None:
    require_quaternion_torch()
    if not torch.is_tensor(value) or value.ndim < 1 or value.shape[-1] != 4:
        raise ValueError(f"{name} must be a tensor with final dimension 4")


def hamilton_product(left: Any, right: Any) -> Any:
    """Return the broadcast Hamilton product ``left * right``."""

    _check_quaternion(left, "left")
    _check_quaternion(right, "right")
    a, b, c, d = left.unbind(dim=-1)
    e, f, g, h = right.unbind(dim=-1)
    return torch.stack(
        (
            a * e - b * f - c * g - d * h,
            a * f + b * e + c * h - d * g,
            a * g - b * h + c * e + d * f,
            a * h + b * g - c * f + d * e,
        ),
        dim=-1,
    )


def quaternion_conjugate(value: Any) -> Any:
    _check_quaternion(value, "value")
    signs = value.new_tensor((1.0, -1.0, -1.0, -1.0))
    return value * signs


def quaternion_norm_squared(value: Any, *, keepdim: bool = False) -> Any:
    _check_quaternion(value, "value")
    return value.square().sum(dim=-1, keepdim=keepdim)


def quaternion_norm(value: Any, *, keepdim: bool = False, epsilon: float = 0.0) -> Any:
    if epsilon < 0.0 or not math.isfinite(epsilon):
        raise ValueError("epsilon must be finite and non-negative")
    return (quaternion_norm_squared(value, keepdim=keepdim) + epsilon).sqrt()


def quaternion_inverse(value: Any, *, epsilon: float = 1e-12) -> Any:
    _check_quaternion(value, "value")
    if epsilon <= 0.0 or not math.isfinite(epsilon):
        raise ValueError("epsilon must be positive and finite")
    denominator = quaternion_norm_squared(value, keepdim=True)
    if bool((denominator <= epsilon).any()):
        raise ValueError("cannot invert a zero or near-zero quaternion")
    return quaternion_conjugate(value) / denominator


def quaternion_real_matrix(weight: Any) -> Any:
    """Return the real matrix for left multiplication by ``weight``.

    Input shape ``[..., 4]`` becomes ``[..., 4, 4]``.
    """

    _check_quaternion(weight, "weight")
    a, b, c, d = weight.unbind(dim=-1)
    return torch.stack(
        (
            torch.stack((a, -b, -c, -d), dim=-1),
            torch.stack((b, a, -d, c), dim=-1),
            torch.stack((c, d, a, -b), dim=-1),
            torch.stack((d, -c, b, a), dim=-1),
        ),
        dim=-2,
    )


if nn is not None:

    class QuaternionLinear(nn.Module):
        """Dense quaternion map using left Hamilton multiplication."""

        def __init__(self, in_channels: int, out_channels: int, *, bias: bool = True) -> None:
            super().__init__()
            if in_channels < 1 or out_channels < 1:
                raise ValueError("quaternion channel counts must be positive")
            self.in_channels = in_channels
            self.out_channels = out_channels
            self.weight = nn.Parameter(torch.empty(out_channels, in_channels, 4))
            if bias:
                self.bias = nn.Parameter(torch.empty(out_channels, 4))
            else:
                self.register_parameter("bias", None)
            self.reset_parameters()

        def reset_parameters(self) -> None:
            bound = 1.0 / math.sqrt(self.in_channels * 4)
            nn.init.uniform_(self.weight, -bound, bound)
            if self.bias is not None:
                nn.init.uniform_(self.bias, -bound, bound)

        def forward(self, value: Any) -> Any:
            _check_quaternion(value, "value")
            if value.shape[-2] != self.in_channels:
                raise ValueError(
                    f"expected {self.in_channels} quaternion channels, got {value.shape[-2]}"
                )
            # Contract through the 4x4 real representation without materializing
            # [..., out_channels, in_channels, 4] Hamilton products. This keeps
            # peak activation memory independent of the input/output channel
            # product while preserving the exact left-multiplication convention.
            matrix = quaternion_real_matrix(self.weight)
            output = torch.einsum("oicd,...id->...oc", matrix, value)
            if self.bias is not None:
                output = output + self.bias
            return output

    class QuaternionRMSNorm(nn.Module):
        def __init__(self, channels: int, *, epsilon: float = 1e-6) -> None:
            super().__init__()
            if channels < 1:
                raise ValueError("channels must be positive")
            if epsilon <= 0.0 or not math.isfinite(epsilon):
                raise ValueError("epsilon must be positive and finite")
            self.channels = channels
            self.epsilon = epsilon
            self.gain = nn.Parameter(torch.ones(channels))

        def forward(self, value: Any) -> Any:
            _check_quaternion(value, "value")
            if value.shape[-2] != self.channels:
                raise ValueError(f"expected {self.channels} quaternion channels")
            rms = value.square().sum(dim=-1).mean(dim=-1, keepdim=True)
            normalized = value / (rms + self.epsilon).sqrt().unsqueeze(-1)
            return normalized * self.gain.view(*((1,) * (value.ndim - 2)), -1, 1)

    class QuaternionGate(nn.Module):
        """Learned real radial gate that preserves quaternion direction."""

        def __init__(self, channels: int) -> None:
            super().__init__()
            if channels < 1:
                raise ValueError("channels must be positive")
            self.channels = channels
            self.slope = nn.Parameter(torch.ones(channels))
            self.bias = nn.Parameter(torch.zeros(channels))

        def forward(self, value: Any) -> Any:
            _check_quaternion(value, "value")
            if value.shape[-2] != self.channels:
                raise ValueError(f"expected {self.channels} quaternion channels")
            magnitude = quaternion_norm(value)
            gate = torch.sigmoid(magnitude * self.slope + self.bias)
            return value * gate.unsqueeze(-1)

    class QuaternionCausalAttention(nn.Module):
        """Causal self-attention with quaternion projections and real logits."""

        def __init__(
            self,
            channels: int,
            heads: int,
            *,
            dropout: float = 0.0,
        ) -> None:
            super().__init__()
            if channels < 1 or heads < 1 or channels % heads:
                raise ValueError("channels must be positive and divisible by heads")
            if not 0.0 <= dropout < 1.0:
                raise ValueError("dropout must be within [0, 1)")
            self.channels = channels
            self.heads = heads
            self.head_channels = channels // heads
            self.query = QuaternionLinear(channels, channels)
            self.key = QuaternionLinear(channels, channels)
            self.value = QuaternionLinear(channels, channels)
            self.output = QuaternionLinear(channels, channels)
            self.dropout = nn.Dropout(dropout)
            self._causal_mask: Any
            self.register_buffer(
                "_causal_mask", torch.empty((0, 0), dtype=torch.bool), persistent=False
            )

        def forward(self, value: Any, valid_mask: Any | None = None) -> Any:
            _check_quaternion(value, "value")
            if value.ndim != 4 or value.shape[-2] != self.channels:
                raise ValueError("value must have shape [batch, time, channels, 4]")
            batch, steps = value.shape[:2]
            if valid_mask is None:
                valid_mask = torch.ones((batch, steps), dtype=torch.bool, device=value.device)
            if valid_mask.shape != (batch, steps) or valid_mask.dtype != torch.bool:
                raise ValueError("valid_mask must be boolean with shape [batch, time]")

            def _heads(projected: Any) -> Any:
                return projected.reshape(batch, steps, self.heads, self.head_channels, 4)

            query = _heads(self.query(value))
            key = _heads(self.key(value))
            projected_value = _heads(self.value(value))
            logits = torch.einsum("bthdc,bshdc->bhts", query, key)
            logits = logits / math.sqrt(4 * self.head_channels)
            if self._causal_mask.device != value.device or self._causal_mask.shape[0] < steps:
                self._causal_mask = torch.ones(
                    (steps, steps), dtype=torch.bool, device=value.device
                ).tril()
            causal = self._causal_mask[:steps, :steps]
            allowed = causal.view(1, 1, steps, steps) & valid_mask[:, None, None, :]
            logits = logits.masked_fill(~allowed, float("-inf"))
            attention = torch.softmax(logits, dim=-1)
            attention = torch.nan_to_num(attention, nan=0.0)
            attention = self.dropout(attention)
            attended = torch.einsum("bhts,bshdc->bthdc", attention, projected_value)
            attended = attended.reshape(batch, steps, self.channels, 4)
            output = self.output(attended)
            return output * valid_mask[:, :, None, None]


elif not TYPE_CHECKING:

    class QuaternionLinear:  # pragma: no cover - torch-free compatibility shim.
        def __init__(self, *_: Any, **__: Any) -> None:
            require_quaternion_torch()

    class QuaternionRMSNorm:  # pragma: no cover
        def __init__(self, *_: Any, **__: Any) -> None:
            require_quaternion_torch()

    class QuaternionGate:  # pragma: no cover
        def __init__(self, *_: Any, **__: Any) -> None:
            require_quaternion_torch()

    class QuaternionCausalAttention:  # pragma: no cover
        def __init__(self, *_: Any, **__: Any) -> None:
            require_quaternion_torch()


__all__ = [
    "QuaternionCausalAttention",
    "QuaternionGate",
    "QuaternionLinear",
    "QuaternionRMSNorm",
    "hamilton_product",
    "quaternion_conjugate",
    "quaternion_inverse",
    "quaternion_norm",
    "quaternion_norm_squared",
    "quaternion_real_matrix",
    "require_quaternion_torch",
]
