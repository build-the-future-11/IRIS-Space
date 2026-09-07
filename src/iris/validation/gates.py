"""Fail-closed reportability decisions.

Machine-learned scores may prioritize review, but they never bypass these
evidence-completeness and known-object gates.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from iris.provenance import CheckProvenance, CheckStatus, digest_value

MANDATORY_SERVICES = ("tns", "skybot", "simbad", "vsx")


class GateDecision(StrEnum):
    REPORTABLE = "reportable"
    REJECT_KNOWN_OBJECT = "reject_known_object"
    BLOCK_INCOMPLETE_EVIDENCE = "block_incomplete_evidence"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"
    REJECT_QUALITY = "reject_quality"


@dataclass(frozen=True)
class GateOutcome:
    decision: GateDecision
    reasons: tuple[str, ...]
    missing_services: tuple[str, ...] = ()
    matched_services: tuple[str, ...] = ()

    @property
    def reportable(self) -> bool:
        return self.decision is GateDecision.REPORTABLE


def evaluate_reportability(
    checks: Iterable[CheckProvenance],
    *,
    quality_passed: bool,
    manual_review_required: bool = False,
    mandatory_services: Iterable[str] = MANDATORY_SERVICES,
    at: datetime | None = None,
) -> GateOutcome:
    if not isinstance(quality_passed, bool) or not isinstance(manual_review_required, bool):
        raise TypeError("quality_passed and manual_review_required must be boolean")
    required_values = tuple(mandatory_services)
    if any(not isinstance(service, str) for service in required_values):
        raise TypeError("mandatory service names must be strings")
    all_checks: dict[str, list[CheckProvenance]] = {}
    for check in checks:
        all_checks.setdefault(check.service, []).append(check)
    by_service_mutable: dict[str, CheckProvenance] = {}
    conflicting_services: set[str] = set()
    for service, service_checks in all_checks.items():
        latest_time = max(datetime.fromisoformat(check.checked_at) for check in service_checks)
        latest = tuple(
            check
            for check in service_checks
            if datetime.fromisoformat(check.checked_at) == latest_time
        )
        fingerprints = {digest_value(check.to_dict()) for check in latest}
        if len(fingerprints) > 1:
            conflicting_services.add(service)
        by_service_mutable[service] = min(
            latest,
            key=lambda check: digest_value(check.to_dict()),
        )
    by_service: Mapping[str, CheckProvenance] = by_service_mutable
    required = tuple(
        dict.fromkeys(service.strip().casefold() for service in required_values if service.strip())
    )
    if not required:
        return GateOutcome(
            GateDecision.BLOCK_INCOMPLETE_EVIDENCE,
            ("mandatory service policy is empty",),
            missing_services=("mandatory_services",),
        )
    matched = tuple(
        service
        for service in required
        if any(check.status is CheckStatus.MATCH for check in all_checks.get(service, ()))
    )
    if matched:
        reasons = tuple(
            f"{service} match: "
            + (
                ", ".join(
                    dict.fromkeys(
                        name
                        for check in all_checks[service]
                        if check.status is CheckStatus.MATCH
                        for name in check.matches
                    )
                )
                or "unnamed object"
            )
            for service in matched
        )
        return GateOutcome(
            GateDecision.REJECT_KNOWN_OBJECT,
            reasons,
            matched_services=matched,
        )

    instant = at or datetime.now(UTC)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("at must include timezone information")
    freshness = {service: check.is_fresh(now=instant) for service, check in by_service.items()}
    integrity = {service: check.clear_integrity_error for service, check in by_service.items()}
    incomplete = tuple(
        service
        for service in required
        if service not in by_service
        or service in conflicting_services
        or by_service[service].status is not CheckStatus.CLEAR
        or integrity[service] is not None
        or not freshness[service]
    )
    if incomplete:
        reasons_list: list[str] = []
        for service in incomplete:
            if service not in by_service:
                reasons_list.append(f"{service}: missing")
                continue
            if service in conflicting_services:
                reasons_list.append(f"{service}: conflicting records at latest timestamp")
                continue
            check = by_service[service]
            integrity_error = integrity[service]
            detail = (
                integrity_error
                if integrity_error is not None
                else "stale or missing TTL"
                if not freshness[service]
                else check.status.value
            )
            suffix = f" ({check.error})" if check.error else ""
            reasons_list.append(f"{service}: {detail}{suffix}")
        reasons = tuple(reasons_list)
        return GateOutcome(
            GateDecision.BLOCK_INCOMPLETE_EVIDENCE,
            reasons,
            missing_services=incomplete,
        )

    if not quality_passed:
        return GateOutcome(GateDecision.REJECT_QUALITY, ("candidate quality gate failed",))
    if manual_review_required:
        return GateOutcome(
            GateDecision.NEEDS_MANUAL_REVIEW,
            ("candidate requires explicit scientific adjudication",),
        )
    return GateOutcome(GateDecision.REPORTABLE, ("all mandatory checks are clear",))
