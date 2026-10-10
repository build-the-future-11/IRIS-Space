"""Training-only APENic episodic residual memory."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from operator import index
from typing import Any

import numpy as np
from numpy.typing import NDArray

from siderea.provenance import digest_value

FloatArray = NDArray[np.float64]


def _quaternion_array(value: Any, name: str) -> FloatArray:
    raw = np.asarray(value)
    if raw.dtype.kind not in "iuf":
        raise ValueError(f"{name} must contain real numeric values")
    array = np.asarray(raw, dtype=np.float64)
    if array.ndim != 2 or array.shape[0] == 0 or array.shape[1] != 4 or np.any(~np.isfinite(array)):
        raise ValueError(f"{name} must be finite with shape [positive channels, 4]")
    return array


def _immutable_array(array: FloatArray) -> FloatArray:
    """Own a byte-backed snapshot whose write flag cannot be re-enabled."""
    return np.frombuffer(array.tobytes(), dtype=np.float64).reshape(array.shape)


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
        object.__setattr__(self, "key", _immutable_array(key))
        object.__setattr__(self, "residual", _immutable_array(residual))


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


@dataclass(frozen=True, init=False, eq=False)
class EpisodicResidualMemory:
    """Immutable query surface over training-only residual entries."""

    entries: tuple[MemoryEntry, ...]
    metric_weights: FloatArray
    temperature: float
    maximum_neighbors: int
    digest: str
    _keys: FloatArray
    _residuals: FloatArray

    def __init__(
        self,
        entries: Iterable[MemoryEntry],
        *,
        metric_weights: Sequence[float] | None = None,
        temperature: float = 1.0,
        maximum_neighbors: int = 16,
    ) -> None:
        object.__setattr__(self, "entries", tuple(entries))
        if not self.entries:
            raise ValueError("episodic memory requires at least one entry")
        if len({entry.entry_id for entry in self.entries}) != len(self.entries):
            raise ValueError("memory entry_id values must be unique")
        shape = self.entries[0].key.shape
        if any(entry.key.shape != shape for entry in self.entries):
            raise ValueError("all memory entries must have equal key shapes")
        if not math.isfinite(temperature) or temperature <= 0.0:
            raise ValueError("temperature must be positive and finite")
        if isinstance(maximum_neighbors, (bool, np.bool_)):
            raise ValueError("maximum_neighbors must be a positive integer")
        try:
            maximum_neighbors = index(maximum_neighbors)
        except TypeError as exc:
            raise ValueError("maximum_neighbors must be a positive integer") from exc
        if maximum_neighbors < 1:
            raise ValueError("maximum_neighbors must be a positive integer")
        if metric_weights is None:
            metric = np.ones(shape[0], dtype=np.float64)
        else:
            raw_metric = np.asarray(metric_weights)
            if raw_metric.dtype.kind not in "iuf":
                raise ValueError("metric_weights must contain real numeric values")
            metric = np.asarray(raw_metric, dtype=np.float64)
        if metric.shape != (shape[0],) or np.any(~np.isfinite(metric)) or np.any(metric <= 0.0):
            raise ValueError("metric_weights must be positive and match quaternion channels")
        # Divide first to avoid overflowing the mean of large, valid weights.
        metric = metric / float(metric.max())
        metric = metric / float(metric.mean())
        if np.any(metric <= 0.0):
            raise ValueError("metric_weights dynamic range is not representable")
        object.__setattr__(self, "metric_weights", _immutable_array(metric))
        object.__setattr__(self, "temperature", float(temperature))
        object.__setattr__(self, "maximum_neighbors", maximum_neighbors)
        object.__setattr__(
            self, "_keys", _immutable_array(np.stack([entry.key for entry in self.entries]))
        )
        object.__setattr__(
            self,
            "_residuals",
            _immutable_array(np.stack([entry.residual for entry in self.entries])),
        )
        digest = digest_value(
            {
                "schema": "siderea.episodic_residual_memory.v2",
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
                "temperature": self.temperature,
                "maximum_neighbors": maximum_neighbors,
            }
        )
        object.__setattr__(self, "digest", digest)

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
        if force_gate is not None and (
            not math.isfinite(force_gate) or not 0.0 <= force_gate <= 1.0
        ):
            raise ValueError("force_gate must lie within [0, 1]")

        eligible = [
            entry_index
            for entry_index, entry in enumerate(self.entries)
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
        # Evaluate the same weighted quaternion metric in one vectorized kernel.
        with np.errstate(over="ignore", invalid="ignore"):
            channel_distances = np.sum((key - self._keys[eligible]) ** 2, axis=2)
            all_distances = np.mean(self.metric_weights * channel_distances, axis=1)
        if np.any(~np.isfinite(all_distances)):
            raise ValueError("memory distance exceeds the finite float64 domain")
        ordered = np.lexsort(([self.entries[i].entry_id for i in eligible], all_distances))
        selected = ordered[: self.maximum_neighbors]
        neighbor_indices = np.asarray(eligible)[selected]
        distances = all_distances[selected]
        logits = -(distances - distances.min()) / self.temperature
        raw_weights = np.exp(logits)
        weights = raw_weights / raw_weights.sum()
        residual = np.sum(
            self._residuals[neighbor_indices] * weights[:, None, None],
            axis=0,
        )
        entropy = float(-np.sum(weights * np.log(np.maximum(weights, np.finfo(float).tiny))))
        normalized_entropy = entropy / math.log(len(weights)) if len(weights) > 1 else 0.0
        automatic_gate = 1.0 / (1.0 + math.exp(min(60.0, distances[0])))
        automatic_gate *= 1.0 - 0.5 * normalized_entropy
        gate = automatic_gate if force_gate is None else force_gate
        with np.errstate(over="ignore", invalid="ignore"):
            corrected = base + gate * residual
        if np.any(~np.isfinite(residual)) or np.any(~np.isfinite(corrected)):
            raise ValueError("memory correction exceeds the finite float64 domain")
        return RetrievalResult(
            residual=residual,
            gate=gate,
            corrected=corrected,
            neighbor_ids=tuple(self.entries[i].entry_id for i in neighbor_indices),
            weights=tuple(float(value) for value in weights),
            nearest_distance=float(distances[0]),
            entropy=entropy,
            supported=True,
        )


__all__ = ["EpisodicResidualMemory", "MemoryEntry", "RetrievalResult"]
