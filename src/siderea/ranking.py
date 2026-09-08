"""Deterministic, capacity-aware nightly review queues.

The anomaly reserve is an explicit discovery route, not a bonus secretly mixed
into the primary priority score.  This makes the finite reviewer budget and the
exploration/exploitation trade-off inspectable in every queue.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from numbers import Real


@dataclass(frozen=True, slots=True)
class QueueCandidate:
    """Minimal candidate record required to allocate review capacity."""

    candidate_id: str
    priority_score: float
    anomaly_score: float = 0.0
    eligible: bool = True
    ineligibility_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str):
            raise ValueError("candidate_id must be a string")
        identifier = self.candidate_id.strip()
        if not identifier:
            raise ValueError("candidate_id must not be empty")
        object.__setattr__(self, "candidate_id", identifier)
        for name in ("priority_score", "anomaly_score"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(f"{name} must be finite and within [0, 1]")
            numeric_value = float(value)
            if not math.isfinite(numeric_value) or not 0.0 <= numeric_value <= 1.0:
                raise ValueError(f"{name} must be finite and within [0, 1]")
            object.__setattr__(self, name, numeric_value)
        if not isinstance(self.eligible, bool):
            raise ValueError("eligible must be boolean")
        if self.ineligibility_reason is not None and not isinstance(self.ineligibility_reason, str):
            raise ValueError("ineligibility_reason must be a string when supplied")
        if self.eligible and self.ineligibility_reason:
            raise ValueError("eligible candidates cannot have an ineligibility reason")
        if not self.eligible and not (self.ineligibility_reason or "").strip():
            raise ValueError("ineligible candidates require a reason")


@dataclass(frozen=True, slots=True)
class QueueEntry:
    """One selected candidate and the budget route that selected it."""

    rank: int
    candidate_id: str
    selection_route: str
    priority_score: float
    anomaly_score: float
    selection_propensity: float | None = None


@dataclass(frozen=True, slots=True)
class NightlyQueue:
    """Auditable result of allocating one night's review budget."""

    schema: str = field(default="siderea.nightly_queue.v2", init=False)
    entries: tuple[QueueEntry, ...]
    budget: int
    requested_anomaly_slots: int
    used_anomaly_slots: int
    requested_audit_slots: int
    used_audit_slots: int
    audit_population: int
    audit_seed: str | None
    audit_selection_probability: float | None
    eligible_candidates: int
    excluded_candidates: int
    selection_policy: str

    @property
    def unused_slots(self) -> int:
        return self.budget - len(self.entries)


def _identifier_key(candidate: QueueCandidate) -> tuple[str, str]:
    return candidate.candidate_id.casefold(), candidate.candidate_id


def _priority_key(candidate: QueueCandidate) -> tuple[float, float, str, str]:
    folded, original = _identifier_key(candidate)
    return -candidate.priority_score, -candidate.anomaly_score, folded, original


def _anomaly_key(candidate: QueueCandidate) -> tuple[float, float, str, str]:
    folded, original = _identifier_key(candidate)
    return -candidate.anomaly_score, -candidate.priority_score, folded, original


def _audit_key(candidate: QueueCandidate, seed: str) -> tuple[bytes, str, str]:
    """Return a seeded, platform-independent pseudo-random ordering key."""

    folded, original = _identifier_key(candidate)
    digest = sha256(f"{seed}\0{candidate.candidate_id}".encode()).digest()
    return digest, folded, original


