"""Provenance primitives used by every external scientific check.

The important invariant is that an error is never represented as a negative
match.  Consumers must explicitly distinguish CLEAR from ERROR/SKIPPED/STALE.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any


class ExternalCheckStatus(StrEnum):
    """Outcome of a remote identity/catalogue check.

    This is deliberately separate from :class:`siderea.domain.CheckStatus`, which
    describes generic workflow evidence using PASS/FAIL semantics.  A catalogue
    lookup instead answers CLEAR/MATCH and must never turn transport failure
    into a scientifically meaningful negative result.
    """

    CLEAR = "clear"
    MATCH = "match"
    ERROR = "error"
    DISABLED = "disabled"
    STALE = "stale"
    PENDING = "pending"


# Backwards-compatible import for the first SIDEREA prototype.  New code should
# prefer the unambiguous public name above.
CheckStatus = ExternalCheckStatus


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class _FrozenSequence(tuple[Any, ...]):
    """Immutable JSON array that retains list-compatible equality."""

    def __new__(cls, values: Iterable[Any] = ()) -> _FrozenSequence:
        return super().__new__(cls, values)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Sequence) and not isinstance(other, (str, bytes, bytearray)):
            return tuple(self) == tuple(other)
        return False

    __hash__ = tuple.__hash__


def _canonical_json_value(value: Any, *, path: str = "$") -> Any:
    """Return plain canonical JSON data or reject lossy/non-standard values.

    Integrity identifiers must not depend on ``str(object)`` fallbacks.  Those
    fallbacks erase types, can be process-dependent, and previously made the
    integer key ``1`` collide with the string key ``"1"``.  RFC-invalid NaN
    and infinity values are rejected for the same reason.
    """

    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite number is not valid canonical JSON at {path}")
        return float(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"canonical JSON object keys must be strings at {path}")
            result[key] = _canonical_json_value(item, path=f"{path}.{key}")
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _canonical_json_value(item, path=f"{path}[{index}]") for index, item in enumerate(value)
        ]
    raise TypeError(
        f"unsupported canonical JSON value {type(value).__name__} at {path}; "
        "serialize it explicitly"
    )


def _freeze_json_value(value: Any) -> Any:
    """Recursively freeze already canonical JSON-compatible data."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenSequence(_freeze_json_value(item) for item in value)
    return value


def stable_json(value: Any) -> str:
    canonical = _canonical_json_value(value)
    return json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest_value(value: Any) -> str:
    return sha256(stable_json(value).encode("utf-8")).hexdigest()


