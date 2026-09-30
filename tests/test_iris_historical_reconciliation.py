"""Check actual archived arithmetic and reject changed or incomplete evidence."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import runpy
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "submission" / "iris-2026-27"
API = runpy.run_path(str(PACKAGE / "reconcile_historical_evidence.py"))


class HistoricalReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = (ROOT / "PIPELINE_OPERATIONS_RECORD.md").read_text(encoding="utf-8")
        self.metrics = json.loads((ROOT / API["PATHS"]["derived_metrics"]).read_text())
        self.manifest = json.loads((PACKAGE / "DOCUMENT_EVIDENCE_MANIFEST.json").read_text())

    def test_actual_snapshot_reconciles_fifteen_fields(self) -> None:
        report = API["reconcile"](ROOT, self.manifest)
        self.assertEqual(report["historical_arithmetic"], "PASS")
        self.assertEqual(report["matched_deterministic_fields"], 15)
        self.assertEqual(report["document_binding"]["verified_document_count"], 6)
        self.assertEqual(report["recomputed"]["unique_pull_detection_rows"], 424223)
        self.assertEqual(report["recomputed"]["unique_pull_clean_rows"], 223938)
        self.assertEqual(len(report["provenance"]["pre_run_ids"]), 10)
        self.assertEqual(len(report["provenance"]["post_run_ids"]), 6)
        self.assertEqual(len(report["provenance"]["incomplete_stage_run_ids"]), 7)
        self.assertFalse(report["scientific_execution_authorized"])
        self.assertFalse(report["submission_authorized"])
        self.assertEqual(report["submission_readiness"], "BLOCKED")

    def test_all_table_totals_remain_distinct_from_duplicate_excluded(self) -> None:
        _, provenance = API["arithmetic"](API["parse_runs"](self.record))
        self.assertEqual(provenance["all_table_detection_rows"], 438610)
        self.assertEqual(provenance["all_table_clean_rows"], 231688)
        self.assertEqual(provenance["excluded_duplicate"], API["DUPLICATE"])

    def test_registry_is_retained_capture_not_fresh_verification(self) -> None:
        capture = API["reconcile"](ROOT, self.manifest)["registry_capture"]
        self.assertEqual(capture["retrieved_on"], "2026-09-13")
        self.assertEqual(capture["at_report"]["report_id"], 312644)
        self.assertEqual(capture["at_report"]["reporter"], "Aadi Ajeesh Nair")
        self.assertFalse(capture["fresh_registry_verification_performed"])

    def test_software_snapshot_is_dated(self) -> None:
        software = API["reconcile"](ROOT, self.manifest)["software_snapshot"]
        self.assertEqual(software["git_revision"], "4e084a795be316ca991b213e2f8309b6143e7f9f")
        self.assertEqual(software["tests_passed"], 499)
        self.assertEqual(software["subtests_passed"], 103)

    def test_deterministic_and_no_new_files(self) -> None:
        before = sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("*"))
        first = API["reconcile"](ROOT, self.manifest)
        self.assertEqual(first, API["reconcile"](ROOT, self.manifest))
        after = sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("*"))
        self.assertEqual(before, after)

    def test_missing_header_fails(self) -> None:
        with self.assertRaises(ValueError):
            API["parse_runs"](self.record.replace(API["HEADER"], "changed header"))

    def test_duplicate_header_fails(self) -> None:
        with self.assertRaises(ValueError):
            API["parse_runs"](self.record + "\n" + API["HEADER"])

    def test_missing_run_fails(self) -> None:
        record = "\n".join(
            line
            for line in self.record.splitlines()
            if not line.startswith("| run_20260605T095611Z")
        )
        with self.assertRaises(ValueError):
            API["parse_runs"](record)

    def test_repeated_run_id_fails(self) -> None:
        record = self.record.replace("| run_20260605T100242Z", "| run_20260605T095611Z")
        with self.assertRaises(ValueError):
            API["parse_runs"](record)

    def test_missing_duplicate_marker_fails(self) -> None:
        with self.assertRaises(ValueError):
            API["parse_runs"](self.record.replace(API["DUPLICATE"] + " †", API["DUPLICATE"]))

    def test_extra_duplicate_marker_fails(self) -> None:
        record = self.record.replace("| run_20260605T095611Z |", "| run_20260605T095611Z † |")
        with self.assertRaises(ValueError):
            API["parse_runs"](record)

    def test_changed_duplicate_counts_fail(self) -> None:
        record = self.record.replace(
            "| run_20260614T014019Z † | 150 | 14,387 |",
            "| run_20260614T014019Z † | 150 | 14,388 |",
        )
        with self.assertRaises(ValueError):
            API["parse_runs"](record)

    def test_invalid_counts_fail(self) -> None:
        for cell in ("-1", "NaN", "Infinity", "1.5", "12,34", "—", "01"):
            with self.subTest(cell=cell), self.assertRaises(ValueError):
                API["number"](cell)

    def test_optional_missing_is_not_zero(self) -> None:
        self.assertIsNone(API["number"]("—", optional=True))
        self.assertEqual(API["number"]("0", optional=True), 0)

    def test_missing_metric_fails(self) -> None:
        values, _ = API["arithmetic"](API["parse_runs"](self.record))
        del self.metrics["pre_objects"]
        with self.assertRaises(ValueError):
            API["compare_metrics"](values, self.metrics)

    def test_changed_metric_fails(self) -> None:
        values, _ = API["arithmetic"](API["parse_runs"](self.record))
        self.metrics["pre_shortlist_fraction"] += 0.001
        with self.assertRaises(ValueError):
            API["compare_metrics"](values, self.metrics)

    def test_boolean_is_not_numeric_evidence(self) -> None:
        with self.assertRaises(ValueError):
            API["compare_metrics"]({"count": 1}, {"count": True})

    def test_source_tampering_fails_before_arithmetic(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["artifacts"][0]["git_blob_sha"] = "0" * 40
        with self.assertRaises(ValueError):
            API["reconcile"](ROOT, manifest)

    def test_missing_derived_artifact_fails(self) -> None:
        manifest = copy.deepcopy(self.manifest)
        manifest["artifacts"] = [
            artifact for artifact in manifest["artifacts"] if artifact["id"] != "derived_metrics"
        ]
        with self.assertRaises(ValueError):
            API["reconcile"](ROOT, manifest)

    def test_approval_flag_fails(self) -> None:
        self.manifest["submission_authorized"] = True
        with self.assertRaises(ValueError):
            API["reconcile"](ROOT, self.manifest)

    def test_duplicate_json_key_fails(self) -> None:
        with self.assertRaises(ValueError):
            API["json_object"](b'{"count": 1, "count": 2}')

    def test_nonfinite_json_fails(self) -> None:
        with self.assertRaises(ValueError):
            API["json_object"](b'{"count": NaN}')

    def test_json_array_fails(self) -> None:
        with self.assertRaises(ValueError):
            API["json_object"](b"[]")

    def test_cli_ready_stays_blocked(self) -> None:
        args = ["--root", str(ROOT), "--manifest", str(PACKAGE / "DOCUMENT_EVIDENCE_MANIFEST.json")]
        for suffix, expected in (([], 0), (["--require-ready"], 2)):
            with self.subTest(expected=expected), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(API["main"](args + suffix), expected)

    def test_cli_missing_manifest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                API["main"](["--root", str(ROOT), "--manifest", str(Path(temp) / "absent")]), 1
            )


if __name__ == "__main__":
    unittest.main()
