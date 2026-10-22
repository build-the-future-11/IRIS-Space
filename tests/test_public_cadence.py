"""Input-contract checks only; mutated rows are synthetic parser fixtures."""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from siderea.public_cadence import (
    MAX_BYTES,
    CadenceInputError,
    SourceReceipt,
    build_report,
    ingest_file,
    load_source,
    main,
)

fits = pytest.importorskip("astropy.io.fits", reason="public cadence requires the astronomy extra")
FIXTURE = Path(__file__).parent / "fixtures" / "public_cadence"
RAW = FIXTURE / "tess-pimen-100.fits"
SOURCE = SourceReceipt.from_dict(json.loads((FIXTURE / "source.json").read_text()))


def mutated(change):
    """Label parser-only mutations; never reuse the public source's receipt."""
    with fits.open(RAW, memmap=False) as hdus:
        hdus[1].data = hdus[1].data[:6].copy()
        change(hdus)
        stream = io.BytesIO()
        hdus.writeto(stream, checksum=True)
    raw = stream.getvalue()
    source = replace(
        SOURCE,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        source_id="siderea:synthetic-parser-fixture",
        source_kind="synthetic_parser_fixture",
        source_revision="test-only mutation of pinned Lightkurve fixture",
    )
    return raw, source


def test_pinned_public_fixture_is_exact_and_input_only():
    raw = RAW.read_bytes()
    assert len(raw) == 40320
    assert hashlib.sha256(raw).hexdigest() == SOURCE.raw_sha256
    assert hashlib.sha1(b"blob 40320\0" + raw).hexdigest() == (
        "0381f5bd0628fdf9047547383996463a0423a19b"
    )
    report = build_report(raw, SOURCE)
    assert report["counts"] == {"input": 100, "accepted": 100, "rejected": 0}
    assert report["dataset_id"] == "tess:261136679:1:4:2"
    assert report["input_only"] is True
    assert report["scientific_execution_authorized"] is False
    assert report["cross_file_assembly_performed"] is False
    assert report["time"]["TIMESYS"] == "TDB"
    assert report["time"]["TIMEREF"] == "SOLARSYSTEM"
    assert report["time"]["BJDREFI"] == 2457000
    assert report["time"]["conversion_performed"] is False
    assert {row["source_row"] for row in report["accepted"]} == set(range(1, 101))
    assert len({row["row_id"] for row in report["accepted"]}) == 100
    assert all(
        set(row) == {"row_id", "source_row", "btjd_tdb_days", "cadence_number", "quality_bitmask"}
        for row in report["accepted"]
    )
    assert report == build_report(raw, SOURCE)
    # Reader must preserve values and flags, including native time precision.
    with fits.open(RAW) as hdus:
        assert [row["btjd_tdb_days"] for row in report["accepted"]] == list(hdus[1].data["TIME"])
        assert [row["quality_bitmask"] for row in report["accepted"]] == list(
            hdus[1].data["QUALITY"]
        )


@pytest.mark.parametrize(
    ("column", "value", "reason"),
    [
        ("TIME", float("nan"), "missing_time"),
        ("TIME", float("inf"), "non_finite_time"),
        ("CADENCENO", -1, "invalid_cadence_number"),
        ("QUALITY", -1, "invalid_quality_bitmask"),
    ],
)
def test_malformed_rows_are_quarantined_without_imputation(column, value, reason):
    raw, source = mutated(lambda hdus: hdus[1].data[column].__setitem__(2, value))
    report = build_report(raw, source)
    assert report["counts"] == {"input": 6, "accepted": 5, "rejected": 1}
    assert report["quarantine"] == [{"source_row": 3, "reason": reason}]
    assert report["rejection_reasons"] == {reason: 1}
    assert 3 not in {row["source_row"] for row in report["accepted"]}
    json.dumps(report, allow_nan=False)


def test_nonzero_quality_flag_is_preserved_without_selection():
    raw, source = mutated(lambda hdus: hdus[1].data["QUALITY"].__setitem__(0, 128))
    report = build_report(raw, source)
    assert report["counts"]["accepted"] == 6
    assert report["accepted"][0]["quality_bitmask"] == 128


def test_duplicate_cadence_retains_first_raw_row():
    def change(hdus):
        hdus[1].data[1] = hdus[1].data[0]

    raw, source = mutated(change)
    report = build_report(raw, source)
    assert report["counts"] == {"input": 6, "accepted": 5, "rejected": 1}
    assert report["accepted"][0]["source_row"] == 1
    assert report["quarantine"] == [
        {
            "source_row": 2,
            "row_id": report["accepted"][0]["row_id"],
            "reason": "duplicate_cadence",
        }
    ]


