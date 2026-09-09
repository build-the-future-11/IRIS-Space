"""Deterministic pre-result trial plan for robust transient-search v2.

This module enumerates stochastic identities only. It never generates noise,
injected signals, search statistics, thresholds, candidate rankings, or outcomes.
The complete plan is frozen by v2.0.5 before any v2 development result exists.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from siderea.research.robust_protocol import (
    FROZEN_PROTOCOL_GIT_BLOB_SHA1,
    build_cadence_manifest,
)
from siderea.research.robust_trial_rng import (
    FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1,
    canonical_trial_key,
)

FROZEN_TRIAL_PLAN_AMENDMENT_GIT_BLOB_SHA1 = "918c853ec8ffc7f9c34720f5fd91c291355179c5"
FROZEN_TRIAL_PLAN_LOCK_GIT_BLOB_SHA1 = "acc0bccb00b406155e83ddf903eaf80fe6fe2d28"
TRIAL_PLAN_AMENDMENT_SCHEMA = "siderea.robust_search_protocol_amendment.v2.0.5"
TRIAL_PLAN_LOCK_SCHEMA = "siderea.robust_search_trial_plan_lock.v2"
SEASONAL_GAP_NULL = "seasonal_gap_with_matched_gaussian_noise"

EXPECTED_ROLE_COUNTS = {
    "development_threshold_null": 14_000,
    "development_feasibility_null": 14_000,
    "development_signal": 12_000,
    "calibration_null": 140_000,
    "v1_raw_bank_comparator_calibration": 102_375,
    "locked_null": 70_000,
    "locked_signal": 48_000,
    "generalization_probe": 15_000,
}
EXPECTED_PHASE_COUNTS = {
    "development": 40_000,
    "calibration": 242_375,
    "locked_evaluation": 133_000,
}
EXPECTED_TOTAL_TRIALS = 415_375
EXPECTED_PLAN_SHA256 = "09228f6174e44c49154900ca8329bf8f3a89bea3adc695e0626498cf87530911"


def _git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git object identity


def verify_frozen_trial_plan_amendment(path: Path) -> dict[str, Any]:
    """Verify the exact pre-result v2.0.5 semantic-plan amendment."""

    raw = path.read_bytes()
    actual = _git_blob_sha1(raw)
    if actual != FROZEN_TRIAL_PLAN_AMENDMENT_GIT_BLOB_SHA1:
        raise RuntimeError(
            "robust-search v2.0.5 trial-plan amendment differs from the frozen "
            f"predevelopment artifact: expected git blob "
            f"{FROZEN_TRIAL_PLAN_AMENDMENT_GIT_BLOB_SHA1}, got {actual}"
        )
    amendment = json.loads(raw)
    if amendment.get("schema") != TRIAL_PLAN_AMENDMENT_SCHEMA:
        raise ValueError("unexpected robust-search trial-plan amendment schema")
    if amendment.get("status") != "frozen_before_any_v2_candidate_development_evaluation":
        raise ValueError("trial-plan amendment is not marked frozen before development")
    if amendment.get("base_protocol_git_blob_sha1") != FROZEN_PROTOCOL_GIT_BLOB_SHA1:
        raise ValueError("trial-plan amendment is not bound to the frozen base protocol")
    if (
        amendment.get("previous_amendment_git_blob_sha1")
        != FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1
    ):
        raise ValueError("trial-plan amendment is not bound to frozen v2.0.4")

    observed = amendment.get("observed_before_amendment")
    forbidden = (
        "v2_candidate_development_statistics",
        "v2_calibration_statistics",
        "v2_locked_evaluation_statistics",
        "v2_generalization_probe_statistics",
    )
    if not isinstance(observed, dict) or any(observed.get(name) is not False for name in forbidden):
        raise ValueError("trial-plan amendment must remain explicitly pre-result")

    changes = amendment.get("changes")
    if not isinstance(changes, dict):
        raise ValueError("trial-plan amendment is missing changes")
    if changes.get("total_stochastic_data_generation_identities") != EXPECTED_TOTAL_TRIALS:
        raise ValueError("trial-plan total count drifted")
    rows = changes.get("role_vocabulary_and_counts")
    if not isinstance(rows, list):
        raise ValueError("trial-plan role vocabulary is missing")
    observed_counts = {row.get("role"): row.get("count") for row in rows if isinstance(row, dict)}
    if observed_counts != EXPECTED_ROLE_COUNTS:
        raise ValueError("trial-plan role counts drifted")
    return amendment


def _cadence_ids(protocol: dict[str, Any]) -> tuple[list[str], list[str]]:
    rows = build_cadence_manifest(protocol)["cadences"]
    irregular = [row["id"] for row in rows if row["kind"] == "irregular"]
    seasonal = [row["id"] for row in rows if row["kind"] == "seasonal_gap"]
    if len(irregular) != 20 or len(seasonal) != 5:
        raise ValueError("frozen cadence allocation no longer contains 20 + 5 cadences")
    return irregular, seasonal


def _key(
    *,
    phase: str,
    role: str,
    cadence_id: str,
    trial_index: int,
    null_regime: str | None = None,
    signal_family: str | None = None,
    signal_width_days: float | None = None,
    amplitude_sigma: float | None = None,
    noise_regime: str | None = None,
    probe_id: str | None = None,
) -> str:
    return canonical_trial_key(
        phase=phase,
        role=role,
        cadence_id=cadence_id,
        null_regime=null_regime,
        candidate_id=None,
        signal_family=signal_family,
        signal_width_days=signal_width_days,
        amplitude_sigma=amplitude_sigma,
        noise_regime=noise_regime,
        probe_id=probe_id,
        trial_index=trial_index,
    )


def _iter_null_role(
    protocol: dict[str, Any],
    *,
    phase: str,
    role: str,
    ordinary_trials_per_cadence: int,
    seasonal_trials_per_cadence: int,
) -> Iterator[str]:
    irregular, seasonal = _cadence_ids(protocol)
    regimes = list(protocol["null_envelope_used_for_calibration"])
    ordinary_regimes = [regime for regime in regimes if regime != SEASONAL_GAP_NULL]
    if len(ordinary_regimes) != 13 or regimes.count(SEASONAL_GAP_NULL) != 1:
        raise ValueError("frozen null envelope no longer contains 13 ordinary + 1 gap regime")

    for regime in ordinary_regimes:
        for cadence_id in irregular:
            for trial_index in range(ordinary_trials_per_cadence):
                yield _key(
                    phase=phase,
                    role=role,
                    cadence_id=cadence_id,
                    null_regime=regime,
                    trial_index=trial_index,
                )
    for cadence_id in seasonal:
        for trial_index in range(seasonal_trials_per_cadence):
            yield _key(
                phase=phase,
                role=role,
                cadence_id=cadence_id,
                null_regime=SEASONAL_GAP_NULL,
                trial_index=trial_index,
            )


def iter_trial_plan(protocol: dict[str, Any]) -> Iterator[str]:
    """Yield all 415,375 canonical stochastic identities and no outcomes."""

    irregular, seasonal = _cadence_ids(protocol)
    all_cadences = irregular + seasonal
    design = protocol["design"]

    for role in ("development_threshold_null", "development_feasibility_null"):
        yield from _iter_null_role(
            protocol,
            phase="development",
            role=role,
            ordinary_trials_per_cadence=50,
            seasonal_trials_per_cadence=200,
        )

    for family in design["template_families"]:
        for width in design["template_widths_days"]:
            for noise_regime in protocol["signal_noise_regimes"]:
                for cadence_id in all_cadences:
                    for trial_index in range(10):
                        yield _key(
                            phase="development",
                            role="development_signal",
                            cadence_id=cadence_id,
                            signal_family=family,
                            signal_width_days=float(width),
                            amplitude_sigma=4.0,
                            noise_regime=noise_regime,
                            trial_index=trial_index,
                        )

    yield from _iter_null_role(
        protocol,
        phase="calibration",
        role="calibration_null",
        ordinary_trials_per_cadence=500,
        seasonal_trials_per_cadence=2000,
    )

    for cadence_id in all_cadences:
        for trial_index in range(4095):
            yield _key(
                phase="calibration",
                role="v1_raw_bank_comparator_calibration",
                cadence_id=cadence_id,
                null_regime="iid_gaussian",
                trial_index=trial_index,
            )

    yield from _iter_null_role(
        protocol,
        phase="locked_evaluation",
        role="locked_null",
        ordinary_trials_per_cadence=250,
        seasonal_trials_per_cadence=1000,
    )

    families = list(design["template_families"])
    widths = [float(width) for width in design["template_widths_days"]]
    amplitudes = [float(value) for value in design["signal_amplitudes_sigma"]]
    noise_regimes = list(protocol["signal_noise_regimes"])
    if widths != [1.0, 3.0, 10.0]:
        raise ValueError("locked-signal width order drifted")
    if len(families) != 4 or len(amplitudes) != 3 or len(noise_regimes) != 4:
        raise ValueError("locked-signal factor dimensions drifted")

    for family_index, family in enumerate(families):
        for amplitude_index, amplitude in enumerate(amplitudes):
            for noise_index, noise_regime in enumerate(noise_regimes):
                cell_index = ((family_index * 3 + amplitude_index) * 4) + noise_index
                for cadence_index, cadence_id in enumerate(all_cadences):
                    width_buckets: dict[float, list[int]] = {width: [] for width in widths}
                    for within_cadence_index in range(40):
                        global_trial_index = 40 * cadence_index + within_cadence_index
                        width = widths[(global_trial_index + cell_index) % 3]
                        width_buckets[width].append(within_cadence_index)
                    for width in widths:
                        for trial_index, _ in enumerate(width_buckets[width]):
                            yield _key(
                                phase="locked_evaluation",
                                role="locked_signal",
                                cadence_id=cadence_id,
                                signal_family=family,
                                signal_width_days=width,
                                amplitude_sigma=amplitude,
                                noise_regime=noise_regime,
                                trial_index=trial_index,
                            )

    for probe_id in protocol["locked_generalization_probes_not_used_for_threshold_selection"]:
        for cadence_id in irregular:
            for trial_index in range(250):
                yield _key(
                    phase="locked_evaluation",
                    role="generalization_probe",
                    cadence_id=cadence_id,
                    probe_id=probe_id,
                    trial_index=trial_index,
                )


def summarize_trial_plan(protocol: dict[str, Any]) -> dict[str, Any]:
    """Validate uniqueness/counts and return the compact sorted-key plan digest."""

    seen: set[str] = set()
    keys: list[str] = []
    role_counts: Counter[str] = Counter()
    phase_counts: Counter[str] = Counter()

    for canonical_key_json in iter_trial_plan(protocol):
        if canonical_key_json in seen:
            raise ValueError("duplicate canonical trial key in frozen v2 plan")
        seen.add(canonical_key_json)
        keys.append(canonical_key_json)
        row = json.loads(canonical_key_json)
        role_counts[row["role"]] += 1
        phase_counts[row["phase"]] += 1

    if dict(role_counts) != EXPECTED_ROLE_COUNTS:
        raise ValueError(f"trial-plan role counts drifted: {dict(role_counts)}")
    if dict(phase_counts) != EXPECTED_PHASE_COUNTS:
        raise ValueError(f"trial-plan phase counts drifted: {dict(phase_counts)}")
    if len(keys) != EXPECTED_TOTAL_TRIALS:
        raise ValueError(f"trial-plan total drifted: {len(keys)}")

    digest = hashlib.sha256()
    for canonical_key_json in sorted(keys):
        digest.update(canonical_key_json.encode("utf-8"))
        digest.update(b"\n")
    return {
        "role_counts": dict(role_counts),
        "phase_counts": dict(phase_counts),
        "total_canonical_trial_keys": len(keys),
        "unique_canonical_trial_keys": len(seen),
        "duplicate_canonical_trial_keys": len(keys) - len(seen),
        "sha256": digest.hexdigest(),
    }


def verify_frozen_trial_plan_lock(path: Path, protocol: dict[str, Any]) -> dict[str, Any]:
    """Verify exact lock bytes and reproduce its complete semantic-plan digest."""

    raw = path.read_bytes()
    actual = _git_blob_sha1(raw)
    if actual != FROZEN_TRIAL_PLAN_LOCK_GIT_BLOB_SHA1:
        raise RuntimeError(
            "robust-search trial-plan lock differs from the frozen predevelopment artifact: "
            f"expected git blob {FROZEN_TRIAL_PLAN_LOCK_GIT_BLOB_SHA1}, got {actual}"
        )
    lock = json.loads(raw)
    if lock.get("schema") != TRIAL_PLAN_LOCK_SCHEMA:
        raise ValueError("unexpected robust-search trial-plan lock schema")
    if lock.get("status") != "frozen_before_any_v2_candidate_development_evaluation":
        raise ValueError("trial-plan lock is not explicitly pre-result")
    if lock.get("observed_scientific_results") is not False:
        raise ValueError("trial-plan lock must not contain observed scientific results")
    if lock.get("bound_protocol_git_blob_sha1") != FROZEN_PROTOCOL_GIT_BLOB_SHA1:
        raise ValueError("trial-plan lock is not bound to the frozen base protocol")
    if (
        lock.get("bound_trial_rng_amendment_git_blob_sha1")
        != FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1
    ):
        raise ValueError("trial-plan lock is not bound to frozen v2.0.4")
    if (
        lock.get("bound_trial_plan_amendment_git_blob_sha1")
        != FROZEN_TRIAL_PLAN_AMENDMENT_GIT_BLOB_SHA1
    ):
        raise ValueError("trial-plan lock is not bound to frozen v2.0.5")

    summary = summarize_trial_plan(protocol)
    if lock.get("role_counts") != summary["role_counts"]:
        raise ValueError("trial-plan lock role counts do not reproduce")
    if lock.get("phase_counts") != summary["phase_counts"]:
        raise ValueError("trial-plan lock phase counts do not reproduce")
    for field in (
        "total_canonical_trial_keys",
        "unique_canonical_trial_keys",
        "duplicate_canonical_trial_keys",
    ):
        if lock.get(field) != summary[field]:
            raise ValueError(f"trial-plan lock field {field!r} does not reproduce")
    digest = lock.get("digest")
    if not isinstance(digest, dict) or digest.get("sha256") != summary["sha256"]:
        raise ValueError("trial-plan sorted-key digest does not reproduce")
    if summary["sha256"] != EXPECTED_PLAN_SHA256:
        raise ValueError("trial-plan implementation drifted from the frozen digest")
    return lock


__all__ = [
    "EXPECTED_PHASE_COUNTS",
    "EXPECTED_PLAN_SHA256",
    "EXPECTED_ROLE_COUNTS",
    "EXPECTED_TOTAL_TRIALS",
    "FROZEN_TRIAL_PLAN_AMENDMENT_GIT_BLOB_SHA1",
    "FROZEN_TRIAL_PLAN_LOCK_GIT_BLOB_SHA1",
    "iter_trial_plan",
    "summarize_trial_plan",
    "verify_frozen_trial_plan_amendment",
    "verify_frozen_trial_plan_lock",
]
