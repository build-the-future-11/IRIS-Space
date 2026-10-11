"""Analytic arithmetic failures must not become completed optimizer steps."""

from __future__ import annotations

import math
from typing import Any

import pytest

torch = pytest.importorskip("torch")

from siderea.ml.space_jepa_v2 import aqpm_jepa_loss  # noqa: E402
from siderea.ml.space_jepa_v2_train import (  # noqa: E402
    SpaceJEPA2TrainingConfig,
    evaluate_space_jepa_v2_loss,
    train_space_jepa_v2,
)


class AnalyticPredictor(torch.nn.Module):
    """Exercise the real loss and optimizer through a four-parameter model."""

    def __init__(self, scale: float = 1.0, initial: float = 0.0) -> None:
        super().__init__()
        self.context_encoder = torch.nn.Linear(1, 4, bias=False)
        torch.nn.init.constant_(self.context_encoder.weight, initial)
        self.predictor = torch.nn.Identity()
        self.scale = scale
        self.ema_calls = 0

    def forward(self, context: Any, _mask: Any) -> dict[str, Any]:
        values = self.context_encoder.weight.reshape(1, 1, 1, 4)
        multiplier = context[:, 0, 0].reshape(-1, 1, 1, 1) * self.scale
        return {"base_forecast": values * multiplier}

    def encode_targets(self, targets: Any, _mask: Any) -> Any:
        return torch.ones((len(targets), 1, 1, 4))

    def update_target(self, _momentum: float) -> None:
        self.ema_calls += 1


def _batch(values: tuple[float, float] = (1.0, 1.0)) -> dict[str, Any]:
    return {
        "context_tokens": torch.tensor(values).reshape(2, 1, 1),
        "context_mask": torch.ones((2, 1), dtype=torch.bool),
        "target_tokens": torch.ones((2, 1, 1, 1)),
        "target_mask": torch.ones((2, 1, 1), dtype=torch.bool),
    }


@pytest.mark.parametrize("scale", [1e20, 1e30])
def test_finite_loss_bad_gradient_norm_cannot_advance_optimizer_or_ema(scale: float) -> None:
    model = AnalyticPredictor(scale)
    initial = model.context_encoder.weight.detach().clone()
    observed_gradients: list[Any] = []
    model.context_encoder.weight.register_hook(
        lambda gradient: observed_gradients.append(gradient.detach().clone())
    )
    with pytest.raises(RuntimeError, match="non-finite"):
        train_space_jepa_v2(
            model, [_batch()], [_batch()], SpaceJEPA2TrainingConfig(epochs=1, seed=7)
        )
    assert model.ema_calls == 0
    assert torch.equal(model.context_encoder.weight, initial)
    assert len(observed_gradients) == 1
    assert bool(torch.isfinite(observed_gradients[0]).all()) is (scale == 1e20)
    # A failed norm check must not erase or corrupt the gradient evidence.
    assert torch.equal(model.context_encoder.weight.grad, observed_gradients[0])


def test_nonfinite_forward_loss_is_rejected_before_backward() -> None:
    model = AnalyticPredictor(scale=1e20, initial=1.0)
    initial = model.context_encoder.weight.detach().clone()
    with pytest.raises(ValueError, match="training loss.*finite"):
        train_space_jepa_v2(
            model,
            [_batch((1.0, -1.0))],
            [_batch()],
            SpaceJEPA2TrainingConfig(epochs=1, seed=7),
        )
    assert model.context_encoder.weight.grad is None
    assert torch.equal(model.context_encoder.weight, initial)
    assert model.ema_calls == 0


@pytest.mark.parametrize("initial", [float("nan"), 1.0])
def test_nonfinite_validation_loss_is_not_returned(initial: float) -> None:
    model = AnalyticPredictor(scale=1e20, initial=initial)
    with pytest.raises(ValueError, match="evaluation loss.*finite"):
        evaluate_space_jepa_v2_loss(model, [_batch((1.0, -1.0))])
    assert model.ema_calls == 0


def test_failed_validation_preserves_earlier_successful_step() -> None:
    model = AnalyticPredictor()
    with pytest.raises(ValueError, match="evaluation loss.*finite"):
        train_space_jepa_v2(
            model,
            [_batch()],
            [_batch((1e20, -1e20))],
            SpaceJEPA2TrainingConfig(epochs=1, seed=7),
        )
    assert model.ema_calls == 1
    assert bool(torch.isfinite(model.context_encoder.weight).all())
    assert bool((model.context_encoder.weight != 0).all())


def test_finite_step_retains_existing_arithmetic_exactly() -> None:
    actual = AnalyticPredictor()
    reference = AnalyticPredictor()
    reference.load_state_dict(actual.state_dict())
    batch = _batch()
    config = SpaceJEPA2TrainingConfig(epochs=1, seed=7)
    optimizer = torch.optim.AdamW(
        reference.context_encoder.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    prediction = reference(batch["context_tokens"], batch["context_mask"])["base_forecast"]
    target = reference.encode_targets(batch["target_tokens"], batch["target_mask"])
    objective = aqpm_jepa_loss(prediction, target)["loss"]
    expected_loss = objective.item()
    objective.backward()
    torch.nn.utils.clip_grad_norm_(reference.context_encoder.parameters(), config.gradient_clip)
    optimizer.step()

    result = train_space_jepa_v2(actual, [batch], [batch], config)
    assert torch.equal(actual.context_encoder.weight, reference.context_encoder.weight)
    assert result["history"][0]["train_loss"] == expected_loss
    assert result["global_steps"] == actual.ema_calls == 1
    assert math.isfinite(result["final_validation_loss"])
