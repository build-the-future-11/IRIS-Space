-- Synthetic fixture generated using pre-migration schema-5 implementation.
-- Source SHA256: 54de485f5f603e186acf36344429dbbfb576c924411a1bced973c48a34b9787c
BEGIN TRANSACTION;
CREATE TABLE adjudications (
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
CREATE TABLE candidate_versions (
                    candidate_id TEXT NOT NULL REFERENCES candidates(candidate_id),
                    version_digest TEXT NOT NULL,
                    campaign TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    PRIMARY KEY(candidate_id, version_digest)
                );
INSERT INTO "candidate_versions" VALUES('migration-example','v1','synthetic','review','{}','2026-09-08T04:40:10.734751+00:00');
CREATE TABLE candidates (
                    candidate_id TEXT PRIMARY KEY,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    campaign TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    version_digest TEXT NOT NULL DEFAULT ''
                );
INSERT INTO "candidates" VALUES('migration-example','2026-09-08T04:40:10.734751+00:00','2026-09-08T04:40:10.734751+00:00','synthetic','review','{}','v1');
CREATE TABLE metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
INSERT INTO "metadata" VALUES('schema_version','5');
CREATE TABLE outcomes (
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
INSERT INTO "outcomes" VALUES(1,'migration-example','synthetic','','{"binary_label": 1}','v1','siderea.outcome.v1','8e79e08b3859fc026a5923cf57824f28e93c046d5059c2d89b06a5422bcf6c13','2026-09-08T04:40:10.742019+00:00');
CREATE TABLE reviews (
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
INSERT INTO "reviews" VALUES(1,'migration-example','v1','legacy-reviewer','reviewer','approve','Synthetic historical named review','2026-09-08T04:40:10.738892+00:00','','','','');
CREATE TRIGGER candidate_versions_no_update
                BEFORE UPDATE ON candidate_versions
                BEGIN
                    SELECT RAISE(ABORT, 'candidate_versions is append-only');
                END;
CREATE TRIGGER candidate_versions_no_delete
                BEFORE DELETE ON candidate_versions
                BEGIN
                    SELECT RAISE(ABORT, 'candidate_versions is append-only');
                END;
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
CREATE TRIGGER reviews_no_update
                BEFORE UPDATE ON reviews
                BEGIN
                    SELECT RAISE(ABORT, 'reviews is append-only');
                END;
CREATE TRIGGER reviews_no_delete
                BEFORE DELETE ON reviews
                BEGIN
                    SELECT RAISE(ABORT, 'reviews is append-only');
                END;
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
CREATE TRIGGER adjudications_no_update
                BEFORE UPDATE ON adjudications
                BEGIN
                    SELECT RAISE(ABORT, 'adjudications is append-only');
                END;
CREATE TRIGGER adjudications_no_delete
                BEFORE DELETE ON adjudications
                BEGIN
                    SELECT RAISE(ABORT, 'adjudications is append-only');
                END;
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
CREATE TRIGGER outcomes_no_update
                BEFORE UPDATE ON outcomes
                BEGIN
                    SELECT RAISE(ABORT, 'outcomes is append-only');
                END;
CREATE TRIGGER outcomes_no_delete
                BEFORE DELETE ON outcomes
                BEGIN
                    SELECT RAISE(ABORT, 'outcomes is append-only');
                END;
CREATE INDEX candidate_versions_recorded_idx
                ON candidate_versions(candidate_id, recorded_at, version_digest)
                ;
CREATE INDEX reviews_candidate_version_idx
                ON reviews(candidate_id, candidate_version, id)
                ;
CREATE INDEX adjudications_candidate_version_idx
                ON adjudications(candidate_id, candidate_version, id)
                ;
CREATE INDEX outcomes_candidate_version_idx
                ON outcomes(candidate_id, candidate_version, id)
                ;
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('reviews',1);
INSERT INTO "sqlite_sequence" VALUES('outcomes',1);
COMMIT;
