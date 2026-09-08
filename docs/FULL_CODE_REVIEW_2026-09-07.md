# SIDEREA repository review and improvement checklist

> Historical baseline audit. Implementation work followed this review. Consult
> [current status](PROJECT_STATUS_2026-09-08.md) and the
> [execution checklist](../PROJECT_FINISH_CHECKLIST.md) for resolved findings,
> current validation and remaining work.

Review date: 2026-09-07. Scope: current working tree, including the staged IRIS-to-SIDEREA migration and new research/operations modules. Existing changes were preserved. This review adds documentation only.

## Overall judgment

SIDEREA's most valuable purpose is **turning irregular astronomical observations into a finite, explainable, reproducible human-review queue, while preserving the evidence behind every decision**. Its long-term opportunity is to connect that queue to measured follow-up outcomes and learn which decisions produce useful science.

The established local core is substantial software, not pseudocode. It has unusually careful evidence binding, uncertainty/missingness handling, immutable artifact publication, and review-version tracking. The weaker area is the bridge from those mechanisms to scientific and operational qualification. Several newer modules record assertions or calculate diagnostics, then a promotion check treats their presence as stronger evidence than they establish.

The project is currently best described as a **research-grade local transient-triage and evidence platform with experimental learning and qualification tools**. The repository does not demonstrate a production autonomous discovery service, calibrated discovery probabilities, telescope scheduling, or a completed prospective validation campaign. Historical campaign accomplishments must remain distinct from validation of the current implementation.

The best next investment is one fully measured workflow: snapshot → analysis → exact review queue → evidence display → authenticated decisions → mature outcomes → reproducible comparison. More independent modules will have diminishing value until this loop works.

## Verification and limits

- Current package: 20,275 Python source lines across the package files inventoried during review; 108 tracked Python paths across the repository at inspection time, including tests, historical copies, and paper tooling.
- `pytest -q`: **320 passed, 96 subtests passed**, 70.32 seconds, using the installed Python 3.11 pytest entry point.
- `ruff check src tests`: passed.
- `ruff format --check src tests`: passed; 87 files already formatted.
- Mypy was unavailable in the inspected Python environments; no fresh type-check pass is claimed.
- The repository `.venv` did not contain pytest. The available system pytest was used without changing dependencies.
- Focused executable probes confirmed the fixture round-trip/redaction problems, inconsistent recovery-drill evidence, and singleton benchmark time blocks described below.
- No live broker/catalogue requests, external submissions, dependency security audit, new wheel build, or prospective scientific experiment was performed. Prior verification records in `paper/research/software-verification.json` are historical evidence, not substitutes for this run.
- This is a repository-wide inventory and cross-component review with deeper inspection of critical paths, not an exhaustive proof of every execution path or an independently verified astronomy result. See the companion source inventory for per-file coverage of the structural scan.

## What is going well

1. **The decision boundary is explicit.** Ranking and reportability are separate. `validation/gates.py`, `validation/binding.py`, and `reporting/preflight.py` preserve missing/error/stale states and require evidence bound to the candidate being reviewed.
2. **Reproducibility is designed into execution.** `ingest/csv.py` hashes the same bytes it parses; `pipeline.py` records normalized inputs, scientific fingerprints, versions, and terminal manifests. `atomic.py` uses exclusive temporary files, fsync, and no-clobber publication where appropriate.
3. **The scientific core avoids several common mistakes.** `features/photometry.py` separates survey/passband channels and magnitude/flux representations. Missing values are visible. `scoring/heuristic.py` explicitly calls its output a ranking score rather than a probability.
4. **Reviews have a meaningful version model.** `ledger.py` preserves first-seen historical candidate versions and binds reviews, adjudications, and outcomes to versions. Old approvals do not automatically authorize new evidence.
5. **Human capacity is represented.** `ranking.py` supports priority, anomaly reserve, and a seeded random-audit route with audit inclusion probability. This is a useful foundation for evaluating selection bias.
6. **The learning implementation is real.** The supervised model fits preprocessing only on training data and separates training/calibration/test chronology. JEPA includes trainable encoders, masking, EMA targets, checkpointing, token contracts, and representation diagnostics. Its usefulness remains an empirical question.
7. **The local web surface has sensible defenses.** The review server escapes HTML, bounds form input, protects writes with CSRF tokens, validates loopback Host headers, and has restrictive response headers.
8. **The test suite covers important failure behavior.** Existing tests cover atomic publication, tampering, stale evidence, review versions, ingestion, ranking, and numerical edge cases. Passing these is valuable even though it does not establish scientific accuracy.
9. **Packaging and CI are thoughtful.** Optional astronomy/ML extras, pinned CI action revisions, linting, strict typing configuration, dependency auditing, and isolated wheel smoke checks are present.
10. **Documentation often distinguishes implementation from validation.** Preserve this discipline, especially as the new promotion commands are documented.

