from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


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
    assert len(receipt["reported_errors_sha256"]) == 64
    assert "threshold" not in receipt
    assert "false_alarm" not in receipt
    assert "recovery" not in receipt
