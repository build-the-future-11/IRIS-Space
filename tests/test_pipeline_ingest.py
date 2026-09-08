from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from siderea.config import (
    GeneralConfig,
    HuntConfig,
    RankingConfig,
    SIDEREAConfig,
    StorageConfig,
)
from siderea.features import compute_photometry_features
from siderea.ingest import AlerceAdapter, BrokerQuery, IngestionError, ingest_csv
from siderea.ingest.snapshot import BROKER_SNAPSHOT_ID_COLUMN, broker_snapshot_id
from siderea.ledger import OutcomeLedger
from siderea.manifest import RunManifest
from siderea.pipeline import _frame_digest, analyze_batch, analyze_csv, deterministic_run_id
from siderea.provenance import CheckProvenance, CheckStatus, digest_value
from siderea.reporting.preflight import reporting_preflight


def _config(root: Path) -> SIDEREAConfig:
    return SIDEREAConfig(
        general=GeneralConfig(campaign="i_spy"),
        storage=StorageConfig(
            root=root,
            runs_dir=root / "runs",
            cache_dir=root / "cache",
            datasets_dir=root / "datasets",
        ),
        hunt=HuntConfig(min_detections=2),
    )


class CSVIngestionTests(unittest.TestCase):
    def test_aliases_identifier_dtype_and_jd_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "alerts.csv"
            path.write_text(
                "oid,meanra,meandec,jd,fid,magpsf,sigmapsf,detected,diffmaglim\n"
                "0012,12.5,-3.0,2460001.5,1,,,false,20.5\n"
                "0012,12.5,-3.0,2460002.5,1,19.0,0.1,true,\n",
                encoding="utf-8",
            )

            batch = ingest_csv(path)
            frame = batch.to_frame()

            self.assertEqual(batch.candidate_ids, ("0012",))
            self.assertEqual(frame["mjd"].tolist(), [60001.0, 60002.0])
            self.assertEqual(frame["band"].tolist(), ["1", "1"])
            self.assertEqual(frame["survey"].tolist(), ["ztf", "ztf"])
            self.assertEqual(frame["is_detection"].tolist(), [False, True])
            self.assertIn("converted_jd_to_mjd", batch.warnings)
            self.assertIn("inferred_ztf_survey_from_fid_column", batch.warnings)
            self.assertEqual(batch.provenance["row_count"], 2)
            self.assertEqual(len(batch.provenance["sha256"]), 64)

    def test_ambiguous_aliases_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "ambiguous.csv"
            path.write_text(
                "candidate_id,oid,ra,dec,mjd,band,mag\nA,A,1,2,3,g,19\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(IngestionError, "ambiguous columns"):
                ingest_csv(path)

    def test_unix_seconds_are_not_silently_treated_as_julian_days(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "unix.csv"
            path.write_text(
                "source_id,ra_deg,dec_deg,time,band,magnitude,magnitude_error\n"
                "A,10.0,20.0,1700000000,g,19.0,0.2\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(IngestionError, "Unix timestamps"):
                ingest_csv(path)

    def test_inconsistent_candidate_coordinates_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "moving.csv"
            path.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,magnitude\n"
                "A,1.0,2.0,60000,g,19\n"
                "A,1.1,2.0,60001,g,18\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(IngestionError, "positions separated"):
                ingest_csv(path)

    def test_flux_only_detections_are_preserved_without_false_magnitude_warning(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "forced.csv"
            path.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,flux,flux_error,is_detection\n"
                "A,10.0,20.0,60000,g,1.0,0.2,true\n"
                "A,10.0,20.0,60001,g,3.0,0.2,true\n",
                encoding="utf-8",
            )

            batch = ingest_csv(path)

            self.assertEqual(batch.observations["flux"].tolist(), [1.0, 3.0])
            self.assertNotIn("detections_with_missing_measurement", batch.warnings)

    def test_missing_explicit_detection_semantics_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "missing-detection.csv"
            path.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,flux,flux_error,is_detection\n"
                "A,10.0,20.0,60000,g,1.0,0.2,\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(IngestionError, "is_detection.*missing"):
                ingest_csv(path)
            with self.assertRaisesRegex(ValueError, "detection column has missing"):
                compute_photometry_features(
                    pd.DataFrame(
                        {
                            "mjd": [60000.0],
                            "band": ["g"],
                            "flux": [1.0],
                            "flux_error": [0.2],
                            "is_detection": [None],
                        }
                    )
                )

    def test_empty_magnitude_column_does_not_hide_flux_only_detection_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "empty-magnitude.csv"
            path.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,magnitude,flux,flux_error\n"
                "A,10.0,20.0,60000,g,,1.0,0.2\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(IngestionError, "flux-only.*is_detection"):
                ingest_csv(path)

    def test_negative_flag_polarity_survives_canonicalization(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "flags.csv"
            path.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,flux,flux_error,is_detection,flags\n"
                "A,10.0,20.0,60000,g,1.0,0.2,true,true\n"
                "A,10.0,20.0,60001,g,2.0,0.2,true,false\n",
                encoding="utf-8",
            )

            batch = ingest_csv(path)
            features = compute_photometry_features(
                batch.observations.drop(columns=["source_id", "ra_deg", "dec_deg"])
            )

            self.assertEqual(batch.observations["quality"].tolist(), [False, True])
            self.assertEqual(features["n_detections"], 1)
            self.assertEqual(features["quality_rejected_fraction"], 0.5)

            positive_quality = compute_photometry_features(
                pd.DataFrame(
                    {
                        "mjd": [1.0, 2.0],
                        "band": ["g", "g"],
                        "flux": [1.0, 2.0],
                        "flux_error": [0.2, 0.2],
                        "is_detection": [True, True],
                        "quality_ok": [1, 1],
                    }
                )
            )
            self.assertEqual(positive_quality["n_detections"], 2)

            canonical_quality = compute_photometry_features(
                pd.DataFrame(
                    {
                        "mjd": [1.0, 2.0],
                        "band": ["g", "g"],
                        "flux": [1.0, 2.0],
                        "flux_error": [0.2, 0.2],
                        "is_detection": [True, True],
                        "quality": [1, 0],
                    }
                )
            )
            self.assertEqual(canonical_quality["n_detections"], 1)

    def test_exact_duplicate_observations_fail_instead_of_inflating_counts(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "duplicates.csv"
            path.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,magnitude,magnitude_error,is_detection\n"
                "A,10.0,20.0,60000,g,19.0,0.2,true\n"
                "A,10.0,20.0,60000,g,19.0,0.2,true\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(IngestionError, "duplicate observations"):
                ingest_csv(path)

    def test_conflicting_rows_cannot_reuse_an_observation_identifier(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "conflicting-id.csv"
            path.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,magnitude,magnitude_error,observation_id\n"
                "A,10.0,20.0,60000,g,19.0,0.2,alert-1\n"
                "A,10.0,20.0,60000,g,18.5,0.2,alert-1\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(IngestionError, "reuse.*observation_id"):
                ingest_csv(path)

    def test_survey_identity_is_canonical_before_duplicate_checks(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "survey-case-duplicate.csv"
            path.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,magnitude,magnitude_error,observation_id,survey\n"
                "A,10.0,20.0,60000,g,19.0,0.2,alert-1,ZTF\n"
                "A,10.0,20.0,60000,g,19.0,0.2,alert-1, ztf \n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(IngestionError, "duplicate observations"):
                ingest_csv(path)

    def test_broker_sidecar_is_content_bound_and_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "broker.csv"
            content = (
                "source_id,ra_deg,dec_deg,mjd,band,magnitude,magnitude_error\n"
                "A,10.0,20.0,60000,g,19.0,0.2\n"
            )
            path.write_text(content, encoding="utf-8")
            sidecar = path.with_suffix(".csv.provenance.json")
            sidecar.write_text(
                json.dumps(
                    {
                        "schema": "siderea.broker_snapshot.v1",
                        "source": "broker:alerce",
                        "retrieved_at": datetime.now(UTC).isoformat(),
                        "photometry_sha256": sha256(content.encode()).hexdigest(),
                        "provenance": {
                            "adapter": "siderea.ingest.alerce.v1",
                            "row_count": 1,
                            "query": {"classes": ["SN"]},
                        },
                        "warnings": ["broker-test"],
                    }
                ),
                encoding="utf-8",
            )

            batch = ingest_csv(path)

            self.assertEqual(batch.source, "broker:alerce")
            self.assertEqual(batch.provenance["adapter"], "siderea.ingest.alerce.v1")
            self.assertIn("broker-test", batch.warnings)
            path.write_text(content.replace("19.0", "18.0"), encoding="utf-8")
            with self.assertRaisesRegex(IngestionError, "does not match"):
                ingest_csv(path)

    def test_marked_broker_csv_requires_and_authenticates_its_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "broker-marked.csv"
            provenance = {
                "adapter": "siderea.ingest.alerce.v1",
                "row_count": 1,
                "query": {"classes": ["SN"]},
            }
            warnings = ["broker-test"]
            retrieved_at = datetime.now(UTC).isoformat()
            snapshot_id = broker_snapshot_id(
                source="broker:alerce",
                retrieved_at=retrieved_at,
                provenance=provenance,
                warnings=warnings,
            )
            content = (
                "source_id,ra_deg,dec_deg,mjd,band,magnitude,magnitude_error,"
                f"{BROKER_SNAPSHOT_ID_COLUMN}\n"
                f"A,10.0,20.0,60000,g,19.0,0.2,{snapshot_id}\n"
            )
            path.write_text(content, encoding="utf-8")

            with self.assertRaisesRegex(IngestionError, "missing its provenance sidecar"):
                ingest_csv(path)

            sidecar = path.with_suffix(".csv.provenance.json")
            payload = {
                "schema": "siderea.broker_snapshot.v1",
                "snapshot_id": snapshot_id,
                "source": "broker:alerce",
                "retrieved_at": retrieved_at,
                "photometry_sha256": sha256(content.encode()).hexdigest(),
                "provenance": provenance,
                "warnings": warnings,
            }
            sidecar.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(ingest_csv(path).source, "broker:alerce")

            payload["provenance"]["query"] = {"classes": ["bogus"]}
            sidecar.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(IngestionError, "metadata does not match"):
                ingest_csv(path)


class _FakeAlerce:
    def query_objects(self, **_: object) -> pd.DataFrame:
        return pd.DataFrame({"oid": ["ZTF-A"], "meanra": [11.0], "meandec": [-2.0]})

    def query_detections(self, _: str, **__: object) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "mjd": [60001.0, 60002.0],
                "fid": [1, 1],
                "magpsf": [19.0, 18.0],
                "sigmapsf": [0.1, 0.1],
                "isdiffpos": [1, 1],
            }
        )

    def query_non_detections(self, _: str, **__: object) -> pd.DataFrame:
        return pd.DataFrame({"mjd": [60000.0], "fid": [1], "diffmaglim": [20.5]})


class AlerceAdapterTests(unittest.TestCase):
    def test_injected_client_needs_no_optional_dependency(self) -> None:
        batch = AlerceAdapter(_FakeAlerce()).fetch(BrokerQuery(max_objects=1))

        self.assertEqual(batch.candidate_ids, ("ZTF-A",))
        self.assertEqual(len(batch.observations), 3)
        self.assertEqual(int(batch.observations["is_detection"].sum()), 2)
        self.assertEqual(batch.provenance["candidate_classes"], {"ZTF-A": "SN"})
        features = compute_photometry_features(
            batch.observations.drop(columns=["source_id", "ra_deg", "dec_deg"])
        )
        self.assertEqual(features["channels"], ["ztf%2Falerce::g"])
        self.assertEqual(features["bands"], ["g"])


class LocalPipelineTests(unittest.TestCase):
    @staticmethod
    def _write_input(path: Path) -> None:
        path.write_text(
            "source_id,ra_deg,dec_deg,mjd,band,magnitude,magnitude_error,is_detection,limiting_magnitude\n"
            "A,10.0,20.0,60000,g,,,false,20.5\n"
            "A,10.0,20.0,60001,g,19.2,0.1,true,\n"
            "A,10.0,20.0,60002,g,18.0,0.1,true,\n"
            "B,30.0,-10.0,60001,r,20.0,0.1,true,\n"
            "B,30.0,-10.0,60002,r,19.9,0.1,true,\n",
            encoding="utf-8",
        )

    @staticmethod
    def _clear_checks(
        config: SIDEREAConfig,
        *,
        candidate_id: str = "A",
        ra: float = 10.0,
        dec: float = 20.0,
        skybot_mjd: float | None = None,
    ) -> tuple[CheckProvenance, ...]:
        checked = datetime.now(UTC)
        expires = checked + timedelta(hours=12)
        radii = {
            "tns": config.validation.tns_radius_arcsec,
            "skybot": config.validation.skybot_radius_arcsec,
            "simbad": config.validation.catalog_radius_arcsec,
            "vsx": config.validation.catalog_radius_arcsec,
        }
        checks: list[CheckProvenance] = []
        for service in config.validation.required_checks:
            query: dict[str, object] = {
                "ra": ra,
                "dec": dec,
                "radius_arcsec": radii[service],
            }
            if service == "tns":
                query.update(
                    {
                        "methods": ["internal_name", "cone"],
                        "coverage_policy": "internal_name_and_position_cone",
                        "candidate_id": candidate_id,
                        "internal_name_checked": candidate_id,
                    }
                )
            if service == "skybot":
                if skybot_mjd is None:
                    query["mjds"] = [60001.0, 60002.0]
                else:
                    query["mjd"] = skybot_mjd
            checks.append(
                CheckProvenance(
                    service=service,
                    status=CheckStatus.CLEAR,
                    checked_at=checked.isoformat(),
                    expires_at=expires.isoformat(),
                    query=query,
                    response_digest=digest_value({"service": service, "query": query}),
                    service_version=("tns-two-stage-search.v1" if service == "tns" else ""),
                )
            )
        return tuple(checks)

    def test_runs_are_immutable_but_scientific_fingerprint_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "photometry.csv"
            self._write_input(input_path)
            config = _config(root / "state")
            ledger_path = root / "state" / "ledger.sqlite"

            batch = ingest_csv(input_path)
            fingerprint = deterministic_run_id(batch, config)
            self.assertEqual(fingerprint, deterministic_run_id(batch, config))

            first = analyze_csv(
                input_path,
                config,
                output_dir=root / "runs",
                ledger_path=ledger_path,
            )
            ranked_content = first.ranked_candidates_path.read_text(encoding="utf-8")
            second = analyze_csv(
                input_path,
                config,
                output_dir=root / "runs",
                ledger_path=ledger_path,
            )

            self.assertNotEqual(first.run_id, second.run_id)
            self.assertNotEqual(first.run_dir, second.run_dir)
            self.assertEqual(
                ranked_content,
                second.ranked_candidates_path.read_text(encoding="utf-8"),
            )
            first_ranked = pd.read_csv(first.ranked_candidates_path)
            second_ranked = pd.read_csv(second.ranked_candidates_path)
            self.assertEqual(
                first_ranked.set_index("candidate_id")["candidate_version"].to_dict(),
                second_ranked.set_index("candidate_id")["candidate_version"].to_dict(),
            )
            self.assertEqual(first.candidate_count, 2)
            self.assertEqual(first.reportable_count, 0)
            ranked = pd.read_csv(first.ranked_candidates_path)
            self.assertTrue((ranked["gate_decision"] == "block_incomplete_evidence").all())
            self.assertTrue((ranked["check_tns"] == "pending").all())
            self.assertFalse(ranked["reportable"].any())
            self.assertEqual(ranked.iloc[0]["candidate_id"], "A")

            candidate = OutcomeLedger(ledger_path).candidate("A")
            self.assertIsNotNone(candidate)
            self.assertEqual(candidate["state"], "needs_review")
            self.assertEqual(len(candidate["payload"]["observations"]), 3)
            self.assertIn("features", candidate["payload"])
            self.assertEqual(len(candidate["payload"]["external_checks"]), 4)
            self.assertEqual(candidate["payload"]["candidate_version"], candidate["version_digest"])
            manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["metrics"]["candidate_count"], 2)
            self.assertTrue(first.snapshot_path.is_file())

    def test_interruption_writes_a_terminal_manifest_with_partial_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "photometry.csv"
            self._write_input(input_path)
            config = _config(root / "state")
            runs = root / "runs"

            with (
                patch(
                    "siderea.pipeline.compute_photometry_features",
                    side_effect=KeyboardInterrupt,
                ),
                self.assertRaises(KeyboardInterrupt),
            ):
                analyze_csv(
                    input_path,
                    config,
                    output_dir=runs,
                    run_id="interrupted-test",
                )

            manifest = json.loads(
                (runs / "interrupted-test" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "interrupted")
            self.assertTrue(manifest["completed_at"])
            self.assertGreaterEqual(manifest["metrics"]["partial_artifact_count"], 2)
            roles = {item["role"] for item in manifest["artifacts"]}
            self.assertIn("normalized-photometry", roles)
            self.assertIn("dataset-snapshot", roles)

    def test_terminal_manifest_failure_never_publishes_ledger_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "photometry.csv"
            self._write_input(input_path)
            ledger_path = root / "state" / "ledger.sqlite"
            original_write = RunManifest.write

            def fail_completed(manifest: RunManifest, path: Path) -> None:
                if manifest.status == "completed":
                    raise OSError("injected terminal publication failure")
                original_write(manifest, path)

            with (
                patch.object(RunManifest, "write", new=fail_completed),
                self.assertRaisesRegex(OSError, "injected terminal"),
            ):
                analyze_csv(
                    input_path,
                    _config(root / "state"),
                    output_dir=root / "runs",
                    ledger_path=ledger_path,
                    run_id="failed-publication",
                )

            self.assertIsNone(OutcomeLedger(ledger_path).candidate("A"))
            manifest = json.loads(
                (root / "runs" / "failed-publication" / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "failed")

    def test_same_version_scientific_payload_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "photometry.csv"
            self._write_input(input_path)
            ledger = OutcomeLedger(root / "state" / "ledger.sqlite")
            analyze_csv(
                input_path,
                _config(root / "state"),
                output_dir=root / "runs",
                ledger=ledger,
            )
            current = ledger.candidate("A")
            self.assertIsNotNone(current)
            payload = dict(current["payload"])
            payload["features"] = {**payload["features"], "n_detections": 999}

            with self.assertRaisesRegex(ValueError, "candidate_version"):
                ledger.upsert_candidate(
                    "A",
                    campaign=str(current["campaign"]),
                    state=str(current["state"]),
                    payload=payload,
                    version_digest=str(current["version_digest"]),
                )

    def test_reporting_preflight_requires_the_published_manifest_digest(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "photometry.csv"
            self._write_input(input_path)
            config = _config(root / "state")
            ledger = OutcomeLedger(root / "state" / "ledger.sqlite")
            checks = {"A": self._clear_checks(config)}
            initial = analyze_csv(
                input_path,
                config,
                output_dir=root / "runs",
                ledger=ledger,
                checks_by_candidate=checks,
            )
            candidate = next(
                item
                for item in json.loads(initial.candidates_path.read_text(encoding="utf-8"))[
                    "candidates"
                ]
                if item["candidate_id"] == "A"
            )
            for reviewer, role in (("screen-a", "screener"), ("review-b", "reviewer")):
                ledger.add_review(
                    "A",
                    candidate_version=candidate["candidate_version"],
                    reviewer=reviewer,
                    role=role,
                    verdict="approve",
                    reason="verified",
                )
            published = analyze_csv(
                input_path,
                config,
                output_dir=root / "runs",
                ledger=ledger,
                checks_by_candidate=checks,
            )
            current = ledger.candidate("A")
            ready = reporting_preflight(
                "A",
                checks=checks["A"],
                quality_passed=True,
                manual_review_required=False,
                ledger=ledger,
                candidate_version=str(current["version_digest"]),
            )
            self.assertTrue(ready.ready, ready.reasons)

            published.manifest_path.write_text(
                published.manifest_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            result = reporting_preflight(
                "A",
                checks=checks["A"],
                quality_passed=True,
                manual_review_required=False,
                ledger=ledger,
                candidate_version=str(current["version_digest"]),
            )

            self.assertFalse(result.ready)
            self.assertIn("manifest differs", result.reasons[0])

    def test_scientific_fingerprint_ignores_source_location_and_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first_path = root / "first.csv"
            second_path = root / "nested" / "second.csv"
            second_path.parent.mkdir()
            self._write_input(first_path)
            second_path.write_bytes(first_path.read_bytes())
            os.utime(second_path, (1_700_000_000, 1_700_000_000))
            config = _config(root / "state")

            first = deterministic_run_id(ingest_csv(first_path), config)
            second = deterministic_run_id(ingest_csv(second_path), config)

            self.assertEqual(first, second)

    def test_frame_digest_preserves_distinct_float64_values(self) -> None:
        first = pd.DataFrame({"measurement": [1.0000000000001]})
        second = pd.DataFrame({"measurement": [1.0000000000002]})

        self.assertNotEqual(_frame_digest(first), _frame_digest(second))

    def test_manifest_archives_the_exact_bytes_that_were_ingested(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "photometry.csv"
            self._write_input(input_path)
            batch = ingest_csv(input_path)
            ingested_bytes = input_path.read_bytes()
            input_path.write_text("source_id,corrupted\nA,replaced\n", encoding="utf-8")

            result = analyze_batch(
                batch,
                _config(root / "state"),
                output_dir=root / "runs",
                ledger_path=root / "state" / "ledger.sqlite",
            )
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            source_artifact = next(
                item for item in manifest["artifacts"] if item["role"] == "source-input-snapshot"
            )

            archived = Path(source_artifact["path"])
            self.assertEqual(archived.read_bytes(), ingested_bytes)
            self.assertEqual(source_artifact["sha256"], batch.provenance["sha256"])

    def test_candidate_version_includes_raw_normalized_observations(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first_path = root / "first.csv"
            second_path = root / "second.csv"
            header = (
                "source_id,ra_deg,dec_deg,mjd,band,magnitude,magnitude_error,"
                "is_detection,observation_id\n"
            )
            first_path.write_text(
                header
                + "A,10.0,20.0,60001,g,19.2,0.1,true,alert-1\n"
                + "A,10.0,20.0,60002,g,18.0,0.1,true,alert-2\n",
                encoding="utf-8",
            )
            second_path.write_text(
                header
                + "A,10.0,20.0,60001,g,19.2,0.1,true,reprocessed-1\n"
                + "A,10.0,20.0,60002,g,18.0,0.1,true,reprocessed-2\n",
                encoding="utf-8",
            )
            config = _config(root / "state")
            ledger_path = root / "state" / "ledger.sqlite"

            first = analyze_csv(
                first_path,
                config,
                output_dir=root / "runs",
                ledger_path=ledger_path,
            )
            second = analyze_csv(
                second_path,
                config,
                output_dir=root / "runs",
                ledger_path=ledger_path,
            )
            first_record = json.loads(first.candidates_path.read_text(encoding="utf-8"))[
                "candidates"
            ][0]
            second_record = json.loads(second.candidates_path.read_text(encoding="utf-8"))[
                "candidates"
            ][0]

            self.assertNotEqual(
                first_record["candidate_version"],
                second_record["candidate_version"],
            )

    def test_all_detection_uncertainties_missing_fails_local_quality(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "uncertainty-free.csv"
            input_path.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,magnitude,is_detection\n"
                "A,10.0,20.0,60001,g,19.2,true\n"
                "A,10.0,20.0,60002,g,18.0,true\n",
                encoding="utf-8",
            )

            result = analyze_csv(
                input_path,
                _config(root / "state"),
                output_dir=root / "runs",
                ledger_path=root / "state" / "ledger.sqlite",
            )
            ranked = pd.read_csv(result.ranked_candidates_path)

            self.assertFalse(bool(ranked.iloc[0]["quality_passed"]))
            self.assertIn(
                "all detection measurement uncertainties are missing or invalid",
                json.loads(ranked.iloc[0]["quality_reasons"]),
            )
            self.assertFalse(bool(ranked.iloc[0]["reportable"]))

    def test_supplied_but_unrecognized_quality_never_becomes_usable(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "unknown-quality.csv"
            input_path.write_text(
                "source_id,ra_deg,dec_deg,mjd,band,magnitude,magnitude_error,quality\n"
                "A,10.0,20.0,60001,g,19.2,0.1,mystery\n"
                "A,10.0,20.0,60002,g,18.0,0.1,mystery\n",
                encoding="utf-8",
            )

            result = analyze_csv(
                input_path,
                _config(root / "state"),
                output_dir=root / "runs",
                ledger_path=root / "state" / "ledger.sqlite",
            )
            candidate = json.loads(result.candidates_path.read_text(encoding="utf-8"))[
                "candidates"
            ][0]

            self.assertEqual(candidate["features"]["n_detections"], 0)
            self.assertEqual(candidate["features"]["quality_rejected_fraction"], 1.0)
            self.assertFalse(candidate["quality"]["passed"])
            self.assertFalse(candidate["reportable"])

    def test_configured_scientific_ranking_weights_drive_the_pipeline_score(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "photometry.csv"
            self._write_input(input_path)
            config = replace(
                _config(root / "state"),
                ranking=RankingConfig(
                    amplitude_weight=1.0,
                    significance_weight=0.0,
                    temporal_weight=0.0,
                    nondetection_weight=0.0,
                    sampling_weight=0.0,
                    quality_weight=0.0,
                    anomaly_slots=0,
                ),
            )

            result = analyze_csv(
                input_path,
                config,
                output_dir=root / "runs",
                ledger_path=root / "state" / "ledger.sqlite",
            )
            records = json.loads(result.candidates_path.read_text(encoding="utf-8"))
            score = records["candidates"][0]["score"]

            self.assertEqual(score["components"]["amplitude"]["weight"], 1.0)
            self.assertEqual(score["components"]["significance"]["weight"], 0.0)

    def test_clear_external_evidence_still_requires_independent_review(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "photometry.csv"
            self._write_input(input_path)
            config = _config(root / "state")
            ledger = OutcomeLedger(root / "state" / "ledger.sqlite")
            analyze_csv(input_path, config, output_dir=root / "runs", ledger=ledger)

            checks = {"A": self._clear_checks(config)}
            without_review = analyze_csv(
                input_path,
                config,
                output_dir=root / "runs",
                ledger=ledger,
                checks_by_candidate=checks,
            )
            records = json.loads(without_review.candidates_path.read_text(encoding="utf-8"))
            candidate_a = next(
                item for item in records["candidates"] if item["candidate_id"] == "A"
            )
            self.assertTrue(candidate_a["gate"]["reportable"])
            self.assertFalse(candidate_a["reportable"])

            ledger.add_review(
                "A",
                candidate_version=candidate_a["candidate_version"],
                reviewer="screen-a",
                role="screener",
                verdict="approve",
                reason="clean",
            )
            ledger.add_review(
                "A",
                candidate_version=candidate_a["candidate_version"],
                reviewer="review-b",
                role="reviewer",
                verdict="approve",
                reason="verified",
            )
            approved = analyze_csv(
                input_path,
                config,
                output_dir=root / "runs",
                ledger=ledger,
                checks_by_candidate=checks,
            )
            self.assertEqual(approved.reportable_count, 1)
            approved_records = json.loads(approved.candidates_path.read_text(encoding="utf-8"))
            candidate_a = next(
                item for item in approved_records["candidates"] if item["candidate_id"] == "A"
            )
            self.assertTrue(candidate_a["reportable"])
            self.assertEqual(candidate_a["state"], "approved")

    def test_manual_catalogue_context_can_be_resolved_for_the_exact_version(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "photometry.csv"
            self._write_input(input_path)
            config = _config(root / "state")
            ledger = OutcomeLedger(root / "state" / "ledger.sqlite")
            checks = {"A": self._clear_checks(config)}
            context = {
                "A": {
                    "simbad": ["NGC 123 (galaxy)"],
                    "skybot_epochs": ["60001.00000000", "60002.00000000"],
                }
            }

            with self.assertRaisesRegex(ValueError, "non-empty SIMBAD context"):
                analyze_csv(
                    input_path,
                    config,
                    output_dir=root / "runs",
                    ledger=ledger,
                    checks_by_candidate=checks,
                    manual_review_by_candidate={"A": True},
                )

            blocked = analyze_csv(
                input_path,
                config,
                output_dir=root / "runs",
                ledger=ledger,
                checks_by_candidate=checks,
                manual_review_by_candidate={"A": True},
                context_by_candidate=context,
            )
            blocked_records = json.loads(blocked.candidates_path.read_text(encoding="utf-8"))
            candidate = next(
                item for item in blocked_records["candidates"] if item["candidate_id"] == "A"
            )
            version = candidate["candidate_version"]
            self.assertEqual(candidate["verification_context"], context["A"])
            self.assertEqual(candidate["gate"]["decision"], "needs_manual_review")
            ledger.add_adjudication(
                "A",
                adjudicator="host-specialist",
                verdict="clear_context",
                reason="catalogue object is an extended host rather than the transient",
                candidate_version=version,
            )
            ledger.add_review(
                "A",
                reviewer="screen-a",
                role="screener",
                verdict="approve",
                reason="clean",
                candidate_version=version,
            )
            ledger.add_review(
                "A",
                reviewer="review-b",
                role="reviewer",
                verdict="approve",
                reason="verified",
                candidate_version=version,
            )

            approved = analyze_csv(
                input_path,
                config,
                output_dir=root / "runs",
                ledger=ledger,
                checks_by_candidate=checks,
                manual_review_by_candidate={"A": True},
                context_by_candidate=context,
            )

            self.assertEqual(approved.reportable_count, 1)

    def test_completed_evidence_for_another_position_cannot_open_gate(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "photometry.csv"
            self._write_input(input_path)
            config = _config(root / "state")
            ledger = OutcomeLedger(root / "state" / "ledger.sqlite")
            initial = analyze_csv(input_path, config, output_dir=root / "runs", ledger=ledger)
            initial_records = json.loads(initial.candidates_path.read_text(encoding="utf-8"))
            initial_version = next(
                item["candidate_version"]
                for item in initial_records["candidates"]
                if item["candidate_id"] == "A"
            )
            ledger.add_review(
                "A",
                candidate_version=initial_version,
                reviewer="screen-a",
                role="screener",
                verdict="approve",
                reason="clean",
            )
            ledger.add_review(
                "A",
                candidate_version=initial_version,
                reviewer="review-b",
                role="reviewer",
                verdict="approve",
                reason="verified",
            )

            result = analyze_csv(
                input_path,
                config,
                output_dir=root / "runs",
                ledger=ledger,
                checks_by_candidate={
                    "A": self._clear_checks(config, candidate_id="A", ra=30.0, dec=-10.0)
                },
            )

            records = json.loads(result.candidates_path.read_text(encoding="utf-8"))
            candidate_a = next(
                item for item in records["candidates"] if item["candidate_id"] == "A"
            )
            self.assertFalse(candidate_a["gate"]["reportable"])
            self.assertFalse(candidate_a["reportable"])
            self.assertTrue(
                all(check["status"] == "error" for check in candidate_a["external_checks"])
            )
            self.assertTrue(
                all(
                    "evidence binding failed" in check["error"]
                    for check in candidate_a["external_checks"]
                )
            )

    def test_skybot_clear_at_unrelated_epoch_cannot_open_gate(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            input_path = root / "photometry.csv"
            self._write_input(input_path)
            config = _config(root / "state")
            ledger = OutcomeLedger(root / "state" / "ledger.sqlite")
            initial = analyze_csv(input_path, config, output_dir=root / "runs", ledger=ledger)
            initial_records = json.loads(initial.candidates_path.read_text(encoding="utf-8"))
            initial_version = next(
                item["candidate_version"]
                for item in initial_records["candidates"]
                if item["candidate_id"] == "A"
            )
            ledger.add_review(
                "A",
                candidate_version=initial_version,
                reviewer="screen-a",
                role="screener",
                verdict="approve",
                reason="clean",
            )
            ledger.add_review(
                "A",
                candidate_version=initial_version,
                reviewer="review-b",
                role="reviewer",
                verdict="approve",
                reason="verified",
            )

            result = analyze_csv(
                input_path,
                config,
                output_dir=root / "runs",
                ledger=ledger,
                checks_by_candidate={"A": self._clear_checks(config, skybot_mjd=59000.0)},
            )

            records = json.loads(result.candidates_path.read_text(encoding="utf-8"))
            candidate_a = next(
                item for item in records["candidates"] if item["candidate_id"] == "A"
            )
            skybot = next(
                check for check in candidate_a["external_checks"] if check["service"] == "skybot"
            )
            self.assertEqual(skybot["status"], "error")
            self.assertIn("does not cover every candidate reference epoch", skybot["error"])
            self.assertFalse(candidate_a["reportable"])


if __name__ == "__main__":
    unittest.main()
