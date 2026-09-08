"""Bind completed external-check evidence to one candidate and query policy.

Catalogue ``CLEAR`` results are safe only when their provenance proves that the
right candidate, sky position, search radius, and (for SkyBoT) epoch were
checked.  Invalid clear evidence is downgraded to ``ERROR`` so every downstream
gate fails closed.  Positive ``MATCH`` results remain conservative vetoes even
when old producers omitted binding metadata.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any

from siderea.evidence_context import serialized_verification_context
from siderea.provenance import CheckProvenance, CheckStatus, digest_value

DEFAULT_REQUIRED_RADII_ARCSEC: Mapping[str, float] = {
    "tns": 5.0,
    "skybot": 10.0,
    "simbad": 3.0,
    "vsx": 3.0,
}

_CONE_SERVICES = frozenset(DEFAULT_REQUIRED_RADII_ARCSEC)
_IDENTITY_KEYS = (
    "candidate_id",
    "internal_name_checked",
    "internal_name",
    "source_id",
    "object_id",
    "objectId",
    "oid",
)
_TNS_TWO_STAGE_VERSION = "tns-two-stage-search.v1"
_TNS_TWO_STAGE_METHODS = ("internal_name", "cone")


@dataclass(frozen=True, slots=True)
class EvidenceBindingContext:
    """Expected candidate identity and policy for validating completed checks."""

    candidate_id: str
    ra_deg: float
    dec_deg: float
    max_ttl_hours: float
    required_radii_arcsec: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_REQUIRED_RADII_ARCSEC)
    )
    skybot_reference_mjds: tuple[float, ...] = ()
    position_tolerance_arcsec: float = 0.1
    skybot_epoch_tolerance_days: float = 1.0e-3

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str):
            raise TypeError("candidate_id must be a string")
        candidate_id = self.candidate_id.strip()
        if not candidate_id:
            raise ValueError("candidate_id must not be empty")
        if isinstance(self.ra_deg, bool) or not isinstance(self.ra_deg, (int, float)):
            raise TypeError("ra_deg must be a number")
        if not math.isfinite(self.ra_deg) or not 0 <= self.ra_deg < 360:
            raise ValueError("ra_deg must be finite and within [0, 360)")
        if isinstance(self.dec_deg, bool) or not isinstance(self.dec_deg, (int, float)):
            raise TypeError("dec_deg must be a number")
        if not math.isfinite(self.dec_deg) or not -90 <= self.dec_deg <= 90:
            raise ValueError("dec_deg must be finite and within [-90, 90]")
        if isinstance(self.max_ttl_hours, bool) or not isinstance(self.max_ttl_hours, (int, float)):
            raise TypeError("max_ttl_hours must be a number")
        if not math.isfinite(self.max_ttl_hours) or self.max_ttl_hours <= 0:
            raise ValueError("max_ttl_hours must be finite and positive")
        if isinstance(self.position_tolerance_arcsec, bool) or not isinstance(
            self.position_tolerance_arcsec, (int, float)
        ):
            raise TypeError("position_tolerance_arcsec must be a number")
        if not math.isfinite(self.position_tolerance_arcsec) or self.position_tolerance_arcsec <= 0:
            raise ValueError("position_tolerance_arcsec must be finite and positive")
        if isinstance(self.skybot_epoch_tolerance_days, bool) or not isinstance(
            self.skybot_epoch_tolerance_days, (int, float)
        ):
            raise TypeError("skybot_epoch_tolerance_days must be a number")
        if (
            not math.isfinite(self.skybot_epoch_tolerance_days)
            or self.skybot_epoch_tolerance_days < 0
        ):
            raise ValueError("skybot_epoch_tolerance_days must be finite and non-negative")

        if not isinstance(self.required_radii_arcsec, Mapping):
            raise TypeError("required_radii_arcsec must be a mapping")
        radii: dict[str, float] = {}
        for raw_service, raw_radius in self.required_radii_arcsec.items():
            if not isinstance(raw_service, str):
                raise TypeError("required-radius service names must be strings")
            service = str(raw_service).strip().casefold()
            if isinstance(raw_radius, bool) or not isinstance(raw_radius, (int, float)):
                raise TypeError("required radii must be numbers")
            radius = float(raw_radius)
            if not service:
                raise ValueError("required-radius service names must not be empty")
            if service in radii:
                raise ValueError("required-radius service names must be unique after normalization")
            if not math.isfinite(radius) or radius <= 0:
                raise ValueError("required radii must be finite and positive")
            radii[service] = radius

        references_list: list[float] = []
        for raw_value in self.skybot_reference_mjds:
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                raise TypeError("SkyBoT reference MJDs must be numbers")
            value = float(raw_value)
            if not math.isfinite(value) or value < 0:
                raise ValueError("SkyBoT reference MJDs must be finite and non-negative")
            references_list.append(value)
        references = tuple(sorted(set(references_list)))

        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "ra_deg", float(self.ra_deg))
        object.__setattr__(self, "dec_deg", float(self.dec_deg))
        object.__setattr__(self, "max_ttl_hours", float(self.max_ttl_hours))
        object.__setattr__(self, "required_radii_arcsec", MappingProxyType(radii))
        object.__setattr__(self, "skybot_reference_mjds", references)
        object.__setattr__(self, "position_tolerance_arcsec", float(self.position_tolerance_arcsec))
        object.__setattr__(
            self,
            "skybot_epoch_tolerance_days",
            float(self.skybot_epoch_tolerance_days),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the policy fields needed to reproduce reporting preflight."""

        return {
            "candidate_id": self.candidate_id,
            "ra_deg": self.ra_deg,
            "dec_deg": self.dec_deg,
            "max_ttl_hours": self.max_ttl_hours,
            "required_radii_arcsec": dict(self.required_radii_arcsec),
            "skybot_reference_mjds": list(self.skybot_reference_mjds),
            "position_tolerance_arcsec": self.position_tolerance_arcsec,
            "skybot_epoch_tolerance_days": self.skybot_epoch_tolerance_days,
        }


