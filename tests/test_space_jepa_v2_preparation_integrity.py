"""Development fixtures for causal preprocessing and source identity."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

from siderea.ml.prequential import PhotometricObservation, build_prequential_examples
from siderea.ml.space_jepa_v2_data import (
    _token,
    chronological_entity_split,
    prepare_space_jepa_v2_batches,
    training_band_vocabulary,
)


def _observation(entity: str, index: int, *, band: str = "g") -> PhotometricObservation:
    return PhotometricObservation(
        entity_id=entity,
        observation_id=f"{entity}-{index}",
        observed_at_mjd=60_000.0 + index,
        available_at_mjd=60_000.0 + index,
        band=band,
        value=float(index),
        value_error=0.1,
        is_detection=True,
    )


def test_simultaneous_bands_produce_unique_cutoff_horizon_examples() -> None:
    rows = [
        replace(_observation("e0", epoch, band=band), observation_id=f"{epoch}-{band}")
        for epoch in range(4)
        for band in ("g", "r")
    ]
    examples = build_prequential_examples(rows, horizons_days=(1.0, 2.0))
    assert len(examples) == 6
    assert len({example.example_id for example in examples}) == 6
    assert [item.example_id for item in examples] == [
        item.example_id
        for item in build_prequential_examples(reversed(rows), horizons_days=(1.0, 2.0))
    ]


def test_vocabulary_is_invariant_to_held_out_band_names() -> None:
    training = [_observation("train", 0, band="g"), _observation("train", 1, band="r")]
    first = training + [_observation("test", 2, band="u")]
    second = training + [_observation("test", 2, band="z")]
    assert training_band_vocabulary(first, ("train",)) == {"unknown": 0, "g": 1, "r": 2}
    assert training_band_vocabulary(first, ("train",)) == training_band_vocabulary(
        second, ("train",)
    )


def test_unseen_band_uses_preallocated_unknown_coordinate() -> None:
    token = _token(
        _observation("test", 2, band="u"),
        first_mjd=60_000.0,
        previous_mjd=60_001.0,
        center=0.0,
        scale=1.0,
        band_to_id={"unknown": 0, "g": 1, "r": 2},
    )
    assert token[-1] == 0.0


@pytest.mark.parametrize("fractions", [(0.99, 0.005, 0.005), (0.001, 0.998, 0.001)])
def test_three_entity_split_is_nonempty_at_extreme_valid_fractions(fractions) -> None:
    rows = [_observation(f"e{index}", index) for index in range(3)]
    splits = chronological_entity_split(
        rows,
        train_fraction=fractions[0],
        validation_fraction=fractions[1],
        test_fraction=fractions[2],
    )
    assert [len(entities) for entities in splits.values()] == [1, 1, 1]
    assert set().union(*map(set, splits.values())) == {"e0", "e1", "e2"}


@pytest.mark.parametrize("value,scale", [(1e100, 1.0), (1.0, 1e-300), (1.0, 0.0)])
def test_nonrepresentable_token_is_rejected_before_float32_conversion(value, scale) -> None:
    with pytest.raises(ValueError, match="normaliz"):
        _token(
            replace(_observation("e0", 2), value=value),
            first_mjd=60_000.0,
            previous_mjd=60_001.0,
            center=0.0,
            scale=scale,
            band_to_id={"unknown": 0, "g": 1},
        )


def _frame(*, held_band: str = "u", simultaneous: bool = False) -> pd.DataFrame:
    rows = []
    for entity in range(6):
        for epoch in range(6):
            for band in ("g", "r") if simultaneous else ("g" if entity < 3 else held_band,):
                rows.append(
                    {
                        "entity_id": f"e{entity}",
                        "observation_id": f"e{entity}-{epoch}-{band}",
                        "observed_at_mjd": 60_000.0 + 100 * entity + epoch,
                        "available_at_mjd": 60_000.0 + 100 * entity + epoch,
                        "band": band,
                        "value": float(epoch),
                        "value_error": 0.1,
                        "is_detection": True,
                    }
                )
    return pd.DataFrame(rows)


def _prepare(source: Path, output: Path) -> dict:
    return prepare_space_jepa_v2_batches(
        source,
        output,
        horizons_days=(1.0, 3.0),
        train_fraction=0.5,
        validation_fraction=0.25,
        test_fraction=0.25,
        batch_size=4,
    )


def test_held_out_bands_cannot_change_any_training_tensor(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    loaded = []
    for band in ("u", "z"):
        source = tmp_path / f"{band}.csv"
        _frame(held_band=band).to_csv(source, index=False)
        output = tmp_path / band
        manifest = _prepare(source, output)
        assert manifest["schema"] == "siderea.space_jepa_v2_tensor_batches.v2"
        assert manifest["band_to_id"] == {"unknown": 0, "g": 1}
        assert manifest["splits"]["validation"]["unknown_band_observations"] == 6
        loaded.append(torch.load(output / "train.pt", weights_only=True))
    for left, right in zip(*loaded, strict=True):
        assert left["example_ids"] == right["example_ids"]
        for key in ("context_tokens", "context_mask", "target_tokens", "target_mask"):
            assert torch.equal(left[key], right[key])


def test_multiband_simultaneous_observations_prepare_end_to_end(tmp_path: Path) -> None:
    pytest.importorskip("torch")
    source = tmp_path / "simultaneous.csv"
    _frame(simultaneous=True).to_csv(source, index=False)
    manifest = _prepare(source, tmp_path / "prepared")
    assert all(split["batch_count"] > 0 for split in manifest["splits"].values())


def test_manifest_hash_binds_parsed_bytes_even_if_source_changes(
    tmp_path: Path, monkeypatch
) -> None:
    pytest.importorskip("torch")
    source = tmp_path / "source.csv"
    _frame().to_csv(source, index=False)
    original = source.read_bytes()
    read_csv = pd.read_csv

    def mutate_after_read(*args, **kwargs):
        frame = read_csv(*args, **kwargs)
        source.write_text("changed after parse\n")
        return frame

    monkeypatch.setattr(pd, "read_csv", mutate_after_read)
    manifest = _prepare(source, tmp_path / "prepared")
    assert manifest["input_sha256"] == sha256(original).hexdigest()
    assert manifest["input_sha256"] != sha256(source.read_bytes()).hexdigest()
