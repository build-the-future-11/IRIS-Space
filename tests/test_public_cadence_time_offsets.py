"""Artificial FITS time-header admission checks; no model or science execution."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from siderea.public_cadence import CadenceInputError, SourceReceipt, build_report
from siderea.public_cadence import main as source_main
from siderea.public_cadence_cohort import build_cohort
from siderea.public_cadence_cohort import main as cohort_main

fits = pytest.importorskip("astropy.io.fits", reason="public cadence requires astronomy extra")
FIXTURE = Path(__file__).parent / "fixtures" / "public_cadence"
RAW = (FIXTURE / "tess-pimen-100.fits").read_bytes()
SOURCE = SourceReceipt.from_dict(json.loads((FIXTURE / "source.json").read_text()))


def artificial_offsets(cards):
    """Recompute FITS checksums and receipt identity for a labelled artificial input."""
    with fits.open(io.BytesIO(RAW), memmap=False) as hdus:
        hdus[1].data = hdus[1].data[:6].copy()
        for key, value in cards:
            hdus[1].header.append((key, value))
        stream = io.BytesIO()
        hdus.writeto(stream, checksum=True)
    raw = stream.getvalue()
    return raw, replace(
        SOURCE,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        source_kind="synthetic_parser_fixture",
        source_id="siderea:artificial-time-offset-contract",
        source_revision="test-only header mutation of pinned Lightkurve fixture",
    )


def assert_schema_rejected(raw, source):
    with pytest.raises(CadenceInputError) as caught:
        build_report(raw, source)
    assert caught.value.code == "schema_drift"


@pytest.mark.parametrize("key", ["TIMEZERO", "TIMEOFFS"])
@pytest.mark.parametrize("value", [1.0, -0.5, 1e-12])
def test_nonzero_time_offsets_cannot_be_silently_ignored(key, value):
    assert_schema_rejected(*artificial_offsets([(key, value)]))


@pytest.mark.parametrize("key", ["TIMEZERO", "TIMEOFFS"])
@pytest.mark.parametrize("value", [False, True, "0", None])
def test_ambiguous_time_offset_types_are_not_numeric_zero(key, value):
    assert_schema_rejected(*artificial_offsets([(key, value)]))


@pytest.mark.parametrize("key", ["TIMEZERO", "TIMEOFFS"])
@pytest.mark.parametrize("values", [(0.0, 0.0), (0.0, 1.0)])
def test_repeated_time_offset_cards_are_rejected(key, values):
    assert_schema_rejected(*artificial_offsets([(key, value) for value in values]))


@pytest.mark.parametrize("key", ["TIMEZERO", "TIMEOFFS"])
@pytest.mark.parametrize("zero", [0, 0.0, -0.0])
def test_one_explicit_numeric_zero_preserves_native_rows(key, zero):
    baseline = build_report(*artificial_offsets([]))
    report = build_report(*artificial_offsets([(key, zero)]))
    assert report["accepted"] == baseline["accepted"]
    assert report["time"] == baseline["time"]
    assert report["counts"] == {"input": 6, "accepted": 6, "rejected": 0}
    assert report["scientific_execution_authorized"] is False


def test_both_explicit_numeric_zero_offsets_preserve_native_rows():
    baseline = build_report(*artificial_offsets([]))
    report = build_report(*artificial_offsets([("TIMEZERO", 0), ("TIMEOFFS", 0.0)]))
    assert report["accepted"] == baseline["accepted"]
    assert report["time"] == baseline["time"]


def test_distinct_nonzero_offsets_are_not_assumed_to_cancel():
    assert_schema_rejected(*artificial_offsets([("TIMEZERO", 1.0), ("TIMEOFFS", -1.0)]))


@pytest.mark.parametrize("key", ["TIMEZERO", "TIMEOFFS"])
def test_shifted_overlapping_source_cannot_enter_cohort_as_identical(key):
    shifted = artificial_offsets([(key, 1.0)])
    with pytest.raises(CadenceInputError) as caught:
        build_cohort([(RAW, SOURCE), shifted])
    assert caught.value.code == "schema_drift"


@pytest.mark.parametrize("key", ["TIMEZERO", "TIMEOFFS"])
@pytest.mark.parametrize("entry_point", ["source", "cohort"])
def test_cli_rejects_offset_input_before_publishing(tmp_path, capsys, key, entry_point):
    raw, source = artificial_offsets([(key, 1.0)])
    raw_path = tmp_path / "artificial.fits"
    receipt_path = tmp_path / "artificial.json"
    output = tmp_path / "outputs"
    raw_path.write_bytes(raw)
    receipt_path.write_text(json.dumps(asdict(source)))
    receipt_before = receipt_path.read_bytes()
    if entry_point == "source":
        status = source_main(
            [str(raw_path), "--source", str(receipt_path), "--output-dir", str(output)]
        )
    else:
        status = cohort_main(
            ["--input", str(raw_path), str(receipt_path), "--output-dir", str(output)]
        )
    assert status == 2
    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "rejected"
    assert response["reason"] == "schema_drift"
    assert not output.exists()
    assert raw_path.read_bytes() == raw
    assert receipt_path.read_bytes() == receipt_before
