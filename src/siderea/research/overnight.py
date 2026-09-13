"""Fail-closed scale and cohort contracts for overnight shadow experiments."""

from __future__ import annotations

import hmac
import json
import math
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

from siderea.provenance import digest_file, digest_value, stable_json

SHARD_MANIFEST_SCHEMA = "siderea.transient_shards.v1"
REFERENCE_COHORT_SCHEMA = "siderea.jepa_reference_cohort.v1"


def _verified(payload: Mapping[str, Any], schema: str, name: str) -> dict[str, Any]:
    materialized = dict(payload)
    if materialized.get("schema") != schema:
        raise ValueError(f"{name} must use schema {schema!r}")
    stored = materialized.pop("result_digest", None)
    if not isinstance(stored, str) or not hmac.compare_digest(stored, digest_value(materialized)):
        raise ValueError(f"{name} result digest differs from its content")
    return dict(payload)


def _canonical_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return " ".join(value.casefold().split())


def shard_flux_table(frame: Any, output_dir: Path, *, max_channels: int = 100) -> dict[str, Any]:
    """Write entity-safe CSV shards and a content-bound manifest atomically."""

    import pandas as pd

    if type(max_channels) is not int or not 1 <= max_channels <= 100:
        raise ValueError("max_channels must be an integer within [1, 100]")
    required = {"source_id", "survey", "band"}
    if not isinstance(frame, pd.DataFrame) or frame.empty or not required <= set(frame):
        raise ValueError(
            "sharding requires a non-empty flux table with source_id, survey, and band"
        )
    data = frame.copy()
    source_ids = data["source_id"].astype("string").str.strip()
    if source_ids.isna().any() or source_ids.eq("").any():
        raise ValueError("sharding requires non-empty source IDs")
    data["source_id"] = source_ids.astype(str)
    entity_groups = list(data.groupby("source_id", sort=True, dropna=False))
    planned: list[list[tuple[str, Any]]] = []
    current: list[tuple[str, Any]] = []
    current_channels = 0
    for source_id, group in entity_groups:
        channels = len(group[["survey", "band"]].drop_duplicates())
        if channels > max_channels:
            raise ValueError(
                f"entity {source_id!r} has {channels} channels and cannot fit one shard"
            )
        if current and current_channels + channels > max_channels:
            planned.append(current)
            current = []
            current_channels = 0
        current.append((str(source_id), group))
        current_channels += channels
    if current:
        planned.append(current)

    destination = output_dir.expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"shard output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    temporary.mkdir(mode=0o700)
    try:
        shards: list[dict[str, Any]] = []
        for index, groups in enumerate(planned, start=1):
            shard = pd.concat([group for _, group in groups], ignore_index=True)
            path = temporary / f"shard-{index:04d}.csv"
            path.write_text(shard.to_csv(index=False, lineterminator="\n"), encoding="utf-8")
            shards.append(
                {
                    "path": path.name,
                    "sha256": digest_file(path),
                    "rows": len(shard),
                    "channels": len(shard[["source_id", "survey", "band"]].drop_duplicates()),
                    "entities": [source for source, _ in groups],
                }
            )
        manifest: dict[str, Any] = {
            "schema": SHARD_MANIFEST_SCHEMA,
            "max_channels": max_channels,
            "rows": len(data),
            "entities": len(entity_groups),
            "shard_count": len(shards),
            "source_table_sha256": digest_value(
                {"columns": list(data.columns), "records": data.to_dict(orient="records")}
            ),
            "shards": shards,
        }
        manifest["result_digest"] = digest_value(manifest)
        (temporary / "manifest.json").write_text(stable_json(manifest) + "\n", encoding="utf-8")
        temporary.replace(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return manifest


def verify_shard_manifest(directory: Path) -> dict[str, Any]:
    """Verify every shard byte and entity allocation in a published directory."""

    manifest_path = directory / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("shard manifest must be a JSON object")
    manifest = _verified(payload, SHARD_MANIFEST_SCHEMA, "shard manifest")
    shards = manifest.get("shards")
    if not isinstance(shards, list) or not shards:
        raise ValueError("shard manifest contains no shards")
    entities: set[str] = set()
    for shard in shards:
        if not isinstance(shard, Mapping):
            raise ValueError("shard manifest entries must be objects")
        raw_path = shard.get("path")
        if not isinstance(raw_path, str) or Path(raw_path).name != raw_path:
            raise ValueError("shard paths must be plain relative filenames")
        path = directory / raw_path
        if not path.is_file() or digest_file(path) != shard.get("sha256"):
            raise ValueError(f"shard {raw_path!r} is missing or differs from its digest")
        raw_entities = shard.get("entities")
        if not isinstance(raw_entities, list) or not raw_entities:
            raise ValueError("every shard must contain entity IDs")
        canonical = {_canonical_id(value, "shard entity") for value in raw_entities}
        if len(canonical) != len(raw_entities) or entities & canonical:
            raise ValueError("shard entities must be unique within and across shards")
        entities.update(canonical)
    if len(entities) != manifest.get("entities"):
        raise ValueError("shard manifest entity count is inconsistent")
    return manifest


def merge_transient_searches(searches: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Merge independently executed entity shards under one identical search contract."""

    if not searches:
        raise ValueError("at least one transient-search shard is required")
    verified = [
        _verified(item, "siderea.transient_search.v1", f"transient shard {index}")
        for index, item in enumerate(searches, start=1)
    ]
    contract_fields = (
        "mode",
        "assumptions",
        "noise_timescale_days",
        "correlated_variance_fraction",
        "null_method",
        "wild_block_size",
        "physical_classification",
        "qualifies_reportability",
        "seed",
        "null_trials",
        "alpha",
        "widths_days",
        "center_count",
        "prediction_cutoff_mjd",
    )
    baseline = verified[0]
    for shard in verified[1:]:
        for field in contract_fields:
            if shard.get(field) != baseline.get(field):
                raise ValueError(f"transient shards disagree on {field}")
        left, right = baseline.get("campaign_inference"), shard.get("campaign_inference")
        if not isinstance(left, Mapping) or not isinstance(right, Mapping):
            if left != right:
                raise ValueError("transient shards disagree on campaign inference")
        else:
            for field in (
                "method",
                "object_universe_size",
                "planned_looks",
                "look_index",
                "correction_factor",
            ):
                if left.get(field) != right.get(field):
                    raise ValueError(f"transient shards disagree on campaign {field}")

    channels: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    seen_entities: set[str] = set()
    seen_channels: set[tuple[str, str, str]] = set()
    for shard in verified:
        raw_objects, raw_channels = shard.get("objects"), shard.get("channels")
        if not isinstance(raw_objects, list) or not isinstance(raw_channels, list):
            raise ValueError("transient shards require object and channel arrays")
        shard_entities: set[str] = set()
        for raw in raw_objects:
            if not isinstance(raw, Mapping):
                raise ValueError("transient object rows must be objects")
            entity = _canonical_id(raw.get("source_id"), "transient source_id")
            if entity in seen_entities or entity in shard_entities:
                raise ValueError(f"transient shards repeat entity {entity!r}")
            shard_entities.add(entity)
            objects.append(dict(raw))
        seen_entities.update(shard_entities)
        for raw in raw_channels:
            if not isinstance(raw, Mapping):
                raise ValueError("transient channel rows must be objects")
            identity = (
                _canonical_id(raw.get("source_id"), "transient source_id"),
                _canonical_id(raw.get("survey"), "transient survey"),
                _canonical_id(raw.get("band"), "transient band"),
            )
            if identity in seen_channels:
                raise ValueError(f"transient shards repeat channel {identity!r}")
            if identity[0] not in shard_entities:
                raise ValueError("transient shard channel has no object summary")
            seen_channels.add(identity)
            channels.append(dict(raw))

    campaign = baseline.get("campaign_inference")
    merged_campaign = None if not isinstance(campaign, Mapping) else dict(campaign)
    if merged_campaign is not None:
        merged_campaign["searched_object_count"] = len(seen_entities)
        universe = merged_campaign.get("object_universe_size")
        if isinstance(universe, int) and len(seen_entities) > universe:
            raise ValueError("merged searched entities exceed the declared object universe")
    output: dict[str, Any] = {field: baseline.get(field) for field in ("schema", *contract_fields)}
    output.update(
        {
            "scope": baseline.get("scope"),
            "campaign_inference": merged_campaign,
            "channels": sorted(
                channels,
                key=lambda row: (
                    str(row.get("source_id")),
                    str(row.get("survey")),
                    str(row.get("band")),
                ),
            ),
            "objects": sorted(objects, key=lambda row: str(row.get("source_id"))),
            "shard_count": len(verified),
            "shard_result_digests": [item["result_digest"] for item in verified],
            "shard_input_sha256": [item.get("input_sha256") for item in verified],
        }
    )
    output["result_digest"] = digest_value(output)
    return output


def freeze_reference_cohort(
    records: Sequence[Mapping[str, Any]],
    *,
    dataset_sha256: str,
    cohort_id: str,
    selection_policy: str,
) -> dict[str, Any]:
    """Freeze the exact entity population permitted to fit JEPA anomaly scoring."""

    normalized_id = cohort_id.strip()
    normalized_policy = selection_policy.strip()
    if not normalized_id or not normalized_policy:
        raise ValueError("cohort_id and selection_policy must be non-empty")
    if len(dataset_sha256) != 64 or any(c not in "0123456789abcdef" for c in dataset_sha256):
        raise ValueError("dataset_sha256 must be a lowercase SHA-256 digest")
    entities: list[str] = []
    cutoffs: list[float] = []
    for record in records:
        entity = _canonical_id(record.get("entity_id"), "reference entity_id")
        if entity in entities:
            raise ValueError(f"reference cohort repeats entity {entity!r}")
        cutoff = record.get("prediction_cutoff_mjd")
        if (
            isinstance(cutoff, bool)
            or not isinstance(cutoff, (int, float))
            or not math.isfinite(float(cutoff))
        ):
            raise ValueError("reference cohort requires finite prediction cutoffs")
        times = record.get("times")
        if isinstance(times, (str, bytes)) or not isinstance(times, Sequence) or not times:
            raise ValueError("reference cohort requires non-empty time arrays")
        numeric_times = [float(value) for value in times]
        if not all(math.isfinite(value) for value in numeric_times) or max(numeric_times) > float(
            cutoff
        ):
            raise ValueError("reference cohort contains invalid or post-cutoff observations")
        entities.append(entity)
        cutoffs.append(float(cutoff))
    if len(entities) < 2:
        raise ValueError("reference cohort requires at least two physical entities")
    output: dict[str, Any] = {
        "schema": REFERENCE_COHORT_SCHEMA,
        "cohort_id": normalized_id,
        "role": "jepa_anomaly_reference_only",
        "selection_policy": normalized_policy,
        "dataset_sha256": dataset_sha256,
        "entity_count": len(entities),
        "canonical_entity_ids": sorted(entities),
        "prediction_cutoff_extent": [min(cutoffs), max(cutoffs)],
        "qualifies_reportability": False,
    }
    output["result_digest"] = digest_value(output)
    return output


def verify_reference_embeddings(
    cohort: Mapping[str, Any], embeddings: Mapping[str, Any]
) -> dict[str, Any]:
    """Verify an embedding artifact is an exact rendering of a frozen cohort."""

    frozen = _verified(cohort, REFERENCE_COHORT_SCHEMA, "reference cohort")
    if embeddings.get("dataset_snapshot_sha256") != frozen.get("dataset_sha256"):
        raise ValueError("reference embeddings use a different dataset snapshot")
    rows = embeddings.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("reference embeddings contain no rows")
    entities = sorted(_canonical_id(row.get("entity_id"), "embedding entity_id") for row in rows)
    if entities != frozen.get("canonical_entity_ids"):
        raise ValueError("reference embeddings differ from the frozen cohort entities")
    return frozen


def verify_integration_manifests(
    *,
    pilot_manifest_path: Path,
    pipeline_manifest_path: Path,
    pipeline_candidates_path: Path,
    transient_search: Mapping[str, Any],
    candidate_embeddings: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify the prepared data and complete operational run used by assembly."""

    pilot_payload = json.loads(pilot_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(pilot_payload, Mapping) or pilot_payload.get("schema") != (
        "siderea.pilot_dataset.v2"
    ):
        raise ValueError("pilot manifest must use schema 'siderea.pilot_dataset.v2'")
    pilot = dict(pilot_payload)
    pilot_digest = pilot.pop("manifest_digest", None)
    if not isinstance(pilot_digest, str) or not hmac.compare_digest(
        pilot_digest, digest_value(pilot)
    ):
        raise ValueError("pilot manifest digest differs from its content")
    pilot_dir = pilot_manifest_path.resolve().parent
    prepared_files = {
        "detector_flux_sha256": pilot_dir / "detector_flux.csv",
        "jepa_dataset_sha256": pilot_dir / "jepa.jsonl",
    }
    pipeline_view = pilot.get("pipeline_view")
    if not isinstance(pipeline_view, Mapping) or pipeline_view.get("status") != "available":
        raise ValueError("pilot manifest does not contain an operational pipeline view")
    pipeline_name = pipeline_view.get("path")
    if not isinstance(pipeline_name, str) or Path(pipeline_name).name != pipeline_name:
        raise ValueError("pilot pipeline path must be a plain relative filename")
    prepared_files["pipeline_view"] = pilot_dir / pipeline_name
    for field, path in prepared_files.items():
        expected = pipeline_view.get("sha256") if field == "pipeline_view" else pilot.get(field)
        if not path.is_file() or digest_file(path) != expected:
            raise ValueError(f"prepared pilot artifact {path.name!r} differs from its manifest")
    if transient_search.get("input_sha256") != pilot.get("detector_flux_sha256"):
        raise ValueError("transient search is not bound to the prepared detector flux")
    if candidate_embeddings.get("dataset_snapshot_sha256") != pilot.get("jepa_dataset_sha256"):
        raise ValueError("candidate embeddings are not bound to the prepared JEPA data")

    pipeline_payload = json.loads(pipeline_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(pipeline_payload, Mapping) or pipeline_payload.get("schema") != (
        "siderea.run_manifest.v1"
    ):
        raise ValueError("pipeline manifest must use schema 'siderea.run_manifest.v1'")
    pipeline = dict(pipeline_payload)
    if pipeline.get("status") != "completed":
        raise ValueError("pipeline manifest must record completed status")
    configuration = pipeline.get("configuration")
    if not isinstance(configuration, Mapping) or pipeline.get("configuration_digest") != (
        digest_value(configuration)
    ):
        raise ValueError("pipeline configuration digest differs from its content")
    artifacts = pipeline.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("pipeline manifest contains no artifacts")
    candidate_artifacts = []
    source_artifacts = []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise ValueError("pipeline manifest artifact entries must be objects")
        path_value = artifact.get("path")
        if not isinstance(path_value, str):
            raise ValueError("pipeline manifest artifact path is invalid")
        path = Path(path_value)
        if not path.is_file() or digest_file(path) != artifact.get("sha256"):
            raise ValueError(f"pipeline artifact {path.name!r} differs from its manifest")
        if artifact.get("role") == "candidate-evidence":
            candidate_artifacts.append(artifact)
        if artifact.get("role") == "source-input-snapshot":
            source_artifacts.append(artifact)
    if len(candidate_artifacts) != 1 or candidate_artifacts[0].get("sha256") != digest_file(
        pipeline_candidates_path
    ):
        raise ValueError("pipeline candidates file is not the manifest's candidate evidence")
    if len(source_artifacts) != 1 or source_artifacts[0].get("sha256") != pipeline_view.get(
        "sha256"
    ):
        raise ValueError("pipeline run did not consume the prepared operational photometry")
    code_digest = pipeline.get("code_source_digest")
    if not isinstance(code_digest, str) or len(code_digest) != 64:
        raise ValueError("pipeline manifest has an invalid code-source digest")
    return {
        "pilot_manifest_digest": pilot_digest,
        "pilot_manifest_sha256": digest_file(pilot_manifest_path),
        "pipeline_manifest_sha256": digest_file(pipeline_manifest_path),
        "pipeline_configuration_digest": pipeline["configuration_digest"],
        "pipeline_code_source_digest": code_digest,
    }


__all__ = [
    "REFERENCE_COHORT_SCHEMA",
    "SHARD_MANIFEST_SCHEMA",
    "freeze_reference_cohort",
    "merge_transient_searches",
    "shard_flux_table",
    "verify_reference_embeddings",
    "verify_integration_manifests",
    "verify_shard_manifest",
]
