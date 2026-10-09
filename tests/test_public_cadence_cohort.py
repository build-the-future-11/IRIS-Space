"""Public fixture plus labelled synthetic overlap cases; no scientific outcomes."""

from __future__ import annotations

import hashlib
import io
import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from siderea import public_cadence_cohort as cohort
from siderea.public_cadence import ADAPTER_VERSION, REPORT_VERSION, CadenceInputError, SourceReceipt

fits = pytest.importorskip("astropy.io.fits", reason="public cadence requires Astropy")
FIXTURE = Path(__file__).parent / "fixtures" / "public_cadence"
RAW = FIXTURE / "tess-pimen-100.fits"
RECEIPT = FIXTURE / "source.json"
SOURCE = SourceReceipt.from_dict(json.loads(RECEIPT.read_text()))
PUBLIC = (RAW.read_bytes(), SOURCE)


def artificial(change=lambda _hdus: None, selection=slice(0, 6), **source_changes):
    with fits.open(RAW, memmap=False) as hdus:
        hdus[1].data = hdus[1].data[selection].copy()
        change(hdus)
        stream = io.BytesIO()
        hdus.writeto(stream, checksum=True)
    raw = stream.getvalue()
    source = replace(
        SOURCE,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        source_id="siderea:synthetic-cohort-parser-fixture",
        source_kind="synthetic_parser_fixture",
        source_revision="cohort-only mutation of pinned Lightkurve fixture",
        **source_changes,
    )
    return raw, source


def local_pair(tmp_path, value, name="input"):
    raw, source = value
    raw_path, receipt_path = tmp_path / f"{name}.fits", tmp_path / f"{name}.json"
    raw_path.write_bytes(raw)
    receipt_path.write_text(json.dumps(asdict(source)))
    return raw_path, receipt_path


def assert_conservation(report):
    representatives = [row["representative"] for row in report["accepted"]]
    quarantined = [row["source"] for row in report["quarantine"]]
    actual = [(ref["raw_sha256"], ref["source_row"]) for ref in representatives + quarantined]
    expected = {
        (source["source"]["raw_sha256"], index)
        for source in report["sources"]
        for index in range(1, source["counts_before_assembly"]["input"] + 1)
    }
    assert len(actual) == len(set(actual)) == len(expected)
    assert set(actual) == expected
    assert len(actual) == report["counts"]["input_rows_across_distinct_sources"]


def test_pinned_input_is_native_input_only_and_every_raw_row_is_accounted_for():
    report = cohort.build_cohort([PUBLIC])
    assert report["counts"] == {
        "distinct_raw_sources": 1,
        "input_rows_across_distinct_sources": 100,
        "accepted_unique_cadence_identities": 100,
        "quarantined_source_rows": 0,
        "duplicate_source_rows": 0,
        "overlapping_cadence_identities": 0,
        "conflicting_cadence_identities": 0,
    }
    assert report["input_only"] is True
    assert report["scientific_execution_authorized"] is False
    assert report["time"]["TIMESYS"] == "TDB"
    assert report["time"]["BJDREFI"] == 2457000
    assert report["time"]["conversion_performed"] is False
    assert report["identity"] == {
        "cohort_schema_version": cohort.COHORT_VERSION,
        "source_report_schema_version": REPORT_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "raw_sha256": [SOURCE.raw_sha256],
    }
    assert all(
        set(row)
        == {
            "row_id",
            "cadence_number",
            "btjd_tdb_days",
            "quality_bitmask",
            "time_interval_days",
            "representative",
            "provenance",
        }
        for row in report["accepted"]
    )
    with fits.open(RAW, memmap=False) as hdus:
        by_cadence = {row["cadence_number"]: row for row in report["accepted"]}
        for row in hdus[1].data:
            assert by_cadence[int(row["CADENCENO"])]["btjd_tdb_days"] == float(row["TIME"])
    assert_conservation(report)


