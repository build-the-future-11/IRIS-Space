from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from siderea.ml.space_jepa_v2_baselines import (  # noqa: E402
    GRUForecastBaseline,
    RealCausalTransformerBaseline,
    RealPredictiveJEPA,
)


@pytest.mark.parametrize("kind", ["gru", "transformer"])
def test_baseline_shapes_and_padding_invariance(kind: str) -> None:
    torch.manual_seed(3)
    if kind == "gru":
        model = GRUForecastBaseline(5, 8, 6, 2, layers=1, dropout=0.0)
    else:
        model = RealCausalTransformerBaseline(5, 8, 6, 2, heads=2, layers=1, dropout=0.0)
    model.eval()
    tokens = torch.randn((2, 5, 5))
    mask = torch.tensor([[True, True, True, False, False], [True] * 5])
    original = model(tokens, mask)
    changed = tokens.clone()
    changed[0, 3:] = 9999.0
    modified = model(changed, mask)
    assert original.shape == (2, 2, 6)
    assert torch.allclose(original[0], modified[0], atol=1e-5)


def test_real_predictive_jepa_has_frozen_target_and_matched_shapes() -> None:
    model = RealPredictiveJEPA(5, 8, 2, heads=2, layers=1, dropout=0.0)
    context = torch.randn((2, 4, 5))
    context_mask = torch.ones((2, 4), dtype=torch.bool)
    targets = torch.randn((2, 2, 3, 5))
    target_mask = torch.ones((2, 2, 3), dtype=torch.bool)
    prediction = model(context, context_mask)
    target = model.encode_targets(targets, target_mask)
    assert prediction.shape == target.shape == (2, 2, 8)
    assert all(not parameter.requires_grad for parameter in model.target.parameters())
    before = [parameter.clone() for parameter in model.target.parameters()]
    with torch.no_grad():
        next(model.online.parameters()).add_(1.0)
    model.update_target(0.5)
    assert any(
        not torch.equal(old, new)
        for old, new in zip(before, model.target.parameters(), strict=True)
    )
