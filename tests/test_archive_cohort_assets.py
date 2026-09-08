from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from threading import Barrier

import pytest
from test_research_qualification import protocol

from siderea.cli import main
from siderea.config import load_config
from siderea.ingest import ingest_csv
from siderea.ingest.snapshot import BROKER_SNAPSHOT_ID_COLUMN, broker_snapshot_id
from siderea.ledger import OutcomeLedger
from siderea.operations.assets import (
    EvidenceAssetSpec,
    create_evidence_asset_bundle,
    verify_evidence_asset_bundle,
)
from siderea.operations.broker_store import BrokerArchive
from siderea.pipeline import analyze_csv
from siderea.provenance import digest_value
from siderea.research.cohort import CohortRegistry, CohortSelection, export_matured_cohort
from siderea.research.preregistration import Preregistration
from siderea.review.assembly import assemble_review_set, verify_review_set


def snapshot(root, index):
    batch = ingest_csv(Path("examples/photometry.csv"))
    metadata = dict(
        source="broker:synthetic-test",
        retrieved_at=f"2026-01-0{index}T00:00:00+00:00",
        provenance={"synthetic": True},
        warnings=[],
    )
    identifier = broker_snapshot_id(**metadata)
    frame = batch.to_frame()
    frame[BROKER_SNAPSHOT_ID_COLUMN] = identifier
    content = frame.to_csv(index=False).encode()
    path = root / f"snapshot-{index}.csv"
    path.write_bytes(content)
    path.with_suffix(".csv.provenance.json").write_text(
        json.dumps(
            {
                "schema": "siderea.broker_snapshot.v1",
                "snapshot_id": identifier,
                "photometry_sha256": sha256(content).hexdigest(),
                **metadata,
            }
        )
    )
    return path


def test_archive_concurrent_watermarks_retry_and_replay(tmp_path):
    archive = BrokerArchive(tmp_path / "archive.sqlite")
    paths = [snapshot(tmp_path, index) for index in (1, 2)]
    barrier = Barrier(2)

    def write(index):
        barrier.wait()
        try:
            return archive.archive_snapshot(
                paths[index - 1], stream="test", cursor=str(index), watermark_mjd=float(index)
            )
        except ValueError as exc:
            assert "backwards" in str(exc)
            return None

    with ThreadPoolExecutor(2) as pool:
        records = list(pool.map(write, (1, 2)))
    assert archive.latest_cursor("test")["watermark_mjd"] == 2
    for index, record in enumerate(records, start=1):
        if record is not None:
            assert (
                archive.archive_snapshot(
                    paths[index - 1], stream="test", cursor=str(index), watermark_mjd=float(index)
                )
                == record
            )
    assert archive.latest_cursor("test")["watermark_mjd"] == 2
    current = records[1]
    replayed, sidecar = archive.replay(current.snapshot_id, tmp_path / "replay")
    assert replayed.read_bytes() == paths[1].read_bytes()
    assert sidecar.read_bytes() == paths[1].with_suffix(".csv.provenance.json").read_bytes()
    with pytest.raises(ValueError, match="different facts"):
        archive.archive_snapshot(paths[1], stream="test", cursor="changed", watermark_mjd=3)


