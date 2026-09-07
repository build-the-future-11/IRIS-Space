# IRIS roadmap

## North star

IRIS should be a scientifically credible, failure-aware discovery workbench that
helps a small human team find and follow unusual astronomical events without
confusing model confidence, catalogue availability, or workflow completion with
scientific truth.

There is no meaningful “perfect” endpoint. The target is a platform whose claims
are falsifiable, whose inputs and decisions are reproducible, whose failure modes
are visible, and whose performance is re-measured as surveys and populations
change.

Status date: **2026-09-06**.

## Status key

- **Implemented:** code exists in the current source tree with a defined local API.
- **Integrated:** exercised through a canonical end-to-end entry point with
  manifests and failure handling.
- **Validated:** passed the preregistered offline or prospective evidence level.
- **Operational:** monitored, recoverable, access-controlled, and covered by a
  runbook.

These terms are cumulative. A component marked implemented is not implied to be
validated or operational.

## Current foundation

| Capability | Current status | Next evidence or integration step |
|---|---|---|
| Strict typed configuration | Implemented | Add deployment-specific secret/storage policy and config migration/versioning |
| Candidate/observation/evidence domain model | Implemented | Exercise complete live lifecycle and persistence/replay |
| Canonical schema and local CSV ingestion | Implemented with exact-duplicate and reused non-empty observation-ID rejection | Qualify additional legacy/survey schemas plus revision/version and near-duplicate policy |
| Bounded lazy ALeRCE ingestion adapter | Implemented with explicit `ztf`/`lsst` request provenance, survey-specific detection filters, a fail-closed qualified Rubin classifier/photometry contract, bounded retries/timeouts, and a content-bound snapshot sidecar | Add durable watermarking, raw replay, recorded live fixtures, schema monitoring, end-to-end deadlines, and recurring qualification |
| Immutable local analysis pipeline (`iris.local_analysis.v4`) and CLI | Integrated locally with source/config/code and candidate-evidence digests plus terminal completion/caught-failure/interruption manifests after run creation | Verify in clean supported environments and extend terminal-manifest coverage to pre-run validation and other production entry points |
| Lifecycle and reportability policy | Implemented | Property tests over every transition and end-to-end fault qualification |
| Survey/passband-aware magnitude and supplied forced-flux features (`iris.photometry.v4`) | Implemented with cross-survey channel separation, explicit survey-less metadata, exact significant-measurement unions, and separate band/channel prior non-detection counts | Independently verify calibration assumptions, numerical behavior, and survey-stratified performance |
| Explainable magnitude/forced-flux heuristic (`iris.heuristic_priority.v2`) | Implemented | Retrospective and prospective finite-budget comparison |
| SkyBoT/SIMBAD/VSX adapters | Implemented | Recorded fixtures, schema monitoring, rate-limit behavior, live qualification |
| Read-only TNS duplicate search | Implemented with strict result-shape failure and imported-clear binding to the versioned two-stage name/cone contract | Recorded/live API fixture suite, schema monitoring, policy verification, credential integration |
| Fail-closed verification and evidence binding | Integrated locally, including all-distinct-detection-epoch SkyBoT aggregation and coverage binding | Zero-fail-open fault campaign, recorded/live fixtures, and operational qualification |
| Candidate/review/adjudication/outcome SQLite ledger | Implemented locally at schema v4 with exact-current-version writes, append-only first-seen candidate-version history, reconstruction APIs, and orphan-reference guards | Authentication, role policy, deployment migration testing, backup, concurrency, audit hardening |
| Independent reporting preflight | Integrated locally with exact candidate/evidence-version binding and manual-context adjudication | Report exporter integration and operational qualification |
| Portable candidate dossier | Implemented | Add plots/stamps, usability study, integrity links, redaction policy |
| Loopback review service | Integrated locally with exact-version review and adjudication events | Add authenticated identity, authorization, and deployment hardening |
| Run manifests and dataset snapshots | Integrated in created local-analysis runs with checkout/installed-package code digest, exact ingested-byte snapshot, and terminal completion/caught-failure/interruption records | Extend coverage to pre-run validation and every other entry point that becomes a production orchestration boundary |
| Ranking/calibration evaluation helpers | Implemented | Locked datasets, confidence intervals, rolling-origin analysis |
| Chronological supervised logistic baseline | Integrated locally with required `--entity` purging or explicit `--assert-unique-entities` | Curate labels and run locked/prospective evaluation of the bound dataset/split metadata |
| Capacity-aware nightly queue and portable review set | Integrated through `queue`/`review-set` with named eligibility, anomaly reserve, seeded random-audit allocation/propensity, exact input/version binding, dossiers, and artifact hashes | Validate campaign eligibility/seed policy and the complete upstream denominator prospectively |
| Chance-coincidence host association | Implemented with deterministic ordering and uncertainty-required acceptance | Integrate catalogue inputs and validate density, uncertainty, tie, and association policy |
| Source-control ignore policy | Implemented | Keep new runtime artifact types covered and audit tracked files before release |
| Robust anomaly and cosine similarity | Implemented as primitives; persisted indexes require encoder/token/dataset provenance | Reference-population curation, duplicate audit, scientific enrichment study |
| Follow-up utility and advisory campaign sketches | Implemented as non-operational primitives | Validate utility factors, wire only an approved TOML policy, then add visibility/facility constraints and runbook integration |
| Irregular-time TS-JEPA | Implemented as shadow research code with context-only normalization, explicit flux detections, split enforcement, deterministic defaults, repeated masks, explicit value-presence/missing-error sentinels, and hashed `iris.light_curve_tokens.v3` contracts enforced across collation/training/evaluation/extraction and persisted by the CLI | Reproducible training corpus, ablations, calibration of any downstream predictor, shadow campaign, model governance |

