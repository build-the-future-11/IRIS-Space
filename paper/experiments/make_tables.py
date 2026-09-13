"""Generate manuscript count tables directly from archived synthetic results."""

from __future__ import annotations

import argparse
from pathlib import Path

from siderea.research.archives import verify_archive


def generate(root: Path) -> dict[str, str]:
    iid = verify_archive(root / "transient-search-final")["results"]
    covariance = verify_archive(root / "covariance-search-final")["results"]
    noise = verify_archive(root / "noise-stress-final")["results"]

    def count(rows, scenario, method, amplitude=0):
        matches = [
            r
            for r in rows
            if r["scenario"] == scenario
            and r["method"] == method
            and r["amplitude_sigma"] == amplitude
        ]
        if len(matches) != 1 or matches[0]["trials"] != 1000:
            raise ValueError("table requires one matching row with exactly 1000 trials")
        return matches[0]["detections"]

    header = [r"\begin{table}[ht]", r"\centering"]
    search = header + [
        r"\caption{Measured synthetic detections per 1,000 evaluation curves. "
        r"Pulse rows are recovery; null and outlier rows are false alarms. "
        r"The last row uses a new seed and supplied covariance.}",
        r"\label{tab:search-diagnostic}",
        r"\begin{tabular}{p{0.47\linewidth}rr}",
        r"\toprule",
        r"Scenario & Bank & Single epoch \\",
        r"\midrule",
    ]
    for title, scenario, amplitude, rows in [
        ("Gaussian pulse, 2-sigma peak", "gaussian", 2, iid),
        ("Exponential pulse, 2-sigma peak", "exponential", 2, iid),
        ("Bazin pulse, 2-sigma peak", "bazin", 2, iid),
        ("Fallback pulse, 2-sigma peak", "fallback", 2, iid),
        ("Independent Gaussian null", "independent_gaussian", 0, iid),
        ("AR(1), diagonal calibration", "ar1_rho_0.7", 0, iid),
        ("One positive 8-sigma outlier", "single_positive_8sigma_outlier", 0, iid),
        ("AR(1), known-covariance calibration", "ar1_rho_0.7", 0, covariance),
    ]:
        bank = count(rows, scenario, "bank", amplitude)
        single = count(rows, scenario, "single_epoch", amplitude)
        search.append(f"{title} & {bank} & {single} " + r"\\")
    footer = [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    stress = header + [
        r"\caption{All declared exponential-covariance null stresses. "
        r"Each row uses 1,000 evaluation curves. Intervals are marginal 95\% Wilson "
        r"intervals conditional on the simulated cadence, not survey uncertainty.}",
        r"\label{tab:noise-stress}",
        r"\begin{tabular}{p{0.48\linewidth}rr}",
        r"\toprule",
        r"Null scenario & False alarms & Fraction interval \\",
        r"\midrule",
    ]
    for row in noise:
        if row["trials"] != 1000:
            raise ValueError("noise table requires 1000 trials per row")
        title = row["scenario"].replace("_", " ")
        lo, hi = row["wilson_95"]
        stress.append(f"{title} & {row['false_alarms']} & [{lo:.3f}, {hi:.3f}] " + r"\\")
    return {
        "search_results_table.tex": "\n".join(search + footer) + "\n",
        "noise_results_table.tex": "\n".join(stress + footer) + "\n",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    tables = generate(Path(__file__).resolve().parent)
    args.output.mkdir(parents=True, exist_ok=False)
    for name, content in tables.items():
        (args.output / name).write_text(content)
