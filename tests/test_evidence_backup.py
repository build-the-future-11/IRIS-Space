from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from siderea.atomic import RESTORE_MARKER
from siderea.cli import main
from siderea.config import load_config
from siderea.ledger import OutcomeLedger
from siderea.operations.backup import (
    create_evidence_backup,
    restore_evidence_backup,
    verify_evidence_backup,
)
from siderea.pipeline import analyze_csv
from siderea.reporting.preflight import _publication_error


def source_run(tmp_path):
    root = tmp_path / "data"
    result = analyze_csv(
        Path("examples/photometry.csv"),
        load_config(),
        output_dir=root / "runs",
        ledger_path=root / "outcomes.sqlite",
    )
    ledger = OutcomeLedger(result.ledger_path)
    candidate = ledger.list_candidates(limit=1)[0]
    ledger.add_review(
        candidate["candidate_id"],
        candidate_version=candidate["version_digest"],
        reviewer="backup-test",
        role="screener",
        verdict="abstain",
        reason="Synthetic backup test",
    )
    return root, result, ledger, candidate


def test_backup_restores_database_reviews_and_every_published_artifact(tmp_path, capsys):
    root, result, ledger, candidate = source_run(tmp_path)
    archive = tmp_path / "backup.zip"
    assert main(["evidence-backup", str(ledger.path), str(root), str(archive)]) == 0
    manifest = json.loads(capsys.readouterr().out)
    assert verify_evidence_backup(archive) == manifest
    with pytest.raises(FileExistsError, match="not exist"):
        restore_evidence_backup(archive, root)
    with pytest.raises(ValueError, match="original root"):
        restore_evidence_backup(archive, tmp_path / "other")
    root.rename(tmp_path / "preserved-original")
    assert main(["evidence-restore", str(archive), str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["restored"] is True
    restored = OutcomeLedger(result.ledger_path)
    assert restored.candidate(candidate["candidate_id"]) == candidate
    assert len(restored.reviews_for(candidate["candidate_id"])) == 1
    assert _publication_error(candidate["payload"]) is None
    assert not (root / RESTORE_MARKER).exists()


def test_backup_rejects_tampering_and_missing_referenced_files(tmp_path):
    root, result, ledger, _ = source_run(tmp_path)
    archive = tmp_path / "backup.zip"
    create_evidence_backup(ledger.path, root, archive)
    corrupt = tmp_path / "corrupt.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(corrupt, "w") as destination:
        for name in source.namelist():
            content = source.read(name)
            if name.endswith("candidates.json"):
                content = b"x" * len(content)
            destination.writestr(name, content)
    with pytest.raises(ValueError, match="digest"):
        verify_evidence_backup(corrupt)
    result.candidates_path.rename(result.candidates_path.with_suffix(".preserved"))
    with pytest.raises(ValueError, match="publication"):
        create_evidence_backup(ledger.path, root, tmp_path / "invalid.zip")
    assert not (tmp_path / "invalid.zip").exists()


def test_failed_restore_remains_blocked_and_source_archive_survives(tmp_path):
    root, _, ledger, _ = source_run(tmp_path)
    archive = tmp_path / "backup.zip"
    create_evidence_backup(ledger.path, root, archive)
    root.rename(tmp_path / "preserved-original")
    with (
        patch("siderea.operations.backup.atomic_create_binary", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        restore_evidence_backup(archive, root)
    assert (root / RESTORE_MARKER).exists()
    assert archive.exists()
    with pytest.raises(ValueError, match="incomplete"):
        OutcomeLedger(root / "outcomes.sqlite")


def test_backup_cannot_omit_publication_files_with_recomputed_inventory(tmp_path):
    from siderea.provenance import digest_value

    root, _, ledger, _ = source_run(tmp_path)
    archive = tmp_path / "backup.zip"
    manifest = create_evidence_backup(ledger.path, root, archive)
    omitted = next(
        entry["path"] for entry in manifest["files"] if entry["path"].endswith("candidates.json")
    )
    manifest["files"] = [entry for entry in manifest["files"] if entry["path"] != omitted]
    manifest.pop("backup_digest")
    manifest["backup_digest"] = digest_value(manifest)
    incomplete = tmp_path / "incomplete.zip"
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(incomplete, "w") as destination:
        for name in source.namelist():
            if name != "files/" + omitted:
                content = json.dumps(manifest) if name == "manifest.json" else source.read(name)
                destination.writestr(name, content)
    root.rename(tmp_path / "original-offline")
    with pytest.raises(ValueError, match="referenced publication artifact"):
        verify_evidence_backup(incomplete)


def test_backup_refuses_incomplete_restore_source(tmp_path):
    root, _, ledger, _ = source_run(tmp_path)
    (root / RESTORE_MARKER).write_text("incomplete")
    with pytest.raises(ValueError, match="incomplete restore"):
        create_evidence_backup(ledger.path, root, tmp_path / "backup.zip")
