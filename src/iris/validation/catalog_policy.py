"""Convert raw SIMBAD evidence into a conservative scientific veto decision."""

from __future__ import annotations

import hmac
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from iris.clients.base import ServiceResult
from iris.provenance import CheckProvenance, CheckStatus, digest_value

VARIABLE_MARKERS = (
    "variable",
    "mira",
    "cepheid",
    "rr lyr",
    "rrlyr",
    "eclips",
    "pulsating",
    "long-period variable",
)
VARIABLE_CODES = {"v*", "v*?", "cv*", "lpv*", "pulsv*", "eclbin", "nova"}
STELLAR_MARKERS = ("star", "stellar", "yso", "white dwarf")
HOST_CODES = {
    "g",
    "galaxy",
    "agn",
    "qso",
    "quasar",
    "seyfert",
    "blazar",
    "bllac",
    "radiog",
    "emg",
    "ginpair",
    "gincluster",
}


@dataclass(frozen=True)
class CatalogInterpretation:
    check: CheckProvenance
    manual_review_required: bool
    context_labels: tuple[str, ...]
    reason: str


def _field(record: Mapping[str, object], names: Sequence[str]) -> str:
    for name in names:
        value = str(record.get(name, "")).strip()
        if value and value.lower() not in {"nan", "none", "--"}:
            return value
    return ""


def _object_category(object_type: str) -> str:
    """Conservatively map a SIMBAD OTYPE label to veto/host/unknown.

    SIMBAD mixes compact codes (for example ``G`` and ``V*``) with human
    labels.  Exact matching for one-character codes avoids the old ``"g" in
    otype`` bug, which could classify almost any label containing that letter
    as a galaxy.
    """

    normalized = " ".join(object_type.casefold().replace("_", " ").split())
    compact = normalized.replace(" ", "")
    if normalized in VARIABLE_CODES or compact in VARIABLE_CODES:
        return "veto"
    if any(marker in normalized for marker in VARIABLE_MARKERS):
        return "veto"
    if normalized in HOST_CODES or compact in HOST_CODES:
        return "host"
    if any(marker in normalized for marker in STELLAR_MARKERS) or "*" in normalized:
        return "veto"
    return "unknown"


def _invalid_simbad_result(original: CheckProvenance, reason: str) -> CatalogInterpretation:
    check = CheckProvenance(
        service="simbad",
        status=CheckStatus.ERROR,
        checked_at=original.checked_at,
        expires_at=original.expires_at,
        query=original.query,
        error=reason,
        attempts=original.attempts,
        latency_ms=original.latency_ms,
        response_digest=original.response_digest,
        service_version=original.service_version,
    )
    return CatalogInterpretation(check, False, (), reason)


def interpret_simbad(result: ServiceResult[list[dict[str, object]]]) -> CatalogInterpretation:
    original = result.provenance
    if original.service != "simbad":
        return _invalid_simbad_result(original, "catalogue result is not identified as SIMBAD")
    if original.status in {
        CheckStatus.ERROR,
        CheckStatus.DISABLED,
        CheckStatus.STALE,
        CheckStatus.PENDING,
    }:
        return CatalogInterpretation(original, False, (), "SIMBAD did not complete")

    raw_records = result.value
    if raw_records is None:
        records: list[dict[str, object]] = []
    elif isinstance(raw_records, (str, bytes, Mapping)) or not isinstance(raw_records, Sequence):
        if original.status is CheckStatus.MATCH:
            return CatalogInterpretation(
                original,
                False,
                (),
                "malformed SIMBAD match retained as a conservative veto",
            )
        return _invalid_simbad_result(original, "SIMBAD supplied a malformed result array")
    elif any(not isinstance(record, Mapping) for record in raw_records):
        if original.status is CheckStatus.MATCH:
            return CatalogInterpretation(
                original,
                False,
                (),
                "malformed SIMBAD match retained as a conservative veto",
            )
        return _invalid_simbad_result(original, "SIMBAD supplied a malformed result row")
    else:
        records = [dict(record) for record in raw_records]

    try:
        expected_digest = digest_value(records)
    except (TypeError, ValueError) as exc:
        if original.status is CheckStatus.MATCH:
            return CatalogInterpretation(
                original,
                False,
                (),
                "non-canonical SIMBAD match retained as a conservative veto",
            )
        return _invalid_simbad_result(
            original,
            f"SIMBAD response is not canonical JSON: {exc}",
        )
    if not hmac.compare_digest(original.response_digest, expected_digest):
        if original.status is CheckStatus.MATCH:
            return CatalogInterpretation(
                original,
                False,
                (),
                "SIMBAD response digest mismatch retained as a conservative veto",
            )
        return _invalid_simbad_result(original, "SIMBAD response digest does not match its records")
    if not records:
        if original.status is CheckStatus.MATCH:
            inconsistent = CheckProvenance(
                service="simbad",
                status=CheckStatus.ERROR,
                checked_at=original.checked_at,
                expires_at=original.expires_at,
                query=original.query,
                error="SIMBAD result claimed a match but supplied no records",
                attempts=original.attempts,
                latency_ms=original.latency_ms,
                response_digest=original.response_digest,
                service_version=original.service_version,
            )
            return CatalogInterpretation(inconsistent, False, (), "inconsistent SIMBAD result")
        clear = CheckProvenance(
            service="simbad",
            status=CheckStatus.CLEAR,
            checked_at=original.checked_at,
            expires_at=original.expires_at,
            query=original.query,
            attempts=original.attempts,
            latency_ms=original.latency_ms,
            response_digest=original.response_digest,
            service_version=original.service_version,
        )
        return CatalogInterpretation(clear, False, (), "no SIMBAD counterpart")

    vetoes: list[str] = []
    hosts: list[str] = []
    unknown: list[str] = []
    for record in records:
        object_id = _field(record, ("MAIN_ID", "main_id")) or "unnamed SIMBAD source"
        object_type = _field(record, ("OTYPE", "otype", "OTYPE_V")).lower()
        label = f"{object_id} ({object_type or 'unknown type'})"
        category = _object_category(object_type)
        if category == "veto":
            vetoes.append(label)
        elif category == "host":
            hosts.append(label)
        else:
            unknown.append(label)

    if vetoes:
        check = CheckProvenance(
            service="simbad",
            status=CheckStatus.MATCH,
            checked_at=original.checked_at,
            expires_at=original.expires_at,
            query=original.query,
            matches=tuple(vetoes),
            attempts=original.attempts,
            latency_ms=original.latency_ms,
            response_digest=original.response_digest,
            service_version=original.service_version,
        )
        return CatalogInterpretation(
            check,
            False,
            tuple(hosts + unknown),
            "known stellar/variable counterpart",
        )

    check = CheckProvenance(
        service="simbad",
        status=CheckStatus.CLEAR,
        checked_at=original.checked_at,
        expires_at=original.expires_at,
        query=original.query,
        attempts=original.attempts,
        latency_ms=original.latency_ms,
        response_digest=original.response_digest,
        service_version=original.service_version,
    )
    context = tuple(hosts + unknown)
    return CatalogInterpretation(
        check,
        bool(context),
        context,
        "host/unknown counterpart requires association review" if context else "clear",
    )
