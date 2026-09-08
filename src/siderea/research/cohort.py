"""Append-only prospective cohort enrollment and exact-version outcome export."""

from __future__ import annotations

import hmac
import json
import math
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from siderea.atomic import atomic_create_binary
from siderea.integrity import verify_candidate_record
from siderea.ledger import OutcomeLedger
from siderea.provenance import digest_value, stable_json
from siderea.research.preregistration import Preregistration

COHORT_REGISTRY_SCHEMA = "siderea.cohort_registry.v1"
COHORT_EXPORT_SCHEMA = "siderea.matured_cohort.v1"


def _aware_timestamp(value: str | None, field: str) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"candidate record has invalid {field}")
    return value.strip()


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"candidate record has invalid {field}")
    return value


def _eligible(record: Mapping[str, Any], policy: str) -> bool:
    quality = record.get("quality")
    gate = record.get("gate")
    if not isinstance(quality, Mapping) or not isinstance(gate, Mapping):
        raise ValueError("candidate record lacks quality or gate evidence")
    if not _boolean(quality.get("passed"), "quality.passed"):
        return False
    decision = _required_text(gate.get("decision"), "gate.decision").casefold()
    if decision in {"reject_known_object", "reject_quality"}:
        return False
    if policy == "gate-clear":
        return decision in {"reportable", "needs_manual_review"}
    return True


@dataclass(frozen=True, slots=True)
class CohortEnrollment:
    study_id: str
    protocol_digest: str
    candidate_id: str
    candidate_version: str
    candidate_record_digest: str
    candidate_run_binding_digest: str
    campaign: str
    enrolled_at: str
    eligible: bool
    selected: bool
    selection_score: float
    selection_stratum: str
    recorded_at: str = ""
    capture_mode: str = "retrospective_reconstruction"
    selection_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CohortSelection:
    candidate: Mapping[str, Any]
    selected: bool
    selection_stratum: str
    selection_metadata: Mapping[str, Any] = field(default_factory=dict)