def _invalid_clear(check: CheckProvenance, reason: str) -> CheckProvenance:
    return replace(
        check,
        status=CheckStatus.ERROR,
        matches=(),
        error=f"evidence binding failed: {reason}",
    )


def _query_number(query: Mapping[str, Any], *names: str) -> float | None:
    values: list[tuple[str, float]] = []
    for name in names:
        if name not in query:
            continue
        raw_value = query[name]
        if isinstance(raw_value, bool):
            raise ValueError(f"query field {name!r} must be a finite number")
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"query field {name!r} must be a finite number") from exc
        if not math.isfinite(value):
            raise ValueError(f"query field {name!r} must be a finite number")
        values.append((name, value))
    if not values:
        return None
    first_name, first_value = values[0]
    if any(
        not math.isclose(value, first_value, rel_tol=0.0, abs_tol=1.0e-12)
        for _, value in values[1:]
    ):
        aliases = ", ".join(name for name, _ in values)
        raise ValueError(f"query has conflicting numeric aliases for {first_name!r}: {aliases}")
    return first_value


def _query_radius_arcsec(query: Mapping[str, Any]) -> float | None:
    direct = _query_number(query, "radius_arcsec", "radiusArcsec", "radius_arcseconds")
    generic = _query_number(query, "radius")
    converted: float | None = None
    if generic is not None:
        raw_units = query.get("units", "arcsec")
        if not isinstance(raw_units, str):
            raise ValueError("query radius units must be a string")
        units = raw_units.strip().casefold()
        if units in {"arcsec", "arcsecond", "arcseconds", '"'}:
            converted = generic
        elif units in {"arcmin", "arcminute", "arcminutes", "'"}:
            converted = generic * 60.0
        elif units in {"deg", "degree", "degrees"}:
            converted = generic * 3600.0
        else:
            raise ValueError("query radius has unsupported units")
    if (
        direct is not None
        and converted is not None
        and not math.isclose(
            direct,
            converted,
            rel_tol=0.0,
            abs_tol=1.0e-9,
        )
    ):
        raise ValueError("query has conflicting radius aliases")
    return direct if direct is not None else converted


def _query_mjds(query: Mapping[str, Any]) -> tuple[float, ...]:
    raw_values = query.get("mjds")
    values: list[float] = []
    if "mjds" in query:
        if not isinstance(raw_values, Iterable) or isinstance(raw_values, (str, bytes, Mapping)):
            raise ValueError("query mjds must be an array of finite non-negative numbers")
        for raw in raw_values:
            if isinstance(raw, bool):
                raise ValueError("query mjds must contain finite non-negative numbers")
            try:
                value = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("query mjds must contain finite non-negative numbers") from exc
            if not math.isfinite(value) or value < 0:
                raise ValueError("query mjds must contain finite non-negative numbers")
            values.append(value)
    single = _query_number(query, "mjd", "MJD", "peak_mjd", "epoch_mjd")
    if single is not None:
        if single < 0:
            raise ValueError("query MJD must be non-negative")
        values.append(single)
    if len(values) != len(set(values)):
        raise ValueError("query MJDs must be unique")
    return tuple(sorted(values))


