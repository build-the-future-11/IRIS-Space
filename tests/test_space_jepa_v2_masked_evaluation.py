from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

torch = pytest.importorskip("torch")

from siderea.cli import main  # noqa: E402
from siderea.ml.space_jepa_v2 import AQPMJEPA, SpaceJEPA2Config  # noqa: E402
from siderea.ml.space_jepa_v2_evaluate import evaluate_space_jepa_v2  # noqa: E402
from siderea.ml.space_jepa_v2_train import (  # noqa: E402
    SpaceJEPA2TrainingConfig,
    save_space_jepa_v2_checkpoint,
)


def _model() -> AQPMJEPA:
    torch.manual_seed(123)
    return AQPMJEPA(
        SpaceJEPA2Config(
            input_dim=3,
            quaternion_width=2,
            encoder_blocks=1,
            attention_heads=1,
            predictor_blocks=1,
            dropout=0.0,
            horizons_days=(1.0, 3.0),
            use_continuous_flow=False,
        )
    ).eval()


def _batch(prefix: str = "example") -> dict[str, Any]:
    generator = torch.Generator().manual_seed(17)
    return {
        "context_tokens": torch.randn((2, 3, 3), generator=generator),
        "context_mask": torch.ones((2, 3), dtype=torch.bool),
        "target_tokens": torch.randn((2, 2, 3, 3), generator=generator),
        "target_mask": torch.ones((2, 2, 3), dtype=torch.bool),
        "example_ids": [f"{prefix}-0", f"{prefix}-1"],
    }


@pytest.mark.parametrize("positions", [(0, 1, 2), (2, 3, 4), (0, 2, 4)])
def test_masked_encoder_matches_packed_values_and_gradients(positions: tuple[int, ...]) -> None:
    model = _model().double()
    packed = torch.randn((1, 3, 3), dtype=torch.float64, requires_grad=True)
    padded = torch.randn((1, 5, 3), dtype=torch.float64)
    padded[:, positions] = packed.detach()
    padded.requires_grad_(True)
    mask = torch.zeros((1, 5), dtype=torch.bool)
    mask[:, positions] = True
    expected = model(packed, torch.ones((1, 3), dtype=torch.bool))
    actual = model(padded, mask)
    torch.testing.assert_close(actual["summary"], expected["summary"], rtol=1e-12, atol=1e-12)
    torch.testing.assert_close(
        actual["base_forecast"], expected["base_forecast"], rtol=1e-12, atol=1e-12
    )
    probe = torch.arange(16, dtype=torch.float64).reshape(1, 2, 2, 4)
    parameters = tuple(model.context_encoder.parameters())
    expected_gradients = torch.autograd.grad(
        (expected["base_forecast"] * probe).sum(), (packed, *parameters)
    )
    actual_gradients = torch.autograd.grad(
        (actual["base_forecast"] * probe).sum(), (padded, *parameters)
    )
    assert all(torch.isfinite(gradient).all() for gradient in actual_gradients)
    torch.testing.assert_close(
        actual_gradients[0][:, positions], expected_gradients[0], rtol=1e-11, atol=1e-11
    )
    assert torch.count_nonzero(actual_gradients[0][~mask]) == 0
    for actual_gradient, expected_gradient in zip(
        actual_gradients[1:], expected_gradients[1:], strict=True
    ):
        torch.testing.assert_close(actual_gradient, expected_gradient, rtol=1e-11, atol=1e-11)