## Concrete findings, ordered by priority

Priority meanings: **P1** = fix before relying on the affected scientific/operational claim; **P2** = fix before wider or sustained use; **P3** = planned improvement. None of these findings claims that an unattended report was actually submitted.

### F01 — P1: Promotion does not bind the benchmark to the study it promotes

Evidence: [promotion.py:287](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/promotion.py:287), [promotion.py:324](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/promotion.py:324), [benchmark.py:203](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/research/benchmark.py:203).

The cohort gate checks the protocol digest and a positive matching row count. The benchmark gate checks an embedded result digest and a named metric's lower confidence bound. It does not require the benchmark to derive from that cohort, its exact outcome versions, its reference model, or its preregistered budget, confidence level, repeat count, seed, and observation cutoff. The benchmark result has no cohort/protocol binding fields.

Consequently, a valid benchmark from a different population or budget can satisfy the statistical gate. A content hash detects a changed document; it does not establish that the correct experiment produced it. The matured-cohort gate also does not independently enforce maturity or missing-outcome handling.

**Fix:** derive benchmark inputs from a verified cohort/outcome export; bind protocol, cohort, labels, model/checkpoint, preprocessing, cutoff, budget, reference, and analysis parameters into the result; compare all bindings at promotion. Apply the declared missing-outcome policy in the analysis. Validate complete finite metric ranges and ordered intervals. Keep promotion advisory until these checks have negative tests.

**Acceptance:** swapping in a well-formed result from another study, budget, reference, confidence level, or label set blocks promotion. Immature and unresolved-outcome inputs cannot silently qualify.

### F02 — P1: Injection recovery does not measure the SIDEREA selection pipeline

Evidence: [injection.py:128](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/research/injection.py:128), [promotion.py:352](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/promotion.py:352).

The experiment adds a Gaussian pulse and fits the same known-location template to the resulting curve. It does not call ingestion, production feature extraction, scoring, finite-budget selection, or review eligibility. The function documents this limited diagnostic honestly, but promotion uses its recovery bound as a qualification gate.

It can therefore show strong recovery while the actual ranking/selection path misses injected events. It also groups by source alone, without a survey/passband or calibration contract.

**Fix:** retain this as a matched-filter diagnostic; add a separate end-to-end injection experiment that feeds synthetic observations through the actual selection path, preserving channels and units. Evaluate zero-injection controls, false positives, missed events, and finite-budget recovery. Avoid allowing this diagnostic alone to certify pipeline completeness.

**Acceptance:** deliberately breaking the production scorer or eligibility route reduces measured end-to-end recovery.

### F03 — P1: “Independent people” is not enforced by the normal review path

Evidence: [server.py:213](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/review/server.py:213), [ledger.py:879](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/ledger.py:879), [preflight.py:406](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/reporting/preflight.py:406), [cli.py:1000](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/cli.py:1000).

The web form accepts reviewer identity and role as text. The ledger supports optional signed-principal metadata, but `independent_approval` defaults to unauthenticated reviews and reporting preflight does not turn authentication on. Different strings can satisfy the local separation check. The README appropriately calls this a research UI; that limitation must remain visible in every reportability claim.

The new signed-identity facility is only partly integrated: the CLI can verify an assertion, whereas the browser flow and adjudication flow do not provide equivalent enforcement. Promotion reviews test for a non-empty assertion digest, but do not retain enough verification evidence to independently reconstruct the complete trust decision.

**Fix:** put authentication policy into immutable candidate/review policy; require trusted principals at authoritative write boundaries; derive identity and roles from the verified session. Preserve issuer/key/assurance and verification evidence. Keep a separately labelled local named-review mode.

