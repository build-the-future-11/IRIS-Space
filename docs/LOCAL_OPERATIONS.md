# Local review, evidence and recovery operations

These procedures operate on local research data. They do not submit reports or
establish live/scientific qualification. Run `siderea COMMAND --help` for exact
arguments. Names such as `study.json` below denote files from your own workflow,
not supplied scientific results.

## Review authentication

Default research mode records typed names as audit labels. To require authenticated
decisions, set `review.require_authenticated = true` and
`review.trusted_assertion_key_ids` to the SHA-256 IDs of approved assertion keys in
the TOML configuration **before analysis**. The policy is included in immutable
candidate evidence. Changing it produces a different scientific version; old
named reviews are not upgraded into authenticated approvals.

Assertions must be signed by a trusted issuer, use audience `siderea`, authorize
the required role and expire within 24 hours. The key is at least 32 bytes and
must be protected outside the repository. HMAC verification is not an identity
provider: anyone possessing the signing key can mint a principal. Deployment
requires an actual issuer, custody/rotation policy and independently assigned
reviewers.

Both `review-add` and `adjudication-add` accept `--principal-assertion` and
`--principal-key`; the verified principal supplies the actor identity. An explicitly
supplied actor must match. Adjudication requires the `adjudicator` role.

```bash
siderea review-serve --principal-assertion reviewer-assertion.json --principal-key /secure/issuer.key
```

The browser server reloads the assertion/key for each request. Identity is read-only
in the form, roles come from the principal, and writes recheck expiry and the
candidate's trusted-key policy. Unreadable/expired sessions fail closed. This is
one local signed session; it is not a shared multi-user login implementation.
No remote binding should be treated as safe merely because assertions exist.

Ledger schema 6 adds append-only decision-authentication records linked to exact
review/adjudication rows, including the verified envelope. Existing historical
reviews remain reconstructable and keep their original assurance level. Back up
the database and linked run artifacts before a release upgrade.

## Bound cohort enrollment

Freeze the protocol before its intake window. New studies intended for comparison
must name `analysis.reference_score` as well as the comparison score. Choose the
population, useful effect and missing-outcome policy before observing results.

Generate a review set using the existing `review-set` command, then import its
selection directly:

```bash
siderea cohort-enroll study.json candidates.json cohort.sqlite --review-set review-set-directory
siderea cohort-export study.json cohort.sqlite outcomes.sqlite matured-cohort.json
```

The importer verifies archived input/artifact hashes, exact candidate versions,
review-set identity and deterministic queue allocation. Budget, audit reserve and
eligibility policy must agree with the frozen protocol. Every candidate in the
supplied file is enrolled, including unselected/ineligible rows; route and audit
metadata are retained. This does not prove the supplied file includes every
upstream arrival. Reconcile the intake denominator separately.

New review sets retain the anomaly threshold in their identity. Older bundles
without allocation parameters remain historical evidence but must be regenerated
for verified cohort import. Do not edit their manifests to manufacture provenance.

Without `--review-set`, explicit `--selected-id` enrollment remains available for
local reconstruction. Supplying `--enrolled-at` marks capture as retrospective;
it cannot satisfy prospective qualification. New capture records use server time.
The registry enforces one physical identifier per study and a UTC-night selected
budget. CLI batches now commit atomically, including study registration; any invalid
row or exhausted budget rolls back the whole batch. Exact retries remain idempotent.

## Benchmark and diagnostic scope

```bash
siderea benchmark-run study.json scores.csv benchmark.json \
  --entity candidate_id --time mjd --label binary_label \
  --scores baseline model --time-block-days 1 --cohort matured-cohort.json
```

Outcome evidence must contain an explicit integer `binary_label` of 0 or 1. The
benchmark must use exactly the evaluable cohort entities/labels and frozen budget,
confidence, bootstrap count and seed. Derived summaries are recomputed from stored
evaluation inputs during binding. Missing/censored outcomes are not silently
converted to negative labels.

The benchmark evaluates **precomputed scores**. It does not refit each model or
prove its training/feature cutoff. The known-template injection diagnostic also
does not run the complete production selection pipeline. `promotion-check` emits
`siderea.promotion_report.v2`; even a ready report means local evidence is ready
for independent review, not scientific or production release approval. Version-1
promotion consumers must update their gate/status handling and recompute evidence
before new signoffs.

## Archive and incident recovery

```bash
siderea broker-inventory broker.sqlite
siderea broker-check broker.sqlite
siderea dead-letter-resolve broker.sqlite 1 resolution-evidence.json --reason "Replayed and verified"
siderea incident-resolve operations.sqlite INCIDENT_ID resolution-evidence.json --reason "Recovery verified"
siderea recovery-check operations.sqlite outcomes.sqlite
siderea ops-health operations.sqlite
```

`broker-check` actually reconstructs and parses archived snapshots. Exact retries
return their original archive record without rewinding the live cursor; changing
cursor/watermark facts for the same snapshot is rejected. Dead-letter resolution
retains original bytes and appends a reason plus nonempty evidence.

