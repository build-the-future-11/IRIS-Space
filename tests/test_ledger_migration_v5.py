import sqlite3
from pathlib import Path

from siderea.ledger import SCHEMA_VERSION, OutcomeLedger


def test_schema_five_upgrade_preserves_events_without_inventing_authentication(tmp_path):
    path = tmp_path / "ledger.sqlite"
    with sqlite3.connect(path) as db:
        db.executescript((Path(__file__).parent / "fixtures/ledger_v5.sql").read_text())
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        before = {
            name: db.execute(f'SELECT * FROM "{name}"').fetchall()
            for name in tables
            if name != "metadata"
        }
    ledger = OutcomeLedger(path)
    with ledger.connect() as db:
        for name, rows in before.items():
            assert [tuple(row) for row in db.execute(f'SELECT * FROM "{name}"')] == rows
        assert db.execute("SELECT COUNT(*) FROM decision_authentication").fetchone()[0] == 0
        assert (
            int(db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0])
            == SCHEMA_VERSION
        )
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert ledger.reviews_for("migration-example")[0].reviewer == "legacy-reviewer"
    OutcomeLedger(path)
    assert len(ledger.reviews_for("migration-example")) == 1
