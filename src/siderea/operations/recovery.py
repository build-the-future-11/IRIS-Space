"""Executed SQLite backup/restore checks with read-only access to the source."""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from siderea.provenance import digest_file, digest_value


def check_sqlite_recovery(source: str | Path) -> dict[str, Any]:
    """Restore a consistent online backup and check integrity, FKs and row counts.

    This qualifies one database backup, not the external artifact files referenced
    by a ledger. No source mutations, replacement or external connection occur.
    """

    path = Path(source).expanduser().resolve()
    if not path.is_file():
        raise ValueError("recovery source must be an existing SQLite database")
    with tempfile.TemporaryDirectory(prefix="siderea-recovery-") as directory:
        backup_path = Path(directory) / "restored.sqlite"
        original = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        restored = sqlite3.connect(backup_path)
        try:
            original.execute("BEGIN")
            tables = [
                row[0]
                for row in original.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name"
                )
            ]
            expected = {
                table: int(
                    original.execute(
                        'SELECT COUNT(*) FROM "' + table.replace('"', '""') + '"'
                    ).fetchone()[0]
                )
                for table in tables
            }
            original.backup(restored)
            integrity = [row[0] for row in restored.execute("PRAGMA integrity_check")]
            foreign_keys = [list(row) for row in restored.execute("PRAGMA foreign_key_check")]
            actual = {
                table: int(
                    restored.execute(
                        'SELECT COUNT(*) FROM "' + table.replace('"', '""') + '"'
                    ).fetchone()[0]
                )
                for table in tables
            }
        finally:
            restored.close()
            original.close()
        report = {
            "schema": "siderea.sqlite_recovery_check.v1",
            "execution_method": "sqlite_online_backup_restore",
            "source": str(path),
            "backup_sha256": digest_file(backup_path),
            "source_table_counts": expected,
            "restored_table_counts": actual,
            "integrity": integrity,
            "foreign_key_violations": foreign_keys,
            "passed": integrity == ["ok"] and not foreign_keys and actual == expected,
            "scope": "single_database_excludes_external_artifacts",
        }
        report["report_digest"] = digest_value(report)
        return report