## Priority sequence

Safety and measurement validity precede model sophistication. The work is ordered
so later milestones can be evaluated rather than merely demonstrated.

## M0 — Package foundation

**Objective:** replace implicit script coupling with explicit, testable contracts.

Delivered in the current tree:

- `src/iris/` package structure and console entry point;
- strict TOML profiles;
- canonical schema, local CSV and bounded ALeRCE ingestion adapters, including a
  content-bound broker snapshot sidecar and duplicate/observation-ID rejection;
- immutable local analysis with a deterministic scientific fingerprint, atomic
  file artifacts, source/config/code digests (including installed-package fallback),
  snapshot and terminal completion/caught-failure/interruption manifest after run
  creation, plus exact-version
  ledger upserts;
- immutable domain types and lifecycle policy;
- v4 survey/passband-channel magnitude and supplied forced/difference-flux
  features, plus transparent v2 basis-aware scoring;
- fail-closed service provenance, candidate/query binding, all-distinct-epoch
  SkyBoT aggregation, and gates;
- exact-version ledger approvals, manual-context adjudications, outcomes,
  append-only candidate-version reconstruction, and evidence-bound preflight,
  plus dossier, manifests, and dataset snapshots;
- loopback-only, CSRF-protected local review queue with no report endpoint;
- atomic `iris.review_set.v1` bundles with exact input/version binding, artifact
  hashes, and a dossier for every selected candidate;
- evaluation, anomaly, retrieval, follow-up, and explicitly advisory campaign sketches;
- chronological supervised baseline with an explicit entity policy,
  capacity-aware review queue with named eligibility and seeded random-audit
  propensity, provenance-required persisted similarity indexes, and transparent
  host-association statistics;
- optional shadow-only TS-JEPA implementation with context-only re-normalization
  during masking, an explicit missing-error sentinel and flux detection flags,
  enforced split policy, deterministic defaults, repeated-mask evaluation, and
  hashed per-curve token contracts enforced through training/evaluation/extraction
  and persisted in CLI checkpoint metadata; and
- unit/safety regression tests plus architecture, validation, and migration docs.

Exit is complete only when the full local validation suite passes in a clean
supported environment; the source-control ignore policy for current generated and
runtime artifacts is now present.

## M1 — Canonical reproducible local pipeline

**Objective:** a canonical offline path turns a validated local observation file
into a ranked, auditable review set. This is implemented as two explicit immutable
steps: `analyze` creates one `iris.local_analysis.v4` run, and `review-set`
atomically packages that run's exact ranking/candidate snapshots, finite queue,
manifest, and selected dossiers. Local analysis now closes interruption manifests
instead of leaving an apparently running execution.

Delivered in code:

- versioned input schema, strict column/unit validation, exact duplicate/reused-ID
  rejection, and content-bound source provenance;
- grouping by canonical input source ID (cross-survey alias resolution remains
  validation/integration work);
- survey/passband-aware magnitude and supplied-flux feature extraction with versioned,
  basis-aware heuristic ranking;
- an optional caller-supplied anomaly score used only by the review-allocation
  route and never reportability;
- finite review-budget queue with named eligibility, reserved random/anomaly audit
  slots, replay seed, and random-route propensity;
- SQLite candidate upsert and portable dossiers;
- an atomic review-set bundle that verifies exact ID/version agreement and refuses
  overwrite;
- terminal local-analysis manifest with source/config/code/artifact digests after
  run creation on completion (including blocked candidates), caught processing
  failure, and interruption;
- deterministic fixtures and a reproducible example dataset; and
- command help, exit codes, and machine-readable summaries.

Remaining qualification/exit criteria:

- repeat runs on the same snapshot/config/code produce matching scientific
  artifacts or documented nondeterministic fields;
- invalid schemas and partial files fail without overwriting a completed run;
- every output can be traced to input/config/code digests; and
- no offline run is labelled reportable without fresh mandatory evidence.

