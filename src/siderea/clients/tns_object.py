"""Read-only TNS Get Object client with no submission capability."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from siderea.clients.base import ResilientExecutor, ServiceResult
from siderea.clients.tns import TNSCredentials
from siderea.provenance import CheckProvenance, CheckStatus, digest_value

TNS_OBJECT_URL = "https://www.wis-tns.org/api/get/object"


def _endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("endpoint must be an HTTPS URL without credentials or fragment")
    return value


def _object_reply(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        successful = int(str(payload.get("id_code"))) == 200
    except ValueError:
        successful = False
    if not successful:
        raise ValueError(f"TNS API error: {payload.get('id_message', 'unknown error')}")
    data = payload.get("data")
    reply = data.get("reply") if isinstance(data, Mapping) else None
    if not isinstance(reply, Mapping):
        raise ValueError("TNS Get Object response lacks an object reply")
    return reply


class TNSObjectClient:
    def __init__(
        self,
        credentials: TNSCredentials,
        *,
        timeout_seconds: float = 30.0,
        endpoint: str = TNS_OBJECT_URL,
        executor: ResilientExecutor | None = None,
        response_loader: Callable[[Request, float], bytes] | None = None,
    ) -> None:
        credentials.validate()
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0.0:
            raise ValueError("timeout_seconds must be positive and finite")
        self.credentials = credentials
        self.timeout_seconds = float(timeout_seconds)
        self.endpoint = _endpoint(endpoint)
        self.executor = executor or ResilientExecutor()
        self.response_loader = response_loader

    def _request(
        self, object_name: str, *, include_photometry: bool, include_spectra: bool
    ) -> Mapping[str, Any]:
        marker = "tns_marker" + json.dumps(
            {
                "tns_id": self.credentials.bot_id,
                "type": "bot",
                "name": self.credentials.bot_name,
            },
            separators=(",", ":"),
        )
        query = {
            "objname": object_name,
            "photometry": "1" if include_photometry else "0",
            "spectra": "1" if include_spectra else "0",
        }
        request = Request(
            self.endpoint,
            data=urlencode(
                {"api_key": self.credentials.api_key, "data": json.dumps(query)}
            ).encode(),
            headers={"User-Agent": marker, "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        if self.response_loader is not None:
            raw = self.response_loader(request, self.timeout_seconds)
        else:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                raw = response.read()
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("TNS returned a non-object response")
        return payload

    def get_object(
        self,
        object_name: str,
        *,
        include_photometry: bool = True,
        include_spectra: bool = False,
    ) -> ServiceResult[Mapping[str, Any]]:
        name = str(object_name).strip()
        if not name:
            raise ValueError("object_name must not be empty")
        public_query = {
            "object_name": name,
            "include_photometry": include_photometry,
            "include_spectra": include_spectra,
            "capability": "read_only_get_object",
        }
        result = self.executor.run(
            service="tns_object",
            query=public_query,
            operation=lambda: self._request(
                name,
                include_photometry=include_photometry,
                include_spectra=include_spectra,
            ),
            has_match=lambda payload: bool(_object_reply(payload)),
            match_names=lambda payload: (name,) if _object_reply(payload) else (),
            retry_if=lambda exc: not isinstance(exc, ValueError),
        )
        if result.value is None:
            return result
        reply = _object_reply(result.value)
        provenance = CheckProvenance(
            service="tns_object",
            status=CheckStatus.MATCH,
            checked_at=result.provenance.checked_at,
            query=public_query,
            matches=(name,),
            attempts=result.provenance.attempts,
            latency_ms=result.provenance.latency_ms,
            response_digest=digest_value(reply),
            service_version="tns-get-object.v1",
        )
        return ServiceResult(provenance=provenance, value=reply, records=result.records)


__all__ = ["TNS_OBJECT_URL", "TNSObjectClient"]
