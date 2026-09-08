"""No-clobber backups of an outcome ledger and its immutable publication evidence."""

from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from collections.abc import Mapping, Sequence
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any

from siderea.atomic import RESTORE_MARKER, atomic_create_binary, fsync_directory
from siderea.provenance import digest_file, digest_value, stable_json
from siderea.reporting.preflight import _publication_error

BACKUP_SCHEMA = "siderea.evidence_backup.v1"


def _payloads(database: Path) -> list[dict[str, Any]]:
    with sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("backup database integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("backup database contains broken foreign keys")
        rows = db.execute(
            "SELECT payload_json FROM candidates UNION SELECT payload_json FROM candidate_versions"
        ).fetchall()
    values = [json.loads(row[0]) for row in rows]
    if any(not isinstance(value, dict) for value in values):
        raise ValueError("backup database contains invalid candidate payloads")
    return values


def create_evidence_backup(
    ledger: str | Path,
    artifact_root: str | Path,
    destination: str | Path,
    *,
    additional_files: Sequence[Path] = (),
) -> dict[str, Any]:
    """Snapshot one ledger and all artifacts referenced by current/historical publications.

    Additional ordinary files can include dossiers/models. Other live databases
    require their own consistent snapshot and are deliberately not copied raw.
    """
    root = Path(artifact_root).expanduser().resolve()
    source = Path(ledger).expanduser().resolve()
    target = Path(destination).expanduser().resolve()
    if not root.is_dir() or not source.is_file() or not source.is_relative_to(root):
        raise ValueError("ledger must be an existing database inside artifact_root")
    if any((parent / RESTORE_MARKER).exists() for parent in (source.parent, *source.parents)):
        raise ValueError("cannot back up an incomplete restore")
    if target.is_relative_to(root):
        raise ValueError("backup destination must be outside artifact_root")
    if target.exists():
        raise FileExistsError("backup destination already exists")
    ledger_relative = source.relative_to(root).as_posix()
    with tempfile.TemporaryDirectory(prefix="siderea-evidence-backup-") as temporary:
        database = Path(temporary) / "ledger.sqlite"
        original = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        copied = sqlite3.connect(database)
        try:
            original.backup(copied)
            copied.execute("PRAGMA journal_mode=DELETE")
        finally:
            copied.close()
            original.close()
        payloads = _payloads(database)
        sources: dict[str, tuple[Path, str]] = {ledger_relative: (database, digest_file(database))}

        def include(path: Path, expected: str | None = None) -> None:
            resolved = path.expanduser().resolve()
            if not resolved.is_file() or not resolved.is_relative_to(root):
                raise ValueError("referenced backup file is missing or outside artifact_root")
            relative = resolved.relative_to(root).as_posix()
            if resolved == source:
                raise ValueError("a live database cannot be copied as an ordinary artifact")
            with resolved.open("rb") as handle:
                if handle.read(16) == b"SQLite format 3\x00":
                    raise ValueError("additional live databases need a separate online backup")
            actual = digest_file(resolved)
            if expected is not None and actual != expected:
                raise ValueError("referenced backup file differs from its publication digest")
            if relative in sources and sources[relative][1] != actual:
                raise ValueError("backup references conflicting versions of an artifact")
            sources[relative] = (resolved, actual)

        for payload in payloads:
            if "pipeline_version" not in payload:
                continue
            error = _publication_error(payload)
            if error is not None:
                raise ValueError(f"cannot back up incomplete publication: {error}")
            publication = payload["publication"]
            manifest_path = Path(publication["manifest_path"])
            include(manifest_path, publication["manifest_sha256"])
            manifest = json.loads(manifest_path.read_bytes())
            for artifact in manifest["artifacts"]:
                include(Path(artifact["path"]), artifact["sha256"])
        for path in additional_files:
            if path.is_dir():
                for child in sorted(path.rglob("*")):
                    if child.is_file():
                        include(child)
            else:
                include(path)
        entries = [
            {"path": relative, "sha256": digest, "size_bytes": path.stat().st_size}
            for relative, (path, digest) in sorted(sources.items())
        ]
        manifest = {
            "schema": BACKUP_SCHEMA,
            "original_root": str(root),
            "ledger_path": ledger_relative,
            "files": entries,
            "scope": "one_outcome_ledger_all_referenced_runs_and_explicit_additional_files",
        }
        manifest["backup_digest"] = digest_value(manifest)
        archive_path = Path(temporary) / "backup.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("manifest.json", stable_json(manifest))
            for relative, (path, _) in sorted(sources.items()):
                archive.write(path, "files/" + relative)
        verify_evidence_backup(archive_path)
        with archive_path.open("rb") as handle:
            atomic_create_binary(target, lambda output: shutil.copyfileobj(handle, output))
        return manifest


def verify_evidence_backup(source: str | Path) -> dict[str, Any]:
    """Verify every archived byte and database before permitting offline restoration."""
    with zipfile.ZipFile(source) as archive:
        if archive.getinfo("manifest.json").file_size > 8 * 1024 * 1024:
            raise ValueError("backup manifest exceeds size limit")
        manifest = json.loads(archive.read("manifest.json"))
        if not isinstance(manifest, dict) or manifest.get("schema") != BACKUP_SCHEMA:
            raise ValueError("unsupported backup schema")
        basis = dict(manifest)
        stored = basis.pop("backup_digest", None)
        if stored != digest_value(basis):
            raise ValueError("backup manifest digest differs")
        entries = manifest.get("files")
        if not isinstance(entries, list) or not entries or len(entries) > 100_000:
            raise ValueError("backup file inventory is invalid")
        names = {"manifest.json"}
        for entry in entries:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str):
                raise ValueError("backup file metadata is invalid")
            relative = PurePosixPath(entry["path"])
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or not relative.parts
                or "\\" in entry["path"]
                or ":" in entry["path"]
                or relative.as_posix() != entry["path"]
                or RESTORE_MARKER in relative.parts
            ):
                raise ValueError("backup contains an unsafe path")
            if type(entry.get("size_bytes")) is not int or entry["size_bytes"] < 0:
                raise ValueError("backup file size metadata is invalid")
            name = "files/" + relative.as_posix()
            if name in names:
                raise ValueError("backup contains duplicate paths")
            names.add(name)
            info = archive.getinfo(name)
            if info.file_size != entry.get("size_bytes"):
                raise ValueError("backup file size differs")
            digest = sha256()
            with archive.open(name) as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != entry.get("sha256"):
                raise ValueError("backup file digest differs")
        if len(archive.namelist()) != len(names) or set(archive.namelist()) != names:
            raise ValueError("backup contains unlisted or duplicate files")
        ledger_name = "files/" + str(manifest.get("ledger_path"))
        if ledger_name not in names or not Path(str(manifest.get("original_root"))).is_absolute():
            raise ValueError("backup root or ledger path is invalid")
        with tempfile.TemporaryDirectory(prefix="siderea-backup-verify-") as temporary:
            database = Path(temporary) / "ledger.sqlite"
            with archive.open(ledger_name) as handle, database.open("wb") as output:
                shutil.copyfileobj(handle, output)
            payloads = _payloads(database)
            inventory = {entry["path"]: entry for entry in entries}
            root = Path(manifest["original_root"])

            def referenced(path: str, digest: str) -> str:
                artifact = Path(path)
                if not artifact.is_absolute() or ".." in artifact.parts:
                    raise ValueError("publication contains an unsafe artifact path")
                try:
                    relative = artifact.relative_to(root).as_posix()
                except ValueError as exc:
                    raise ValueError("publication artifact is outside backup root") from exc
                if relative not in inventory or inventory[relative]["sha256"] != digest:
                    raise ValueError("backup omits or changes a referenced publication artifact")
                return "files/" + relative

            for payload in payloads:
                if "pipeline_version" not in payload:
                    continue
                publication = payload["publication"]
                name = referenced(publication["manifest_path"], publication["manifest_sha256"])
                run_manifest = json.loads(archive.read(name))
                for artifact in run_manifest["artifacts"]:
                    name = referenced(artifact["path"], artifact["sha256"])
                    if archive.getinfo(name).file_size != artifact["size_bytes"]:
                        raise ValueError("publication artifact size differs")
        return manifest


