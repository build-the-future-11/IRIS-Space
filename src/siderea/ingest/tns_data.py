"""Offline inventory and normalization for user-supplied TNS data."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from siderea.provenance import digest_file, digest_value, utc_now

TNS_INVENTORY_SCHEMA = "siderea.tns_data_inventory.v1"
TNS_PHOTOMETRY_SCHEMA = "siderea.tns_photometry.v1"

_TABLE_SUFFIXES = {".csv", ".tsv"}
_JSON_SUFFIXES = {".json", ".jsonl", ".ndjson"}


def _folded_fields(fields: list[str]) -> set[str]:
    return {field.strip().casefold() for field in fields}


def classify_tns_fields(fields: list[str]) -> str:
    """Classify a tabular/object schema without interpreting scientific values."""

    folded = _folded_fields(fields)
    time_fields = {"mjd", "jd", "observed_at_mjd", "observation_time", "dateobs"}
    band_fields = {"band", "filter", "filter_value", "filter_name"}
    value_fields = {"flux", "flux_density", "magnitude", "mag", "value"}
    wavelength_fields = {"wavelength", "wavelength_angstrom", "lambda", "wave"}
    if folded & wavelength_fields and folded & {"flux", "flux_density", "flam", "fnu"}:
        return "spectra"
    if folded & time_fields and folded & band_fields and folded & value_fields:
        return "photometry"
    if folded & {"tns_name", "objname"} and folded & {
        "source_id",
        "oid",
        "alerce_id",
        "ztf_id",
    }:
        return "crossmatch"
    if folded & {"objid", "objname", "tns_name", "name"} and folded & {
        "ra",
        "ra_deg",
        "radeg",
    }:
        return "registry"
    if folded & {"classification", "object_type", "type", "redshift"}:
        return "classification"
    return "unknown"


def _json_records(path: Path) -> tuple[list[Mapping[str, Any]], list[str]]:
    if path.suffix.casefold() in {".jsonl", ".ndjson"}:
        records: list[Mapping[str, Any]] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, Mapping):
                raise ValueError(f"JSONL row {line_number} is not an object")
            records.append(value)
        fields = sorted({str(key) for record in records for key in record})
        return records, fields
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        records = [item for item in value if isinstance(item, Mapping)]
    elif isinstance(value, Mapping):
        data = value.get("data")
        reply = data.get("reply") if isinstance(data, Mapping) else None
        candidate = reply if isinstance(reply, list) else data
        if isinstance(candidate, list):
            records = [item for item in candidate if isinstance(item, Mapping)]
        elif isinstance(candidate, Mapping):
            records = [candidate]
        else:
            records = [value]
    else:
        raise ValueError("JSON root is neither an object nor an array")
    fields = sorted({str(key) for record in records for key in record})
    return records, fields


def inspect_tns_asset(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise ValueError(f"TNS asset is not a regular file: {source}")
    suffix = source.suffix.casefold()
    result: dict[str, Any] = {
        "path": str(source),
        "size_bytes": source.stat().st_size,
        "modified_ns": source.stat().st_mtime_ns,
        "sha256": digest_file(source),
        "format": "unknown",
        "classification": "unknown",
        "rows": None,
        "fields": [],
        "parse_status": "unsupported",
        "error": None,
    }
    try:
        if suffix in _TABLE_SUFFIXES:
            delimiter = "\t" if suffix == ".tsv" else ","
            frame = pd.read_csv(source, sep=delimiter)
            fields = [str(column) for column in frame.columns]
            result.update(
                format=suffix[1:],
                classification=classify_tns_fields(fields),
                rows=int(len(frame)),
                fields=fields,
                parse_status="parsed",
            )
        elif suffix in _JSON_SUFFIXES:
            records, fields = _json_records(source)
            result.update(
                format=suffix[1:],
                classification=classify_tns_fields(fields),
                rows=len(records),
                fields=fields,
                parse_status="parsed",
            )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        pd.errors.ParserError,
        ValueError,
    ) as exc:
        result["parse_status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def audit_tns_input(path: str | Path) -> dict[str, Any]:
    """Return a deterministic, read-only inventory for a file or directory."""

    source = Path(path).expanduser().resolve()
    if source.is_file():
        files = [source]
    elif source.is_dir():
        files = sorted(
            item for item in source.rglob("*") if item.is_file() and not item.is_symlink()
        )
    else:
        raise ValueError(f"TNS input does not exist: {source}")
    assets = [inspect_tns_asset(item) for item in files]
    parsed = [asset for asset in assets if asset["parse_status"] == "parsed"]
    classifications: dict[str, int] = {}
    row_counts: dict[str, int] = {}
    for asset in parsed:
        kind = str(asset["classification"])
        classifications[kind] = classifications.get(kind, 0) + 1
        rows = asset["rows"]
        row_counts[kind] = row_counts.get(kind, 0) + (int(rows) if rows is not None else 0)
    if row_counts.get("photometry", 0) > 0:
        decision = "READY_FULL"
    elif row_counts.get("registry", 0) + row_counts.get("classification", 0) > 0:
        decision = "READY_REGISTRY_LABELS_ONLY"
    else:
        decision = "NOT_READY"
    identity = {
        "schema": TNS_INVENTORY_SCHEMA,
        "input_root": str(source),
        "assets": assets,
        "classifications": classifications,
        "row_counts": row_counts,
        "readiness": decision,
    }
    return {
        **identity,
        "created_at": utc_now(),
        "inventory_digest": digest_value(identity),
    }


def normalize_tns_photometry(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize a strict tabular TNS photometry export and retain rejected rows."""

    aliases = {
        "entity_id": ("entity_id", "tns_name", "objname", "name"),
        "observation_id": ("observation_id", "measurement_id", "id"),
        "observed_at_mjd": ("observed_at_mjd", "mjd"),
        "available_at_mjd": ("available_at_mjd", "query_mjd"),
        "band": ("band", "filter", "filter_name"),
        "value": ("value", "flux", "flux_density", "magnitude", "mag"),
        "value_error": ("value_error", "flux_error", "magnitude_error", "magerr"),
        "is_detection": ("is_detection", "detected"),
        "limiting_value": ("limiting_value", "limiting_magnitude", "limmag"),
    }
    folded = {str(column).casefold(): str(column) for column in frame.columns}
    resolved: dict[str, str | None] = {}
    for logical, candidates in aliases.items():
        matches = [folded[name] for name in candidates if name in folded]
        resolved[logical] = matches[0] if len(matches) == 1 else None
    required = ("entity_id", "observation_id", "observed_at_mjd", "available_at_mjd", "band")
    missing = [name for name in required if resolved[name] is None]
    if missing:
        raise ValueError(f"TNS photometry is missing required fields: {missing}")

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row_index, row in frame.iterrows():
        try:
            entity = str(row[resolved["entity_id"]]).strip()  # type: ignore[index]
            observation = str(row[resolved["observation_id"]]).strip()  # type: ignore[index]
            band = str(row[resolved["band"]]).strip()  # type: ignore[index]
            observed = float(row[resolved["observed_at_mjd"]])  # type: ignore[index]
            available = float(row[resolved["available_at_mjd"]])  # type: ignore[index]
            if not entity or not observation or not band:
                raise ValueError("empty identity or band")
            if not math.isfinite(observed) or not math.isfinite(available):
                raise ValueError("non-finite time")
            detection_column = resolved["is_detection"]
            is_detection = True if detection_column is None else bool(row[detection_column])
            value_column = resolved["value"]
            error_column = resolved["value_error"]
            limit_column = resolved["limiting_value"]
            value = (
                None
                if value_column is None or pd.isna(row[value_column])
                else float(row[value_column])
            )
            error = (
                None
                if error_column is None or pd.isna(row[error_column])
                else float(row[error_column])
            )
            limit = (
                None
                if limit_column is None or pd.isna(row[limit_column])
                else float(row[limit_column])
            )
            if is_detection and (value is None or error is None or error <= 0.0):
                raise ValueError("detection lacks value or positive uncertainty")
            if not is_detection and limit is None:
                raise ValueError("non-detection lacks limiting value")
            accepted.append(
                {
                    "schema": TNS_PHOTOMETRY_SCHEMA,
                    "entity_id": entity,
                    "observation_id": observation,
                    "observed_at_mjd": observed,
                    "available_at_mjd": available,
                    "band": band,
                    "value": value,
                    "value_error": error,
                    "is_detection": is_detection,
                    "limiting_value": limit,
                }
            )
        except (TypeError, ValueError) as exc:
            rejected.append({"row_index": str(row_index), "reason": str(exc), "row": row.to_json()})
    return pd.DataFrame(accepted), pd.DataFrame(rejected)


__all__ = [
    "TNS_INVENTORY_SCHEMA",
    "TNS_PHOTOMETRY_SCHEMA",
    "audit_tns_input",
    "classify_tns_fields",
    "inspect_tns_asset",
    "normalize_tns_photometry",
]
