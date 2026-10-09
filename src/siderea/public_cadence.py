"""Offline, input-only TESS SPOC cadence provenance (contract version 1).

This module deliberately has no dependency on research execution or scoring.
See docs/PUBLIC_CADENCE_SOURCE_CONTRACT.md before adding another source schema.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import stat
import warnings
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from siderea.atomic import atomic_create_binary

ADAPTER_VERSION = "tess-spoc-cadence/1"
REPORT_VERSION = "siderea-public-cadence/1"
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 10_000
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_RECEIPT_BYTES = 64 * 1024

# Ordered (TTYPE, TFORM, TUNIT) signature, read from the pinned public fixture.
# Unused flux/centroid columns are checked structurally, never extracted.
COLUMNS = (
    ("TIME", "D", "BJD - 2457000, days"),
    ("TIMECORR", "E", "d"),
    ("CADENCENO", "J", ""),
    ("SAP_FLUX", "E", "e-/s"),
    ("SAP_FLUX_ERR", "E", "e-/s"),
    ("SAP_BKG", "E", "e-/s"),
    ("SAP_BKG_ERR", "E", "e-/s"),
    ("PDCSAP_FLUX", "E", "e-/s"),
    ("PDCSAP_FLUX_ERR", "E", "e-/s"),
    ("QUALITY", "J", ""),
    ("PSF_CENTR1", "D", "pixel"),
    ("PSF_CENTR1_ERR", "E", "pixel"),
    ("PSF_CENTR2", "D", "pixel"),
    ("PSF_CENTR2_ERR", "E", "pixel"),
    ("MOM_CENTR1", "D", "pixel"),
    ("MOM_CENTR1_ERR", "E", "pixel"),
    ("MOM_CENTR2", "D", "pixel"),
    ("MOM_CENTR2_ERR", "E", "pixel"),
    ("POS_CORR1", "E", "pixels"),
    ("POS_CORR2", "E", "pixels"),
)
PRIMARY = {
    "TELESCOP": "TESS",
    "INSTRUME": "TESS Photometer",
    "ORIGIN": "NASA/Ames",
    "FILEVER": "1.0",
    "DATA_REL": 42,
    "PROCVER": "spoc-5.0.10-20200904",
    "SIMDATA": False,
}
TIME_HEADER = {
    "TIMESYS": "TDB",
    "TIMEREF": "SOLARSYSTEM",
    "TIMEUNIT": "d",
    "BJDREFI": 2457000,
    "BJDREFF": 0.0,
    "TIMEPIXR": 0.5,
}
FIELD_MAPPING = {
    "PRIMARY.TICID,SECTOR,CAMERA,CCD + LIGHTCURVE.CADENCENO": "row_id",
    "LIGHTCURVE.TIME": "btjd_tdb_days (unchanged)",
    "LIGHTCURVE.CADENCENO": "cadence_number (unchanged)",
    "LIGHTCURVE.QUALITY": "quality_bitmask (unchanged; no filtering)",
    "one-based LIGHTCURVE row index": "source_row",
}


class CadenceInputError(ValueError):
    """A stable error code with no best-effort repair of the input."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(detail)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 2048:
        raise CadenceInputError("invalid_source_receipt", f"Invalid {name}")
    return value


