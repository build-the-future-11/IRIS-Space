from __future__ import annotations

from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from siderea.ml.space_jepa_v2 import AQPMJEPA, SpaceJEPA2Config  # noqa: E402
from siderea.ml.space_jepa_v2_evaluate import evaluate_space_jepa_v2  # noqa: E402
from siderea.ml.space_jepa_v2_train import (  # noqa: E402
    SpaceJEPA2TrainingConfig,
    load_space_jepa_v2_checkpoint,
    save_space_jepa_v2_checkpoint,
    train_space_jepa_v2,
)


def _model() -> AQPMJEPA:
    return AQPMJEPA(
        SpaceJEPA2Config(
            input_dim=5,
            quaternion_width=4,
            encoder_blocks=1,
            attention_heads=2,
            predictor_blocks=1,
            dropout=0.0,
            horizons_days=(1.0, 3.0),
            use_continuous_flow=False,
        )
    )


def _batch(seed: int) -> dict[str, object]:
    generator = torch.Generator().manual_seed(seed)
    return {
        "context_tokens": torch.randn((3, 4, 5), generator=generator),
        "context_mask": torch.ones((3, 4), dtype=torch.bool),
        "target_tokens": torch.randn((3, 2, 3, 5), generator=generator),
        "target_mask": torch.ones((3, 2, 3), dtype=torch.bool),
        "example_ids": [f"source-{seed}-{index}" for index in range(3)],
    }


def test_training_checkpoint_and_evaluation_round_trip(tmp_path: Path) -> None:
    torch.manual_seed(2)
    model = _model()
    config = SpaceJEPA2TrainingConfig(epochs=2, seed=17)
    result = train_space_jepa_v2(model, [_batch(1), _batch(2)], [_batch(3)], config)
    assert result["global_steps"] == 4
    checkpoint = tmp_path / "model.pt"
    save_space_jepa_v2_checkpoint(
        checkpoint,
        model,
        training_config=config,
        training_result=result,
        protocol_digest="a" * 64,
        data_digest="b" * 64,
    )
    loaded, metadata = load_space_jepa_v2_checkpoint(checkpoint)
    assert metadata["protocol_digest"] == "a" * 64
    evaluation = evaluate_space_jepa_v2(loaded, [_batch(4)])
    assert evaluation["row_count"] == 3
    assert len(str(evaluation["result_digest"])) == 64
