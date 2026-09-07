"""Transient Name Server search client with no write/submission capability."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from iris.provenance import CheckProvenance, CheckStatus, digest_value

from .base import ResilientExecutor, ServiceResult

TNS_SEARCH_URL = "https://www.wis-tns.org/api/get/search"


@dataclass(frozen=True)
class TNSCredentials:
    api_key: str = field(repr=False)
    bot_id: str
    bot_name: str

    def validate(self) -> None:
        if not all(isinstance(value, str) for value in (self.api_key, self.bot_id, self.bot_name)):
            raise TypeError("TNS credentials must be strings")
        if not self.api_key.strip() or not self.bot_id.strip() or not self.bot_name.strip():
            raise ValueError("complete TNS bot credentials are required")


def _rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    data = payload.get("data", {})
    if isinstance(data, list):
        return [row for row in data if isinstance(row, Mapping)]
    if isinstance(data, Mapping):
        reply = data.get("reply")
        if isinstance(reply, list):
            return [row for row in reply if isinstance(row, Mapping)]
        if "objname" in data:
            return [data]
    return []


def _names(payload: Mapping[str, Any]) -> Sequence[str]:
    names: set[str] = set()
    for row in _rows(payload):
        prefix = str(row.get("prefix", "")).strip()
        name = str(row.get("objname", "")).strip()
        value = f"{prefix} {name}".strip()
        if value:
            names.add(value)
    return tuple(sorted(names))


def _validate_response(payload: Mapping[str, Any]) -> None:
    """Reject TNS errors or malformed success payloads before calling them clear."""

    code = payload.get("id_code")
    try:
        successful = int(str(code)) == 200
    except (TypeError, ValueError):
        successful = False
    if not successful:
        message = str(payload.get("id_message") or "missing/invalid TNS status")
        raise ValueError(f"TNS API error ({code!r}): {message}")
    # TNS 2 search replies use a data list; the legacy API nests that list at
    # data.reply. An absent or differently shaped payload is not evidence that
    # the search found nothing, so it must fail closed.
    data = payload.get("data")
    if isinstance(data, list):
        rows = data
    elif isinstance(data, Mapping) and isinstance(data.get("reply"), list):
        rows = data["reply"]
    else:
        raise ValueError("TNS success response has no recognized search-result array")
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("TNS search-result array contains a malformed row")


def _validated_https_endpoint(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("endpoint must be a string")
    endpoint = value.strip()
    try:
        parsed = urlsplit(endpoint)
        _ = parsed.port  # Force validation of a malformed explicit port.
    except ValueError as exc:
        raise ValueError("endpoint must be a valid HTTPS URL") from exc
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("endpoint must be a valid HTTPS URL without credentials or a fragment")
    return endpoint


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


class TNSClient:
    def __init__(
        self,
        credentials: TNSCredentials,
        *,
        timeout_seconds: float = 30.0,
        endpoint: str = TNS_SEARCH_URL,
        executor: ResilientExecutor | None = None,
    ) -> None:
        credentials.validate()
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
            raise TypeError("timeout_seconds must be a number")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self.credentials = credentials
        self.timeout_seconds = float(timeout_seconds)
        self.endpoint = _validated_https_endpoint(endpoint)
        self.executor = executor or ResilientExecutor()

    def _request(self, query: Mapping[str, object]) -> Mapping[str, Any]:
        marker = "tns_marker" + json.dumps(
            {
                "tns_id": self.credentials.bot_id,
                "type": "bot",
                "name": self.credentials.bot_name,
            },
            separators=(",", ":"),
        )
        body = urlencode(
            {
                "api_key": self.credentials.api_key,
                "data": json.dumps(dict(query)),
            }
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            headers={"User-Agent": marker, "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(  # noqa: S310 - endpoint is validated as HTTPS during construction
            request,
            timeout=self.timeout_seconds,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("TNS returned a non-object response")
        _validate_response(payload)
        return payload

    def _search_once(
        self,
        query: Mapping[str, object],
        public_query: Mapping[str, object],
    ) -> ServiceResult[Mapping[str, Any]]:
        return self.executor.run(
            service="tns",
            query=public_query,
            operation=lambda: self._request(query),
            has_match=lambda payload: bool(_rows(payload)),
            match_names=_names,
            retry_if=lambda exc: not isinstance(exc, ValueError),
        )

    def search(
        self,
        *,
        internal_name: str,
        ra: float,
        dec: float,
        radius_arcsec: float = 3.0,
    ) -> ServiceResult[Mapping[str, Any]]:
        if not isinstance(internal_name, str):
            raise TypeError("internal_name must be a string")
        internal_name = internal_name.strip()
        if not internal_name:
            raise ValueError("internal_name must not be empty")
        ra = _finite_number(ra, "ra")
        dec = _finite_number(dec, "dec")
        radius_arcsec = _finite_number(radius_arcsec, "radius_arcsec")
        if not 0 <= ra < 360:
            raise ValueError("ra must be within [0, 360)")
        if not -90 <= dec <= 90:
            raise ValueError("dec must be within [-90, 90]")
        if radius_arcsec <= 0:
            raise ValueError("radius_arcsec must be positive")
        by_name = self._search_once(
            {"internal_name": internal_name},
            {"method": "internal_name", "internal_name": internal_name},
        )
        if by_name.provenance.status is not CheckStatus.CLEAR:
            return by_name
        by_cone = self._search_once(
            {"ra": ra, "dec": dec, "radius": radius_arcsec, "units": "arcsec"},
            {
                "method": "cone",
                "ra": ra,
                "dec": dec,
                "radius_arcsec": radius_arcsec,
                "internal_name_checked": internal_name,
            },
        )
        subchecks = (by_name.provenance, by_cone.provenance)
        checked_at = max(
            subchecks,
            key=lambda check: datetime.fromisoformat(check.checked_at),
        ).checked_at
        latencies = [check.latency_ms for check in subchecks if check.latency_ms is not None]
        matches = tuple(
            dict.fromkeys(name for check in subchecks for name in check.matches if name)
        )
        completed = by_cone.provenance.status in {CheckStatus.CLEAR, CheckStatus.MATCH}
        combined_value: Mapping[str, Any] = {
            "internal_name": by_name.value,
            "cone": by_cone.value,
        }
        provenance = CheckProvenance(
            service="tns",
            status=by_cone.provenance.status,
            checked_at=checked_at,
            query={
                "methods": ["internal_name", "cone"],
                "candidate_id": internal_name,
                "internal_name_checked": internal_name,
                "ra": ra,
                "dec": dec,
                "radius_arcsec": radius_arcsec,
                "coverage_policy": "internal_name_and_position_cone",
            },
            matches=matches,
            error=by_cone.provenance.error,
            attempts=sum(check.attempts for check in subchecks),
            latency_ms=sum(latencies) if latencies else None,
            response_digest=(
                digest_value([check.to_dict() for check in subchecks]) if completed else ""
            ),
            service_version="tns-two-stage-search.v1",
        )
        return ServiceResult(
            provenance=provenance,
            value=combined_value,
            records=(*by_name.records, *by_cone.records),
        )
