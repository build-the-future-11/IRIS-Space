from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from siderea.cli import main
from siderea.config import load_config
from siderea.ledger import OutcomeLedger
from siderea.pipeline import analyze_csv


SOURCE = Path("examples/photometry.csv")


def _manifest(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_r07_existing_run_collision_preserves_terminal_evidence(tmp_path: Path) -> None:
    config = load_config()
    runs = tmp_path / "runs"
    ledger_path = tmp_path / "outcomes.sqlite"
    run_id = "r07-collision"

    result = analyze_csv(
        SOURCE,
        config,
        output_dir=runs,
        ledger_path=ledger_path,
        run_id=run_id,
    )
    before = result.manifest_path.read_bytes()
    before_payload = _manifest(result.manifest_path)
    assert before_payload["status"] == "completed"

    with pytest.raises(FileExistsError, match="already exists and will not be overwritten"):
        analyze_csv(
            SOURCE,
            config,
            output_dir=runs,
            ledger_path=ledger_path,
            run_id=run_id,
        )

    assert result.manifest_path.read_bytes() == before
    assert _manifest(result.manifest_path)["status"] == "completed"


def test_r07_unreadable_input_is_actionable_at_cli_boundary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    message = "permission denied reading input: /restricted/photometry.csv"
    with patch("siderea.pipeline.ingest_csv", side_effect=PermissionError(message)):
        code = main(
            [
                "analyze",
                "/restricted/photometry.csv",
                "--output-dir",
                str(tmp_path / "runs"),
            ]
        )

    captured = capsys.readouterr()
    assert code == 2
    assert message in captured.err


def test_r07_unwritable_output_finishes_failed_manifest(tmp_path: Path) -> None:
    config = load_config()
    runs = tmp_path / "runs"
    run_id = "r07-unwritable"
    message = "permission denied publishing normalized output"

    with (
        patch("siderea.pipeline._atomic_csv", side_effect=PermissionError(message)),
        pytest.raises(PermissionError, match="permission denied publishing normalized output"),
    ):
        analyze_csv(
            SOURCE,
            config,
            output_dir=runs,
            ledger_path=tmp_path / "outcomes.sqlite",
            run_id=run_id,
        )

    manifest_path = runs / run_id / "manifest.json"
    payload = _manifest(manifest_path)
    assert payload["status"] == "failed"
    assert payload["completed_at"]
    assert payload["metrics"]["partial_artifact_count"] == 0
    assert any(
        "PermissionError" in warning and message in warning
        for warning in payload["warnings"]
    )


def test_r07_interrupt_during_publication_rewrites_manifest_terminal_state(
    tmp_path: Path,
) -> None:
    config = load_config()
    runs = tmp_path / "runs"
    run_id = "r07-interrupted-publication"
    ledger = OutcomeLedger(tmp_path / "outcomes.sqlite")

    with (
        patch.object(ledger, "upsert_candidates", side_effect=KeyboardInterrupt),
        pytest.raises(KeyboardInterrupt),
    ):
        analyze_csv(
            SOURCE,
            config,
            output_dir=runs,
            ledger=ledger,
            run_id=run_id,
        )

    manifest_path = runs / run_id / "manifest.json"
    payload = _manifest(manifest_path)
    assert payload["status"] == "interrupted"
    assert payload["completed_at"]
    assert payload["metrics"]["candidate_count"] >= 1
    assert any(
        warning == "pipeline interrupted during publication"
        for warning in payload["warnings"]
    )
    assert len(payload["artifacts"]) >= 5
