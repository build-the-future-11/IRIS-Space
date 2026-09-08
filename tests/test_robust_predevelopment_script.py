from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from siderea.research.robust_protocol import FROZEN_CADENCE_MANIFEST_SHA256
from siderea.research.robust_trial_rng import FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1


SCRIPT = Path("paper/experiments/verify_robust_search_predevelopment.py")


def test_predevelopment_verifier_entrypoint_executes_complete_lock_chain() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(completed.stdout)
    assert receipt["status"] == "PASS_PREDEVELOPMENT_INPUT_LOCKS_NO_PERFORMANCE_STATISTICS"
    assert len(receipt["protocol_git_blob_sha1"]) == 40
    assert len(receipt["amendment_git_blob_sha1"]) == 40
    assert len(receipt["execution_amendment_git_blob_sha1"]) == 40
    assert len(receipt["identifier_erratum_git_blob_sha1"]) == 40
    assert receipt["cadence_manifest_sha256"] == FROZEN_CADENCE_MANIFEST_SHA256
    assert receipt["trial_rng_amendment_git_blob_sha1"] == FROZEN_TRIAL_RNG_AMENDMENT_GIT_BLOB_SHA1
    assert len(receipt["reported_errors_sha256"]) == 64
    assert "threshold" not in receipt
    assert "false_alarm" not in receipt
    assert "recovery" not in receipt
