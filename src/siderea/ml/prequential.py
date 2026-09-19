"""Causal prefix/target construction for Space JEPA 2."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from siderea.provenance import stable_json

PREQUENTIAL_CONTRACT_VERSION = "siderea.space_jepa_v2_prequential.v1"


@dataclass(frozen=True)
class PhotometricObservation:
    entity_id: str
    observation_id: str
    observed_at_mjd: float
    available_at_mjd: float
    band: str
    value: float | None
    value_error: float | None
    is_detection: bool
    limiting_value: float | None = None
    survey: str = "unknown"
    calibration_id: str = "unknown"

    def __post_init__(self) -> None:
        for name in ("entity_id", "observation_id", "band", "survey", "calibration_id"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")
        for name in ("observed_at_mjd", "available_at_mjd"):
            if not math.isfinite(float(getattr(self, name))):
                raise ValueError(f"{name} must be finite")
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("value must be finite when present")
        if self.value_error is not None and (
            not math.isfinite(self.value_error) or self.value_error <= 0.0
        ):
            raise ValueError("value_error must be positive and finite when present")
        if self.limiting_value is not None and not math.isfinite(self.limiting_value):
            raise ValueError("limiting_value must be finite when present")
        if self.is_detection and (self.value is None or self.value_error is None):
            raise ValueError("detections require value and value_error")
        if not self.is_detection and self.limiting_value is None:
            raise ValueError("non-detections require limiting_value")


@dataclass(frozen=True)
class Normalization:
    center: float
    scale: float


@dataclass(frozen=True)
class PrequentialExample:
    example_id: str
    entity_id: str
    cutoff_mjd: float
    horizon_days: float
    prefix: tuple[PhotometricObservation, ...]
    target: tuple[PhotometricObservation, ...]
    normalization: Normalization
    contract_digest: str


def observation_from_mapping(row: Mapping[str, Any]) -> PhotometricObservation:
    """Parse the strict Space JEPA 2 row contract."""

    return PhotometricObservation(
        entity_id=str(row["entity_id"]).strip(),
        observation_id=str(row["observation_id"]).strip(),
        observed_at_mjd=float(row["observed_at_mjd"]),
        available_at_mjd=float(row["available_at_mjd"]),
        band=str(row["band"]).strip(),
        value=None if row.get("value") is None else float(row["value"]),
        value_error=None if row.get("value_error") is None else float(row["value_error"]),
        is_detection=bool(row["is_detection"]),
        limiting_value=(
            None if row.get("limiting_value") is None else float(row["limiting_value"])
        ),
        survey=str(row.get("survey", "unknown")).strip(),
        calibration_id=str(row.get("calibration_id", "unknown")).strip(),
    )


def prefix_normalization(
    observations: Sequence[PhotometricObservation], *, minimum_scale: float = 1e-6
) -> Normalization:
    """Fit robust normalization using detected prefix measurements only."""

    if not math.isfinite(minimum_scale) or minimum_scale <= 0.0:
        raise ValueError("minimum_scale must be positive and finite")
    values = sorted(
        float(item.value) for item in observations if item.is_detection and item.value is not None
    )
    errors = sorted(
        float(item.value_error)
        for item in observations
        if item.is_detection and item.value_error is not None
    )
    if not values:
        return Normalization(0.0, minimum_scale)

    def _median(items: Sequence[float]) -> float:
        middle = len(items) // 2
        return items[middle] if len(items) % 2 else 0.5 * (items[middle - 1] + items[middle])

    center = _median(values)
    deviations = sorted(abs(value - center) for value in values)
    mad_scale = 1.4826 * _median(deviations)
    error_scale = _median(errors) if errors else minimum_scale
    return Normalization(center, max(mad_scale, error_scale, minimum_scale))


def _contract_digest(
    entity_id: str,
    cutoff_mjd: float,
    horizon_days: float,
    prefix: Sequence[PhotometricObservation],
) -> str:
    identity = {
        "schema": PREQUENTIAL_CONTRACT_VERSION,
        "entity_id": entity_id,
        "cutoff_mjd": cutoff_mjd,
        "horizon_days": horizon_days,
        "prefix": [
            {
                "observation_id": item.observation_id,
                "observed_at_mjd": item.observed_at_mjd,
                "available_at_mjd": item.available_at_mjd,
                "band": item.band,
                "value": item.value,
                "value_error": item.value_error,
                "is_detection": item.is_detection,
                "limiting_value": item.limiting_value,
                "survey": item.survey,
                "calibration_id": item.calibration_id,
            }
            for item in prefix
        ],
    }
    return sha256(stable_json(identity).encode("utf-8")).hexdigest()


def build_prequential_examples(
    observations: Iterable[PhotometricObservation],
    *,
    horizons_days: Sequence[float] = (1.0, 3.0, 7.0, 14.0),
    minimum_prefix: int = 2,
) -> list[PrequentialExample]:
    """Create forward-only examples without reading post-cutoff availability."""

    if isinstance(minimum_prefix, bool) or minimum_prefix < 1:
        raise ValueError("minimum_prefix must be a positive integer")
    horizons = tuple(float(value) for value in horizons_days)
    if not horizons or any(not math.isfinite(value) or value <= 0.0 for value in horizons):
        raise ValueError("horizons_days must contain positive finite values")
    if len(set(horizons)) != len(horizons):
        raise ValueError("horizons_days must not contain duplicates")

    grouped: dict[str, list[PhotometricObservation]] = defaultdict(list)
    observation_ids: set[tuple[str, str]] = set()
    for item in observations:
        key = (item.entity_id, item.observation_id)
        if key in observation_ids:
            raise ValueError(f"duplicate observation identity {key!r}")
        observation_ids.add(key)
        grouped[item.entity_id].append(item)

    examples: list[PrequentialExample] = []
    for entity_id, rows in sorted(grouped.items()):
        ordered = sorted(rows, key=lambda item: (item.observed_at_mjd, item.observation_id))
        for cutoff_index in range(minimum_prefix - 1, len(ordered) - 1):
            cutoff = ordered[cutoff_index].observed_at_mjd
            prefix = tuple(
                item
                for item in ordered
                if item.observed_at_mjd <= cutoff and item.available_at_mjd <= cutoff
            )
            if len(prefix) < minimum_prefix:
                continue
            normalization = prefix_normalization(prefix)
            for horizon in horizons:
                target = tuple(
                    item for item in ordered if cutoff < item.observed_at_mjd <= cutoff + horizon
                )
                if not target:
                    continue
                digest = _contract_digest(entity_id, cutoff, horizon, prefix)
                example_id = sha256(
                    f"{entity_id}|{cutoff:.12g}|{horizon:.12g}|{digest}".encode()
                ).hexdigest()
                examples.append(
                    PrequentialExample(
                        example_id=example_id,
                        entity_id=entity_id,
                        cutoff_mjd=cutoff,
                        horizon_days=horizon,
                        prefix=prefix,
                        target=target,
                        normalization=normalization,
                        contract_digest=digest,
                    )
                )
    return examples


def assert_entity_disjoint_splits(splits: Mapping[str, Iterable[str]]) -> None:
    """Reject physical entities appearing in more than one named split."""

    owner: dict[str, str] = {}
    for split_name, entities in splits.items():
        name = str(split_name).strip()
        if not name:
            raise ValueError("split names must not be empty")
        for raw_entity in entities:
            entity = str(raw_entity).strip()
            if not entity:
                raise ValueError(f"split {name!r} contains an empty entity")
            previous = owner.get(entity)
            if previous is not None and previous != name:
                raise ValueError(
                    f"physical entity {entity!r} appears in both {previous!r} and {name!r}"
                )
            owner[entity] = name


__all__ = [
    "PREQUENTIAL_CONTRACT_VERSION",
    "Normalization",
    "PhotometricObservation",
    "PrequentialExample",
    "assert_entity_disjoint_splits",
    "build_prequential_examples",
    "observation_from_mapping",
    "prefix_normalization",
]
