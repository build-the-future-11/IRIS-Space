from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from siderea.ml.space_jepa_v2 import (  # noqa: E402
    AQPMJEPA,
    SpaceJEPA2Config,
    aqpm_jepa_loss,
)


def _model(*, flow: bool = False) -> AQPMJEPA:
    return AQPMJEPA(
        SpaceJEPA2Config(
            input_dim=6,
            quaternion_width=4,
            encoder_blocks=2,
            attention_heads=2,
            predictor_blocks=2,
            dropout=0.0,
            horizons_days=(1.0, 3.0),
            use_continuous_flow=flow,
            flow_steps=2,
        )
    )


def test_model_shapes_and_target_encoder_contract() -> None:
    model = _model()
    context = torch.randn((3, 5, 6))
    mask = torch.tensor(
        [
            [True, True, True, True, True],
            [True, True, True, False, False],
            [True, True, False, False, False],
        ]
    )
    output = model(context, mask)
    assert output["sequence"].shape == (3, 5, 4, 4)
    assert output["base_forecast"].shape == (3, 2, 4, 4)
    target = torch.randn((3, 2, 4, 6))
    target_mask = torch.ones((3, 2, 4), dtype=torch.bool)
    encoded = model.encode_targets(target, target_mask)
    assert encoded.shape == output["base_forecast"].shape
    assert all(not parameter.requires_grad for parameter in model.target_encoder.parameters())


def test_context_is_causal_and_padding_invariant() -> None:
    torch.manual_seed(5)
    model = _model().eval()
    context = torch.randn((1, 5, 6))
    mask = torch.tensor([[True, True, True, False, False]])
    original = model(context, mask)
    changed = context.clone()
    changed[:, 3:] = 9999.0
    modified = model(changed, mask)
    assert torch.allclose(original["summary"], modified["summary"], atol=1e-6)
    assert torch.allclose(original["base_forecast"], modified["base_forecast"], atol=1e-6)


def test_ema_update_and_loss_are_finite() -> None:
    model = _model(flow=True)
    context = torch.randn((4, 5, 6))
    mask = torch.ones((4, 5), dtype=torch.bool)
    prediction = model(context, mask)["base_forecast"]
    target = torch.randn_like(prediction)
    losses = aqpm_jepa_loss(prediction, target)
    assert torch.isfinite(losses["loss"])
    before = [parameter.clone() for parameter in model.target_encoder.parameters()]
    with torch.no_grad():
        next(model.context_encoder.parameters()).add_(1.0)
    model.update_target(0.5)
    assert any(
        not torch.equal(previous, current)
        for previous, current in zip(before, model.target_encoder.parameters(), strict=True)
    )


def test_flow_changes_longer_horizon_prediction() -> None:
    model = _model(flow=True).eval()
    context = torch.randn((2, 3, 6))
    output = model(context, torch.ones((2, 3), dtype=torch.bool))["base_forecast"]
    assert not torch.equal(output[:, 0], output[:, 1])
