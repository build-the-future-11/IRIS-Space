"""SQLite-backed scientific outcome and independent-review ledger."""

from __future__ import annotations

import hmac
import json
import sqlite3
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from siderea.atomic import RESTORE_MARKER
from siderea.identity import AuthenticatedPrincipal
from siderea.integrity import verify_candidate_version_payload
from siderea.provenance import digest_value

SCHEMA_VERSION = 6
REVIEW_ROLES = frozenset({"screener", "reviewer"})
REVIEW_VERDICTS = frozenset({"approve", "reject", "needs_more_data", "abstain"})
ADJUDICATION_VERDICTS = frozenset({"clear_context", "reject", "needs_more_data"})


def _derived_version_digest(
    candidate_id: str,
    campaign: str,
    payload: Mapping[str, Any],
) -> str:
    """Return the compatibility version for callers without an explicit digest."""

    return digest_value(
        {
            "candidate_id": candidate_id,
            "campaign": campaign,
            "payload": dict(payload),
        }
    )


def _validated_payload_json(
    payload: Mapping[str, Any],
    *,
    candidate_id: str,
    campaign: str,
    version_digest: str,
) -> str:
    """Validate self-verifying pipeline payloads before mutable projection writes."""

    materialized = dict(payload)
    pipeline_version = materialized.get("pipeline_version")
    if pipeline_version is not None:
        if not isinstance(pipeline_version, str) or not pipeline_version.strip():
            raise ValueError("pipeline_version must be a non-empty string")
        verify_candidate_version_payload(
            materialized,
            pipeline_version=pipeline_version,
            expected_candidate_id=candidate_id,
            expected_campaign=campaign,
            expected_version=version_digest,
        )
    return json.dumps(materialized, sort_keys=True, allow_nan=False)


