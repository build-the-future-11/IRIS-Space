"""Transparent urgency and observability ranking for human-approved follow-up."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from numbers import Real


@dataclass(frozen=True)
class FollowupFactors:
    """Dimensionless decision scores; none is implicitly a probability.

    A caller may supply a calibrated probability as a score, but it remains the
    caller's responsibility to preserve that model's calibration and validity
    metadata alongside the resulting follow-up decision.
    """

    reality_score: float
    novelty_score: float
    scientific_value: float
    urgency: float
    observability: float
    information_gain: float

    def validate(self) -> None:
        for name, value in self.__dict__.items():
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(f"{name} must be finite and within [0, 1]")
            numeric_value = float(value)
            if not math.isfinite(numeric_value) or not 0.0 <= numeric_value <= 1.0:
                raise ValueError(f"{name} must be finite and within [0, 1]")


@dataclass(frozen=True, slots=True)
class FollowupPriorityResult:
    """Auditable components of a heuristic follow-up ranking decision."""

    priority: float
    core_score: float
    anomaly_route_score: float
    selected_route: str
    score_semantics: str = "heuristic_priority_not_probability"


def explain_followup_priority(
    factors: FollowupFactors,
    *,
    anomaly_score: float = 0.0,
) -> FollowupPriorityResult:
    """Return the priority and both transparent decision routes.

    This result is a bounded heuristic ranking score, never an automatically
    calibrated event probability. ``selected_route`` makes it visible when the
    anomaly reserve, rather than the core scientific score, set the priority.
    """

    factors.validate()
    if isinstance(anomaly_score, bool) or not isinstance(anomaly_score, Real):
        raise ValueError("anomaly_score must be finite and within [0, 1]")
    numeric_anomaly_score = float(anomaly_score)
    if not math.isfinite(numeric_anomaly_score) or not 0.0 <= numeric_anomaly_score <= 1.0:
        raise ValueError("anomaly_score must be finite and within [0, 1]")
    core = (
        factors.reality_score
        * factors.novelty_score
        * math.sqrt(max(factors.scientific_value * factors.urgency, 0.0))
        * math.sqrt(max(factors.observability * factors.information_gain, 0.0))
    )
    # Reserve a modest independent route for unusual candidates without allowing
    # anomaly alone to override low reality probability.
    anomaly_route = 0.35 * numeric_anomaly_score * factors.reality_score * factors.observability
    priority = min(1.0, max(core, anomaly_route))
    selected_route = "anomaly_reserve" if anomaly_route > core else "core"
    return FollowupPriorityResult(
        priority=priority,
        core_score=core,
        anomaly_route_score=anomaly_route,
        selected_route=selected_route,
    )


def followup_priority(factors: FollowupFactors, *, anomaly_score: float = 0.0) -> float:
    """Return the bounded heuristic priority while preserving the legacy API."""

    return explain_followup_priority(factors, anomaly_score=anomaly_score).priority


def hours_since(mjd: float, *, now: datetime | None = None) -> float:
    if isinstance(mjd, bool) or not isinstance(mjd, Real):
        raise ValueError("mjd must be finite and non-negative")
    numeric_mjd = float(mjd)
    if not math.isfinite(numeric_mjd) or numeric_mjd < 0:
        raise ValueError("mjd must be finite and non-negative")
    current = now or datetime.now(UTC)
    if not isinstance(current, datetime):
        raise ValueError("now must be a datetime with timezone information")
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("now must include timezone information")
    current_mjd = current.timestamp() / 86400.0 + 40587.0
    age_hours = (current_mjd - numeric_mjd) * 24.0
    if age_hours < -1.0 / 60.0:
        raise ValueError("mjd is in the future relative to now")
    return max(0.0, age_hours)
