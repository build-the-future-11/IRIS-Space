from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import NormalDist

from siderea.research.robust_protocol import FROZEN_PROTOCOL_GIT_BLOB_SHA1
from siderea.research.robust_trial_rng import FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1

AUDIT = Path("paper/experiments/robust_search_gate_audit.v2.json")


def _wilson_upper(k: int, n: int, confidence: float = 0.95) -> float:
    z = NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)
    p = k / n
    denominator = 1.0 + z**2 / n
    center = (p + z**2 / (2.0 * n)) / denominator
    radius = z * math.sqrt(p * (1.0 - p) / n + z**2 / (4.0 * n**2)) / denominator
    return center + radius


def test_frozen_safety_uncertainty_gate_is_deterministically_nonbinding() -> None:
    payload = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert payload["status"] == "pre_result_deterministic_audit_no_protocol_change"
    assert payload["observed_scientific_results"] is False
    assert payload["bound_protocol_git_blob_sha1"] == FROZEN_PROTOCOL_GIT_BLOB_SHA1
    assert (
        payload["bound_amendment_v2_0_4_git_blob_sha1"] == FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1
    )

    inputs = payload["inputs"]
    derived = payload["derived"]
    n = inputs["locked_null_trials_per_regime"]
    point_cap = inputs["point_estimate_false_alarm_cap"]
    wilson_cap = inputs["wilson_upper_cap"]
    max_k = math.floor(n * point_cap)

    assert max_k == derived["maximum_false_alarms_allowed_by_point_estimate_gate"] == 50
    boundary_upper = _wilson_upper(max_k, n)
    next_upper = _wilson_upper(max_k + 1, n)
    assert math.isclose(
        boundary_upper,
        derived["wilson_95_upper_at_50_of_5000"],
        rel_tol=0.0,
        abs_tol=1e-15,
    )
    assert math.isclose(
        next_upper,
        derived["wilson_95_upper_at_51_of_5000"],
        rel_tol=0.0,
        abs_tol=1e-15,
    )
    assert boundary_upper < wilson_cap
    assert next_upper < wilson_cap
    assert (max_k + 1) / n > point_cap
    assert derived["wilson_uncertainty_gate_is_binding"] is False