@pytest.mark.parametrize("reverse", [False, True])
def test_conflicting_cadence_quarantines_all_versions(reverse):
    def change(hdus):
        hdus[1].data["CADENCENO"][1] = hdus[1].data["CADENCENO"][0]
        if reverse:
            hdus[1].data = hdus[1].data[::-1].copy()

    raw, source = mutated(change)
    report = build_report(raw, source)
    assert report["counts"] == {"input": 6, "accepted": 4, "rejected": 2}
    assert report["rejection_reasons"] == {"conflicting_cadence": 2}
    rejected_id = report["quarantine"][0]["row_id"]
    assert all(row["row_id"] == rejected_id for row in report["quarantine"])
    assert rejected_id not in {row["row_id"] for row in report["accepted"]}


@pytest.mark.parametrize(
    ("hdu", "key", "value"),
    [
        (0, "DATA_REL", 41),
        (0, "FILEVER", "2.0"),
        (0, "TICID", 1),
        (0, "OBJECT", "TIC 1"),
        (0, "SECTOR", 2),
        (0, "CAMERA", 1),
        (1, "TICID", 1),
        (1, "TIMESYS", "UTC"),
        (1, "TIMEREF", "LOCAL"),
        (1, "TIMEUNIT", "s"),
        (1, "BJDREFI", 2454833),
        (1, "BJDREFF", 0.5),
        (1, "TIMEPIXR", 0.0),
        (1, "TIMEDEL", -1.0),
        (1, "TNULL3", -999),
        (1, "TSCAL1", 2.0),
    ],
)
def test_changed_header_or_encoding_fails_closed_despite_matching_new_hash(hdu, key, value):
    raw, source = mutated(lambda hdus: hdus[hdu].header.__setitem__(key, value))
    with pytest.raises(CadenceInputError) as error:
        build_report(raw, source)
    assert error.value.code == "schema_drift"


@pytest.mark.parametrize(
    "mode", ["missing_time", "duplicate_time", "duplicate_unit", "renamed_column", "wrong_unit"]
)
def test_schema_drift_does_not_silently_reinterpret_source(mode):
    def change(hdus):
        header = hdus[1].header
        if mode == "missing_time":
            del header["TIMESYS"]
        elif mode == "duplicate_time":
            header.append(("TIMESYS", "TDB"))
        elif mode == "duplicate_unit":
            header.append(("TUNIT1", "BJD - 2457000, days"))
        elif mode == "renamed_column":
            hdus[1].columns.change_name("CADENCENO", "OTHER_ID")
        else:
            hdus[1].columns[0].unit = "s"

    raw, source = mutated(change)
    with pytest.raises(CadenceInputError) as error:
        build_report(raw, source)
    assert error.value.code == "schema_drift"


def test_hash_change_is_rejected_before_fits_parse():
    with pytest.raises(CadenceInputError) as error:
        build_report(b"not FITS", SOURCE)
    assert error.value.code == "source_hash_mismatch"


@pytest.mark.parametrize("raw", [b"not FITS", b"", b"SIMPLE  =" + b" " * 80])
def test_malformed_whole_file_is_not_repaired(raw):
    with pytest.raises(CadenceInputError) as error:
        build_report(raw, replace(SOURCE, raw_sha256=hashlib.sha256(raw).hexdigest()))
    assert error.value.code == "invalid_fits"


def test_input_size_cap_precedes_parsing():
    with pytest.raises(CadenceInputError) as error:
        build_report(b" " * (MAX_BYTES + 1), SOURCE)
    assert error.value.code == "input_too_large"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 2),
        ("schema_version", True),
        ("tic_id", True),
        ("camera", 5),
        ("source_kind", "qualified"),
        ("source_id", ""),
        ("raw_sha256", "A" * 64),
        ("source_uri", "http://example.org/source.fits"),
        ("source_uri", "https://name:secret@example.org/source.fits"),
        ("retrieved_at_utc", "2026-10-08T12:00:00+05:30"),
        ("retrieved_at_utc", "2026-02-30T12:00:00Z"),
    ],
)
def test_receipt_identity_has_no_guessed_defaults(field, value):
    receipt = {**asdict(SOURCE), field: value}
    with pytest.raises(CadenceInputError) as error:
        SourceReceipt.from_dict(receipt)
    assert error.value.code == "invalid_source_receipt"


