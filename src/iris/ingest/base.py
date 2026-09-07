"""Shared contracts for obtaining candidate photometry.

Ingestion adapters return the same canonical table whether the source is a
local file or a live broker.  Network-backed adapters are deliberately kept
behind a protocol so local analysis and tests never require broker access.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Any, Protocol, runtime_checkable

import pandas as pd

CANONICAL_COLUMNS = (
    "source_id",
    "ra_deg",
    "dec_deg",
    "mjd",
    "band",
    "magnitude",
    "magnitude_error",
    "is_detection",
    "limiting_magnitude",
    "flux",
    "flux_error",
    "survey",
    "observation_id",
    "quality",
)


class IngestionError(ValueError):
    """Raised when source data cannot be converted without ambiguity."""


class BrokerDependencyError(RuntimeError):
    """Raised when an optional broker client is not installed or configured."""


@dataclass(frozen=True, slots=True)
class BrokerQuery:
    """Portable subset of a transient-broker search request."""

    classes: tuple[str, ...] = ("SN",)
    max_objects: int = 350
    discovered_after_mjd: float | None = None
    min_detections: int = 3

    def __post_init__(self) -> None:
        if isinstance(self.classes, (str, bytes)) or not isinstance(self.classes, tuple):
            raise TypeError("classes must be a tuple of strings")
        if any(not isinstance(item, str) for item in self.classes):
            raise TypeError("classes must be a tuple of strings")
        normalized = tuple(item.strip() for item in self.classes if item.strip())
        if not normalized:
            raise ValueError("classes must contain at least one class name")
        if len(set(normalized)) != len(normalized):
            raise ValueError("classes must not contain duplicates")
        if isinstance(self.max_objects, bool) or not isinstance(self.max_objects, int):
            raise TypeError("max_objects must be an integer")
        if self.max_objects < 1:
            raise ValueError("max_objects must be at least one")
        if isinstance(self.min_detections, bool) or not isinstance(self.min_detections, int):
            raise TypeError("min_detections must be an integer")
        if self.min_detections < 1:
            raise ValueError("min_detections must be at least one")
        if self.discovered_after_mjd is not None:
            if isinstance(self.discovered_after_mjd, bool) or not isinstance(
                self.discovered_after_mjd, (int, float)
            ):
                raise TypeError("discovered_after_mjd must be a number or null")
            if not math.isfinite(self.discovered_after_mjd) or self.discovered_after_mjd < 0:
                raise ValueError("discovered_after_mjd must be finite and non-negative")
        object.__setattr__(self, "classes", normalized)


@dataclass(frozen=True, slots=True, init=False)
class IngestionBatch:
    """Canonical photometry plus source-level provenance.

    The data frame is copied on construction and access so callers cannot
    accidentally mutate the observations recorded by a pipeline run.
    """

    _observations: pd.DataFrame = field(repr=False)
    source: str
    retrieved_at: str
    _provenance: Mapping[str, Any] = field(repr=False)
    warnings: tuple[str, ...] = ()
    source_content: bytes | None = field(default=None, repr=False)

    def __init__(
        self,
        observations: pd.DataFrame,
        source: str,
        retrieved_at: str,
        provenance: Mapping[str, Any] | None = None,
        warnings: tuple[str, ...] = (),
        source_content: bytes | None = None,
    ) -> None:
        object.__setattr__(self, "_observations", observations)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "retrieved_at", retrieved_at)
        object.__setattr__(self, "_provenance", {} if provenance is None else provenance)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "source_content", source_content)
        self.__post_init__()

    def __post_init__(self) -> None:
        if not isinstance(self.source, str):
            raise TypeError("source must be a string")
        source = self.source.strip()
        if not source:
            raise ValueError("source must not be empty")
        try:
            retrieved = datetime.fromisoformat(self.retrieved_at)
        except (TypeError, ValueError) as exc:
            raise ValueError("retrieved_at must be an ISO-8601 timestamp") from exc
        if retrieved.tzinfo is None or retrieved.utcoffset() is None:
            raise ValueError("retrieved_at must include timezone information")
        if not isinstance(self._observations, pd.DataFrame):
            raise TypeError("observations must be a pandas DataFrame")
        if not isinstance(self._provenance, Mapping):
            raise TypeError("provenance must be a mapping")
        if isinstance(self.warnings, (str, bytes)) or not isinstance(self.warnings, tuple):
            raise TypeError("warnings must be a tuple of strings")
        if any(not isinstance(item, str) for item in self.warnings):
            raise TypeError("warnings must be a tuple of strings")
        missing = set(CANONICAL_COLUMNS) - set(self._observations.columns)
        if missing:
            raise ValueError(f"canonical ingestion table is missing: {sorted(missing)}")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "_observations", self._observations.copy(deep=True))
        object.__setattr__(self, "_provenance", deepcopy(dict(self._provenance)))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if self.source_content is not None:
            if not isinstance(self.source_content, bytes):
                raise TypeError("source_content must be immutable bytes when supplied")
            actual_digest = sha256(self.source_content).hexdigest()
            expected_digest = self._provenance.get("sha256")
            broker_snapshot = self._provenance.get("broker_snapshot")
            if expected_digest is None and isinstance(broker_snapshot, Mapping):
                expected_digest = broker_snapshot.get("photometry_sha256")
            if expected_digest is not None and expected_digest != actual_digest:
                raise ValueError("source_content does not match its provenance digest")

    @property
    def observations(self) -> pd.DataFrame:
        """Return a defensive copy of the canonical observation table."""

        return self._observations.copy(deep=True)

    @property
    def provenance(self) -> Mapping[str, Any]:
        """Return a defensive copy of the source-level provenance."""

        return deepcopy(dict(self._provenance))

    @property
    def candidate_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(self._observations["source_id"].astype(str).tolist()))

    def to_frame(self) -> pd.DataFrame:
        """Return a defensive copy of the canonical observation table."""

        return self._observations.copy(deep=True)


@runtime_checkable
class BrokerAdapter(Protocol):
    """Interface implemented by optional live broker integrations."""

    name: str

    def fetch(self, query: BrokerQuery) -> IngestionBatch:
        """Fetch and normalize one bounded broker query."""
