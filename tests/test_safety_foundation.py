from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from iris.clients.base import ResilientExecutor
from iris.integrity import (
    candidate_observations_digest,
    candidate_record_digest,
    candidate_run_binding_digest,
    candidate_version_basis,
)
from iris.ledger import OutcomeLedger
from iris.manifest import RUN_MANIFEST_SCHEMA
from iris.provenance import CheckProvenance, CheckStatus, digest_file, digest_value
from iris.reporting.preflight import reporting_preflight
from iris.similarity import EmbeddingIndex
from iris.validation import EvidenceBindingContext, preflight_digest
from iris.validation.gates import GateDecision, evaluate_reportability


class SafetyGateTests(unittest.TestCase):
    @staticmethod
    def binding_context() -> EvidenceBindingContext:
        return EvidenceBindingContext(
            candidate_id="ZTF-test",
            ra_deg=12.3,
            dec_deg=-4.5,
            max_ttl_hours=24.0,
            required_radii_arcsec={
                "tns": 5.0,
                "skybot": 10.0,
                "simbad": 3.0,
                "vsx": 3.0,
            },
            skybot_reference_mjds=(61000.0,),
        )

    def publish_candidate(
        self,
        ledger: OutcomeLedger,
        checks: list[CheckProvenance],
        *,
        quality_passed: bool = True,
        manual_review_required: bool = False,
        mandatory_services: tuple[str, ...] = ("tns", "skybot", "simbad", "vsx"),
        required_reviewers: int = 1,
        context: EvidenceBindingContext | None = None,
    ) -> str:
        context = context or self.binding_context()
        review_policy = {
            "required_reviewers": required_reviewers,
            "require_human_approval": True,
            "allow_self_approval": False,
        }
        scientific_config = {
            "hunt": {"min_detections": 1},
            "validation": {"required_checks": list(mandatory_services)},
            "ranking": {},
            "review": {"nightly_budget": 10, **review_policy},
        }
        observations = [{"source_id": "ZTF-test", "mjd": 61000.0, "magnitude": 19.0}]
        observation_digest = candidate_observations_digest(observations)
        verification_context = {
            "simbad": ["NGC 123 (galaxy)"] if manual_review_required else [],
            "skybot_epochs": ["61000.00000000"],
        }
        stored_preflight = preflight_digest(
            context=context,
            checks=checks,
            quality_passed=quality_passed,
            manual_review_required=manual_review_required,
            mandatory_services=mandatory_services,
            required_reviewers=required_reviewers,
            verification_context=verification_context,
        )
        quality = {"passed": quality_passed, "reasons": []}
        decision = (
            "reject_quality"
            if not quality_passed
            else "needs_manual_review"
            if manual_review_required
            else "reportable"
        )
        automated_gate = {
            "decision": decision,
            "reasons": [],
            "missing_services": [],
            "matched_services": [],
        }
        basis = candidate_version_basis(
            pipeline_version="iris.local_analysis.v3",
            candidate_id="ZTF-test",
            campaign="ispy",
            observations_digest=observation_digest,
            position={"ra_deg": 12.3, "dec_deg": -4.5},
            quality=quality,
            features={},
            score={},
            external_checks=checks,
            manual_review_required=manual_review_required,
            automated_gate=automated_gate,
            evidence_binding=context.to_dict(),
            reporting_preflight_digest=stored_preflight,
            scientific_config=scientific_config,
            verification_context=verification_context,
        )
        version = digest_value(basis)
        run_id = "safety-fixture"
        fingerprint = "safety-fixture-science"
        payload = {
            "run_id": run_id,
            "scientific_fingerprint": fingerprint,
            "candidate_id": "ZTF-test",
            "pipeline_version": "iris.local_analysis.v3",
            "candidate_version": version,
            "observations_digest": observation_digest,
            "observations": observations,
            "position": {"ra_deg": 12.3, "dec_deg": -4.5},
            "quality": quality,
            "features": {},
            "score": {},
            "external_checks": [check.to_dict() for check in checks],
            "automated_gate": automated_gate,
            "manual_review_required": manual_review_required,
            "verification_context": verification_context,
            "evidence_binding": context.to_dict(),
            "preflight_digest": stored_preflight,
            "review_policy": review_policy,
            "scientific_config": scientific_config,
            "campaign": "ispy",
        }
        payload["candidate_record_digest"] = candidate_record_digest(payload)
        payload["candidate_run_binding_digest"] = candidate_run_binding_digest(payload)
        candidate_path = ledger.path.parent / "safety-fixture.candidates.json"
        candidate_path.write_text(
            json.dumps(
                {
                    "schema": "iris.candidates.v1",
                    "run_id": run_id,
                    "scientific_fingerprint": fingerprint,
                    "pipeline_version": "iris.local_analysis.v3",
                    "candidates": [payload],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        configuration = {
            "pipeline_version": "iris.local_analysis.v3",
            "scientific_fingerprint": fingerprint,
        }
        manifest_path = ledger.path.parent / "safety-fixture.manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema": RUN_MANIFEST_SCHEMA,
                    "run_id": run_id,
                    "status": "completed",
                    "configuration": configuration,
                    "configuration_digest": digest_value(configuration),
                    "code_source_digest": "a" * 64,
                    "artifacts": [
                        {
                            "path": str(candidate_path.resolve()),
                            "sha256": digest_file(candidate_path),
                            "size_bytes": candidate_path.stat().st_size,
                            "role": "candidate-evidence",
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        payload["publication"] = {
            "schema": "iris.run_publication.v1",
            "run_id": run_id,
            "manifest_path": str(manifest_path),
            "manifest_sha256": digest_file(manifest_path),
            "status": "completed",
        }
        ledger.upsert_candidate(
            "ZTF-test",
            campaign="ispy",
            state="review",
            payload=payload,
            version_digest=version,
        )
        return version

    def checks(
        self,
        status: CheckStatus = CheckStatus.CLEAR,
        *,
        candidate_id: str = "ZTF-test",
        ra: float = 12.3,
        dec: float = -4.5,
        peak_mjd: float = 61000.0,
    ):
        checked = datetime.now(UTC)
        expires = checked + timedelta(hours=24)
        radii = {"tns": 5.0, "skybot": 10.0, "simbad": 3.0, "vsx": 3.0}
        checks = []
        for name in ("tns", "skybot", "simbad", "vsx"):
            query = {
                "candidate_id": candidate_id,
                "ra": ra,
                "dec": dec,
                "radius_arcsec": radii[name],
                **({"mjd": peak_mjd} if name == "skybot" else {}),
            }
            service_version = ""
            if name == "tns":
                query.update(
                    {
                        "methods": ["internal_name", "cone"],
                        "coverage_policy": "internal_name_and_position_cone",
                        "internal_name_checked": candidate_id,
                    }
                )
                service_version = "tns-two-stage-search.v1"
            checks.append(
                CheckProvenance(
                    service=name,
                    status=status,
                    checked_at=checked.isoformat(),
                    expires_at=expires.isoformat(),
                    query=query,
                    response_digest=digest_value({"service": name, "result": []}),
                    service_version=service_version,
                )
            )
        return checks

    def test_clear_without_ttl_is_not_fresh(self):
        check = CheckProvenance(
            service="tns",
            status=CheckStatus.CLEAR,
            response_digest=digest_value([]),
        )
        self.assertFalse(check.safe_clear)
        outcome = evaluate_reportability(
            [check, *self.checks()[1:]],
            quality_passed=True,
        )
        self.assertEqual(outcome.decision, GateDecision.BLOCK_INCOMPLETE_EVIDENCE)

    def test_error_never_becomes_clear(self):
        executor = ResilientExecutor(attempts=2, base_delay_seconds=0, sleeper=lambda _: None)
        result = executor.run(
            service="skybot",
            query={"ra": 1.0},
            operation=lambda: (_ for _ in ()).throw(RuntimeError("offline")),
            has_match=bool,
        )
        self.assertEqual(result.provenance.status, CheckStatus.ERROR)
        outcome = evaluate_reportability(
            [result.provenance, *self.checks()[:1], *self.checks()[2:]],
            quality_passed=True,
        )
        self.assertEqual(outcome.decision, GateDecision.BLOCK_INCOMPLETE_EVIDENCE)

    def test_clear_without_a_response_digest_cannot_open_the_gate(self):
        checks = self.checks()
        checks[0] = CheckProvenance(
            service="tns",
            status=CheckStatus.CLEAR,
            checked_at=checks[0].checked_at,
            expires_at=checks[0].expires_at,
            query=checks[0].query,
            response_digest="",
        )

        outcome = evaluate_reportability(checks, quality_passed=True)

        self.assertEqual(outcome.decision, GateDecision.BLOCK_INCOMPLETE_EVIDENCE)
        self.assertTrue(any("response digest" in reason for reason in outcome.reasons))

    def test_equal_time_conflicting_checks_block_in_every_input_order(self):
        checks = self.checks()
        clear = checks[0]
        error = CheckProvenance(
            service="tns",
            status=CheckStatus.ERROR,
            checked_at=clear.checked_at,
            expires_at=clear.expires_at,
            query=clear.query,
            error="conflicting transport record",
        )
        tail = checks[1:]

        first = evaluate_reportability([clear, error, *tail], quality_passed=True)
        second = evaluate_reportability([error, clear, *tail], quality_passed=True)

        self.assertEqual(first, second)
        self.assertEqual(first.decision, GateDecision.BLOCK_INCOMPLETE_EVIDENCE)
        self.assertTrue(any("conflicting records" in reason for reason in first.reasons))

    def test_match_rejects(self):
        checks = self.checks()
        checks[0] = CheckProvenance(
            service="tns", status=CheckStatus.MATCH, matches=("AT 2026abc",)
        )
        outcome = evaluate_reportability(checks, quality_passed=True)
        self.assertEqual(outcome.decision, GateDecision.REJECT_KNOWN_OBJECT)

    def test_known_match_cannot_be_erased_by_a_later_clear_for_same_service(self):
        checks = self.checks()
        later_clear = checks[0]
        checks[0] = CheckProvenance(
            service="tns",
            status=CheckStatus.MATCH,
            checked_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            query=later_clear.query,
            matches=("known-object",),
        )
        checks.append(later_clear)
        outcome = evaluate_reportability(checks, quality_passed=True)
        self.assertEqual(outcome.decision, GateDecision.REJECT_KNOWN_OBJECT)

    def test_quality_gate_requires_an_actual_boolean(self):
        with self.assertRaisesRegex(TypeError, "boolean"):
            evaluate_reportability(self.checks(), quality_passed="false")  # type: ignore[arg-type]

    def test_independent_review_is_enforced(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            checks = self.checks()
            version = self.publish_candidate(ledger, checks)
            ledger.add_review(
                "ZTF-test",
                candidate_version=version,
                reviewer="A",
                role="screener",
                verdict="approve",
                reason="clean",
            )
            ledger.add_review(
                "ZTF-test",
                candidate_version=version,
                reviewer="A",
                role="reviewer",
                verdict="approve",
                reason="also clean",
            )
            preflight = reporting_preflight(
                "ZTF-test",
                checks=checks,
                quality_passed=True,
                manual_review_required=False,
                ledger=ledger,
            )
            self.assertFalse(preflight.ready)
            ledger.add_review(
                "ZTF-test",
                candidate_version=version,
                reviewer="B",
                role="reviewer",
                verdict="approve",
                reason="independent",
            )
            self.assertTrue(
                reporting_preflight(
                    "ZTF-test",
                    checks=checks,
                    quality_passed=True,
                    manual_review_required=False,
                    ledger=ledger,
                ).ready
            )

    def test_preflight_rejects_fresh_but_unbound_clear_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            reviewed_checks = self.checks()
            version = self.publish_candidate(ledger, reviewed_checks)
            ledger.add_review(
                "ZTF-test",
                candidate_version=version,
                reviewer="A",
                role="screener",
                verdict="approve",
                reason="clean",
            )
            ledger.add_review(
                "ZTF-test",
                candidate_version=version,
                reviewer="B",
                role="reviewer",
                verdict="approve",
                reason="independent",
            )
            checked = datetime.now(UTC)
            expires = checked + timedelta(hours=24)
            unbound = [
                CheckProvenance(
                    service=name,
                    status=CheckStatus.CLEAR,
                    checked_at=checked.isoformat(),
                    expires_at=expires.isoformat(),
                )
                for name in ("tns", "skybot", "simbad", "vsx")
            ]

            result = reporting_preflight(
                "ZTF-test",
                checks=unbound,
                quality_passed=True,
                manual_review_required=False,
                ledger=ledger,
            )

            self.assertFalse(result.ready)
            self.assertTrue(any("immutable reviewed" in reason for reason in result.reasons))

    def test_preflight_preserves_the_versioned_binding_tolerances(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            checks = self.checks()
            context = EvidenceBindingContext(
                candidate_id="ZTF-test",
                ra_deg=12.3,
                dec_deg=-4.5,
                max_ttl_hours=24.0,
                required_radii_arcsec={
                    "tns": 5.0,
                    "skybot": 10.0,
                    "simbad": 3.0,
                    "vsx": 3.0,
                },
                skybot_reference_mjds=(61000.0,),
                position_tolerance_arcsec=0.05,
                skybot_epoch_tolerance_days=0.0005,
            )
            version = self.publish_candidate(ledger, checks, context=context)
            for reviewer, role in (("screen-a", "screener"), ("review-b", "reviewer")):
                ledger.add_review(
                    "ZTF-test",
                    candidate_version=version,
                    reviewer=reviewer,
                    role=role,
                    verdict="approve",
                    reason="verified",
                )

            result = reporting_preflight(
                "ZTF-test",
                checks=checks,
                quality_passed=True,
                manual_review_required=False,
                ledger=ledger,
            )

            self.assertTrue(result.ready, result.reasons)

    def test_preflight_rechecks_the_published_candidate_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            checks = self.checks()
            version = self.publish_candidate(ledger, checks)
            for reviewer, role in (("screen-a", "screener"), ("review-b", "reviewer")):
                ledger.add_review(
                    "ZTF-test",
                    candidate_version=version,
                    reviewer=reviewer,
                    role=role,
                    verdict="approve",
                    reason="verified",
                )
            candidate = ledger.candidate("ZTF-test")
            manifest = json.loads(
                Path(candidate["payload"]["publication"]["manifest_path"]).read_text(
                    encoding="utf-8"
                )
            )
            artifact_path = Path(manifest["artifacts"][0]["path"])
            artifact_path.write_bytes(artifact_path.read_bytes() + b"\n")

            result = reporting_preflight(
                "ZTF-test",
                checks=checks,
                quality_passed=True,
                manual_review_required=False,
                ledger=ledger,
            )

            self.assertFalse(result.ready)
            self.assertIn("differs from its run manifest", result.reasons[0])

    def test_preflight_cannot_replace_reviewed_quality_decision(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            checks = self.checks()
            version = self.publish_candidate(ledger, checks, quality_passed=False)
            ledger.add_review(
                "ZTF-test",
                candidate_version=version,
                reviewer="A",
                role="screener",
                verdict="approve",
                reason="clean",
            )
            ledger.add_review(
                "ZTF-test",
                candidate_version=version,
                reviewer="B",
                role="reviewer",
                verdict="approve",
                reason="independent",
            )

            result = reporting_preflight(
                "ZTF-test",
                checks=checks,
                quality_passed=True,
                manual_review_required=False,
                ledger=ledger,
            )

            self.assertFalse(result.ready)
            self.assertTrue(any("immutable reviewed" in reason for reason in result.reasons))

    def test_preflight_cannot_downgrade_the_bound_reviewer_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            checks = self.checks()
            version = self.publish_candidate(ledger, checks, required_reviewers=2)
            ledger.add_review(
                "ZTF-test",
                candidate_version=version,
                reviewer="A",
                role="screener",
                verdict="approve",
                reason="clean",
            )
            ledger.add_review(
                "ZTF-test",
                candidate_version=version,
                reviewer="B",
                role="reviewer",
                verdict="approve",
                reason="independent",
            )

            downgraded = reporting_preflight(
                "ZTF-test",
                checks=checks,
                quality_passed=True,
                manual_review_required=False,
                ledger=ledger,
                required_reviewers=1,
            )
            bound_policy = reporting_preflight(
                "ZTF-test",
                checks=checks,
                quality_passed=True,
                manual_review_required=False,
                ledger=ledger,
            )

            self.assertFalse(downgraded.ready)
            self.assertIn("reviewer policy differs", downgraded.reasons[0])
            self.assertFalse(bound_policy.ready)
            self.assertIn("need 2 reviewer", bound_policy.reasons[0])

    def test_manual_catalogue_context_needs_version_bound_adjudication(self):
        with tempfile.TemporaryDirectory() as folder:
            ledger = OutcomeLedger(Path(folder) / "ledger.sqlite")
            checks = self.checks()
            version = self.publish_candidate(
                ledger,
                checks,
                manual_review_required=True,
            )
            ledger.add_review(
                "ZTF-test",
                candidate_version=version,
                reviewer="A",
                role="screener",
                verdict="approve",
                reason="clean",
            )
            ledger.add_review(
                "ZTF-test",
                candidate_version=version,
                reviewer="B",
                role="reviewer",
                verdict="approve",
                reason="independent",
            )

            blocked = reporting_preflight(
                "ZTF-test",
                checks=checks,
                quality_passed=True,
                manual_review_required=True,
                ledger=ledger,
            )
            self.assertFalse(blocked.ready)
            self.assertIn("scientific adjudication", blocked.reasons[0])

            ledger.add_adjudication(
                "ZTF-test",
                adjudicator="host-specialist",
                verdict="clear_context",
                reason="extended host is contextual, not a variable-source match",
                candidate_version=version,
            )
            self.assertTrue(
                reporting_preflight(
                    "ZTF-test",
                    checks=checks,
                    quality_passed=True,
                    manual_review_required=True,
                    ledger=ledger,
                ).ready
            )


class SimilarityTests(unittest.TestCase):
    def test_nearest_neighbor(self):
        index = EmbeddingIndex().fit(["a", "b"], np.array([[1.0, 0.0], [0.0, 1.0]]), ["SN", "AGN"])
        result = index.query(np.array([0.9, 0.1]), k=1)
        self.assertEqual(result[0].candidate_id, "a")

    def test_zero_k_and_invalid_embeddings_are_explicit(self):
        index = EmbeddingIndex().fit(["a"], np.array([[1.0, 0.0]]))
        self.assertEqual(index.query(np.array([1.0, 0.0]), k=0), [])
        with self.assertRaisesRegex(ValueError, "zero-norm"):
            index.query(np.array([0.0, 0.0]))
        with self.assertRaisesRegex(ValueError, "finite"):
            EmbeddingIndex().fit(["bad"], np.array([[np.nan, 1.0]]))

    def test_cosine_normalization_is_stable_across_extreme_scales(self):
        index = EmbeddingIndex().fit(
            ["large", "orthogonal"],
            np.array([[1.0e200, 1.0e200], [1.0e-200, -1.0e-200]]),
        )
        neighbors = index.query(np.array([1.0e-200, 1.0e-200]), k=1)
        self.assertEqual(neighbors[0].candidate_id, "large")
        self.assertAlmostEqual(neighbors[0].similarity, 1.0, places=6)

    def test_unfitted_index_cannot_be_saved(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            self.assertRaisesRegex(RuntimeError, "fit"),
        ):
            EmbeddingIndex().save(Path(folder) / "empty.npz")


if __name__ == "__main__":
    unittest.main()
