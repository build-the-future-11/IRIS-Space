"""Matched neural forecasting baselines for the Space JEPA 2 protocol."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import TYPE_CHECKING, Any

try:
    import torch
    from torch import nn
except ImportError as exc:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    nn = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR: ImportError | None = exc
else:
    _TORCH_IMPORT_ERROR = None


def _require_torch() -> None:
    if torch is None:
        raise RuntimeError(
            "Space JEPA 2 neural baselines require the 'ml' extra"
        ) from _TORCH_IMPORT_ERROR


if nn is not None:

    class GRUForecastBaseline(nn.Module):
        def __init__(
            self,
            input_dim: int,
            hidden_dim: int,
            output_dim: int,
            horizons: int,
            *,
            layers: int = 2,
            dropout: float = 0.1,
        ) -> None:
            super().__init__()
            if min(input_dim, hidden_dim, output_dim, horizons, layers) < 1:
                raise ValueError("GRU dimensions must be positive")
            self.horizons = horizons
            self.output_dim = output_dim
            self.gru = nn.GRU(
                input_dim,
                hidden_dim,
                num_layers=layers,
                batch_first=True,
                dropout=dropout if layers > 1 else 0.0,
            )
            self.output = nn.Linear(hidden_dim, horizons * output_dim)

        def forward(self, tokens: Any, valid_mask: Any) -> Any:
            if tokens.ndim != 3 or valid_mask.shape != tokens.shape[:2]:
                raise ValueError("tokens/mask shapes differ")
            lengths = valid_mask.sum(dim=1)
            if bool((lengths < 1).any()):
                raise ValueError("every sequence needs at least one valid token")
            packed = nn.utils.rnn.pack_padded_sequence(
                tokens,
                lengths.detach().cpu(),
                batch_first=True,
                enforce_sorted=False,
            )
            _, hidden = self.gru(packed)
            return self.output(hidden[-1]).reshape(tokens.shape[0], self.horizons, self.output_dim)

    class RealCausalTransformerBaseline(nn.Module):
        def __init__(
            self,
            input_dim: int,
            hidden_dim: int,
            output_dim: int,
            horizons: int,
            *,
            heads: int = 4,
            layers: int = 4,
            dropout: float = 0.1,
        ) -> None:
            super().__init__()
            if min(input_dim, hidden_dim, output_dim, horizons, heads, layers) < 1:
                raise ValueError("Transformer dimensions must be positive")
            if hidden_dim % heads:
                raise ValueError("hidden_dim must be divisible by heads")
            if not 0.0 <= dropout < 1.0 or not math.isfinite(dropout):
                raise ValueError("dropout must lie within [0, 1)")
            self.horizons = horizons
            self.output_dim = output_dim
            self.input = nn.Linear(input_dim, hidden_dim)
            layer = nn.TransformerEncoderLayer(
                d_model=hidden_dim,
                nhead=heads,
                dim_feedforward=hidden_dim * 4,
                dropout=dropout,
                batch_first=True,
                norm_first=True,
            )
            self.encoder = nn.TransformerEncoder(layer, num_layers=layers)
            self.output = nn.Linear(hidden_dim, horizons * output_dim)

        def forward(self, tokens: Any, valid_mask: Any) -> Any:
            if tokens.ndim != 3 or valid_mask.shape != tokens.shape[:2]:
                raise ValueError("tokens/mask shapes differ")
            if bool((valid_mask.sum(dim=1) < 1).any()):
                raise ValueError("every sequence needs at least one valid token")
            steps = tokens.shape[1]
            causal = torch.ones((steps, steps), dtype=torch.bool, device=tokens.device).triu(1)
            encoded = self.encoder(
                self.input(tokens),
                mask=causal,
                src_key_padding_mask=~valid_mask,
            )
            indices = valid_mask.sum(dim=1) - 1
            summary = encoded[torch.arange(tokens.shape[0], device=tokens.device), indices]
            return self.output(summary).reshape(tokens.shape[0], self.horizons, self.output_dim)

    class RealPredictiveJEPA(nn.Module):
        """Real-valued causal JEPA control with a matched EMA target encoder."""

        def __init__(
            self,
            input_dim: int,
            hidden_dim: int,
            horizons: int,
            *,
            heads: int = 4,
            layers: int = 4,
            dropout: float = 0.1,
        ) -> None:
            super().__init__()
            self.horizons = horizons
            self.online = RealCausalTransformerBaseline(
                input_dim,
                hidden_dim,
                hidden_dim,
                1,
                heads=heads,
                layers=layers,
                dropout=dropout,
            )
            self.target = deepcopy(self.online)
            for parameter in self.target.parameters():
                parameter.requires_grad_(False)
            self.horizon_embedding = nn.Parameter(torch.zeros(horizons, hidden_dim))
            nn.init.normal_(self.horizon_embedding, mean=0.0, std=0.02)
            self.predictor = nn.Sequential(
                nn.LayerNorm(hidden_dim),
                nn.Linear(hidden_dim, hidden_dim * 2),
                nn.GELU(),
                nn.Linear(hidden_dim * 2, hidden_dim),
            )

        def train(self, mode: bool = True) -> RealPredictiveJEPA:
            super().train(mode)
            self.target.eval()
            return self

        def forward(self, tokens: Any, valid_mask: Any) -> Any:
            summary = self.online(tokens, valid_mask)[:, 0]
            value = summary[:, None, :] + self.horizon_embedding[None, :, :]
            return value + self.predictor(value)

        @torch.no_grad()
        def encode_targets(self, tokens: Any, valid_mask: Any) -> Any:
            if tokens.ndim != 4 or valid_mask.shape != tokens.shape[:3]:
                raise ValueError("target tokens/mask shapes differ")
            batch, horizons, steps, features = tokens.shape
            if horizons != self.horizons:
                raise ValueError("target horizon count differs")
            encoded = self.target(
                tokens.reshape(batch * horizons, steps, features),
                valid_mask.reshape(batch * horizons, steps),
            )
            return encoded[:, 0].reshape(batch, horizons, -1)

        @torch.no_grad()
        def update_target(self, momentum: float) -> None:
            if not math.isfinite(momentum) or not 0.0 <= momentum < 1.0:
                raise ValueError("momentum must lie within [0, 1)")
            for target, online in zip(
                self.target.parameters(), self.online.parameters(), strict=True
            ):
                target.mul_(momentum).add_(online, alpha=1.0 - momentum)


elif not TYPE_CHECKING:

    class GRUForecastBaseline:  # pragma: no cover
        def __init__(self, *_: Any, **__: Any) -> None:
            _require_torch()

    class RealCausalTransformerBaseline:  # pragma: no cover
        def __init__(self, *_: Any, **__: Any) -> None:
            _require_torch()

    class RealPredictiveJEPA:  # pragma: no cover
        def __init__(self, *_: Any, **__: Any) -> None:
            _require_torch()


__all__ = ["GRUForecastBaseline", "RealCausalTransformerBaseline", "RealPredictiveJEPA"]