def build_nightly_queue(
    candidates: Sequence[QueueCandidate],
    *,
    budget: int,
    anomaly_slots: int = 0,
    anomaly_threshold: float = 0.80,
    audit_slots: int = 0,
    audit_seed: str | None = None,
    selection_policy: str = "caller_supplied_eligibility",
) -> NightlyQueue:
    """Allocate priority, anomaly, and randomized-audit routes without duplicates.

    ``anomaly_slots`` are reserved only for candidates meeting
    ``anomaly_threshold``.  Empty reserve slots flow back to the primary route,
    so a quiet night never wastes reviewer capacity. ``audit_slots`` are sampled
    first from the complete eligible population using a SHA-256 ordering keyed by
    the required ``audit_seed``. The seed and the uniform without-replacement
    inclusion probability are returned with the queue, making the randomized
    denominator replayable and suitable for inverse-propensity analyses. All
    score ties end with the stable candidate identifier.
    """

    count_values = (
        ("budget", budget),
        ("anomaly_slots", anomaly_slots),
        ("audit_slots", audit_slots),
    )
    for name, value in count_values:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
    if budget < 0:
        raise ValueError("budget must be non-negative")
    if anomaly_slots < 0:
        raise ValueError("anomaly_slots must be non-negative")
    if audit_slots < 0:
        raise ValueError("audit_slots must be non-negative")
    if isinstance(anomaly_threshold, bool) or not isinstance(anomaly_threshold, Real):
        raise ValueError("anomaly_threshold must be finite and within [0, 1]")
    numeric_anomaly_threshold = float(anomaly_threshold)
    if not math.isfinite(numeric_anomaly_threshold) or not 0.0 <= numeric_anomaly_threshold <= 1.0:
        raise ValueError("anomaly_threshold must be finite and within [0, 1]")
    normalized_seed = None if audit_seed is None else str(audit_seed).strip()
    if audit_slots and not normalized_seed:
        raise ValueError("audit_seed is required when audit_slots is positive")
    if not isinstance(selection_policy, str):
        raise ValueError("selection_policy must be a string")
    normalized_policy = selection_policy.strip()
    if not normalized_policy:
        raise ValueError("selection_policy must not be empty")

    identifiers = [candidate.candidate_id for candidate in candidates]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("candidate_id values must be unique within a nightly queue")

    eligible = [candidate for candidate in candidates if candidate.eligible]
    excluded = len(candidates) - len(eligible)
    if budget == 0 or not eligible:
        return NightlyQueue(
            (),
            budget,
            anomaly_slots,
            0,
            audit_slots,
            0,
            len(eligible),
            normalized_seed if audit_slots else None,
            0.0 if audit_slots and eligible else None,
            len(eligible),
            excluded,
            normalized_policy,
        )

    audit_count = min(audit_slots, budget, len(eligible))
    audit = (
        sorted(eligible, key=lambda candidate: _audit_key(candidate, normalized_seed or ""))[
            :audit_count
        ]
        if audit_count
        else []
    )
    selected_ids = {candidate.candidate_id for candidate in audit}
    remaining_candidates = [
        candidate for candidate in eligible if candidate.candidate_id not in selected_ids
    ]
    remaining_budget = budget - len(audit)
    reserve = min(anomaly_slots, remaining_budget)
    primary_slots = remaining_budget - reserve
    priority_order = sorted(remaining_candidates, key=_priority_key)
    primary = priority_order[:primary_slots]
    selected_ids.update(candidate.candidate_id for candidate in primary)

    anomaly_pool = sorted(
        (
            candidate
            for candidate in eligible
            if candidate.candidate_id not in selected_ids
            and candidate.anomaly_score >= numeric_anomaly_threshold
        ),
        key=_anomaly_key,
    )
    anomaly = anomaly_pool[:reserve]
    selected_ids.update(candidate.candidate_id for candidate in anomaly)

    unfilled = budget - len(audit) - len(primary) - len(anomaly)
    priority_fill = [
        candidate for candidate in priority_order if candidate.candidate_id not in selected_ids
    ][:unfilled]

    routed = [
        *((candidate, "priority") for candidate in primary),
        *((candidate, "anomaly_reserve") for candidate in anomaly),
        *((candidate, "priority_fill") for candidate in priority_fill),
        *((candidate, "random_audit") for candidate in audit),
    ]
    audit_probability = audit_count / len(eligible) if audit_count else None
    entries = tuple(
        QueueEntry(
            rank=index,
            candidate_id=candidate.candidate_id,
            selection_route=route,
            priority_score=candidate.priority_score,
            anomaly_score=candidate.anomaly_score,
            selection_propensity=(audit_probability if route == "random_audit" else None),
        )
        for index, (candidate, route) in enumerate(routed, start=1)
    )
    return NightlyQueue(
        entries=entries,
        budget=budget,
        requested_anomaly_slots=anomaly_slots,
        used_anomaly_slots=len(anomaly),
        requested_audit_slots=audit_slots,
        used_audit_slots=len(audit),
        audit_population=len(eligible),
        audit_seed=normalized_seed if audit_slots else None,
        audit_selection_probability=audit_probability,
        eligible_candidates=len(eligible),
        excluded_candidates=excluded,
        selection_policy=normalized_policy,
    )


__all__ = ["NightlyQueue", "QueueCandidate", "QueueEntry", "build_nightly_queue"]
