"""Fail-closed predevelopment execution locks for robust transient-search v2.

This module deliberately generates no candidate-performance statistic. It binds
the v2.0.1 scientific amendment, the v2.0.2 execution/analysis contract, the
v2.0.3 cadence-identifier erratum, and the amendment-mandated reported-error
vectors before a development runner is allowed to exist.

The base protocol and cadence times are locked in :mod:`robust_protocol`. This
module closes the remaining execution-contract gaps:

* exact v2.0.1, v2.0.2, and v2.0.3 amendment bytes must match pre-result artifacts;
* the effective candidate set and development split must match v2.0.1;
* signal/cadence allocation and bootstrap mechanics must match v2.0.2;
* canonical cadence identifiers must match the already-frozen generator via v2.0.3;
* one heteroskedastic reported-error vector is deterministically frozen for each
  of the 25 already-frozen cadence realizations; and
* the committed lock must bind the complete generated vector manifest by SHA-256.

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
FROZEN_EXECUTION_AMENDMENT_GIT_BLOB_SHA1 = "52fdce6a876e189450beb87d08326597a8473f67"
FROZEN_IDENTIFIER_ERRATUM_GIT_BLOB_SHA1 = "dee0cb3b256e4823e784466e8b5df6041482c3b5"
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


def _verify_pre_result_observed(payload: dict[str, Any], *, label: str) -> None:
    observed = payload.get("observed_before_amendment")
    if not isinstance(observed, dict):
        raise ValueError(f"{label} is missing observed-before state")
    forbidden_observed = (
        "v2_candidate_development_statistics",
        "v2_calibration_statistics",
        "v2_locked_evaluation_statistics",
        "v2_generalization_probe_statistics",
    )
    if any(observed.get(name) is not False for name in forbidden_observed):
        raise ValueError(f"{label} must remain explicitly pre-result for every v2 phase")


def verify_frozen_amendment(
    amendment_path: Path,
    protocol_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify the exact pre-result v2.0.1 amendment and base-protocol binding."""

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
    _verify_pre_result_observed(amendment, label="robust-search amendment")

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


