"""Integrity contract for broker-produced CSV snapshots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from siderea.provenance import digest_value

BROKER_SNAPSHOT_SCHEMA = "siderea.broker_snapshot.v1"
BROKER_SNAPSHOT_ID_SCHEMA = "siderea.broker_snapshot.identity.v1"
BROKER_SNAPSHOT_ID_COLUMN = "_siderea_broker_snapshot_id"


def broker_snapshot_id(
    *,
    source: str,
    retrieved_at: str,
    provenance: Mapping[str, Any],
    warnings: Sequence[str],
) -> str:
    """Bind a snapshot identity to all broker metadata outside the CSV bytes.

    The identifier is embedded in every CSV row and repeated in the adjacent
    sidecar.  The sidecar separately binds the resulting CSV bytes, avoiding a
    circular digest while making either missing half detectable.
    """

    if not isinstance(source, str) or not source.strip():
        raise ValueError("broker snapshot source must be a non-empty string")
    if not isinstance(retrieved_at, str):
        raise TypeError("broker snapshot retrieved_at must be a string")
    try:
        retrieved = datetime.fromisoformat(retrieved_at)
    except ValueError as exc:
        raise ValueError("broker snapshot retrieved_at must be an ISO-8601 timestamp") from exc
    if retrieved.tzinfo is None or retrieved.utcoffset() is None:
        raise ValueError("broker snapshot retrieved_at must include timezone information")
    if not isinstance(provenance, Mapping):
        raise TypeError("broker snapshot provenance must be a mapping")
    if isinstance(warnings, (str, bytes)) or not isinstance(warnings, Sequence):
        raise TypeError("broker snapshot warnings must be a sequence of strings")
    if any(not isinstance(warning, str) for warning in warnings):
        raise TypeError("broker snapshot warnings must be a sequence of strings")
    return digest_value(
        {
            "schema": BROKER_SNAPSHOT_ID_SCHEMA,
            "source": source.strip(),
            "retrieved_at": retrieved_at,
            "provenance": dict(provenance),
            "warnings": list(warnings),
        }
    )
