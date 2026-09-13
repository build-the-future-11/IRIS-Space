"""Verify synthetic experiment archives before using them as manuscript evidence.

Checksums detect changes, not authorship. Recomputed ranks and summaries establish
internal consistency; they do not establish real-sky performance or provenance
against an independently trusted release digest.
"""

from __future__ import annotations

import json
import math
from bisect import bisect_left
from pathlib import Path
from statistics import NormalDist
from typing import Any

from siderea.provenance import digest_file, digest_value


def _read(path: Path) -> Any:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    value = json.loads(path.read_text(), object_pairs_hook=unique)
    digest_value(value)  # Reject non-finite, non-standard JSON numbers.
    return value


def _vector(value: Any, length: int) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError("trial vector length differs from protocol")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError("trial vector must contain finite numbers")
    return [float(v) for v in value]


def _wilson(k: int, n: int, confidence: float) -> list[float]:
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p = k / n
    divisor = 1 + z * z / n
    center = (p + z * z / (2 * n)) / divisor
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / divisor
    return [max(0.0, center - half), min(1.0, center + half)]


NOISE_SCENARIOS = frozenset(
    {
        "matched_gaussian",
        "errors_underestimated_1.5",
        "student_t_3_unit_variance",
        "variance_doubles_second_half",
        "seasonal_gap_matched",
        "true_timescale_1_day",
        "true_timescale_20_days",
    }
)
NULL_SCENARIOS = ["independent_gaussian", "ar1_rho_0.7", "single_positive_8sigma_outlier"]


def validate_experiment_protocol(config: dict[str, Any], *, noise: bool) -> None:
    """Reject unsupported experiment labels instead of silently simulating a null."""
    if not isinstance(config, dict):
        raise ValueError("experiment protocol must be an object")
    schema = "siderea.noise_stress_protocol.v1" if noise else "siderea.synthetic_search_protocol.v1"
    if config.get("schema") != schema:
        raise ValueError("unsupported experiment protocol schema")
    digest_value(config)
    fields = (
        "epochs",
        "calibration_trials",
        "evaluation_trials",
        "centers" if noise else "center_count",
    )
    for field in fields:
        if type(config.get(field)) is not int or config[field] <= 0:
            raise ValueError(f"{field} must be a positive integer")
    if config["epochs"] < 3:
        raise ValueError("experiment needs at least three epochs")
    seed = config.get("seed" if noise else "master_seed")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    for field in ("alpha",) if noise else ("alpha", "confidence"):
        if type(config.get(field)) not in (int, float) or not 0 < config[field] < 1:
            raise ValueError(f"{field} must lie strictly between zero and one")
    for field in ("duration_days", "assumed_timescale_days") if noise else ("duration_days",):
        if type(config.get(field)) not in (int, float) or config[field] <= 0:
            raise ValueError(f"{field} must be positive")
    widths = config.get("widths_days")
    if (
        not isinstance(widths, list)
        or not widths
        or any(type(w) not in (int, float) or w <= 0 for w in widths)
    ):
        raise ValueError("widths_days must contain positive widths")
    if noise:
        names = config.get("scenarios")
        if (
            not isinstance(names, list)
            or not names
            or any(not isinstance(name, str) or name not in NOISE_SCENARIOS for name in names)
            or len(set(names)) != len(names)
        ):
            raise ValueError("noise scenarios must be supported and unique")
        fraction = config.get("correlated_fraction")
        if fraction is None or type(fraction) not in (int, float) or not 0 <= fraction < 1:
            raise ValueError("correlated_fraction must be in [0, 1)")
    else:
        if config.get("null_stress_tests") != NULL_SCENARIOS:
            raise ValueError("runner requires the declared fixed null stress scenarios")
        families = config.get("families")
        if (
            not isinstance(families, list)
            or not families
            or any(f not in ("gaussian", "exponential", "bazin", "fallback") for f in families)
            or len(set(families)) != len(families)
        ):
            raise ValueError("template families must be supported and unique")
        amplitudes = config.get("amplitudes_sigma")
        if (
            not isinstance(amplitudes, list)
            or not amplitudes
            or any(type(a) not in (int, float) or a <= 0 for a in amplitudes)
            or len(set(amplitudes)) != len(amplitudes)
        ):
            raise ValueError("signal amplitudes must be positive and unique")
        for field in ("signal_centers_days", "signal_widths_days"):
            bounds = config.get(field)
            if (
                not isinstance(bounds, list)
                or len(bounds) != 2
                or any(type(v) not in (int, float) for v in bounds)
                or not bounds[0] < bounds[1]
                or (field == "signal_widths_days" and bounds[0] <= 0)
            ):
                raise ValueError(f"{field} requires ordered valid bounds")
        rho = config.get("calibration_correlation_rho", 0)
        if type(rho) not in (int, float) or not -1 < rho < 1:
            raise ValueError("calibration correlation must lie strictly between -1 and 1")