**Acceptance:** typing a second name, using an untrusted key, lacking a role, or using an expired assertion cannot satisfy an authenticated workflow. An external gateway alone is insufficient unless the application consumes its verified identity.

### F04 — P1: Fixture storage can retain credentials that its guard appears to reject

Evidence: [fixtures.py:46](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/operations/fixtures.py:46).

`_canonical_mapping` checks sensitive keys only at the top level. A request such as `{"headers":{"Authorization":"DUMMY_ONLY"}}` is accepted, and `Set-Cookie` is not in the forbidden-key set. URLs, response bodies, and nested arrays/objects can also contain secrets. A local probe confirmed nested Authorization and Set-Cookie are retained.

**Fix:** define allowed capture fields and redact before persistence; recurse through structured content; sanitize headers and query parameters; explicitly handle bodies that may echo credentials. Store redaction metadata so altered captures are interpretable.

**Acceptance:** synthetic sentinel secrets in nested headers, cookies, URL parameters, and supported body formats never appear in persisted fixtures. This review used dummy strings and found no actual leaked credential.

### F05 — P1: The new qualification modules lack direct test coverage in the committed test sources

Evidence: repository-wide test-source search found no direct references to the new cohort/preregistration, promotion, benchmark, injection, signed-identity, fixture, asset, broker archive, or operations-ledger implementations. CLI dispatch/help coverage is not behavioral qualification of those modules.

These additions introduce persistence, authentication assertions, statistical claims, and promotion decisions, yet the established suite still passes without exercising their central contracts.

**Fix:** add focused integration and adversarial tests around F01–F04 and F06–F12. Use per-module coverage to locate gaps; do not treat the global 70% coverage threshold as a safety boundary.

**Acceptance:** tests demonstrate both a completely bound valid case and rejection of independently varied invalid evidence at every promotion gate.

### F06 — P2: The rolling benchmark can degenerate into one-object “nightly” evaluations

Evidence: [benchmark.py:114](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/research/benchmark.py:114).

Every unique numeric timestamp becomes a time block. With ordinary per-object detection timestamps, nearly every fold can contain one object. A local four-object probe yielded future fold sizes `[1, 1]`, despite a review budget of ten. Such folds cannot evaluate competition for a nightly queue. The historical rows are counted, but no model is fitted or prediction provenance checked: this is a temporal evaluation of precomputed scores, not a full rolling refit experiment.

**Fix:** require explicit night/session/window identifiers or a declared time-binning policy; require meaningful cohort sizes; bind score-generation time and training cutoff. If claiming rolling-origin training, actually refit or verify an appropriate frozen predictor per origin. Define whether uncertainty is conditional on observed nights or includes between-night variation.

**Acceptance:** realistic continuous timestamps yield intentional multi-object review blocks; future-trained or full-light-curve scores are rejected.

### F07 — P2: Prospective enrollment is not enforced as a prospective selection process

Evidence: [preregistration.py:315](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/research/preregistration.py:315), [cohort.py:175](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/research/cohort.py:175), [cli.py:1393](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/cli.py:1393).

Freeze timestamps are accepted without requiring freeze before cohort opening. Enrollment accepts a caller-supplied historical timestamp and selected IDs. It does not enforce the preregistered review budget/audit allocation or import selection from the verified queue. The uniqueness key permits multiple versions of the same physical object in one study. Retrospective replay is useful, but these records alone do not prove prospective enrollment or an unbiased denominator.

**Fix:** distinguish prospective capture from historical reconstruction; store server capture time separately from claimed event time; enforce or externally attest preregistration timing; enroll from bound review-set manifests; preserve all eligible/ineligible arrivals and audit propensity; define one decision unit per physical object or a repeated-decision estimand.

**Acceptance:** retrospectively assembled records cannot receive the same prospective qualification as contemporaneously captured enrollment; queue budget and denominator reconcile automatically.

### F08 — P2: Operational qualification counts declarations rather than verified exercises

Evidence: [promotion.py:387](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/promotion.py:387), [observability.py:222](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/operations/observability.py:222).

Fixture qualification checks labels such as `live` and `success`; it does not replay them through real adapters and compare expected fail-closed results. A probe successfully created a fixture labelled live-success with HTTP 500. Broker qualification counts stored snapshots without exercising reconstruction. Recovery passes can be recorded directly, and supplied evidence can overwrite the `passed` and `drill` attributes because it is expanded last; a probe produced a counted pass whose attributes said `passed: false`.