def digest_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class CheckProvenance:
    service: str
    status: ExternalCheckStatus
    checked_at: str = field(default_factory=utc_now)
    expires_at: str = ""
    query: Mapping[str, Any] = field(default_factory=dict)
    matches: Sequence[str] = field(default_factory=tuple)
    error: str = ""
    attempts: int = 1
    latency_ms: float | None = None
    response_digest: str = ""
    service_version: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.service, str):
            raise TypeError("service must be a string")
        service = self.service.strip().casefold()
        if not service:
            raise ValueError("service must not be empty")
        if not isinstance(self.status, ExternalCheckStatus):
            raise TypeError("status must be an ExternalCheckStatus")
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int):
            raise TypeError("attempts must be an integer")
        if self.attempts < 0:
            raise ValueError("attempts must be non-negative")
        if not isinstance(self.query, Mapping):
            raise TypeError("query must be a mapping")
        for name, value in (
            ("error", self.error),
            ("service_version", self.service_version),
            ("expires_at", self.expires_at),
        ):
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a string")
        if self.latency_ms is not None and (
            isinstance(self.latency_ms, bool)
            or not isinstance(self.latency_ms, (int, float))
            or not math.isfinite(self.latency_ms)
            or self.latency_ms < 0
        ):
            raise ValueError("latency_ms must be finite and non-negative")

        if not isinstance(self.response_digest, str):
            raise TypeError("response_digest must be a string")
        response_digest = self.response_digest.strip().casefold()
        if response_digest and not re.fullmatch(r"[0-9a-f]{64}", response_digest):
            raise ValueError("response_digest must be a SHA-256 hexadecimal digest")

        checked = self._parse_timestamp(self.checked_at)
        if checked is None:
            raise ValueError("checked_at must be an ISO-8601 timestamp with a timezone")
        if self.expires_at:
            expires = self._parse_timestamp(self.expires_at)
            if expires is None:
                raise ValueError("expires_at must be an ISO-8601 timestamp with a timezone")
            if expires <= checked:
                raise ValueError("expires_at must be later than checked_at")

        canonical_query = _canonical_json_value(self.query, path="$.query")
        object.__setattr__(self, "service", service)
        object.__setattr__(self, "query", _freeze_json_value(canonical_query))
        if isinstance(self.matches, str):
            matches: Sequence[str] = (self.matches,)
        elif isinstance(self.matches, (bytes, bytearray)) or not isinstance(self.matches, Sequence):
            raise TypeError("matches must be a sequence of strings")
        else:
            matches = self.matches
        if any(not isinstance(item, str) for item in matches):
            raise TypeError("matches must be a sequence of strings")
        object.__setattr__(self, "matches", tuple(matches))
        object.__setattr__(self, "response_digest", response_digest)

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed

    @property
    def completed(self) -> bool:
        return self.status in {ExternalCheckStatus.CLEAR, ExternalCheckStatus.MATCH}

    @property
    def safe_clear(self) -> bool:
        return self.clear_integrity_error is None and self.is_fresh()

    @property
    def clear_integrity_error(self) -> str | None:
        """Explain why a claimed clear result lacks auditable response evidence."""

        if self.status is not ExternalCheckStatus.CLEAR:
            return "status is not clear"
        if self.attempts < 1:
            return "clear result records no successful service attempt"
        if not self.response_digest:
            return "clear result has no response digest"
        if self.matches:
            return "clear result contains matches"
        if self.error.strip():
            return "clear result contains an error"
        return None

    def is_fresh(self, *, now: datetime | None = None) -> bool:
        """Return true only for explicitly time-bounded, unexpired evidence.

        Missing expiration metadata is intentionally *not* fresh.  This makes a
        forgotten TTL fail closed instead of allowing a years-old catalogue
        response to open a reporting gate.
        """

        if not self.expires_at:
            return False
        instant = now or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("now must include timezone information")
        expiry = self._parse_timestamp(self.expires_at)
        if expiry is None:
            return False
        checked = self._parse_timestamp(self.checked_at)
        if checked is None or checked > instant + timedelta(minutes=5):
            return False
        return instant < expiry

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "status": self.status.value,
            "checked_at": self.checked_at,
            "expires_at": self.expires_at,
            "query": _canonical_json_value(self.query, path="$.query"),
            "matches": list(self.matches),
            "error": self.error,
            "attempts": self.attempts,
            "latency_ms": self.latency_ms,
            "response_digest": self.response_digest,
            "service_version": self.service_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CheckProvenance:
        required = {
            "service",
            "status",
            "checked_at",
            "expires_at",
            "query",
            "matches",
            "error",
            "attempts",
            "latency_ms",
            "response_digest",
            "service_version",
        }
        missing = sorted(required - set(payload))
        unknown = sorted(set(payload) - required)
        if missing:
            raise ValueError(f"check provenance is missing required fields: {missing}")
        if unknown:
            raise ValueError(f"check provenance has unknown fields: {unknown}")
        string_fields = (
            "service",
            "status",
            "checked_at",
            "expires_at",
            "error",
            "response_digest",
            "service_version",
        )
        for name in string_fields:
            if not isinstance(payload[name], str):
                raise TypeError(f"{name} must be a string")
        if isinstance(payload["attempts"], bool) or not isinstance(payload["attempts"], int):
            raise TypeError("attempts must be an integer")
        query = payload["query"]
        if not isinstance(query, Mapping):
            raise TypeError("query must be a mapping")
        raw_matches = payload["matches"]
        if not isinstance(raw_matches, (list, tuple)) or any(
            not isinstance(item, str) for item in raw_matches
        ):
            raise TypeError("matches must be an array of strings")
        raw_latency = payload["latency_ms"]
        if raw_latency is not None and (
            isinstance(raw_latency, bool) or not isinstance(raw_latency, (int, float))
        ):
            raise TypeError("latency_ms must be a number or null")
        return cls(
            service=payload["service"],
            status=ExternalCheckStatus(payload["status"]),
            checked_at=payload["checked_at"],
            expires_at=payload["expires_at"],
            query=dict(query),
            matches=tuple(raw_matches),
            error=payload["error"],
            attempts=payload["attempts"],
            latency_ms=float(raw_latency) if raw_latency is not None else None,
            response_digest=payload["response_digest"],
            service_version=payload["service_version"],
        )


__all__ = [
    "CheckProvenance",
    "CheckStatus",
    "ExternalCheckStatus",
    "digest_file",
    "digest_value",
    "stable_json",
    "utc_now",
]