def test_exact_source_duplicates_do_not_inflate_rows_or_change_cohort_identity():
    one = cohort.build_cohort([PUBLIC])
    repeated = cohort.build_cohort([PUBLIC, PUBLIC, PUBLIC])
    assert repeated == one
    assert all(len(row["provenance"]) == 1 for row in repeated["accepted"])


def test_input_order_does_not_change_bytes_and_disjoint_inputs_do_not_overlap():
    first, second = artificial(), artificial(selection=slice(6, 12))
    forward = cohort.build_cohort([first, second])
    assert cohort.build_cohort([second, first]) == forward
    assert forward["counts"]["accepted_unique_cadence_identities"] == 12
    assert forward["counts"]["quarantined_source_rows"] == 0
    assert_conservation(forward)


def test_overlapping_files_keep_one_identity_and_all_input_provenance():
    subset = artificial()
    report = cohort.build_cohort([PUBLIC, subset])
    assert report["counts"]["input_rows_across_distinct_sources"] == 106
    assert report["counts"]["accepted_unique_cadence_identities"] == 100
    assert report["counts"]["duplicate_source_rows"] == 6
    assert report["counts"]["overlapping_cadence_identities"] == 6
    shared = [row for row in report["accepted"] if len(row["provenance"]) == 2]
    assert len(shared) == 6
    for row in shared:
        assert {ref["raw_sha256"] for ref in row["provenance"]} == {
            SOURCE.raw_sha256,
            subset[1].raw_sha256,
        }
        assert row["representative"] == min(
            row["provenance"], key=lambda ref: (ref["raw_sha256"], ref["source_row"])
        )
    assert_conservation(report)


@pytest.mark.parametrize("field,expected_conflicts", [("TIME", 1), ("QUALITY", 1), ("TIMEDEL", 6)])
def test_native_value_or_exposure_conflict_quarantines_the_whole_identity(
    field, expected_conflicts
):
    def change(hdus):
        if field == "TIMEDEL":
            hdus[1].header["TIMEDEL"] *= 2
        else:
            hdus[1].data[field][0] += 1

    conflicting = artificial(change)
    report = cohort.build_cohort([PUBLIC, conflicting])
    assert report["counts"]["conflicting_cadence_identities"] == expected_conflicts
    assert report["counts"]["accepted_unique_cadence_identities"] == 100 - expected_conflicts
    assert report["quarantine_reasons"]["conflicting_cadence"] == 2 * expected_conflicts
    excluded = {
        row["row_id"] for row in report["quarantine"] if row["reason"] == "conflicting_cadence"
    }
    assert excluded.isdisjoint(row["row_id"] for row in report["accepted"])
    assert_conservation(report)


def test_a_conflict_already_quarantined_within_one_source_cannot_be_revived():
    def change(hdus):
        hdus[1].data["CADENCENO"][1] = hdus[1].data["CADENCENO"][0]

    conflicting = artificial(change)
    report = cohort.build_cohort([conflicting, PUBLIC])
    assert report["counts"]["conflicting_cadence_identities"] == 1
    rejected = [row for row in report["quarantine"] if row["reason"] == "conflicting_cadence"]
    assert len(rejected) == 3
    assert sum(row["source_disposition"] == "conflicting_cadence" for row in rejected) == 2
    assert report["counts"]["accepted_unique_cadence_identities"] == 99
    assert_conservation(report)


def test_within_file_duplicate_keeps_all_references_without_double_counting():
    def change(hdus):
        hdus[1].data[1] = hdus[1].data[0]

    report = cohort.build_cohort([PUBLIC, artificial(change)])
    assert report["counts"]["accepted_unique_cadence_identities"] == 100
    assert report["counts"]["duplicate_source_rows"] == 6
    assert sum(len(row["provenance"]) == 3 for row in report["accepted"]) == 1
    assert_conservation(report)


