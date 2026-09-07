# Migrating the legacy I SPY scripts to IRIS

## Goal

The migration replaces a chain of loosely coupled CSV scripts with a versioned,
testable package while keeping the original workflow available for audit. It is a
parallel validation and handover, not a bulk rename and not permission to discard
past evidence.

The canonical development target is `src/iris/`. Root-level Python scripts are
legacy reference implementations. `cool-stuff-master/` is a historical duplicate,
not a second source tree to maintain.

## Why migration is necessary

The original scripts contain useful operating knowledge but exchange implicit CSV
schemas, duplicate selection logic, and mix acquisition, inference, network calls,
and reporting concerns. That makes it difficult to answer basic audit questions:

- Which code and thresholds produced this shortlist?
- Were magnitudes from different filters compared directly?
- Did an empty catalogue result mean clear sky or a failed request?
- Did verification and catalogue screening operate on the same candidate version?
- Was the score a trained probability or a hand-built priority?
- Who independently approved the result?
- Can the exact input population and outcome denominator be reconstructed?

IRIS addresses those questions with typed records, explicit statuses, strict
configuration, hashes/manifests, a ledger, and independent gates.

## Legacy-to-IRIS map

| Legacy file or responsibility | IRIS destination | Migration status |
|---|---|---|
| `run_1000_candidate_hunt.py` orchestration | `iris.pipeline` local analysis and run manifest; future live coordinator | Local path implemented; live integration work |
| `ai_candidate_hunter.py` broker intake | `iris.ingest.alerce` behind the shared ingestion contract | Bounded adapter with explicit `ztf`/`lsst` survey binding and a content-bound snapshot sidecar implemented; durable operations pending |
| `ai_candidate_hunter.py` feature calculation | `iris.features.photometry` | v4 survey/passband-channel magnitude and supplied forced/difference-flux extraction implemented; scientific parity must be measured |
| Legacy transient score | `iris.scoring.heuristic` | v2 magnitude/forced-flux basis selection implemented as a new explainable priority; intentionally not numerically compatible |
| `fetch_alerce_detections.py` | `iris.ingest.alerce` and future durable raw cache | Adapter implemented; durable cache/replay pending |
| `optical_transient_pipeline.py` | `iris.features.photometry` plus future period/image and survey-side acquisition components | Survey/passband-channel magnitude and supplied forced-flux extraction implemented; acquisition/calibration pending |
| `catalog_validation_engine.py` | `iris.clients.catalogs`, `iris.validation.catalog_policy` | Core adapters/policy implemented; live qualification pending |
| `verify_candidates.py` | `iris.validation.suite`, read-only `iris.clients.tns` | Core coordinator implemented; broker parity and live qualification pending |
| `final_candidate_filter.py` | `iris.validation.gates`, `iris.reporting.preflight` | Safety gates implemented |
| `build_tns_report.py` | `iris.review.dossier`, preflight, future report exporter | Dossier/preflight implemented; no new submission transport |
| Ad hoc output folders | `iris.pipeline`, `iris.manifest`, `iris.data.snapshot`, `iris.review.assembly`, configured storage | Local pipeline and atomic review-set bundle integrated; other entry points pending |
| Manual notes and decisions | `iris.ledger`, `iris.review.server` | Schema-v4 exact-version reviews, catalogue-context adjudications/outcomes, append-only candidate-version reconstruction, and orphan guards implemented locally; identity/access control pending |
| Nearest examples and novelty | `iris.similarity`, `iris.anomaly`, `iris.ranking` | Deterministic retrieval and provenance-required persisted indexes implemented; population validation pending |
| Host context | `iris.host` | Geometric chance-coincidence ranking implemented; catalogue/population validation pending |
| Supervised baseline | `iris.ml.baseline` | Chronological logistic baseline with a required entity policy and optional held-out calibration implemented; training data/validation pending |
| Representation learning | `iris.ml.*` | TS-JEPA with versioned per-curve token contracts, incompatible-batch rejection, enforced/default chronological splitting, deterministic training controls, and repeated-mask evaluation implemented in the shadow boundary |
| Follow-up ordering | `iris.followup`, `iris.campaigns` | Utility primitive and advisory-only research sketches implemented; no campaign sketch activates operational policy, and observatory integration is pending |

“Implemented” means code exists with a defined API. It does not mean parity,
performance, or prospective scientific validity has been established.

## Important behavior changes

### Configuration is explicit

New settings live in TOML profiles under `configs/`. Unknown keys are errors, and
safety booleans such as fail-closed validation and human approval cannot be turned
off through normal configuration. Relative paths are resolved from the config
file rather than the shell working directory.