def _uncovered_reference_mjds(
    references: tuple[float, ...],
    queries: tuple[float, ...],
    tolerance_days: float,
) -> list[float]:
    """Find epochs without a distinct query epoch using ordered matching."""

    uncovered: list[float] = []
    query_index = 0
    for reference in references:
        while query_index < len(queries) and queries[query_index] < reference - tolerance_days:
            query_index += 1
        if query_index >= len(queries) or queries[query_index] > reference + tolerance_days:
            uncovered.append(reference)
            continue
        query_index += 1
    return uncovered


def _separation_arcsec(ra_a: float, dec_a: float, ra_b: float, dec_b: float) -> float:
    ra_a_rad, dec_a_rad = math.radians(ra_a), math.radians(dec_a)
    ra_b_rad, dec_b_rad = math.radians(ra_b), math.radians(dec_b)
    cosine = math.sin(dec_a_rad) * math.sin(dec_b_rad) + math.cos(dec_a_rad) * math.cos(
        dec_b_rad
    ) * math.cos(ra_a_rad - ra_b_rad)
    return math.degrees(math.acos(min(1.0, max(-1.0, cosine)))) * 3600.0


def bind_completed_check(
    check: CheckProvenance,
    context: EvidenceBindingContext,
) -> CheckProvenance:
    """Validate one completed check, downgrading an unbound ``CLEAR`` result.

    A ``MATCH`` is returned unchanged: discarding a positive association because
    of incomplete legacy metadata could make a known object appear novel.
    """

    if check.status is CheckStatus.MATCH:
        return check
    if check.expires_at:
        checked = datetime.fromisoformat(check.checked_at)
        expires = datetime.fromisoformat(check.expires_at)
        maximum_age = timedelta(hours=context.max_ttl_hours)
        if expires - checked > maximum_age + timedelta(seconds=1):
            return replace(
                check,
                status=CheckStatus.STALE,
                matches=(),
                error=(
                    f"evidence TTL exceeds configured maximum of {context.max_ttl_hours:g} hours"
                ),
            )
    if check.status is not CheckStatus.CLEAR:
        return check

    integrity_error = check.clear_integrity_error
    if integrity_error is not None:
        return _invalid_clear(check, integrity_error)

    if check.service == "tns":
        if check.service_version != _TNS_TWO_STAGE_VERSION:
            return _invalid_clear(
                check,
                f"TNS clearance requires service_version {_TNS_TWO_STAGE_VERSION!r}",
            )
        raw_methods = check.query.get("methods")
        if not isinstance(raw_methods, Iterable) or isinstance(raw_methods, (str, bytes, Mapping)):
            return _invalid_clear(check, "TNS clearance lacks two-stage method coverage")
        methods = tuple(str(method).strip().casefold() for method in raw_methods)
        if methods != _TNS_TWO_STAGE_METHODS:
            return _invalid_clear(
                check,
                "TNS clearance must cover internal-name then position-cone search",
            )
        if check.query.get("coverage_policy") != "internal_name_and_position_cone":
            return _invalid_clear(check, "TNS clearance has the wrong coverage policy")
        if (
            check.query.get("candidate_id") != context.candidate_id
            or check.query.get("internal_name_checked") != context.candidate_id
        ):
            return _invalid_clear(check, "TNS two-stage identity does not match candidate_id")

    bound_names = [str(check.query[name]).strip() for name in _IDENTITY_KEYS if name in check.query]
    if check.service == "tns" and not bound_names:
        return _invalid_clear(check, "TNS cone result has no candidate identity")
    if any(name != context.candidate_id for name in bound_names):
        return _invalid_clear(check, "query identity does not match candidate_id")

    try:
        query_ra = _query_number(check.query, "ra", "RA", "ra_deg", "meanra", "ramean")
        query_dec = _query_number(
            check.query,
            "dec",
            "DEC",
            "dec_deg",
            "meandec",
            "decmean",
        )
    except ValueError as exc:
        return _invalid_clear(check, str(exc))
    if query_ra is None or query_dec is None:
        return _invalid_clear(check, "completed cone check has no finite sky position")
    if not 0 <= query_ra < 360 or not -90 <= query_dec <= 90:
        return _invalid_clear(check, "completed cone check has an invalid sky position")
    if (
        _separation_arcsec(context.ra_deg, context.dec_deg, query_ra, query_dec)
        > context.position_tolerance_arcsec
    ):
        return _invalid_clear(
            check,
            "query position differs from the candidate by more than "
            f"{context.position_tolerance_arcsec:g} arcsec",
        )

    required_radius = context.required_radii_arcsec.get(check.service)
    if check.service in _CONE_SERVICES and required_radius is None:
        return _invalid_clear(check, "no required query-radius policy is available")
    if required_radius is not None:
        try:
            query_radius = _query_radius_arcsec(check.query)
        except ValueError as exc:
            return _invalid_clear(check, str(exc))
        if query_radius is None or query_radius + 1.0e-9 < required_radius:
            return _invalid_clear(
                check,
                f"query radius is smaller than required {required_radius:g} arcsec",
            )

    if check.service == "skybot":
        try:
            query_mjds = _query_mjds(check.query)
        except ValueError as exc:
            return _invalid_clear(check, str(exc))
        if not query_mjds:
            return _invalid_clear(check, "SkyBoT result has no valid observation epoch")
        if not context.skybot_reference_mjds:
            return _invalid_clear(check, "candidate has no reference epochs for SkyBoT binding")
        uncovered = _uncovered_reference_mjds(
            context.skybot_reference_mjds,
            query_mjds,
            context.skybot_epoch_tolerance_days,
        )
        if uncovered:
            return _invalid_clear(
                check,
                "SkyBoT query does not cover every candidate reference epoch within "
                f"{context.skybot_epoch_tolerance_days:g} day; uncovered={uncovered[:5]}",
            )
    return check