def test_detector_identity_is_not_dropped_when_cadence_numbers_overlap():
    def change(hdus):
        hdus[0].header["CAMERA"] = 3

    report = cohort.build_cohort([PUBLIC, artificial(change, camera=3)])
    assert report["counts"]["accepted_unique_cadence_identities"] == 106
    assert report["counts"]["overlapping_cadence_identities"] == 0
    assert_conservation(report)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("TIME", float("nan"), "missing_time"),
        ("TIME", float("inf"), "non_finite_time"),
        ("CADENCENO", -1, "invalid_cadence_number"),
        ("QUALITY", -1, "invalid_quality_bitmask"),
    ],
)
def test_malformed_source_rows_keep_original_quarantine_reason(field, value, reason):
    bad = artificial(lambda hdus: hdus[1].data[field].__setitem__(0, value))
    report = cohort.build_cohort([PUBLIC, bad])
    assert report["counts"]["accepted_unique_cadence_identities"] == 100
    assert report["quarantine_reasons"][reason] == 1
    assert report["quarantine_reasons"]["duplicate_cadence"] == 5
    assert_conservation(report)
    json.dumps(report, allow_nan=False)


def test_raw_hash_is_checked_even_for_a_repeated_declared_source():
    with pytest.raises(CadenceInputError, match="Raw bytes differ") as caught:
        cohort.build_cohort([PUBLIC, (PUBLIC[0] + b"changed", SOURCE)])
    assert caught.value.code == "source_hash_mismatch"


def test_same_bytes_with_differing_acquisition_identity_are_rejected():
    changed = replace(SOURCE, retrieved_at_utc="2026-10-09T01:00:00Z")
    with pytest.raises(CadenceInputError) as caught:
        cohort.build_cohort([PUBLIC, (PUBLIC[0], changed)])
    assert caught.value.code == "source_provenance_conflict"


def test_schema_drift_cannot_be_blessed_by_a_new_matching_source_hash():
    changed = artificial(lambda hdus: hdus[1].header.__setitem__("TIMESYS", "UTC"))
    with pytest.raises(CadenceInputError) as caught:
        cohort.build_cohort([PUBLIC, changed])
    assert caught.value.code == "schema_drift"


@pytest.mark.parametrize("count", [0, 17])
def test_request_count_bound_is_enforced_before_parsing(count):
    with pytest.raises(CadenceInputError) as caught:
        cohort.build_cohort([PUBLIC] * count)
    assert caught.value.code == "cohort_too_large"


@pytest.mark.parametrize("limit,value", [("MAX_TOTAL_BYTES", 40319), ("MAX_TOTAL_ROWS", 99)])
def test_aggregate_bounds_are_enforced(monkeypatch, limit, value):
    monkeypatch.setattr(cohort, limit, value)
    with pytest.raises(CadenceInputError) as caught:
        cohort.build_cohort([PUBLIC])
    assert caught.value.code == "cohort_too_large"


def test_literal_schema_versions_are_part_of_the_cohort_identity(monkeypatch):
    before = cohort.build_cohort([PUBLIC])
    monkeypatch.setattr(cohort, "COHORT_VERSION", "siderea-public-cadence-cohort/artificial-test")
    after = cohort.build_cohort([PUBLIC])
    assert after["cohort_sha256"] != before["cohort_sha256"]


def test_cli_reordered_and_repeated_inputs_reuse_one_immutable_artifact(tmp_path, capsys):
    extra = local_pair(tmp_path, artificial())
    output = tmp_path / "cohorts"
    first_args = [
        "--input",
        str(RAW),
        str(RECEIPT),
        "--input",
        *map(str, extra),
        "--output-dir",
        str(output),
    ]
    assert cohort.main(first_args) == 0
    created = json.loads(capsys.readouterr().out)
    path = Path(created["artifact"])
    before = path.read_bytes()
    replay_args = [
        "--input",
        *map(str, extra),
        "--input",
        str(RAW),
        str(RECEIPT),
        "--input",
        str(RAW),
        str(RECEIPT),
        "--output-dir",
        str(output),
    ]
    assert cohort.main(replay_args) == 0
    replay = json.loads(capsys.readouterr().out)
    assert created["new_artifacts"] == 1
    assert replay["new_artifacts"] == 0
    assert replay["repeated_source_pairs"] == 1
    assert replay["cohort_sha256"] == created["cohort_sha256"]
    assert replay["counts"]["accepted_unique_cadence_identities"] == 100
    assert path.read_bytes() == before
    assert list(output.iterdir()) == [path]