@pytest.mark.parametrize("extra", [False, True])
def test_receipt_field_set_is_versioned(extra):
    receipt = asdict(SOURCE)
    if extra:
        receipt["scientific_execution_authorized"] = True
    else:
        del receipt["source_revision"]
    with pytest.raises(CadenceInputError) as error:
        SourceReceipt.from_dict(receipt)
    assert error.value.code == "invalid_source_receipt"


def test_replay_reuses_exact_artifact_without_rewrite(tmp_path):
    first = ingest_file(RAW, SOURCE, tmp_path)
    path = Path(first["artifact"])
    before = path.read_bytes(), path.stat().st_mtime_ns
    second = ingest_file(RAW, SOURCE, tmp_path)
    assert first["status"] == "created" and first["new_artifacts"] == 1
    assert second["status"] == "reused" and second["new_artifacts"] == 0
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert list(tmp_path.iterdir()) == [path]


def test_concurrent_replays_publish_one_complete_artifact(tmp_path):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: ingest_file(RAW, SOURCE, tmp_path), range(2)))
    assert sum(result["new_artifacts"] for result in results) == 1
    paths = list(tmp_path.iterdir())
    assert len(paths) == 1
    assert json.loads(paths[0].read_bytes())["counts"]["input"] == 100


@pytest.mark.parametrize(
    "existing", ["changed_report", "changed_receipt", "directory", "symlink", "dangling_symlink"]
)
def test_existing_artifact_conflicts_never_overwrite(tmp_path, existing):
    destination = tmp_path / "reports"
    destination.mkdir()
    artifact = destination / f"{SOURCE.raw_sha256}.json"
    source = SOURCE
    if existing == "changed_report":
        artifact.write_text("existing user data")
    elif existing == "changed_receipt":
        ingest_file(RAW, SOURCE, destination)
        source = replace(SOURCE, source_revision="another unverified retrieval")
    elif existing == "directory":
        artifact.mkdir()
    else:
        target = tmp_path / "target"
        if existing == "symlink":
            target.write_text("preserve me")
        artifact.symlink_to(target)
    before = artifact.read_bytes() if artifact.is_file() else None
    with pytest.raises(CadenceInputError) as error:
        ingest_file(RAW, source, destination)
    assert error.value.code == "artifact_conflict"
    assert list(destination.iterdir()) == [artifact]
    if before is not None:
        assert artifact.read_bytes() == before
    if existing.endswith("symlink"):
        assert artifact.is_symlink()


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipe check")
def test_nonregular_artifact_does_not_block_or_count_as_replay(tmp_path):
    artifact = tmp_path / f"{SOURCE.raw_sha256}.json"
    os.mkfifo(artifact)
    with pytest.raises(CadenceInputError) as error:
        ingest_file(RAW, SOURCE, tmp_path)
    assert error.value.code == "artifact_conflict"


def test_cli_returns_machine_readable_creation_replay_and_rejection(tmp_path, capsys):
    args = [str(RAW), "--source", str(FIXTURE / "source.json"), "--output-dir", str(tmp_path)]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["new_artifacts"] == 1
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["new_artifacts"] == 0
    assert main([str(tmp_path / "missing"), *args[1:]]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "local_input_error"


def test_duplicate_receipt_keys_are_rejected_before_identity_is_discarded(tmp_path):
    receipt = tmp_path / "ambiguous.json"
    receipt.write_text('{"tic_id": 999, ' + json.dumps(asdict(SOURCE))[1:])
    with pytest.raises(CadenceInputError) as error:
        load_source(receipt)
    assert error.value.code == "invalid_source_receipt"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipe check")
@pytest.mark.parametrize("role", ["raw", "receipt"])
def test_special_input_files_are_rejected_without_blocking(tmp_path, role):
    path = tmp_path / "pipe"
    os.mkfifo(path)
    with pytest.raises(CadenceInputError) as error:
        if role == "raw":
            ingest_file(path, SOURCE, tmp_path / "reports")
        else:
            load_source(path)
    assert error.value.code == ("local_input_error" if role == "raw" else "invalid_source_receipt")
    assert not (tmp_path / "reports").exists()


def test_module_import_does_not_load_optional_astronomy_or_research_stack():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import siderea.public_cadence; "
            "assert 'astropy' not in sys.modules; "
            "assert not any(x.startswith('siderea.research') for x in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
    )
    assert result.returncode == 0, result.stderr
