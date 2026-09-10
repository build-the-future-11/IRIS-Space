"""Integrity helpers for the frozen robust transient-search v2 study.

This module contains no scientific result and runs no candidate evaluation.  It
exists to make two preregistration promises mechanical before development data
are generated:

* the machine-readable protocol must be byte-for-byte the frozen protocol; and
* the 20 irregular plus 5 seasonal-gap cadence realizations are deterministically
  fixed from the preregistered cadence seed.

A changed protocol or a changed cadence generator fails closed.  Any deliberate
change therefore requires a new versioned protocol/lock rather than silently
changing the inputs to an already named study.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from siderea.provenance import stable_json

# Git's content-addressed blob identifier for robust_search_protocol.v2.json on
# the branch at the moment the prospective v2 protocol was frozen.  This binds
# the exact bytes, including whitespace, without modifying the frozen document.
FROZEN_PROTOCOL_GIT_BLOB_SHA1 = "9ab09a2ad2702649fe31ab19eb8b73d45fc7d60b"

# SHA-256 of ``stable_json(build_cadence_manifest(protocol)) + "\n"`` for the
# frozen protocol.  The digest commits the exact 25 x 64 time arrays before any
# v2 candidate is evaluated, while keeping the source tree compact.
FROZEN_CADENCE_MANIFEST_SHA256 = "5abfdaa328f5793e92bed7aa6dcfaade44ac1a54a1996b8c310e51112dc72451"


def _git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git object identity


def verify_frozen_protocol(path: Path) -> dict[str, Any]:
    """Return the parsed v2 protocol only if the exact frozen bytes are present."""

    raw = path.read_bytes()
    actual = _git_blob_sha1(raw)
    if actual != FROZEN_PROTOCOL_GIT_BLOB_SHA1:
        raise RuntimeError(
            "robust-search v2 protocol differs from the frozen preregistration: "
            f"expected git blob {FROZEN_PROTOCOL_GIT_BLOB_SHA1}, got {actual}; "
            "create a versioned amendment instead of running this study"
        )
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("robust-search protocol must be a JSON object")
    config: dict[str, Any] = parsed
    if config.get("schema") != "siderea.robust_search_protocol.v2":
        raise ValueError("unexpected robust-search protocol schema")
    if config.get("status") != "frozen_before_v2_development_execution":
        raise ValueError("robust-search protocol is not marked frozen before development")

    design = config.get("design")
    if not isinstance(design, dict):
        raise ValueError("robust-search protocol is missing design")
    expected = {
        "duration_days": 60,
        "epochs_per_curve": 64,
        "cadence_realizations": 20,
        "seasonal_gap_cadence_realizations": 5,
        "cadence_seed": 2026091120,
    }
    for key, value in expected.items():
        if design.get(key) != value:
            raise ValueError(f"frozen design field {key!r} does not match its lock")

    phase_seeds = [
        design.get("development_seed"),
        design.get("calibration_seed"),
        design.get("locked_evaluation_seed"),
    ]
    if any(type(seed) is not int or seed < 0 for seed in phase_seeds):
        raise ValueError("development/calibration/locked seeds must be nonnegative integers")
    if len(set(phase_seeds)) != len(phase_seeds):
        raise ValueError("development, calibration, and locked-evaluation seeds must be disjoint")
    return config


def build_cadence_manifest(config: dict[str, Any]) -> dict[str, Any]:
    """Build the exact preregistered cadence inputs without evaluating a method.

    The generation rule deliberately mirrors the repository's earlier synthetic
    experiments: ordinary cadences are sorted uniform arrivals over 60 days;
    seasonal-gap cadences use 32 arrivals in days [0, 20] and 32 in [40, 60].
    Each cadence receives an independent child SeedSequence so generating one
    cadence cannot change any later cadence's random stream.
    """

    design = config["design"]
    ordinary_count = int(design["cadence_realizations"])
    gap_count = int(design["seasonal_gap_cadence_realizations"])
    epochs = int(design["epochs_per_curve"])
    duration = float(design["duration_days"])
    if epochs % 2:
        raise ValueError("seasonal-gap cadence generation requires an even epoch count")

    total = ordinary_count + gap_count
    children = np.random.SeedSequence(int(design["cadence_seed"])).spawn(total)
    cadences: list[dict[str, Any]] = []
    for index, child in enumerate(children):
        rng = np.random.default_rng(child)
        if index < ordinary_count:
            kind = "irregular"
            number = index + 1
            times = np.sort(rng.uniform(0.0, duration, epochs))
        else:
            kind = "seasonal_gap"
            number = index - ordinary_count + 1
            half = epochs // 2
            times = np.sort(
                np.concatenate(
                    [
                        rng.uniform(0.0, duration / 3.0, half),
                        rng.uniform(2.0 * duration / 3.0, duration, epochs - half),
                    ]
                )
            )
        cadences.append(
            {
                "id": f"{kind}_{number:02d}",
                "kind": kind,
                "seed_spawn_index": index,
                "times_days": [float(value) for value in times],
            }
        )

    return {
        "schema": "siderea.robust_search_cadences.v2",
        "protocol": "robust_search_protocol.v2.json",
        "cadence_seed": int(design["cadence_seed"]),
        "generator": {
            "numpy_rng": "default_rng(SeedSequence(cadence_seed).spawn(25)[index])",
            "irregular": "sort(Uniform(0,60), size=64)",
            "seasonal_gap": ("sort(concat(Uniform(0,20), size=32; Uniform(40,60), size=32))"),
            "note": (
                "Frozen before any v2 candidate development evaluation; these times are "
                "inputs, not results."
            ),
        },
        "cadences": cadences,
    }


def cadence_manifest_bytes(config: dict[str, Any]) -> bytes:
    return (stable_json(build_cadence_manifest(config)) + "\n").encode("utf-8")


def verify_cadence_manifest(config: dict[str, Any]) -> bytes:
    """Return exact cadence JSON bytes only if they match the preregistered digest."""

    encoded = cadence_manifest_bytes(config)
    actual = hashlib.sha256(encoded).hexdigest()
    if actual != FROZEN_CADENCE_MANIFEST_SHA256:
        raise RuntimeError(
            "cadence generator no longer reproduces the frozen v2 cadence manifest: "
            f"expected {FROZEN_CADENCE_MANIFEST_SHA256}, got {actual}"
        )
    return encoded


def materialize_cadence_manifest(protocol_path: Path, destination: Path) -> str:
    """Write the exact cadence definitions once and return their SHA-256 digest."""

    if destination.exists():
        raise FileExistsError("cadence manifest already exists; preserve the frozen artifact")
    config = verify_frozen_protocol(protocol_path)
    encoded = verify_cadence_manifest(config)
    destination.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "FROZEN_CADENCE_MANIFEST_SHA256",
    "FROZEN_PROTOCOL_GIT_BLOB_SHA1",
    "build_cadence_manifest",
    "cadence_manifest_bytes",
    "materialize_cadence_manifest",
    "verify_cadence_manifest",
    "verify_frozen_protocol",
]
