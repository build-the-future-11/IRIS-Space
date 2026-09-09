"""Outcome-free execution authority for SIDEREA robust-search compound probes.

The compound-nuisance extension is secondary and post-lock: it may constrain
claims, but it cannot change the frozen v2 candidate, threshold, promotion
rules, or primary result. This module freezes only stochastic trial identities
for that extension and generates no scientific outcome.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from siderea.provenance import stable_json

FROZEN_COMPOUND_EXTENSION_GIT_BLOB_SHA1 = "5fef19f439d5b581f317f30f5292bf5df6900e76"
FROZEN_COMPOUND_PLAN_LOCK_GIT_BLOB_SHA1 = "f37868143fd9fa9df0b3c02622043a4a878f3e5f"
COMPOUND_EXTENSION_SCHEMA = "siderea.robust_search_compound_nuisance_extension.v2"
COMPOUND_PLAN_LOCK_SCHEMA = "siderea.robust_search_compound_trial_plan_lock.v2"
COMPOUND_TRIAL_KEY_SCHEMA = "siderea.robust_search_compound_trial_rng.v1"
EXPECTED_EXTENSION_SEED = 2026091105
EXPECTED_TOTAL_TRIALS = 30_000
EXPECTED_PLAN_SHA256 = "618966be54879ba16eb10a13dd01e1b1b642a572d0f77b1f041577dd93b672de"
EXPECTED_PROBE_COUNTS = {
    "seasonal_gap_x_ar1_rho_0_7": 5_000,
    "seasonal_gap_x_errors_underestimated_factor_1_5": 5_000,
    "ar1_rho_0_7_x_errors_underestimated_factor_1_5": 5_000,
    "ar1_rho_0_7_x_single_positive_6sigma_outlier": 5_000,
    "student_t3_x_errors_underestimated_factor_1_5": 5_000,
    "variance_doubles_second_half_x_single_positive_6sigma_outlier": 5_000,
}


def _git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git object identity


def _cadence_ids(spec: str) -> tuple[str, ...]:
    if spec == "seasonal_gap_01..seasonal_gap_05":
        return tuple(f"seasonal_gap_{index:02d}" for index in range(1, 6))
    if spec == "irregular_01..irregular_20":
        return tuple(f"irregular_{index:02d}" for index in range(1, 21))
    raise ValueError(f"unrecognized frozen compound cadence specification: {spec!r}")


def canonical_compound_trial_key(
    *,
    probe_id: str,
    cadence_id: str,
    trial_index: int,
) -> str:
    """Return one canonical compound-extension trial identity and no outcome."""

    if not isinstance(probe_id, str) or not probe_id:
        raise ValueError("probe_id must be a non-empty string")
    if not isinstance(cadence_id, str) or not cadence_id:
        raise ValueError("cadence_id must be a non-empty string")
    if isinstance(trial_index, bool) or not isinstance(trial_index, int) or trial_index < 0:
        raise ValueError("trial_index must be a nonnegative integer")
    return stable_json(
        {
            "schema": COMPOUND_TRIAL_KEY_SCHEMA,
            "probe_id": probe_id,
            "cadence_id": cadence_id,
            "trial_index": trial_index,
        }
    )


def verify_frozen_compound_extension(path: Path) -> dict[str, Any]:
    """Verify exact pre-outcome extension bytes and its execution contract."""

    raw = path.read_bytes()
    actual = _git_blob_sha1(raw)
    if actual != FROZEN_COMPOUND_EXTENSION_GIT_BLOB_SHA1:
        raise RuntimeError(
            "compound-nuisance extension differs from the frozen pre-outcome artifact: "
            f"expected git blob {FROZEN_COMPOUND_EXTENSION_GIT_BLOB_SHA1}, got {actual}"
        )
    extension = json.loads(raw)
    if extension.get("schema") != COMPOUND_EXTENSION_SCHEMA:
        raise ValueError("unexpected compound-nuisance extension schema")
    if extension.get("status") != "frozen_pre_outcome_secondary_extension_no_v2_protocol_change":
        raise ValueError("compound-nuisance extension is not frozen pre-outcome")

    observed = extension.get("outcome_access_before_freeze")
    if not isinstance(observed, dict) or any(value is not False for value in observed.values()):
        raise ValueError("compound-nuisance extension must remain explicitly pre-outcome")

    rng = extension.get("rng_contract")
    if not isinstance(rng, dict):
        raise ValueError("compound-nuisance extension is missing rng_contract")
    if rng.get("extension_seed") != EXPECTED_EXTENSION_SEED:
        raise ValueError("compound-nuisance extension seed drifted")
    if rng.get("canonical_key_schema") != COMPOUND_TRIAL_KEY_SCHEMA:
        raise ValueError("compound trial-key schema drifted")
    if rng.get("canonical_key_fields") != ["probe_id", "cadence_id", "trial_index"]:
        raise ValueError("compound trial-key fields drifted")

    probes = extension.get("probes")
    if not isinstance(probes, list):
        raise ValueError("compound-nuisance extension is missing probes")
    counts: dict[str, int] = {}
    for probe in probes:
        if not isinstance(probe, dict):
            raise ValueError("compound probe must be an object")
        probe_id = probe.get("id")
        if not isinstance(probe_id, str) or not probe_id:
            raise ValueError("compound probe is missing id")
        cadence_ids = _cadence_ids(probe.get("cadences"))
        trials_per_cadence = probe.get("trials_per_cadence")
        total_trials = probe.get("total_trials")
        if isinstance(trials_per_cadence, bool) or not isinstance(trials_per_cadence, int):
            raise ValueError("compound trials_per_cadence must be an integer")
        expected_total = len(cadence_ids) * trials_per_cadence
        if total_trials != expected_total:
            raise ValueError(f"compound probe {probe_id!r} total does not reproduce")
        counts[probe_id] = expected_total

    if counts != EXPECTED_PROBE_COUNTS:
        raise ValueError(f"compound probe counts drifted: {counts}")
    if extension.get("total_extension_trials") != EXPECTED_TOTAL_TRIALS:
        raise ValueError("compound extension total trial count drifted")
    return extension


def iter_compound_trial_plan(extension: dict[str, Any]) -> Iterator[str]:
    """Yield the exact 30,000 frozen secondary stochastic identities."""

    for probe in extension["probes"]:
        probe_id = probe["id"]
        cadence_ids = _cadence_ids(probe["cadences"])
        trials_per_cadence = probe["trials_per_cadence"]
        for cadence_id in cadence_ids:
            for trial_index in range(trials_per_cadence):
                yield canonical_compound_trial_key(
                    probe_id=probe_id,
                    cadence_id=cadence_id,
                    trial_index=trial_index,
                )


def compound_plan_digest(canonical_keys: Iterable[str]) -> tuple[str, int, int]:
    """Return sorted-key SHA-256, total key count, and duplicate count."""

    keys = list(canonical_keys)
    unique = set(keys)
    duplicate_count = len(keys) - len(unique)
    if duplicate_count:
        raise ValueError("duplicate canonical trial key in compound extension plan")

    digest = hashlib.sha256()
    for canonical_key_json in sorted(keys):
        digest.update(canonical_key_json.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest(), len(keys), duplicate_count


def summarize_compound_trial_plan(extension: dict[str, Any]) -> dict[str, Any]:
    """Reproduce exact counts and digest before any compound curve is generated."""

    keys = list(iter_compound_trial_plan(extension))
    probe_counts: Counter[str] = Counter()
    for canonical_key_json in keys:
        row = json.loads(canonical_key_json)
        if row.get("schema") != COMPOUND_TRIAL_KEY_SCHEMA:
            raise ValueError("compound trial-plan key schema drifted")
        probe_counts[row["probe_id"]] += 1

    digest, total, duplicates = compound_plan_digest(keys)
    if dict(probe_counts) != EXPECTED_PROBE_COUNTS:
        raise ValueError(f"compound trial-plan probe counts drifted: {dict(probe_counts)}")
    if total != EXPECTED_TOTAL_TRIALS:
        raise ValueError(f"compound trial-plan total drifted: {total}")
    if digest != EXPECTED_PLAN_SHA256:
        raise ValueError("compound trial-plan digest drifted")
    return {
        "probe_counts": dict(probe_counts),
        "total_canonical_trial_keys": total,
        "unique_canonical_trial_keys": total - duplicates,
        "duplicate_canonical_trial_keys": duplicates,
        "sha256": digest,
    }


def verify_frozen_compound_plan_lock(
    path: Path,
    extension: dict[str, Any],
) -> dict[str, Any]:
    """Verify exact lock bytes and reproduce its complete semantic plan."""

    raw = path.read_bytes()
    actual = _git_blob_sha1(raw)
    if actual != FROZEN_COMPOUND_PLAN_LOCK_GIT_BLOB_SHA1:
        raise RuntimeError(
            "compound trial-plan lock differs from the frozen pre-outcome artifact: "
            f"expected git blob {FROZEN_COMPOUND_PLAN_LOCK_GIT_BLOB_SHA1}, got {actual}"
        )
    lock = json.loads(raw)
    if lock.get("schema") != COMPOUND_PLAN_LOCK_SCHEMA:
        raise ValueError("unexpected compound trial-plan lock schema")
    if lock.get("status") != "frozen_pre_outcome_secondary_extension_execution_lock":
        raise ValueError("compound trial-plan lock is not frozen pre-outcome")
    if lock.get("observed_scientific_results") is not False:
        raise ValueError("compound trial-plan lock must not contain scientific outcomes")
    if lock.get("bound_extension_git_blob_sha1") != FROZEN_COMPOUND_EXTENSION_GIT_BLOB_SHA1:
        raise ValueError("compound trial-plan lock is not bound to the frozen extension")
    if lock.get("extension_seed") != EXPECTED_EXTENSION_SEED:
        raise ValueError("compound trial-plan lock seed drifted")
    if lock.get("canonical_key_schema") != COMPOUND_TRIAL_KEY_SCHEMA:
        raise ValueError("compound trial-plan lock key schema drifted")

    summary = summarize_compound_trial_plan(extension)
    for field in (
        "probe_counts",
        "total_canonical_trial_keys",
        "unique_canonical_trial_keys",
        "duplicate_canonical_trial_keys",
    ):
        if lock.get(field) != summary[field]:
            raise ValueError(f"compound trial-plan lock field {field!r} does not reproduce")
    digest = lock.get("digest")
    if not isinstance(digest, dict) or digest.get("sha256") != summary["sha256"]:
        raise ValueError("compound trial-plan lock digest does not reproduce")
    return lock


__all__ = [
    "COMPOUND_TRIAL_KEY_SCHEMA",
    "EXPECTED_PLAN_SHA256",
    "EXPECTED_PROBE_COUNTS",
    "EXPECTED_TOTAL_TRIALS",
    "FROZEN_COMPOUND_EXTENSION_GIT_BLOB_SHA1",
    "FROZEN_COMPOUND_PLAN_LOCK_GIT_BLOB_SHA1",
    "canonical_compound_trial_key",
    "compound_plan_digest",
    "iter_compound_trial_plan",
    "summarize_compound_trial_plan",
    "verify_frozen_compound_extension",
    "verify_frozen_compound_plan_lock",
]
