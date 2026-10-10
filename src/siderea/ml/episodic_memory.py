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


def _contains_boolean(value: Any) -> bool:
    if isinstance(value, np.ndarray):
        return bool(value.dtype.kind == "b")
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_boolean(item) for item in value)
    return isinstance(value, (bool, np.bool_))


def _quaternion_array(value: Any, name: str) -> FloatArray:
    array = np.asarray(value)
    if (
        array.ndim != 2
        or array.shape[0] < 1
        or array.shape[1] != 4
        or array.dtype.kind not in "iuf"
        or _contains_boolean(value)
        or np.any(~np.isfinite(array))
    ):
        raise ValueError(f"{name} must contain finite real values with shape [channels > 0, 4]")
    with np.errstate(over="ignore"):
        array = array.astype(np.float64)
    if np.any(~np.isfinite(array)):
        raise ValueError(f"{name} exceeds the finite float64 range")
    return array


def _finite_real(value: Any, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    try:
        converted = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real number") from exc
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be a finite real number")
    return converted


@dataclass(frozen=True, init=False)
class MemoryEntry:
    entry_id: str
    source_group: str
    cutoff_mjd: float
    population: str
    calibration: str
    _key_bytes: bytes
    _residual_bytes: bytes
    _shape: tuple[int, int]

    def __init__(
        self,
        entry_id: str,
        key: Any,
        residual: Any,
        source_group: str,
        cutoff_mjd: float,
        population: str,
        calibration: str,
    ) -> None:
        for name, value in (
            ("entry_id", entry_id),
            ("source_group", source_group),
            ("population", population),
            ("calibration", calibration),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"memory {name} must be a non-empty string")
            object.__setattr__(self, name, value)
        key_array = _quaternion_array(key, "key")
        residual_array = _quaternion_array(residual, "residual")
        if key_array.shape != residual_array.shape:
            raise ValueError("memory key and residual must have equal shapes")
        object.__setattr__(self, "cutoff_mjd", _finite_real(cutoff_mjd, "memory cutoff_mjd"))
        object.__setattr__(self, "_key_bytes", key_array.tobytes())
        object.__setattr__(self, "_residual_bytes", residual_array.tobytes())
        object.__setattr__(self, "_shape", (key_array.shape[0], key_array.shape[1]))

    @property
    def key(self) -> FloatArray:
        # Fresh views prevent callers from changing the stored shape or dtype;
        # immutable bytes also prevent re-enabling writes to the array contents.
        return np.frombuffer(self._key_bytes, dtype=np.float64).reshape(self._shape)

    @property
    def residual(self) -> FloatArray:
        return np.frombuffer(self._residual_bytes, dtype=np.float64).reshape(self._shape)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> MemoryEntry:
        required = {
            "entry_id",
            "key",
            "residual",
            "source_group",
            "cutoff_mjd",
            "population",
            "calibration",
        }
        if set(payload) != required:
            raise ValueError("memory entry fields differ from the supported schema")
        return cls(**dict(payload))


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
    _metric_bytes: bytes
    temperature: float
    maximum_neighbors: int
    digest: str

    @property
    def metric_weights(self) -> FloatArray:
        return np.frombuffer(self._metric_bytes, dtype=np.float64)

    def __init__(
        self,
        entries: Iterable[MemoryEntry],
        *,
        metric_weights: Sequence[float] | None = None,
        temperature: float = 1.0,
        maximum_neighbors: int = 16,
    ) -> None:
        entry_tuple = tuple(entries)
        if not entry_tuple:
            raise ValueError("episodic memory requires at least one entry")
        if any(not isinstance(entry, MemoryEntry) for entry in entry_tuple):
            raise ValueError("episodic memory entries must be MemoryEntry values")
        if len({entry.entry_id for entry in entry_tuple}) != len(entry_tuple):
            raise ValueError("memory entry IDs must be unique")
        shape = entry_tuple[0].key.shape
        if any(entry.key.shape != shape for entry in entry_tuple):
            raise ValueError("all memory entries must have equal key shapes")
        temperature = _finite_real(temperature, "temperature")
        if temperature <= 0.0:
            raise ValueError("temperature must be positive and finite")
        if (
            isinstance(maximum_neighbors, bool)
            or not isinstance(maximum_neighbors, int)
            or maximum_neighbors < 1
        ):
            raise ValueError("maximum_neighbors must be a positive integer")
        if metric_weights is None:
            metric = np.ones(shape[0], dtype=np.float64)
        else:
            metric = np.asarray(metric_weights)
        if (
            metric.shape != (shape[0],)
            or metric.dtype.kind not in "iuf"
            or _contains_boolean(metric_weights)
            or np.any(~np.isfinite(metric))
            or np.any(metric <= 0.0)
        ):
            raise ValueError("metric_weights must be positive and match quaternion channels")
        with np.errstate(over="ignore"):
            metric = metric.astype(np.float64)
            mean = float(metric.mean())
        if np.any(~np.isfinite(metric)):
            raise ValueError("metric_weights exceeds the finite float64 range")
        if not math.isfinite(mean) or mean == 0.0:
            metric = metric / float(metric.max())
            mean = float(metric.mean())
        normalized = metric / mean
        if np.any(~np.isfinite(normalized)) or np.any(normalized <= 0.0):
            raise ValueError("normalized metric_weights exceeds the positive finite range")
        object.__setattr__(self, "entries", entry_tuple)
        object.__setattr__(self, "_metric_bytes", normalized.tobytes())
        object.__setattr__(self, "temperature", temperature)
        object.__setattr__(self, "maximum_neighbors", maximum_neighbors)
        digest = digest_value(
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
        object.__setattr__(self, "digest", digest)

    @classmethod
    def from_artifact(cls, payload: Mapping[str, Any]) -> EpisodicResidualMemory:
        """Read the uniform-metric v1 CLI artifact and verify its recorded identity."""
        required = {
            "schema",
            "entry_count",
            "temperature",
            "maximum_neighbors",
            "memory_digest",
            "entries",
        }
        if set(payload) != required or payload.get("schema") != "siderea.space_jepa_v2_memory.v1":
            raise ValueError("APENic memory artifact schema differs")
        entries = payload["entries"]
        if not isinstance(entries, list) or any(not isinstance(item, Mapping) for item in entries):
            raise ValueError("APENic memory artifact lacks entry objects")
        count = payload["entry_count"]
        if isinstance(count, bool) or not isinstance(count, int) or count != len(entries):
            raise ValueError("APENic memory artifact entry_count differs")
        memory = cls(
            [MemoryEntry.from_mapping(item) for item in entries],
            temperature=payload["temperature"],
            maximum_neighbors=payload["maximum_neighbors"],
        )
        if payload["memory_digest"] != memory.digest:
            raise ValueError("APENic memory artifact digest differs")
        return memory

    def _distance(self, query: FloatArray, entry: MemoryEntry) -> float:
        with np.errstate(over="ignore", invalid="ignore"):
            channel_distance = np.sum((query - entry.key) ** 2, axis=1)
            distance = float(np.mean(self.metric_weights * channel_distance))
        if not math.isfinite(distance):
            raise ValueError("memory distance exceeds the finite numeric range")
        return distance

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
        for name, value in (
            ("query_source_group", query_source_group),
            ("population", population),
            ("calibration", calibration),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        _finite_real(query_cutoff_mjd, "query_cutoff_mjd")
        if not isinstance(allow_cross_population, bool):
            raise ValueError("allow_cross_population must be a boolean")
        if force_gate is not None and not 0.0 <= _finite_real(force_gate, "force_gate") <= 1.0:
            raise ValueError("force_gate must lie within [0, 1]")

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
        # Overflow to -inf here is a valid zero softmax weight. The nearest
        # distance always has a zero logit after finite-distance validation.
        with np.errstate(over="ignore"):
            logits = -(distances - distances.min()) / self.temperature
        raw_weights = np.exp(logits)
        weights = raw_weights / raw_weights.sum()
        with np.errstate(over="ignore", invalid="ignore"):
            residual = np.sum(
                np.stack([entry.residual for _, entry in ranked]) * weights[:, None, None],
                axis=0,
            )
        if np.any(~np.isfinite(residual)):
            raise ValueError("memory residual exceeds the finite numeric range")
        entropy = float(-np.sum(weights * np.log(np.maximum(weights, np.finfo(float).tiny))))
        normalized_entropy = entropy / math.log(len(weights)) if len(weights) > 1 else 0.0
        automatic_gate = 1.0 / (1.0 + math.exp(min(60.0, distances[0])))
        automatic_gate *= 1.0 - 0.5 * normalized_entropy
        gate = automatic_gate if force_gate is None else force_gate
        with np.errstate(over="ignore", invalid="ignore"):
            corrected = base + gate * residual
        if np.any(~np.isfinite(corrected)):
            raise ValueError("memory correction exceeds the finite numeric range")
        return RetrievalResult(
            residual=residual,
            gate=gate,
            corrected=corrected,
            neighbor_ids=tuple(entry.entry_id for _, entry in ranked),
            weights=tuple(float(value) for value in weights),
            nearest_distance=float(distances[0]),
            entropy=entropy,
            supported=True,
        )


__all__ = ["EpisodicResidualMemory", "MemoryEntry", "RetrievalResult"]
