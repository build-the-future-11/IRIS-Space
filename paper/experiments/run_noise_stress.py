"""Fixed-design null stress experiment; preserves every scenario and trial."""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from run_transient_search import interval

from siderea.provenance import digest_file, digest_value, stable_json
from siderea.research.transients import TransientBank


def run(protocol: Path, output: Path) -> None:
    config = json.loads(protocol.read_text())
    output.mkdir(parents=True, exist_ok=False)
    (output / "protocol.json").write_text(stable_json(config) + "\n")
    sources = {
        "runner.source.txt": Path(__file__),
        "interval.source.txt": Path(__file__).with_name("run_transient_search.py"),
        "transients.source.txt": Path(__file__).resolve().parents[2]
        / "src/siderea/research/transients.py",
    }
    for name, path in sources.items():
        (output / name).write_bytes(path.read_bytes())
    seeds = np.random.SeedSequence(config["seed"]).spawn(1 + 2 * len(config["scenarios"]))
    cadence_rng = np.random.default_rng(seeds[0])
    n = config["epochs"]
    ordinary = np.sort(cadence_rng.uniform(0, config["duration_days"], n))
    gap = np.sort(
        np.concatenate(
            [cadence_rng.uniform(0, 20, n // 2), cadence_rng.uniform(40, 60, n - n // 2)]
        )
    )
    errors = cadence_rng.uniform(0.7, 1.3, n)
    results, trials = [], []
    for index, name in enumerate(config["scenarios"]):
        calibration = np.random.default_rng(seeds[1 + 2 * index])
        evaluation = np.random.default_rng(seeds[2 + 2 * index])
        times = gap if name == "seasonal_gap_matched" else ordinary

        def covariance(tau, times=times):
            fraction = config["correlated_fraction"]
            return fraction * np.exp(-np.abs(times[:, None] - times) / tau) + (
                1 - fraction
            ) * np.eye(n)

        assumed = covariance(config["assumed_timescale_days"])
        bank = TransientBank(
            times,
            errors,
            centers=np.linspace(times.min(), times.max(), config["centers"]),
            widths=config["widths_days"],
            correlation=assumed,
        )
        null = (
            calibration.normal(size=(config["calibration_trials"], n))
            @ np.linalg.cholesky(assumed).T
            * errors
        )
        reference = np.sort(bank.statistics(null))
        m = config["evaluation_trials"]
        innovations = (
            evaluation.standard_t(3, size=(m, n)) / np.sqrt(3)
            if name == "student_t_3_unit_variance"
            else evaluation.normal(size=(m, n))
        )
        tau = {"true_timescale_1_day": 1, "true_timescale_20_days": 20}.get(
            name, config["assumed_timescale_days"]
        )
        flux = innovations @ np.linalg.cholesky(covariance(tau)).T * errors
        if name == "errors_underestimated_1.5":
            flux *= 1.5
        if name == "variance_doubles_second_half":
            flux[:, times > 30] *= np.sqrt(2)
        values = bank.statistics(flux)
        pvalues = (1 + len(reference) - np.searchsorted(reference, values, side="left")) / (
            len(reference) + 1
        )
        detections = int(np.sum(pvalues <= config["alpha"]))
        results.append(
            {
                "scenario": name,
                "trials": m,
                "false_alarms": detections,
                "fraction": detections / m,
                "wilson_95": interval(detections, m, 0.95),
                "bank_digest": bank.identity,
            }
        )
        trials.append(
            {
                "scenario": name,
                "times": times.tolist(),
                "errors": errors.tolist(),
                "calibration_statistics": reference.tolist(),
                "statistics": values.tolist(),
                "pvalues": pvalues.tolist(),
            }
        )
    trial_file = output / "trial_statistics.json"
    trial_file.write_text(stable_json(trials) + "\n")
    report = {
        "schema": "siderea.noise_stress_results.v1",
        "protocol_digest": digest_value(config),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "source_digests": {name: digest_file(output / name) for name in sources},
        "trial_statistics_sha256": digest_file(trial_file),
        "results": results,
        "scope": config["scope"],
        "interval_scope": "marginal Monte Carlo, conditional on this cadence and supplied model",
    }
    report["digest"] = digest_value(report)
    (output / "results.json").write_text(stable_json(report) + "\n")
    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    positions = np.arange(len(results))
    ax.barh(positions, [r["fraction"] for r in results], color="#285f91")
    for i, row in enumerate(results):
        low, high = row["wilson_95"]
        ax.plot([low, high], [i, i], color="black")
    ax.axvline(config["alpha"], linestyle=":", color="#a4521a", label="Nominal per-curve 1%")
    ax.set_yticks(positions, [r["scenario"].replace("_", " ") for r in results])
    ax.set_xlabel("False-alarm fraction (bars: marginal 95% Wilson intervals)")
    ax.legend()
    fig.savefig(output / "noise_stress.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--protocol", type=Path, default=Path(__file__).with_name("noise_stress_protocol.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.protocol, args.output)