@pytest.mark.parametrize("padding", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("target", [False, True])
def test_masked_nonfinite_padding_is_ignored(padding: float, target: bool) -> None:
    model = _model()
    packed = torch.randn((1, 2, 3))
    padded = torch.full((1, 5, 3), padding)
    padded[:, (1, 4)] = packed
    mask = torch.tensor([[False, True, False, False, True]])
    if target:
        expected = model.encode_targets(
            packed[:, None].repeat(1, 2, 1, 1), torch.ones((1, 2, 2), dtype=torch.bool)
        )
        actual = model.encode_targets(
            padded[:, None].repeat(1, 2, 1, 1), mask[:, None].repeat(1, 2, 1)
        )
    else:
        expected = model(packed, torch.ones((1, 2), dtype=torch.bool))["base_forecast"]
        actual = model(padded, mask)["base_forecast"]
    assert torch.isfinite(actual).all()
    torch.testing.assert_close(actual, expected, rtol=1e-5, atol=1e-6)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("target", [False, True])
def test_nonfinite_observed_token_is_rejected(value: float, target: bool) -> None:
    model = _model()
    tokens = torch.zeros((1, 2, 3))
    tokens[0, 0, 0] = value
    with pytest.raises(ValueError, match="valid tokens must be finite"):
        if target:
            model.encode_targets(
                tokens[:, None].repeat(1, 2, 1, 1), torch.ones((1, 2, 2), dtype=torch.bool)
            )
        else:
            model(tokens, torch.ones((1, 2), dtype=torch.bool))


def test_gapped_encoder_remains_causal() -> None:
    model = _model()
    tokens = torch.randn((1, 5, 3))
    mask = torch.tensor([[True, False, True, False, True]])
    original = model(tokens, mask)["sequence"]
    tokens[:, 4] += 100.0
    changed = model(tokens, mask)["sequence"]
    torch.testing.assert_close(original[:, :4], changed[:, :4], rtol=0.0, atol=0.0)
    assert not torch.allclose(original[:, 4], changed[:, 4])


@pytest.mark.parametrize("cross_batch", [False, True])
def test_evaluation_rejects_duplicate_identities_before_model_execution(
    monkeypatch: pytest.MonkeyPatch, cross_batch: bool
) -> None:
    model = _model()
    first = _batch()
    batches = [first, _batch()] if cross_batch else [first]
    if not cross_batch:
        first["example_ids"] = ["duplicate", "duplicate"]
    calls: list[bool] = []
    monkeypatch.setattr(model, "forward", lambda *_: calls.append(True))
    with pytest.raises(ValueError, match="duplicate example_id"):
        evaluate_space_jepa_v2(model, batches)
    assert calls == []


@pytest.mark.parametrize("identifiers", ["ab", [None, "b"], [1, "b"], [True, "b"], [" ", "b"]])
def test_evaluation_rejects_ambiguous_identities(identifiers: Any) -> None:
    batch = _batch()
    batch["example_ids"] = identifiers
    with pytest.raises(ValueError, match="example_ids"):
        evaluate_space_jepa_v2(_model(), [batch])


def test_evaluation_checks_collision_with_generated_identity() -> None:
    first, second = _batch(), _batch("second")
    del first["example_ids"]
    second["example_ids"][0] = "batch-0-row-0"
    with pytest.raises(ValueError, match="duplicate example_id"):
        evaluate_space_jepa_v2(_model(), [first, second])


def test_evaluation_retains_valid_v1_identity_and_loss_contract() -> None:
    model = _model()
    first, second = _batch(), _batch("second")
    del second["example_ids"]
    report = evaluate_space_jepa_v2(model, [first, second])
    assert report["schema"] == "siderea.space_jepa_v2_evaluation.v1"
    assert report["row_count"] == 4
    assert [row["example_id"] for row in report["rows"]] == [
        "example-0",
        "example-1",
        "batch-1-row-0",
        "batch-1-row-1",
    ]
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("damage", ["duplicate-identities", "nonfinite-checkpoint"])
def test_inference_cli_rejects_corrupt_input_without_publishing(
    tmp_path: Path, damage: str
) -> None:
    model = _model()
    if damage == "nonfinite-checkpoint":
        with torch.no_grad():
            next(model.context_encoder.parameters()).fill_(float("nan"))
    checkpoint = tmp_path / "model.pt"
    save_space_jepa_v2_checkpoint(
        checkpoint,
        model,
        training_config=SpaceJEPA2TrainingConfig(epochs=1, seed=17),
        training_result={"scope": "constructed untrained checkpoint for CLI contract"},
        protocol_digest="a" * 64,
        data_digest="b" * 64,
    )
    batches = tmp_path / "batches.pt"
    batch = _batch()
    if damage == "duplicate-identities":
        batch["example_ids"] = ["duplicate", "duplicate"]
    torch.save([batch], batches)
    output = tmp_path / "rejected.json"
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    assert main(["space-jepa-2-infer", str(checkpoint), str(batches), str(output)]) == 2
    assert not output.exists()
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before