class CohortRegistry:
    """SQLite cohort registry whose scientific rows cannot be edited or deleted."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS studies (
                    study_id TEXT PRIMARY KEY,
                    protocol_digest TEXT NOT NULL UNIQUE,
                    protocol_json TEXT NOT NULL,
                    registered_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS enrollments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    study_id TEXT NOT NULL REFERENCES studies(study_id),
                    protocol_digest TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    candidate_version TEXT NOT NULL,
                    candidate_record_digest TEXT NOT NULL,
                    candidate_run_binding_digest TEXT NOT NULL,
                    campaign TEXT NOT NULL,
                    enrolled_at TEXT NOT NULL,
                    eligible INTEGER NOT NULL CHECK(eligible IN (0, 1)),
                    selected INTEGER NOT NULL CHECK(selected IN (0, 1)),
                    selection_score REAL NOT NULL,
                    selection_stratum TEXT NOT NULL,
                    UNIQUE(study_id, candidate_id, candidate_version)
                );
                CREATE TRIGGER IF NOT EXISTS cohort_studies_no_update
                BEFORE UPDATE ON studies BEGIN
                    SELECT RAISE(ABORT, 'study registrations are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS cohort_studies_no_delete
                BEFORE DELETE ON studies BEGIN
                    SELECT RAISE(ABORT, 'study registrations are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS cohort_enrollments_no_update
                BEFORE UPDATE ON enrollments BEGIN
                    SELECT RAISE(ABORT, 'cohort enrollments are append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS cohort_enrollments_no_delete
                BEFORE DELETE ON enrollments BEGIN
                    SELECT RAISE(ABORT, 'cohort enrollments are append-only');
                END;
                """
            )

            columns = {str(row["name"]) for row in db.execute("PRAGMA table_info(enrollments)")}
            for name, default in (
                ("recorded_at", ""),
                ("capture_mode", "retrospective_reconstruction"),
                ("selection_metadata_json", "{}"),
            ):
                if name not in columns:
                    db.execute(
                        f"ALTER TABLE enrollments ADD COLUMN {name} "
                        f"TEXT NOT NULL DEFAULT '{default}'"
                    )

    def register(self, preregistration: Preregistration) -> None:
        preregistration = preregistration.validated()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._register(preregistration, db)

    def _register(self, preregistration: Preregistration, db: sqlite3.Connection) -> None:
        content = stable_json(preregistration.to_dict())
        existing = db.execute(
            "SELECT protocol_digest, protocol_json FROM studies WHERE study_id=?",
            (preregistration.study_id,),
        ).fetchone()
        if existing is not None:
            if (
                not hmac.compare_digest(
                    str(existing["protocol_digest"]), preregistration.protocol_digest
                )
                or str(existing["protocol_json"]) != content
            ):
                raise ValueError("study ID is already bound to a different preregistration")
            return
        db.execute(
            """
            INSERT INTO studies(study_id, protocol_digest, protocol_json, registered_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                preregistration.study_id,
                preregistration.protocol_digest,
                content,
                datetime.now(UTC).isoformat(),
            ),
        )

    def enroll(
        self,
        preregistration: Preregistration,
        candidate: Mapping[str, Any],
        *,
        selected: bool,
        selection_stratum: str,
        enrolled_at: str | None = None,
        selection_metadata: Mapping[str, Any] | None = None,
    ) -> CohortEnrollment:
        return self.enroll_batch(
            preregistration,
            [
                CohortSelection(
                    candidate,
                    selected,
                    selection_stratum,
                    {} if selection_metadata is None else selection_metadata,
                )
            ],
            enrolled_at=enrolled_at,
        )[0]

    def enroll_batch(
        self,
        preregistration: Preregistration,
        selections: Sequence[CohortSelection],
        *,
        enrolled_at: str | None = None,
    ) -> tuple[CohortEnrollment, ...]:
        """Atomically register and enroll a batch; any invalid row rolls back all rows."""
        preregistration = preregistration.validated()
        if not selections or any(not isinstance(item, CohortSelection) for item in selections):
            raise ValueError("cohort batch requires non-empty CohortSelection records")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._register(preregistration, db)
            return tuple(
                self._enroll(
                    preregistration,
                    item.candidate,
                    db=db,
                    selected=item.selected,
                    selection_stratum=item.selection_stratum,
                    enrolled_at=enrolled_at,
                    selection_metadata=item.selection_metadata,
                )
                for item in selections
            )

    def _enroll(
        self,
        preregistration: Preregistration,
        candidate: Mapping[str, Any],
        *,
        db: sqlite3.Connection,
        selected: bool,
        selection_stratum: str,
        enrolled_at: str | None = None,
        selection_metadata: Mapping[str, Any] | None = None,
    ) -> CohortEnrollment:
        """Enroll exactly one self-verifying candidate evidence version."""

        if not isinstance(selected, bool):
            raise TypeError("selected must be a boolean")
        if selection_metadata is not None and not isinstance(selection_metadata, Mapping):
            raise ValueError("selection metadata must be an object")
        if not isinstance(selection_stratum, str) or not selection_stratum.strip():
            raise ValueError("selection_stratum must be a non-empty string")
        protocol = preregistration.protocol
        cohort = protocol["cohort"]
        selection = protocol["selection"]
        if not isinstance(cohort, Mapping) or not isinstance(selection, Mapping):
            raise ValueError("preregistration has invalid cohort or selection policy")
        pipeline_version = _required_text(
            selection.get("pipeline_version"), "selection.pipeline_version"
        )
        record_digest = verify_candidate_record(candidate, pipeline_version=pipeline_version)
        candidate_id = _required_text(candidate.get("candidate_id"), "candidate_id")
        version = _required_text(candidate.get("candidate_version"), "candidate_version")
        run_binding = _required_text(
            candidate.get("candidate_run_binding_digest"), "candidate_run_binding_digest"
        )
        campaign = _required_text(candidate.get("campaign"), "campaign")
        scientific_config = candidate.get("scientific_config")
        if not isinstance(scientific_config, Mapping):
            raise ValueError("candidate record lacks scientific_config")
        expected_config_digest = _required_text(
            selection.get("configuration_digest"), "selection.configuration_digest"
        ).casefold()
        if not hmac.compare_digest(digest_value(dict(scientific_config)), expected_config_digest):
            raise ValueError("candidate scientific configuration differs from preregistration")

        instant = _aware_timestamp(enrolled_at, "enrolled_at")
        recorded = datetime.now(UTC)
        capture_mode = "prospective" if enrolled_at is None else "retrospective_reconstruction"
        opens = _aware_timestamp(str(cohort["opens_at"]), "cohort.opens_at")
        closes = _aware_timestamp(str(cohort["closes_at"]), "cohort.closes_at")
        if not opens <= instant <= closes:
            raise ValueError("candidate enrollment is outside the preregistered cohort window")
        eligibility_policy = _required_text(
            selection.get("eligibility_policy"), "selection.eligibility_policy"
        )
        eligible = _eligible(candidate, eligibility_policy)
        if selected and not eligible:
            raise ValueError("an ineligible candidate cannot be recorded as selected")
        score = candidate.get("score")
        if not isinstance(score, Mapping):
            raise ValueError("candidate record lacks score evidence")
        raw_priority = score.get("priority_score")
        if isinstance(raw_priority, bool) or not isinstance(raw_priority, (int, float)):
            raise ValueError("candidate priority score must be numeric")
        priority = float(raw_priority)
        if not math.isfinite(priority):
            raise ValueError("candidate priority score must be finite")

        record = CohortEnrollment(
            study_id=preregistration.study_id,
            protocol_digest=preregistration.protocol_digest,
            candidate_id=candidate_id,
            candidate_version=version,
            candidate_record_digest=record_digest,
            candidate_run_binding_digest=run_binding,
            campaign=campaign,
            enrolled_at=instant.isoformat(),
            eligible=eligible,
            selected=selected,
            selection_score=priority,
            selection_stratum=selection_stratum.strip(),
            recorded_at=recorded.isoformat(),
            capture_mode=capture_mode,
            selection_metadata=dict(selection_metadata or {}),
        )
        existing = db.execute(
            """
            SELECT * FROM enrollments
            WHERE study_id=? AND candidate_id=? AND candidate_version=?
            """,
            (record.study_id, record.candidate_id, record.candidate_version),
        ).fetchone()
        if existing is not None:
            decoded = _row_to_enrollment(existing)
            prior_facts, new_facts = asdict(decoded), asdict(record)
            for field in ("recorded_at", "enrolled_at"):
                if field == "recorded_at" or enrolled_at is None:
                    prior_facts.pop(field)
                    new_facts.pop(field)
            if prior_facts != new_facts:
                raise ValueError("candidate version is already enrolled with different facts")
            return decoded
        if (
            db.execute(
                "SELECT id FROM enrollments WHERE study_id=? AND lower(candidate_id)=lower(?)",
                (record.study_id, candidate_id),
            ).fetchone()
            is not None
        ):
            raise ValueError("study already enrolled this physical entity at another version")
        if selected:
            previous_selected = db.execute(
                "SELECT enrolled_at FROM enrollments WHERE study_id=? AND selected=1",
                (record.study_id,),
            ).fetchall()
            day = instant.astimezone(UTC).date()
            used = sum(
                _aware_timestamp(str(row["enrolled_at"]), "enrolled_at").astimezone(UTC).date()
                == day
                for row in previous_selected
            )
            if used >= int(selection["review_budget"]):
                raise ValueError("preregistered UTC-night review budget is exhausted")
        db.execute(
            """
            INSERT INTO enrollments(
                study_id, protocol_digest, candidate_id, candidate_version,
                candidate_record_digest, candidate_run_binding_digest, campaign,
                enrolled_at, eligible, selected, selection_score, selection_stratum,
                recorded_at, capture_mode, selection_metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.study_id,
                record.protocol_digest,
                record.candidate_id,
                record.candidate_version,
                record.candidate_record_digest,
                record.candidate_run_binding_digest,
                record.campaign,
                record.enrolled_at,
                int(record.eligible),
                int(record.selected),
                record.selection_score,
                record.selection_stratum,
                record.recorded_at,
                record.capture_mode,
                stable_json(record.selection_metadata),
            ),
        )
        return record

    def enrollments(self, study_id: str) -> tuple[CohortEnrollment, ...]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM enrollments WHERE study_id=? ORDER BY id", (study_id.strip(),)
            ).fetchall()
        return tuple(_row_to_enrollment(row) for row in rows)