**Fix:** separate “recorded assertion” from “executed qualification”; produce signed/bound executor results for adapter replay, restore, and broker reconstruction. Reject reserved evidence-key collisions. Store expected versus observed behavior, code version, run ID, and complete test-case coverage.

**Acceptance:** invalid adapter behavior, a corrupt archive, or an unsuccessful restore causes qualification failure even if a human-provided label says success.

### F09 — P2: A valid empty-body fixture cannot be loaded after saving

Evidence: [fixtures.py:105](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/operations/fixtures.py:105), [fixtures.py:157](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/operations/fixtures.py:157).

Creation accepts `response_body=b""`, which encodes to an empty string. Loading requires a non-empty `response_body_base64`. The create → serialize → load round trip therefore fails for empty-body responses, including useful outage/empty-response fixtures. Confirmed by an executable probe.

**Fix/acceptance:** accept an empty but valid base64 encoding, preserving strict type and digest validation; add empty-response and malformed-base64 round trips.

### F10 — P2: Broker cursor monotonicity is not concurrency-safe

Evidence: [broker_store.py:177](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/operations/broker_store.py:177).

The previous cursor is read and validated before the first write transaction starts. Two writers can both validate against the same old cursor, then commit in reverse watermark order. The later unconditional upsert can move the cursor backwards. This is a code-level concurrency finding; no concurrent stress reproduction was run.

**Fix:** acquire an appropriate write transaction before reading or use an atomic conditional cursor update with checked row count. Define repeated-snapshot semantics: an existing snapshot currently returns without checking its supplied cursor/watermark against the stored record.

**Acceptance:** concurrent reverse-order commits preserve monotonic watermarks; retries return an unambiguous committed cursor; replaying an old identical snapshot has documented idempotent behavior.

### F11 — P2: Recoverable operational failures become permanent promotion blockers

Evidence: [promotion.py:454](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/promotion.py:454), [observability.py:240](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/operations/observability.py:240), [broker_store.py:92](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/operations/broker_store.py:92).

Promotion asks for an all-history health report with zero errors and zero archived dead letters. Events/dead letters are append-only and have no resolution state. A past handled outage remains disqualifying even after recovery. This encourages starting a new empty ledger rather than preserving honest history.

**Fix:** retain immutable incidents and append resolution/replay events; qualify against a declared campaign/window and unresolved incident policy; require minimum observed activity so an empty log cannot imply health. Normalize timestamps to UTC before time-indexed SQL comparisons, since textual ISO timestamps with different offsets do not sort by instant.

**Acceptance:** a resolved incident remains auditable but no longer blocks forever; an unresolved incident still blocks; time-window filtering works across offsets.

### F12 — P2: Asset completeness is stronger than asset scientific validation

Evidence: [assets.py:65](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/operations/assets.py:65), [promotion.py:426](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/promotion.py:426).

Bundles require four role names, files, hashes, and calibration field names. Forced-photometry calibration values are not validated for coordinate type/range or agreement with the candidate. Image content, WCS, passband, and observation association are not scientifically verified. Arbitrary files can satisfy role completeness.

**Fix:** preserve the useful packaging function, but label its result “integrity/completeness verified.” Add typed calibration validation, supported file decoding, observation IDs, coordinate/time/channel agreement, and separate quality adjudication before qualification treats assets as image evidence.

**Acceptance:** an unrelated image, invalid calibration value, inconsistent position, or incompatible photometry channel blocks scientific qualification despite valid hashes.

### F13 — P2: Ledger initialization can escape terminal-run failure recording

Evidence: [pipeline.py:467](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/pipeline.py:467), [pipeline.py:499](/Volumes/PRO-BLADE/IRIS-Project/src/siderea/pipeline.py:499).

The run directory is created before constructing the effective ledger, and that construction sits outside the processing try/except. A ledger path/initialization failure can leave a created run directory with no terminal manifest. The README's “once a run directory is created” promise is therefore too broad.

**Fix/acceptance:** include post-directory initialization in terminal-error handling, or initialize prerequisites before creating the run. Inject a ledger initialization failure and verify a terminal failure record or no created run.

