"""Fail-closed predevelopment execution locks for robust transient-search v2.

This module deliberately generates no candidate-performance statistic. It binds
the v2.0.1 amendment and the amendment-mandated reported-error vectors before a
development runner is allowed to exist.

The base protocol and cadence times are locked in :mod:`robust_protocol`. This
module closes the remaining execution-contract gap:

* the exact amendment bytes must match the pre-result v2.0.1 amendment;
* the effective candidate set and development split must match that amendment;
* one heteroskedastic reported-error vector is deterministically frozen for each
  of the 25 already-frozen cadence realizations; and
* a committed materialization of those vectors must match the deterministic
  bytes exactly.

No outcome, search statistic, threshold, recovery value, or false-alarm count is
computed here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from siderea.provenance import stable_json
from siderea.research.robust_protocol import (
    FROZEN_PROTOCOL_GIT_BLOB_SHA1,
    build_cadence_manifest,
    verify_frozen_protocol,
)

FROZEN_AMENDMENT_GIT_BLOB_SHA1 = "8262ffb14b95ea7c67164935b694ff41df31fa7b"
FROZEN_REPORTED_ERRORS_MANIFEST_SHA256 = (
    "c047f7c56138ba562ad41e960d8ee52b8c773d199c9347e64e0db39bde857bd7"
)
EFFECTIVE_CANDIDATES = (
    "raw_bank_envelope_calibrated",
    "selected_template_leave_one_out_stability",
)


def _git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git object identity


def verify_frozen_amendment(
    amendment_path: Path,
    protocol_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify the exact pre-result amendment and its binding to the base protocol."""

    protocol = verify_frozen_protocol(protocol_path)
    raw = amendment_path.read_bytes()
    actual = _git_blob_sha1(raw)
    if actual != FROZEN_AMENDMENT_GIT_BLOB_SHA1:
        raise RuntimeError(
            "robust-search v2.0.1 amendment differs from the frozen predevelopment "
            f"artifact: expected git blob {FROZEN_AMENDMENT_GIT_BLOB_SHA1}, got {actual}; "
            "create a new versioned amendment before generating any result"
        )

    amendment = json.loads(raw)
    if amendment.get("schema") != "siderea.robust_search_protocol_amendment.v2.0.1":
        raise ValueError("unexpected robust-search amendment schema")
    if amendment.get("status") != "frozen_before_any_v2_candidate_development_evaluation":
        raise ValueError("robust-search amendment is not marked frozen before development")
    if amendment.get("base_protocol_git_blob_sha1") != FROZEN_PROTOCOL_GIT_BLOB_SHA1:
        raise ValueError("robust-search amendment is not bound to the frozen base protocol")

    observed = amendment.get("observed_before_amendment")
    if not isinstance(observed, dict):
        raise ValueError("robust-search amendment is missing observed-before state")
    forbidden_observed = (
        "v2_candidate_development_statistics",
        "v2_calibration_statistics",
        "v2_locked_evaluation_statistics",
        "v2_generalization_probe_statistics",
    )
    if any(observed.get(name) is not False for name in forbidden_observed):
        raise ValueError("amendment must remain explicitly pre-result for every v2 phase")

    changes = amendment.get("changes")
    if not isinstance(changes, dict):
        raise ValueError("robust-search amendment is missing changes")
    candidate_change = changes.get("candidate_statistics")
    if not isinstance(candidate_change, dict):
        raise ValueError("robust-search amendment is missing candidate-statistic changes")
    if tuple(candidate_change.get("effective_candidates", ())) != EFFECTIVE_CANDIDATES:
        raise ValueError("effective v2 candidate set drifted from the frozen amendment")

    split = changes.get("development_null_split")
    if not isinstance(split, dict):
        raise ValueError("robust-search amendment is missing development-null split")
    expected_split = {
        "total_trials_per_regime_unchanged": 2000,
        "threshold_construction_trials_per_regime": 1000,
        "feasibility_evaluation_trials_per_regime": 1000,
    }
    for key, expected in expected_split.items():
        if split.get(key) != expected:
            raise ValueError(f"frozen development split field {key!r} drifted")

    return protocol, amendment