def _decoded_candidate_payload(
    payload_json: str,
    *,
    candidate_id: str,
    campaign: str,
    version_digest: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"candidate {candidate_id!r} has invalid stored JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValueError(f"candidate {candidate_id!r} payload is not a JSON object")
    materialized = dict(payload)
    pipeline_version = materialized.get("pipeline_version")
    if pipeline_version is not None:
        if not isinstance(pipeline_version, str) or not pipeline_version.strip():
            raise ValueError(f"candidate {candidate_id!r} has invalid pipeline_version")
        verify_candidate_version_payload(
            materialized,
            pipeline_version=pipeline_version,
            expected_candidate_id=candidate_id,
            expected_campaign=campaign,
            expected_version=version_digest,
        )
    return materialized


@dataclass(frozen=True)
class ReviewRecord:
    candidate_id: str
    candidate_version: str
    reviewer: str
    role: str
    verdict: str
    reason: str
    created_at: str
    principal_assertion_digest: str = ""
    principal_issuer: str = ""
    principal_subject: str = ""
    principal_assurance: str = ""


@dataclass(frozen=True)
class AdjudicationRecord:
    candidate_id: str
    candidate_version: str
    adjudicator: str
    verdict: str
    reason: str
    created_at: str


@dataclass(frozen=True)
class OutcomeRecord:
    candidate_id: str
    candidate_version: str
    outcome: str
    designation: str
    taxonomy_version: str
    evidence_digest: str
    evidence: Mapping[str, Any]
    recorded_at: str


def _principal_id(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = " ".join(unicodedata.normalize("NFKC", value).split()).casefold()
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def _archive_candidate_version(
    db: sqlite3.Connection,
    *,
    candidate_id: str,
    version_digest: str,
    campaign: str,
    state: str,
    payload_json: str,
    recorded_at: str,
) -> None:
    """Archive the first ledger snapshot observed for an evidence version."""

    db.execute(
        """
        INSERT OR IGNORE INTO candidate_versions(
            candidate_id, version_digest, campaign, state, payload_json, recorded_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            version_digest,
            campaign,
            state,
            payload_json,
            recorded_at,
        ),
    )


class OutcomeLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        if any((parent / RESTORE_MARKER).exists() for parent in self.path.resolve().parents):
            raise ValueError("ledger is inside an incomplete evidence restore; serving is blocked")
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
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidates (
                    candidate_id TEXT PRIMARY KEY,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    campaign TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    version_digest TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
                    candidate_version TEXT NOT NULL DEFAULT '',
                    reviewer TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('screener', 'reviewer')),
                    verdict TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    principal_assertion_digest TEXT NOT NULL DEFAULT '',
                    principal_issuer TEXT NOT NULL DEFAULT '',
                    principal_subject TEXT NOT NULL DEFAULT '',
                    principal_assurance TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS adjudications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
                    candidate_version TEXT NOT NULL,
                    adjudicator TEXT NOT NULL,
                    verdict TEXT NOT NULL CHECK(
                        verdict IN ('clear_context', 'reject', 'needs_more_data')
                    ),
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outcomes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
                    outcome TEXT NOT NULL,
                    designation TEXT NOT NULL DEFAULT '',
                    evidence_json TEXT NOT NULL,
                    candidate_version TEXT NOT NULL DEFAULT '',
                    taxonomy_version TEXT NOT NULL DEFAULT '',
                    evidence_digest TEXT NOT NULL DEFAULT '',
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidate_versions (
                    candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
                    version_digest TEXT NOT NULL,
                    campaign TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(candidate_id, version_digest)
                );
                CREATE TABLE IF NOT EXISTS decision_authentication (
                    review_id INTEGER UNIQUE REFERENCES reviews(id),
                    adjudication_id INTEGER UNIQUE REFERENCES adjudications(id),
                    principal_json TEXT NOT NULL,
                    CHECK ((review_id IS NULL) <> (adjudication_id IS NULL))
                );
                CREATE TRIGGER IF NOT EXISTS decision_authentication_no_update
                BEFORE UPDATE ON decision_authentication BEGIN
                    SELECT RAISE(ABORT, 'decision authentication is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS decision_authentication_no_delete
                BEFORE DELETE ON decision_authentication BEGIN
                    SELECT RAISE(ABORT, 'decision authentication is append-only');
                END;
                """
            )
            metadata_row = db.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
            if metadata_row is not None and int(metadata_row["value"]) > SCHEMA_VERSION:
                raise RuntimeError(
                    "ledger schema is newer than this SIDEREA version; refusing to downgrade it"
                )

            candidate_columns = {
                str(row["name"]) for row in db.execute("PRAGMA table_info(candidates)")
            }
            if "version_digest" not in candidate_columns:
                db.execute(
                    "ALTER TABLE candidates ADD COLUMN version_digest TEXT NOT NULL DEFAULT ''"
                )
            review_columns = {str(row["name"]) for row in db.execute("PRAGMA table_info(reviews)")}
            if "candidate_version" not in review_columns:
                db.execute(
                    "ALTER TABLE reviews ADD COLUMN candidate_version TEXT NOT NULL DEFAULT ''"
                )
            for name in (
                "principal_assertion_digest",
                "principal_issuer",
                "principal_subject",
                "principal_assurance",
            ):
                if name not in review_columns:
                    db.execute(f"ALTER TABLE reviews ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
            outcome_columns = {
                str(row["name"]) for row in db.execute("PRAGMA table_info(outcomes)")
            }
            for name in ("candidate_version", "taxonomy_version", "evidence_digest"):
                if name not in outcome_columns:
                    db.execute(f"ALTER TABLE outcomes ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
            legacy_candidates = db.execute(
                """
                SELECT candidate_id, campaign, payload_json
                FROM candidates
                WHERE version_digest=''
                """
            ).fetchall()
            for candidate in legacy_candidates:
                try:
                    payload = json.loads(str(candidate["payload_json"]))
                except json.JSONDecodeError:
                    payload = {"legacy_payload_json": str(candidate["payload_json"])}
                derived = _derived_version_digest(
                    str(candidate["candidate_id"]),
                    str(candidate["campaign"]),
                    payload,
                )
                db.execute(
                    "UPDATE candidates SET version_digest=? WHERE candidate_id=?",
                    (derived, str(candidate["candidate_id"])),
                )
            db.execute(
                """
                INSERT OR IGNORE INTO candidate_versions(
                    candidate_id, version_digest, campaign, state, payload_json, recorded_at
                )
                SELECT candidate_id, version_digest, campaign, state, payload_json, last_seen
                FROM candidates
                WHERE version_digest<>''
                """
            )
            db.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS candidate_versions_no_update
                BEFORE UPDATE ON candidate_versions
                BEGIN
                    SELECT RAISE(ABORT, 'candidate_versions is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS candidate_versions_no_delete
                BEFORE DELETE ON candidate_versions
                BEGIN
                    SELECT RAISE(ABORT, 'candidate_versions is append-only');
                END;

                DROP TRIGGER IF EXISTS reviews_candidate_version_guard;
                CREATE TRIGGER reviews_candidate_version_guard
                BEFORE INSERT ON reviews
                WHEN NEW.candidate_version='' OR NOT EXISTS (
                    SELECT 1
                    FROM candidate_versions
                    WHERE candidate_id=NEW.candidate_id
                      AND version_digest=NEW.candidate_version
                )
                BEGIN
                    SELECT RAISE(ABORT, 'review references an unknown candidate version');
                END;

                DROP TRIGGER IF EXISTS reviews_invariant_guard;
                CREATE TRIGGER reviews_invariant_guard
                BEFORE INSERT ON reviews
                WHEN trim(NEW.candidate_id, char(9) || char(10) || char(13) || ' ')=''
                  OR trim(NEW.candidate_version, char(9) || char(10) || char(13) || ' ')=''
                  OR trim(NEW.reviewer, char(9) || char(10) || char(13) || ' ')=''
                  OR NEW.role NOT IN ('screener', 'reviewer')
                  OR NEW.verdict NOT IN ('approve', 'reject', 'needs_more_data', 'abstain')
                  OR trim(NEW.reason, char(9) || char(10) || char(13) || ' ')=''
                  OR trim(NEW.created_at, char(9) || char(10) || char(13) || ' ')=''
                  OR (
                    (NEW.principal_assertion_digest='' AND (
                      NEW.principal_issuer<>''
                      OR NEW.principal_subject<>''
                      OR NEW.principal_assurance<>''
                    ))
                    OR (NEW.principal_assertion_digest<>'' AND (
                      length(NEW.principal_assertion_digest)<>64
                      OR trim(NEW.principal_issuer)=''
                      OR trim(NEW.principal_subject)=''
                      OR trim(NEW.principal_assurance)=''
                    ))
                  )
                BEGIN
                    SELECT RAISE(ABORT, 'review violates ledger invariants');
                END;

                DROP TRIGGER IF EXISTS reviews_candidate_version_update_guard;
                DROP TRIGGER IF EXISTS reviews_no_update;
                CREATE TRIGGER reviews_no_update
                BEFORE UPDATE ON reviews
                BEGIN
                    SELECT RAISE(ABORT, 'reviews is append-only');
                END;

                DROP TRIGGER IF EXISTS reviews_no_delete;
                CREATE TRIGGER reviews_no_delete
                BEFORE DELETE ON reviews
                BEGIN
                    SELECT RAISE(ABORT, 'reviews is append-only');
                END;

                DROP TRIGGER IF EXISTS adjudications_candidate_version_guard;
                CREATE TRIGGER adjudications_candidate_version_guard
                BEFORE INSERT ON adjudications
                WHEN NEW.candidate_version='' OR NOT EXISTS (
                    SELECT 1
                    FROM candidate_versions
                    WHERE candidate_id=NEW.candidate_id
                      AND version_digest=NEW.candidate_version
                )
                BEGIN
                    SELECT RAISE(ABORT, 'adjudication references an unknown candidate version');
                END;

                DROP TRIGGER IF EXISTS adjudications_invariant_guard;
                CREATE TRIGGER adjudications_invariant_guard
                BEFORE INSERT ON adjudications
                WHEN trim(NEW.candidate_id, char(9) || char(10) || char(13) || ' ')=''
                  OR trim(NEW.candidate_version, char(9) || char(10) || char(13) || ' ')=''
                  OR trim(NEW.adjudicator, char(9) || char(10) || char(13) || ' ')=''
                  OR NEW.verdict NOT IN ('clear_context', 'reject', 'needs_more_data')
                  OR trim(NEW.reason, char(9) || char(10) || char(13) || ' ')=''
                  OR trim(NEW.created_at, char(9) || char(10) || char(13) || ' ')=''
                BEGIN
                    SELECT RAISE(ABORT, 'adjudication violates ledger invariants');
                END;

                DROP TRIGGER IF EXISTS adjudications_candidate_version_update_guard;
                DROP TRIGGER IF EXISTS adjudications_no_update;
                CREATE TRIGGER adjudications_no_update
                BEFORE UPDATE ON adjudications
                BEGIN
                    SELECT RAISE(ABORT, 'adjudications is append-only');
                END;

                DROP TRIGGER IF EXISTS adjudications_no_delete;
                CREATE TRIGGER adjudications_no_delete
                BEFORE DELETE ON adjudications
                BEGIN
                    SELECT RAISE(ABORT, 'adjudications is append-only');
                END;

                DROP TRIGGER IF EXISTS outcomes_candidate_version_guard;
                CREATE TRIGGER outcomes_candidate_version_guard
                BEFORE INSERT ON outcomes
                WHEN NEW.candidate_version='' OR NOT EXISTS (
                    SELECT 1
                    FROM candidate_versions
                    WHERE candidate_id=NEW.candidate_id
                      AND version_digest=NEW.candidate_version
                )
                BEGIN
                    SELECT RAISE(ABORT, 'outcome references an unknown candidate version');
                END;

                DROP TRIGGER IF EXISTS outcomes_invariant_guard;
                CREATE TRIGGER outcomes_invariant_guard
                BEFORE INSERT ON outcomes
                WHEN trim(NEW.candidate_id, char(9) || char(10) || char(13) || ' ')=''
                  OR trim(NEW.candidate_version, char(9) || char(10) || char(13) || ' ')=''
                  OR trim(NEW.outcome, char(9) || char(10) || char(13) || ' ')=''
                  OR trim(NEW.evidence_json, char(9) || char(10) || char(13) || ' ')=''
                  OR trim(NEW.taxonomy_version, char(9) || char(10) || char(13) || ' ')=''
                  OR trim(NEW.evidence_digest, char(9) || char(10) || char(13) || ' ')=''
                  OR trim(NEW.recorded_at, char(9) || char(10) || char(13) || ' ')=''
                BEGIN
                    SELECT RAISE(ABORT, 'outcome violates ledger invariants');
                END;

                DROP TRIGGER IF EXISTS outcomes_candidate_version_update_guard;
                DROP TRIGGER IF EXISTS outcomes_no_update;
                CREATE TRIGGER outcomes_no_update
                BEFORE UPDATE ON outcomes
                BEGIN
                    SELECT RAISE(ABORT, 'outcomes is append-only');
                END;

                DROP TRIGGER IF EXISTS outcomes_no_delete;
                CREATE TRIGGER outcomes_no_delete
                BEFORE DELETE ON outcomes
                BEGIN
                    SELECT RAISE(ABORT, 'outcomes is append-only');
                END;
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS candidate_versions_recorded_idx
                ON candidate_versions(candidate_id, recorded_at, version_digest)
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS reviews_candidate_version_idx
                ON reviews(candidate_id, candidate_version, id)
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS adjudications_candidate_version_idx
                ON adjudications(candidate_id, candidate_version, id)
                """
            )
            db.execute(
                """
                CREATE INDEX IF NOT EXISTS outcomes_candidate_version_idx
                ON outcomes(candidate_id, candidate_version, id)
                """
            )
            db.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def upsert_candidate(
        self,
        candidate_id: str,
        *,
        campaign: str,
        state: str,
        payload: Mapping[str, Any],
        version_digest: str | None = None,
    ) -> None:
        candidate_id = candidate_id.strip()
        campaign = campaign.strip()
        state = state.strip()
        if not candidate_id or not campaign or not state:
            raise ValueError("candidate_id, campaign, and state are required")
        version = (
            _derived_version_digest(candidate_id, campaign, payload)
            if version_digest is None
            else version_digest.strip()
        )
        if not version:
            raise ValueError("version_digest must not be empty when supplied")
        now = datetime.now(UTC).isoformat()
        payload_json = _validated_payload_json(
            payload,
            candidate_id=candidate_id,
            campaign=campaign,
            version_digest=version,
        )
        with self.connect() as db:
            updated = db.execute(
                """
                INSERT INTO candidates(
                    candidate_id, first_seen, last_seen, campaign, state, payload_json,
                    version_digest
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    last_seen=excluded.last_seen,
                    state=excluded.state,
                    payload_json=excluded.payload_json,
                    version_digest=excluded.version_digest
                WHERE candidates.campaign=excluded.campaign
                """,
                (
                    candidate_id,
                    now,
                    now,
                    campaign,
                    state,
                    payload_json,
                    version,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError(
                    f"candidate_id {candidate_id!r} already belongs to another campaign"
                )
            _archive_candidate_version(
                db,
                candidate_id=candidate_id,
                version_digest=version,
                campaign=campaign,
                state=state,
                payload_json=payload_json,
                recorded_at=now,
            )

    def upsert_candidates(self, records: Sequence[Mapping[str, Any]]) -> None:
        """Atomically publish a complete batch of analyzed candidate records."""

        prepared: list[tuple[str, str, str, str, str]] = []
        seen: set[str] = set()
        for record in records:
            candidate_id = str(record.get("candidate_id", "")).strip()
            campaign = str(record.get("campaign", "")).strip()
            state = str(record.get("state", "")).strip()
            version = str(record.get("version_digest", "")).strip()
            payload = record.get("payload")
            if not candidate_id or not campaign or not state or not version:
                raise ValueError(
                    "every candidate update needs candidate_id, campaign, state, and version_digest"
                )
            if not isinstance(payload, Mapping):
                raise TypeError("every candidate update payload must be a mapping")
            if candidate_id in seen:
                raise ValueError(f"duplicate candidate_id in ledger batch: {candidate_id!r}")
            seen.add(candidate_id)
            prepared.append(
                (
                    candidate_id,
                    campaign,
                    state,
                    _validated_payload_json(
                        payload,
                        candidate_id=candidate_id,
                        campaign=campaign,
                        version_digest=version,
                    ),
                    version,
                )
            )
        if not prepared:
            return
        now = datetime.now(UTC).isoformat()
        with self.connect() as db:
            for candidate_id, campaign, state, payload_json, version in prepared:
                updated = db.execute(
                    """
                    INSERT INTO candidates(
                        candidate_id, first_seen, last_seen, campaign, state, payload_json,
                        version_digest
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(candidate_id) DO UPDATE SET
                        last_seen=excluded.last_seen,
                        state=excluded.state,
                        payload_json=excluded.payload_json,
                        version_digest=excluded.version_digest
                    WHERE candidates.campaign=excluded.campaign
                    """,
                    (candidate_id, now, now, campaign, state, payload_json, version),
                )
                if updated.rowcount != 1:
                    raise ValueError(
                        f"candidate_id {candidate_id!r} already belongs to another campaign"
                    )
                _archive_candidate_version(
                    db,
                    candidate_id=candidate_id,
                    version_digest=version,
                    campaign=campaign,
                    state=state,
                    payload_json=payload_json,
                    recorded_at=now,
                )

    def add_review(
        self,
        candidate_id: str,
        *,
        candidate_version: str,
        reviewer: str,
        role: str,
        verdict: str,
        reason: str,
        principal: AuthenticatedPrincipal | None = None,
    ) -> ReviewRecord:
        candidate_id = candidate_id.strip()
        reviewer = _principal_id(reviewer, "reviewer")
        role = role.strip().casefold()
        verdict = verdict.strip().casefold()
        reason = reason.strip()
        principal_digest = ""
        principal_issuer = ""
        principal_subject = ""
        principal_assurance = ""
        if principal is not None:
            principal_reviewer = _principal_id(principal.principal_id, "principal_id")
            if reviewer != principal_reviewer:
                raise ValueError("reviewer identity differs from the authenticated principal")
            if role not in principal.roles:
                raise ValueError("authenticated principal does not authorize the review role")
            principal_digest = principal.assertion_digest
            principal_issuer = principal.issuer
            principal_subject = principal.subject
            principal_assurance = principal.assurance_level
        if role not in REVIEW_ROLES:
            raise ValueError("role must be screener or reviewer")
        if verdict not in REVIEW_VERDICTS:
            raise ValueError("verdict must be one of " + ", ".join(sorted(REVIEW_VERDICTS)))
        expected_version = candidate_version.strip()
        if not candidate_id or not reason or not expected_version:
            raise ValueError("candidate_id, candidate_version, and reason are required")
        created_at = datetime.now(UTC).isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            candidate = db.execute(
                "SELECT version_digest, payload_json FROM candidates WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
            if candidate is None:
                raise ValueError(f"unknown candidate in ledger: {candidate_id}")
            self._authorize_decision(candidate, principal, role)
            current_version = str(candidate["version_digest"])
            if not current_version:
                raise ValueError(
                    "candidate has no immutable version digest; upsert it with "
                    "version_digest before review"
                )
            if expected_version != current_version:
                raise ValueError("candidate changed after the reviewed version was loaded")
            inserted = db.execute(
                """
                INSERT INTO reviews(
                    candidate_id, candidate_version, reviewer, role, verdict, reason, created_at,
                    principal_assertion_digest, principal_issuer, principal_subject,
                    principal_assurance
                )
                SELECT candidate_id, version_digest, ?, ?, ?, ?, ?, ?, ?, ?, ?
                FROM candidates
                WHERE candidate_id=? AND version_digest=?
                """,
                (
                    reviewer,
                    role,
                    verdict,
                    reason,
                    created_at,
                    principal_digest,
                    principal_issuer,
                    principal_subject,
                    principal_assurance,
                    candidate_id,
                    expected_version,
                ),
            )
            if inserted.rowcount != 1:
                raise ValueError("candidate changed while the review was being recorded")
            if principal is not None:
                db.execute(
                    "INSERT INTO decision_authentication(review_id, principal_json) VALUES (?, ?)",
                    (inserted.lastrowid, json.dumps(asdict(principal), sort_keys=True)),
                )
        return ReviewRecord(
            candidate_id,
            current_version,
            reviewer,
            role,
            verdict,
            reason,
            created_at,
            principal_digest,
            principal_issuer,
            principal_subject,
            principal_assurance,
        )

    def reviews_for(
        self,
        candidate_id: str,
        *,
        candidate_version: str | None = None,
    ) -> list[ReviewRecord]:
        with self.connect() as db:
            if candidate_version is None:
                rows = db.execute(
                    """
                    SELECT candidate_id, candidate_version, reviewer, role, verdict, reason,
                           created_at, principal_assertion_digest, principal_issuer,
                           principal_subject, principal_assurance
                    FROM reviews
                    WHERE candidate_id=?
                    ORDER BY id
                    """,
                    (candidate_id,),
                ).fetchall()
            else:
                rows = db.execute(
                    """
                    SELECT candidate_id, candidate_version, reviewer, role, verdict, reason,
                           created_at, principal_assertion_digest, principal_issuer,
                           principal_subject, principal_assurance
                    FROM reviews
                    WHERE candidate_id=? AND candidate_version=?
                    ORDER BY id
                    """,
                    (candidate_id, candidate_version),
                ).fetchall()
        return [ReviewRecord(**dict(row)) for row in rows]

    def add_adjudication(
        self,
        candidate_id: str,
        *,
        adjudicator: str,
        verdict: str,
        reason: str,
        candidate_version: str,
        principal: AuthenticatedPrincipal | None = None,
    ) -> AdjudicationRecord:
        """Append a version-bound scientific resolution of ambiguous context."""

        candidate_id = candidate_id.strip()
        adjudicator = _principal_id(adjudicator, "adjudicator")
        if principal is not None and adjudicator != _principal_id(
            principal.principal_id, "principal"
        ):
            raise ValueError("adjudicator differs from authenticated principal")
        verdict = verdict.strip().casefold()
        reason = reason.strip()
        expected_version = candidate_version.strip()
        if verdict not in ADJUDICATION_VERDICTS:
            raise ValueError(
                "adjudication verdict must be one of " + ", ".join(sorted(ADJUDICATION_VERDICTS))
            )
        if not candidate_id or not reason or not expected_version:
            raise ValueError("candidate_id, candidate_version, and reason are required")
        created_at = datetime.now(UTC).isoformat()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            candidate = db.execute(
                "SELECT payload_json FROM candidates WHERE candidate_id=?", (candidate_id,)
            ).fetchone()
            if candidate is None:
                raise ValueError("unknown candidate")
            self._authorize_decision(candidate, principal, "adjudicator")
            inserted = db.execute(
                """
                INSERT INTO adjudications(
                    candidate_id, candidate_version, adjudicator, verdict, reason, created_at
                )
                SELECT candidate_id, version_digest, ?, ?, ?, ?
                FROM candidates
                WHERE candidate_id=? AND version_digest=?
                """,
                (
                    adjudicator,
                    verdict,
                    reason,
                    created_at,
                    candidate_id,
                    expected_version,
                ),
            )
            if inserted.rowcount != 1:
                raise ValueError("candidate changed after the adjudicated version was loaded")
            if principal is not None:
                db.execute(
                    "INSERT INTO decision_authentication(adjudication_id, principal_json) "
                    "VALUES (?, ?)",
                    (inserted.lastrowid, json.dumps(asdict(principal), sort_keys=True)),
                )
        return AdjudicationRecord(
            candidate_id,
            expected_version,
            adjudicator,
            verdict,
            reason,
            created_at,
        )

    def adjudications_for(
        self,
        candidate_id: str,
        *,
        candidate_version: str | None = None,
    ) -> list[AdjudicationRecord]:
        with self.connect() as db:
            if candidate_version is None:
                rows = db.execute(
                    """
                    SELECT candidate_id, candidate_version, adjudicator, verdict, reason,
                           created_at
                    FROM adjudications
                    WHERE candidate_id=?
                    ORDER BY id
                    """,
                    (candidate_id,),
                ).fetchall()
            else:
                rows = db.execute(
                    """
                    SELECT candidate_id, candidate_version, adjudicator, verdict, reason,
                           created_at
                    FROM adjudications
                    WHERE candidate_id=? AND candidate_version=?
                    ORDER BY id
                    """,
                    (candidate_id, candidate_version),
                ).fetchall()
        return [AdjudicationRecord(**dict(row)) for row in rows]

    def manual_adjudication(
        self,
        candidate_id: str,
        *,
        candidate_version: str,
    ) -> tuple[bool, str]:
        """Return whether ambiguous catalogue context was explicitly cleared."""

        candidate = self.candidate(candidate_id)
        expected_version = candidate_version.strip()
        if candidate is None:
            return False, "candidate is absent from the ledger"
        if not expected_version or expected_version != str(candidate["version_digest"]):
            return False, "requested candidate version is not the current ledger version"
        records = self.adjudications_for(
            candidate_id,
            candidate_version=expected_version,
        )
        latest: dict[str, AdjudicationRecord] = {}
        for record in records:
            latest[_principal_id(record.adjudicator, "adjudicator")] = record
        active = tuple(latest.values())
        if (
            candidate.get("payload", {})
            .get("review_policy", {})
            .get("require_authenticated", False)
        ):
            authenticated = self._authenticated_decisions(
                candidate_id, candidate_version, "adjudications"
            )
            active = tuple(
                record
                for record in active
                if (record.adjudicator, record.created_at) in authenticated
            )
        rejecting = sorted(record.adjudicator for record in active if record.verdict == "reject")
        if rejecting:
            return False, "unresolved scientific rejection from " + ", ".join(rejecting)
        clearing = sorted(
            record.adjudicator for record in active if record.verdict == "clear_context"
        )
        if not clearing:
            return False, "ambiguous catalogue context needs scientific adjudication"
        return True, "catalogue context cleared by " + ", ".join(clearing)

    def independent_approval(
        self,
        candidate_id: str,
        *,
        required_reviewers: int = 1,
        candidate_version: str | None = None,
        require_authenticated: bool = False,
    ) -> tuple[bool, str]:
        if required_reviewers < 1:
            raise ValueError("required_reviewers must be at least one")
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT
                    candidates.version_digest AS current_version,
                    reviews.candidate_id,
                    reviews.candidate_version,
                    reviews.reviewer,
                    reviews.role,
                    reviews.verdict,
                    reviews.reason,
                    reviews.created_at,
                    reviews.principal_assertion_digest,
                    reviews.principal_issuer,
                    reviews.principal_subject,
                    reviews.principal_assurance
                FROM candidates
                LEFT JOIN reviews
                  ON reviews.candidate_id=candidates.candidate_id
                 AND reviews.candidate_version=candidates.version_digest
                WHERE candidates.candidate_id=?
                ORDER BY reviews.id
                """,
                (candidate_id,),
            ).fetchall()
        if not rows:
            return False, "candidate is absent from the ledger"
        current_version = str(rows[0]["current_version"])
        if not current_version:
            return False, "candidate has no immutable version digest"
        if candidate_version is not None and candidate_version.strip() != current_version:
            return False, "requested candidate version is not the current ledger version"
        reviews = [
            ReviewRecord(
                candidate_id=str(row["candidate_id"]),
                candidate_version=str(row["candidate_version"]),
                reviewer=str(row["reviewer"]),
                role=str(row["role"]),
                verdict=str(row["verdict"]),
                reason=str(row["reason"]),
                created_at=str(row["created_at"]),
                principal_assertion_digest=str(row["principal_assertion_digest"]),
                principal_issuer=str(row["principal_issuer"]),
                principal_subject=str(row["principal_subject"]),
                principal_assurance=str(row["principal_assurance"]),
            )
            for row in rows
            if row["reviewer"] is not None
        ]
        latest: dict[tuple[str, str], ReviewRecord] = {}
        for review in reviews:
            latest[(_principal_id(review.reviewer, "reviewer"), review.role)] = review
        active = tuple(latest.values())
        candidate = self.candidate(candidate_id)
        policy = (candidate or {}).get("payload", {}).get("review_policy", {})
        require_authenticated = require_authenticated or policy.get("require_authenticated", False)
        authenticated = self._authenticated_decisions(candidate_id, current_version, "reviews")
        rejecting = sorted(
            {
                _principal_id(review.reviewer, "reviewer")
                for review in active
                if review.verdict == "reject"
            }
        )
        if rejecting:
            return False, "unresolved rejection from " + ", ".join(rejecting)
        if not isinstance(require_authenticated, bool):
            raise TypeError("require_authenticated must be a boolean")
        approved = tuple(
            review
            for review in active
            if not require_authenticated or (review.reviewer, review.created_at) in authenticated
        )
        screeners = {
            _principal_id(review.reviewer, "reviewer")
            for review in approved
            if review.role == "screener" and review.verdict == "approve"
        }
        reviewers = {
            _principal_id(review.reviewer, "reviewer")
            for review in approved
            if review.role == "reviewer" and review.verdict == "approve"
        }
        if not screeners:
            qualifier = "authenticated " if require_authenticated else ""
            return False, f"missing {qualifier}screener approval"
        independent_reviewers = reviewers - screeners
        if reviewers and not independent_reviewers:
            return False, "screener and reviewer must be different people"
        if len(independent_reviewers) < required_reviewers:
            return False, (
                f"need {required_reviewers} reviewer approval(s) from people who are not "
                f"screeners; have {len(independent_reviewers)}"
            )
        return True, "independent approvals recorded"

    @staticmethod
    def _authorize_decision(
        candidate: sqlite3.Row,
        principal: AuthenticatedPrincipal | None,
        role: str,
    ) -> None:
        policy = json.loads(str(candidate["payload_json"])).get("review_policy", {})
        required = policy.get("require_authenticated", False)
        if not isinstance(required, bool):
            raise ValueError("invalid candidate authentication policy")
        trusted = policy.get("trusted_assertion_key_ids", ())
        if required and (principal is None or not trusted):
            raise ValueError("candidate requires an authenticated principal under trusted keys")
        if principal is not None:
            principal.require_current(role, trusted)

    def _authenticated_decisions(
        self,
        candidate_id: str,
        version: str,
        kind: str,
    ) -> set[tuple[str, str]]:
        table, foreign_key, actor = (
            ("reviews", "review_id", "reviewer")
            if kind == "reviews"
            else ("adjudications", "adjudication_id", "adjudicator")
        )
        candidate = self.candidate_version(candidate_id, version)
        trusted = (
            (candidate or {})
            .get("payload", {})
            .get("review_policy", {})
            .get("trusted_assertion_key_ids", ())
        )
        with self.connect() as db:
            rows = db.execute(
                f"SELECT d.{actor} AS actor, d.created_at, a.principal_json "
                f"FROM {table} d JOIN decision_authentication a ON a.{foreign_key}=d.id "
                "WHERE d.candidate_id=? AND d.candidate_version=?",
                (candidate_id, version),
            ).fetchall()
        result: set[tuple[str, str]] = set()
        for row in rows:
            principal = json.loads(str(row["principal_json"]))
            if (not trusted or principal.get("key_id") in trusted) and principal.get(
                "principal_id"
            ) == row["actor"]:
                result.add((str(row["actor"]), str(row["created_at"])))
        return result

    def record_outcome(
        self,
        candidate_id: str,
        *,
        outcome: str,
        designation: str = "",
        evidence: Mapping[str, Any] | None = None,
        candidate_version: str,
        taxonomy_version: str = "siderea.outcome.v1",
    ) -> OutcomeRecord:
        candidate_id = candidate_id.strip()
        outcome = outcome.strip().casefold()
        designation = designation.strip()
        candidate_version = candidate_version.strip()
        taxonomy_version = taxonomy_version.strip()
        if not candidate_id or not outcome or not candidate_version or not taxonomy_version:
            raise ValueError(
                "candidate_id, candidate_version, outcome, and taxonomy_version are required"
            )
        evidence_payload = dict(evidence or {})
        evidence_digest = digest_value(evidence_payload)
        now = datetime.now(UTC).isoformat()
        with self.connect() as db:
            inserted = db.execute(
                """
                INSERT INTO outcomes(
                    candidate_id, outcome, designation, evidence_json, candidate_version,
                    taxonomy_version, evidence_digest, recorded_at
                )
                SELECT candidate_id, ?, ?, ?, version_digest, ?, ?, ?
                FROM candidates
                WHERE candidate_id=? AND version_digest=?
                """,
                (
                    outcome,
                    designation,
                    json.dumps(evidence_payload, sort_keys=True, allow_nan=False),
                    taxonomy_version,
                    evidence_digest,
                    now,
                    candidate_id,
                    candidate_version,
                ),
            )
            if inserted.rowcount != 1:
                raise ValueError("candidate changed after the outcome evidence version was loaded")
        return OutcomeRecord(
            candidate_id=candidate_id,
            candidate_version=candidate_version,
            outcome=outcome,
            designation=designation,
            taxonomy_version=taxonomy_version,
            evidence_digest=evidence_digest,
            evidence=evidence_payload,
            recorded_at=now,
        )

    def outcomes_for(self, candidate_id: str) -> list[OutcomeRecord]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT candidate_id, candidate_version, outcome, designation,
                       taxonomy_version, evidence_digest, evidence_json, recorded_at
                FROM outcomes
                WHERE candidate_id=?
                ORDER BY id
                """,
                (candidate_id,),
            ).fetchall()
        outcomes: list[OutcomeRecord] = []
        for row in rows:
            candidate = str(row["candidate_id"])
            try:
                evidence = json.loads(str(row["evidence_json"]))
            except json.JSONDecodeError as exc:
                raise ValueError(f"outcome for candidate {candidate!r} has invalid JSON") from exc
            if not isinstance(evidence, Mapping):
                raise ValueError(f"outcome for candidate {candidate!r} has non-object evidence")
            stored_digest = str(row["evidence_digest"])
            computed_digest = digest_value(dict(evidence))
            if not hmac.compare_digest(stored_digest, computed_digest):
                raise ValueError(f"outcome for candidate {candidate!r} fails evidence integrity")
            outcomes.append(
                OutcomeRecord(
                    candidate_id=candidate,
                    candidate_version=str(row["candidate_version"]),
                    outcome=str(row["outcome"]),
                    designation=str(row["designation"]),
                    taxonomy_version=str(row["taxonomy_version"]),
                    evidence_digest=stored_digest,
                    evidence=dict(evidence),
                    recorded_at=str(row["recorded_at"]),
                )
            )
        return outcomes

    def candidate(self, candidate_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM candidates WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["payload"] = _decoded_candidate_payload(
            str(result.pop("payload_json")),
            candidate_id=str(result["candidate_id"]),
            campaign=str(result["campaign"]),
            version_digest=str(result["version_digest"]),
        )
        return result

    def candidate_version(
        self,
        candidate_id: str,
        version_digest: str,
    ) -> dict[str, Any] | None:
        """Return the immutable first-seen snapshot for one evidence version."""

        candidate_id = candidate_id.strip()
        version_digest = version_digest.strip()
        if not candidate_id or not version_digest:
            return None
        with self.connect() as db:
            row = db.execute(
                """
                SELECT candidate_id, version_digest, campaign, state, payload_json, recorded_at
                FROM candidate_versions
                WHERE candidate_id=? AND version_digest=?
                """,
                (candidate_id, version_digest),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["payload"] = _decoded_candidate_payload(
            str(result.pop("payload_json")),
            candidate_id=str(result["candidate_id"]),
            campaign=str(result["campaign"]),
            version_digest=str(result["version_digest"]),
        )
        return result

    def candidate_versions_for(self, candidate_id: str) -> list[dict[str, Any]]:
        """Return all immutable evidence-version snapshots in first-seen order."""

        with self.connect() as db:
            rows = db.execute(
                """
                SELECT candidate_id, version_digest, campaign, state, payload_json, recorded_at
                FROM candidate_versions
                WHERE candidate_id=?
                ORDER BY recorded_at, version_digest
                """,
                (candidate_id.strip(),),
            ).fetchall()
        snapshots: list[dict[str, Any]] = []
        for row in rows:
            snapshot = dict(row)
            snapshot["payload"] = _decoded_candidate_payload(
                str(snapshot.pop("payload_json")),
                candidate_id=str(snapshot["candidate_id"]),
                campaign=str(snapshot["campaign"]),
                version_digest=str(snapshot["version_digest"]),
            )
            snapshots.append(snapshot)
        return snapshots

    def list_candidates(
        self,
        *,
        state: str | None = None,
        limit: int = 100,
        offset: int = 0,
        search: str = "",
    ) -> list[dict[str, Any]]:
        """Return the most recently seen candidates for review tooling."""

        if type(limit) is not int or limit < 1 or limit > 10_000:
            raise ValueError("limit must be within [1, 10000]")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        if not isinstance(search, str) or len(search) > 200:
            raise ValueError("search must be a string of at most 200 characters")
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM candidates WHERE (? IS NULL OR state=?) "
                "AND instr(lower(candidate_id), lower(?)) > 0 "
                "ORDER BY last_seen DESC, candidate_id LIMIT ? OFFSET ?",
                (state, state, search.strip(), limit, offset),
            ).fetchall()
        candidates: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = _decoded_candidate_payload(
                str(item.pop("payload_json")),
                candidate_id=str(item["candidate_id"]),
                campaign=str(item["campaign"]),
                version_digest=str(item["version_digest"]),
            )
            candidates.append(item)
        return candidates