## M2 — Durable live intake and evidence acquisition

**Objective:** ingest and replay live alerts while preserving the data needed for
independent verification.

Deliverables:

- ALeRCE adapter with schema versioning, pagination, watermarking, idempotency, and
  a replayable raw cache;
- at least one second broker/survey adapter to expose broker-specific shortcuts;
- alert cutout acquisition with hashes and observation association;
- survey-side forced-photometry and upper-limit acquisition with calibration,
  image association, and provenance (distinct from the implemented extractor for
  supplied values);
- coordinate, time-scale, unit, and duplicate normalization;
- a source-qualified global object identity plus explicit campaign membership;
  the current local ledger deliberately blocks reuse of one `candidate_id` across
  campaigns rather than risking an overwrite;
- durable queue/retry/dead-letter behavior;
- cached external checks with TTL and explicit refresh;
- preservation of the implemented all-distinct-detection-epoch SkyBoT coverage
  contract through cache/replay; and
- service health, latency, rate-limit, and schema-change monitoring.

Exit criteria:

- reconnect/replay cannot create duplicate scientific candidates;
- raw alert and check evidence is reconstructable by run ID;
- upstream outages block affected gates and preserve unaffected work; and
- a fault-injection suite records zero fail-open results.

## M3 — Calibrated reality and novelty baselines

**Objective:** learn defensible probabilities only after enough mature outcomes
exist.

Deliverables:

- exact-candidate-version outcome records with evidence digests and a versioned
  label policy separating real, novel, campaign-relevant,
  duplicate, moving, variable, artifact, unresolved, and retracted states;
- alias-grouped chronological and rolling-origin splits;
- regularized linear and gradient/tree baselines with missingness indicators;
- separate `probability_real`, `probability_novel`, and scientific-value concepts;
- out-of-time calibration and abstention outside training support;
- uncertainty intervals and subgroup reports;
- model card, registry, data lineage, approval, and rollback; and
- drift and delayed-outcome monitoring.

Exit criteria:

- locked-test improvement at the nightly budget exceeds a preregistered useful
  effect with uncertainty;
- calibration is acceptable in declared operating strata;
- no leakage or duplicate-object split violation is found; and
- prospective shadow performance confirms retrospective conclusions.

The heuristic remains available as an interpretable control and rollback.

## M4 — TS-JEPA research program

**Objective:** determine whether irregular-time self-supervised representations add
scientific value, not merely whether the network trains.

The current research implementation already re-bases value/error normalization
from unmasked context for each masked example and uses `0` as a missing-error
sentinel because valid supplied uncertainties must be positive. Flux records need
explicit detection flags; the CLI also enforces disjoint entity groups,
chronological separation by default, deterministic algorithms unless explicitly
opted out, and repeated-mask held-out evaluation with dispersion. It remains
uncalibrated, scientifically unvalidated, and shadow-only. Tokenized curves carry
the hashed `iris.light_curve_tokens.v3` interpretation contract, and batching
rejects mixed, partial, or mismatched known contracts (with an all-legacy
compatibility path). Training/evaluation/extraction enforce one run-level digest;
the CLI matches train/validation contracts and persists it. These leakage,
provenance, and repeatability controls are
implementation properties, not evidence of
astrophysical utility.

Deliverables:

- large, versioned, deduplicated multi-band light-curve corpus;
- decision-time truncation and chronological dataset construction;
- reproducible multi-seed training and checkpoint registry;
- collapse, shortcut, effective-rank, and nearest-neighbor audits;
- ablations for time, band, non-detection, masking, initialization, and baseline
  architecture;
- frozen-embedding linear probes and matched downstream heads;
- analogue retrieval with source/label provenance;
- anomaly route evaluated with random-audit denominator; and
- prospective output-hidden shadow campaign followed by a controlled assisted
  phase only if justified.

Exit criteria are the JEPA promotion gate in
[`SCIENTIFIC_VALIDATION.md`](SCIENTIFIC_VALIDATION.md). Until then,
`enabled = true` must coexist with `shadow_mode = true`; embeddings cannot change
reportability.

## M5 — Scientific review workbench

**Objective:** give reviewers the evidence needed to make faster, more consistent,
and still-independent decisions.

The local ledger/CLI and loopback UI already support reason-coded, exact-version
review and catalogue-context adjudication. Production work remains to authenticate
and authorize the decision maker, harden deployment, and qualify usability.

Deliverables:

- authenticated, role-aware review service;
- production UI display and confirmation of the already implemented immutable
  candidate/evidence version on every decision;
- synchronized light curves, non-detections, cutouts, reference/difference stamps,
  catalogue overlays, and external-check provenance;
