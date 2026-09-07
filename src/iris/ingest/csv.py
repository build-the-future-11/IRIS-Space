"""Local CSV ingestion with alias resolution and content provenance."""

from __future__ import annotations

import csv
import json
import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path

import pandas as pd

from .base import IngestionBatch, IngestionError
from .schema import normalize_photometry_frame, resolve_columns
from .snapshot import (
    BROKER_SNAPSHOT_ID_COLUMN,
    BROKER_SNAPSHOT_SCHEMA,
    broker_snapshot_id,
)


def ingest_csv(
    path: str | Path,
    *,
    column_map: Mapping[str, str] | None = None,
    coordinate_tolerance_arcsec: float = 2.0,
    survey: str = "local_csv",
) -> IngestionBatch:
    """Read and strictly normalize a candidate-photometry CSV file.

    The source identifier is read as text to preserve values such as ``0012``.
    Common ZTF/ALeRCE aliases are recognized; ambiguous aliases require an
    explicit ``column_map`` instead of silently choosing one.
    """

    source_path = Path(path).expanduser().resolve()
    if not source_path.is_file():
        raise IngestionError(f"CSV input does not exist or is not a file: {source_path}")
    try:
        # Parse and hash the exact same immutable byte snapshot. Reading the
        # path separately for schema, rows, and digest could otherwise bind a
        # run to different file generations if a producer replaced it midway.
        with source_path.open("rb") as source_handle:
            source_bytes = source_handle.read()
            source_stat = os.fstat(source_handle.fileno())
        raw_header = next(csv.reader(StringIO(source_bytes.decode("utf-8-sig"), newline="")))
        resolved_header = resolve_columns(raw_header, column_map=column_map)
        source_column = resolved_header["source_id"]
        observation_column = resolved_header["observation_id"]
        identifier_dtypes = {source_column: "string"}
        if observation_column is not None:
            identifier_dtypes[observation_column] = "string"
        frame = pd.read_csv(BytesIO(source_bytes), dtype=identifier_dtypes)
    except IngestionError:
        raise
    except Exception as exc:
        raise IngestionError(f"cannot read CSV input {source_path}: {exc}") from exc

    snapshot_marker: str | None = None
    marker_columns = [
        str(column)
        for column in frame.columns
        if str(column).casefold() == BROKER_SNAPSHOT_ID_COLUMN.casefold()
    ]
    reserved_broker_columns = [
        str(column)
        for column in frame.columns
        if str(column).casefold().startswith("_iris_broker_")
    ]
    if reserved_broker_columns and (
        len(marker_columns) != 1 or marker_columns != reserved_broker_columns
    ):
        raise IngestionError("broker CSV contains an unknown or malformed identity marker")
    if marker_columns:
        raw_markers = frame[marker_columns[0]]
        marker_missing = raw_markers.isna() | raw_markers.astype("string").str.strip().eq("")
        marker_values = raw_markers.astype("string").str.strip().drop_duplicates().tolist()
        if (
            marker_missing.any()
            or len(marker_values) != 1
            or not re.fullmatch(r"[0-9a-f]{64}", str(marker_values[0]) if marker_values else "")
        ):
            raise IngestionError("broker snapshot identity marker is missing or inconsistent")
        snapshot_marker = str(marker_values[0])

    effective_survey = survey
    inferred_ztf_bands = bool(
        resolved_header["survey"] is None
        and str(resolved_header["band"]).strip().casefold() == "fid"
        and survey.strip().casefold() == "local_csv"
    )
    if inferred_ztf_bands:
        effective_survey = "ztf"
    normalized, resolved, warnings = normalize_photometry_frame(
        frame,
        column_map=column_map,
        coordinate_tolerance_arcsec=coordinate_tolerance_arcsec,
        default_survey=effective_survey,
    )
    content_digest = sha256(source_bytes).hexdigest()
    source_modified_at = datetime.fromtimestamp(source_stat.st_mtime, tz=UTC).isoformat()
    source = f"csv:{source_path}"
    retrieved_at = datetime.now(UTC).isoformat()
    provenance: dict[str, object] = {
        "adapter": "iris.ingest.csv.v1",
        "path": str(source_path),
        "sha256": content_digest,
        "size_bytes": len(source_bytes),
        "source_modified_at": source_modified_at,
        "row_count": len(normalized),
        "column_map": {key: value for key, value in resolved.items() if value is not None},
    }
    combined_warnings = set(warnings)
    if inferred_ztf_bands:
        combined_warnings.add("inferred_ztf_survey_from_fid_column")
        provenance["band_system_inference"] = "ztf_from_fid_column"

    sidecar_path = source_path.with_suffix(source_path.suffix + ".provenance.json")
    if snapshot_marker is not None and not sidecar_path.is_file():
        raise IngestionError(
            f"broker-produced CSV is missing its provenance sidecar: {sidecar_path}"
        )
    if sidecar_path.is_file():
        try:
            sidecar_bytes = sidecar_path.read_bytes()
            sidecar = json.loads(sidecar_bytes)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise IngestionError(
                f"cannot read broker provenance sidecar {sidecar_path}: {exc}"
            ) from exc
        if not isinstance(sidecar, Mapping) or sidecar.get("schema") != BROKER_SNAPSHOT_SCHEMA:
            raise IngestionError("broker provenance sidecar has an unsupported schema")
        allowed_fields = {
            "schema",
            "snapshot_id",
            "source",
            "retrieved_at",
            "photometry_sha256",
            "provenance",
            "warnings",
        }
        unknown_fields = sorted(set(sidecar) - allowed_fields)
        if unknown_fields:
            raise IngestionError(f"broker provenance sidecar has unknown fields: {unknown_fields}")
        if sidecar.get("photometry_sha256") != content_digest:
            raise IngestionError("broker provenance sidecar does not match the CSV content digest")
        broker_provenance = sidecar.get("provenance")
        if not isinstance(broker_provenance, Mapping):
            raise IngestionError("broker provenance sidecar has no provenance object")
        if "row_count" in broker_provenance:
            row_count = broker_provenance["row_count"]
            if isinstance(row_count, bool) or not isinstance(row_count, int):
                raise IngestionError("broker provenance row count must be an integer")
            if row_count != len(normalized):
                raise IngestionError("broker provenance row count does not match normalized CSV")
        sidecar_source = sidecar.get("source")
        sidecar_retrieved = sidecar.get("retrieved_at")
        if not isinstance(sidecar_source, str) or not sidecar_source.strip():
            raise IngestionError("broker provenance sidecar has no source identity")
        if not sidecar_source.strip().casefold().startswith("broker:"):
            raise IngestionError("broker provenance sidecar source is not a broker identity")
        if not isinstance(sidecar_retrieved, str):
            raise IngestionError("broker provenance sidecar has no retrieval timestamp")
        try:
            parsed_retrieved = datetime.fromisoformat(sidecar_retrieved)
        except ValueError as exc:
            raise IngestionError("broker provenance retrieval timestamp is invalid") from exc
        if parsed_retrieved.tzinfo is None or parsed_retrieved.utcoffset() is None:
            raise IngestionError("broker provenance retrieval timestamp needs a timezone")
        raw_warnings = sidecar.get("warnings", [])
        if not isinstance(raw_warnings, list) or any(
            not isinstance(item, str) for item in raw_warnings
        ):
            raise IngestionError("broker provenance warnings must be an array of strings")
        sidecar_snapshot_id = sidecar.get("snapshot_id")
        if snapshot_marker is not None:
            if sidecar_snapshot_id != snapshot_marker:
                raise IngestionError("broker snapshot identity does not match its sidecar")
            expected_snapshot_id = broker_snapshot_id(
                source=sidecar_source,
                retrieved_at=sidecar_retrieved,
                provenance=broker_provenance,
                warnings=raw_warnings,
            )
            if snapshot_marker != expected_snapshot_id:
                raise IngestionError("broker snapshot metadata does not match its identity")
        elif sidecar_snapshot_id is not None:
            raise IngestionError("broker provenance sidecar identity is absent from the CSV")
        source = sidecar_source.strip()
        retrieved_at = sidecar_retrieved
        provenance = {
            **dict(broker_provenance),
            "broker_snapshot": {
                "schema": sidecar["schema"],
                "photometry_sha256": content_digest,
                "sidecar_sha256": sha256(sidecar_bytes).hexdigest(),
                "path": str(sidecar_path),
            },
        }
        combined_warnings.update(raw_warnings)

    return IngestionBatch(
        observations=normalized,
        source=source,
        retrieved_at=retrieved_at,
        provenance=provenance,
        warnings=tuple(sorted(combined_warnings)),
        source_content=source_bytes,
    )
