"""Reconstruct manuscript experiments in a new, self-contained source workspace.

No live requests or learned-model training. Comparisons fail on scientific output
or trial-digest drift; timestamps and rendering bytes are not scientific equality.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from siderea.research.archives import verify_archive

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_results(reference: Path, reproduced: Path) -> dict:
    old = verify_archive(reference)
    new = verify_archive(reproduced)
    checks = {
        "protocol_equal": old["protocol_digest"] == new["protocol_digest"],
        "rows_equal": old["results"] == new["results"],
        "trials_equal": old["trial_statistics_sha256"] == new["trial_statistics_sha256"],
        "rows": len(new["results"]),
        "trial_sha256": new["trial_statistics_sha256"],
    }
    if not all(checks[key] for key in ("protocol_equal", "rows_equal", "trials_equal")):
        raise ValueError(f"scientific reconstruction differs: {reference.name}: {checks}")
    return checks


def run(output: Path) -> dict:
    output = output.resolve()
    if (
        output == ROOT
        or output.is_relative_to(ROOT / "paper")
        or output.is_relative_to(ROOT / "src")
    ):
        raise ValueError("output must be outside source and paper directories")
    output.mkdir(parents=True, exist_ok=False)
    workspace = output / "workspace"
    workspace.mkdir()
    report = {
        "schema": "siderea.paper_reconstruction.v1",
        "started_at": datetime.now(UTC).isoformat(),
        "scope": "historical_figure_and_synthetic_reconstruction_not_live_science",
        "python": sys.version,
        "commands": [],
        "checks": {},
        "passed": False,
    }
    try:
        # Explicit input allowlist; never copy environment files, credentials or ledgers.
        for name in ("src", "paper", "examples", "configs"):
            shutil.copytree(
                ROOT / name,
                workspace / name,
                ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", "*.egg-info", "*.aux", "*.log", "*.out", "*.xdv"
                ),
            )
        for name in ("pyproject.toml", "README.md", "MANIFEST.in", "PIPELINE_OPERATIONS_RECORD.md"):
            shutil.copy2(ROOT / name, workspace / name)
        inventory = {
            str(p.relative_to(workspace)): sha(p)
            for p in sorted(workspace.rglob("*"))
            if p.is_file()
        }
        (output / "input-manifest.json").write_text(json.dumps(inventory, indent=2) + "\n")
        report["input_manifest_sha256"] = sha(output / "input-manifest.json")
        dependencies = sorted(
            f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions()
        )
        (output / "runtime-dependencies.txt").write_text("\n".join(dependencies) + "\n")
        report["runtime_dependencies_sha256"] = sha(output / "runtime-dependencies.txt")
        env = os.environ.copy()
        env["PYTHONPATH"] = str(workspace / "src")
        env.setdefault("MPLCONFIGDIR", str(output / "matplotlib-cache"))

        def execute(arguments: list[str], log_name: str) -> None:
            command = [sys.executable, *arguments]
            with (output / log_name).open("w") as log:
                result = subprocess.run(
                    command,
                    cwd=workspace,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            report["commands"].append(
                {
                    "argv": ["python", *arguments],
                    "exit_code": result.returncode,
                    "log": log_name,
                    "log_sha256": sha(output / log_name),
                }
            )
            if result.returncode:
                raise RuntimeError(f"command failed; see {log_name}")

        old_metrics = json.loads((workspace / "paper/figures/derived_run_metrics.json").read_text())
        execute(["paper/figures/make_figures.py"], "historical-figures.log")
        new_metrics = json.loads((workspace / "paper/figures/derived_run_metrics.json").read_text())
        if old_metrics != new_metrics:
            raise ValueError("historical metric reconstruction differs")
        report["checks"]["historical_metrics_equal"] = True
        report["checks"]["historical_metrics"] = new_metrics
        for name, runner, protocol, reference in (
            ("iid", "run_transient_search.py", "transient_protocol.json", "transient-search-final"),
            (
                "covariance",
                "run_transient_search.py",
                "covariance_protocol.json",
                "covariance-search-final",
            ),
            ("noise", "run_noise_stress.py", "noise_stress_protocol.json", "noise-stress-final"),
        ):
            execute(
                [
                    f"paper/experiments/{runner}",
                    "--protocol",
                    f"paper/experiments/{protocol}",
                    "--output",
                    f"reproduced/{name}",
                ],
                f"{name}.log",
            )
            report["checks"][name] = compare_results(
                workspace / "paper/experiments" / reference, workspace / "reproduced" / name
            )
        execute(["paper/experiments/make_tables.py", "--output", "reproduced/tables"], "tables.log")
        for name in ("search_results_table.tex", "noise_results_table.tex"):
            if (workspace / "reproduced/tables" / name).read_bytes() != (
                workspace / "paper/experiments" / name
            ).read_bytes():
                raise ValueError(f"generated manuscript table differs: {name}")
        report["checks"]["generated_tables_equal"] = True
        report["passed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        (output / "reconstruction.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
