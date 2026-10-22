"""Deterministic tensor preparation for Space JEPA 2."""

from __future__ import annotations

import io
import math
import os
import shutil
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pandas as pd

from siderea.atomic import atomic_create_binary, atomic_write_text
from siderea.ingest.tns_data import normalize_tns_photometry
from siderea.provenance import digest_file, digest_value, stable_json

from .prequential import (
    PhotometricObservation,
    PrequentialExample,
    build_prequential_examples,
)
from .quaternion import require_quaternion_torch

try:
    import torch
except ImportError as exc:  # pragma: no cover
    torch = None  # type: ignore[assignment]
    _TORCH_IMPORT_ERROR: ImportError | None = exc
else:
    _TORCH_IMPORT_ERROR = None

SPACE_JEPA_V2_TENSOR_SCHEMA = "siderea.space_jepa_v2_tensor_batches.v2"
SPACE_JEPA_V2_INPUT_DIM = 7


def _observations(frame: pd.DataFrame) -> tuple[list[PhotometricObservation], pd.DataFrame]:
    accepted, rejected = normalize_tns_photometry(frame)
    observations = []
    for raw_row in accepted.itertuples(index=False):
        row = cast(Any, raw_row)
        observations.append(
            PhotometricObservation(
                entity_id=str(row.entity_id),
                observation_id=str(row.observation_id),
                observed_at_mjd=float(row.observed_at_mjd),
                available_at_mjd=float(row.available_at_mjd),
                band=str(row.band),
                value=None if pd.isna(row.value) else float(row.value),
                value_error=None if pd.isna(row.value_error) else float(row.value_error),
                is_detection=bool(row.is_detection),
                limiting_value=(None if pd.isna(row.limiting_value) else float(row.limiting_value)),
                survey="TNS_or_supplied_survey",
                calibration_id="input_declared",
            )
        )
    return observations, rejected


def chronological_entity_split(
    observations: Sequence[PhotometricObservation],
    *,
    train_fraction: float,
    validation_fraction: float,
    test_fraction: float,
) -> dict[str, tuple[str, ...]]:
    fractions = (train_fraction, validation_fraction, test_fraction)
    if any(not math.isfinite(value) or value <= 0.0 for value in fractions):
        raise ValueError("split fractions must be positive and finite")
    if not math.isclose(sum(fractions), 1.0, abs_tol=1e-12):
        raise ValueError("split fractions must sum to one")
    first_available: dict[str, float] = {}
    for observation in observations:
        first_available[observation.entity_id] = min(
            observation.available_at_mjd,
            first_available.get(observation.entity_id, math.inf),
        )
    ordered = sorted(first_available, key=lambda entity: (first_available[entity], entity))
    if len(ordered) < 3:
        raise ValueError("entity-disjoint train/validation/test split requires at least 3 entities")
    train_end = min(len(ordered) - 2, max(1, int(math.floor(len(ordered) * train_fraction))))
    validation_end = max(
        train_end + 1, int(math.floor(len(ordered) * (train_fraction + validation_fraction)))
    )
    validation_end = min(validation_end, len(ordered) - 1)
    return {
        "train": tuple(ordered[:train_end]),
        "validation": tuple(ordered[train_end:validation_end]),
        "test": tuple(ordered[validation_end:]),
    }


def training_band_vocabulary(
    observations: Sequence[PhotometricObservation], training_entities: Sequence[str]
) -> dict[str, int]:
    """Fit a stable vocabulary using training entities alone.

    Index zero is reserved before inspecting any held-out band. Adding or
    renaming a validation/test band therefore cannot change training tokens.
    """
    entities = frozenset(training_entities)
    bands = sorted(
        {
            item.band
            for item in observations
            if item.entity_id in entities and item.band != "unknown"
        }
    )
    return {"unknown": 0, **{band: index + 1 for index, band in enumerate(bands)}}


