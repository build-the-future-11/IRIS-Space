from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

torch = pytest.importorskip("torch")

from siderea.ml.space_jepa_v2_data import prepare_space_jepa_v2_batches  # noqa: E402


def test_prepare_publishes_entity_disjoint_batches(tmp_path: Path) -> None:
    rows = []
    for entity_index in range(6):
        for epoch in range(8):
            rows.append(
                {
                    "entity_id": f"e{entity_index}",
                    "observation_id": f"e{entity_index}-o{epoch}",
                    "observed_at_mjd": 60000.0 + entity_index * 100.0 + epoch,
                    "available_at_mjd": 60000.0 + entity_index * 100.0 + epoch,
                    "band": "g" if epoch % 2 == 0 else "r",
                    "value": float(epoch),
                    "value_error": 0.1,
                    "is_detection": True,
                    "limiting_value": None,
                }
            )
    source = tmp_path / "photometry.csv"
    pd.DataFrame(rows).to_csv(source, index=False)
    output = tmp_path / "prepared"
    manifest = prepare_space_jepa_v2_batches(
        source,
        output,
        horizons_days=(1.0, 3.0),
        train_fraction=0.5,
        validation_fraction=0.25,
        test_fraction=0.25,
        batch_size=4,
    )
    assert manifest["input_dim"] == 7
    owners = [set(manifest["splits"][name]["entities"]) for name in ("train", "validation", "test")]
    assert not owners[0] & owners[1]
    assert not owners[0] & owners[2]
    assert not owners[1] & owners[2]
    batches = torch.load(output / "train.pt", weights_only=True)
    assert batches[0]["target_tokens"].shape[1] == 2


def test_prepare_leaves_no_partial_directory_when_a_split_is_unusable(tmp_path: Path) -> None:
    rows = []
    for entity_index, epochs in enumerate((5, 5, 2)):
        for epoch in range(epochs):
            rows.append(
                {
                    "entity_id": f"e{entity_index}",
                    "observation_id": f"e{entity_index}-o{epoch}",
                    "observed_at_mjd": 60_000.0 + entity_index * 100.0 + epoch,
                    "available_at_mjd": 60_000.0 + entity_index * 100.0 + epoch,
                    "band": "g",
                    "value": float(epoch),
                    "value_error": 0.1,
                    "is_detection": True,
                }
            )
    source = tmp_path / "photometry.csv"
    pd.DataFrame(rows).to_csv(source, index=False)
    output = tmp_path / "prepared"
    with pytest.raises(ValueError, match="has no complete multi-horizon examples"):
        prepare_space_jepa_v2_batches(
            source,
            output,
            horizons_days=(1.0, 3.0),
            train_fraction=1 / 3,
            validation_fraction=1 / 3,
            test_fraction=1 / 3,
            batch_size=2,
        )
    assert not output.exists()
    assert not list(tmp_path.glob(".prepared.*"))