def verify_frozen_execution_amendment(
    execution_amendment_path: Path,
    amendment_path: Path,
    protocol_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Verify the pre-result v2.0.2 execution and analysis contract."""

    protocol, amendment = verify_frozen_amendment(amendment_path, protocol_path)
    raw = execution_amendment_path.read_bytes()
    actual = _git_blob_sha1(raw)
    if actual != FROZEN_EXECUTION_AMENDMENT_GIT_BLOB_SHA1:
        raise RuntimeError(
            "robust-search v2.0.2 execution amendment differs from the frozen "
            f"predevelopment artifact: expected git blob "
            f"{FROZEN_EXECUTION_AMENDMENT_GIT_BLOB_SHA1}, got {actual}; create a new "
            "versioned amendment before generating any result"
        )

    execution_amendment = json.loads(raw)
    if execution_amendment.get("schema") != "siderea.robust_search_protocol_amendment.v2.0.2":
        raise ValueError("unexpected robust-search execution-amendment schema")
    if execution_amendment.get("status") != (
        "frozen_before_any_v2_candidate_development_evaluation"
    ):
        raise ValueError("execution amendment is not marked frozen before development")
    if execution_amendment.get("base_protocol_git_blob_sha1") != FROZEN_PROTOCOL_GIT_BLOB_SHA1:
        raise ValueError("execution amendment is not bound to the frozen base protocol")
    if execution_amendment.get("previous_amendment_git_blob_sha1") != (
        FROZEN_AMENDMENT_GIT_BLOB_SHA1
    ):
        raise ValueError("execution amendment is not bound to the frozen v2.0.1 amendment")
    _verify_pre_result_observed(execution_amendment, label="execution amendment")

    changes = execution_amendment.get("changes")
    if not isinstance(changes, dict):
        raise ValueError("execution amendment is missing changes")

    null_allocation = changes.get("null_trial_allocation")
    if not isinstance(null_allocation, dict):
        raise ValueError("execution amendment is missing null-trial allocation")
    expected_allocations = {
        ("development_threshold_construction", "ordinary_trials_per_cadence_per_regime"): 50,
        ("development_threshold_construction", "seasonal_gap_trials_per_cadence"): 200,
        ("development_independent_feasibility", "ordinary_trials_per_cadence_per_regime"): 50,
        ("development_independent_feasibility", "seasonal_gap_trials_per_cadence"): 200,
        ("calibration", "ordinary_trials_per_cadence_per_regime"): 500,
        ("calibration", "seasonal_gap_trials_per_cadence"): 2000,
        ("locked_evaluation", "ordinary_trials_per_cadence_per_regime"): 250,
        ("locked_evaluation", "seasonal_gap_trials_per_cadence"): 1000,
    }
    for (section, key), expected in expected_allocations.items():
        block = null_allocation.get(section)
        if not isinstance(block, dict) or block.get(key) != expected:
            raise ValueError(f"frozen execution allocation {section}.{key} drifted")

    bootstrap = changes.get("paired_bootstrap")
    if not isinstance(bootstrap, dict):
        raise ValueError("execution amendment is missing paired-bootstrap contract")
    if bootstrap.get("cadence_count") != 25 or bootstrap.get("replicates") != 10000:
        raise ValueError("paired-bootstrap size drifted from the frozen execution contract")
    if bootstrap.get("rng") != "numpy.random.default_rng(2026091104)":
        raise ValueError("paired-bootstrap RNG drifted from the frozen execution contract")

    probes = changes.get("generalization_probe_allocation")
    if not isinstance(probes, dict) or probes.get("trials_per_probe") != 5000:
        raise ValueError("generalization-probe allocation drifted from the frozen contract")

    return protocol, amendment, execution_amendment


def verify_frozen_identifier_erratum(
    identifier_erratum_path: Path,
    execution_amendment_path: Path,
    amendment_path: Path,
    protocol_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Verify the pre-result v2.0.3 canonical cadence-identifier correction."""

    protocol, amendment, execution = verify_frozen_execution_amendment(
        execution_amendment_path,
        amendment_path,
        protocol_path,
    )
    raw = identifier_erratum_path.read_bytes()
    actual = _git_blob_sha1(raw)
    if actual != FROZEN_IDENTIFIER_ERRATUM_GIT_BLOB_SHA1:
        raise RuntimeError(
            "robust-search v2.0.3 identifier erratum differs from the frozen "
            f"predevelopment artifact: expected git blob "
            f"{FROZEN_IDENTIFIER_ERRATUM_GIT_BLOB_SHA1}, got {actual}; create a new "
            "versioned amendment before generating any result"
        )

    erratum = json.loads(raw)
    if erratum.get("schema") != "siderea.robust_search_protocol_amendment.v2.0.3":
        raise ValueError("unexpected robust-search identifier-erratum schema")
    if erratum.get("status") != "frozen_before_any_v2_candidate_development_evaluation":
        raise ValueError("identifier erratum is not marked frozen before development")
    if erratum.get("base_protocol_git_blob_sha1") != FROZEN_PROTOCOL_GIT_BLOB_SHA1:
        raise ValueError("identifier erratum is not bound to the frozen base protocol")
    if erratum.get("previous_amendment_git_blob_sha1") != (
        FROZEN_EXECUTION_AMENDMENT_GIT_BLOB_SHA1
    ):
        raise ValueError("identifier erratum is not bound to the frozen v2.0.2 amendment")
    _verify_pre_result_observed(erratum, label="identifier erratum")

    changes = erratum.get("changes")
    if not isinstance(changes, dict):
        raise ValueError("identifier erratum is missing changes")
    identifiers = changes.get("cadence_identifier_erratum")
    if not isinstance(identifiers, dict):
        raise ValueError("identifier erratum is missing canonical cadence identifiers")

    expected_ordinary = tuple(f"irregular_{index:02d}" for index in range(1, 21))
    expected_gap = tuple(f"seasonal_gap_{index:02d}" for index in range(1, 6))
    if identifiers.get("canonical_ordinary_kind") != "irregular":
        raise ValueError("canonical ordinary cadence kind drifted")
    if identifiers.get("canonical_seasonal_gap_kind") != "seasonal_gap":
        raise ValueError("canonical seasonal-gap cadence kind drifted")
    if tuple(identifiers.get("canonical_ordinary_ids", ())) != expected_ordinary:
        raise ValueError("canonical ordinary cadence identifiers drifted")
    if tuple(identifiers.get("canonical_seasonal_gap_ids", ())) != expected_gap:
        raise ValueError("canonical seasonal-gap cadence identifiers drifted")
    if identifiers.get("numeric_design_change") is not False:
        raise ValueError("v2.0.3 must remain an identifier-only erratum")

    cadence_rows = build_cadence_manifest(protocol)["cadences"]
    generated_ordinary = tuple(row["id"] for row in cadence_rows if row["kind"] == "irregular")
    generated_gap = tuple(row["id"] for row in cadence_rows if row["kind"] == "seasonal_gap")
    if generated_ordinary != expected_ordinary or generated_gap != expected_gap:
        raise RuntimeError("frozen cadence generator disagrees with canonical v2.0.3 identifiers")

    return protocol, amendment, execution, erratum


def build_reported_error_manifest(
    protocol: dict[str, Any],
    amendment: dict[str, Any],
) -> dict[str, Any]:
    """Build the exact amendment-mandated heteroskedastic error vectors."""

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
            "numpy_rng": "default_rng(SeedSequence(cadence_seed).spawn(50)[25 + cadence_index])",
            "distribution": "Uniform(0.7,1.3), size=64",
            "mapping": "children 25..49 correspond one-to-one to frozen cadence indices 0..24",
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


def verify_reported_error_lock(
    path: Path,
    protocol: dict[str, Any],
    amendment: dict[str, Any],
) -> str:
    """Verify that the committed pre-result lock binds the generated vectors."""

    generated = verify_reported_error_manifest(protocol, amendment)
    generated_sha256 = hashlib.sha256(generated).hexdigest()
    lock = json.loads(path.read_text(encoding="utf-8"))
    expected_fields: dict[str, Any] = {
        "schema": "siderea.robust_search_reported_errors_lock.v2",
        "status": "frozen_before_any_v2_candidate_development_evaluation",
        "protocol": "robust_search_protocol.v2.json",
        "amendment": "robust_search_amendment.v2.0.1.json",
        "cadence_seed": 2026091120,
        "vector_count": 25,
        "epochs_per_vector": 64,
        "distribution": "Uniform(0.7,1.3)",
        "seed_spawn_indices": [25, 49],
        "canonical_generated_manifest_sha256": FROZEN_REPORTED_ERRORS_MANIFEST_SHA256,
    }
    for key, expected in expected_fields.items():
        if lock.get(key) != expected:
            raise RuntimeError(f"reported-error precommitment field {key!r} drifted")
    if lock["canonical_generated_manifest_sha256"] != generated_sha256:
        raise RuntimeError("reported-error lock does not bind the deterministic generated manifest")
    return generated_sha256


def verify_predevelopment_inputs(
    protocol_path: Path,
    amendment_path: Path,
    execution_amendment_path: Path,
    identifier_erratum_path: Path,
    reported_error_lock_path: Path,
) -> dict[str, Any]:
    """Verify every predevelopment input lock without producing a scientific result."""

    protocol, amendment, _, _ = verify_frozen_identifier_erratum(
        identifier_erratum_path,
        execution_amendment_path,
        amendment_path,
        protocol_path,
    )
    errors_sha256 = verify_reported_error_lock(reported_error_lock_path, protocol, amendment)
    return {
        "status": "PASS_PREDEVELOPMENT_INPUT_LOCKS_NO_PERFORMANCE_STATISTICS",
        "protocol_git_blob_sha1": FROZEN_PROTOCOL_GIT_BLOB_SHA1,
        "amendment_git_blob_sha1": FROZEN_AMENDMENT_GIT_BLOB_SHA1,
        "execution_amendment_git_blob_sha1": FROZEN_EXECUTION_AMENDMENT_GIT_BLOB_SHA1,
        "identifier_erratum_git_blob_sha1": FROZEN_IDENTIFIER_ERRATUM_GIT_BLOB_SHA1,
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
    "FROZEN_EXECUTION_AMENDMENT_GIT_BLOB_SHA1",
    "FROZEN_IDENTIFIER_ERRATUM_GIT_BLOB_SHA1",
    "FROZEN_REPORTED_ERRORS_MANIFEST_SHA256",
    "build_reported_error_manifest",
    "reported_error_manifest_bytes",
    "verify_frozen_amendment",
    "verify_frozen_execution_amendment",
    "verify_frozen_identifier_erratum",
    "verify_predevelopment_inputs",
    "verify_reported_error_lock",
    "verify_reported_error_manifest",
]
