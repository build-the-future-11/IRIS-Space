"""Short-lived, signed principal assertions for authenticated review workflows."""

from __future__ import annotations

import hmac
import json
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from siderea.atomic import atomic_create_binary
from siderea.provenance import digest_value, stable_json

PRINCIPAL_ASSERTION_SCHEMA = "siderea.principal_assertion.v1"
PRINCIPAL_AUDIENCE = "siderea"
_ASSERTION_FIELDS = frozenset(
    {
        "issuer",
        "subject",
        "display_name",
        "roles",
        "issued_at",
        "expires_at",
        "audience",
        "assurance_level",
        "nonce",
    }
)


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _timestamp(value: Any, name: str) -> datetime:
    raw = _text(value, name)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information")
    return parsed


def _normalized_principal(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _key(value: bytes) -> bytes:
    if not isinstance(value, bytes):
        raise TypeError("principal assertion verification key must be bytes")
    if len(value) < 32:
        raise ValueError("principal assertion verification key must contain at least 32 bytes")
    return value


def _canonical_assertion(payload: Mapping[str, Any]) -> dict[str, Any]:
    if set(payload) != _ASSERTION_FIELDS:
        raise ValueError("principal assertion has missing or unknown fields")
    raw_roles = payload.get("roles")
    if isinstance(raw_roles, (str, bytes)) or not isinstance(raw_roles, Sequence):
        raise ValueError("principal assertion roles must be an array")
    roles = [_text(value, "principal role").casefold() for value in raw_roles]
    if not roles or len(set(roles)) != len(roles):
        raise ValueError("principal assertion roles must be non-empty and unique")
    issued = _timestamp(payload.get("issued_at"), "issued_at")
    expires = _timestamp(payload.get("expires_at"), "expires_at")
    if expires <= issued:
        raise ValueError("principal assertion expires_at must follow issued_at")
    if (expires - issued).total_seconds() > 86400:
        raise ValueError("principal assertion lifetime must not exceed 24 hours")
    audience = _text(payload.get("audience"), "audience")
    if audience != PRINCIPAL_AUDIENCE:
        raise ValueError(f"principal assertion audience must be {PRINCIPAL_AUDIENCE!r}")
    return {
        "issuer": _text(payload.get("issuer"), "issuer").casefold(),
        "subject": _text(payload.get("subject"), "subject"),
        "display_name": _text(payload.get("display_name"), "display_name"),
        "roles": sorted(roles),
        "issued_at": issued.isoformat(),
        "expires_at": expires.isoformat(),
        "audience": audience,
        "assurance_level": _text(payload.get("assurance_level"), "assurance_level").casefold(),
        "nonce": _text(payload.get("nonce"), "nonce"),
    }


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    principal_id: str
    display_name: str
    issuer: str
    subject: str
    roles: tuple[str, ...]
    assurance_level: str
    assertion_digest: str
    key_id: str
    expires_at: str
    assertion_envelope: Mapping[str, Any] = field(default_factory=dict)

    def require_current(self, role: str, trusted_keys: Sequence[str] = ()) -> None:
        """Recheck a previously verified assertion at the actual write boundary."""

        if datetime.now(UTC) >= _timestamp(self.expires_at, "expires_at"):
            raise ValueError("principal assertion has expired")
        if role not in self.roles:
            raise ValueError("principal assertion does not authorize the required role")
        if trusted_keys and self.key_id not in trusted_keys:
            raise ValueError("principal assertion key is not trusted by this policy")


def create_principal_assertion(
    destination: str | Path,
    assertion: Mapping[str, Any],
    *,
    signing_key: bytes,
) -> dict[str, Any]:
    """Create a short-lived HMAC assertion for a trusted authentication gateway.

    The shared key must be protected outside the repository. This format gives
    local SIDEREA a verifiable issuer/subject identity; it is not an IdP itself.
    """

    secret = _key(signing_key)
    canonical = _canonical_assertion(assertion)
    assertion_digest = digest_value(canonical)
    payload = {
        "schema": PRINCIPAL_ASSERTION_SCHEMA,
        "algorithm": "hmac-sha256",
        "key_id": sha256(secret).hexdigest(),
        "assertion": canonical,
        "assertion_digest": assertion_digest,
        "signature": hmac.new(secret, stable_json(canonical).encode("utf-8"), sha256).hexdigest(),
    }
    atomic_create_binary(
        Path(destination).expanduser().resolve(),
        lambda handle: handle.write((stable_json(payload) + "\n").encode("utf-8")),
    )
    return payload


def verify_principal_assertion(
    source: str | Path | Mapping[str, Any],
    *,
    verification_key: bytes,
    required_role: str | None = None,
    now: datetime | None = None,
) -> AuthenticatedPrincipal:
    """Verify signature, audience, freshness, role, and stable principal identity."""

    secret = _key(verification_key)
    if isinstance(source, Mapping):
        payload = dict(source)
    else:
        path = Path(source).expanduser().resolve()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read principal assertion {path}: {exc}") from exc
        if not isinstance(raw, Mapping):
            raise ValueError("principal assertion file must contain a JSON object")
        payload = dict(raw)
    expected_fields = {
        "schema",
        "algorithm",
        "key_id",
        "assertion",
        "assertion_digest",
        "signature",
    }
    if set(payload) != expected_fields:
        raise ValueError("principal assertion envelope has missing or unknown fields")
    if payload.get("schema") != PRINCIPAL_ASSERTION_SCHEMA:
        raise ValueError(f"principal assertion schema must be {PRINCIPAL_ASSERTION_SCHEMA!r}")
    if payload.get("algorithm") != "hmac-sha256":
        raise ValueError("principal assertion algorithm must be hmac-sha256")
    assertion = payload.get("assertion")
    if not isinstance(assertion, Mapping):
        raise ValueError("principal assertion payload must be an object")
    canonical = _canonical_assertion(assertion)
    assertion_digest = digest_value(canonical)
    stored_digest = _text(payload.get("assertion_digest"), "assertion_digest").casefold()
    if not hmac.compare_digest(stored_digest, assertion_digest):
        raise ValueError("principal assertion digest differs from its payload")
    expected_key_id = sha256(secret).hexdigest()
    if not hmac.compare_digest(_text(payload.get("key_id"), "key_id"), expected_key_id):
        raise ValueError("principal assertion was issued under a different key")
    expected_signature = hmac.new(
        secret, stable_json(canonical).encode("utf-8"), sha256
    ).hexdigest()
    if not hmac.compare_digest(
        _text(payload.get("signature"), "signature").casefold(), expected_signature
    ):
        raise ValueError("principal assertion signature is invalid")
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("principal assertion verification time must include a timezone")
    issued = _timestamp(canonical["issued_at"], "issued_at")
    expires = _timestamp(canonical["expires_at"], "expires_at")
    if instant < issued:
        raise ValueError("principal assertion is not yet valid")
    if instant >= expires:
        raise ValueError("principal assertion has expired")
    roles = tuple(str(value) for value in canonical["roles"])
    if required_role is not None and required_role.strip().casefold() not in roles:
        raise ValueError("principal assertion does not authorize the required role")
    issuer = str(canonical["issuer"])
    subject = str(canonical["subject"])
    return AuthenticatedPrincipal(
        principal_id=f"{issuer}::{_normalized_principal(subject)}",
        display_name=str(canonical["display_name"]),
        issuer=issuer,
        subject=subject,
        roles=roles,
        assurance_level=str(canonical["assurance_level"]),
        assertion_digest=assertion_digest,
        key_id=expected_key_id,
        expires_at=expires.isoformat(),
        assertion_envelope=payload,
    )


__all__ = [
    "PRINCIPAL_ASSERTION_SCHEMA",
    "PRINCIPAL_AUDIENCE",
    "AuthenticatedPrincipal",
    "create_principal_assertion",
    "verify_principal_assertion",
]