Keep the exact effective configuration with every run. Do not translate old
thresholds mechanically: first identify their units, filter dependence, and
scientific purpose.

### Source snapshots and manifests are content-bound

The CSV adapter hashes the same immutable byte buffer that it parses. A direct
local CSV retains its path, digest, size, modification time, row count, and column
mapping in ingestion provenance; the exact parsed bytes—not a later reopening of
the path—are archived as a `source-input-snapshot` artifact. `broker-fetch` writes
an adjacent `iris.broker_snapshot.v1` sidecar containing the emitted photometry SHA-256 plus
broker query/source/retrieval metadata. Later ingestion rejects a missing-schema,
mismatched, or malformed sidecar instead of combining provenance from another
CSV.

Local run manifests record artifact digests, the effective configuration, Git
revision/dirty state when available, and a content digest over `src/iris`,
`configs`, and `pyproject.toml` even when the checkout has no usable Git metadata.
When no checkout tree is available, that digest falls back to the actual installed
`iris` package files and refuses to emit an empty code identity. Local analysis
closes a terminal manifest after run creation on completion, caught processing
failure, and user interruption;
failure/interruption manifests best-effort inventory already-finalized partial
artifacts. The scientific fingerprint excludes storage paths and retrieval-time
bookkeeping, but retains scientific source provenance. This supports repeatability
without claiming that hashes authenticate an upstream producer.

### Review allocation is a versioned artifact

The legacy shortlist is replaced by `iris.nightly_queue.v2`. The default
`triage` policy admits quality-passing candidates whose external evidence remains
incomplete while excluding known-object and quality vetoes; `gate-clear` is the
narrower post-verification policy. Separate primary, anomaly, and seeded
random-audit routes never duplicate a candidate. Random-audit entries record the
eligible population, seed, uniform without-replacement inclusion probability, and
per-entry propensity. Audit slots default to zero and must be enabled by an
explicit campaign policy.

`iris review-set` reads and archives the exact `ranked_candidates.csv` and
`iris.candidates.v1` bytes, verifies identical candidate ID/version sets, and
atomically creates a new `iris.review_set.v1` directory with the queue, artifact
hashes, and one dossier per selected candidate. It refuses overwrite. This is a
portable review denominator, not external-clearance evidence or reporting
authorization.

### Feature values are not drop-in compatible

IRIS does not pool raw `g`, `r`, and `i` magnitudes. In
`iris.photometry.v4`, amplitudes, slopes, flux summaries, and prior-nondetection
pairs are computed within survey/passband channels whenever survey identity is
present. Thus, `g` observations from two facilities cannot fabricate one light
curve. Missing survey values are isolated in an explicit `unspecified` channel and
reported; an input with no survey column retains passband-only behavior for
compatibility. Numeric ZTF/ALeRCE `fid` mapping is restricted to those named
surveys when identity is present. Only comparable derived quantities are
aggregated across channels. Non-detections, missing uncertainties, and quality
rejection rates are explicit. The local quality gate fails if every detection
uncertainty is missing or invalid; partial missingness remains visible and
penalizes the heuristic quality component but does not alone fail that gate.

`iris.photometry.v4` also accepts forced/difference-flux values already present in
the input. Flux features stay per channel; their aggregate excursion and rate terms
are normalized by a robust within-channel scale so a positive rescaling of flux
units does not change them. That fractional excursion is not a physical flux ratio.
Input with no finite magnitudes—including an entirely empty magnitude column—must
declare a non-missing detection status on every row, and useful significance
features require supplied positive uncertainties. Exact duplicate observations are
rejected, as is reuse of a non-empty observation ID within one source/survey. A
survey-specific revision/version and near-duplicate policy still needs
qualification. IRIS does not yet obtain forced photometry, calibrate it, or
certify its image provenance.

`iris.heuristic_priority.v2` prefers magnitude evidence for amplitude and temporal
shape, then records an explicit forced-flux fallback basis when magnitude evidence
is absent. This is a schema and scoring-version boundary: do not concatenate v2/v3
feature records or v1/v2 score columns without version-aware migration.

As a result, new feature columns and scores will differ from historical outputs by
design. A parity study should compare decisions and physical behavior, not demand
identical numbers from scientifically different definitions.

### The priority score is not a probability

The IRIS heuristic is a decomposed relative-priority index. Never map an old
`transient_score` field into a column named `probability_real`, and never present
the new priority as a confidence. A future probability field requires a labelled,
chronologically evaluated, calibrated model and model-version metadata.

