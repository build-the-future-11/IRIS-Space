"""Versioned passband-response contracts for Space JEPA 2 physics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from siderea.provenance import digest_file, digest_value

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class Passband:
    identifier: str
    frequency_hz: FloatArray
    transmission: FloatArray
    counting_convention: str
    source_sha256: str
    contract_digest: str


def load_passband_csv(
    path: str | Path,
    *,
    identifier: str,
    frequency_column: str = "frequency_hz",
    transmission_column: str = "transmission",
    counting_convention: str,
) -> Passband:
    source = Path(path).expanduser().resolve()
    name = identifier.strip()
    if not name:
        raise ValueError("passband identifier must not be empty")
    if counting_convention not in {"photon", "energy"}:
        raise ValueError("counting_convention must be photon or energy")
    frame = pd.read_csv(source)
    missing = sorted({frequency_column, transmission_column} - set(frame.columns))
    if missing:
        raise ValueError(f"passband table is missing columns: {missing}")
    frequency = pd.to_numeric(frame[frequency_column], errors="raise").to_numpy(dtype=np.float64)
    transmission = pd.to_numeric(frame[transmission_column], errors="raise").to_numpy(
        dtype=np.float64
    )
    if len(frequency) < 2 or np.any(~np.isfinite(frequency)) or np.any(frequency <= 0.0):
        raise ValueError("passband frequencies must contain at least two positive finite values")
    if np.any(~np.isfinite(transmission)) or np.any(transmission < 0.0):
        raise ValueError("passband transmission must be finite and non-negative")
    if not np.any(transmission > 0.0):
        raise ValueError("passband transmission must have positive support")
    order = np.argsort(frequency)
    frequency = frequency[order]
    transmission = transmission[order]
    if np.any(np.diff(frequency) <= 0.0):
        raise ValueError("passband frequencies must be unique")
    source_sha256 = digest_file(source)
    contract = {
        "identifier": name,
        "frequency_hz": frequency.tolist(),
        "transmission": transmission.tolist(),
        "counting_convention": counting_convention,
        "source_sha256": source_sha256,
    }
    return Passband(
        identifier=name,
        frequency_hz=frequency,
        transmission=transmission,
        counting_convention=counting_convention,
        source_sha256=source_sha256,
        contract_digest=digest_value(contract),
    )


def effective_frequency_hz(passband: Passband) -> float:
    weight = passband.transmission
    denominator = float(np.trapezoid(weight, passband.frequency_hz))
    if not math.isfinite(denominator) or denominator <= 0.0:
        raise ValueError("passband has zero integrated transmission")
    return float(np.trapezoid(passband.frequency_hz * weight, passband.frequency_hz) / denominator)


__all__ = ["Passband", "effective_frequency_hz", "load_passband_csv"]
