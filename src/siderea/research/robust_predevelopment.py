"""Canonical predevelopment input gate for robust transient-search v2.

This module produces no scientific result. It binds the existing protocol,
amendment, cadence, reported-error, stochastic trial-identity, and complete
semantic trial-plan locks before any candidate-performance statistic can be
generated.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from siderea.research.robust_authorized_plan import (
    AuthorizedTrialPlan,
    load_authorized_trial_plan,
)
from siderea.research.robust_execution import verify_predevelopment_inputs
from siderea.research.robust_protocol import (
    FROZEN_CADENCE_MANIFEST_SHA256,
    verify_cadence_manifest,
    verify_frozen_protocol,
)
from siderea.research.robust_trial_plan import (
    FROZEN_TRIAL_PLAN_AMENDMENT_GIT_BLOB_SHA1,
    FROZEN_TRIAL_PLAN_LOCK_GIT_BLOB_SHA1,
    verify_frozen_trial_plan_amendment,
    verify_frozen_trial_plan_lock,
)
from siderea.research.robust_trial_rng import (
    FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1,
    verify_frozen_trial_rng_amendment,
)


@dataclass(frozen=True)
class PredevelopmentAuthority:
    """Verified capability a future v2 outcome runner must consume.

    A receipt proves that the frozen inputs were checked. The attached
    ``AuthorizedTrialPlan`` additionally constrains execution to the exact
    415,375 semantic identities already frozen by v2.0.5. Keeping the two
    together prevents receipt-only code from inventing a new deterministic but
    unauthorized trial key after verification.
    """

    receipt: Mapping[str, Any]
    trial_plan: AuthorizedTrialPlan

    @property
    def full_plan_sha256(self) -> str:
        return self.trial_plan.full_plan_sha256

    @property
    def total_keys(self) -> int:
        return self.trial_plan.total_keys


def verify_materialized_cadence_manifest(
    cadence_manifest_path: Path,
    protocol: dict[str, Any],
) -> str:
    """Bind the exact on-disk cadence bytes to the frozen generator and digest."""

    expected = verify_cadence_manifest(protocol)
    actual = cadence_manifest_path.read_bytes()
    actual_sha256 = hashlib.sha256(actual).hexdigest()
    if actual != expected:
        raise RuntimeError(
            "materialized robust-search cadence manifest differs from the frozen "
            "generator output: expected SHA-256 "
            f"{FROZEN_CADENCE_MANIFEST_SHA256}, got {actual_sha256}; correct the "
            "pre-result materialization instead of changing the frozen digest"
        )
    if actual_sha256 != FROZEN_CADENCE_MANIFEST_SHA256:
        raise RuntimeError(
            "materialized robust-search cadence manifest passed byte comparison but "
            "does not reproduce the frozen digest"
        )
    return actual_sha256


def verify_all_predevelopment_inputs(
    protocol_path: Path,
    cadence_manifest_path: Path,
    amendment_path: Path,
    execution_amendment_path: Path,
    identifier_erratum_path: Path,
    trial_rng_amendment_path: Path,
    trial_plan_amendment_path: Path,
    trial_plan_lock_path: Path,
    reported_error_lock_path: Path,
) -> dict[str, Any]:
    """Verify every pre-result input, including the complete semantic trial plan."""

    protocol = verify_frozen_protocol(protocol_path)
    cadence_sha256 = verify_materialized_cadence_manifest(
        cadence_manifest_path, protocol
    )
    verify_frozen_trial_rng_amendment(trial_rng_amendment_path)
    verify_frozen_trial_plan_amendment(trial_plan_amendment_path)
    trial_plan_lock = verify_frozen_trial_plan_lock(trial_plan_lock_path, protocol)
    receipt = verify_predevelopment_inputs(
        protocol_path,
        amendment_path,
        execution_amendment_path,
        identifier_erratum_path,
        reported_error_lock_path,
    )
    bound_receipt = dict(receipt)
    bound_receipt["cadence_manifest_sha256"] = cadence_sha256
    bound_receipt["trial_rng_amendment_git_blob_sha1"] = (
        FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1
    )
    bound_receipt["trial_plan_amendment_git_blob_sha1"] = (
        FROZEN_TRIAL_PLAN_AMENDMENT_GIT_BLOB_SHA1
    )
    bound_receipt["trial_plan_lock_git_blob_sha1"] = (
        FROZEN_TRIAL_PLAN_LOCK_GIT_BLOB_SHA1
    )
    bound_receipt["trial_plan_sha256"] = trial_plan_lock["digest"]["sha256"]
    return bound_receipt


def load_predevelopment_authority(
    protocol_path: Path,
    cadence_manifest_path: Path,
    amendment_path: Path,
    execution_amendment_path: Path,
    identifier_erratum_path: Path,
    trial_rng_amendment_path: Path,
    trial_plan_amendment_path: Path,
    trial_plan_lock_path: Path,
    reported_error_lock_path: Path,
) -> PredevelopmentAuthority:
    """Verify all pre-result locks and return the exact executable trial capability."""

    receipt = verify_all_predevelopment_inputs(
        protocol_path,
        cadence_manifest_path,
        amendment_path,
        execution_amendment_path,
        identifier_erratum_path,
        trial_rng_amendment_path,
        trial_plan_amendment_path,
        trial_plan_lock_path,
        reported_error_lock_path,
    )
    protocol = verify_frozen_protocol(protocol_path)
    trial_plan = load_authorized_trial_plan(protocol, trial_plan_lock_path)
    if receipt.get("trial_plan_sha256") != trial_plan.full_plan_sha256:
        raise RuntimeError(
            "predevelopment receipt and authorized trial plan bind different plan digests"
        )
    return PredevelopmentAuthority(
        receipt=MappingProxyType(dict(receipt)),
        trial_plan=trial_plan,
    )


__all__ = [
    "PredevelopmentAuthority",
    "load_predevelopment_authority",
    "verify_all_predevelopment_inputs",
    "verify_materialized_cadence_manifest",
]