def restore_evidence_backup(source: str | Path, destination: str | Path) -> dict[str, Any]:
    """Restore offline to the original absolute root without overwriting existing data.

    An interrupted restore retains a marker that OutcomeLedger refuses to open.
    Preserve that failed directory for diagnosis, then retry into an absent root.
    """
    archive_path = Path(source).expanduser().resolve()
    manifest = verify_evidence_backup(archive_path)
    target = Path(destination).expanduser().resolve()
    if str(target) != manifest["original_root"]:
        raise ValueError(
            "restore must retain the original root to preserve immutable path bindings"
        )
    if target.exists():
        raise FileExistsError(
            "restore destination must not exist; existing data will not be replaced"
        )
    target.mkdir(parents=True, exist_ok=False)
    marker = target / RESTORE_MARKER
    marker.write_text("Restore incomplete. Do not serve this directory.\n")
    fsync_directory(target)
    with zipfile.ZipFile(archive_path) as archive:
        for entry in manifest["files"]:
            output_path = target / entry["path"]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open("files/" + entry["path"]) as handle:
                atomic_create_binary(output_path, lambda output: shutil.copyfileobj(handle, output))
            if digest_file(output_path) != entry["sha256"]:
                raise ValueError("restored artifact digest differs")
    database = target / manifest["ledger_path"]
    for payload in _payloads(database):
        error = _publication_error(payload)
        if error is not None:
            raise ValueError(f"restored publication validation failed: {error}")
    marker.unlink()
    fsync_directory(target)
    return {"restored": True, "root": str(target), "backup_digest": manifest["backup_digest"]}
