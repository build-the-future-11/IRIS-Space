"""Reconcile retained historical summaries without running scientific experiments."""

from __future__ import annotations

import argparse
import json
import re
import runpy
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BINDING = runpy.run_path(str(Path(__file__).with_name("verify_evidence.py")))
HEADER = (
    "| Run | Objects | Detection rows | Clean rows | Sources | Ranked | Early veto | Shortlist |"
)
FIELDS = ("objects", "detections", "clean", "sources", "ranked", "early_veto", "shortlist")
DUPLICATE = "run_20260614T014019Z"
ORIGINAL = "run_20260614T013847Z"
PATHS = {
    "operations": "PIPELINE_OPERATIONS_RECORD.md",
    "derived_metrics": "paper/figures/derived_run_metrics.json",
    "registry_capture": "paper/research/primary-registry/AT2026rsp.public-record.json",
    "software_snapshot": "paper/research/software-verification-2026-09-13.json",
}


def number(cell: str, optional: bool = False) -> int | None:
    if optional and cell == "—":
        return None
    if not re.fullmatch(r"(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)", cell):
        raise ValueError(f"Malformed or missing count: {cell!r}")
    return int(cell.replace(",", ""))


def parse_runs(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    if lines.count(HEADER) != 1:
        raise ValueError("Exactly one canonical productive-run table is required")
    start = lines.index(HEADER)
    if start + 1 >= len(lines) or lines[start + 1] != "|---|---|---|---|---|---|---|---|":
        raise ValueError("Unexpected table separator")
    runs: list[dict[str, Any]] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 8:
            raise ValueError("Run table must have eight columns")
        match = re.fullmatch(r"(run_\d{8}T\d{6}Z)( †)?", cells[0])
        if not match:
            raise ValueError("Malformed run identity or duplicate marker")
        rid = match.group(1)
        datetime.strptime(rid[4:], "%Y%m%dT%H%M%SZ")
        row: dict[str, Any] = {"id": rid, "duplicate": bool(match.group(2))}
        for i, field in enumerate(FIELDS):
            row[field] = number(cells[i + 1], optional=i >= 5)
        if row["objects"] == 0 or row["detections"] == 0:
            raise ValueError("Productive rows need positive object and detection counts")
        if row["clean"] > row["detections"]:
            raise ValueError("Clean rows exceed detection rows")
        runs.append(row)
    if len(runs) != 24 or len({run["id"] for run in runs}) != 24:
        raise ValueError("Expected exactly 24 distinct productive-run identifiers")
    marked = [row["id"] for row in runs if row["duplicate"]]
    if marked != [DUPLICATE]:
        raise ValueError("Only the already-declared duplicate may be excluded")
    by_id = {row["id"]: row for row in runs}
    if ORIGINAL not in by_id or any(
        by_id[ORIGINAL][field] != by_id[DUPLICATE][field] for field in FIELDS
    ):
        raise ValueError("Declared duplicate does not match its original table row")
    return runs


def arithmetic(runs: list[dict[str, Any]]) -> tuple[dict[str, int | float], dict[str, Any]]:
    unique = [row for row in runs if not row["duplicate"]]
    observed = [row for row in unique if all(row[k] is not None for k in FIELDS[-2:])]
    pre = [row for row in observed if row["id"] <= "run_20260705T050105Z"]
    post = [row for row in observed if row["id"] >= "run_20260705T161401Z"]
    if not pre or not post or len(pre) + len(post) != len(observed):
        raise ValueError("Observed rows must fit the existing nonempty pre/post groups")

    def total(group: list[dict[str, Any]], field: str) -> int:
        return sum(row[field] for row in group)

    values: dict[str, int | float] = {
        "productive_runs": len(runs),
        "nonduplicate_pulls": len(unique),
        "unique_pull_detection_rows": total(unique, "detections"),
        "unique_pull_clean_rows": total(unique, "clean"),
        "unique_pull_clean_fraction": total(unique, "clean") / total(unique, "detections"),
    }
    for prefix, group in (("pre", pre), ("post", post)):
        values[f"{prefix}_runs"] = len(group)
        values[f"{prefix}_objects"] = total(group, "objects")
        for field in FIELDS[-2:]:
            values[f"{prefix}_{field}_fraction"] = total(group, field) / total(group, "objects")
    for field in FIELDS[-2:]:
        values[f"delta_{field}"] = (
            values[f"post_{field}_fraction"] - values[f"pre_{field}_fraction"]
        )
    provenance = {
        "excluded_duplicate": DUPLICATE,
        "duplicate_of": ORIGINAL,
        "all_table_detection_rows": total(runs, "detections"),
        "all_table_clean_rows": total(runs, "clean"),
        "pre_run_ids": [row["id"] for row in pre],
        "post_run_ids": [row["id"] for row in post],
        "incomplete_stage_run_ids": [row["id"] for row in unique if row not in observed],
        "method": "Existing cutoff, complete-stage rows, ratio of sums; no bootstrap rerun",
    }
    return values, provenance


def compare_metrics(values: dict[str, int | float], retained: dict[str, Any]) -> None:
    for field, value in values.items():
        actual = retained.get(field)
        if type(actual) is not type(value) or actual != value:
            raise ValueError(f"Retained metric mismatch: {field}")


def load_bound(root: Path, manifest: dict[str, Any], aid: str) -> bytes:
    artifact = next(item for item in manifest["artifacts"] if item["id"] == aid)
    if artifact["path"] != PATHS[aid]:
        raise ValueError(f"Noncanonical source path: {aid}")
    data = BINDING["source_bytes"](root, artifact["path"])
    if BINDING["git_blob_sha"](data) != artifact["git_blob_sha"]:
        raise ValueError(f"Bound source changed during read: {aid}")
    return data


def json_object(data: bytes) -> dict[str, Any]:
    value = json.loads(
        data,
        object_pairs_hook=BINDING["unique_object"],
        parse_constant=BINDING["reject_constant"],
    )
    if not isinstance(value, dict):
        raise ValueError("Evidence JSON must be an object")
    return value


def reconcile(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    binding = BINDING["audit"](root, manifest)
    if binding["source_integrity"] != "PASS":
        raise ValueError("Document binding failed: " + "; ".join(binding["errors"]))
    operations = load_bound(root, manifest, "operations").decode("utf-8")
    retained = json_object(load_bound(root, manifest, "derived_metrics"))
    registry = json_object(load_bound(root, manifest, "registry_capture"))
    software = json_object(load_bound(root, manifest, "software_snapshot"))
    values, provenance = arithmetic(parse_runs(operations))
    compare_metrics(values, retained)
    return {
        "schema": "siderea.iris_historical_reconciliation.v1",
        "source_snapshot_revision": manifest["source_snapshot_revision"],
        "document_binding": binding,
        "historical_arithmetic": "PASS",
        "matched_deterministic_fields": len(values),
        "recomputed": values,
        "provenance": provenance,
        "retained_bootstrap_not_rerun": {
            key: value for key, value in retained.items() if "cluster_" in key
        },
        "registry_capture": {
            "evidence_class": "RETAINED_STRUCTURED_EXTRACTION_ONLY",
            "retrieved_on": registry.get("retrieved_on"),
            "capture_method": registry.get("capture_method"),
            "object_name": registry.get("object_name"),
            "object_id": registry.get("object_id"),
            "at_report": registry.get("at_report"),
            "limitations": registry.get("limitations"),
            "fresh_registry_verification_performed": False,
        },
        "software_snapshot": {
            key: software.get(key)
            for key in ("executed_at", "git_revision", "tests_passed", "subtests_passed", "scope")
        },
        "unresolved": [
            "3,824 unique objects remain summary-attributed; raw identities were not rebuilt.",
            "30/200 and 55/193 are separate stages; seven unmatched evaluations remain unresolved.",
            "This audit verifies neither both TNS designations nor physical classification.",
            "Synthetic trial provenance, human review and submission approval remain separate.",
        ],
        "scientific_execution_authorized": False,
        "submission_authorized": False,
        "submission_readiness": "BLOCKED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = reconcile(args.root, BINDING["read_json"](args.manifest))
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        print(
            json.dumps(
                {
                    "historical_arithmetic": "FAIL",
                    "submission_readiness": "BLOCKED",
                    "error": str(exc),
                }
            )
        )
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    return 2 if args.require_ready else 0


if __name__ == "__main__":
    sys.exit(main())
