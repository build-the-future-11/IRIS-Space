from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from siderea.cli import main
from siderea.config import load_config
from siderea.operations.broker_store import BrokerArchive
from siderea.operations.fixtures import ServiceFixture
from siderea.operations.observability import OperationsLedger
from siderea.operations.recovery import check_sqlite_recovery
from siderea.pipeline import analyze_csv


def fixture(**overrides):
    values = dict(
        service="tns",
        service_version="test",
        capture_mode="synthetic",
        scenario="failure",
        request={"radius": 2},
        status_code=503,
        response_headers={},
        response_body=b"",
    )
    values.update(overrides)
    return ServiceFixture.create(**values)


def test_empty_body_fixture_roundtrip():
    original = fixture()
    restored = ServiceFixture.from_dict(original.to_dict())
    assert restored.replay({"radius": 2}) == (503, {}, b"")
    with pytest.raises(ValueError, match="differs"):
        restored.replay({"radius": 3})


@pytest.mark.parametrize(
    "fields",
    [
        {"request": {"headers": {"Authorization": "SENTINEL"}}},
        {"request": {"nested": [{"api_key": "SENTINEL"}]}},
        {"request": {"url": "https://example.test/?access_token=SENTINEL"}},
        {"request": {"url": "https://user:SENTINEL@example.test/"}},
        {"response_headers": {"Set-Cookie": "SENTINEL"}},
        {"response_body": b'{"data":{"password":"SENTINEL"}}'},
        {"response_body": b"access_token=SENTINEL"},
    ],
)
def test_fixture_credentials_are_rejected_without_echoing_values(fields):
    with pytest.raises(ValueError, match="credential") as error:
        fixture(**fields)
    assert "SENTINEL" not in str(error.value)


def test_fixture_tampering_rejected():
    payload = fixture(response_body=b'{"error":"unavailable"}').to_dict()
    payload["status_code"] = 200
    with pytest.raises(ValueError, match="content"):
        ServiceFixture.from_dict(payload)


def test_incident_resolution_preserves_history(tmp_path):
    ledger = OperationsLedger(tmp_path / "ops.sqlite")
    assert ledger.health_report()["healthy"] is False
    event = ledger.record_event(level="error", component="broker", event="outage", attributes={})
    assert ledger.health_report()["unresolved_failure_count"] == 1
    ledger.resolve_incident(event.event_id, reason="restored", evidence={"replay_digest": "test"})
    report = ledger.health_report()
    assert report["healthy"] is True
    assert report["failure_count"] == report["resolved_failure_count"] == 1
    assert report["unresolved_failure_count"] == 0
    with pytest.raises(ValueError, match="recorded"):
        ledger.resolve_incident("absent", reason="fixed", evidence={"run": 1})


def test_recovery_reserved_fields_and_timezones(tmp_path):
    ledger = OperationsLedger(tmp_path / "ops.sqlite")
    with pytest.raises(ValueError, match="reserved"):
        ledger.record_recovery_drill("restore", passed=True, evidence={"passed": False})
    ledger.record_recovery_drill(
        "restore",
        passed=True,
        evidence={"run": "test"},
        observed_at="2026-01-01T01:00:00+02:00",
    )
    assert ledger.health_report(since="2026-01-01T00:00:00+00:00")["event_count"] == 0
    assert ledger.health_report(since="2025-12-31T22:00:00+00:00")["recovery_drill_pass_count"] == 1


def test_dead_letter_disposition_preserves_bytes(tmp_path):
    archive = BrokerArchive(tmp_path / "broker.sqlite")
    archive.record_dead_letter(stream="ztf", cursor="1", reason="malformed", payload=b"bad")
    inventory = archive.inventory()
    identifier = inventory["unresolved_dead_letters"][0]["id"]
    archive.resolve_dead_letter(identifier, reason="replayed", evidence={"run": "replay-1"})
    assert archive.inventory()["dead_letter_count"] == 1
    assert archive.inventory()["unresolved_dead_letter_count"] == 0
    with archive.connect() as db:
        assert bytes(db.execute("SELECT payload_bytes FROM dead_letters").fetchone()[0]) == b"bad"


def test_ledger_initialization_failure_closes_created_run(tmp_path):
    config = load_config()
    with (
        patch("siderea.pipeline.OutcomeLedger", side_effect=OSError("cannot initialize")),
        pytest.raises(OSError, match="initialize"),
    ):
        analyze_csv(
            Path("examples/photometry.csv"),
            config,
            output_dir=tmp_path,
            run_id="initialization-failure",
        )
    manifest = json.loads((tmp_path / "initialization-failure" / "manifest.json").read_text())
    assert manifest["status"] == "failed"


def test_executed_recovery_and_resolution_commands(tmp_path, capsys):
    source = tmp_path / "source.sqlite"
    archive = BrokerArchive(source)
    archive.record_dead_letter(stream="test", cursor="1", reason="invalid", payload=b"test")
    before = source.read_bytes()
    report = check_sqlite_recovery(source)
    assert report["passed"] is True
    assert report["source_table_counts"]["dead_letters"] == 1
    assert report["source_table_counts"] == report["restored_table_counts"]
    assert source.read_bytes() == before
    ops = tmp_path / "ops.sqlite"
    assert main(["recovery-check", str(ops), str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["passed"] is True
    assert OperationsLedger(ops).health_report()["recovery_drill_pass_count"] == 1
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"replayed_run":"synthetic-test"}')
    assert (
        main(["dead-letter-resolve", str(source), "1", str(evidence), "--reason", "replayed"]) == 0
    )
    assert json.loads(capsys.readouterr().out)["unresolved_dead_letter_count"] == 0


def test_recovery_rejects_corrupt_database(tmp_path):
    import sqlite3

    source = tmp_path / "bad.sqlite"
    source.write_bytes(b"not a database")
    with pytest.raises(sqlite3.DatabaseError):
        check_sqlite_recovery(source)


def test_cli_database_failure_is_controlled(tmp_path, capsys):
    path = tmp_path / "corrupt.sqlite"
    path.write_bytes(b"not a database")
    assert main(["broker-inventory", str(path)]) == 2
    assert "not a database" in capsys.readouterr().err


def test_malformed_incident_resolution_cannot_corrupt_health(tmp_path):
    ledger = OperationsLedger(tmp_path / "ops.sqlite")
    with pytest.raises(ValueError, match="incident_id"):
        ledger.record_event(
            level="info",
            component="recovery",
            event="incident_resolved",
            attributes={"incident_id": []},
        )
    assert ledger.health_report()["healthy"] is False