## Implementation versus scaffolding

| Area | What actually exists | What remains |
|---|---|---|
| Canonical local analysis | Executable ingestion, features, heuristic ranking, manifests, ledger publication | Large-scale qualification and broader scientific contracts |
| Catalogue verification | Real lazy adapters, retry handling, evidence binding, fail-closed gates | Captured adapter replay matrix, live qualification, cache/rate-limit operations |
| Review sets | Exact-version queue/dossier bundles | A reviewer-centered evidence interface and authenticated browser decisions |
| Baseline ML | Real logistic fitting, held-out calibration, persistence, diagnostics | Representative labels, deployable prediction integration, domain qualification |
| TS-JEPA | Real neural training/evaluation/checkpoint implementation | Demonstrated benefit, physical time/channel representation studies, production inference |
| Anomaly/retrieval/host | Implemented numerical utilities with useful integrity checks | Integrated catalogue/corpus pipelines and outcome-based validation |
| Follow-up | Formula over caller-supplied dimensionless factors | Computation of visibility, urgency/information gain, facility constraints, requests/results |
| Campaign profiles | Explicitly advisory Python data | An enforced, versioned operational policy if desired |
| Broker archive | Actual SQLite byte persistence/replay and dead-letter storage | Polling worker, leases, atomic cursor semantics, replay resolution, stream supervision |
| Service fixtures | Actual capture envelope, serialization, exact-request replay | Safe redaction and execution through the real adapter validation paths |
| Operations | Actual append-only event/schema/drill records | Automatic instrumentation, genuine restore exercises, alerting and incident lifecycle |
| Prospective research | Protocol/cohort storage and numerical diagnostics | Enforced timing, complete denominator, bound analysis and mature labels |
| Promotion | Executable Boolean policy aggregation | Scientific linkage and trust enforcement sufficient to justify promotion |
| Reporting | Real read-only preflight | Exporter and transport are absent; `build_tns_report.py` intentionally exits 78 |
| Legacy root/copy scripts | Executable exploratory historical workflows | Consolidation/quarantine; they are not interchangeable with the current core |

No broad TODO/NotImplemented-style fake implementation was found in the active package scan. Protocol methods containing `...` are legitimate interface definitions; exception-handler `pass` statements are not automatically placeholders. The more important incompleteness is **semantic scaffolding**: recording a “passed” declaration where an executed experiment is still needed.

The legacy scripts retain patterns the canonical package has deliberately improved. For example, `optical_transient_pipeline.py:304` computes aggregate source features before separating physical passbands, and its periodicity exception path returns `False` plus NaNs. Legacy catalogue helpers can mark a service “checked” while also returning an error and zero count. These are hazardous inputs for downstream consumers that only examine Boolean/count fields. Keep them explicitly historical and test disagreement before porting any scientific logic.

## Ultimate implementation checklist

Each unchecked item is proposed work, not a claim that the corresponding capability is wholly absent. P1 items address demonstrated decision/claim boundaries; P2 items complete practical use; P3 items extend scientific value. Assign an owner, evidence artifact, and acceptance result to each item before closing it.

### A. Purpose and product boundaries

- [ ] P1 — Define the primary user and decision: e.g. a transient screener choosing a fixed nightly review budget.
- [ ] P1 — State separately what is implemented, integrated, operationally qualified, and scientifically validated.
- [ ] P1 — Rename or constrain promotion status so a passing diagnostic collection cannot imply proven discovery performance.
- [ ] P2 — Choose one campaign and one measurable primary endpoint for the next release.
- [ ] P2 — Track review yield, missed positives, review time, unresolved fraction, and follow-up completion alongside model scores.
- [ ] P2 — Make the complete default workflow one documented executable example with versioned expected outputs.

### B. Ingestion, identity, and measurement contracts

