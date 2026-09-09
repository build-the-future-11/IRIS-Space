"""Order-independent stochastic trial identity for robust transient-search v2.

This module generates random-number generators, not scientific outcomes. It
implements the pre-result v2.0.4 amendment so a semantic trial keeps the same
random stream even if runner loop order, batching, or candidate iteration is
refactored later.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from siderea.provenance import stable_json
from siderea.research.robust_protocol import FROZEN_PROTOCOL_GIT_BLOB_SHA1

FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1 = "139c6832004bd5a945c9a96c5c30e4b006154880"
FROZEN_IDENTIFIER_ERRATUM_GIT_BLOB_SHA1 = "dee0cb3b256e4823e784466e8b5df6041482c3b5"
TRIAL_RNG_SCHEMA = "siderea.robust_search_trial_rng.v2"
TRIAL_KEY_FIELDS = (
    "phase",
    "role",
    "cadence_id",
    "null_regime",
    "candidate_id",
    "signal_family",
    "signal_width_days",
    "amplitude_sigma",
    "noise_regime",
    "probe_id",
    "trial_index",
)


def _git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git object identity


def verify_frozen_trial_rng_amendment(path: Path) -> dict[str, Any]:
    """Verify exact v2.0.4 amendment bytes and its stochastic-identity contract."""

    raw = path.read_bytes()
    actual = _git_blob_sha1(raw)
    if actual != FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1:
        raise RuntimeError(
            "robust-search v2.0.4 trial-RNG amendment differs from the frozen "
            f"predevelopment artifact: expected git blob "
            f"{FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1}, got {actual}; create a "
            "new versioned amendment before generating any result"
        )
    amendment = json.loads(raw)
    if amendment.get("schema") != "siderea.robust_search_protocol_amendment.v2.0.4":
        raise ValueError("unexpected robust-search trial-RNG amendment schema")
    if amendment.get("status") != "frozen_before_any_v2_candidate_development_evaluation":
        raise ValueError("trial-RNG amendment is not marked frozen before development")
    if amendment.get("base_protocol_git_blob_sha1") != FROZEN_PROTOCOL_GIT_BLOB_SHA1:
        raise ValueError("trial-RNG amendment is not bound to the frozen base protocol")
    if (
        amendment.get("previous_amendment_git_blob_sha1")
        != FROZEN_IDENTIFIER_ERRATUM_GIT_BLOB_SHA1
    ):
        raise ValueError("trial-RNG amendment is not bound to the frozen v2.0.3 erratum")

    observed = amendment.get("observed_before_amendment")
    if not isinstance(observed, dict):
        raise ValueError("trial-RNG amendment is missing observed-before state")
    forbidden = (
        "v2_candidate_development_statistics",
        "v2_calibration_statistics",
        "v2_locked_evaluation_statistics",
        "v2_generalization_probe_statistics",
    )
    if any(observed.get(name) is not False for name in forbidden):
        raise ValueError("trial-RNG amendment must remain explicitly pre-result")

    changes = amendment.get("changes")
    contract = changes.get("deterministic_trial_rng") if isinstance(changes, dict) else None
    if not isinstance(contract, dict):
        raise ValueError("trial-RNG amendment is missing deterministic_trial_rng")
    if contract.get("canonical_key_schema") != TRIAL_RNG_SCHEMA:
        raise ValueError("trial-RNG canonical key schema drifted")
    if tuple(contract.get("canonical_key_fields", ())) != TRIAL_KEY_FIELDS:
        raise ValueError("trial-RNG canonical key fields drifted")
    if contract.get("numpy_bit_generator") != (
        "numpy.random.Generator(numpy.random.PCG64(numpy.random.SeedSequence(seed_words)))"
    ):
        raise ValueError("trial-RNG NumPy bit generator drifted")
    return amendment


def _optional_text(value: str | None, *, field: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(f"{field} must be a non-empty string or null")
    return value


def _optional_number(value: float | None, *, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field} must be a finite number or null")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def canonical_trial_key(
    *,
    phase: str,
    role: str,
    cadence_id: str | None,
    null_regime: str | None,
    candidate_id: str | None,
    signal_family: str | None,
    signal_width_days: float | None,
    amplitude_sigma: float | None,
    noise_regime: str | None,
    probe_id: str | None,
    trial_index: int,
) -> str:
    """Return the exact semantic trial key committed by v2.0.4."""

    if not isinstance(phase, str) or not phase:
        raise ValueError("phase must be a non-empty string")
    if not isinstance(role, str) or not role:
        raise ValueError("role must be a non-empty string")
    if isinstance(trial_index, bool) or not isinstance(trial_index, int) or trial_index < 0:
        raise ValueError("trial_index must be a nonnegative integer")

    payload = {
        "schema": TRIAL_RNG_SCHEMA,
        "phase": phase,
        "role": role,
        "cadence_id": _optional_text(cadence_id, field="cadence_id"),
        "null_regime": _optional_text(null_regime, field="null_regime"),
        "candidate_id": _optional_text(candidate_id, field="candidate_id"),
        "signal_family": _optional_text(signal_family, field="signal_family"),
        "signal_width_days": _optional_number(signal_width_days, field="signal_width_days"),
        "amplitude_sigma": _optional_number(amplitude_sigma, field="amplitude_sigma"),
        "noise_regime": _optional_text(noise_regime, field="noise_regime"),
        "probe_id": _optional_text(probe_id, field="probe_id"),
        "trial_index": trial_index,
    }
    return stable_json(payload)


def _validate_canonical_trial_key(canonical_key_json: str) -> None:
    """Reject partial, extra-field, malformed, or noncanonical semantic trial keys."""

    try:
        parsed = json.loads(canonical_key_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("canonical_key_json is not a canonical v2 trial key") from exc
    if not isinstance(parsed, dict):
        raise ValueError("canonical_key_json is not a canonical v2 trial key")

    expected_fields = {"schema", *TRIAL_KEY_FIELDS}
    if set(parsed) != expected_fields or parsed.get("schema") != TRIAL_RNG_SCHEMA:
        raise ValueError("canonical_key_json is not a canonical v2 trial key")

    try:
        rebuilt = canonical_trial_key(
            phase=parsed["phase"],
            role=parsed["role"],
            cadence_id=parsed["cadence_id"],
            null_regime=parsed["null_regime"],
            candidate_id=parsed["candidate_id"],
            signal_family=parsed["signal_family"],
            signal_width_days=parsed["signal_width_days"],
            amplitude_sigma=parsed["amplitude_sigma"],
            noise_regime=parsed["noise_regime"],
            probe_id=parsed["probe_id"],
            trial_index=parsed["trial_index"],
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("canonical_key_json is not a canonical v2 trial key") from exc
    if rebuilt != canonical_key_json:
        raise ValueError("canonical_key_json is not a canonical v2 trial key")


def trial_seed_words(phase_seed: int, canonical_key_json: str) -> tuple[int, int, int, int]:
    """Derive four big-endian uint32 seed words from phase seed plus canonical key."""

    if isinstance(phase_seed, bool) or not isinstance(phase_seed, int) or phase_seed < 0:
        raise ValueError("phase_seed must be a nonnegative integer")
    _validate_canonical_trial_key(canonical_key_json)

    digest = hashlib.sha256(f"{phase_seed}\n{canonical_key_json}".encode("utf-8")).digest()
    return tuple(
        int.from_bytes(digest[offset : offset + 4], "big") for offset in range(0, 16, 4)
    )


def trial_rng(phase_seed: int, canonical_key_json: str) -> np.random.Generator:
    """Construct the frozen PCG64 stream for one semantic trial."""

    words = trial_seed_words(phase_seed, canonical_key_json)
    seed_sequence = np.random.SeedSequence(words)
    return np.random.Generator(np.random.PCG64(seed_sequence))


def trial_identity(phase_seed: int, canonical_key_json: str) -> dict[str, Any]:
    """Return compact provenance suitable for a per-trial evidence row."""

    words = trial_seed_words(phase_seed, canonical_key_json)
    return {
        "schema": TRIAL_RNG_SCHEMA,
        "canonical_key_json": canonical_key_json,
        "canonical_key_sha256": hashlib.sha256(canonical_key_json.encode("utf-8")).hexdigest(),
        "phase_seed": phase_seed,
        "seed_words": list(words),
        "bit_generator": "PCG64",
    }


__all__ = [
    "FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1",
    "TRIAL_KEY_FIELDS",
    "TRIAL_RNG_SCHEMA",
    "canonical_trial_key",
    "trial_identity",
    "trial_rng",
    "trial_seed_words",
    "verify_frozen_trial_rng_amendment",
]
