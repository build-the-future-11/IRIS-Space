"""Development-only physical-entity and source-population tensor preparation.

Run with ``python -m siderea.ml.space_jepa_population_v1 --help``. This is an
opt-in input producer, not the frozen campaign or an astronomy evaluation.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import platform
import stat
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from contextlib import suppress
from hashlib import sha256
from pathlib import Path
from typing import Any, BinaryIO

from siderea.atomic import atomic_create_binary
from siderea.provenance import digest_value, stable_json

from .prequential import PhotometricObservation, PrequentialExample, build_prequential_examples
from .quaternion import require_quaternion_torch
from .space_jepa_v2_data import (
    SPACE_JEPA_V2_INPUT_DIM,
    chronological_entity_split,
    examples_to_batches,
    training_band_vocabulary,
)

MEMBERSHIP_SCHEMA = "siderea.space_jepa_population_membership.v1"
PREPARATION_SCHEMA = "siderea.space_jepa_population_preparation.v1"
PARTITIONS = ("train", "validation", "test", "population_b")
MAX_TENSOR_VALUES = 2_000_000
_CSV_FIELDS = {
    "entity_id",
    "observation_id",
    "observed_at_mjd",
    "available_at_mjd",
    "survey",
    "band",
    "calibration_id",
    "value",
    "value_error",
    "is_detection",
    "limiting_value",
}


def _identifier(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f"{name} must be a nonempty exact string without surrounding whitespace")
    return value


def _keys(value: Any, expected: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{name} must contain exactly {sorted(expected)}")
    return value


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> Any:
    raise ValueError(f"nonfinite JSON constant {value}")


def _membership(raw: bytes) -> tuple[dict[str, Any], dict[str, str], dict[str, str]]:
    document = json.loads(
        raw.decode("utf-8"), object_pairs_hook=_json_object, parse_constant=_invalid_constant
    )
    document = _keys(
        document,
        {
            "schema",
            "purpose",
            "population_a",
            "population_b",
            "population_basis",
            "measurement",
            "entities",
        },
        "membership",
    )
    if document["schema"] != MEMBERSHIP_SCHEMA or document["purpose"] != "development":
        raise ValueError("membership requires the v1 schema and development purpose")
    population_a = _identifier(document["population_a"], "population_a")
    population_b = _identifier(document["population_b"], "population_b")
    if population_a == population_b:
        raise ValueError("population_a and population_b must differ")
    _identifier(document["population_basis"], "population_basis")
    measurement = _keys(document["measurement"], {"value_kind", "unit"}, "measurement")
    if measurement["value_kind"] not in ("flux", "magnitude"):
        raise ValueError("measurement value_kind must be flux or magnitude")
    _identifier(measurement["unit"], "measurement unit")
    entities = document["entities"]
    if not isinstance(entities, list) or not 4 <= len(entities) <= 128:
        raise ValueError("membership requires 4 through 128 physical entities")
    aliases: dict[str, str] = {}
    populations: dict[str, str] = {}
    for entry in entities:
        entry = _keys(entry, {"physical_entity_id", "population", "aliases"}, "entity")
        entity = _identifier(entry["physical_entity_id"], "physical_entity_id")
        population = _identifier(entry["population"], "population")
        if entity in populations:
            raise ValueError(f"duplicate physical entity {entity!r}")
        if population not in (population_a, population_b):
            raise ValueError(f"unknown population for {entity!r}")
        names = entry["aliases"]
        if not isinstance(names, list) or not 1 <= len(names) <= 128:
            raise ValueError("each entity requires 1 through 128 aliases")
        names = [_identifier(name, "alias") for name in names]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate alias declaration for {entity!r}")
        for name in [entity, *names]:
            if name in aliases and aliases[name] != entity:
                raise ValueError(f"physical alias {name!r} belongs to different entities")
            aliases[name] = entity
        populations[entity] = population
    if sum(p == population_a for p in populations.values()) < 3:
        raise ValueError("population A requires at least three physical entities")
    if population_b not in populations.values():
        raise ValueError("population B requires at least one physical entity")
    return document, aliases, populations


def _csv_number(value: str, name: str, *, optional: bool = False) -> float | None:
    if optional and value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _observations(
    raw: bytes, aliases: Mapping[str, str], populations: Mapping[str, str]
) -> tuple[list[PhotometricObservation], dict[tuple[str, str], dict[str, Any]]]:
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8"), newline=""), strict=True)
    fields = reader.fieldnames
    if fields is None or set(fields) != _CSV_FIELDS or len(fields) != len(_CSV_FIELDS):
        raise ValueError("photometry must have exactly the canonical CSV columns")
    observations: list[PhotometricObservation] = []
    provenance: dict[tuple[str, str], dict[str, Any]] = {}
    counts: dict[str, int] = defaultdict(int)
    for record_index, row in enumerate(reader, start=1):
        if record_index > 4096:
            raise ValueError("photometry exceeds 4096 rows")
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"CSV record {record_index} has missing or extra fields")
        alias = _identifier(row["entity_id"], "entity_id")
        if alias not in aliases:
            raise ValueError(f"undeclared photometry entity {alias!r}")
        entity = aliases[alias]
        observation_id = _identifier(row["observation_id"], "observation_id")
        key = (entity, observation_id)
        if key in provenance:
            raise ValueError(f"duplicate physical-entity observation {key!r}")
        survey = _identifier(row["survey"], "survey")
        band = _identifier(row["band"], "band")
        calibration = _identifier(row["calibration_id"], "calibration_id")
        if row["is_detection"] not in ("true", "false"):
            raise ValueError("is_detection must be literal true or false")
        observed = _csv_number(row["observed_at_mjd"], "observed_at_mjd")
        available = _csv_number(row["available_at_mjd"], "available_at_mjd")
        assert observed is not None and available is not None
        if available < observed:
            raise ValueError("availability cannot predate observation")
        channel = json.dumps([survey, band], ensure_ascii=False, separators=(",", ":"))
        item = PhotometricObservation(
            entity_id=entity,
            observation_id=observation_id,
            observed_at_mjd=observed,
            available_at_mjd=available,
            band=channel,
            value=_csv_number(row["value"], "value", optional=True),
            value_error=_csv_number(row["value_error"], "value_error", optional=True),
            is_detection=row["is_detection"] == "true",
            limiting_value=_csv_number(row["limiting_value"], "limiting_value", optional=True),
            survey=survey,
            calibration_id=calibration,
        )
        counts[entity] += 1
        if counts[entity] > 128:
            raise ValueError(f"physical entity {entity!r} exceeds 128 observations")
        observations.append(item)
        provenance[key] = {
            "csv_record": record_index,
            "input_alias": alias,
            "observation_id": observation_id,
            "observed_at_mjd": observed,
            "available_at_mjd": available,
            "survey": survey,
            "band": band,
            "calibration_id": calibration,
        }
    if set(counts) != set(populations):
        raise ValueError("declared physical entities and observed physical entities must match")
    return observations, provenance


def _bounded_snapshot(path: Path, maximum: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise ValueError(f"input must be a regular file of at most {maximum} bytes")
        raw = handle.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError(f"input exceeds {maximum} bytes")
    return raw


def _publish_bytes(path: Path, raw: bytes) -> None:
    atomic_create_binary(path, lambda handle: handle.write(raw))


def _publish_json(path: Path, value: Any) -> None:
    _publish_bytes(path, (stable_json(value) + "\n").encode("utf-8"))


def _source_hashes() -> dict[str, str]:
    ml_root = Path(__file__).parent
    files = {
        f"src/siderea/ml/{name}": ml_root / name
        for name in ("space_jepa_population_v1.py", "space_jepa_v2_data.py", "prequential.py")
    }
    files.update(
        {f"src/siderea/{name}": ml_root.parent / name for name in ("atomic.py", "provenance.py")}
    )
    return {name: sha256(path.read_bytes()).hexdigest() for name, path in files.items()}


def _checked_sources() -> dict[str, str]:
    if _source_hashes() != _IMPORTED_SOURCE_FILES:
        raise ValueError("source files changed since import; use a fresh interpreter and checkout")
    return dict(_IMPORTED_SOURCE_FILES)


def _complete_groups(
    examples: Sequence[PrequentialExample], horizons: tuple[float, ...]
) -> list[dict[float, PrequentialExample]]:
    groups: dict[tuple[str, float], dict[float, PrequentialExample]] = defaultdict(dict)
    for example in examples:
        key = (example.entity_id, example.cutoff_mjd)
        if example.horizon_days in groups[key]:
            raise ValueError("duplicate entity/cutoff/horizon example")
        groups[key][example.horizon_days] = example
    return [group for _, group in sorted(groups.items()) if group.keys() == set(horizons)]


def _padded_values(groups: Sequence[dict[float, PrequentialExample]], batch_size: int) -> int:
    result = 0
    for start in range(0, len(groups), batch_size):
        chunk = groups[start : start + batch_size]
        context_size = max(len(next(iter(group.values())).prefix) for group in chunk)
        target_size = max(len(item.target) for group in chunk for item in group.values())
        result += (
            len(chunk) * SPACE_JEPA_V2_INPUT_DIM * (context_size + len(chunk[0]) * target_size)
        )
    return result


def _tensor_digest(batches: Sequence[Mapping[str, Any]]) -> str:
    identity = []
    for batch in batches:
        tensors = {}
        for name in ("context_tokens", "context_mask", "target_tokens", "target_mask"):
            array = batch[name].detach().cpu().numpy()
            dtype = "uint8" if name.endswith("mask") else "<f4"
            tensors[name] = {
                "shape": list(array.shape),
                "dtype": dtype,
                "sha256": sha256(array.astype(dtype, copy=False).tobytes(order="C")).hexdigest(),
            }
        identity.append({"tensors": tensors, "example_ids": batch["example_ids"]})
    return digest_value(identity)


def prepare_population_batches(
    photometry_csv: str | Path,
    membership_json: str | Path,
    output_directory: str | Path,
    *,
    horizons_days: Sequence[float],
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
    test_fraction: float = 0.2,
    batch_size: int = 32,
) -> dict[str, Any]:
    """Publish four generated/development partitions; retain all failed attempts.

    Population metadata and exhaustive physical aliases must be supplied by the
    caller. Their hashes establish byte identity, not verified astrophysical truth.
    """
    output = Path(output_directory).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=False)
    stage = "input_snapshot"
    try:
        source_files = _checked_sources()
        photometry = _bounded_snapshot(Path(photometry_csv).expanduser(), 8 * 1024 * 1024)
        _publish_bytes(output / "photometry-input.csv", photometry)
        membership = _bounded_snapshot(Path(membership_json).expanduser(), 2 * 1024 * 1024)
        _publish_bytes(output / "membership-input.json", membership)
        stage = "input_validation"
        document, aliases, populations = _membership(membership)
        observations, provenance = _observations(photometry, aliases, populations)
        values = (*horizons_days, train_fraction, validation_fraction, test_fraction)
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
            for value in values
        ):
            raise ValueError("horizons and fractions must be positive finite real numbers")
        horizons = tuple(float(value) for value in horizons_days)
        if not 1 <= len(horizons) <= 8 or tuple(sorted(set(horizons))) != horizons:
            raise ValueError("require one through eight strictly increasing horizons")
        if not math.isclose(
            train_fraction + validation_fraction + test_fraction, 1.0, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError("split fractions must sum to one")
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or not 1 <= batch_size <= 64
        ):
            raise ValueError("batch_size must be an integer from 1 through 64")
        require_quaternion_torch()
        import torch

        if torch.get_default_device().type != "cpu" or torch.get_default_dtype() != torch.float32:
            raise ValueError("population preparation requires CPU default device and float32 dtype")
        population_a = document["population_a"]
        a_observations = [
            item for item in observations if populations[item.entity_id] == population_a
        ]
        splits = chronological_entity_split(
            a_observations,
            train_fraction=train_fraction,
            validation_fraction=validation_fraction,
            test_fraction=test_fraction,
        )
        splits["population_b"] = tuple(
            sorted(
                entity for entity, population in populations.items() if population != population_a
            )
        )
        band_to_id = training_band_vocabulary(a_observations, splits["train"])
        stage = "tensor_preparation"
        split_receipts: dict[str, Any] = {}
        row_receipts: list[dict[str, Any]] = []
        total_values = 0
        for split_name, entities in splits.items():
            entity_set = frozenset(entities)
            selected = [item for item in observations if item.entity_id in entity_set]
            examples = build_prequential_examples(
                selected, horizons_days=horizons, minimum_prefix=2
            )
            groups = _complete_groups(examples, horizons)
            total_values += _padded_values(groups, batch_size)
            if total_values > MAX_TENSOR_VALUES:
                raise ValueError("prepared tensors exceed two million padded floating-point values")
            batches, counts = examples_to_batches(
                examples,
                horizons_days=horizons,
                batch_size=batch_size,
                band_to_id=band_to_id,
            )
            if not batches:
                raise ValueError(f"partition {split_name!r} has no complete multi-horizon rows")
            expected_ids = [group[horizons[0]].example_id for group in groups]
            if [item for batch in batches for item in batch["example_ids"]] != expected_ids:
                raise RuntimeError("prepared tensor identities disagree with row provenance")
            active_entities: set[str] = set()
            for group in groups:
                representative = group[horizons[0]]
                entity = representative.entity_id
                active_entities.add(entity)
                targets = []
                for horizon in horizons:
                    example = group[horizon]
                    targets.append(
                        {
                            "horizon_days": horizon,
                            "prefix_contract_digest": example.contract_digest,
                            "latest_target_available_at_mjd": max(
                                item.available_at_mjd for item in example.target
                            ),
                            "observations": [
                                provenance[(entity, item.observation_id)] for item in example.target
                            ],
                        }
                    )
                row_receipts.append(
                    {
                        "partition": split_name,
                        "population": populations[entity],
                        "physical_entity_id": entity,
                        "example_id": representative.example_id,
                        "cutoff_mjd": representative.cutoff_mjd,
                        "normalization": {
                            "center": representative.normalization.center,
                            "scale": representative.normalization.scale,
                        },
                        "prefix": [
                            provenance[(entity, item.observation_id)]
                            for item in representative.prefix
                        ],
                        "targets": targets,
                    }
                )
            destination = output / f"{split_name}.pt"

            def save_batches(handle: BinaryIO, data: list[dict[str, Any]] = batches) -> None:
                torch.save(data, handle)

            atomic_create_binary(destination, save_batches)
            split_receipts[split_name] = {
                **counts,
                "physical_entities": list(entities),
                "entities_with_complete_rows": sorted(active_entities),
                "entities_without_complete_rows": sorted(entity_set - active_entities),
                "observation_count": len(selected),
                "row_count": len(expected_ids),
                "batch_count": len(batches),
                "tensor_content_digest": _tensor_digest(batches),
                "file_sha256": sha256(destination.read_bytes()).hexdigest(),
                "unknown_channel_observations": sum(
                    item.band not in band_to_id for item in selected
                ),
                "observed_at_mjd_bounds": [
                    min(item.observed_at_mjd for item in selected),
                    max(item.observed_at_mjd for item in selected),
                ],
                "available_at_mjd_bounds": [
                    min(item.available_at_mjd for item in selected),
                    max(item.available_at_mjd for item in selected),
                ],
            }
        stage = "manifest_publication"
        rows_raw = "".join(
            json.dumps(row, sort_keys=True, allow_nan=False) + "\n" for row in row_receipts
        ).encode("utf-8")
        _publish_bytes(output / "rows.jsonl", rows_raw)
        _checked_sources()
        identity = {
            "schema": PREPARATION_SCHEMA,
            "status": "COMPLETE",
            "purpose": "development",
            "scientific_execution_authorized": False,
            "reporting_authorized": False,
            "input_sha256": sha256(photometry).hexdigest(),
            "membership_sha256": sha256(membership).hexdigest(),
            "rows_sha256": sha256(rows_raw).hexdigest(),
            "population_a": population_a,
            "population_b": document["population_b"],
            "population_basis": document["population_basis"],
            "measurement_declaration": document["measurement"],
            "membership_provenance_status": "caller_declared_unverified",
            "input_dim": SPACE_JEPA_V2_INPUT_DIM,
            "tensor_dtype": "float32",
            "device": "cpu",
            "horizons_days": list(horizons),
            "batch_size": batch_size,
            "band_to_id": band_to_id,
            "vocabulary_policy": "A_training_entities_only; channel=[survey,band]; unknown_id=0",
            "normalization_policy": "detected_context_prefix_only",
            "split_policy": "A_first_available_then_canonical_entity; B_excluded_from_A_split",
            "global_training_before_evaluation_established": False,
            "requested_A_fractions": {
                "train": train_fraction,
                "validation": validation_fraction,
                "test": test_fraction,
            },
            "accepted_observations": len(observations),
            "rejected_rows": 0,
            "padded_floating_point_values": total_values,
            "splits": split_receipts,
            "source_file_sha256": source_files,
            "environment": {"python": platform.python_version(), "torch": str(torch.__version__)},
        }
        manifest = {**identity, "result_digest": digest_value(identity)}
        _publish_json(output / "manifest.json", manifest)
        return manifest
    except BaseException as exc:
        # Preserve the original error if the filesystem cannot save its receipt.
        with suppress(OSError):
            _publish_json(
                output / "failure.json",
                {
                    "schema": PREPARATION_SCHEMA,
                    "status": "FAILED",
                    "stage": stage,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "scientific_execution_authorized": False,
                    "finalized_files": {
                        item.name: sha256(item.read_bytes()).hexdigest()
                        for item in sorted(output.iterdir())
                        if item.is_file()
                    },
                },
            )
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photometry", required=True, type=Path)
    parser.add_argument("--membership", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--horizons-days", required=True, nargs="+", type=float)
    parser.add_argument(
        "--fractions",
        nargs=3,
        type=float,
        default=(0.6, 0.2, 0.2),
        metavar=("TRAIN", "VALIDATION", "TEST"),
    )
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args(argv)
    try:
        result = prepare_population_batches(
            args.photometry,
            args.membership,
            args.output,
            horizons_days=args.horizons_days,
            train_fraction=args.fractions[0],
            validation_fraction=args.fractions[1],
            test_fraction=args.fractions[2],
            batch_size=args.batch_size,
        )
    except (ValueError, OSError, RuntimeError, csv.Error) as exc:
        print(f"population preparation failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": result["status"],
                "result_digest": result["result_digest"],
                "partition_rows": {
                    name: row["row_count"] for name, row in result["splits"].items()
                },
                "scientific_execution_authorized": False,
            },
            sort_keys=True,
        )
    )
    return 0


_IMPORTED_SOURCE_FILES = _source_hashes()

if __name__ == "__main__":
    raise SystemExit(main())