- [ ] P1 — Add explicit time scale, coordinate frame/epoch, flux unit, zero-point/calibration system, and instrument identifiers where interpretation depends on them.
- [ ] P1 — Preserve those contracts through normalization, features, models, assets, and export; reject incompatible combinations.
- [ ] P2 — Introduce source-qualified global identity and an audited alias/entity map; make campaign membership separate from identity.
- [ ] P2 — Define stationarity versus moving-source behavior instead of forcing both into one coordinate-tolerance contract.
- [ ] P2 — Retain raw broker responses as well as normalized CSV snapshots when exact adapter replay is required.
- [ ] P2 — Implement cursor-safe polling, backfill, retry leases, late arrivals, and append-only dead-letter resolution.
- [ ] P2 — Test provider pagination boundaries, duplicate pages, changed schema, partial batches, and interrupted checkpoints.
- [ ] P2 — Isolate per-object acquisition failures so one bad object does not discard all otherwise useful fetched objects; preserve explicit incompleteness.
- [ ] P2 — Add a second independent adapter to expose hidden assumptions in the common contract.
- [ ] P3 — Define bounded-memory ingestion/storage formats after measuring real batch sizes.

### C. Photometry and scientific features

- [ ] P1 — Validate supplied flux calibration and image association separately from numerical feature extraction.
- [ ] P2 — Add reference cases with independently computed feature values and documented tolerances.
- [ ] P2 — Exercise multi-survey same-band data, non-detections, negative difference flux, sparse cadence, outliers, and changing noise.
- [ ] P2 — Record decision-time truncation explicitly; do not let future light-curve history enter a retrospective early-discovery score.
- [ ] P2 — Quantify sensitivity to bad observations, sampling gaps, calibration offsets, and source blending.
- [ ] P2 — Add fit uncertainties or stability diagnostics for features used to justify prioritization.
- [ ] P3 — Evaluate richer temporal/color features only with a clearly stated channel and calibration contract.
- [ ] P3 — Extend host association with measured catalogue density/completeness and calibrated uncertainty inputs.

### D. Scoring and capacity allocation

- [ ] P1 — Preserve ranking-score semantics in every CSV, UI, paper figure, and model comparison.
- [ ] P2 — Benchmark the existing heuristic before changing its hand-chosen scales and weights.
- [ ] P2 — Make the prediction/scoring backend explicit and versioned in analysis artifacts.
- [ ] P2 — Persist queue selection route, audit seed, audit population, and propensity into cohort enrollment.
- [ ] P2 — Distinguish random-audit inclusion probability from the overall mixed-policy inclusion probability.
- [ ] P2 — Bind a nightly/session definition to the budget; avoid singleton timestamp folds.
- [ ] P2 — Track unfinished review work and repeated candidate versions without silently spending budget twice.
- [ ] P3 — Add campaign-specific utility only after measuring tradeoffs against the shared baseline.

### E. Catalogue and external-evidence validation

- [ ] P1 — Replay recorded fixtures through real parsers/gates, asserting exact clear/match/error outcomes.
- [ ] P1 — Cover malformed-success responses, empty bodies, partial results, timeouts, rate limits, disabled dependencies, stale checks, and query mismatch.
- [ ] P1 — Fix fixture redaction and empty-body round trips.
- [ ] P2 — Qualify adapter behavior against recorded provider/version contracts and explicitly dated live checks.
- [ ] P2 — Add bounded per-service concurrency, retry classification, rate-limit handling, and overall request budgets.
- [ ] P2 — Cache only query-bound results with policy-aware TTL and epoch coverage.
- [ ] P2 — Retain response interpretation/version alongside response digest.
- [ ] P2 — Define an explicit correction path for erroneous historical positive matches without silently deleting a veto.

### F. Review interface and authentication

- [ ] P1 — Enforce authenticated identity/roles for workflows that claim independent people.
- [ ] P1 — Bind identity policy to candidate versions and preflight; cover adjudications as well as reviews.
- [ ] P1 — Retain sufficient signed-assertion verification evidence and trusted-key policy for audit.
- [ ] P2 — Implement expiry-at-use, key rotation/revocation, and maximum assertion-lifetime policy at the application boundary.
- [ ] P2 — Display channel-aware light curves, error bars, upper limits, and science/reference/difference images together.
- [ ] P2 — Summarize the decision-relevant evidence before the raw JSON payload.
- [ ] P2 — Add filter/sort/search/pagination and review-set membership; the current root view lists at most 500 ledger candidates.
- [ ] P2 — Provide abstention, disagreement resolution, version-change warnings, and clear missing-evidence status.
- [ ] P2 — Add keyboard navigation, accessible contrast/focus behavior, and consistent image descriptions.
- [ ] P2 — Copy and hash media into portable dossiers instead of relying solely on supplied image path strings.
- [ ] P3 — Add blind review mode and measure inter-reviewer agreement and decision time.