### Training identity and split policy are explicit

`baseline-train` now requires exactly one of `--entity COLUMN` or
`--assert-unique-entities`. The first option enables leakage purging across the
chronological partitions and should be used whenever a physical-source identifier
exists. The second is a strong caller assertion that every row represents a
different physical entity; it must not be used merely because an ID column is
inconvenient. The saved metadata records the entity policy, dataset digest, and
exact split digest.

`jepa-train` requires disjoint train/validation object IDs and optional entity/group
IDs. Its default `--split-policy chronological` requires all training observations
to precede all validation observations; `predefined` is an explicit assertion of
an externally audited split. Flux records require explicit detection arrays.
Training uses seeded deterministic algorithms by default, with an explicit
`--allow-nondeterministic` opt-out, and held-out loss is computed across at least
two seeded masks (`--evaluation-masks`, default five) with dispersion reported.
Every newly tokenized curve carries a hashed `iris.light_curve_tokens.v3`
interpretation contract. Collation rejects different contracts, partial
known/missing provenance, and digest mismatches; an entirely legacy batch remains
loadable but is not silently upgraded to v3 provenance. The v3 token adds an
explicit value-presence bit so missing values cannot masquerade as measured zero
or leak masked-target normalization information.
Training, repeated-mask evaluation, and embedding extraction enforce and return a
single digest across the run. The CLI requires matching train/validation
contracts, verifies their runtime digests, and records the full contract plus
digest in checkpoint metadata and the training summary.

These controls do not promote JEPA beyond shadow research or guarantee identical
floating-point output across every hardware/software stack.

Persisted `iris.embedding_index.v2` similarity indexes require SHA-256 identifiers
for the encoder, token contract, and dataset snapshot. Loading rejects legacy or
incomplete provenance. The digests bind the matrix to declared artifacts but do
not establish their trustworthiness or scientific validity.

### External validation fails closed

Each remote check now distinguishes clear, match, error, disabled, pending, stale,
and missing states. Only a fresh explicit clear result satisfies a mandatory
check. Missing credentials or dependencies therefore block the new preflight;
they do not produce a clean candidate.

Completed clearance is also bound to the candidate identity and coordinates, the
minimum cone radius, the configured maximum TTL, and every SkyBoT reference epoch.
Verification queries SkyBoT once per distinct requested MJD and creates an
all-epochs aggregate: any match vetoes and any non-clear component blocks. The
local pipeline then requires that aggregate to cover every distinct usable
detection MJD in normalized photometry. Reporting preflight revalidates those
fields and verifies a digest over the full checks, quality/manual flags,
mandatory-service set, and binding policy.

Verification artifacts imported by `analyze` must declare
`iris.verification.v1`, a valid candidate ID/checks array, and a boolean manual
review flag. Every check must contain the complete exact provenance shape;
missing/unknown fields are rejected rather than receiving synthesized timestamps,
attempts, or service metadata. A TNS `clear` additionally requires
the versioned `tns-two-stage-search.v1` contract, the ordered internal-name and
position-cone methods, their coverage policy, and exact candidate identity.

### Human approval is structured

The reporting preflight requires one screener and the configured number of
reviewer approvals, with at least one reviewer identifier different from the
screener. Each new review must explicitly name the exact immutable candidate
version shown in the reviewed ledger/artifact; neither the ledger API nor CLI
infers it. Stale versions are rejected, and an evidence or
scientific-policy change means old approvals no longer count. Legacy notes can be
imported as historical evidence, but do not invent reviewer identities or convert
ambiguous notes into approval.

Ledger schema v4 keeps a mutable current-candidate view and an append-only
first-seen snapshot for every candidate version. Historical-version lookup keeps
the payload referenced by an older review/adjudication/outcome reconstructable;
database triggers prevent archive mutation and new orphan version references.
Normal write APIs still require the exact current version. Migration backfills
candidate history for an older ledger's current rows, but legacy unbound reviews
remain unbound and never become approvals by inference.

```bash
iris review-add CANDIDATE_ID --candidate-version CANDIDATE_VERSION \
  --reviewer REVIEWER --role reviewer --verdict approve \
  --reason "Independent evidence review complete"
```

Re-evaluate readiness from the immutable ledger payload immediately before any
separately governed reporting step. Exit code `3` means blocked and must not be
converted to success:

```bash
iris preflight CANDIDATE_ID --candidate-version CANDIDATE_VERSION
```

This command is read-only and creates no registry payload.

When catalogue context sets `manual_review_required`, ordinary approvals still do
not clear it. A separate CLI event records scientific adjudication against the
exact current version:

