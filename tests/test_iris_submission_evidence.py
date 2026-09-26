"""Negative-path coverage for the read-only IRIS document binding checker."""

from __future__ import annotations

import contextlib
import copy
import io
import json
import runpy
import tempfile
import unittest
from pathlib import Path

CHECKER = (
    Path(__file__).resolve().parents[1]
    / "submission"
    / "iris-2026-27"
    / "verify_evidence.py"
)
API = runpy.run_path(str(CHECKER))


class SubmissionEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ledger = self.root / "CLAIM_LEDGER.md"
        self.ledger.write_text(
            "| Claim | Evidence class | Canonical source | Current status | Wording |\n"
            "|---|---|---|---|---|\n"
            "| Frozen count | Software | record | SNAPSHOT ONLY | Historical only |\n"
            "| Real-sky accuracy | Science | none | UNSUPPORTED | Prohibited |\n",
            encoding="utf-8",
        )
        self.manifest = {
            "schema": API["SCHEMA"],
            "source_snapshot_revision": "a" * 40,
            "scope": "retained_documentation_only",
            "scientific_execution_authorized": False,
            "submission_authorized": False,
            "unresolved_gates": ["Independent review"],
            "artifacts": [
                {
                    "id": "ledger",
                    "path": "CLAIM_LEDGER.md",
                    "git_blob_sha": API["git_blob_sha"](self.ledger.read_bytes()),
                }
            ],
            "claims": [
                {
                    "id": "C01",
                    "claim": "Frozen count",
                    "ledger_status": "SNAPSHOT ONLY",
                    "document_refs": ["ledger"],
                    "independently_approved": False,
                    "remaining_evidence_boundary": "Historical snapshot only",
                },
                {
                    "id": "C02",
                    "claim": "Real-sky accuracy",
                    "ledger_status": "UNSUPPORTED",
                    "document_refs": ["ledger"],
                    "independently_approved": False,
                    "remaining_evidence_boundary": "Prohibited without prospective evidence",
                },
            ],
        }

    def result(self) -> dict:
        return API["audit"](self.root, self.manifest)

    def assert_rejected(self) -> None:
        report = self.result()
        self.assertEqual(report["source_integrity"], "FAIL")
        self.assertFalse(report["submission_authorized"])
        self.assertEqual(report["submission_readiness"], "BLOCKED")

    def test_valid_sources_do_not_authorize_submission(self) -> None:
        report = self.result()
        self.assertEqual(report["source_integrity"], "PASS")
        self.assertEqual(report["verified_document_count"], 1)
        self.assertEqual(report["claim_count"], 2)
        self.assertEqual(report["submission_readiness"], "BLOCKED")
        self.assertFalse(report["scientific_execution_authorized"])
        self.assertFalse(report["submission_authorized"])

    def test_git_blob_hash_includes_header(self) -> None:
        self.assertEqual(
            API["git_blob_sha"](b""), "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
        )

    def test_tampered_source_fails(self) -> None:
        self.ledger.write_bytes(self.ledger.read_bytes() + b"changed\n")
        self.assert_rejected()

    def test_missing_source_fails(self) -> None:
        self.ledger.unlink()
        self.assert_rejected()

    def test_deleted_claim_fails(self) -> None:
        self.manifest["claims"].pop()
        self.assert_rejected()

    def test_reordered_claims_fail(self) -> None:
        self.manifest["claims"].reverse()
        self.assert_rejected()

    def test_promoted_status_fails(self) -> None:
        self.manifest["claims"][1]["ledger_status"] = "SUPPORTED"
        self.assert_rejected()

    def test_duplicate_claim_id_fails(self) -> None:
        self.manifest["claims"][1]["id"] = "C01"
        self.assert_rejected()

    def test_missing_evidence_boundary_fails(self) -> None:
        self.manifest["claims"][0]["remaining_evidence_boundary"] = " "
        self.assert_rejected()

    def test_independent_approval_flag_fails(self) -> None:
        self.manifest["claims"][0]["independently_approved"] = True
        self.assert_rejected()

    def test_unverified_reference_fails(self) -> None:
        self.manifest["claims"][0]["document_refs"] = ["missing"]
        self.assert_rejected()

    def test_duplicate_artifact_id_fails(self) -> None:
        self.manifest["artifacts"].append(copy.deepcopy(self.manifest["artifacts"][0]))
        self.assert_rejected()

    def test_duplicate_path_fails(self) -> None:
        extra = copy.deepcopy(self.manifest["artifacts"][0])
        extra["id"] = "other"
        self.manifest["artifacts"].append(extra)
        self.assert_rejected()

    def test_missing_ledger_artifact_fails(self) -> None:
        self.manifest["artifacts"][0]["id"] = "other"
        self.assert_rejected()

    def test_invalid_blob_sha_fails(self) -> None:
        self.manifest["artifacts"][0]["git_blob_sha"] = "main"
        self.assert_rejected()

    def test_short_source_revision_fails(self) -> None:
        self.manifest["source_snapshot_revision"] = "abc123"
        self.assert_rejected()

    def test_changed_scope_fails(self) -> None:
        self.manifest["scope"] = "run_experiments"
        self.assert_rejected()

    def test_execution_flag_true_fails(self) -> None:
        self.manifest["scientific_execution_authorized"] = True
        self.assert_rejected()

    def test_submission_flag_true_fails(self) -> None:
        self.manifest["submission_authorized"] = True
        self.assert_rejected()

    def test_numeric_false_is_not_boolean_false(self) -> None:
        self.manifest["submission_authorized"] = 0
        self.assert_rejected()

    def test_missing_authorization_flag_fails(self) -> None:
        del self.manifest["submission_authorized"]
        self.assert_rejected()

    def test_empty_blockers_fail(self) -> None:
        self.manifest["unresolved_gates"] = []
        self.assert_rejected()

    def test_unsafe_paths_fail(self) -> None:
        for path in ("../escape", "/tmp/escape", "a/../b", "a//b", "./a", "C:/x"):
            with self.subTest(path=path):
                self.manifest["artifacts"][0]["path"] = path
                self.assert_rejected()

    def test_symlink_file_fails(self) -> None:
        link = self.root / "link.md"
        link.symlink_to(self.ledger)
        self.manifest["artifacts"][0]["path"] = "link.md"
        self.assert_rejected()

    def test_symlink_parent_fails(self) -> None:
        (self.root / "linked").symlink_to(self.root, target_is_directory=True)
        self.manifest["artifacts"][0]["path"] = "linked/CLAIM_LEDGER.md"
        self.assert_rejected()

    def test_directory_source_fails(self) -> None:
        (self.root / "directory").mkdir()
        self.manifest["artifacts"][0]["path"] = "directory"
        self.assert_rejected()

    def test_duplicate_json_key_fails(self) -> None:
        path = self.root / "manifest.json"
        path.write_text('{"submission_authorized": false, "submission_authorized": true}')
        with self.assertRaises(ValueError):
            API["read_json"](path)

    def test_non_finite_json_fails(self) -> None:
        path = self.root / "manifest.json"
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                path.write_text('{"value": ' + value + "}")
                with self.assertRaises(ValueError):
                    API["read_json"](path)

    def test_nested_duplicate_json_key_fails(self) -> None:
        path = self.root / "manifest.json"
        path.write_text('{"nested": {"approval": false, "approval": true}}')
        with self.assertRaises(ValueError):
            API["read_json"](path)

    def test_non_object_json_fails(self) -> None:
        path = self.root / "manifest.json"
        path.write_text("[]")
        with self.assertRaises(ValueError):
            API["read_json"](path)

    def test_invalid_artifact_type_fails(self) -> None:
        self.manifest["artifacts"] = [None]
        self.assert_rejected()

    def test_invalid_claim_type_fails(self) -> None:
        self.manifest["claims"] = [None]
        self.assert_rejected()

    def test_malformed_table_fails(self) -> None:
        self.ledger.write_text("| broken | table |\n", encoding="utf-8")
        self.manifest["artifacts"][0]["git_blob_sha"] = API["git_blob_sha"](
            self.ledger.read_bytes()
        )
        self.assert_rejected()

    def test_read_only_and_deterministic(self) -> None:
        before = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        self.assertEqual(self.result(), self.result())
        after = {p.name: p.read_bytes() for p in self.root.iterdir() if p.is_file()}
        self.assertEqual(before, after)

    def test_cli_exit_codes_keep_ready_blocked(self) -> None:
        path = self.root / "manifest.json"
        path.write_text(json.dumps(self.manifest), encoding="utf-8")
        args = ["--root", str(self.root), "--manifest", str(path)]
        for suffix, expected in (([], 0), (["--require-ready"], 2)):
            with self.subTest(expected=expected), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(API["main"](args + suffix), expected)

    def test_cli_missing_manifest_fails(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()):
            code = API["main"](
                ["--root", str(self.root), "--manifest", str(self.root / "absent.json")]
            )
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