### G. Ledger, artifacts, and operational reliability

- [ ] P1 — Move ledger initialization into a failure-recorded run boundary.
- [ ] P1 — Make broker cursor checks atomic under concurrent writers.
- [ ] P2 — Add schema-version migrations for every new persistent store, with upgrade/rollback compatibility tests.
- [ ] P2 — Define a complete backup set: ledger, immutable run files, broker archive, assets, protocol/cohort, and trusted identity metadata.
- [ ] P2 — Execute restore into a clean destination and verify hashes, foreign references, and preflight behavior.
- [ ] P2 — Add crash reconciliation for completed files whose ledger publication did not finish.
- [ ] P2 — Instrument real CLI/adapter/pipeline operations into the operations ledger rather than requiring only manual event entry.
- [ ] P2 — Implement incident acknowledgement/resolution and campaign-scoped health windows with minimum activity.
- [ ] P2 — Normalize operational timestamps to UTC before indexed comparisons.
- [ ] P2 — Monitor service latency, retry/error rates, queue age, disk space, artifact growth, and backup age.
- [ ] P3 — Establish storage retention and archival tiers without breaking evidence reconstruction.

### H. Scientific evaluation and outcome data

- [ ] P1 — Bind promotion to protocol, exact cohort, model, labels, reference, budget, and every analysis parameter.
- [ ] P1 — Enforce prospective timing or explicitly label retrospective reconstruction.
- [ ] P1 — Define and actually execute missing-outcome/censoring policy; unresolved objects must not silently become negative labels.
- [ ] P1 — Replace pipeline-completeness claims based on known-template injection with end-to-end recovery.
- [ ] P2 — Create a frozen, reviewed outcome dataset with alias grouping, label provenance, maturity rules, and retraction handling.
- [ ] P2 — Capture the complete upstream denominator and reasons for exclusion.
- [ ] P2 — Use explicit temporal blocks and score-generation cutoffs; distinguish fixed-score evaluation from rolling refitting.
- [ ] P2 — Require meaningful sample sizes and report subgroup support as well as aggregate metrics.
- [ ] P2 — Compare heuristic, supervised baseline, and research models at the same review budget and data cutoff.
- [ ] P2 — Define uncertainty assumptions, repeat/multiple-comparison policy, and locked-test access rules before optimizing.
- [ ] P2 — Include no-injection controls, nuisance variations, and false-positive burden in injection experiments.
- [ ] P2 — Run a hidden-output prospective shadow study before model-assisted decisions.
- [ ] P3 — Estimate selection functions only once ingestion, selection, review, follow-up, and outcomes share a reconciled denominator.

### I. Supervised learning and JEPA

- [ ] P1 — Keep JEPA shadow-only until comparative evidence justifies a controlled change.
- [ ] P2 — Separate “calibration fitted” from “calibration shown adequate in this deployment domain.”
- [ ] P2 — Add model-card metadata, feature contracts, training cutoff, entity-map version, and rollback artifact.
- [ ] P2 — Provide a documented prediction path and persist its output provenance with candidate ranking.
- [ ] P2 — Evaluate drift, missing-feature support, and abstention outside validated domains.
- [ ] P2 — Test whether cadence normalization removes useful absolute-duration information in JEPA; retain physical duration/cadence features where justified.
- [ ] P2 — Address survey/instrument identity and calibrated cross-band meaning in JEPA tokens; the current vocabulary is survey-agnostic.
- [ ] P2 — Represent limiting-depth information explicitly if non-detections are meant to constrain physical behavior, rather than contributing mainly timing/flags.
- [ ] P2 — Run multi-seed, frozen-embedding, random-encoder, masking, time, passband, and missingness ablations.
- [ ] P2 — Inspect collapse, effective rank, nearest-neighbor duplication, survey shortcuts, and label leakage.
- [ ] P3 — Add image/context fusion only after light-curve-only baselines and evidence acquisition are qualified.

### J. Architecture, maintenance, and release quality

