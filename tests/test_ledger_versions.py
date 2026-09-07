from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from iris.ledger import SCHEMA_VERSION, OutcomeLedger


class VersionBoundReviewTests(unittest.TestCase):
    @staticmethod
    def _approve(ledger: OutcomeLedger, candidate_id: str, candidate_version: str) -> None:
        ledger.add_review(
            candidate_id,
            candidate_version=candidate_version,
            reviewer="screen-a",
            role="screener",
            verdict="approve",
            reason="screened this evidence version",
        )
        ledger.add_review(
            candidate_id,
            candidate_version=candidate_version,
            reviewer="review-b",
            role="reviewer",
            verdict="approve",
            reason="independently reviewed this evidence version",
        )

    def test_candidate_change_invalidates_prior_approvals(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            version_a = "a" * 64
            version_b = "b" * 64
            ledger.upsert_candidate(
                "ZTF-versioned",
                campaign="ispy",
                state="needs_review",
                payload={"evidence": "first"},
                version_digest=version_a,
            )
            self._approve(ledger, "ZTF-versioned", version_a)
            self.assertTrue(
                ledger.independent_approval("ZTF-versioned", candidate_version=version_a)[0]
            )

            ledger.upsert_candidate(
                "ZTF-versioned",
                campaign="ispy",
                state="needs_review",
                payload={"evidence": "changed"},
                version_digest=version_b,
            )

            approved, reason = ledger.independent_approval("ZTF-versioned")
            self.assertFalse(approved)
            self.assertIn("missing screener", reason)
            approved, reason = ledger.independent_approval(
                "ZTF-versioned", candidate_version=version_a
            )
            self.assertFalse(approved)
            self.assertIn("not the current", reason)
            with self.assertRaisesRegex(ValueError, "changed after"):
                ledger.add_review(
                    "ZTF-versioned",
                    reviewer="late-reviewer",
                    role="reviewer",
                    verdict="approve",
                    reason="stale browser form",
                    candidate_version=version_a,
                )

            self._approve(ledger, "ZTF-versioned", version_b)
            self.assertTrue(
                ledger.independent_approval("ZTF-versioned", candidate_version=version_b)[0]
            )
            self.assertEqual(
                [review.candidate_version for review in ledger.reviews_for("ZTF-versioned")],
                [version_a, version_a, version_b, version_b],
            )

    def test_candidate_history_reconstructs_every_referenced_version(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            version_a = "1" * 64
            version_b = "2" * 64
            ledger.upsert_candidate(
                "ZTF-history",
                campaign="ispy",
                state="needs_review",
                payload={"evidence": "first", "nested": {"score": 0.25}},
                version_digest=version_a,
            )
            ledger.add_review(
                "ZTF-history",
                candidate_version=version_a,
                reviewer="screen-a",
                role="screener",
                verdict="approve",
                reason="reviewed the first snapshot",
            )
            ledger.add_adjudication(
                "ZTF-history",
                candidate_version=version_a,
                adjudicator="scientist-a",
                verdict="clear_context",
                reason="context checked against the first snapshot",
            )
            ledger.record_outcome(
                "ZTF-history",
                candidate_version=version_a,
                outcome="followup_requested",
                evidence={"request_id": "followup-1"},
            )

            ledger.upsert_candidate(
                "ZTF-history",
                campaign="ispy",
                state="needs_review",
                payload={"evidence": "second", "nested": {"score": 0.75}},
                version_digest=version_b,
            )

            current = ledger.candidate("ZTF-history")
            first = ledger.candidate_version("ZTF-history", version_a)
            second = ledger.candidate_version("ZTF-history", version_b)
            self.assertIsNotNone(current)
            self.assertEqual(current["version_digest"], version_b)
            self.assertEqual(first["payload"], {"evidence": "first", "nested": {"score": 0.25}})
            self.assertEqual(second["payload"], {"evidence": "second", "nested": {"score": 0.75}})
            self.assertEqual(
                [item["version_digest"] for item in ledger.candidate_versions_for("ZTF-history")],
                [version_a, version_b],
            )
            referenced_versions = {
                ledger.reviews_for("ZTF-history")[0].candidate_version,
                ledger.adjudications_for("ZTF-history")[0].candidate_version,
                ledger.outcomes_for("ZTF-history")[0].candidate_version,
            }
            self.assertEqual(referenced_versions, {version_a})
            self.assertTrue(
                all(
                    ledger.candidate_version("ZTF-history", version) is not None
                    for version in referenced_versions
                )
            )

    def test_first_snapshot_for_a_version_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            version = "3" * 64
            ledger.upsert_candidate(
                "ZTF-workflow-refresh",
                campaign="ispy",
                state="needs_review",
                payload={"evidence": "fixed", "reportable": False},
                version_digest=version,
            )
            ledger.upsert_candidate(
                "ZTF-workflow-refresh",
                campaign="ispy",
                state="approved",
                payload={"evidence": "fixed", "reportable": True},
                version_digest=version,
            )

            current = ledger.candidate("ZTF-workflow-refresh")
            archived = ledger.candidate_version("ZTF-workflow-refresh", version)
            self.assertEqual(current["state"], "approved")
            self.assertEqual(current["payload"]["reportable"], True)
            self.assertEqual(archived["state"], "needs_review")
            self.assertEqual(archived["payload"]["reportable"], False)

    def test_database_guards_version_history_and_child_references(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ledger.sqlite"
            ledger = OutcomeLedger(path)
            version = "4" * 64
            ledger.upsert_candidate(
                "ZTF-guarded",
                campaign="ispy",
                state="needs_review",
                payload={"evidence": "immutable"},
                version_digest=version,
            )
            ledger.add_review(
                "ZTF-guarded",
                candidate_version=version,
                reviewer="reviewer-a",
                role="reviewer",
                verdict="approve",
                reason="valid version-bound review",
            )
            ledger.add_adjudication(
                "ZTF-guarded",
                candidate_version=version,
                adjudicator="scientist-a",
                verdict="clear_context",
                reason="valid version-bound adjudication",
            )
            ledger.record_outcome(
                "ZTF-guarded",
                candidate_version=version,
                outcome="followup_requested",
                evidence={"request_id": "request-1"},
            )

            with closing(sqlite3.connect(path)) as db, db:
                with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                    db.execute(
                        "UPDATE candidate_versions SET state='changed' WHERE candidate_id=?",
                        ("ZTF-guarded",),
                    )
                with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                    db.execute(
                        "DELETE FROM candidate_versions WHERE candidate_id=?",
                        ("ZTF-guarded",),
                    )
                with self.assertRaisesRegex(sqlite3.IntegrityError, "unknown candidate version"):
                    db.execute(
                        """
                        INSERT INTO reviews(
                            candidate_id, candidate_version, reviewer, role,
                            verdict, reason, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "ZTF-guarded",
                            "9" * 64,
                            "reviewer-a",
                            "reviewer",
                            "approve",
                            "invalid direct reference",
                            "2026-01-01T00:00:00+00:00",
                        ),
                    )
                for table in ("reviews", "adjudications", "outcomes"):
                    with (
                        self.subTest(table=table, operation="update"),
                        self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"),
                    ):
                        db.execute(
                            f"UPDATE {table} SET candidate_version=? WHERE candidate_id=?",
                            ("8" * 64, "ZTF-guarded"),
                        )
                    with (
                        self.subTest(table=table, operation="delete"),
                        self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"),
                    ):
                        db.execute(
                            f"DELETE FROM {table} WHERE candidate_id=?",
                            ("ZTF-guarded",),
                        )

            self.assertEqual(
                ledger.candidate_version("ZTF-guarded", version)["payload"],
                {"evidence": "immutable"},
            )

    def test_raw_decision_inserts_must_satisfy_ledger_invariants(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ledger.sqlite"
            ledger = OutcomeLedger(path)
            version = "5" * 64
            ledger.upsert_candidate(
                "ZTF-raw-invariants",
                campaign="ispy",
                state="needs_review",
                payload={},
                version_digest=version,
            )
            review_sql = """
                INSERT INTO reviews(
                    candidate_id, candidate_version, reviewer, role,
                    verdict, reason, created_at
                ) VALUES (
                    :candidate_id, :candidate_version, :reviewer, :role,
                    :verdict, :reason, :created_at
                )
            """
            review = {
                "candidate_id": "ZTF-raw-invariants",
                "candidate_version": version,
                "reviewer": "reviewer-a",
                "role": "reviewer",
                "verdict": "approve",
                "reason": "valid reason",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
            adjudication_sql = """
                INSERT INTO adjudications(
                    candidate_id, candidate_version, adjudicator,
                    verdict, reason, created_at
                ) VALUES (
                    :candidate_id, :candidate_version, :adjudicator,
                    :verdict, :reason, :created_at
                )
            """
            adjudication = {
                "candidate_id": "ZTF-raw-invariants",
                "candidate_version": version,
                "adjudicator": "scientist-a",
                "verdict": "clear_context",
                "reason": "valid reason",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
            outcome_sql = """
                INSERT INTO outcomes(
                    candidate_id, candidate_version, outcome, designation,
                    evidence_json, taxonomy_version, evidence_digest, recorded_at
                ) VALUES (
                    :candidate_id, :candidate_version, :outcome, :designation,
                    :evidence_json, :taxonomy_version, :evidence_digest, :recorded_at
                )
            """
            outcome = {
                "candidate_id": "ZTF-raw-invariants",
                "candidate_version": version,
                "outcome": "followup_requested",
                "designation": "",
                "evidence_json": "{}",
                "taxonomy_version": "iris.outcome.v1",
                "evidence_digest": "6" * 64,
                "recorded_at": "2026-01-01T00:00:00+00:00",
            }

            invalid_cases = (
                (review_sql, review, "role", "administrator"),
                (review_sql, review, "verdict", "maybe"),
                (review_sql, review, "reviewer", " \t\n"),
                (review_sql, review, "reason", "   "),
                (adjudication_sql, adjudication, "verdict", "maybe"),
                (adjudication_sql, adjudication, "adjudicator", " \r\n"),
                (adjudication_sql, adjudication, "reason", "   "),
                (outcome_sql, outcome, "outcome", "   "),
                (outcome_sql, outcome, "taxonomy_version", "\t"),
                (outcome_sql, outcome, "evidence_json", "\n"),
                (outcome_sql, outcome, "evidence_digest", "   "),
                (outcome_sql, outcome, "recorded_at", "\r"),
            )
            with closing(sqlite3.connect(path)) as db, db:
                for sql, valid, field, invalid_value in invalid_cases:
                    with self.subTest(field=field, invalid_value=invalid_value):
                        invalid = {**valid, field: invalid_value}
                        with self.assertRaises(sqlite3.IntegrityError):
                            db.execute(sql, invalid)

                counts = {
                    table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("reviews", "adjudications", "outcomes")
                }
            self.assertEqual(counts, {"reviews": 0, "adjudications": 0, "outcomes": 0})

    def test_review_api_refuses_to_infer_the_candidate_version(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            ledger.upsert_candidate(
                "ZTF-explicit",
                campaign="ispy",
                state="needs_review",
                payload={},
                version_digest="a" * 64,
            )
            with self.assertRaisesRegex(TypeError, "candidate_version"):
                ledger.add_review(  # type: ignore[call-arg]
                    "ZTF-explicit",
                    reviewer="reviewer",
                    role="reviewer",
                    verdict="approve",
                    reason="must name the evidence version",
                )

    def test_v1_migration_never_counts_legacy_unbound_reviews(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ledger.sqlite"
            with closing(sqlite3.connect(path)) as db, db:
                db.executescript(
                    """
                    CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    CREATE TABLE candidates (
                        candidate_id TEXT PRIMARY KEY,
                        first_seen TEXT NOT NULL,
                        last_seen TEXT NOT NULL,
                        campaign TEXT NOT NULL,
                        state TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE TABLE reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
                        reviewer TEXT NOT NULL,
                        role TEXT NOT NULL,
                        verdict TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    INSERT INTO metadata VALUES ('schema_version', '1');
                    INSERT INTO candidates VALUES (
                        'legacy', '2026-01-01T00:00:00+00:00',
                        '2026-01-01T00:00:00+00:00', 'ispy', 'needs_review', '{}'
                    );
                    INSERT INTO reviews(
                        candidate_id, reviewer, role, verdict, reason, created_at
                    ) VALUES
                        ('legacy', 'screen-a', 'screener', 'approve', 'old',
                         '2026-01-01T00:00:00+00:00'),
                        ('legacy', 'review-b', 'reviewer', 'approve', 'old',
                         '2026-01-01T00:00:00+00:00');
                    """
                )

            ledger = OutcomeLedger(path)
            candidate = ledger.candidate("legacy")
            self.assertIsNotNone(candidate)
            self.assertTrue(candidate["version_digest"])
            archived = ledger.candidate_version("legacy", str(candidate["version_digest"]))
            self.assertIsNotNone(archived)
            self.assertEqual(archived["payload"], {})
            self.assertEqual(
                [review.candidate_version for review in ledger.reviews_for("legacy")],
                ["", ""],
            )
            approved, reason = ledger.independent_approval("legacy")
            self.assertFalse(approved)
            self.assertIn("missing screener", reason)

            self._approve(ledger, "legacy", str(candidate["version_digest"]))
            self.assertTrue(ledger.independent_approval("legacy")[0])
            with closing(sqlite3.connect(path)) as db, db:
                stored_version = db.execute(
                    "SELECT value FROM metadata WHERE key='schema_version'"
                ).fetchone()[0]
            self.assertEqual(stored_version, str(SCHEMA_VERSION))

    def test_principal_case_variants_are_not_independent_people(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            version = "c" * 64
            ledger.upsert_candidate(
                "ZTF-identities",
                campaign="ispy",
                state="needs_review",
                payload={},
                version_digest=version,
            )
            ledger.add_review(
                "ZTF-identities",
                reviewer=" Alice ",
                role="screener",
                verdict="approve",
                reason="screened",
                candidate_version=version,
            )
            ledger.add_review(
                "ZTF-identities",
                reviewer="ALICE",
                role="reviewer",
                verdict="approve",
                reason="same principal spelling",
                candidate_version=version,
            )

            approved, reason = ledger.independent_approval(
                "ZTF-identities", candidate_version=version
            )

            self.assertFalse(approved)
            self.assertIn("different people", reason)

    def test_required_reviewer_count_excludes_every_active_screener(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            version = "f" * 64
            ledger.upsert_candidate(
                "ZTF-separation",
                campaign="ispy",
                state="needs_review",
                payload={},
                version_digest=version,
            )
            for reviewer, role in (
                ("alice", "screener"),
                ("alice", "reviewer"),
                ("bob", "reviewer"),
            ):
                ledger.add_review(
                    "ZTF-separation",
                    candidate_version=version,
                    reviewer=reviewer,
                    role=role,
                    verdict="approve",
                    reason="reviewed",
                )

            approved, reason = ledger.independent_approval(
                "ZTF-separation",
                required_reviewers=2,
                candidate_version=version,
            )

            self.assertFalse(approved)
            self.assertIn("have 1", reason)

    def test_outcome_reader_rejects_a_forged_evidence_digest(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ledger.sqlite"
            ledger = OutcomeLedger(path)
            version = "9" * 64
            ledger.upsert_candidate(
                "ZTF-outcome-integrity",
                campaign="ispy",
                state="needs_review",
                payload={},
                version_digest=version,
            )
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("PRAGMA foreign_keys = ON")
                db.execute(
                    """
                    INSERT INTO outcomes(
                        candidate_id, outcome, designation, evidence_json,
                        candidate_version, taxonomy_version, evidence_digest, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "ZTF-outcome-integrity",
                        "confirmed",
                        "",
                        '{"spectrum": "sha256:abc"}',
                        version,
                        "iris.outcome.v1",
                        "0" * 64,
                        "2026-09-06T00:00:00+00:00",
                    ),
                )

            with self.assertRaisesRegex(ValueError, "evidence integrity"):
                ledger.outcomes_for("ZTF-outcome-integrity")

    def test_adjudications_and_outcomes_bind_to_exact_candidate_version(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            version_a = "d" * 64
            version_b = "e" * 64
            ledger.upsert_candidate(
                "ZTF-science",
                campaign="ispy",
                state="needs_review",
                payload={},
                version_digest=version_a,
            )
            ledger.add_adjudication(
                "ZTF-science",
                adjudicator="Scientist A",
                verdict="clear_context",
                reason="offset host is physically plausible and not a source veto",
                candidate_version=version_a,
            )
            self.assertTrue(
                ledger.manual_adjudication("ZTF-science", candidate_version=version_a)[0]
            )
            outcome = ledger.record_outcome(
                "ZTF-science",
                outcome="confirmed_transient",
                designation="AT 2026abc",
                evidence={"spectrum_sha256": "f" * 64},
                candidate_version=version_a,
                taxonomy_version="iris.outcome.v1",
            )
            self.assertEqual(outcome.candidate_version, version_a)
            self.assertEqual(len(outcome.evidence_digest), 64)

            ledger.upsert_candidate(
                "ZTF-science",
                campaign="ispy",
                state="needs_review",
                payload={"changed": True},
                version_digest=version_b,
            )
            self.assertFalse(
                ledger.manual_adjudication("ZTF-science", candidate_version=version_b)[0]
            )
            with self.assertRaisesRegex(ValueError, "changed after"):
                ledger.record_outcome(
                    "ZTF-science",
                    outcome="confirmed_transient",
                    evidence={},
                    candidate_version=version_a,
                )

    def test_cross_campaign_collision_fails_and_rolls_back_a_batch(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            ledger.upsert_candidate(
                "shared-name",
                campaign="ispy",
                state="needs_review",
                payload={"original": True},
                version_digest="a" * 64,
            )

            with self.assertRaisesRegex(ValueError, "another campaign"):
                ledger.upsert_candidates(
                    [
                        {
                            "candidate_id": "new-in-same-transaction",
                            "campaign": "nuclear",
                            "state": "needs_review",
                            "payload": {},
                            "version_digest": "b" * 64,
                        },
                        {
                            "candidate_id": "shared-name",
                            "campaign": "nuclear",
                            "state": "needs_review",
                            "payload": {"overwritten": True},
                            "version_digest": "c" * 64,
                        },
                    ]
                )

            self.assertIsNone(ledger.candidate("new-in-same-transaction"))
            self.assertEqual(ledger.candidate_versions_for("new-in-same-transaction"), [])
            original = ledger.candidate("shared-name")
            self.assertIsNotNone(original)
            self.assertEqual(original["campaign"], "ispy")
            self.assertEqual(original["payload"], {"original": True})
            self.assertEqual(
                [
                    snapshot["version_digest"]
                    for snapshot in ledger.candidate_versions_for("shared-name")
                ],
                ["a" * 64],
            )


if __name__ == "__main__":
    unittest.main()
