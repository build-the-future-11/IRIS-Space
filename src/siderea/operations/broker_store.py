"""Durable, replayable storage for content-bound broker snapshots."""

from __future__ import annotations

import hmac
import json
import math
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from siderea.atomic import atomic_write_bytes, fsync_directory
from siderea.ingest import ingest_csv
from siderea.ingest.snapshot import BROKER_SNAPSHOT_SCHEMA
from siderea.provenance import stable_json

BROKER_ARCHIVE_SCHEMA = "siderea.broker_archive.v1"


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class ArchivedBrokerSnapshot:
    snapshot_id: str
    stream: str
    cursor: str
    watermark_mjd: float
    source: str
    retrieved_at: str
    photometry_sha256: str
    sidecar_sha256: str
    archived_at: str


class BrokerArchive:
    """SQLite byte archive with monotonic stream watermarks and dead letters."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 5000")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    stream TEXT NOT NULL,
                    cursor TEXT NOT NULL,
                    watermark_mjd REAL NOT NULL,
                    source TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL,
                    photometry_sha256 TEXT NOT NULL,
                    sidecar_sha256 TEXT NOT NULL,
                    photometry_bytes BLOB NOT NULL,
                    sidecar_bytes BLOB NOT NULL,
                    archived_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cursors (
                    stream TEXT PRIMARY KEY,
                    cursor TEXT NOT NULL,
                    watermark_mjd REAL NOT NULL,
                    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id),
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS dead_letters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stream TEXT NOT NULL,
                    cursor TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    payload_bytes BLOB NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS broker_snapshots_no_update
                BEFORE UPDATE ON snapshots BEGIN
                    SELECT RAISE(ABORT, 'broker snapshots are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS broker_snapshots_no_delete
                BEFORE DELETE ON snapshots BEGIN
                    SELECT RAISE(ABORT, 'broker snapshots are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS broker_dead_letters_no_update
                BEFORE UPDATE ON dead_letters BEGIN
                    SELECT RAISE(ABORT, 'broker dead letters are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS broker_dead_letters_no_delete
                BEFORE DELETE ON dead_letters BEGIN
                    SELECT RAISE(ABORT, 'broker dead letters are append-only');
                END;
                CREATE TABLE IF NOT EXISTS dead_letter_resolutions (
                    dead_letter_id INTEGER PRIMARY KEY REFERENCES dead_letters(id),
                    reason TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    resolved_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS broker_resolutions_no_update
                BEFORE UPDATE ON dead_letter_resolutions BEGIN
                    SELECT RAISE(ABORT, 'broker resolutions are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS broker_resolutions_no_delete
                BEFORE DELETE ON dead_letter_resolutions BEGIN
                    SELECT RAISE(ABORT, 'broker resolutions are append-only');
                END;
                """
            )

    def archive_snapshot(
        self,
        photometry_path: str | Path,
        *,
        stream: str,
        cursor: str,
        watermark_mjd: float,
    ) -> ArchivedBrokerSnapshot:
        """Validate and atomically archive one published broker CSV/sidecar pair."""

        stream_name = _text(stream, "stream")
        cursor_value = _text(cursor, "cursor")
        if isinstance(watermark_mjd, bool) or not isinstance(watermark_mjd, (int, float)):
            raise ValueError("watermark_mjd must be finite and non-negative")
        watermark = float(watermark_mjd)
        if not math.isfinite(watermark) or watermark < 0:
            raise ValueError("watermark_mjd must be finite and non-negative")
        source_path = Path(photometry_path).expanduser().resolve()
        sidecar_path = source_path.with_suffix(source_path.suffix + ".provenance.json")
        batch = ingest_csv(source_path)
        if batch.source_content is None:
            raise ValueError("broker ingestion did not retain immutable source bytes")
        photometry_bytes = batch.source_content
        try:
            sidecar_bytes = sidecar_path.read_bytes()
            sidecar = json.loads(sidecar_bytes)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read broker sidecar {sidecar_path}: {exc}") from exc
        if not isinstance(sidecar, Mapping) or sidecar.get("schema") != BROKER_SNAPSHOT_SCHEMA:
            raise ValueError("broker sidecar has an unsupported schema")
        snapshot_id = _text(sidecar.get("snapshot_id"), "snapshot_id").casefold()
        source = _text(sidecar.get("source"), "source")
        retrieved_at = _text(sidecar.get("retrieved_at"), "retrieved_at")
        photometry_digest = sha256(photometry_bytes).hexdigest()
        if not hmac.compare_digest(
            _text(sidecar.get("photometry_sha256"), "photometry_sha256").casefold(),
            photometry_digest,
        ):
            raise ValueError("broker sidecar differs from immutable photometry bytes")
        sidecar_digest = sha256(sidecar_bytes).hexdigest()
        provenance = batch.provenance.get("broker_snapshot")
        if (
            not isinstance(provenance, Mapping)
            or provenance.get("sidecar_sha256") != sidecar_digest
        ):
            raise ValueError("broker ingestion and archived sidecar snapshots differ")
        archived_at = datetime.now(UTC).isoformat()
        record = ArchivedBrokerSnapshot(
            snapshot_id=snapshot_id,
            stream=stream_name,
            cursor=cursor_value,
            watermark_mjd=watermark,
            source=source,
            retrieved_at=retrieved_at,
            photometry_sha256=photometry_digest,
            sidecar_sha256=sidecar_digest,
            archived_at=archived_at,
        )
        with self.connect() as db:
            # Serialize the read/validate/write sequence, not only the INSERT.
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT * FROM snapshots WHERE snapshot_id=?", (snapshot_id,)
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["photometry_sha256"]) != photometry_digest
                    or str(existing["sidecar_sha256"]) != sidecar_digest
                    or str(existing["stream"]) != stream_name
                    or str(existing["cursor"]) != cursor_value
                    or float(existing["watermark_mjd"]) != watermark
                ):
                    raise ValueError("broker snapshot ID is already bound to different facts")
                # An exact historical retry does not rewind the current cursor.
                return _snapshot_from_row(existing)
            previous = db.execute(
                "SELECT cursor, watermark_mjd, snapshot_id FROM cursors WHERE stream=?",
                (stream_name,),
            ).fetchone()
            if previous is not None:
                previous_watermark = float(previous["watermark_mjd"])
                if watermark < previous_watermark:
                    raise ValueError("broker watermark cannot move backwards")
                if watermark == previous_watermark and (
                    cursor_value != str(previous["cursor"])
                    or snapshot_id != str(previous["snapshot_id"])
                ):
                    raise ValueError("equal broker watermarks must identify the same snapshot")
            db.execute(
                """
                INSERT INTO snapshots(
                    snapshot_id, stream, cursor, watermark_mjd, source, retrieved_at,
                    photometry_sha256, sidecar_sha256, photometry_bytes, sidecar_bytes, archived_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    stream_name,
                    cursor_value,
                    watermark,
                    source,
                    retrieved_at,
                    photometry_digest,
                    sidecar_digest,
                    photometry_bytes,
                    sidecar_bytes,
                    archived_at,
                ),
            )
            db.execute(
                """
                INSERT INTO cursors(stream, cursor, watermark_mjd, snapshot_id, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(stream) DO UPDATE SET
                    cursor=excluded.cursor,
                    watermark_mjd=excluded.watermark_mjd,
                    snapshot_id=excluded.snapshot_id,
                    updated_at=excluded.updated_at
                """,
                (stream_name, cursor_value, watermark, snapshot_id, archived_at),
            )
        return record

    def latest_cursor(self, stream: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM cursors WHERE stream=?", (_text(stream, "stream"),)
            ).fetchone()
        return dict(row) if row is not None else None

    def record_dead_letter(
        self,
        *,
        stream: str,
        cursor: str,
        reason: str,
        payload: bytes,
    ) -> str:
        if not isinstance(payload, bytes):
            raise TypeError("dead-letter payload must be bytes")
        payload_digest = sha256(payload).hexdigest()
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO dead_letters(
                    stream, cursor, reason, payload_sha256, payload_bytes, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _text(stream, "stream"),
                    _text(cursor, "cursor"),
                    _text(reason, "reason"),
                    payload_digest,
                    payload,
                    datetime.now(UTC).isoformat(),
                ),
            )
        return payload_digest

    def replay(self, snapshot_id: str, destination: str | Path) -> tuple[Path, Path]:
        """Recreate an exact CSV/sidecar pair inside a new directory."""

        identifier = _text(snapshot_id, "snapshot_id").casefold()
        with self.connect() as db:
            row = db.execute(
                "SELECT photometry_bytes, sidecar_bytes, photometry_sha256, sidecar_sha256 "
                "FROM snapshots WHERE snapshot_id=?",
                (identifier,),
            ).fetchone()
        if row is None:
            raise ValueError(f"unknown archived broker snapshot: {identifier}")
        photometry_bytes = bytes(row["photometry_bytes"])
        sidecar_bytes = bytes(row["sidecar_bytes"])
        if (
            sha256(photometry_bytes).hexdigest() != row["photometry_sha256"]
            or sha256(sidecar_bytes).hexdigest() != row["sidecar_sha256"]
        ):
            raise ValueError("archived broker bytes differ from their stored digests")
        target = Path(destination).expanduser().resolve()
        if target.exists():
            raise FileExistsError(f"broker replay destination already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.parent / f".{target.name}.{uuid4().hex}.tmp"
        staging.mkdir(mode=0o700)
        try:
            csv_path = staging / "photometry.csv"
            sidecar_path = staging / "photometry.csv.provenance.json"
            atomic_write_bytes(sidecar_path, sidecar_bytes)
            atomic_write_bytes(csv_path, photometry_bytes)
            ingest_csv(csv_path)
            staging.replace(target)
            fsync_directory(target.parent)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return target / "photometry.csv", target / "photometry.csv.provenance.json"

    def verify_archive(self) -> dict[str, Any]:
        """Actually reconstruct and ingest every snapshot in a temporary directory."""

        inventory = self.inventory()
        failures: list[dict[str, str]] = []
        verified: list[str] = []
        with tempfile.TemporaryDirectory(prefix="siderea-broker-verify-") as directory:
            for item in inventory["snapshots"]:
                identifier = item["snapshot_id"]
                try:
                    self.replay(identifier, Path(directory) / identifier)
                    verified.append(identifier)
                except (OSError, ValueError) as exc:
                    failures.append({"snapshot_id": identifier, "error": str(exc)})
        report = {
            "schema": "siderea.broker_replay_verification.v1",
            "inventory_digest": inventory["inventory_digest"],
            "verified_snapshot_ids": verified,
            "failures": failures,
            "passed": bool(verified) and not failures,
        }
        report["report_digest"] = sha256(stable_json(report).encode()).hexdigest()
        return report

    def resolve_dead_letter(
        self, dead_letter_id: int, *, reason: str, evidence: Mapping[str, Any]
    ) -> None:
        """Append a disposition with evidence, preserving the original bytes."""

        if isinstance(dead_letter_id, bool) or not isinstance(dead_letter_id, int):
            raise ValueError("dead_letter_id must be an integer")
        if not isinstance(evidence, Mapping) or not evidence:
            raise ValueError("resolution evidence must be a non-empty object")
        with self.connect() as db:
            if (
                db.execute("SELECT id FROM dead_letters WHERE id=?", (dead_letter_id,)).fetchone()
                is None
            ):
                raise ValueError("unknown dead letter")
            db.execute(
                "INSERT INTO dead_letter_resolutions VALUES (?, ?, ?, ?)",
                (
                    dead_letter_id,
                    _text(reason, "reason"),
                    stable_json(dict(evidence)),
                    datetime.now(UTC).isoformat(),
                ),
            )

    def inventory(self, *, stream: str | None = None) -> dict[str, Any]:
        with self.connect() as db:
            if stream is None:
                rows = db.execute(
                    "SELECT * FROM snapshots ORDER BY archived_at, snapshot_id"
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM snapshots WHERE stream=? ORDER BY archived_at, snapshot_id",
                    (_text(stream, "stream"),),
                ).fetchall()
            dead_letters = int(db.execute("SELECT COUNT(*) FROM dead_letters").fetchone()[0])
            unresolved = [
                dict(row)
                for row in db.execute(
                    "SELECT id, stream, cursor, reason, payload_sha256 FROM dead_letters "
                    "WHERE id NOT IN (SELECT dead_letter_id FROM dead_letter_resolutions) "
                    "ORDER BY id"
                ).fetchall()
            ]
        records = [_snapshot_from_row(row) for row in rows]
        serialized = [asdict(record) for record in records]
        return {
            "schema": BROKER_ARCHIVE_SCHEMA,
            "snapshot_count": len(records),
            "dead_letter_count": dead_letters,
            "unresolved_dead_letter_count": len(unresolved),
            "unresolved_dead_letters": unresolved,
            "snapshots": serialized,
            "inventory_digest": sha256(stable_json(serialized).encode("utf-8")).hexdigest(),
        }


def _snapshot_from_row(row: sqlite3.Row) -> ArchivedBrokerSnapshot:
    return ArchivedBrokerSnapshot(
        snapshot_id=str(row["snapshot_id"]),
        stream=str(row["stream"]),
        cursor=str(row["cursor"]),
        watermark_mjd=float(row["watermark_mjd"]),
        source=str(row["source"]),
        retrieved_at=str(row["retrieved_at"]),
        photometry_sha256=str(row["photometry_sha256"]),
        sidecar_sha256=str(row["sidecar_sha256"]),
        archived_at=str(row["archived_at"]),
    )


__all__ = ["BROKER_ARCHIVE_SCHEMA", "ArchivedBrokerSnapshot", "BrokerArchive"]
