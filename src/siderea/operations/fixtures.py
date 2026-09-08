"""Content-addressed recorded HTTP/service fixtures for deterministic replay."""

from __future__ import annotations

import base64
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from siderea.atomic import atomic_create_binary
from siderea.provenance import digest_value, stable_json, utc_now

SERVICE_FIXTURE_SCHEMA = "siderea.service_fixture.v1"
_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "proxyauthorization",
        "apikey",
        "token",
        "accesstoken",
        "refreshtoken",
        "password",
        "secret",
        "clientsecret",
        "cookie",
        "setcookie",
        "xapikey",
    }
)


def _assert_no_credentials(value: Any) -> None:
    """Reject credentials before hashing/persistence; never echo secret values.

    Captures must be sanitized by the operator. Rejection preserves exact-byte
    replay semantics instead of silently changing the evidence being archived.
    This detects structured fields, not arbitrary secrets in opaque binary data.
    """

    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("fixture object keys must be strings")
            normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
            if normalized in _SENSITIVE_KEYS:
                raise ValueError("fixture contains forbidden credential fields; sanitize capture")
            _assert_no_credentials(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_credentials(item)
    elif isinstance(value, str):
        if value.startswith(("http://", "https://")):
            parsed = urlsplit(value)
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("fixture URL contains credentials; sanitize capture")
            _assert_no_credentials(dict(parse_qsl(parsed.query, keep_blank_values=True)))
            _assert_no_credentials(dict(parse_qsl(parsed.fragment, keep_blank_values=True)))
        if re.search(
            r"(?im)(?:^|[\s&{,])(?:authorization|set-cookie|api[_-]?key|access_token|"
            r"refresh_token|password|client_secret)\s*[:=]",
            value,
        ):
            raise ValueError("fixture text contains credential fields; sanitize capture")


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _timestamp(value: Any, name: str) -> str:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information")
    return parsed.isoformat()


def _canonical_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a JSON object")
    result = dict(value)
    _assert_no_credentials(result)
    stable_json(result)
    return result


@dataclass(frozen=True, slots=True)
class ServiceFixture:
    fixture_id: str
    service: str
    service_version: str
    capture_mode: str
    scenario: str
    recorded_at: str
    request: Mapping[str, Any]
    request_digest: str
    status_code: int
    response_headers: Mapping[str, Any]
    response_body_sha256: str
    response_body_base64: str
    schema: str = SERVICE_FIXTURE_SCHEMA

    @classmethod
    def create(
        cls,
        *,
        service: str,
        service_version: str,
        capture_mode: str,
        scenario: str,
        request: Mapping[str, Any],
        status_code: int,
        response_headers: Mapping[str, Any],
        response_body: bytes,
        recorded_at: str | None = None,
    ) -> ServiceFixture:
        normalized_service = _text(service, "service").casefold()
        normalized_version = _text(service_version, "service_version")
        normalized_capture = _text(capture_mode, "capture_mode").casefold()
        if normalized_capture not in {"live", "synthetic"}:
            raise ValueError("capture_mode must be live or synthetic")
        normalized_scenario = _text(scenario, "scenario").casefold()
        if normalized_scenario not in {"success", "failure"}:
            raise ValueError("scenario must be success or failure")
        canonical_request = _canonical_mapping(request, "request")
        canonical_headers = _canonical_mapping(response_headers, "response_headers")
        if isinstance(status_code, bool) or not isinstance(status_code, int):
            raise ValueError("status_code must be an integer")
        if not 100 <= status_code <= 599:
            raise ValueError("status_code must be within [100, 599]")
        if not isinstance(response_body, bytes):
            raise TypeError("response_body must be bytes")
        try:
            decoded_body = response_body.decode("utf-8")
        except UnicodeDecodeError:
            decoded_body = ""
        try:
            structured_body = json.loads(decoded_body)
        except json.JSONDecodeError:
            structured_body = decoded_body
        _assert_no_credentials(structured_body)
        body_digest = sha256(response_body).hexdigest()
        timestamp = _timestamp(recorded_at or utc_now(), "recorded_at")
        request_digest = digest_value(canonical_request)
        identity = {
            "schema": SERVICE_FIXTURE_SCHEMA,
            "service": normalized_service,
            "service_version": normalized_version,
            "capture_mode": normalized_capture,
            "scenario": normalized_scenario,
            "recorded_at": timestamp,
            "request_digest": request_digest,
            "status_code": status_code,
            "response_headers": canonical_headers,
            "response_body_sha256": body_digest,
        }
        return cls(
            fixture_id=digest_value(identity),
            service=normalized_service,
            service_version=normalized_version,
            capture_mode=normalized_capture,
            scenario=normalized_scenario,
            recorded_at=timestamp,
            request=canonical_request,
            request_digest=request_digest,
            status_code=status_code,
            response_headers=canonical_headers,
            response_body_sha256=body_digest,
            response_body_base64=base64.b64encode(response_body).decode("ascii"),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ServiceFixture:
        expected = {
            "schema",
            "fixture_id",
            "service",
            "service_version",
            "capture_mode",
            "scenario",
            "recorded_at",
            "request",
            "request_digest",
            "status_code",
            "response_headers",
            "response_body_sha256",
            "response_body_base64",
        }
        if set(payload) != expected:
            raise ValueError("service fixture has missing or unknown fields")
        if payload.get("schema") != SERVICE_FIXTURE_SCHEMA:
            raise ValueError(f"service fixture schema must be {SERVICE_FIXTURE_SCHEMA!r}")
        encoded = payload.get("response_body_base64")
        if not isinstance(encoded, str):
            raise ValueError("response_body_base64 must be a string")
        try:
            body = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise ValueError("response_body_base64 is not valid base64") from exc
        raw_status_code = payload.get("status_code")
        if isinstance(raw_status_code, bool) or not isinstance(raw_status_code, int):
            raise ValueError("status_code must be an integer")
        fixture = cls.create(
            service=_text(payload.get("service"), "service"),
            service_version=_text(payload.get("service_version"), "service_version"),
            capture_mode=_text(payload.get("capture_mode"), "capture_mode"),
            scenario=_text(payload.get("scenario"), "scenario"),
            request=_canonical_mapping(payload.get("request"), "request"),
            status_code=raw_status_code,
            response_headers=_canonical_mapping(
                payload.get("response_headers"), "response_headers"
            ),
            response_body=body,
            recorded_at=_text(payload.get("recorded_at"), "recorded_at"),
        )
        for name, expected_value in (
            ("fixture_id", fixture.fixture_id),
            ("request_digest", fixture.request_digest),
            ("response_body_sha256", fixture.response_body_sha256),
        ):
            stored = _text(payload.get(name), name).casefold()
            if not hmac.compare_digest(stored, expected_value):
                raise ValueError(f"service fixture {name} does not match its content")
        return fixture

    def response_body(self) -> bytes:
        return base64.b64decode(self.response_body_base64, validate=True)

    def replay(self, request: Mapping[str, Any]) -> tuple[int, Mapping[str, Any], bytes]:
        """Return the recorded response only for the exact canonical request."""

        request_digest = digest_value(_canonical_mapping(request, "request"))
        if not hmac.compare_digest(request_digest, self.request_digest):
            raise ValueError("replay request differs from the recorded fixture")
        return self.status_code, dict(self.response_headers), self.response_body()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "fixture_id": self.fixture_id,
            "service": self.service,
            "service_version": self.service_version,
            "capture_mode": self.capture_mode,
            "scenario": self.scenario,
            "recorded_at": self.recorded_at,
            "request": dict(self.request),
            "request_digest": self.request_digest,
            "status_code": self.status_code,
            "response_headers": dict(self.response_headers),
            "response_body_sha256": self.response_body_sha256,
            "response_body_base64": self.response_body_base64,
        }


def record_service_fixture(
    destination: str | Path,
    *,
    service: str,
    service_version: str,
    capture_mode: str,
    scenario: str,
    request: Mapping[str, Any],
    status_code: int,
    response_headers: Mapping[str, Any],
    response_body: bytes,
    recorded_at: str | None = None,
) -> ServiceFixture:
    fixture = ServiceFixture.create(
        service=service,
        service_version=service_version,
        capture_mode=capture_mode,
        scenario=scenario,
        request=request,
        status_code=status_code,
        response_headers=response_headers,
        response_body=response_body,
        recorded_at=recorded_at,
    )
    content = (stable_json(fixture.to_dict()) + "\n").encode("utf-8")
    atomic_create_binary(
        Path(destination).expanduser().resolve(), lambda handle: handle.write(content)
    )
    return fixture


def load_service_fixture(path: str | Path) -> ServiceFixture:
    source = Path(path).expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read service fixture {source}: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("service fixture must contain a JSON object")
    return ServiceFixture.from_dict(payload)


__all__ = [
    "SERVICE_FIXTURE_SCHEMA",
    "ServiceFixture",
    "load_service_fixture",
    "record_service_fixture",
]
