from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

from iris.integrity import (
    candidate_observations_digest,
    candidate_record_digest,
    candidate_run_binding_digest,
    candidate_version_basis,
)
from iris.provenance import CheckProvenance, CheckStatus, digest_value
from iris.review import assemble_review_set, load_queue_candidates
from iris.validation.binding import EvidenceBindingContext, preflight_digest
from iris.validation.gates import GateDecision, evaluate_reportability


class ReviewAssemblyTests(unittest.TestCase):
    @staticmethod
    def _record(candidate_id: str, priority: float, gate_decision: str) -> dict[str, object]:
        observations = [
            {
                "source_id": candidate_id,
                "ra_deg": 10.0,
                "dec_deg": 20.0,
                "mjd": 60000.0,
                "survey": "ztf",
                "band": "g",
                "magnitude": 19.0,
                "magnitude_error": 0.1,
                "flux": None,
                "flux_error": None,
                "limiting_magnitude": None,
                "is_detection": True,
                "quality": True,
                "observation_id": f"{candidate_id}-1",
            }
        ]
        observations_digest = candidate_observations_digest(observations)
        binding = EvidenceBindingContext(
            candidate_id=candidate_id,
            ra_deg=10.0,
            dec_deg=20.0,
            max_ttl_hours=24.0,
        )
        review_policy = {
            "required_reviewers": 1,
            "require_human_approval": True,
            "allow_self_approval": False,
        }
        scientific_config = {
            "hunt": {"min_detections": 1},
            "validation": {"required_checks": ["simbad"]},
            "ranking": {},
            "review": {"nightly_budget": 10, **review_policy},
        }
        quality = {"passed": True, "reasons": []}
        features = {"n_detections": 3}
        score = {"priority_score": priority}
        checked = datetime.now(UTC)
        check_kwargs: dict[str, object] = {
            "service": "simbad",
            "checked_at": checked.isoformat(),
            "query": {
                "candidate_id": candidate_id,
                "ra_deg": 10.0,
                "dec_deg": 20.0,
                "radius_arcsec": 3.0,
            },
        }
        if gate_decision == GateDecision.REPORTABLE.value:
            check = CheckProvenance(
                **check_kwargs,
                status=CheckStatus.CLEAR,
                expires_at=(checked + timedelta(hours=1)).isoformat(),
                response_digest=digest_value([]),
            )
        elif gate_decision == GateDecision.REJECT_KNOWN_OBJECT.value:
            check = CheckProvenance(
                **check_kwargs,
                status=CheckStatus.MATCH,
                matches=("known object",),
                response_digest=digest_value([{"name": "known object"}]),
            )
        else:
            check = CheckProvenance(
                **check_kwargs,
                status=CheckStatus.PENDING,
                attempts=0,
            )
        checks = (check,)
        gate_outcome = evaluate_reportability(
            checks,
            quality_passed=True,
            mandatory_services=("simbad",),
            at=checked,
        )
        if gate_outcome.decision.value != gate_decision:
            raise AssertionError("test fixture requested an incoherent gate decision")
        automated_gate = {
            "decision": gate_outcome.decision.value,
            "reportable": gate_outcome.reportable,
            "reasons": list(gate_outcome.reasons),
            "missing_services": list(gate_outcome.missing_services),
            "matched_services": list(gate_outcome.matched_services),
        }
        verification_context = {"simbad": [], "skybot_epochs": []}
        preflight = preflight_digest(
            context=binding,
            checks=checks,
            quality_passed=True,
            manual_review_required=False,
            mandatory_services=("simbad",),
            required_reviewers=1,
            verification_context=verification_context,
        )
        basis = candidate_version_basis(
            pipeline_version="iris.local_analysis.v3",
            candidate_id=candidate_id,
            campaign="ispy",
            observations_digest=observations_digest,
            position={"ra_deg": 10.0, "dec_deg": 20.0},
            quality=quality,
            features=features,
            score=score,
            external_checks=checks,
            manual_review_required=False,
            automated_gate=automated_gate,
            evidence_binding=binding.to_dict(),
            reporting_preflight_digest=preflight,
            scientific_config=scientific_config,
            verification_context=verification_context,
        )
        record: dict[str, object] = {
            "run_id": "source-run",
            "scientific_fingerprint": "science-fingerprint",
            "candidate_id": candidate_id,
            "pipeline_version": "iris.local_analysis.v3",
            "candidate_version": digest_value(basis),
            "preflight_digest": preflight,
            "observations_digest": observations_digest,
            "observations": observations,
            "position": {"ra_deg": 10.0, "dec_deg": 20.0},
            "origin": "test",
            "campaign": "ispy",
            "state": "needs_review",
            "quality": quality,
            "features": features,
            "score": score,
            "external_checks": [check.to_dict()],
            "automated_gate": automated_gate,
            "gate": automated_gate,
            "manual_review_required": False,
            "verification_context": verification_context,
            "review_policy": review_policy,
            "scientific_config": scientific_config,
            "manual_adjudication": {"resolved": True, "reason": "not required"},
            "evidence_binding": binding.to_dict(),
            "independent_review": {"approved": False, "reason": "missing"},
            "reportable": False,
        }
        record["candidate_record_digest"] = candidate_record_digest(record)
        record["candidate_run_binding_digest"] = candidate_run_binding_digest(record)
        return record

    @staticmethod
    def _inputs(root: Path) -> tuple[Path, Path]:
        records = [
            ReviewAssemblyTests._record("pending", 0.2, "block_incomplete_evidence"),
            ReviewAssemblyTests._record("ready", 0.9, "reportable"),
            ReviewAssemblyTests._record("known", 1.0, "reject_known_object"),
        ]
        ranking = root / "ranked.csv"
        rows = [
            "scientific_fingerprint,pipeline_version,campaign,candidate_id,candidate_version,"
            "candidate_record_digest,priority_score,quality_passed,gate_decision,"
            "review_queue_eligible"
        ]
        for record in records:
            candidate_id = str(record["candidate_id"])
            gate = str(record["gate"]["decision"])
            eligible = gate != "reject_known_object"
            rows.append(
                ",".join(
                    [
                        "science-fingerprint",
                        "iris.local_analysis.v3",
                        "ispy",
                        candidate_id,
                        str(record["candidate_version"]),
                        str(record["candidate_record_digest"]),
                        str(record["score"]["priority_score"]),
                        "true",
                        gate,
                        str(eligible).lower(),
                    ]
                )
            )
        ranking.write_text("\n".join(rows) + "\n", encoding="utf-8")
        candidates = root / "candidates.json"
        candidates.write_text(
            json.dumps(
                {
                    "schema": "iris.candidates.v1",
                    "run_id": "source-run",
                    "scientific_fingerprint": "science-fingerprint",
                    "pipeline_version": "iris.local_analysis.v3",
                    "candidates": records,
                }
            ),
            encoding="utf-8",
        )
        return ranking, candidates

    def test_review_set_is_portable_bound_and_contains_audit_propensity(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ranking, candidates = self._inputs(root)
            result = assemble_review_set(
                ranking,
                candidates,
                root / "nightly-review",
                budget=2,
                anomaly_slots=0,
                audit_slots=1,
                audit_seed="night-seed",
                eligibility_policy="triage",
            )

            self.assertEqual(result.selected_count, 2)
            self.assertTrue(result.manifest_path.is_file())
            self.assertEqual(
                (result.output_dir / "inputs" / "ranked_candidates.csv").read_bytes(),
                ranking.read_bytes(),
            )
            self.assertEqual(
                (result.output_dir / "inputs" / "candidates.json").read_bytes(),
                candidates.read_bytes(),
            )
            queue = json.loads(result.queue_path.read_text(encoding="utf-8"))
            self.assertEqual(queue["schema"], "iris.nightly_queue.v2")
            self.assertEqual(queue["audit_seed"], "night-seed")
            self.assertEqual(queue["audit_population"], 2)
            audit = [item for item in queue["entries"] if item["selection_route"] == "random_audit"]
            self.assertEqual(len(audit), 1)
            self.assertEqual(audit[0]["selection_propensity"], 0.5)
            self.assertEqual(len(result.dossier_paths), 2)
            self.assertTrue(all(path.is_file() for path in result.dossier_paths))

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema"], "iris.review_set.v1")
            self.assertEqual(manifest["source_run_id"], "source-run")
            self.assertEqual(set(manifest["selected_candidate_ids"]), {"pending", "ready"})
            self.assertIn("reporting preflight", manifest["safety_boundary"])
            self.assertTrue(all(not item["path"].startswith("/") for item in manifest["artifacts"]))

    def test_gate_clear_policy_excludes_pending_while_triage_keeps_it(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            ranking, _ = self._inputs(Path(folder))
            triage = load_queue_candidates(ranking, eligibility_policy="triage")
            gate_clear = load_queue_candidates(ranking, eligibility_policy="gate-clear")

            self.assertTrue(
                next(item for item in triage if item.candidate_id == "pending").eligible
            )
            self.assertFalse(
                next(item for item in gate_clear if item.candidate_id == "pending").eligible
            )
            self.assertFalse(next(item for item in triage if item.candidate_id == "known").eligible)

    def test_version_mismatch_fails_without_publishing_partial_directory(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ranking, candidates = self._inputs(root)
            payload = json.loads(candidates.read_text(encoding="utf-8"))
            payload["candidates"][0]["candidate_version"] = "d" * 64
            candidates.write_text(json.dumps(payload), encoding="utf-8")
            destination = root / "invalid-review"

            with self.assertRaisesRegex(ValueError, "candidate_version"):
                assemble_review_set(
                    ranking,
                    candidates,
                    destination,
                    budget=2,
                )

            self.assertFalse(destination.exists())

    def test_tampered_ranking_science_fails_cross_artifact_binding(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ranking, candidates = self._inputs(root)
            lines = ranking.read_text(encoding="utf-8").splitlines()
            columns = lines[0].split(",")
            priority_index = columns.index("priority_score")
            for index, line in enumerate(lines):
                values = line.split(",")
                if "ready" in values:
                    values[priority_index] = "1.0"
                    lines[index] = ",".join(values)
            ranking.write_text("\n".join(lines) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "priority differs"):
                assemble_review_set(ranking, candidates, root / "tampered", budget=1)

    def test_wrapper_cannot_relabel_records_as_another_source_run(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ranking, candidates = self._inputs(root)
            payload = json.loads(candidates.read_text(encoding="utf-8"))
            payload["run_id"] = "forged-run"
            payload["scientific_fingerprint"] = "forged-fingerprint"
            candidates.write_text(json.dumps(payload), encoding="utf-8")
            ranking.write_text(
                ranking.read_text(encoding="utf-8").replace(
                    "science-fingerprint", "forged-fingerprint"
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "another run"):
                assemble_review_set(ranking, candidates, root / "relabelled", budget=1)

    def test_candidate_evidence_mutations_fail_self_verification(self) -> None:
        mutations = {
            "observations": lambda record: record["observations"][0].__setitem__(
                "magnitude", -99.0
            ),
            "features": lambda record: record["features"].__setitem__("n_detections", 999),
            "checks": lambda record: record.__setitem__(
                "external_checks",
                [
                    {
                        "service": "tns",
                        "status": "pending",
                        "checked_at": "2026-01-01T00:00:00+00:00",
                    }
                ],
            ),
            "binding": lambda record: record["evidence_binding"].__setitem__("ra_deg", 11.0),
            "policy": lambda record: record["review_policy"].__setitem__("required_reviewers", 2),
            "verification_context": lambda record: record["verification_context"].__setitem__(
                "simbad", ["tampered host (galaxy)"]
            ),
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ranking, candidates = self._inputs(root)
            original = json.loads(candidates.read_text(encoding="utf-8"))
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    payload = deepcopy(original)
                    mutate(payload["candidates"][0])
                    candidates.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "candidate|record|evidence"):
                        assemble_review_set(
                            ranking,
                            candidates,
                            root / f"tampered-{name}",
                            budget=1,
                        )

    def test_unknown_gate_value_fails_closed_for_queue_eligibility(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            ranking = root / "unknown.csv"
            ranking.write_text(
                "candidate_id,priority_score,gate_decision\nA,0.9,future_decision\n",
                encoding="utf-8",
            )

            candidate = load_queue_candidates(ranking)[0]

            self.assertFalse(candidate.eligible)
            self.assertIn("unknown", candidate.ineligibility_reason or "")


if __name__ == "__main__":
    unittest.main()
