"""Append-only operational events, schema qualification, and recovery drills."""

from __future__ import annotations

import hmac
import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from siderea.provenance import digest_value, stable_json

OPERATIONS_LEDGER_SCHEMA = "siderea.operations_ledger.v1"
_LEVELS = frozenset({"info", "warning", "error", "critical"})


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def _timestamp(value: str | None, name: str) -> str:
    raw = datetime.now(UTC).isoformat() if value is None else _text(value, name)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include timezone information")
    return parsed.astimezone(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class OperationalEvent:
    event_id: str
    observed_at: str
    level: str
    component: str
    event: str
    run_id: str
    candidate_id: str
    attributes: Mapping[str, Any]


class OperationsLedger:
    """Local qualification ledger; it is not a replacement for remote monitoring."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
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
                CREATE TABLE IF NOT EXISTS schema_contracts (
                    stream TEXT PRIMARY KEY,
                    fields_json TEXT NOT NULL,
                    fields_digest TEXT NOT NULL,
                    registered_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    observed_at TEXT NOT NULL,
                    level TEXT NOT NULL CHECK(level IN ('info','warning','error','critical')),
                    component TEXT NOT NULL,
                    event TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    attributes_json TEXT NOT NULL,
                    attributes_digest TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS operations_contracts_no_update
                BEFORE UPDATE ON schema_contracts BEGIN
                    SELECT RAISE(ABORT, 'schema contracts are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS operations_contracts_no_delete
                BEFORE DELETE ON schema_contracts BEGIN
                    SELECT RAISE(ABORT, 'schema contracts are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS operations_events_no_update
                BEFORE UPDATE ON events BEGIN
                    SELECT RAISE(ABORT, 'operational events are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS operations_events_no_delete
                BEFORE DELETE ON events BEGIN
                    SELECT RAISE(ABORT, 'operational events are append-only');
                END;
                """
            )

    def record_event(
        self,
        *,
        level: str,
        component: str,
        event: str,
        attributes: Mapping[str, Any],
        run_id: str = "",
        candidate_id: str = "",
        observed_at: str | None = None,
    ) -> OperationalEvent:
        normalized_level = _text(level, "level").casefold()
        if normalized_level not in _LEVELS:
            raise ValueError("level must be info, warning, error, or critical")
        if not isinstance(attributes, Mapping):
            raise ValueError("attributes must be a JSON object")
        materialized = dict(attributes)
        attributes_json = stable_json(materialized)
        timestamp = _timestamp(observed_at, "observed_at")
        basis = {
            "observed_at": timestamp,
            "level": normalized_level,
            "component": _text(component, "component").casefold(),
            "event": _text(event, "event").casefold(),
            "run_id": run_id.strip(),
            "candidate_id": candidate_id.strip(),
            "attributes": materialized,
        }
        record = OperationalEvent(
            event_id=digest_value({"schema": OPERATIONS_LEDGER_SCHEMA, **basis}),
            observed_at=timestamp,
            level=normalized_level,
            component=str(basis["component"]),
            event=str(basis["event"]),
            run_id=str(basis["run_id"]),
            candidate_id=str(basis["candidate_id"]),
            attributes=materialized,
        )
        with self.connect() as db:
            if record.event == "incident_resolved":
                identifier = _text(materialized.get("incident_id"), "incident_id")
                _text(materialized.get("reason"), "resolution reason")
                evidence = materialized.get("evidence")
                if not isinstance(evidence, Mapping) or not evidence:
                    raise ValueError("resolution evidence must be a non-empty object")
                incident = db.execute(
                    "SELECT level, observed_at FROM events WHERE event_id=?", (identifier,)
                ).fetchone()
                if (
                    record.level != "info"
                    or record.component != "recovery"
                    or incident is None
                    or incident["level"] not in {"error", "critical"}
                    or datetime.fromisoformat(str(incident["observed_at"]))
                    > datetime.fromisoformat(timestamp)
                ):
                    raise ValueError("resolution must follow a recorded error or critical incident")
            db.execute(
                """
                INSERT OR IGNORE INTO events(
                    event_id, observed_at, level, component, event, run_id,
                    candidate_id, attributes_json, attributes_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.event_id,
                    record.observed_at,
                    record.level,
                    record.component,
                    record.event,
                    record.run_id,
                    record.candidate_id,
                    attributes_json,
                    digest_value(materialized),
                ),
            )
        return record

    def register_schema_contract(self, stream: str, fields: Mapping[str, Any]) -> str:
        if not isinstance(fields, Mapping) or not fields:
            raise ValueError("schema contract fields must be a non-empty object")
        stream_name = _text(stream, "stream").casefold()
        materialized = dict(fields)
        fields_json = stable_json(materialized)
        fields_digest = digest_value(materialized)
        with self.connect() as db:
            existing = db.execute(
                "SELECT fields_json, fields_digest FROM schema_contracts WHERE stream=?",
                (stream_name,),
            ).fetchone()
            if existing is not None:
                if not hmac.compare_digest(str(existing["fields_digest"]), fields_digest):
                    raise ValueError("stream already has a different qualified schema contract")
                return fields_digest
            db.execute(
                """
                INSERT INTO schema_contracts(stream, fields_json, fields_digest, registered_at)
                VALUES (?, ?, ?, ?)
                """,
                (stream_name, fields_json, fields_digest, datetime.now(UTC).isoformat()),
            )
        return fields_digest

    def observe_schema(
        self,
        stream: str,
        fields: Mapping[str, Any],
        *,
        observed_at: str | None = None,
    ) -> OperationalEvent:
        stream_name = _text(stream, "stream").casefold()
        if not isinstance(fields, Mapping) or not fields:
            raise ValueError("observed schema fields must be a non-empty object")
        observed = dict(fields)
        with self.connect() as db:
            contract = db.execute(
                "SELECT fields_json, fields_digest FROM schema_contracts WHERE stream=?",
                (stream_name,),
            ).fetchone()
        if contract is None:
            raise ValueError("stream has no qualified schema contract")
        expected = json.loads(str(contract["fields_json"]))
        if not isinstance(expected, Mapping):
            raise ValueError("stored schema contract is invalid")
        matches = hmac.compare_digest(digest_value(observed), str(contract["fields_digest"]))
        return self.record_event(
            level="info" if matches else "error",
            component="schema_monitor",
            event="schema_match" if matches else "schema_drift",
            observed_at=observed_at,
            attributes={
                "stream": stream_name,
                "matches": matches,
                "expected": dict(expected),
                "observed": observed,
                "expected_digest": str(contract["fields_digest"]),
                "observed_digest": digest_value(observed),
            },
        )

    def record_recovery_drill(
        self,
        name: str,
        *,
        passed: bool,
        evidence: Mapping[str, Any],
        observed_at: str | None = None,
    ) -> OperationalEvent:
        if not isinstance(passed, bool):
            raise TypeError("passed must be a boolean")
        if not isinstance(evidence, Mapping) or not evidence:
            raise ValueError("recovery evidence must be a non-empty object")
        if {"drill", "passed"} & set(evidence):
            raise ValueError("recovery evidence cannot override reserved drill/passed fields")
        return self.record_event(
            level="info" if passed else "error",
            component="recovery",
            event="drill_passed" if passed else "drill_failed",
            observed_at=observed_at,
            attributes={"drill": _text(name, "drill name"), "passed": passed, **dict(evidence)},
        )

    def resolve_incident(
        self, event_id: str, *, reason: str, evidence: Mapping[str, Any]
    ) -> OperationalEvent:
        """Append an operator resolution while retaining the original failure."""

        identifier = _text(event_id, "event_id")
        if not isinstance(evidence, Mapping) or not evidence:
            raise ValueError("resolution evidence must be a non-empty object")
        with self.connect() as db:
            row = db.execute("SELECT level FROM events WHERE event_id=?", (identifier,)).fetchone()
        if row is None or row["level"] not in {"error", "critical"}:
            raise ValueError("resolution must reference a recorded error or critical incident")
        return self.record_event(
            level="info",
            component="recovery",
            event="incident_resolved",
            attributes={
                "incident_id": identifier,
                "reason": _text(reason, "reason"),
                "evidence": dict(evidence),
            },
        )

    def health_report(self, *, since: str | None = None) -> dict[str, Any]:
        lower_bound = _timestamp(since, "since") if since is not None else ""
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM events ORDER BY observed_at, event_id",
            ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            # Older stores may contain ISO timestamps with non-UTC offsets.
            if lower_bound and datetime.fromisoformat(str(row["observed_at"])) < (
                datetime.fromisoformat(lower_bound)
            ):
                continue
            attributes = json.loads(str(row["attributes_json"]))
            if not isinstance(attributes, Mapping):
                raise ValueError("stored operational event attributes are invalid")
            if not hmac.compare_digest(
                digest_value(dict(attributes)), str(row["attributes_digest"])
            ):
                raise ValueError("stored operational event fails integrity validation")
            event_payload = {
                "event_id": str(row["event_id"]),
                "observed_at": str(row["observed_at"]),
                "level": str(row["level"]),
                "component": str(row["component"]),
                "event": str(row["event"]),
                "run_id": str(row["run_id"]),
                "candidate_id": str(row["candidate_id"]),
                "attributes": dict(attributes),
            }
            basis = dict(event_payload)
            stored_id = basis.pop("event_id")
            if stored_id != digest_value({"schema": OPERATIONS_LEDGER_SCHEMA, **basis}):
                raise ValueError("stored operational event identity fails integrity validation")
            events.append(event_payload)
        events.sort(
            key=lambda event: (datetime.fromisoformat(event["observed_at"]), event["event_id"])
        )
        failures = [event for event in events if event["level"] in {"error", "critical"}]
        resolved_ids = {
            event["attributes"].get("incident_id")
            for event in events
            if event["event"] == "incident_resolved"
            and event["level"] == "info"
            and isinstance(event["attributes"].get("incident_id"), str)
        }
        unresolved = [event for event in failures if event["event_id"] not in resolved_ids]
        recovery_passes = [
            event
            for event in events
            if event["event"] == "drill_passed"
            and event["level"] == "info"
            and event["attributes"].get("passed") is True
        ]
        payload = {
            "schema": OPERATIONS_LEDGER_SCHEMA,
            "since": lower_bound or None,
            "event_count": len(events),
            "failure_count": len(failures),
            "unresolved_failure_count": len(unresolved),
            "resolved_failure_count": len(failures) - len(unresolved),
            "unresolved_schema_drift_count": sum(
                event["event"] == "schema_drift" for event in unresolved
            ),
            "schema_drift_count": sum(event["event"] == "schema_drift" for event in events),
            "recovery_drill_pass_count": len(recovery_passes),
            "healthy": bool(events) and not unresolved,
            "qualification_scope": "recorded_operational_evidence_not_independent_execution",
            "events": events,
        }
        payload["report_digest"] = digest_value(payload)
        return payload


__all__ = ["OPERATIONS_LEDGER_SCHEMA", "OperationalEvent", "OperationsLedger"]
