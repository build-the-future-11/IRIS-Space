"""Offline assembly of already-contracted public cadence inputs, without scoring.

Each source is reparsed from its raw bytes and acquisition receipt. Existing JSON
reports are never trusted as an alternate input. See the versioned cohort contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from siderea.atomic import atomic_create_binary
from siderea.public_cadence import (
    ADAPTER_VERSION,
    MAX_BYTES,
    REPORT_VERSION,
    TIME_HEADER,
    CadenceInputError,
    SourceReceipt,
    _json_bytes,
    _read_regular,
    build_report,
    load_source,
)

COHORT_VERSION = "siderea-public-cadence-cohort/1"
MAX_INPUTS = 16
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_TOTAL_ROWS = 40_000
MAX_COHORT_BYTES = 32 * 1024 * 1024


def _source_ref(digest: str, row: dict[str, Any]) -> dict[str, Any]:
    return {"raw_sha256": digest, "source_row": row["source_row"]}


def _member_key(member: dict[str, Any]) -> tuple[str, int]:
    return member["source"]["raw_sha256"], member["source"]["source_row"]


def _assemble(reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    quarantine: list[dict[str, Any]] = []
    sources = []
    total_rows = 0
    for digest, report in sorted(reports.items()):
        total_rows += report["counts"]["input"]
        if total_rows > MAX_TOTAL_ROWS:
            raise CadenceInputError("cohort_too_large", "Cohort exceeds 40,000 input rows")
        sources.append(
            {
                "source": report["source"],
                "source_receipt_sha256": report["source_receipt_sha256"],
                "source_report_sha256": hashlib.sha256(_json_bytes(report)).hexdigest(),
                "raw_size_bytes": report["raw_size_bytes"],
                "dataset_id": report["dataset_id"],
                "time": report["time"],
                "counts_before_assembly": report["counts"],
                "rejection_reasons_before_assembly": report["rejection_reasons"],
            }
        )
        accepted_by_id = {row["row_id"]: row for row in report["accepted"]}
        for row in report["accepted"]:
            groups[row["row_id"]].append(
                {
                    "source": _source_ref(digest, row),
                    "value": row,
                    "interval": report["time"]["TIMEDEL"],
                    "source_disposition": "accepted",
                }
            )
        for row in report["quarantine"]:
            reason = row["reason"]
            if reason in {"duplicate_cadence", "conflicting_cadence"}:
                # A within-source conflict poisons this identity for the entire
                # cohort. A later source must not revive one of its values.
                groups[row["row_id"]].append(
                    {
                        "source": _source_ref(digest, row),
                        "value": (
                            accepted_by_id[row["row_id"]] if reason == "duplicate_cadence" else None
                        ),
                        "interval": report["time"]["TIMEDEL"],
                        "source_disposition": reason,
                    }
                )
            else:
                # Malformed rows stay quarantined with the source adapter's
                # reason. No missing time or identity is reconstructed here.
                quarantine.append({"source": _source_ref(digest, row), "reason": reason})

    accepted = []
    conflicts = 0
    overlaps = 0
    for row_id, members in sorted(groups.items()):
        members.sort(key=_member_key)
        overlaps += len(members) > 1
        values = {
            (
                member["value"]["btjd_tdb_days"],
                member["value"]["quality_bitmask"],
                member["interval"],
            )
            for member in members
            if member["value"] is not None
        }
        conflict = len(values) != 1 or any(member["value"] is None for member in members)
        if conflict:
            conflicts += 1
            quarantine.extend(
                {
                    "source": member["source"],
                    "row_id": row_id,
                    "reason": "conflicting_cadence",
                    "source_disposition": member["source_disposition"],
                }
                for member in members
            )
            continue
        representative = members[0]
        row = representative["value"]
        accepted.append(
            {
                "row_id": row_id,
                "cadence_number": row["cadence_number"],
                "btjd_tdb_days": row["btjd_tdb_days"],
                "quality_bitmask": row["quality_bitmask"],
                "time_interval_days": representative["interval"],
                "representative": representative["source"],
                "provenance": [member["source"] for member in members],
            }
        )
        quarantine.extend(
            {
                "source": member["source"],
                "row_id": row_id,
                "reason": "duplicate_cadence",
                "representative": representative["source"],
                "source_disposition": member["source_disposition"],
            }
            for member in members[1:]
        )
    quarantine.sort(key=lambda row: (row["source"]["raw_sha256"], row["source"]["source_row"]))
    reasons = dict(sorted(Counter(row["reason"] for row in quarantine).items()))
    if total_rows != len(accepted) + len(quarantine):
        raise CadenceInputError("cohort_accounting_error", "Input rows did not reconcile")
    identity = {
        "cohort_schema_version": COHORT_VERSION,
        "source_report_schema_version": REPORT_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "raw_sha256": sorted(reports),
    }
    return {
        "schema_version": COHORT_VERSION,
        "identity": identity,
        "cohort_sha256": hashlib.sha256(_json_bytes(identity)).hexdigest(),
        "input_only": True,
        "scientific_execution_authorized": False,
        "cross_file_assembly_performed": True,
        "time": {**TIME_HEADER, "conversion_performed": False},
        "sources": sources,
        "counts": {
            "distinct_raw_sources": len(sources),
            "input_rows_across_distinct_sources": total_rows,
            "accepted_unique_cadence_identities": len(accepted),
            "quarantined_source_rows": len(quarantine),
            "duplicate_source_rows": reasons.get("duplicate_cadence", 0),
            "overlapping_cadence_identities": overlaps,
            "conflicting_cadence_identities": conflicts,
        },
        "quarantine_reasons": reasons,
        "accepted": accepted,
        "quarantine": quarantine,
    }


def build_cohort(inputs: Sequence[tuple[bytes, SourceReceipt]]) -> dict[str, Any]:
    """Reparse a bounded source set and reconcile native cadence identities."""
    if not 1 <= len(inputs) <= MAX_INPUTS:
        raise CadenceInputError("cohort_too_large", "Supply between one and 16 source pairs")
    total_bytes = 0
    reports: dict[str, dict[str, Any]] = {}
    receipts: dict[str, bytes] = {}
    for raw, source in inputs:
        if not isinstance(raw, bytes):
            raise CadenceInputError("local_input_error", "Raw inputs must be exact bytes")
        total_bytes += len(raw)
        if total_bytes > MAX_TOTAL_BYTES:
            raise CadenceInputError("cohort_too_large", "Supplied inputs exceed 16 MiB")
        source = SourceReceipt.from_dict(asdict(source))
        digest = hashlib.sha256(raw).hexdigest()
        if digest != source.raw_sha256:
            raise CadenceInputError("source_hash_mismatch", "Raw bytes differ from their receipt")
        receipt_bytes = _json_bytes(asdict(source))
        if digest in receipts:
            if receipts[digest] != receipt_bytes:
                raise CadenceInputError(
                    "source_provenance_conflict",
                    "One raw source has differing acquisition identities",
                )
            continue
        reports[digest] = build_report(raw, source)
        receipts[digest] = receipt_bytes
    return _assemble(reports)


def ingest_cohort(inputs: Sequence[tuple[Path, Path]], output_dir: Path) -> dict[str, Any]:
    """Publish one immutable cohort; repeated source requests create no new evidence."""
    if not 1 <= len(inputs) <= MAX_INPUTS:
        raise CadenceInputError("cohort_too_large", "Supply between one and 16 source pairs")
    loaded = []
    total_bytes = 0
    for raw_path, receipt_path in inputs:
        source = load_source(receipt_path)
        raw = _read_regular(raw_path, MAX_BYTES, "local_input_error")
        total_bytes += len(raw)
        if total_bytes > MAX_TOTAL_BYTES:
            raise CadenceInputError("cohort_too_large", "Supplied inputs exceed 16 MiB")
        loaded.append((raw, source))
    report = build_cohort(loaded)
    encoded = _json_bytes(report)
    if len(encoded) > MAX_COHORT_BYTES:
        raise CadenceInputError("cohort_too_large", "Cohort report exceeds 32 MiB")
    path = output_dir / f"{report['cohort_sha256']}.cohort.json"
    created = True
    try:
        atomic_create_binary(path, lambda handle: handle.write(encoded))
    except FileExistsError:
        existing = _read_regular(path, MAX_COHORT_BYTES, "artifact_conflict")
        if existing != encoded:
            raise CadenceInputError(
                "artifact_conflict",
                "Existing cohort differs; provenance and results cannot be replaced",
            ) from None
        created = False
    return {
        "status": "created" if created else "reused",
        "artifact": str(path),
        "cohort_sha256": report["cohort_sha256"],
        "supplied_source_pairs": len(inputs),
        "repeated_source_pairs": len(inputs) - report["counts"]["distinct_raw_sources"],
        "counts": report["counts"],
        "new_artifacts": int(created),
        "input_only": True,
        "scientific_execution_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", action="append", nargs=2, metavar=("RAW", "RECEIPT"), type=Path, required=True
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = ingest_cohort(args.input, args.output_dir)
    except (CadenceInputError, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, CadenceInputError) else "local_input_error"
        print(json.dumps({"status": "rejected", "reason": code, "detail": str(exc)}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