def _token(
    observation: PhotometricObservation,
    *,
    first_mjd: float,
    previous_mjd: float,
    center: float,
    scale: float,
    band_to_id: Mapping[str, int],
) -> list[float]:
    raw_value = observation.value if observation.is_detection else observation.limiting_value
    assert raw_value is not None
    if not math.isfinite(center) or not math.isfinite(scale) or scale <= 0:
        raise ValueError("prefix normalization must be finite with a positive scale")
    normalized_value = (raw_value - center) / scale
    normalized_error = (
        observation.value_error / scale if observation.value_error is not None else 0.0
    )
    delta = max(0.0, observation.observed_at_mjd - previous_mjd)
    elapsed = max(0.0, observation.observed_at_mjd - first_mjd)
    band_scale = max(len(band_to_id) - 1, 1)
    band_id = band_to_id.get(observation.band, band_to_id.get("unknown"))
    if band_id is None:
        raise ValueError(f"passband {observation.band!r} has no configured ID or unknown bucket")
    token = [
        normalized_value,
        normalized_error,
        math.log1p(delta),
        math.log1p(elapsed),
        float(observation.is_detection),
        float(not observation.is_detection),
        band_id / band_scale,
    ]
    float32_max = float.fromhex("0x1.fffffep+127")
    if any(not math.isfinite(value) or abs(value) > float32_max for value in token):
        raise ValueError("normalized Space JEPA 2 token exceeds the finite float32 range")
    return token


def _tokens(
    rows: Sequence[PhotometricObservation],
    example: PrequentialExample,
    band_to_id: Mapping[str, int],
) -> list[list[float]]:
    ordered = sorted(rows, key=lambda item: (item.observed_at_mjd, item.observation_id))
    result = []
    first_mjd = min(item.observed_at_mjd for item in example.prefix)
    previous = first_mjd if ordered[0].observed_at_mjd <= example.cutoff_mjd else example.cutoff_mjd
    for row in ordered:
        result.append(
            _token(
                row,
                first_mjd=first_mjd,
                previous_mjd=previous,
                center=example.normalization.center,
                scale=example.normalization.scale,
                band_to_id=band_to_id,
            )
        )
        previous = row.observed_at_mjd
    return result


