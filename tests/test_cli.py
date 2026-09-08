from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from siderea.cli import _load_candidate, main
from siderea.ingest import BrokerQuery, IngestionBatch, ingest_csv
from siderea.ledger import OutcomeLedger


def _config(path: Path) -> Path:
    path.write_text(
        """
[general]
campaign = "i_spy"

[storage]
root = "state"

[hunt]
min_detections = 2

[review]
nightly_budget = 2
required_reviewers = 1
require_human_approval = true
allow_self_approval = false
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return path


def _broker_batch() -> IngestionBatch:
    return IngestionBatch(
        observations=pd.DataFrame(
            [
                {
                    "source_id": "ZTF-test",
                    "ra_deg": 10.0,
                    "dec_deg": 20.0,
                    "mjd": 60000.0,
                    "band": "g",
                    "magnitude": 19.0,
                    "magnitude_error": 0.1,
                    "is_detection": True,
                    "limiting_magnitude": None,
                    "flux": None,
                    "flux_error": None,
                    "survey": "ztf/alerce",
                    "observation_id": "alert-1",
                    "quality": True,
                }
            ]
        ),
        source="broker:alerce",
        retrieved_at="2026-09-06T00:00:00+00:00",
        provenance={
            "adapter": "siderea.ingest.alerce.v3",
            "row_count": 1,
            "query": {"classes": ["SN"]},
        },
        warnings=("broker-fixture",),
    )


class CLITests(unittest.TestCase):
    def run_cli(self, arguments: list[str]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_candidate_loader_rejects_non_object_array_entries(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "candidates.json"
            path.write_text(
                json.dumps({"candidates": [None, {"candidate_id": "A"}]}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "non-object"):
                _load_candidate(path, "A")

    def test_analyze_creates_auditable_run(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = _config(root / "siderea.toml")
            source = root / "photometry.csv"
            source.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,magnitude,magnitude_error\n"
                "A,10,20,60000,g,19,0.1\n"
                "A,10,20,60001,g,18,0.1\n",
                encoding="utf-8",
            )
            code, stdout, stderr = self.run_cli(
                [
                    "analyze",
                    str(source),
                    "--config",
                    str(config),
                    "--output-dir",
                    str(root / "runs"),
                ]
            )
            self.assertEqual(code, 0, stderr)
            result = json.loads(stdout)
            self.assertEqual(result["candidate_count"], 1)
            self.assertTrue(result["scientific_fingerprint"].startswith("analysis-"))
            self.assertTrue(Path(result["manifest_path"]).is_file())
            candidates = json.loads(Path(result["candidates_path"]).read_text(encoding="utf-8"))
            self.assertEqual(
                candidates["candidates"][0]["pipeline_version"], "siderea.local_analysis.v4"
            )

    def test_preflight_reports_a_pending_candidate_without_drafting_output(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = _config(root / "siderea.toml")
            source = root / "photometry.csv"
            source.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,magnitude,magnitude_error\n"
                "A,10,20,60000,g,19,0.1\n"
                "A,10,20,60001,g,18,0.1\n",
                encoding="utf-8",
            )
            code, stdout, stderr = self.run_cli(
                [
                    "analyze",
                    str(source),
                    "--config",
                    str(config),
                    "--output-dir",
                    str(root / "runs"),
                ]
            )
            self.assertEqual(code, 0, stderr)
            analysis = json.loads(stdout)
            candidates = json.loads(Path(analysis["candidates_path"]).read_text(encoding="utf-8"))
            candidate_version = candidates["candidates"][0]["candidate_version"]

            code, stdout, stderr = self.run_cli(
                [
                    "preflight",
                    "A",
                    "--config",
                    str(config),
                    "--candidate-version",
                    candidate_version,
                ]
            )

            self.assertEqual(code, 3, stderr)
            result = json.loads(stdout)
            self.assertFalse(result["ready"])
            self.assertEqual(result["candidate_id"], "A")
            self.assertTrue(result["reasons"])

            code, stdout, stderr = self.run_cli(
                [
                    "preflight",
                    "A",
                    "--config",
                    str(config),
                    "--candidate-version",
                    "stale-version",
                ]
            )
            self.assertEqual(code, 3, stderr)
            self.assertIn("stale", " ".join(json.loads(stdout)["reasons"]))

    def test_broker_fetch_publishes_a_bound_pair_that_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = _config(root / "siderea.toml")
            destination = root / "broker.csv"

            with patch("siderea.ingest.AlerceAdapter.fetch", return_value=_broker_batch()):
                code, stdout, stderr = self.run_cli(
                    ["broker-fetch", str(destination), "--config", str(config)]
                )

            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            sidecar = destination.with_suffix(".csv.provenance.json")
            self.assertEqual(Path(payload["photometry"]).resolve(), destination.resolve())
            self.assertTrue(destination.is_file())
            self.assertTrue(sidecar.is_file())
            self.assertIn("_siderea_broker_snapshot_id", destination.read_text(encoding="utf-8"))
            restored = ingest_csv(destination)
            self.assertEqual(restored.source, "broker:alerce")
            self.assertEqual(restored.provenance["row_count"], 1)

    def test_broker_fetch_durably_orders_sidecar_before_csv_commit(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = _config(root / "siderea.toml")
            destination = root / "broker.csv"
            sidecar = destination.with_suffix(".csv.provenance.json")
            events: list[tuple[str, str]] = []
            real_link = os.link

            def recording_link(source: Path, target: Path) -> None:
                events.append(("link", target.name))
                real_link(source, target)

            def recording_fsync(path: Path) -> None:
                events.append(("fsync", path.name))

            with (
                patch("siderea.ingest.AlerceAdapter.fetch", return_value=_broker_batch()),
                patch("siderea.cli.os.link", side_effect=recording_link),
                patch("siderea.cli.fsync_directory", side_effect=recording_fsync),
            ):
                code, _, stderr = self.run_cli(
                    ["broker-fetch", str(destination), "--config", str(config)]
                )

            self.assertEqual(code, 0, stderr)
            self.assertEqual(
                events,
                [
                    ("link", sidecar.name),
                    ("fsync", root.name),
                    ("link", destination.name),
                    ("fsync", root.name),
                ],
            )

    def test_broker_fetch_passes_the_explicit_survey_to_alerce(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = _config(root / "siderea.toml")
            config.write_text(
                config.read_text(encoding="utf-8")
                + """

[network]
timeout_seconds = 7.5
max_retries = 1
backoff_seconds = 0.25
user_agent = "siderea-broker-policy/test-contact"
""",
                encoding="utf-8",
            )
            destination = root / "broker.csv"

            with patch("siderea.ingest.AlerceAdapter") as adapter:
                adapter.return_value.fetch.return_value = _broker_batch()
                code, _, stderr = self.run_cli(
                    [
                        "broker-fetch",
                        str(destination),
                        "--config",
                        str(config),
                        "--survey",
                        "lsst",
                        "--classifier",
                        "lsst-production-classifier",
                        "--classifier-version",
                        "2026.09",
                    ]
                )

                self.assertEqual(code, 0, stderr)
                adapter.assert_called_once_with(
                    classifier="lsst-production-classifier",
                    classifier_version="2026.09",
                    survey="lsst",
                    timeout_seconds=7.5,
                    user_agent="siderea-broker-policy/test-contact",
                    max_retries=1,
                    backoff_seconds=0.25,
                )
                adapter.return_value.fetch.assert_called_once()
                broker_query = adapter.return_value.fetch.call_args.args[0]
                self.assertIsInstance(broker_query, BrokerQuery)
                self.assertEqual(broker_query.classes, ("SN",))
                self.assertEqual(broker_query.max_objects, 350)
                self.assertEqual(broker_query.min_detections, 2)

    def test_broker_fetch_removes_sidecar_when_csv_publication_fails(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = _config(root / "siderea.toml")
            destination = root / "broker.csv"
            sidecar = destination.with_suffix(".csv.provenance.json")
            real_link = os.link
            link_calls = 0

            def fail_csv_link(source: Path, target: Path) -> None:
                nonlocal link_calls
                link_calls += 1
                if link_calls == 2:
                    raise OSError("injected CSV publication failure")
                real_link(source, target)

            with (
                patch("siderea.ingest.AlerceAdapter.fetch", return_value=_broker_batch()),
                patch("siderea.cli.os.link", side_effect=fail_csv_link),
            ):
                code, _, stderr = self.run_cli(
                    ["broker-fetch", str(destination), "--config", str(config)]
                )

            self.assertEqual(code, 2)
            self.assertIn("injected CSV publication failure", stderr)
            self.assertFalse(destination.exists())
            self.assertFalse(sidecar.exists())
            self.assertEqual(list(root.glob(".broker.csv.*.broker.tmp")), [])

    def test_broker_fetch_cleans_committed_pair_on_keyboard_interrupt(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = _config(root / "siderea.toml")
            destination = root / "broker.csv"
            sidecar = destination.with_suffix(".csv.provenance.json")

            with (
                patch("siderea.ingest.AlerceAdapter.fetch", return_value=_broker_batch()),
                patch("siderea.cli._emit_json", side_effect=KeyboardInterrupt),
                self.assertRaises(KeyboardInterrupt),
            ):
                main(["broker-fetch", str(destination), "--config", str(config)])

            self.assertFalse(destination.exists())
            self.assertFalse(sidecar.exists())
            self.assertEqual(list(root.glob(".broker.csv.*.broker.tmp")), [])

    def test_analyze_rejects_unknown_or_incomplete_verification_serialization(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = _config(root / "siderea.toml")
            source = root / "photometry.csv"
            source.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,magnitude,magnitude_error\n"
                "A,10,20,60000,g,19,0.1\n"
                "A,10,20,60001,g,18,0.1\n",
                encoding="utf-8",
            )
            invalid_schema = root / "future.json"
            invalid_schema.write_text(
                json.dumps(
                    {
                        "schema": "siderea.verification.v999",
                        "candidate_id": "A",
                        "manual_review_required": False,
                        "checks": [],
                    }
                ),
                encoding="utf-8",
            )
            code, _, stderr = self.run_cli(
                [
                    "analyze",
                    str(source),
                    "--config",
                    str(config),
                    "--checks-json",
                    str(invalid_schema),
                ]
            )
            self.assertEqual(code, 2)
            self.assertIn("schema must be", stderr)

            incomplete = root / "incomplete.json"
            incomplete.write_text(
                json.dumps(
                    {
                        "schema": "siderea.verification.v1",
                        "candidate_id": "A",
                        "manual_review_required": False,
                        "checks": [
                            {
                                "service": "simbad",
                                "status": "clear",
                                "expires_at": "2099-01-01T00:00:00+00:00",
                                "query": {},
                                "matches": [],
                                "error": "",
                                "attempts": 1,
                                "latency_ms": 1.0,
                                "response_digest": "a" * 64,
                                "service_version": "fixture",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            code, _, stderr = self.run_cli(
                [
                    "analyze",
                    str(source),
                    "--config",
                    str(config),
                    "--checks-json",
                    str(incomplete),
                ]
            )
            self.assertEqual(code, 2)
            self.assertIn("missing required fields", stderr)
            self.assertIn("checked_at", stderr)

            malformed_context = root / "malformed-context.json"
            malformed_context.write_text(
                json.dumps(
                    {
                        "schema": "siderea.verification.v1",
                        "candidate_id": "A",
                        "manual_review_required": False,
                        "context": {"simbad": "not-an-array", "skybot_epochs": []},
                        "checks": [],
                    }
                ),
                encoding="utf-8",
            )
            code, _, stderr = self.run_cli(
                [
                    "analyze",
                    str(source),
                    "--config",
                    str(config),
                    "--checks-json",
                    str(malformed_context),
                ]
            )
            self.assertEqual(code, 2)
            self.assertIn("context simbad must be an array", stderr)

    def test_offline_verification_is_explicitly_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = _config(root / "siderea.toml")
            output = root / "verification.json"
            code, _, stderr = self.run_cli(
                [
                    "verify",
                    "ZTF-offline",
                    "10",
                    "20",
                    "60000",
                    "--config",
                    str(config),
                    "--quality-passed",
                    "--disable-network",
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(code, 3, stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(payload["gate"]["reportable"])
            self.assertTrue(all(check["status"] == "disabled" for check in payload["checks"]))

    def test_verify_wires_configured_network_policy_to_every_catalog_client(self) -> None:
        from siderea.clients.catalogs import SimbadClient, SkyBotClient, VSXClient

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = _config(root / "siderea.toml")
            config.write_text(
                config.read_text(encoding="utf-8")
                + """

[network]
timeout_seconds = 7.5
max_retries = 0
backoff_seconds = 0.0
user_agent = "siderea-cli-policy/test-contact"
""",
                encoding="utf-8",
            )
            calls: dict[str, dict[str, object]] = {}

            def factory(name: str, client_type: type):
                def build(*args: object, **kwargs: object) -> object:
                    calls[name] = dict(kwargs)
                    return client_type(*args, **kwargs)

                return build

            with (
                patch(
                    "siderea.clients.catalogs.SkyBotClient",
                    side_effect=factory("skybot", SkyBotClient),
                ),
                patch(
                    "siderea.clients.catalogs.SimbadClient",
                    side_effect=factory("simbad", SimbadClient),
                ),
                patch(
                    "siderea.clients.catalogs.VSXClient",
                    side_effect=factory("vsx", VSXClient),
                ),
            ):
                code, _, stderr = self.run_cli(
                    [
                        "verify",
                        "ZTF-network-policy",
                        "10",
                        "20",
                        "60000",
                        "--config",
                        str(config),
                        "--quality-passed",
                        "--disable-network",
                    ]
                )

            self.assertEqual(code, 3, stderr)
            self.assertEqual(set(calls), {"skybot", "simbad", "vsx"})
            for service, call in calls.items():
                with self.subTest(service=service):
                    self.assertFalse(call["enabled"])
                    self.assertEqual(call["timeout_seconds"], 7.5)
                    self.assertEqual(call["user_agent"], "siderea-cli-policy/test-contact")

    def test_queue_distinguishes_triage_from_reportability_and_records_audit_seed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = _config(root / "siderea.toml")
            ranking = root / "ranked.csv"
            ranking.write_text(
                "candidate_id,priority_score,quality_passed,gate_decision,review_queue_eligible\n"
                "pending,0.9,true,block_incomplete_evidence,true\n"
                "known,0.8,true,reject_known_object,false\n",
                encoding="utf-8",
            )

            code, stdout, stderr = self.run_cli(
                [
                    "queue",
                    str(ranking),
                    "--config",
                    str(config),
                    "--anomaly-slots",
                    "0",
                    "--audit-slots",
                    "1",
                    "--audit-seed",
                    "auditable-night",
                ]
            )
            self.assertEqual(code, 0, stderr)
            triage = json.loads(stdout)
            self.assertEqual([item["candidate_id"] for item in triage["entries"]], ["pending"])
            self.assertEqual(triage["entries"][0]["selection_route"], "random_audit")
            self.assertEqual(triage["entries"][0]["selection_propensity"], 1.0)
            self.assertEqual(triage["audit_seed"], "auditable-night")
            self.assertEqual(triage["selection_policy"], "triage_v1")

            code, stdout, stderr = self.run_cli(
                [
                    "queue",
                    str(ranking),
                    "--config",
                    str(config),
                    "--anomaly-slots",
                    "0",
                    "--audit-slots",
                    "0",
                    "--eligibility-policy",
                    "gate-clear",
                ]
            )
            self.assertEqual(code, 0, stderr)
            gate_clear = json.loads(stdout)
            self.assertEqual(gate_clear["entries"], [])
            self.assertEqual(gate_clear["selection_policy"], "gate-clear_v1")

    def test_review_set_command_packages_a_pending_offline_candidate_for_triage(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = _config(root / "siderea.toml")
            source = root / "photometry.csv"
            source.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,magnitude,magnitude_error\n"
                "A,10,20,60000,g,19,0.1\n"
                "A,10,20,60001,g,18,0.1\n",
                encoding="utf-8",
            )
            code, stdout, stderr = self.run_cli(
                [
                    "analyze",
                    str(source),
                    "--config",
                    str(config),
                    "--output-dir",
                    str(root / "runs"),
                ]
            )
            self.assertEqual(code, 0, stderr)
            analysis = json.loads(stdout)
            review_dir = root / "review-set"

            code, stdout, stderr = self.run_cli(
                [
                    "review-set",
                    analysis["ranked_candidates_path"],
                    analysis["candidates_path"],
                    str(review_dir),
                    "--config",
                    str(config),
                    "--anomaly-slots",
                    "0",
                    "--audit-slots",
                    "1",
                    "--audit-seed",
                    "cli-replay-seed",
                ]
            )

            self.assertEqual(code, 0, stderr)
            result = json.loads(stdout)
            self.assertEqual(result["selected_count"], 1)
            queue = json.loads((review_dir / "queue.json").read_text(encoding="utf-8"))
            self.assertEqual(queue["entries"][0]["candidate_id"], "A")
            self.assertEqual(queue["entries"][0]["selection_route"], "random_audit")
            self.assertTrue(Path(result["manifest_path"]).is_file())

    def test_review_add_rejects_unknown_candidate_then_records_known_one(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = _config(root / "siderea.toml")
            ledger_path = root / "ledger.sqlite"
            candidate_version = "reviewed-evidence-v1"
            arguments = [
                "review-add",
                "A",
                "--config",
                str(config),
                "--ledger",
                str(ledger_path),
                "--candidate-version",
                candidate_version,
                "--reviewer",
                "scientist-a",
                "--role",
                "screener",
                "--verdict",
                "approve",
                "--reason",
                "clean subtraction",
            ]
            code, _, stderr = self.run_cli(arguments)
            self.assertEqual(code, 2)
            self.assertIn("unknown candidate", stderr)

            ledger = OutcomeLedger(ledger_path)
            ledger.upsert_candidate(
                "A",
                campaign="i_spy",
                state="needs_review",
                payload={},
                version_digest=candidate_version,
            )
            code, stdout, stderr = self.run_cli(arguments)
            self.assertEqual(code, 0, stderr)
            self.assertEqual(json.loads(stdout)["reviewer"], "scientist-a")

            ledger.upsert_candidate(
                "A",
                campaign="i_spy",
                state="needs_review",
                payload={"updated": True},
                version_digest="reviewed-evidence-v2",
            )
            code, _, stderr = self.run_cli(arguments)
            self.assertEqual(code, 2)
            self.assertIn("changed after", stderr)


if __name__ == "__main__":
    unittest.main()