def _row_to_enrollment(row: sqlite3.Row) -> CohortEnrollment:
    return CohortEnrollment(
        study_id=str(row["study_id"]),
        protocol_digest=str(row["protocol_digest"]),
        candidate_id=str(row["candidate_id"]),
        candidate_version=str(row["candidate_version"]),
        candidate_record_digest=str(row["candidate_record_digest"]),
        candidate_run_binding_digest=str(row["candidate_run_binding_digest"]),
        campaign=str(row["campaign"]),
        enrolled_at=str(row["enrolled_at"]),
        eligible=bool(row["eligible"]),
        selected=bool(row["selected"]),
        selection_score=float(row["selection_score"]),
        selection_stratum=str(row["selection_stratum"]),
        recorded_at=str(row["recorded_at"]),
        capture_mode=str(row["capture_mode"]),
        selection_metadata=json.loads(str(row["selection_metadata_json"])),
    )


def export_matured_cohort(
    preregistration: Preregistration,
    registry: CohortRegistry,
    ledger: OutcomeLedger,
    destination: str | Path,
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Export all enrollments with exact-version outcomes after cohort maturity."""

    preregistration = preregistration.validated()
    evaluation_time = _aware_timestamp(as_of, "as_of")
    cohort = preregistration.protocol["cohort"]
    if not isinstance(cohort, Mapping):
        raise ValueError("preregistration has invalid cohort policy")
    matures_at = _aware_timestamp(str(cohort["matures_at"]), "cohort.matures_at")
    if evaluation_time < matures_at:
        raise ValueError("cohort has not reached its preregistered maturity time")
    analysis = preregistration.protocol["analysis"]
    if not isinstance(analysis, Mapping):
        raise ValueError("preregistration has invalid analysis policy")
    missing_policy = _required_text(
        analysis.get("missing_outcome_policy"), "analysis.missing_outcome_policy"
    )

    rows: list[dict[str, Any]] = []
    missing_outcomes = 0
    for enrollment in registry.enrollments(preregistration.study_id):
        if not hmac.compare_digest(enrollment.protocol_digest, preregistration.protocol_digest):
            raise ValueError("cohort registry mixes preregistration digests")
        archived = ledger.candidate_version(enrollment.candidate_id, enrollment.candidate_version)
        if archived is None:
            raise ValueError(
                f"ledger cannot reconstruct enrolled candidate {enrollment.candidate_id!r} "
                f"version {enrollment.candidate_version!r}"
            )
        outcomes = [
            outcome
            for outcome in ledger.outcomes_for(enrollment.candidate_id)
            if outcome.candidate_version == enrollment.candidate_version
            and _aware_timestamp(outcome.recorded_at, "outcome.recorded_at") <= evaluation_time
        ]
        if not outcomes:
            missing_outcomes += 1
        rows.append(
            {
                **asdict(enrollment),
                "outcome_status": "observed" if outcomes else "missing",
                "outcomes": [asdict(outcome) for outcome in outcomes],
            }
        )
    payload = {
        "schema": COHORT_EXPORT_SCHEMA,
        "study_id": preregistration.study_id,
        "protocol_digest": preregistration.protocol_digest,
        "as_of": evaluation_time.isoformat(),
        "missing_outcome_policy": missing_policy,
        "enrollment_count": len(rows),
        "selected_count": sum(bool(row["selected"]) for row in rows),
        "missing_outcome_count": missing_outcomes,
        "records": rows,
        "capture_mode": (
            "prospective"
            if rows and all(row["capture_mode"] == "prospective" for row in rows)
            else "retrospective_reconstruction"
        ),
    }
    payload["cohort_digest"] = digest_value(payload)
    content = (stable_json(payload) + "\n").encode("utf-8")
    atomic_create_binary(
        Path(destination).expanduser().resolve(), lambda handle: handle.write(content)
    )
    return payload


__all__ = [
    "COHORT_EXPORT_SCHEMA",
    "COHORT_REGISTRY_SCHEMA",
    "CohortEnrollment",
    "CohortRegistry",
    "CohortSelection",
    "export_matured_cohort",
]
