"""Training-only APENic episodic residual memory."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from siderea.provenance import digest_value

FloatArray = NDArray[np.float64]


def _quaternion_array(value: Any, name: str) -> FloatArray:
    array = np.asarray(value, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 4 or np.any(~np.isfinite(array)):
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

    def __post_init__(self) -> None:
        if (
            not self.entry_id.strip()
            or not self.source_group.strip()
            or not self.population.strip()
        ):
            raise ValueError("memory identities and population must not be empty")
        if not self.calibration.strip():
            raise ValueError("memory calibration must not be empty")
        key = _quaternion_array(self.key, "key")
        residual = _quaternion_array(self.residual, "residual")
        if key.shape != residual.shape:
            raise ValueError("memory key and residual must have equal shapes")
        if not math.isfinite(self.cutoff_mjd):
            raise ValueError("memory cutoff_mjd must be finite")
        object.__setattr__(self, "key", key.copy())
        object.__setattr__(self, "residual", residual.copy())


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
        shape = self.entries[0].key.shape
        if any(entry.key.shape != shape for entry in self.entries):
            raise ValueError("all memory entries must have equal key shapes")
        if not math.isfinite(temperature) or temperature <= 0.0:
            raise ValueError("temperature must be positive and finite")
        if isinstance(maximum_neighbors, bool) or maximum_neighbors < 1:
            raise ValueError("maximum_neighbors must be a positive integer")
        if metric_weights is None:
            metric = np.ones(shape[0], dtype=np.float64)
        else:
            metric = np.asarray(metric_weights, dtype=np.float64)
        if metric.shape != (shape[0],) or np.any(~np.isfinite(metric)) or np.any(metric <= 0.0):
            raise ValueError("metric_weights must be positive and match quaternion channels")
        self.metric_weights = metric / float(metric.mean())
        self.temperature = temperature
        self.maximum_neighbors = maximum_neighbors
        self.digest = digest_value(
            {
                "entries": [
                    {
                        "entry_id": entry.entry_id,
                        "source_group": entry.source_group,
                        "cutoff_mjd": entry.cutoff_mjd,
                        "population": entry.population,
                        "calibration": entry.calibration,
                        "key": entry.key.tolist(),
                        "residual": entry.residual.tolist(),
                    }
                    for entry in self.entries
                ],
                "metric_weights": self.metric_weights.tolist(),
                "temperature": temperature,
                "maximum_neighbors": maximum_neighbors,
            }
        )

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
        key = _quaternion_array(query, "query")
        base = _quaternion_array(base_forecast, "base_forecast")
        if key.shape != self.entries[0].key.shape or base.shape != key.shape:
            raise ValueError("query and base forecast must match memory shape")
        if not query_source_group.strip() or not population.strip() or not calibration.strip():
            raise ValueError("query group, population and calibration must not be empty")
        if not math.isfinite(query_cutoff_mjd):
            raise ValueError("query_cutoff_mjd must be finite")

        eligible = [
            entry
            for entry in self.entries
            if entry.source_group != query_source_group
            and entry.cutoff_mjd <= query_cutoff_mjd
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
        if force_gate is None:
            gate = automatic_gate
        else:
            if not math.isfinite(force_gate) or not 0.0 <= force_gate <= 1.0:
                raise ValueError("force_gate must lie within [0, 1]")
            gate = force_gate
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


__all__ = ["EpisodicResidualMemory", "MemoryEntry", "RetrievalResult"]
