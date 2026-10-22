"""Independent gradient and compact-sequence oracles for masked encoding."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from siderea.ml.quaternion import QuaternionCausalAttention, QuaternionGate  # noqa: E402
from siderea.ml.space_jepa_v2 import AQPMJEPA, SpaceJEPA2Config  # noqa: E402


def _model() -> AQPMJEPA:
    torch.manual_seed(101)
    return (
        AQPMJEPA(
            SpaceJEPA2Config(
                input_dim=3,
                quaternion_width=2,
                encoder_blocks=1,
                attention_heads=1,
                predictor_blocks=1,
                dropout=0.0,
                horizons_days=(1.0,),
                use_continuous_flow=False,
            )
        )
        .double()
        .eval()
    )


def test_radial_gate_zero_has_the_analytic_half_identity_jacobian() -> None:
    gate = QuaternionGate(2).double()
    value = torch.zeros(1, 2, 4, dtype=torch.float64, requires_grad=True)
    gate(value).sum().backward()
    torch.testing.assert_close(value.grad, torch.full_like(value, 0.5))
    assert all(torch.isfinite(p.grad).all() for p in gate.parameters())


@pytest.mark.parametrize("mask_values", [[False, True, True], [True, False, True]])
def test_summary_matches_the_last_valid_observation_not_the_valid_count(mask_values) -> None:
    model = _model()
    values = torch.randn(1, 3, 3, dtype=torch.float64)
    mask = torch.tensor([mask_values])
    actual = model(values, mask)
    compact = values[:, mask[0]]
    expected = model(compact, torch.ones(1, 2, dtype=torch.bool))
    torch.testing.assert_close(actual["summary"], expected["summary"], rtol=1e-12, atol=1e-12)
    torch.testing.assert_close(
        actual["base_forecast"], expected["base_forecast"], rtol=1e-12, atol=1e-12
    )


@pytest.mark.parametrize("poison", [float("nan"), float("inf"), -float("inf")])
def test_padding_payload_is_excluded_before_projection_and_gradients(poison) -> None:
    model = _model()
    values = torch.randn(1, 3, 3, dtype=torch.float64)
    mask = torch.tensor([[True, False, True]])
    expected = model(values[:, [0, 2]], torch.ones(1, 2, dtype=torch.bool))["summary"]
    values[:, 1] = poison
    values.requires_grad_()
    actual = model(values, mask)["summary"]
    torch.testing.assert_close(actual, expected, rtol=1e-12, atol=1e-12)
    actual.sum().backward()
    assert torch.isfinite(values.grad).all()
    assert torch.count_nonzero(values.grad[:, 1]) == 0
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters())


def test_attention_all_masked_prefix_has_zero_finite_gradient() -> None:
    torch.manual_seed(102)
    attention = QuaternionCausalAttention(2, 1).double()
    values = torch.randn(1, 3, 2, 4, dtype=torch.float64, requires_grad=True)
    mask = torch.tensor([[False, True, True]])
    output = attention(values, mask)
    output.sum().backward()
    assert torch.isfinite(values.grad).all()
    assert torch.count_nonzero(values.grad[:, 0]) == 0
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in attention.parameters())


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_live_tokens_are_rejected(value) -> None:
    model = _model()
    tokens = torch.zeros(1, 2, 3, dtype=torch.float64)
    tokens[0, 1, 0] = value
    with pytest.raises(ValueError, match="finite"):
        model(tokens, torch.ones(1, 2, dtype=torch.bool))


def test_target_encoder_uses_the_same_last_valid_token_contract() -> None:
    model = _model()
    tokens = torch.randn(1, 1, 3, 3, dtype=torch.float64)
    mask = torch.tensor([[[True, False, True]]])
    compact = model.encode_targets(tokens[:, :, [0, 2]], torch.ones(1, 1, 2, dtype=torch.bool))
    tokens[:, :, 1] = float("nan")
    torch.testing.assert_close(model.encode_targets(tokens, mask), compact, rtol=1e-12, atol=1e-12)


def test_legacy_checkpoint_is_not_silently_reinterpreted(tmp_path, monkeypatch) -> None:
    from siderea.ml import space_jepa_v2_train as training

    checkpoint = tmp_path / "legacy.pt"
    torch.save({"metadata": {"schema": "siderea.space_jepa_v2_checkpoint.v1"}}, checkpoint)
    monkeypatch.setattr(
        training, "AQPMJEPA", lambda *a: pytest.fail("legacy identity reached model construction")
    )
    with pytest.raises(ValueError, match="schema differs"):
        training.load_space_jepa_v2_checkpoint(checkpoint)