def test_review_set_selection_is_bound_replayed_and_preserved_in_cohort(tmp_path, capsys):
    result, records = analysis(tmp_path)
    raw = deepcopy(dict(protocol().protocol))
    raw["selection"]["pipeline_version"] = records[0]["pipeline_version"]
    raw["selection"]["configuration_digest"] = digest_value(records[0]["scientific_config"])
    study = Preregistration.from_protocol(raw, frozen_at="2025-12-01T00:00:00+00:00")
    study_path = tmp_path / "study.json"
    study_path.write_text(json.dumps(study.to_dict()))
    bundle = assemble_review_set(
        result.ranked_candidates_path, result.candidates_path, tmp_path / "review", budget=1
    )
    verified = verify_review_set(bundle.output_dir)
    registry = tmp_path / "enrollments.sqlite"
    assert (
        main(
            [
                "cohort-enroll",
                str(study_path),
                str(result.candidates_path),
                str(registry),
                "--review-set",
                str(bundle.output_dir),
                "--enrolled-at",
                "2026-01-02T00:00:00+00:00",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["selected"] == 1
    enrolled = CohortRegistry(registry).enrollments(study.study_id)
    assert len(enrolled) == len(records)
    assert all(
        row.selection_metadata["review_set_id"] == verified["review_set_id"] for row in enrolled
    )
    selected = next(row for row in enrolled if row.selected)
    assert selected.selection_stratum == selected.selection_metadata["entry"]["selection_route"]
    queue_path = bundle.output_dir / "queue.json"
    queue_path.write_text(queue_path.read_text() + " ")
    with pytest.raises(ValueError, match="content"):
        verify_review_set(bundle.output_dir)


def analysis(tmp_path):
    result = analyze_csv(
        Path("examples/photometry.csv"),
        load_config(),
        output_dir=tmp_path / "runs",
        ledger_path=tmp_path / "ledger.sqlite",
    )
    return result, json.loads(result.candidates_path.read_text())["candidates"]


def test_cohort_batch_rolls_back_registration_and_all_rows_on_failure(tmp_path):
    _, records = analysis(tmp_path)
    raw = protocol().to_dict()["protocol"]
    raw["selection"]["pipeline_version"] = records[0]["pipeline_version"]
    raw["selection"]["configuration_digest"] = digest_value(records[0]["scientific_config"])
    study = Preregistration.from_protocol(raw, frozen_at="2025-12-01T00:00:00+00:00")
    registry = CohortRegistry(tmp_path / "batch.sqlite")
    selections = [CohortSelection(record, True, "main") for record in records]
    with pytest.raises(ValueError, match="budget"):
        registry.enroll_batch(study, selections, enrolled_at="2026-01-02T00:00:00+00:00")
    assert registry.enrollments(study.study_id) == ()
    with registry.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM studies").fetchone()[0] == 0
    selections[1] = CohortSelection(records[1], False, "main")
    enrolled = registry.enroll_batch(study, selections, enrolled_at="2026-01-02T00:00:00+00:00")
    assert len(enrolled) == len(records)
    assert (
        registry.enroll_batch(study, selections, enrolled_at="2026-01-02T00:00:00+00:00")
        == enrolled
    )


def test_cohort_records_capture_mode_budget_and_exact_retry(tmp_path):
    result, records = analysis(tmp_path)
    raw = deepcopy(dict(protocol().protocol))
    raw["selection"]["pipeline_version"] = records[0]["pipeline_version"]
    raw["selection"]["configuration_digest"] = digest_value(records[0]["scientific_config"])
    study = Preregistration.from_protocol(raw, frozen_at="2025-12-01T00:00:00+00:00")
    registry = CohortRegistry(tmp_path / "cohort.sqlite")
    options = dict(selected=True, selection_stratum="test", enrolled_at="2026-01-02T00:00:00+00:00")
    first = registry.enroll(study, records[0], **options)
    assert first.capture_mode == "retrospective_reconstruction" and first.recorded_at
    assert registry.enroll(study, records[0], **options) == first
    with pytest.raises(ValueError, match="budget"):
        registry.enroll(study, records[1], **options)
    exported = export_matured_cohort(
        study,
        registry,
        OutcomeLedger(result.ledger_path),
        tmp_path / "cohort.json",
        as_of="2026-04-01T00:00:00+00:00",
    )
    assert exported["capture_mode"] == "retrospective_reconstruction"
    assert exported["missing_outcome_count"] == 1


def specs(tmp_path, record):
    values = []
    for role in ("science_image", "reference_image", "difference_image", "forced_photometry"):
        path = tmp_path / f"{role}.bin"
        path.write_bytes(b"synthetic integrity test; not a scientific image")
        calibration = (
            {}
            if role != "forced_photometry"
            else dict(
                flux_unit="test-unit",
                calibration_reference="synthetic",
                extraction_method="synthetic",
                position_ra_deg=record["position"]["ra_deg"],
                position_dec_deg=record["position"]["dec_deg"],
            )
        )
        values.append(
            EvidenceAssetSpec(
                role,
                path,
                "application/octet-stream",
                "test",
                "test",
                "2026-01-01T00:00:00+00:00",
                calibration,
            )
        )
    return values


def test_asset_integrity_and_calibration_boundaries(tmp_path):
    _, records = analysis(tmp_path)
    assets = specs(tmp_path, records[0])
    bundle = tmp_path / "bundle"
    created = create_evidence_asset_bundle(bundle, candidate=records[0], assets=assets)
    assert verify_evidence_asset_bundle(bundle) == created
    assets[-1].calibration["position_ra_deg"] = "invalid"
    with pytest.raises(ValueError, match="coordinate"):
        assets[-1].validated()
    stored = bundle / created["assets"][0]["path"]
    stored.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="differs"):
        verify_evidence_asset_bundle(bundle)


def test_assets_reject_foreign_position_and_escaping_symlink(tmp_path):
    _, records = analysis(tmp_path)
    assets = specs(tmp_path, records[0])
    original_ra = assets[-1].calibration["position_ra_deg"]
    assets[-1].calibration["position_ra_deg"] = (original_ra + 1) % 360
    with pytest.raises(ValueError, match="differs"):
        create_evidence_asset_bundle(tmp_path / "foreign", candidate=records[0], assets=assets)
    assets[-1].calibration["position_ra_deg"] = original_ra
    bundle = tmp_path / "bundle"
    created = create_evidence_asset_bundle(bundle, candidate=records[0], assets=assets)
    stored = bundle / created["assets"][0]["path"]
    external = tmp_path / "external.bin"
    external.write_bytes(stored.read_bytes())
    stored.unlink()
    stored.symlink_to(external)
    with pytest.raises(ValueError, match="escapes"):
        verify_evidence_asset_bundle(bundle)
