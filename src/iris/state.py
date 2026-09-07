"""Candidate lifecycle and fail-closed evidence gating."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime

from iris.domain import Candidate, CandidateState, CheckStatus, utc_now


class TransitionError(ValueError):
    """Raised when a candidate lifecycle transition is not permitted."""


class ReportabilityError(ValueError):
    """Raised when required evidence does not support reporting."""


_ALLOWED_TRANSITIONS: dict[CandidateState, frozenset[CandidateState]] = {
    CandidateState.INGESTED: frozenset(
        {CandidateState.ENRICHING, CandidateState.REJECTED, CandidateState.ERROR}
    ),
    CandidateState.ENRICHING: frozenset(
        {
            CandidateState.READY_FOR_SCREENING,
            CandidateState.NEEDS_REVIEW,
            CandidateState.REJECTED,
            CandidateState.ERROR,
        }
    ),
    CandidateState.READY_FOR_SCREENING: frozenset(
        {CandidateState.SCREENING, CandidateState.REJECTED, CandidateState.ERROR}
    ),
    CandidateState.SCREENING: frozenset(
        {
            CandidateState.NEEDS_REVIEW,
            CandidateState.REJECTED,
            CandidateState.REPORTABLE,
            CandidateState.ERROR,
        }
    ),
    CandidateState.NEEDS_REVIEW: frozenset(
        {
            CandidateState.SCREENING,
            CandidateState.REJECTED,
            CandidateState.REPORTABLE,
            CandidateState.ERROR,
        }
    ),
    CandidateState.REJECTED: frozenset({CandidateState.CLOSED}),
    CandidateState.REPORTABLE: frozenset(
        {
            CandidateState.APPROVED,
            CandidateState.NEEDS_REVIEW,
            CandidateState.REJECTED,
            CandidateState.ERROR,
        }
    ),
    CandidateState.APPROVED: frozenset(
        {
            CandidateState.REPORTED,
            CandidateState.NEEDS_REVIEW,
            CandidateState.REJECTED,
            CandidateState.ERROR,
        }
    ),
    CandidateState.REPORTED: frozenset(
        {CandidateState.FOLLOW_UP, CandidateState.CLOSED, CandidateState.ERROR}
    ),
    CandidateState.FOLLOW_UP: frozenset({CandidateState.CLOSED, CandidateState.ERROR}),
    CandidateState.ERROR: frozenset(
        {
            CandidateState.ENRICHING,
            CandidateState.SCREENING,
            CandidateState.NEEDS_REVIEW,
            CandidateState.CLOSED,
        }
    ),
    CandidateState.CLOSED: frozenset(),
}


def allowed_transitions(state: CandidateState) -> frozenset[CandidateState]:
    """Return valid next states without exposing the mutable transition table."""

    return _ALLOWED_TRANSITIONS[state]


def can_transition(current: CandidateState, target: CandidateState) -> bool:
    return current == target or target in _ALLOWED_TRANSITIONS[current]


def transition_candidate(
    candidate: Candidate,
    target: CandidateState,
    *,
    at: datetime | None = None,
    required_checks: Iterable[str] | None = None,
    approval_recorded: bool = False,
    reporting_preflight_passed: bool = False,
) -> Candidate:
    """Return a candidate in ``target`` or raise for an invalid transition.

    Entering a safety-sensitive state requires explicit evidence/authorization;
    the lifecycle graph alone is never a reportability gate.
    """

    if candidate.state == target:
        return candidate
    if not can_transition(candidate.state, target):
        raise TransitionError(
            f"cannot transition {candidate.candidate_id} from "
            f"{candidate.state.value} to {target.value}"
        )
    if target is CandidateState.REPORTABLE:
        if required_checks is None:
            raise ReportabilityError("required_checks are needed to enter reportable state")
        require_reportable(candidate, required_checks, at=at)
    if target is CandidateState.APPROVED and approval_recorded is not True:
        raise ReportabilityError("independent approval is needed to enter approved state")
    if target is CandidateState.REPORTED and reporting_preflight_passed is not True:
        raise ReportabilityError("reporting preflight is needed to enter reported state")
    return replace(candidate, state=target, updated_at=at or utc_now())


@dataclass(frozen=True, slots=True)
class ReportabilityAssessment:
    """Structured explanation of a fail-closed reporting decision."""

    reportable: bool
    missing_checks: tuple[str, ...] = ()
    non_passing_checks: tuple[str, ...] = ()
    stale_checks: tuple[str, ...] = ()

    @property
    def reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if self.missing_checks:
            reasons.append("missing: " + ", ".join(self.missing_checks))
        if self.non_passing_checks:
            reasons.append("not passing: " + ", ".join(self.non_passing_checks))
        if self.stale_checks:
            reasons.append("stale: " + ", ".join(self.stale_checks))
        return tuple(reasons)


def assess_reportability(
    candidate: Candidate,
    required_checks: Iterable[str],
    *,
    at: datetime | None = None,
) -> ReportabilityAssessment:
    """Require a fresh explicit PASS from every configured check.

    Empty required-check configuration is itself treated as missing evidence,
    preventing a configuration mistake from opening the reporting gate.
    """

    instant = at or utc_now()
    required = tuple(
        dict.fromkeys(name.strip().casefold() for name in required_checks if name.strip())
    )
    if not required:
        return ReportabilityAssessment(False, missing_checks=("required_checks",))

    missing: list[str] = []
    non_passing: list[str] = []
    stale: list[str] = []
    for name in required:
        matching = tuple(item for item in candidate.evidence if item.check_name == name)
        result = candidate.latest_evidence(name)
        if result is None:
            missing.append(name)
        elif any(item.checked_at == result.checked_at and item != result for item in matching):
            non_passing.append(f"{name}=conflicting_latest_evidence")
        elif result.expires_at is None or not result.is_fresh(instant):
            stale.append(name)
        elif result.status is not CheckStatus.PASS:
            non_passing.append(f"{name}={result.status.value}")

    return ReportabilityAssessment(
        not (missing or non_passing or stale),
        missing_checks=tuple(missing),
        non_passing_checks=tuple(non_passing),
        stale_checks=tuple(stale),
    )


def require_reportable(
    candidate: Candidate,
    required_checks: Iterable[str],
    *,
    at: datetime | None = None,
) -> None:
    """Raise :class:`ReportabilityError` unless all checks explicitly pass."""

    assessment = assess_reportability(candidate, required_checks, at=at)
    if not assessment.reportable:
        explanation = "; ".join(assessment.reasons)
        raise ReportabilityError(
            f"candidate {candidate.candidate_id} is not reportable: {explanation}"
        )