def bind_completed_checks(
    checks: Iterable[CheckProvenance],
    context: EvidenceBindingContext,
) -> tuple[CheckProvenance, ...]:
    """Apply :func:`bind_completed_check` to an evidence collection."""

    return tuple(bind_completed_check(check, context) for check in checks)


def preflight_digest(
    *,
    context: EvidenceBindingContext,
    checks: Iterable[CheckProvenance],
    quality_passed: bool,
    manual_review_required: bool,
    mandatory_services: Iterable[str],
    required_reviewers: int,
    verification_context: Mapping[str, Any] | None = None,
) -> str:
    """Hash every scientific input that reporting preflight is allowed to use."""

    if not isinstance(quality_passed, bool) or not isinstance(manual_review_required, bool):
        raise TypeError("quality_passed and manual_review_required must be boolean")
    service_values = tuple(mandatory_services)
    if any(not isinstance(service, str) for service in service_values):
        raise TypeError("mandatory service names must be strings")
    if (
        isinstance(required_reviewers, bool)
        or not isinstance(required_reviewers, int)
        or required_reviewers < 1
    ):
        raise TypeError("required_reviewers must be a positive integer")

    required = tuple(service.strip().casefold() for service in service_values)
    if not required or any(not service for service in required):
        raise ValueError("mandatory_services must contain at least one non-empty service")
    if len(set(required)) != len(required):
        raise ValueError("mandatory_services must be unique after normalization")
    context_evidence = serialized_verification_context(
        verification_context,
        manual_review_required=manual_review_required,
        expected_skybot_reference_mjds=context.skybot_reference_mjds,
    )
    check_payloads: list[dict[str, Any]] = []
    for check in checks:
        payload = check.to_dict()
        # Timing for an unfinished attempt is acquisition bookkeeping, not
        # scientific evidence.  Normalizing it keeps a candidate version stable
        # across identical offline runs while CLEAR/MATCH timestamps remain
        # fully bound for freshness decisions.
        if not check.completed:
            payload["checked_at"] = None
            payload["expires_at"] = None
            payload["latency_ms"] = None
        check_payloads.append(payload)
    check_payloads.sort(
        key=lambda payload: (
            str(payload["service"]),
            str(payload["checked_at"]),
            digest_value(payload),
        )
    )
    return digest_value(
        {
            "schema": "siderea.reporting_preflight.v2",
            "binding_context": context.to_dict(),
            "checks": check_payloads,
            "quality_passed": quality_passed,
            "manual_review_required": manual_review_required,
            "verification_context": context_evidence,
            "mandatory_services": required,
            "review_policy": {"required_reviewers": required_reviewers},
        }
    )


__all__ = [
    "DEFAULT_REQUIRED_RADII_ARCSEC",
    "EvidenceBindingContext",
    "bind_completed_check",
    "bind_completed_checks",
    "preflight_digest",
]
