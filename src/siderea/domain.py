"""Core, dependency-free domain types used throughout SIDEREA.

The records in this module are immutable on purpose.  A pipeline stage returns
a new candidate record rather than silently changing the evidence that a human
reviewer previously saw.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum


def utc_now() -> datetime:
    """Return an aware UTC timestamp (kept as a function for deterministic tests)."""

    return datetime.now(UTC)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone information")


def _finite(value: float | None, field_name: str) -> None:
    if value is not None and not math.isfinite(value):
        raise ValueError(f"{field_name} must be finite when supplied")


class CandidateState(StrEnum):
    """Auditable lifecycle states for a transient candidate."""

    INGESTED = "ingested"
    ENRICHING = "enriching"
    READY_FOR_SCREENING = "ready_for_screening"
    SCREENING = "screening"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"
    REPORTABLE = "reportable"
    APPROVED = "approved"
    REPORTED = "reported"
    FOLLOW_UP = "follow_up"
    CLOSED = "closed"
    ERROR = "error"


class CheckStatus(StrEnum):
    """State of a scientific or operational check.

    Only :attr:`PASS` is affirmative evidence.  In particular, ``ERROR`` and
    ``UNAVAILABLE`` are never aliases for a negative catalogue match.
    """

    NOT_RUN = "not_run"
    RUNNING = "running"
    PASS = "pass"
    FAIL = "fail"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
    SKIPPED = "skipped"


class EvidenceKind(StrEnum):
    """Broad provenance category for a piece of candidate evidence."""

    PHOTOMETRY = "photometry"
    IMAGE = "image"
    BROKER = "broker"
    CATALOG = "catalog"
    MODEL = "model"
    HUMAN_REVIEW = "human_review"
    FOLLOW_UP = "follow_up"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class Observation:
    """One calibrated detection, forced measurement, or upper limit."""

    mjd: float
    band: str
    detected: bool
    magnitude: float | None = None
    magnitude_error: float | None = None
    flux: float | None = None
    flux_error: float | None = None
    limiting_magnitude: float | None = None
    survey: str = "unknown"
    observation_id: str | None = None
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not math.isfinite(self.mjd) or self.mjd < 0:
            raise ValueError("mjd must be a finite, non-negative value")

        band = self.band.strip()
        survey = self.survey.strip()
        if not band:
            raise ValueError("band must not be empty")
        if not survey:
            raise ValueError("survey must not be empty")
        object.__setattr__(self, "band", band)
        object.__setattr__(self, "survey", survey)

        for name in (
            "magnitude",
            "magnitude_error",
            "flux",
            "flux_error",
            "limiting_magnitude",
        ):
            _finite(getattr(self, name), name)
        if self.magnitude_error is not None and self.magnitude_error <= 0:
            raise ValueError("magnitude_error must be positive")
        if self.flux_error is not None and self.flux_error <= 0:
            raise ValueError("flux_error must be positive")
        if self.detected and self.magnitude is None and self.flux is None:
            raise ValueError("a detection requires magnitude or flux")
        if not self.detected and all(
            value is None for value in (self.flux, self.limiting_magnitude)
        ):
            raise ValueError("a non-detection requires forced flux or a limiting magnitude")

        raw_flags = (
            (self.quality_flags,) if isinstance(self.quality_flags, str) else self.quality_flags
        )
        flags = tuple(flag.strip() for flag in raw_flags if flag.strip())
        object.__setattr__(self, "quality_flags", flags)


@dataclass(frozen=True, slots=True)
class Evidence:
    """A timestamped result from a catalogue, model, image, or reviewer check."""

    check_name: str
    kind: EvidenceKind
    status: CheckStatus
    source: str
    checked_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None
    summary: str = ""
    payload_ref: str | None = None

    def __post_init__(self) -> None:
        check_name = self.check_name.strip().casefold()
        source = self.source.strip()
        if not check_name:
            raise ValueError("check_name must not be empty")
        if not source:
            raise ValueError("source must not be empty")
        object.__setattr__(self, "check_name", check_name)
        object.__setattr__(self, "source", source)
        _require_aware(self.checked_at, "checked_at")
        if self.expires_at is not None:
            _require_aware(self.expires_at, "expires_at")
            if self.expires_at <= self.checked_at:
                raise ValueError("expires_at must be later than checked_at")

    def is_fresh(self, at: datetime | None = None) -> bool:
        """Return whether explicitly time-bounded evidence is valid at ``at``."""

        instant = at or utc_now()
        _require_aware(instant, "at")
        return (
            self.expires_at is not None and self.checked_at <= instant and instant < self.expires_at
        )


@dataclass(frozen=True, slots=True)
class Candidate:
    """Immutable aggregate containing a candidate and all evidence seen so far."""

    candidate_id: str
    ra_deg: float
    dec_deg: float
    origin: str = "unknown"
    state: CandidateState = CandidateState.INGESTED
    observations: tuple[Observation, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    aliases: tuple[str, ...] = ()
    discovered_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        candidate_id = self.candidate_id.strip()
        origin = self.origin.strip()
        if not candidate_id:
            raise ValueError("candidate_id must not be empty")
        if not origin:
            raise ValueError("origin must not be empty")
        if not math.isfinite(self.ra_deg) or not 0 <= self.ra_deg < 360:
            raise ValueError("ra_deg must be in [0, 360)")
        if not math.isfinite(self.dec_deg) or not -90 <= self.dec_deg <= 90:
            raise ValueError("dec_deg must be in [-90, 90]")
        object.__setattr__(self, "candidate_id", candidate_id)
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        raw_aliases = (self.aliases,) if isinstance(self.aliases, str) else self.aliases
        aliases = tuple(dict.fromkeys(alias.strip() for alias in raw_aliases if alias.strip()))
        object.__setattr__(self, "aliases", aliases)

        _require_aware(self.created_at, "created_at")
        _require_aware(self.updated_at, "updated_at")
        if self.discovered_at is not None:
            _require_aware(self.discovered_at, "discovered_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not be earlier than created_at")

    @property
    def latest_observation(self) -> Observation | None:
        return max(self.observations, key=lambda item: item.mjd, default=None)

    def latest_evidence(self, check_name: str) -> Evidence | None:
        """Return the latest result, resolving equal-time records conservatively."""

        normalized = check_name.strip().casefold()
        matching = (item for item in self.evidence if item.check_name == normalized)

        def conservative_key(item: Evidence) -> tuple[datetime, bool, bool, float, str, str]:
            expiry_key = float("inf") if item.expires_at is None else -item.expires_at.timestamp()
            return (
                item.checked_at,
                item.status is not CheckStatus.PASS,
                item.expires_at is None,
                expiry_key,
                item.status.value,
                item.source,
            )

        return max(matching, key=conservative_key, default=None)

    def add_observations(
        self, observations: Iterable[Observation], *, at: datetime | None = None
    ) -> Candidate:
        timestamp = at or utc_now()
        _require_aware(timestamp, "at")
        combined = (*self.observations, *tuple(observations))
        return replace(self, observations=combined, updated_at=timestamp)

    def record_evidence(self, evidence: Evidence, *, at: datetime | None = None) -> Candidate:
        timestamp = at or utc_now()
        _require_aware(timestamp, "at")
        return replace(self, evidence=(*self.evidence, evidence), updated_at=timestamp)