def test_later_provenance_change_cannot_reuse_or_overwrite_accepted_cohort(tmp_path):
    output = tmp_path / "cohorts"
    first = cohort.ingest_cohort([(RAW, RECEIPT)], output)
    path = Path(first["artifact"])
    before = path.read_bytes()
    altered = local_pair(
        tmp_path, (PUBLIC[0], replace(SOURCE, source_revision="changed acquisition"))
    )
    with pytest.raises(CadenceInputError) as caught:
        cohort.ingest_cohort([altered], output)
    assert caught.value.code == "artifact_conflict"
    assert path.read_bytes() == before
    assert list(output.iterdir()) == [path]


def test_mutated_existing_artifact_is_preserved_and_rejected(tmp_path):
    output = tmp_path / "cohorts"
    first = cohort.ingest_cohort([(RAW, RECEIPT)], output)
    path = Path(first["artifact"])
    sentinel = b"existing conflicting record\n"
    path.write_bytes(sentinel)
    with pytest.raises(CadenceInputError) as caught:
        cohort.ingest_cohort([(RAW, RECEIPT)], output)
    assert caught.value.code == "artifact_conflict"
    assert path.read_bytes() == sentinel


def test_invalid_input_does_not_create_an_output_directory(tmp_path):
    pair = local_pair(tmp_path, (PUBLIC[0] + b"wrong", SOURCE))
    output = tmp_path / "cohorts"
    with pytest.raises(CadenceInputError):
        cohort.ingest_cohort([pair], output)
    assert not output.exists()


def test_oversized_report_does_not_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(cohort, "MAX_COHORT_BYTES", 10)
    output = tmp_path / "cohorts"
    with pytest.raises(CadenceInputError) as caught:
        cohort.ingest_cohort([(RAW, RECEIPT)], output)
    assert caught.value.code == "cohort_too_large"
    assert not output.exists()


@pytest.mark.parametrize("which", ["raw", "receipt", "existing_report"])
def test_symlink_inputs_or_replay_artifacts_are_rejected(tmp_path, which):
    pair = list(local_pair(tmp_path, PUBLIC))
    output = tmp_path / "cohorts"
    if which == "existing_report":
        path = Path(cohort.ingest_cohort([tuple(pair)], output)["artifact"])
    else:
        path = pair[0 if which == "raw" else 1]
    target = path.with_suffix(".preserved")
    path.rename(target)
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    before = target.read_bytes()
    with pytest.raises(CadenceInputError):
        cohort.ingest_cohort([tuple(pair)], output)
    assert path.is_symlink()
    assert target.read_bytes() == before


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO is unavailable")
@pytest.mark.parametrize("which", ["raw", "receipt", "existing_report"])
def test_special_file_inputs_or_replay_artifacts_are_rejected(tmp_path, which):
    pair = list(local_pair(tmp_path, PUBLIC))
    output = tmp_path / "cohorts"
    if which == "existing_report":
        path = Path(cohort.ingest_cohort([tuple(pair)], output)["artifact"])
    else:
        path = pair[0 if which == "raw" else 1]
    path.unlink()
    os.mkfifo(path)
    with pytest.raises(CadenceInputError):
        cohort.ingest_cohort([tuple(pair)], output)
    assert path.exists()


def test_competing_identical_ingestions_create_exactly_one_complete_artifact(tmp_path):
    output = tmp_path / "cohorts"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: cohort.ingest_cohort([(RAW, RECEIPT)], output), range(2)))
    assert sum(result["new_artifacts"] for result in results) == 1
    assert len(list(output.iterdir())) == 1
    assert results[0]["cohort_sha256"] == results[1]["cohort_sha256"]
    assert_conservation(json.loads(Path(results[0]["artifact"]).read_bytes()))
