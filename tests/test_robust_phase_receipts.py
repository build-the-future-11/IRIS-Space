from __future__ import annotations

from pathlib import Path

import pytest

from siderea.research.robust_phase_receipts import (
    PHASE_ORDER,
    freeze_phase_receipt,
    verify_phase_receipt,
)


def _artifact(root: Path, name: str, content: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_phase_receipt_binds_artifact_and_is_immutable(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path, "development/summary.json", '{"status":"complete"}\n')
    receipt = tmp_path / "receipts/development.json"

    digest = freeze_phase_receipt(
        receipt,
        phase="development_complete",
        study_root=tmp_path,
        artifacts=[artifact],
    )

    assert len(digest) == 64
    payload = verify_phase_receipt(receipt, study_root=tmp_path)
    assert payload["phase"] == "development_complete"
    assert payload["artifacts"][0]["path"] == "development/summary.json"
    with pytest.raises(FileExistsError, match="already exists"):
        freeze_phase_receipt(
            receipt,
            phase="development_complete",
            study_root=tmp_path,
            artifacts=[artifact],
        )


def test_artifact_drift_fails_closed(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path, "development/summary.json", "before\n")
    receipt = tmp_path / "receipts/development.json"
    freeze_phase_receipt(
        receipt,
        phase="development_complete",
        study_root=tmp_path,
        artifacts=[artifact],
    )

    artifact.write_text("after\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="artifact drifted"):
        verify_phase_receipt(receipt, study_root=tmp_path)


def test_phase_chain_requires_immediate_predecessor(tmp_path: Path) -> None:
    development_artifact = _artifact(tmp_path, "development/summary.json", "dev\n")
    development_receipt = tmp_path / "receipts/development.json"
    freeze_phase_receipt(
        development_receipt,
        phase="development_complete",
        study_root=tmp_path,
        artifacts=[development_artifact],
    )

    selection_artifact = _artifact(tmp_path, "development/selection.json", "selected\n")
    selection_receipt = tmp_path / "receipts/selection.json"
    freeze_phase_receipt(
        selection_receipt,
        phase="selection_frozen",
        study_root=tmp_path,
        artifacts=[selection_artifact],
        previous_receipt=development_receipt,
    )
    assert verify_phase_receipt(selection_receipt, study_root=tmp_path)["phase"] == (
        "selection_frozen"
    )

    calibration_artifact = _artifact(tmp_path, "calibration/summary.json", "cal\n")
    with pytest.raises(RuntimeError, match="requires predecessor calibration_complete"):
        freeze_phase_receipt(
            tmp_path / "receipts/threshold.json",
            phase="threshold_frozen",
            study_root=tmp_path,
            artifacts=[calibration_artifact],
            previous_receipt=selection_receipt,
        )


def test_later_phase_without_predecessor_fails_closed(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path, "calibration/summary.json", "cal\n")
    with pytest.raises(ValueError, match="requires the immediately preceding"):
        freeze_phase_receipt(
            tmp_path / "receipts/calibration.json",
            phase="calibration_complete",
            study_root=tmp_path,
            artifacts=[artifact],
        )


def test_artifacts_cannot_escape_study_root(tmp_path: Path) -> None:
    study_root = tmp_path / "study"
    study_root.mkdir()
    outside = _artifact(tmp_path, "outside.txt", "outside\n")
    with pytest.raises(ValueError, match="outside the study root"):
        freeze_phase_receipt(
            study_root / "receipt.json",
            phase="development_complete",
            study_root=study_root,
            artifacts=[outside],
        )


def test_phase_order_is_explicit_and_complete() -> None:
    assert PHASE_ORDER == (
        "development_complete",
        "selection_frozen",
        "calibration_complete",
        "threshold_frozen",
        "locked_evaluation_complete",
        "generalization_complete",
    )
