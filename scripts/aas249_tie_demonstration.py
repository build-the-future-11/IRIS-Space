"""Exhaustive arithmetic illustration for the retained four-row synthetic fixture."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
from fractions import Fraction
from pathlib import Path

from siderea.evaluation import ranking_metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must be new")
    root = Path(__file__).resolve().parents[1]
    fixture = root / "examples/space_jepa_2_tie_fixture.csv"
    with fixture.open(newline="") as stream:
        records = list(csv.DictReader(stream))
    if len(records) != 4:
        raise ValueError("This exhaustive illustration expects the retained four-row fixture")
    rows = []
    for order in itertools.permutations(range(4)):
        selected = [records[i] for i in order]
        labels = [int(row["label"]) for row in selected]
        for name in ("incumbent", "candidate"):
            scores = [float(row[name]) for row in selected]
            ranked = sorted(range(4), key=lambda i: -scores[i])
            for budget in range(1, 5):
                metric = ranking_metrics(labels, scores, review_budget=budget)
                actual_tp = sum(labels[i] for i in ranked[:budget])
                rows.append(
                    {
                        "order": "".join(row["entity_id"] for row in selected),
                        "model_label": name,
                        "review_budget": budget,
                        "expected_precision": metric.precision_at_k,
                        "expected_recall": metric.recall_at_k,
                        "threshold_average_precision": metric.average_precision,
                        "row_order_precision_fraction": str(Fraction(actual_tp, budget)),
                        "row_order_recall_fraction": str(Fraction(actual_tp, 2)),
                    }
                )
    summary = []
    for name in ("incumbent", "candidate"):
        for budget in range(1, 5):
            group = [r for r in rows if r["model_label"] == name and r["review_budget"] == budget]
            points = {
                (r["expected_precision"], r["expected_recall"], r["threshold_average_precision"])
                for r in group
            }
            if len(points) != 1:
                raise RuntimeError("The metric changed under a row permutation")
            exact_precision = sum(Fraction(r["row_order_precision_fraction"]) for r in group) / 24
            exact_recall = sum(Fraction(r["row_order_recall_fraction"]) for r in group) / 24
            precision, recall, ap = next(iter(points))
            if abs(float(exact_precision) - precision) > 1e-14:
                raise RuntimeError("Metric differs from the exhaustive uniform-tie precision")
            if abs(float(exact_recall) - recall) > 1e-14:
                raise RuntimeError("Metric differs from the exhaustive uniform-tie recall")
            summary.append(
                {
                    "model_label": name,
                    "budget": budget,
                    "exact_expected_precision": str(exact_precision),
                    "exact_expected_recall": str(exact_recall),
                    "threshold_average_precision": ap,
                    "row_order_precision_min": str(
                        min(Fraction(r["row_order_precision_fraction"]) for r in group)
                    ),
                    "row_order_precision_max": str(
                        max(Fraction(r["row_order_precision_fraction"]) for r in group)
                    ),
                }
            )
    result = {
        "schema": "siderea.aas249_tie_demonstration.v1",
        "evidence_type": "constructed four-row arithmetic illustration, not sky data",
        "permutations": 24,
        "models": 2,
        "budgets": 4,
        "evaluations": len(rows),
        "result": "PASS",
        "summary": summary,
        "rows": rows,
        "no_training_or_protected_outcomes": True,
        "sources_sha256": {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [fixture, root / "src/siderea/evaluation.py", Path(__file__).resolve()]
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"rows", "sources_sha256"}}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