```bash
iris adjudication-add CANDIDATE_ID --candidate-version CANDIDATE_VERSION \
  --adjudicator ADJUDICATOR --verdict clear_context \
  --reason "Reviewed the catalogue association and resolved the ambiguity"
```

At least one adjudicator's active decision must be `clear_context`, and any active
`reject` blocks. With no active clearance, an absent decision or
`needs_more_data` remains unresolved. Adjudication cannot waive a known-object
match, failed quality, incomplete external checks, or the independent-review
requirement. It is append-only and becomes inapplicable if the candidate version
changes. The current CLI identity is still a typed audit label, not authenticated
identity.

Mature downstream outcomes have the same stale-version guard and carry a taxonomy
version plus a digest of the optional evidence object:

```bash
iris outcome-add CANDIDATE_ID --candidate-version CANDIDATE_VERSION \
  --outcome confirmed_transient --taxonomy-version iris.outcome.v1 \
  --evidence-json outcome-evidence.json
```

### TNS is read-only in the new package

`iris.clients.tns` searches for duplicates. It validates the application-level
success code and accepted result-array shapes, so a missing or malformed result is
an error rather than an empty clearance. A clear result aggregates both its
internal-name and sky-cone subchecks into one auditable digest and declares the
binding contract described above; a generic legacy cone-only clear is not
accepted. It does not submit. Continue to treat any report construction/transport
as an explicit human-controlled step governed by the current I SPY submission
protocol and live TNS policy.

## Migration phases

### Phase 0 — Freeze and inventory

1. Preserve the root scripts and the historical protocol/operations documents.
2. Inventory known run directories, input caches, shortlist files, report drafts,
   correspondence, and final outcomes.
3. Record file hashes before transforming historical data.
4. Document the Python/dependency versions where known.
5. Mark `cool-stuff-master/` as a historical duplicate and stop editing it.

Do not delete or rewrite prior outputs. If secrets are discovered, revoke and
remove them through a separately audited security procedure while retaining
non-secret scientific provenance.

### Phase 1 — Establish the new local foundation

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[all,dev]'
.venv/bin/python -m iris doctor --strict
.venv/bin/python -m pytest
```

Review the effective profile:

```bash
.venv/bin/python -m iris config-show --config configs/default.toml
```

Exercise the local migration path on a copied input artifact before any live
handover:

```bash
.venv/bin/python -m iris analyze historical-photometry.csv \
  --config configs/default.toml
```

This first analysis is expected to be blocked on pending external evidence. That
is the correct fail-closed result, not a migration failure. The complete command
inventory and evidence/review sequence are in the top-level `README.md`.

Package a bounded triage set from that run without rewriting its analysis
artifacts. Use an explicit preserved audit seed for a preregistered campaign, or
omit it once and retain the seed generated in the bundle:

```bash
.venv/bin/python -m iris review-set \
  var/iris/runs/RUN_ID/ranked_candidates.csv \
  var/iris/runs/RUN_ID/candidates.json \
  var/iris/review-sets/NIGHT_ID \
  --audit-slots 2 --audit-seed CAMPAIGN_NIGHT_SEED
