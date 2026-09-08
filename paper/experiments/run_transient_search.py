"""Reproduce the fixed synthetic experiment; never queries live sky services."""

from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path
from statistics import NormalDist

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from siderea.atomic import atomic_create_binary
from siderea.provenance import digest_file, digest_value, stable_json
from siderea.research.transients import TransientBank, transient_template


def interval(successes, n, confidence):
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p = successes / n
    divisor = 1 + z * z / n
    center = (p + z * z / (2 * n)) / divisor
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / divisor
    return [max(0.0, center - half), min(1.0, center + half)]


def run(protocol_path, destination):
    config = json.loads(protocol_path.read_text())
    if destination.exists():
        raise FileExistsError("experiment destination exists; preserve previous results")
    destination.mkdir(parents=True)
    protocol_digest = digest_value(config)
    (destination / "protocol.json").write_text(stable_json(config) + "\n")
    source_path = Path(__file__).resolve().parents[2] / "src/siderea/research/transients.py"
    (destination / "transients.source.txt").write_bytes(source_path.read_bytes())
    (destination / "runner.source.txt").write_bytes(Path(__file__).read_bytes())
    seeds = np.random.SeedSequence(config["master_seed"]).spawn(4)
    cadence, calibration, testing, signals = [np.random.default_rng(s) for s in seeds]
    count, n = config["epochs"], config["evaluation_trials"]
    time = np.sort(cadence.uniform(0, config["duration_days"], count))
    error = cadence.uniform(0.7, 1.3, count)
    rho = config.get("calibration_correlation_rho", 0.0)
    correlation = rho ** np.abs(np.arange(count)[:, None] - np.arange(count))
    factor = np.linalg.cholesky(correlation)
    bank = TransientBank(
        time,
        error,
        centers=np.linspace(time.min(), time.max(), config["center_count"]),
        widths=config["widths_days"],
        families=config["families"],
        correlation=correlation if rho else None,
    )
    weights = 1 / error**2

    def baseline(curves):
        mean = np.average(curves, axis=1, weights=weights)
        return np.maximum(0, ((curves - mean[:, None]) / error).max(axis=1))

    null = calibration.normal(size=(config["calibration_trials"], count)) @ factor.T * error
    calibrations = {"bank": np.sort(bank.statistics(null)), "single_epoch": np.sort(baseline(null))}
    rows = []
    measurements = []

    def evaluate(label, flux, amplitude=0):
        for method, values in [("bank", bank.statistics(flux)), ("single_epoch", baseline(flux))]:
            reference = calibrations[method]
            p = (1 + len(reference) - np.searchsorted(reference, values, side="left")) / (
                len(reference) + 1
            )
            detected = p <= config["alpha"]
            total = int(detected.sum())
            rows.append(
                {
                    "scenario": label,
                    "amplitude_sigma": amplitude,
                    "method": method,
                    "trials": n,
                    "detections": total,
                    "fraction": total / n,
                    "wilson_interval": interval(total, n, config["confidence"]),
                }
            )
            measurements.append(
                {
                    "scenario": label,
                    "amplitude_sigma": amplitude,
                    "method": method,
                    "statistics": values.tolist(),
                    "pvalues": p.tolist(),
                }
            )

    independent = testing.normal(size=(n, count))
    evaluate("independent_gaussian", independent * error)
    correlated = testing.normal(size=(n, count))
    for i in range(1, count):
        correlated[:, i] = 0.7 * correlated[:, i - 1] + np.sqrt(1 - 0.7**2) * correlated[:, i]
    evaluate("ar1_rho_0.7", correlated * error)
    outliers = testing.normal(size=(n, count))
    outliers[np.arange(n), testing.integers(0, count, n)] += 8
    evaluate("single_positive_8sigma_outlier", outliers * error)
    for family in config["families"]:
        centers = signals.uniform(*config["signal_centers_days"], n)
        widths = np.exp(signals.uniform(*np.log(config["signal_widths_days"]), n))
        templates = np.stack(
            [
                transient_template(time, center=c, width=w, family=family)
                for c, w in zip(centers, widths, strict=True)
            ]
        )
        # Pair methods and amplitudes on identical test noise; intervals are marginal,
        # not an independence claim across rows or a statistical superiority test.
        noise = testing.normal(size=(n, count)) @ factor.T * error
        for amplitude in config["amplitudes_sigma"]:
            evaluate(family, noise + amplitude * np.median(error) * templates, amplitude)
    artifacts = {
        "times_days": time.tolist(),
        "errors": error.tolist(),
        "calibration_statistics": {k: v.tolist() for k, v in calibrations.items()},
        "measurements": measurements,
    }
    raw = destination / "trial_statistics.json"
    raw.write_text(stable_json(artifacts) + "\n")
    report = {
        "schema": "siderea.synthetic_search_results.v1",
        "protocol_digest": protocol_digest,
        "bank_digest": bank.identity,
        "template_count": len(bank.specs),
        "results": rows,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "source_sha256": digest_file(destination / "transients.source.txt"),
        "runner_sha256": digest_file(destination / "runner.source.txt"),
        "calibration_correlation_rho": rho,
        "trial_statistics_sha256": digest_file(raw),
        "limitations": [
            "Synthetic cadence and Gaussian noise with the declared calibration covariance",
            "Conditional on one cadence realization",
            "Any stress row differing from declared covariance violates calibration assumptions",
            "No astrophysical class or survey selection claim",
            "No empirical red-noise calibration or real transient benchmark",
        ],
    }
    report["result_digest"] = digest_value(report)
    encoded = (stable_json(report) + "\n").encode()
    atomic_create_binary(destination / "results.json", lambda handle: handle.write(encoded))
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.1), layout="constrained")
    colors = {
        "gaussian": "#285f91",
        "exponential": "#a4521a",
        "bazin": "#2b7853",
        "fallback": "#79529b",
    }
    for family, color in colors.items():
        for method, style in [("bank", "-"), ("single_epoch", "--")]:
            data = [row for row in rows if row["scenario"] == family and row["method"] == method]
            axes[0].plot(
                [r["amplitude_sigma"] for r in data],
                [r["fraction"] for r in data],
                style,
                color=color,
                marker="o",
                label=f"{family}, {method}",
            )
    axes[0].set(
        xlabel="Injected peak amplitude / median error", ylabel="Recovery fraction", ylim=(0, 1.03)
    )
    axes[0].legend(fontsize=6, loc="lower right")
    names = config["null_stress_tests"]
    for j, method in enumerate(["bank", "single_epoch"]):
        data = [
            next(r for r in rows if r["scenario"] == name and r["method"] == method)
            for name in names
        ]
        axes[1].bar(
            np.arange(3) + (j - 0.5) * 0.34, [r["fraction"] for r in data], 0.34, label=method
        )
    axes[1].axhline(config["alpha"], color="black", linestyle=":", label="nominal 1%")
    axes[1].set_xticks(range(3), ["Gaussian", "AR(1), 0.7", "8-sigma outlier"])
    axes[1].set(ylabel="False-alarm fraction", ylim=(0, 1.03))
    axes[1].legend(fontsize=8)
    fig.savefig(destination / "search_diagnostic.png", dpi=200)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--protocol", type=Path, default=Path(__file__).with_name("transient_protocol.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.protocol, args.output)