- nearest known analogues with label and dataset lineage;
- reason-coded decisions, abstention, disagreement, and authenticated adjudication;
- blind/hide-model mode for experiments;
- accessibility and latency budgets;
- immutable append-only audit events; and
- reviewer workload, agreement, and overlooked-warning metrics.

Exit criteria:

- no self-approval or approval of stale evidence is possible;
- usability study shows no safety degradation;
- every visible number links to source/provenance; and
- backup/restore and access-revocation exercises succeed.

## M6 — Follow-up and reporting operations

**Objective:** turn human-approved evidence into timely, policy-compliant action
without automating away accountability.

Deliverables:

- observability from site, horizon, airmass, Sun/Moon, weather, and instrument
  constraints;
- explicit expected-information-gain and urgency models;
- facility-specific exposure and cadence templates;
- request tracking, acknowledgement, data return, and failure status;
- report draft schemas with unit/coordinate/time validation;
- duplicate re-check immediately before report preparation;
- integration of the existing exact candidate/evidence-version preflight into the
  report exporter;
- explicit human confirmation before any external write; and
- exact-version designation/follow-up outcomes with taxonomy and evidence digests
  fed back into the ledger.

Exit criteria:

- a dry-run campaign exercises every path without external submission;
- current service policy and identifiers are verified;
- external writes are least-privilege, auditable, idempotent where possible, and
  recoverable; and
- a runbook and incident/withdrawal procedure are rehearsed.

## M7 — Beyond the initial IRIS level

These are high-value research extensions after M1–M6 are stable:

### Multi-modal representation learning

Jointly model irregular photometry, alert cutouts, host context, spectra, and
textual catalogue evidence while preserving missing-modality masks. Compare with
late-fusion baselines and audit whether the model shortcuts on survey artifacts or
catalogue availability.

### Multi-survey domain adaptation

Learn survey-aware but physically useful representations across ZTF, Rubin/LSST,
ATLAS, Pan-STARRS, Gaia, and follow-up photometry. Require survey-held-out tests,
calibration by survey, and explicit abstention on unseen filters/cadences.

### Active learning with unbiased audits

Use information gain to request labels while reserving randomized audit samples.
The current queue already records a replayable uniform propensity for its seeded
random-audit route. A future active learner must preserve that independent route,
extend propensity logging to any stochastic acquisition policy it introduces, and
ensure scientific evaluation is not confined to what the current model already
considers interesting.

### Hierarchical and open-set inference

Represent “astrophysical,” “new,” broad family, subtype, and anomaly as separate
uncertain questions. Allow unknown/open-set outcomes rather than forcing every
candidate into a known class.

### Physical parameter and counterfactual views

Estimate timescale, color evolution, host offset, extinction sensitivity, and
observability under stated assumptions. Show how ranking changes if an uncertain
measurement or association is removed; do not present attention maps as causal
explanations.

### Population-aware discovery

Measure selection functions and discovery completeness, not only top-candidate
quality. Connect alert eligibility, review allocation, follow-up success, and final
classification into a denominator suitable for population studies.

### Federated telescope network

Coordinate independent facilities through portable request/evidence schemas while
keeping each site in control. Record acknowledgements, constraints, calibration,
and returned data as provenance-rich events.

## Cross-cutting engineering work

Every milestone includes:

- security review and secret redaction;
- deterministic fixtures and property/fault tests;
- schema and artifact versioning;
- structured logs, metrics, and alerting;
- resource/cost and latency budgets;
- backup, restore, and retention;
- data licensing and attribution;
- accessible documentation and runbooks; and
- explicit ownership and rollback.

## Near-term order of work

1. Verify the completed local-analysis/review-set path in clean supported
   environments, including interruption and immutable-bundle fault cases.
2. Create recorded catalogue/broker fixtures and run the fail-closed fault matrix,
   including strict verification-import and two-stage TNS-contract failures.
3. Define and import a small, reviewed historical outcome dataset without treating
   unknowns as negatives.
4. Run the legacy-versus-IRIS disagreement study on a frozen snapshot.
5. Add terminal manifests/snapshots to every command that becomes a production
   orchestration boundary and to pre-run validation; created local-analysis runs
   already cover completion, caught processing failure, and interruption.
6. Build durable ALeRCE polling/replay, cutout acquisition, and a calibrated
   forced-photometry acquisition/provenance contract around the existing feature
   extractor.
7. Preregister the prospective denominator and exercise the implemented seeded
   random-audit/propensity route in a shadow campaign.
8. Establish the calibrated supervised baseline on mature outcomes before
   optimizing JEPA.
9. Run JEPA ablations and hidden-output shadow evaluation.
10. Build the authenticated review workbench and complete the prospective
    assisted-review campaign only if shadow results justify it.

This order deliberately makes the ambitious work measurable. A larger model is an
upgrade only when it improves a declared scientific outcome without weakening the
safety and human-review contract.