def verify_archive(folder: Path) -> dict[str, Any]:
    """Load a supported archive or fail before downstream tables are generated."""
    try:
        return _verify(folder)
    except (KeyError, TypeError, IndexError, AttributeError, OSError) as exc:
        raise ValueError(f"incomplete or malformed experiment archive: {folder.name}") from exc


def _verify(folder: Path) -> dict[str, Any]:
    report = _read(folder / "results.json")
    if not isinstance(report, dict):
        raise ValueError("experiment report must be an object")
    schema = report["schema"]
    if schema not in ("siderea.synthetic_search_results.v1", "siderea.noise_stress_results.v1"):
        raise ValueError("unsupported experiment schema")
    noise = schema == "siderea.noise_stress_results.v1"
    digest_key = "digest" if noise else "result_digest"
    if report[digest_key] != digest_value({k: v for k, v in report.items() if k != digest_key}):
        raise ValueError("result digest mismatch")
    protocol = _read(folder / "protocol.json")
    validate_experiment_protocol(protocol, noise=noise)
    if digest_value(protocol) != report["protocol_digest"]:
        raise ValueError("protocol digest mismatch")
    sources = (
        report["source_digests"]
        if noise
        else {
            "transients.source.txt": report["source_sha256"],
            "runner.source.txt": report["runner_sha256"],
        }
    )
    expected_sources = {"runner.source.txt", "transients.source.txt"}
    if noise:
        expected_sources.add("interval.source.txt")
    if set(sources) != expected_sources:
        raise ValueError("source inventory mismatch")
    for name, expected in sources.items():
        if digest_file(folder / name) != expected:
            raise ValueError(f"source digest mismatch: {name}")
    if digest_file(folder / "trial_statistics.json") != report["trial_statistics_sha256"]:
        raise ValueError("trial integrity mismatch")
    trials = _read(folder / "trial_statistics.json")
    n, calibration_n = protocol["evaluation_trials"], protocol["calibration_trials"]
    if any(type(v) is not int or v <= 0 for v in (n, calibration_n)):
        raise ValueError("protocol requires positive integer trial counts")
    alpha = protocol["alpha"]
    confidence = 0.95 if noise else protocol["confidence"]
    if not 0 < alpha < 1 or not 0 < confidence < 1:
        raise ValueError("invalid probability in protocol")
    expected_keys: list[tuple[Any, ...]]
    if noise:
        expected_keys = [(name,) for name in protocol["scenarios"]]
        measurements = trials
    else:
        scenarios = [
            ("independent_gaussian", 0),
            ("ar1_rho_0.7", 0),
            ("single_positive_8sigma_outlier", 0),
        ] + [(f, a) for f in protocol["families"] for a in protocol["amplitudes_sigma"]]
        expected_keys = [(s, a, m) for s, a in scenarios for m in ("bank", "single_epoch")]
        measurements = trials["measurements"]

    def key(row: dict[str, Any]) -> tuple[Any, ...]:
        return (
            (row["scenario"],)
            if noise
            else (row["scenario"], row["amplitude_sigma"], row["method"])
        )

    if len(set(expected_keys)) != len(expected_keys):
        raise ValueError("duplicate protocol scenarios")
    for rows in (report["results"], measurements):
        keys = [key(row) for row in rows]
        if len(keys) != len(expected_keys) or set(keys) != set(expected_keys):
            raise ValueError("missing, duplicate or unexpected experiment rows")
    indexed = {key(row): row for row in measurements}
    for row in report["results"]:
        trial = indexed[key(row)]
        reference = _vector(
            trial["calibration_statistics"]
            if noise
            else trials["calibration_statistics"][row["method"]],
            calibration_n,
        )
        if reference != sorted(reference):
            raise ValueError("calibration statistics must be sorted")
        statistics = _vector(trial["statistics"], n)
        pvalues = _vector(trial["pvalues"], n)
        expected_p = [
            (1 + calibration_n - bisect_left(reference, v)) / (calibration_n + 1)
            for v in statistics
        ]
        if pvalues != expected_p:
            raise ValueError("p-values disagree with calibrated plus-one ranks")
        detected = sum(p <= alpha for p in pvalues)
        count_key = "false_alarms" if noise else "detections"
        if (
            type(row[count_key]) is not int
            or row[count_key] != detected
            or type(row["trials"]) is not int
            or row["trials"] != n
        ):
            raise ValueError("summary counts disagree with trials")
        if not math.isclose(row["fraction"], detected / n, rel_tol=0, abs_tol=1e-14):
            raise ValueError("summary fraction disagrees with trials")
        actual_ci = _vector(row["wilson_95" if noise else "wilson_interval"], 2)
        if any(
            not math.isclose(a, b, rel_tol=0, abs_tol=1e-14)
            for a, b in zip(actual_ci, _wilson(detected, n, confidence), strict=True)
        ):
            raise ValueError("summary Wilson interval disagrees with trials")
    return report
