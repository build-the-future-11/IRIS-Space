from __future__ import annotations

from dataclasses import replace

import pytest

from siderea.ml.prequential import (
    PhotometricObservation,
    assert_entity_disjoint_splits,
    build_prequential_examples,
)


def _row(index: int, value: float, *, available: float | None = None) -> PhotometricObservation:
    time = 60000.0 + index
    return PhotometricObservation(
        entity_id="ZTF-A",
        observation_id=f"obs-{index}",
        observed_at_mjd=time,
        available_at_mjd=time if available is None else available,
        band="g" if index % 2 == 0 else "r",
        value=value,
        value_error=0.2,
        is_detection=True,
        survey="ZTF",
        calibration_id="cal-v1",
    )


def test_future_changes_do_not_change_prefix_contract() -> None:
    rows = [_row(index, float(index)) for index in range(5)]
    original = build_prequential_examples(rows, horizons_days=(1.0,), minimum_prefix=2)
    changed = list(rows)
    changed[-1] = replace(changed[-1], value=9999.0)
    modified = build_prequential_examples(changed, horizons_days=(1.0,), minimum_prefix=2)
    assert original[0].contract_digest == modified[0].contract_digest
    assert original[0].normalization == modified[0].normalization


def test_delayed_observation_is_not_in_prefix() -> None:
    rows = [_row(0, 1.0), _row(1, 2.0, available=60004.0), _row(2, 3.0), _row(3, 4.0)]
    examples = build_prequential_examples(rows, horizons_days=(1.0,), minimum_prefix=2)
    assert examples
    assert all("obs-1" not in {item.observation_id for item in ex.prefix} for ex in examples)


def test_non_detection_requires_limit() -> None:
    with pytest.raises(ValueError, match="limiting_value"):
        PhotometricObservation(
            entity_id="x",
            observation_id="y",
            observed_at_mjd=1.0,
            available_at_mjd=1.0,
            band="g",
            value=None,
            value_error=None,
            is_detection=False,
        )


def test_entity_overlap_is_rejected() -> None:
    with pytest.raises(ValueError, match="appears in both"):
        assert_entity_disjoint_splits({"train": ["a", "b"], "test": ["b"]})