def _integer(value: object, name: str, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise CadenceInputError("invalid_source_receipt", f"Invalid {name}")
    return value


@dataclass(frozen=True)
class SourceReceipt:
    """Acquisition metadata supplied before parsing and bound to exact bytes."""

    source_id: str
    source_uri: str
    source_revision: str
    source_kind: str
    retrieved_at_utc: str
    raw_sha256: str
    tic_id: int
    sector: int
    camera: int
    ccd: int
    schema_version: int = 1

    @classmethod
    def from_dict(cls, value: object) -> SourceReceipt:
        if not isinstance(value, dict) or set(value) != set(cls.__dataclass_fields__):
            raise CadenceInputError("invalid_source_receipt", "Receipt fields differ from v1")
        strings = {
            name: _string(value[name], name)
            for name in (
                "source_id",
                "source_uri",
                "source_revision",
                "source_kind",
                "retrieved_at_utc",
                "raw_sha256",
            )
        }
        integers = {
            name: _integer(value[name], name)
            for name in ("tic_id", "sector", "camera", "ccd", "schema_version")
        }
        if integers["schema_version"] != 1 or not (
            1 <= integers["camera"] <= 4 and 1 <= integers["ccd"] <= 4
        ):
            raise CadenceInputError(
                "invalid_source_receipt", "Unsupported receipt version or detector"
            )
        if strings["source_kind"] not in {
            "public_fixture",
            "local_input",
            "synthetic_parser_fixture",
        }:
            raise CadenceInputError("invalid_source_receipt", "Unknown source kind")
        uri = urlsplit(strings["source_uri"])
        if (
            uri.scheme != "https"
            or not uri.hostname
            or uri.username
            or uri.password
            or uri.fragment
        ):
            raise CadenceInputError(
                "invalid_source_receipt", "Source URI must be public HTTPS identity"
            )
        if not re.fullmatch(r"[0-9a-f]{64}", strings["raw_sha256"]):
            raise CadenceInputError("invalid_source_receipt", "Invalid raw SHA-256")
        timestamp = strings["retrieved_at_utc"]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", timestamp):
            raise CadenceInputError("invalid_source_receipt", "UTC retrieval identity is required")
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise CadenceInputError(
                "invalid_source_receipt", "Invalid retrieval timestamp"
            ) from exc
        return cls(**strings, **integers)  # type: ignore[arg-type]


def _header_value(header: Any, key: str) -> object:
    if key not in header or header.count(key) != 1:
        raise CadenceInputError("schema_drift", f"Missing or repeated FITS header {key}")
    return header[key]


def _expect_header(header: Any, expected: dict[str, object]) -> None:
    for key, expected_value in expected.items():
        actual = _header_value(header, key)
        # bool compares equal to integer 1 in Python; reject that ambiguity.
        if actual != expected_value or isinstance(actual, bool) != isinstance(expected_value, bool):
            raise CadenceInputError("schema_drift", f"Unsupported FITS header {key}")


def _require_zero_time_offsets(header: Any) -> None:
    # TIME is emitted unchanged as native BTJD. Neither the FITS time offset
    # nor the legacy TIME-column offset may silently change that meaning.
    # Missing offsets have their zero default; do not infer cancellation.
    for key in ("TIMEZERO", "TIMEOFFS"):
        if key in header:
            value = _header_value(header, key)
            if type(value) not in (int, float) or value != 0:
                raise CadenceInputError(
                    "schema_drift", f"Unsupported nonzero or nonnumeric FITS header {key}"
                )


def _extract(raw: bytes, source: SourceReceipt) -> tuple[list[dict[str, Any]], float]:
    # Lazy optional dependency: importing SIDEREA or this module does not load Astropy.
    try:
        from astropy.io import fits
        from astropy.io.fits.verify import VerifyWarning
    except ImportError as exc:
        raise CadenceInputError(
            "missing_astropy", "Install the astronomy extra or astropy>=6"
        ) from exc

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", VerifyWarning)
            with fits.open(io.BytesIO(raw), memmap=False, lazy_load_hdus=False) as hdus:
                hdus.verify("exception")
                if len(hdus) != 3 or not isinstance(hdus[1], fits.BinTableHDU):
                    raise CadenceInputError("schema_drift", "Expected the three-HDU SPOC product")
                primary, table = hdus[0], hdus[1]
                _expect_header(primary.header, PRIMARY)
                _expect_header(
                    primary.header,
                    {
                        "TICID": source.tic_id,
                        "SECTOR": source.sector,
                        "CAMERA": source.camera,
                        "CCD": source.ccd,
                        "OBJECT": f"TIC {source.tic_id}",
                    },
                )
                _expect_header(
                    table.header,
                    {
                        **TIME_HEADER,
                        "EXTNAME": "LIGHTCURVE",
                        "TELESCOP": "TESS",
                        "TICID": source.tic_id,
                        "OBJECT": f"TIC {source.tic_id}",
                    },
                )
                _require_zero_time_offsets(table.header)
                if (
                    tuple(
                        (column.name, str(column.format), column.unit or "")
                        for column in table.columns
                    )
                    != COLUMNS
                ):
                    raise CadenceInputError("schema_drift", "FITS column signature changed")
                for index, column in enumerate(table.columns, start=1):
                    if any(
                        value is not None
                        for value in (
                            column.bscale,
                            column.bzero,
                            column.null,
                            column.dim,
                        )
                    ):
                        raise CadenceInputError("schema_drift", "Unsupported column encoding")
                    for key in (f"TTYPE{index}", f"TFORM{index}"):
                        _header_value(table.header, key)
                    if f"TUNIT{index}" in table.header:
                        _header_value(table.header, f"TUNIT{index}")
                for hdu in hdus:
                    if hdu.verify_checksum() != 1 or hdu.verify_datasum() != 1:
                        raise CadenceInputError(
                            "invalid_fits_checksum", "FITS checksum missing or invalid"
                        )
                interval = _header_value(table.header, "TIMEDEL")
                if not isinstance(interval, (float, int)) or isinstance(interval, bool):
                    raise CadenceInputError("schema_drift", "TIMEDEL is not numeric")
                cadence_interval = float(interval)
                if not math.isfinite(cadence_interval) or cadence_interval <= 0:
                    raise CadenceInputError("schema_drift", "TIMEDEL is not positive and finite")
                nrows = _header_value(table.header, "NAXIS2")
                if type(nrows) is not int or not 0 <= nrows <= MAX_ROWS:
                    raise CadenceInputError("input_too_large", "Invalid or excessive row count")
                # Do not read fluxes or infer coordinates from the fixture's label.
                rows = [
                    {
                        "source_row": index + 1,
                        "btjd_tdb_days": float(time),
                        "cadence_number": int(cadence),
                        "quality_bitmask": int(quality),
                    }
                    for index, (time, cadence, quality) in enumerate(
                        zip(
                            table.data["TIME"],
                            table.data["CADENCENO"],
                            table.data["QUALITY"],
                            strict=True,
                        )
                    )
                ]
                return rows, cadence_interval
    except CadenceInputError:
        raise
    except (OSError, ValueError, TypeError, KeyError, VerifyWarning) as exc:
        raise CadenceInputError("invalid_fits", "FITS could not be parsed without repair") from exc


def build_report(raw: bytes, source: SourceReceipt) -> dict[str, Any]:
    """Validate one local source and return deterministic input-only evidence."""
    source = SourceReceipt.from_dict(asdict(source))
    if len(raw) > MAX_BYTES:
        raise CadenceInputError("input_too_large", "Input exceeds the 2 MiB contract")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != source.raw_sha256:
        raise CadenceInputError(
            "source_hash_mismatch", "Raw bytes differ from the acquisition receipt"
        )
    rows, cadence_interval = _extract(raw, source)
    quarantine: list[dict[str, Any]] = []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    prefix = f"tess:{source.tic_id}:{source.sector}:{source.camera}:{source.ccd}"
    for row in rows:
        reason = None
        if math.isnan(row["btjd_tdb_days"]):
            reason = "missing_time"
        elif not math.isfinite(row["btjd_tdb_days"]):
            reason = "non_finite_time"
        elif row["cadence_number"] < 0:
            reason = "invalid_cadence_number"
        elif row["quality_bitmask"] < 0:
            reason = "invalid_quality_bitmask"
        if reason:
            quarantine.append({"source_row": row["source_row"], "reason": reason})
            continue
        row["row_id"] = f"{prefix}:{row['cadence_number']}"
        groups[row["row_id"]].append(row)

    accepted = []
    for row_id, group in sorted(groups.items()):
        values = {(row["btjd_tdb_days"], row["quality_bitmask"]) for row in group}
        if len(values) > 1:
            quarantine.extend(
                {"source_row": row["source_row"], "row_id": row_id, "reason": "conflicting_cadence"}
                for row in group
            )
        else:
            accepted.append(group[0])
            quarantine.extend(
                {"source_row": row["source_row"], "row_id": row_id, "reason": "duplicate_cadence"}
                for row in group[1:]
            )
    accepted.sort(key=lambda row: (row["cadence_number"], row["source_row"]))
    quarantine.sort(key=lambda row: row["source_row"])
    source_record = asdict(source)
    return {
        "schema_version": REPORT_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "input_only": True,
        "scientific_execution_authorized": False,
        "source": source_record,
        "source_receipt_sha256": hashlib.sha256(_json_bytes(source_record)).hexdigest(),
        "raw_size_bytes": len(raw),
        "dataset_id": prefix,
        "time": {**TIME_HEADER, "TIMEDEL": cadence_interval, "conversion_performed": False},
        "raw_to_clean": dict(FIELD_MAPPING),
        "counts": {"input": len(rows), "accepted": len(accepted), "rejected": len(quarantine)},
        "rejection_reasons": dict(sorted(Counter(row["reason"] for row in quarantine).items())),
        "cross_file_assembly_performed": False,
        "accepted": accepted,
        "quarantine": quarantine,
    }


def _read_regular(path: Path, limit: int, error_code: str) -> bytes:
    """Bound local reads and reject special files without blocking on a FIFO."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if path.is_symlink():
        raise CadenceInputError(error_code, "The requested path is a symlink")
    try:
        descriptor = os.open(path, flags)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise CadenceInputError(error_code, "The requested path is not a regular file")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                return handle.read(limit + 1)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise CadenceInputError(error_code, "The requested local file cannot be read") from exc


def _verify_replay(path: Path, expected: bytes) -> None:
    if _read_regular(path, MAX_REPORT_BYTES, "artifact_conflict") != expected:
        raise CadenceInputError("artifact_conflict", "Existing artifact differs; no overwrite")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CadenceInputError("invalid_source_receipt", f"Repeated receipt field {key}")
        result[key] = value
    return result


def load_source(path: Path) -> SourceReceipt:
    raw = _read_regular(path, MAX_RECEIPT_BYTES, "invalid_source_receipt")
    if len(raw) > MAX_RECEIPT_BYTES:
        raise CadenceInputError("invalid_source_receipt", "Receipt exceeds the size limit")
    try:
        decoded = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CadenceInputError(
            "invalid_source_receipt", "Receipt is not valid UTF-8 JSON"
        ) from exc
    return SourceReceipt.from_dict(decoded)


def ingest_file(raw_path: Path, source: SourceReceipt, output_dir: Path) -> dict[str, Any]:
    """Publish one immutable report; an exact replay creates no new artifact."""
    raw = _read_regular(raw_path, MAX_BYTES, "local_input_error")
    report = build_report(raw, source)
    encoded = _json_bytes(report)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{source.raw_sha256}.json"
    created = True
    try:
        atomic_create_binary(path, lambda handle: handle.write(encoded))
    except FileExistsError:
        _verify_replay(path, encoded)
        created = False
    return {
        "status": "created" if created else "reused",
        "artifact": str(path),
        "source_id": source.source_id,
        "raw_sha256": source.raw_sha256,
        "counts": report["counts"],
        "new_artifacts": int(created),
        "scientific_execution_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path)
    parser.add_argument(
        "--source", type=Path, required=True, help="Pre-bound acquisition receipt JSON"
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        source = load_source(args.source)
        result = ingest_file(args.raw, source, args.output_dir)
    except (CadenceInputError, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, CadenceInputError) else "local_input_error"
        print(json.dumps({"status": "rejected", "reason": code, "detail": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
