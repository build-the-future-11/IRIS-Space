"""Protect scientific comparison from accepting altered or mismatched trial archives."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "paper_reconstruct", Path(__file__).resolve().parents[1] / "paper/reconstruct.py"
)
assert SPEC is not None and SPEC.loader is not None
RECONSTRUCT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECONSTRUCT)


def archive(path, rows=None, protocol=None):
    source = Path(__file__).resolve().parents[1] / "paper/experiments/transient-search-final"
    shutil.copytree(source, path)
    report_path = path / "results.json"
    report = json.loads(report_path.read_text())
    if rows is not None:
        report["results"] = rows
    if protocol is not None:
        report["protocol_digest"] = protocol
    report_path.write_text(json.dumps(report))
    return path


def test_reconstruction_accepts_identical_science(tmp_path):
    reference = archive(tmp_path / "reference")
    reproduced = archive(tmp_path / "reproduced")
    assert RECONSTRUCT.compare_results(reference, reproduced)["trials_equal"]


@pytest.mark.parametrize("mutation", ["trial", "rows", "protocol"])
def test_reconstruction_rejects_tampering_and_drift(tmp_path, mutation):
    reference = archive(tmp_path / "reference")
    reproduced = archive(
        tmp_path / "reproduced",
        rows=[{"detections": 2}] if mutation == "rows" else None,
        protocol="changed" if mutation == "protocol" else None,
    )
    if mutation == "trial":
        (reproduced / "trial_statistics.json").write_text("changed")
    with pytest.raises(ValueError):
        RECONSTRUCT.compare_results(reference, reproduced)


def test_reconstruction_preserves_existing_output(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "result"
    sentinel.write_text("keep")
    with pytest.raises(FileExistsError):
        RECONSTRUCT.run(output)
    assert sentinel.read_text() == "keep"