def build_reported_error_manifest(
    protocol: dict[str, Any],
    amendment: dict[str, Any],
) -> dict[str, Any]:
    """Build the exact amendment-mandated heteroskedastic error vectors.

    SeedSequence child indices 0..24 are reserved by the cadence lock. The
    amendment assigns children 25..49 to the 25 reported-error vectors. Using
    one child per cadence prevents any phase or candidate from advancing a
    shared RNG stream and thereby changing another cadence's errors.
    """

    design = protocol["design"]
    cadence_rows = build_cadence_manifest(protocol)["cadences"]
    total = len(cadence_rows)
    if total != 25:
        raise ValueError("reported-error lock requires exactly 25 frozen cadences")

    error_contract = amendment["changes"].get("reported_error_vectors")
    if not isinstance(error_contract, dict):
        raise ValueError("amendment is missing reported-error vector contract")

    cadence_seed = int(design["cadence_seed"])
    children = np.random.SeedSequence(cadence_seed).spawn(2 * total)
    vectors: list[dict[str, Any]] = []
    for cadence_index, cadence in enumerate(cadence_rows):
        child_index = total + cadence_index
        rng = np.random.default_rng(children[child_index])
        values = rng.uniform(0.7, 1.3, int(design["epochs_per_curve"]))
        vectors.append(
            {
                "cadence_index": cadence_index,
                "cadence_id": str(cadence["id"]),
                "seed_spawn_index": child_index,
                "reported_errors": [float(value) for value in values],
            }
        )

    return {
        "schema": "siderea.robust_search_reported_errors.v2",
        "protocol": "robust_search_protocol.v2.json",
        "amendment": "robust_search_amendment.v2.0.1.json",
        "cadence_seed": cadence_seed,
        "generator": {
            "numpy_rng": ("default_rng(SeedSequence(cadence_seed).spawn(50)[25 + cadence_index])"),
            "distribution": "Uniform(0.7,1.3), size=64",
            "mapping": ("children 25..49 correspond one-to-one to frozen cadence indices 0..24"),
            "note": (
                "Frozen before any v2 candidate development evaluation and reused across "
                "development, calibration, and locked evaluation."
            ),
        },
        "reported_error_vectors": vectors,
    }


def reported_error_manifest_bytes(
    protocol: dict[str, Any],
    amendment: dict[str, Any],
) -> bytes:
    return (stable_json(build_reported_error_manifest(protocol, amendment)) + "\n").encode("utf-8")


def verify_reported_error_manifest(
    protocol: dict[str, Any],
    amendment: dict[str, Any],
) -> bytes:
    """Return deterministic manifest bytes only if they match the precommitted digest."""

    encoded = reported_error_manifest_bytes(protocol, amendment)
    actual = hashlib.sha256(encoded).hexdigest()
    if actual != FROZEN_REPORTED_ERRORS_MANIFEST_SHA256:
        raise RuntimeError(
            "reported-error generator no longer reproduces the frozen v2 input manifest: "
            f"expected {FROZEN_REPORTED_ERRORS_MANIFEST_SHA256}, got {actual}"
        )
    return encoded


def verify_materialized_reported_errors(
    path: Path,
    protocol: dict[str, Any],
    amendment: dict[str, Any],
) -> str:
    """Fail closed unless the committed input artifact is byte-identical to the lock."""

    expected = verify_reported_error_manifest(protocol, amendment)
    actual = path.read_bytes()
    if actual != expected:
        raise RuntimeError(
            "materialized robust-search reported-error vectors differ from the frozen manifest"
        )
    return hashlib.sha256(actual).hexdigest()


def verify_predevelopment_inputs(
    protocol_path: Path,
    amendment_path: Path,
    reported_errors_path: Path,
) -> dict[str, Any]:
    """Verify every predevelopment input lock without producing a scientific result."""

    protocol, amendment = verify_frozen_amendment(amendment_path, protocol_path)
    errors_sha256 = verify_materialized_reported_errors(reported_errors_path, protocol, amendment)
    return {
        "status": "PASS_PREDEVELOPMENT_INPUT_LOCKS_NO_PERFORMANCE_STATISTICS",
        "protocol_git_blob_sha1": FROZEN_PROTOCOL_GIT_BLOB_SHA1,
        "amendment_git_blob_sha1": FROZEN_AMENDMENT_GIT_BLOB_SHA1,
        "reported_errors_sha256": errors_sha256,
        "effective_candidates": list(EFFECTIVE_CANDIDATES),
        "development_null_split": {
            "threshold_construction": 1000,
            "independent_feasibility": 1000,
        },
    }


__all__ = [
    "EFFECTIVE_CANDIDATES",
    "FROZEN_AMENDMENT_GIT_BLOB_SHA1",
    "FROZEN_REPORTED_ERRORS_MANIFEST_SHA256",
    "build_reported_error_manifest",
    "reported_error_manifest_bytes",
    "verify_frozen_amendment",
    "verify_materialized_reported_errors",
    "verify_predevelopment_inputs",
    "verify_reported_error_manifest",
]
