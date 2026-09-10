"""Verified execution views over the frozen robust-search v2 trial plan.

This module generates no noise, signals, search statistics, thresholds, or
scientific outcomes.  It closes an execution-integrity gap between two already
frozen contracts:

* v2.0.4 makes a syntactically canonical semantic key map deterministically to an
  RNG stream; and
* v2.0.5 freezes the *authorized set* of 415,375 semantic trial identities.

A deterministic RNG key is not automatically an authorized scientific trial.
Future outcome-producing runners should obtain their work exclusively from the
verified subsets exposed here instead of constructing semantic keys ad hoc.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from siderea.research.robust_trial_plan import (
    EXPECTED_PLAN_SHA256,
    EXPECTED_ROLE_COUNTS,
    EXPECTED_TOTAL_TRIALS,
    iter_trial_plan,
    verify_frozen_trial_plan_lock,
)

ROLE_PHASE = {
    "development_threshold_null": "development",
    "development_feasibility_null": "development",
    "development_signal": "development",
    "calibration_null": "calibration",
    "v1_raw_bank_comparator_calibration": "calibration",
    "locked_null": "locked_evaluation",
    "locked_signal": "locked_evaluation",
    "generalization_probe": "locked_evaluation",
}


def _sorted_key_digest(keys: tuple[str, ...]) -> str:
    digest = hashlib.sha256()
    for canonical_key_json in sorted(keys):
        digest.update(canonical_key_json.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


@dataclass(frozen=True)
class AuthorizedTrialSubset:
    """One exact phase/role slice derived from the verified frozen trial plan."""

    phase: str
    role: str
    keys: tuple[str, ...] = field(repr=False)
    digest_sha256: str
    _key_set: frozenset[str] = field(repr=False)

    @classmethod
    def from_keys(
        cls,
        *,
        phase: str,
        role: str,
        keys: tuple[str, ...],
    ) -> AuthorizedTrialSubset:
        if not keys:
            raise ValueError(f"authorized trial subset is empty: {phase}/{role}")
        expected_phase = ROLE_PHASE.get(role)
        if expected_phase is None:
            raise ValueError(f"unknown frozen v2 role: {role}")
        if phase != expected_phase:
            raise ValueError(
                f"frozen v2 role {role!r} belongs to phase {expected_phase!r}, got {phase!r}"
            )
        key_set = frozenset(keys)
        if len(key_set) != len(keys):
            raise ValueError(f"duplicate key inside authorized subset: {phase}/{role}")
        expected_count = EXPECTED_ROLE_COUNTS[role]
        if len(keys) != expected_count:
            raise ValueError(
                f"authorized subset {phase}/{role} has {len(keys)} keys; expected {expected_count}"
            )
        return cls(
            phase=phase,
            role=role,
            keys=keys,
            digest_sha256=_sorted_key_digest(keys),
            _key_set=key_set,
        )

    def require_key(self, canonical_key_json: str) -> str:
        """Return ``canonical_key_json`` only when it is in this frozen subset."""

        if canonical_key_json not in self._key_set:
            raise ValueError(
                f"semantic trial key is not authorized for frozen subset {self.phase}/{self.role}"
            )
        return canonical_key_json


@dataclass(frozen=True)
class AuthorizedTrialPlan:
    """Immutable, verified execution view of the complete frozen v2 plan."""

    full_plan_sha256: str
    total_keys: int
    subsets: tuple[AuthorizedTrialSubset, ...] = field(repr=False)

    def subset(self, *, phase: str, role: str) -> AuthorizedTrialSubset:
        expected_phase = ROLE_PHASE.get(role)
        if expected_phase is None:
            raise ValueError(f"unknown frozen v2 role: {role}")
        if phase != expected_phase:
            raise ValueError(
                f"frozen v2 role {role!r} belongs to phase {expected_phase!r}, got {phase!r}"
            )
        for subset in self.subsets:
            if subset.phase == phase and subset.role == role:
                return subset
        raise RuntimeError(f"verified frozen plan is missing subset {phase}/{role}")

    def require_key(self, canonical_key_json: str) -> str:
        """Reject any syntactically valid key that is outside the frozen v2 plan."""

        try:
            row = json.loads(canonical_key_json)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("semantic trial key is not valid JSON") from exc
        if not isinstance(row, dict):
            raise ValueError("semantic trial key must be a JSON object")
        phase = row.get("phase")
        role = row.get("role")
        if not isinstance(phase, str) or not isinstance(role, str):
            raise ValueError("semantic trial key must contain string phase and role fields")
        return self.subset(phase=phase, role=role).require_key(canonical_key_json)


def load_authorized_trial_plan(
    protocol: dict[str, Any],
    trial_plan_lock_path: Path,
) -> AuthorizedTrialPlan:
    """Verify the lock, then derive the only trial identities a runner may execute."""

    lock = verify_frozen_trial_plan_lock(trial_plan_lock_path, protocol)
    digest = lock.get("digest")
    if not isinstance(digest, dict) or digest.get("sha256") != EXPECTED_PLAN_SHA256:
        raise RuntimeError("frozen trial-plan lock does not bind the expected plan digest")

    buckets: dict[tuple[str, str], list[str]] = {
        (phase, role): [] for role, phase in ROLE_PHASE.items()
    }
    total = 0
    for canonical_key_json in iter_trial_plan(protocol):
        row = json.loads(canonical_key_json)
        phase = row.get("phase")
        role = row.get("role")
        if not isinstance(phase, str) or not isinstance(role, str):
            raise RuntimeError("frozen trial-plan iterator emitted a malformed semantic key")
        expected_phase = ROLE_PHASE.get(role)
        if expected_phase is None:
            raise RuntimeError(f"frozen trial-plan iterator emitted unknown role {role!r}")
        if phase != expected_phase:
            raise RuntimeError(
                f"frozen trial-plan iterator mapped role {role!r} to phase {phase!r}; "
                f"expected {expected_phase!r}"
            )
        buckets[(phase, role)].append(canonical_key_json)
        total += 1

    if total != EXPECTED_TOTAL_TRIALS:
        raise RuntimeError(
            f"authorized trial-plan view contains {total} keys; expected {EXPECTED_TOTAL_TRIALS}"
        )

    subsets = tuple(
        AuthorizedTrialSubset.from_keys(
            phase=phase,
            role=role,
            keys=tuple(buckets[(phase, role)]),
        )
        for role, phase in ROLE_PHASE.items()
    )
    if sum(len(subset.keys) for subset in subsets) != EXPECTED_TOTAL_TRIALS:
        raise RuntimeError("authorized trial subsets do not reconstruct the frozen total")

    return AuthorizedTrialPlan(
        full_plan_sha256=EXPECTED_PLAN_SHA256,
        total_keys=EXPECTED_TOTAL_TRIALS,
        subsets=subsets,
    )


__all__ = [
    "AuthorizedTrialPlan",
    "AuthorizedTrialSubset",
    "ROLE_PHASE",
    "load_authorized_trial_plan",
]
