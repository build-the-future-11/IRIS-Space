from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest

torch = pytest.importorskip("torch")

from siderea.research.space_jepa_v2_campaign import run_space_jepa_v2_campaign  # noqa: E402
from space_jepa_v2_split_fixture import prepared_fixture  # noqa: E402


def _campaign_with_prepared_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    prepared, survey, protocol = prepared_fixture(tmp_path)
    root = tmp_path / "campaign"
    (root / "data").mkdir(parents=True)
    shutil.copytree(prepared, root / "data/prepared")
    tns = tmp_path / "tns.csv"
    pd.DataFrame([{"objid": 1, "objname": "2026abc", "ra": 1.0}]).to_csv(tns, index=False)
    return root, tns, survey, Path(protocol)


def test_resume_rejects_prepared_tensor_drift_before_training(tmp_path: Path) -> None:
    root, tns, survey, protocol = _campaign_with_prepared_fixture(tmp_path)
    train = root / "data/prepared/train.pt"
    train.write_bytes(train.read_bytes() + b"drift")

    status = run_space_jepa_v2_campaign(
        protocol_path=protocol,
        tns_input=tns,
        survey_input=survey,
        output=root,
        resume=True,
        epochs=1,
        batch_size=4,
        device="cpu",
    )

    assert status["state"] == "BLOCKED_VALIDATION"
    assert "train.pt digest differs" in status["blockers"][0]
    assert not list((root / "checkpoints").glob("*.pt"))
    assert not (root / "forecasts/work-cells.json").exists()


def test_integrity_receipt_is_written_before_tensor_loading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, tns, survey, protocol = _campaign_with_prepared_fixture(tmp_path)

    def refuse_tensor_load(*args, **kwargs):
        raise RuntimeError("sentinel: tensor loading reached")

    monkeypatch.setattr(torch, "load", refuse_tensor_load)
    status = run_space_jepa_v2_campaign(
        protocol_path=protocol,
        tns_input=tns,
        survey_input=survey,
        output=root,
        resume=True,
        epochs=1,
        batch_size=4,
        device="cpu",
    )

    assert status["state"] == "BLOCKED_VALIDATION"
    assert "sentinel: tensor loading reached" in status["blockers"][0]
    receipt = json.loads((root / "data/prepared-integrity.json").read_text())
    assert receipt["status"] == "PASS"
    assert receipt["scope"] == "integrity_only_no_model_execution"
    assert receipt["prepared_manifest_digest"] == json.loads(
        (root / "data/prepared/manifest.json").read_text()
    )["result_digest"]