```

The repository default profile resolves storage to `var/iris/` in this checkout.
An installed package used without the repository profile falls back to the
bundled configuration and `~/.iris`. Before live use, select the profile
explicitly and define backup, access, retention, and secret-handling policy for
its resolved storage location.

### Phase 2 — Qualify and extend schema adapters

The local CSV adapter already resolves common aliases, rejects ambiguity, validates
coordinates/times, preserves string IDs, and hashes its source. For each additional
legacy artifact type, qualify or write a one-way importer that:

- declares the exact source script/version and column schema;
- preserves the original file and hashes it;
- maps object IDs and aliases without silently merging uncertain sources;
- converts times and units explicitly;
- preserves raw band, detection, magnitude/flux values, their uncertainties,
  upper-limit, calibration/provenance, and quality fields;
- maps unavailable information to missing/unknown, never zero or clear;
- records conversion warnings by row; and
- writes a versioned output plus a conversion manifest.

Do not let the new package consume arbitrary legacy CSVs merely because their
column names look similar. Validate required columns, units, coordinate bounds,
time ranges, and uniqueness.

### Phase 3 — Offline parallel run

Use frozen historical inputs so both workflows see the same eligible population
and decision cutoff. Compare:

- intake and eligibility counts;
- per-survey/passband-channel detection/non-detection counts;
- feature distributions and expected intentional differences;
- ranking overlap at the nightly review budget;
- every external-check status and rejection reason;
- candidates blocked by missing or stale evidence;
- review workload and final mature outcomes; and
- artifact/manifests completeness.

Investigate disagreements candidate-by-candidate. Classify each as a legacy bug,
new bug, intentional policy change, upstream-data difference, or unresolved.
Publish the full disagreement table, not only examples that favor IRIS.

### Phase 4 — Live shadow operation

Run IRIS beside the established human workflow without changing what reviewers
see initially. Capture the complete pre-ranking denominator and reserve random
audit slots with the implemented seeded queue route so the missed-positive rate
can be estimated. Preserve the queue's population, inclusion probability,
per-entry propensity, seed, and named eligibility policy. No shadow model output
may alter external reporting.

After outcomes mature, evaluate under the protocol in
[`SCIENTIFIC_VALIDATION.md`](SCIENTIFIC_VALIDATION.md). A stable process over
multiple out-of-time periods is required; a single successful night is not a
handover criterion.

### Phase 5 — Assisted-review handover

Move one responsibility at a time, in this order:

1. typed ingestion and immutable raw snapshots;
2. survey/passband-aware feature generation;
3. explainable baseline ranking;
4. fail-closed external verification;
5. dossier generation and review ledger;
6. reporting preflight; and
7. experimental ranking signals such as JEPA, only after their separate promotion.

For each step, define the old and new owner, effective date, rollback trigger, and
last known-good version. Do not mix a legacy stage and new stage unless the schema
adapter and provenance transfer are tested.

### Phase 6 — Legacy retirement

Retirement means no longer using root scripts for new operations; it does not mean
deleting them. Before retirement:

- all required capabilities have an owner and runbook;
- retrospective and prospective acceptance gates pass;
- output and outcome records are backed up and recoverable;
- external service failure drills pass with zero fail-open outcomes;
- reviewer independence is demonstrated end to end;
- a rollback rehearsal succeeds; and
- the final legacy run and first canonical IRIS run are recorded.

Tag or archive the legacy tree read-only and keep enough environment information
to interpret historical results.

## Historical data import policy

Historical records are valuable but heterogeneous. Use these principles:

- preserve original bytes and hash them before import;
- store original and normalized values side by side where conversion is nontrivial;
- distinguish observation time, ingest time, check time, review time, and outcome
  time;
- never backfill an external check as though it occurred at the candidate decision
  time;
- label legacy network failures as unknown/error unless there is affirmative raw
  evidence of a successful empty response;
- preserve historical score name and version; do not coerce it into the new score;
- import reviewer notes as notes unless the historical protocol proves they were
  formal approvals; and
- record current catalogue queries as new evidence, not replacements for historical
  evidence.

## Credentials and external services

Do not place API keys, bot IDs tied to a secret, session cookies, or bearer tokens
in TOML, source code, manifests, dossiers, test fixtures, or shell history. Supply
secrets through the approved runtime secret mechanism and redact request/response
artifacts. Public query provenance should contain coordinates/radii and method,
not credentials.

Use recorded fixtures for repeatable tests. Live-service checks should be a
separate marked test class because network availability and changing catalogues
make them unsuitable as deterministic unit tests.

## Rollback

A migration release must identify a last known-good code/config/data tuple. Roll
back ranking or orchestration if any of these occurs:

- a fail-open safety result;
- corrupted or untraceable input/output artifacts;
- unexplained eligibility or ranking shift;
- loss of reviewer independence/auditability;
- severe latency causing scientifically material delays;
- unhandled upstream schema change; or
- model/input drift beyond the registered operating range.

Rollback does not authorize use of stale validation evidence. Re-run mandatory
checks, create/review the resulting immutable candidate version, and run preflight
against that exact version.

## Completion checklist

- [ ] Historical source and outputs inventoried and hashed.
- [ ] Duplicate tree marked read-only.
- [ ] Canonical config and storage policy approved.
- [ ] Legacy schemas have versioned importers and fixtures.
- [ ] Offline parallel-run disagreement audit complete.
- [x] Once a local-analysis run directory is created, completion, caught processing
  failure, and interruption paths emit terminal manifests.
- [ ] Every additional production orchestration path emits an equivalent terminal
  manifest.
- [ ] External service fault suite has zero fail-open outcomes.
- [ ] Prospective shadow campaign and random audit complete.
- [ ] Reviewer workflow and separation of duties qualified.
- [ ] Reporting transport, if added, remains explicit and preflight-gated.
- [ ] Rollback rehearsed.
- [ ] Legacy operational retirement recorded without deleting evidence.
