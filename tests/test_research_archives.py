"""Manuscript evidence must remain consistent even after a report is re-hashed."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

from siderea.provenance import digest_file, digest_value
from siderea.research.archives import verify_archive

ROOT = Path(__file__).resolve().parents[1]
ARCHIVES = ("transient-search-final", "covariance-search-final", "noise-stress-final")


@pytest.mark.parametrize("name", ARCHIVES)
def test_archived_science_verifies(name):
    assert verify_archive(ROOT / "paper/experiments" / name)["results"]


@pytest.mark.parametrize("name", [ARCHIVES[0], ARCHIVES[2]])
@pytest.mark.parametrize(
    "mutation",
    [
        "count",
        "interval",
        "fraction",
        "duplicate",
        "missing",
        "pvalues",
        "protocol",
        "source",
        "trials",
    ],
)
def test_inconsistent_archives_rejected_even_with_refreshed_report_digest(tmp_path, name, mutation):
    folder = tmp_path / name
    shutil.copytree(ROOT / "paper/experiments" / name, folder)
    report_path = folder / "results.json"
    report = json.loads(report_path.read_text())
    noise = name == "noise-stress-final"
    if mutation == "count":
        report["results"][0]["false_alarms" if noise else "detections"] += 1
    elif mutation == "interval":
        report["results"][0]["wilson_95" if noise else "wilson_interval"][0] = 0.99
    elif mutation == "fraction":
        report["results"][0]["fraction"] = 0.99
    elif mutation == "duplicate":
        report["results"][-1] = report["results"][0]
    elif mutation == "missing":
        report["results"].pop()
    elif mutation == "protocol":
        (folder / "protocol.json").write_text("{}")
    elif mutation == "source":
        (folder / "transients.source.txt").write_text("modified")
    elif mutation == "trials":
        (folder / "trial_statistics.json").write_text("{}")
    else:
        trial_path = folder / "trial_statistics.json"
        trials = json.loads(trial_path.read_text())
        measurement = trials[0] if noise else trials["measurements"][0]
        measurement["pvalues"][0] = 0.0
        trial_path.write_text(json.dumps(trials))
        report["trial_statistics_sha256"] = digest_file(trial_path)
    digest_key = "digest" if noise else "result_digest"
    report[digest_key] = digest_value({k: v for k, v in report.items() if k != digest_key})
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError):
        verify_archive(folder)


def test_generated_tables_remain_identical():
    script = ROOT / "paper/experiments/make_tables.py"
    spec = importlib.util.spec_from_file_location("paper_tables", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, contents in module.generate(script.parent).items():
        assert contents == (script.parent / name).read_text()


@pytest.mark.parametrize("runner", ["run_transient_search.py", "run_noise_stress.py"])
def test_runner_rejects_wrong_imported_detector_before_creating_output(
    tmp_path, monkeypatch, runner
):
    monkeypatch.syspath_prepend(str(ROOT / "paper/experiments"))
    spec = importlib.util.spec_from_file_location(
        "experiment_runner", ROOT / "paper/experiments" / runner
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class DifferentDetector:
        pass

    monkeypatch.setattr(module, "TransientBank", DifferentDetector)
    protocol = "noise_stress_protocol.json" if "noise" in runner else "transient_protocol.json"
    output = tmp_path / "experiment"
    with pytest.raises(ValueError, match="Imported detector differs"):
        module.run(ROOT / "paper/experiments" / protocol, output)
    assert not output.exists()


@pytest.mark.parametrize("noise", [False, True])
@pytest.mark.parametrize(
    "field,value",
    [
        ("evaluation_trials", 0),
        ("calibration_trials", True),
        ("epochs", 2),
        ("alpha", 1),
        ("duration_days", -1),
        ("widths_days", [0]),
        ("schema", "future"),
    ],
)
def test_invalid_protocol_rejected(noise, field, value):
    from siderea.research.archives import validate_experiment_protocol

    name = "noise_stress_protocol.json" if noise else "transient_protocol.json"
    config = json.loads((ROOT / "paper/experiments" / name).read_text())
    config[field] = value
    with pytest.raises(ValueError):
        validate_experiment_protocol(config, noise=noise)


@pytest.mark.parametrize(
    "noise,field,value",
    [
        (True, "scenarios", ["misspelled_stress"]),
        (True, "scenarios", ["matched_gaussian", "matched_gaussian"]),
        (False, "null_stress_tests", ["unimplemented"]),
        (False, "families", ["gaussian", "gaussian"]),
        (False, "amplitudes_sigma", [2, 2]),
    ],
)
def test_runner_rejects_unsupported_or_duplicate_protocol_before_output(
    tmp_path, monkeypatch, noise, field, value
):
    monkeypatch.syspath_prepend(str(ROOT / "paper/experiments"))
    runner = "run_noise_stress.py" if noise else "run_transient_search.py"
    spec = importlib.util.spec_from_file_location(
        "experiment_runner", ROOT / "paper/experiments" / runner
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    name = "noise_stress_protocol.json" if noise else "transient_protocol.json"
    config = json.loads((ROOT / "paper/experiments" / name).read_text())
    config[field] = value
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps(config))
    output = tmp_path / "experiment"
    with pytest.raises(ValueError):
        module.run(protocol, output)
    assert not output.exists()


def test_noise_stress_uses_configured_duration(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "paper/experiments"))
    spec = importlib.util.spec_from_file_location(
        "noise_runner", ROOT / "paper/experiments/run_noise_stress.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = json.loads((ROOT / "paper/experiments/noise_stress_protocol.json").read_text())
    config.update(
        duration_days=90,
        epochs=16,
        centers=5,
        calibration_trials=199,
        evaluation_trials=25,
        scenarios=["seasonal_gap_matched", "variance_doubles_second_half"],
    )
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps(config))
    output = tmp_path / "experiment"
    module.run(protocol, output)
    assert len(verify_archive(output)["results"]) == 2
    trials = json.loads((output / "trial_statistics.json").read_text())
    times = trials[0]["times"]
    assert max(times) > 60
    assert all(0 <= t < 30 or 60 <= t <= 90 for t in times)