Incident resolution references a recorded error/critical event and preserves it.
Health reports distinguish total/resolved/unresolved failures and compare aware
timestamps by instant. An empty event log is not healthy. `recovery-drill` records
operator evidence; `recovery-check` actually performs an online SQLite backup into
temporary storage, checks integrity/foreign keys and compares row counts. It does
not restore the external files referenced by that database. Full disaster recovery
must include run/dossier/model artifacts and their digests.

## Fixture and asset limits

Fixture recording rejects recognized nested credential fields, userinfo/token URLs,
cookies and credential-bearing structured/text bodies before publication. It does
not silently redact bytes. Sanitize approved captures before recording and retain
sanitation provenance externally; opaque binary content cannot be exhaustively
secret-scanned. A `live` capture label is an operator assertion, not independent
proof that an adapter was exercised.

Asset bundles check file integrity, role completeness, calibration types/coordinate
ranges and candidate position association. They do not independently validate FITS,
WCS, survey calibration or astrophysical interpretation.

## Build and validation

```bash
python -m pip install -e '.[all,dev]'
python -m pip check
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy src/siderea
python -m pytest -q --cov=siderea --cov-report=term-missing
python -m build
```

HTTP integration tests bind a temporary loopback port; a sandbox that forbids all
socket binding must grant local-test permission. Do not disable the test to obtain
a green run. After package renames, preserve/move aside stale generated `build/`
output before direct source installation. The release build should produce the
sdist and then its wheel in clean build directories; inspect the wheel for retired
package names and install it into a fresh environment. A successful local build
does not establish that remote CI or live services passed.

## Evidence-complete offline recovery

```bash
siderea evidence-backup /data/siderea/outcomes.sqlite /data/siderea /backups/siderea.zip --include /data/siderea/dossiers
siderea evidence-backup-verify /backups/siderea.zip
siderea evidence-restore /backups/siderea.zip /data/siderea
```

The backup takes an online SQLite snapshot and includes all run artifacts referenced
by current and historical candidate publications. Explicit additional ordinary files
can include models and dossiers. Verification checks both archived bytes and
publication references, even when original files are unavailable. A rehashed archive
inventory cannot conceal a missing referenced artifact. Other live databases require
separate consistent snapshots; this is not a coordinated multi-database backup.

Restore is offline and requires the original absolute root to be absent. Stop writers
and preserve the existing directory elsewhere before restoring. Existing data is never
overwritten. Absolute publication bindings are retained. An interrupted restore leaves
a marker that blocks ledger access and subsequent backups; preserve that failed directory
for diagnosis, then retry into the absent original root. Do not remove the marker to
bypass verification.

## Outcome dashboard and parser qualification

`siderea outcome-summary --ledger outcomes.sqlite` emits campaign-level JSON; the local
review server exposes the same summary at `/outcomes`. Counts use current candidate
versions, latest exact-version outcomes and active reviewer decisions. Missing outcomes
are explicit. Yield is conditional on reviewed, binary-labeled candidates, not a claim
about population precision. The dashboard shares the server's session protections.

```bash
siderea fixture-qualify-tns query.json qualification.json fixture-search.json fixture-cone.json --expected-status clear
```

The query contains `internal_name`, `ra`, `dec` and `radius_arcsec`. Fixtures must match
the production adapter's exact public request representation (endpoint and query).
The runner uses the actual TNS parser, consumes all specified fixtures and has no
network fallback. Unmatched requests fail even when an error outcome was expected.
The report records fixture identities and adapter source digest. This qualifies a
recorded parser case only; it does not establish live service access or qualify other
catalogue adapters.

Candidate pages also provide a JSON download bound to the displayed evidence version.
It includes the complete stored payload, not the 500-point chart preview. The link
continues to retrieve the archived version if newer evidence arrives. Downloads use
the same session checks as the review page; unknown versions return 404.

### Upgrade and rollback

Schema-5 migration is rehearsed from a preserved synthetic SQL fixture generated by
the previous implementation. Upgrade retains candidate bindings, reviews and outcomes;
it never retroactively authenticates old named decisions. Opening a newer unsupported
schema fails closed. There is no destructive downgrade command: rollback requires
stopping writers and restoring a pre-upgrade database/evidence backup with its compatible
software version. Preserve post-upgrade records separately before any rollback.
## Reviewer inspection controls

Candidate pages provide GET-only MJD, survey and band filters with a reset link and
visible/total observation counts. These affect the preview only; the exact-version
JSON download retains all measurements. Invalid or duplicate filters return HTTP 400.

When evidence changes while a form is open, a rejected submission preserves the
rationale and compares added/removed observations and changed payload fields. Both
versions remain downloadable; an old decision is never copied onto new evidence.

The authenticated `/inbox` view lists current reporting-preflight blockers in pages
of 50 candidates. Its links lead to evidence inspection. There is no dismiss endpoint:
only new valid evidence or authorized review can resolve an underlying requirement.
