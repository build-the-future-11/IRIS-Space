"""Training-only APENic episodic residual memory."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from numbers import Real
from typing import Any

import numpy as np
from numpy.typing import NDArray

from siderea.provenance import digest_value

FloatArray = NDArray[np.float64]
MEMORY_CONTRACT_VERSION = "siderea.space_jepa_v2_memory.v2"


def _finite_time(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite numeric MJD")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite numeric MJD") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite numeric MJD")
    return result


def _immutable_array(array: FloatArray) -> FloatArray:
    # A bytes owner prevents callers from re-enabling writes after digesting.
    return np.frombuffer(array.tobytes(), dtype=np.float64).reshape(array.shape)


def _quaternion_array(value: Any, name: str) -> FloatArray:
    if np.iscomplexobj(value):
        raise ValueError(f"{name} must contain real quaternion components")
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] != 4 or np.any(~np.isfinite(array)):
        raise ValueError(f"{name} must be finite with shape [channels, 4]")
    return array


@dataclass(frozen=True)
class MemoryEntry:
    entry_id: str
    key: FloatArray
    residual: FloatArray
    source_group: str
    cutoff_mjd: float
    population: str
    calibration: str
    available_at_mjd: float

    def __post_init__(self) -> None:
        for name in ("entry_id", "source_group", "population", "calibration"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"memory {name} must be a nonempty string")
        key = _quaternion_array(self.key, "key")
        residual = _quaternion_array(self.residual, "residual")
        if key.shape != residual.shape:
            raise ValueError("memory key and residual must have equal shapes")
        cutoff = _finite_time(self.cutoff_mjd, "memory cutoff_mjd")
        available = _finite_time(self.available_at_mjd, "memory available_at_mjd")
        if available < cutoff:
            raise ValueError("memory available_at_mjd must not precede its prefix cutoff")
        object.__setattr__(self, "cutoff_mjd", cutoff)
        object.__setattr__(self, "available_at_mjd", available)
        object.__setattr__(self, "key", _immutable_array(key))
        object.__setattr__(self, "residual", _immutable_array(residual))

    @classmethod
    def from_mapping(cls, item: Mapping[str, Any]) -> MemoryEntry:
        if "available_at_mjd" not in item:
            raise ValueError("memory entries require explicit residual available_at_mjd")
        return cls(
            entry_id=item["entry_id"],
            key=item["key"],
            residual=item["residual"],
            source_group=item["source_group"],
            cutoff_mjd=item["cutoff_mjd"],
            population=item["population"],
            calibration=item["calibration"],
            available_at_mjd=item["available_at_mjd"],
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "source_group": self.source_group,
            "cutoff_mjd": self.cutoff_mjd,
            "available_at_mjd": self.available_at_mjd,
            "population": self.population,
            "calibration": self.calibration,
            "key": self.key.tolist(),
            "residual": self.residual.tolist(),
        }


@dataclass(frozen=True)
class RetrievalResult:
    residual: FloatArray
    gate: float
    corrected: FloatArray
    neighbor_ids: tuple[str, ...]
    weights: tuple[float, ...]
    nearest_distance: float
    entropy: float
    supported: bool


class EpisodicResidualMemory:
    """Immutable query surface over training-only residual entries."""

    entries: tuple[MemoryEntry, ...]
    _metric_input: FloatArray
    metric_weights: FloatArray
    temperature: float
    maximum_neighbors: int
    digest: str

    def __init__(
        self,
        entries: Iterable[MemoryEntry],
        *,
        metric_weights: Sequence[float] | None = None,
        temperature: float = 1.0,
        maximum_neighbors: int = 16,
    ) -> None:
        self.entries = tuple(entries)
        if not self.entries:
            raise ValueError("episodic memory requires at least one entry")
        if len({entry.entry_id for entry in self.entries}) != len(self.entries):
            raise ValueError("memory entry_id values must be unique")
        shape = self.entries[0].key.shape
        if any(entry.key.shape != shape for entry in self.entries):
            raise ValueError("all memory entries must have equal key shapes")
        if (
            isinstance(temperature, (bool, np.bool_))
            or not isinstance(temperature, Real)
            or not math.isfinite(temperature)
            or temperature <= 0.0
        ):
            raise ValueError("temperature must be positive and finite")
        if type(maximum_neighbors) is not int or maximum_neighbors < 1:
            raise ValueError("maximum_neighbors must be a positive integer")
        if metric_weights is None:
            metric = np.ones(shape[0], dtype=np.float64)
        else:
            if np.iscomplexobj(metric_weights):
                raise ValueError("metric_weights must be real")
            metric = np.asarray(metric_weights, dtype=np.float64)
        if metric.shape != (shape[0],) or np.any(~np.isfinite(metric)) or np.any(metric <= 0.0):
            raise ValueError("metric_weights must be positive and match quaternion channels")
        self._metric_input = _immutable_array(metric)
        # Normalize without overflowing the mean of otherwise finite weights.
        metric = metric / float(metric.max())
        self.metric_weights = _immutable_array(metric / float(metric.mean()))
        if np.any(self.metric_weights <= 0.0):
            raise ValueError("normalized metric_weights must remain positive")
        self.temperature = float(temperature)
        self.maximum_neighbors = maximum_neighbors
        self.digest = digest_value(
            {
                "schema": MEMORY_CONTRACT_VERSION,
                "entries": [entry.to_mapping() for entry in self.entries],
                "metric_weights": self.metric_weights.tolist(),
                "temperature": self.temperature,
                "maximum_neighbors": maximum_neighbors,
            }
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema": MEMORY_CONTRACT_VERSION,
            "entry_count": len(self.entries),
            "temperature": self.temperature,
            "maximum_neighbors": self.maximum_neighbors,
            "metric_weights": self._metric_input.tolist(),
            "memory_digest": self.digest,
            "entries": [entry.to_mapping() for entry in self.entries],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> EpisodicResidualMemory:
        if payload.get("schema") != MEMORY_CONTRACT_VERSION:
            raise ValueError("memory v2 is required; rebuild with explicit residual availability")
        raw = payload.get("entries")
        if not isinstance(raw, list) or any(not isinstance(item, Mapping) for item in raw):
            raise ValueError("APENic memory artifact lacks entry objects")
        if type(payload.get("entry_count")) is not int or payload["entry_count"] != len(raw):
            raise ValueError("APENic memory entry_count differs from its entries")
        memory = cls(
            [MemoryEntry.from_mapping(item) for item in raw],
            metric_weights=payload.get("metric_weights"),
            temperature=payload["temperature"],
            maximum_neighbors=payload["maximum_neighbors"],
        )
        if payload.get("memory_digest") != memory.digest:
            raise ValueError("APENic memory digest mismatch")
        return memory

    def _distance(self, query: FloatArray, entry: MemoryEntry) -> float:
        channel_distance = np.sum((query - entry.key) ** 2, axis=1)
        return float(np.mean(self.metric_weights * channel_distance))

    def retrieve(
        self,
        query: Any,
        base_forecast: Any,
        *,
        query_source_group: str,
        query_cutoff_mjd: float,
        population: str,
        calibration: str,
        allow_cross_population: bool = False,
        force_gate: float | None = None,
    ) -> RetrievalResult:
        # Policy controls are validated before inspecting eligibility. A string
        # such as "false" is truthy in Python and must never broaden the
        # admitted population. Invalid forced gates must not be hidden by an
        # empty neighbor set either.
        if type(allow_cross_population) is not bool:
            raise ValueError("allow_cross_population must be an explicit boolean")
        if force_gate is not None and (
            isinstance(force_gate, (bool, np.bool_))
            or not isinstance(force_gate, Real)
            or not math.isfinite(force_gate)
            or not 0.0 <= force_gate <= 1.0
        ):
            raise ValueError("force_gate must be a finite real number within [0, 1]")
        key = _quaternion_array(query, "query")
        base = _quaternion_array(base_forecast, "base_forecast")
        if key.shape != self.entries[0].key.shape or base.shape != key.shape:
            raise ValueError("query and base forecast must match memory shape")
        if not query_source_group.strip() or not population.strip() or not calibration.strip():
            raise ValueError("query group, population and calibration must not be empty")
        query_cutoff_mjd = _finite_time(query_cutoff_mjd, "query_cutoff_mjd")

        eligible = [
            entry
            for entry in self.entries
            if entry.source_group != query_source_group
            and entry.cutoff_mjd <= query_cutoff_mjd
            and entry.available_at_mjd <= query_cutoff_mjd
            and entry.calibration == calibration
            and (allow_cross_population or entry.population == population)
        ]
        if not eligible:
            zeros = np.zeros_like(base)
            return RetrievalResult(
                residual=zeros,
                gate=0.0,
                corrected=base.copy(),
                neighbor_ids=(),
                weights=(),
                nearest_distance=math.inf,
                entropy=0.0,
                supported=False,
            )
        ranked = sorted(
            ((self._distance(key, entry), entry) for entry in eligible),
            key=lambda item: (item[0], item[1].entry_id),
        )[: self.maximum_neighbors]
        distances = np.asarray([item[0] for item in ranked], dtype=np.float64)
        logits = -(distances - distances.min()) / self.temperature
        raw_weights = np.exp(logits)
        weights = raw_weights / raw_weights.sum()
        residual = np.sum(
            np.stack([entry.residual for _, entry in ranked]) * weights[:, None, None],
            axis=0,
        )
        entropy = float(-np.sum(weights * np.log(np.maximum(weights, np.finfo(float).tiny))))
        normalized_entropy = entropy / math.log(len(weights)) if len(weights) > 1 else 0.0
        automatic_gate = 1.0 / (1.0 + math.exp(min(60.0, distances[0])))
        automatic_gate *= 1.0 - 0.5 * normalized_entropy
        gate = automatic_gate if force_gate is None else float(force_gate)
        return RetrievalResult(
            residual=residual,
            gate=gate,
            corrected=base + gate * residual,
            neighbor_ids=tuple(entry.entry_id for _, entry in ranked),
            weights=tuple(float(value) for value in weights),
            nearest_distance=float(distances[0]),
            entropy=entropy,
            supported=True,
        )


__all__ = ["MEMORY_CONTRACT_VERSION", "EpisodicResidualMemory", "MemoryEntry", "RetrievalResult"]