- [ ] P1 — Add direct tests for all new research/operations/identity/promotion contracts.
- [ ] P2 — Split the 1,825-line CLI into command families with shared boundary validation and thin handlers.
- [ ] P2 — Split ledger migrations/storage from review authorization; split pipeline orchestration from artifact serialization.
- [ ] P2 — Replace repeated loosely typed payload reconstruction with versioned typed boundary models and centralized serializers.
- [ ] P2 — Reuse strict digest/time/number validators across the new modules; enforce finite values consistently.
- [ ] P2 — Separate research-only convenience inputs from authoritative API inputs.
- [ ] P2 — Consolidate duplicate historical script copies and make their execution status obvious.
- [ ] P2 — Keep paper figures, code claims, schemas, README, and roadmap aligned with the actual integrated path.
- [ ] P2 — Remove tracked coverage output from release source and ensure generated/runtime files are ignored appropriately.
- [ ] P2 — Make a reproducible developer environment and run mypy in it; preserve clean minimum-install and all-extras checks.
- [ ] P2 — Add supported Python 3.12 to CI or revise the support claim; add OS/filesystem checks matching intended users.
- [ ] P2 — Record tested dependency resolutions for scientific releases, alongside the broad installation requirements.
- [ ] P2 — Verify installed-wheel end-to-end analysis/review-set behavior, not only imports/help/config.
- [ ] P3 — Establish component owners, compatibility/deprecation policy, and benchmark budgets for latency and memory.

### K. Follow-up, reporting, and external actions

- [ ] P2 — Keep the disabled legacy report builder disabled until a new exporter consumes exact-version preflight.
- [ ] P2 — Build a draft exporter with explicit units, coordinates, times, evidence links, and the precise reviewed version.
- [ ] P2 — Recheck duplicate evidence immediately before the human-controlled external action.
- [ ] P2 — Implement facility-specific visibility and exposure/cadence constraints before interpreting follow-up factors operationally.
- [ ] P2 — Record request, acknowledgement, failure, returned observations, and resulting labels as distinct states.
- [ ] P2 — Add dry-run, idempotency, least-privilege credentials, and an explicit human action for external submission.
- [ ] P3 — Close the feedback loop from follow-up outcome to ranking evaluation and subsequent model training.

## Extensions with the highest potential value

| Extension | User benefit | Prerequisite | Evidence of success |
|---|---|---|---|
| Evidence workbench | Review one object without reconstructing its story from JSON | Channel-aware plots, asset binding, identity | Faster review with equal or better decision quality |
| Candidate timeline and version diff | Understand exactly what changed since the last decision | Existing version ledger plus change summaries | Reviewers identify material changes reliably |
| Historical replay laboratory | Compare policies on the same arrivals and budgets | Raw snapshots, decision-time cutoffs, mature labels | Reproducible disagreement and yield analysis |
| Outcome-linked learning | Improve priorities using actual scientific results | Trusted labels, denominator, temporal evaluation | Locked and prospective benefit over heuristic |
| Analogue explorer | Find known events resembling a candidate | Curated embeddings and label provenance | Useful analogues without duplicate/leakage shortcuts |
| Follow-up planner | Choose feasible next observations | Site/instrument constraints and outcome tracking | More useful returned observations per budget |
| Population selection analysis | Quantify what the system tends to miss | Complete intake and audit/follow-up denominator | Defensible completeness estimates in declared strata |
| Multimodal research | Combine light curves, stamps, and host context | Qualified acquisition and unimodal baselines | Incremental benefit under matched evaluation |

These are proposals grounded in the repository's architecture, not a claim that a particular external product or model is currently the best choice.

## Recommended execution order

1. **Repair qualification claims and add negative tests:** F01–F05, F08–F09. Preserve the current local core as the reference.
2. **Make the operational history honest and recoverable:** cursor transactions, terminal manifests, incident resolution, real restore/replay exercises.
3. **Complete one review loop:** bound assets and plots, authenticated decisions, exact-version outcomes, coherent CLI documentation.
4. **Build the dataset and denominator:** bound enrollment, mature labels, decision-time replay, real review windows, preregistered comparison.
5. **Prove incremental value:** establish the supervised baseline, then assess JEPA and richer extensions using the same evaluation contract.

The milestone that would change this project's standing most is a small, independently reviewable campaign whose entire evidence chain can be replayed and whose improvement over the simple baseline is measured. That would convert the existing engineering foundation into a defensible scientific instrument.