def examples_to_batches(
    examples: Sequence[PrequentialExample],
    *,
    horizons_days: Sequence[float],
    batch_size: int,
    band_to_id: Mapping[str, int],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    require_quaternion_torch()
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    horizons = tuple(float(value) for value in horizons_days)
    if not horizons or any(not math.isfinite(value) or value <= 0 for value in horizons):
        raise ValueError("horizons_days must contain positive finite values")
    if len(set(horizons)) != len(horizons):
        raise ValueError("horizons_days must not contain duplicates")
    horizon_set = frozenset(horizons)
    by_cutoff: dict[tuple[str, float], dict[float, PrequentialExample]] = defaultdict(dict)
    for example in examples:
        key = (example.entity_id, example.cutoff_mjd)
        if example.horizon_days in by_cutoff[key]:
            raise ValueError("duplicate entity/cutoff/horizon example")
        by_cutoff[key][example.horizon_days] = example
    complete = [
        (key, grouped)
        for key, grouped in sorted(by_cutoff.items())
        if grouped.keys() == horizon_set
    ]
    dropped = len(by_cutoff) - len(complete)
    batches: list[dict[str, Any]] = []
    for start in range(0, len(complete), batch_size):
        chunk = complete[start : start + batch_size]
        contexts: list[list[list[float]]] = []
        targets: list[list[list[list[float]]]] = []
        identifiers: list[str] = []
        for (_, _), grouped in chunk:
            representative = grouped[horizons[0]]
            contexts.append(_tokens(representative.prefix, representative, band_to_id))
            targets.append(
                [
                    _tokens(grouped[horizon].target, grouped[horizon], band_to_id)
                    for horizon in horizons
                ]
            )
            identifiers.append(representative.example_id)
        max_context = max(len(rows) for rows in contexts)
        max_target = max(len(rows) for item in targets for rows in item)
        context_tensor = torch.zeros((len(chunk), max_context, SPACE_JEPA_V2_INPUT_DIM))
        context_mask = torch.zeros((len(chunk), max_context), dtype=torch.bool)
        target_tensor = torch.zeros(
            (len(chunk), len(horizons), max_target, SPACE_JEPA_V2_INPUT_DIM)
        )
        target_mask = torch.zeros((len(chunk), len(horizons), max_target), dtype=torch.bool)
        for row_index, rows in enumerate(contexts):
            context_tensor[row_index, : len(rows)] = torch.tensor(rows)
            context_mask[row_index, : len(rows)] = True
        for row_index, horizon_rows in enumerate(targets):
            for horizon_index, rows in enumerate(horizon_rows):
                target_tensor[row_index, horizon_index, : len(rows)] = torch.tensor(rows)
                target_mask[row_index, horizon_index, : len(rows)] = True
        batches.append(
            {
                "context_tokens": context_tensor,
                "context_mask": context_mask,
                "target_tokens": target_tensor,
                "target_mask": target_mask,
                "example_ids": identifiers,
            }
        )
    return batches, {
        "cutoffs_seen": len(by_cutoff),
        "complete_cutoffs": len(complete),
        "incomplete_cutoffs_dropped": dropped,
    }


def prepare_space_jepa_v2_batches(
    input_csv: str | Path,
    output_directory: str | Path,
    *,
    horizons_days: Sequence[float],
    train_fraction: float,
    validation_fraction: float,
    test_fraction: float,
    batch_size: int = 32,
) -> dict[str, Any]:
    """Normalize strict photometry and publish entity-disjoint tensor batches."""

    require_quaternion_torch()
    source = Path(input_csv).expanduser().resolve()
    output = Path(output_directory).expanduser().resolve()
    if output.exists():
        raise FileExistsError("Space JEPA 2 prepared-data output already exists")
    # Parse and hash the same snapshot. Reopening the pathname after tensor
    # construction could bind a changed source to batches made from old bytes.
    source_bytes = source.read_bytes()
    frame = pd.read_csv(io.BytesIO(source_bytes))
    observations, rejected = _observations(frame)
    splits = chronological_entity_split(
        observations,
        train_fraction=train_fraction,
        validation_fraction=validation_fraction,
        test_fraction=test_fraction,
    )
    band_to_id = training_band_vocabulary(observations, splits["train"])
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        split_receipts: dict[str, Any] = {}
        for split_name, entities in splits.items():
            entity_set = frozenset(entities)
            selected = [item for item in observations if item.entity_id in entity_set]
            examples = build_prequential_examples(
                selected, horizons_days=horizons_days, minimum_prefix=2
            )
            batches, receipt = examples_to_batches(
                examples,
                horizons_days=horizons_days,
                batch_size=batch_size,
                band_to_id=band_to_id,
            )
            if not batches:
                raise ValueError(f"split {split_name!r} has no complete multi-horizon examples")
            destination = staging / f"{split_name}.pt"

            def _write(handle: Any, values: list[dict[str, Any]] = batches) -> None:
                torch.save(values, handle)

            atomic_create_binary(destination, _write)
            split_receipts[split_name] = {
                **receipt,
                "entities": list(entities),
                "batch_count": len(batches),
                "unknown_band_observations": sum(
                    item.band not in band_to_id or item.band == "unknown" for item in selected
                ),
                "sha256": digest_file(destination),
            }
        rejected.to_csv(staging / "rejected-rows.csv", index=False)
        identity = {
            "schema": SPACE_JEPA_V2_TENSOR_SCHEMA,
            "input_sha256": sha256(source_bytes).hexdigest(),
            "input_dim": SPACE_JEPA_V2_INPUT_DIM,
            "horizons_days": list(horizons_days),
            "band_to_id": band_to_id,
            "band_vocabulary_policy": "training_entities_only; unknown_id=0",
            "split_policy": "first_available_time_then_entity_id; nonempty_entity_partitions",
            "requested_split_fractions": {
                "train": train_fraction,
                "validation": validation_fraction,
                "test": test_fraction,
            },
            "accepted_observations": len(observations),
            "rejected_rows": len(rejected),
            "splits": split_receipts,
        }
        manifest = {**identity, "result_digest": digest_value(identity)}
        atomic_write_text(staging / "manifest.json", stable_json(manifest) + "\n")
        os.rename(staging, output)
        return manifest
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


__all__ = [
    "SPACE_JEPA_V2_INPUT_DIM",
    "SPACE_JEPA_V2_TENSOR_SCHEMA",
    "chronological_entity_split",
    "examples_to_batches",
    "prepare_space_jepa_v2_batches",
    "training_band_vocabulary",
]
