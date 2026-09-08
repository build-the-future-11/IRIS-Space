# SIDEREA execution checklist

Started 2026-09-07; expanded 2026-09-08. See [current audit and implementation assessment](docs/PROJECT_STATUS_2026-09-08.md). Operating scope: finish the locally verifiable transient-triage research product, preserve existing scientific/version contracts, and repair the concrete audit findings. Scientific deployment qualification requires real data and independent evaluation; it will not be inferred from synthetic tests.

## P0 — RELEASE BLOCKERS

- [x] Reject nested fixture credentials, unsafe URL credentials, response cookies and credential-bearing structured bodies; round-trip empty response bodies.
- [x] Prevent unrelated or policy-mismatched benchmark/cohort/injection evidence from satisfying promotion checks.
- [x] Separate known-template recovery and recorded qualification declarations from verified production-readiness claims.
- [x] Make broker watermark updates transaction-safe and define replay/retry idempotency.
- [x] Record a terminal failure when ledger initialization fails after creating an analysis run.
- [x] Add direct regression tests for the new operations/research/identity boundaries.

## P1 — CORE PRODUCT

- [x] Enforce explicit review authentication policy at authoritative boundaries without silently changing legacy research records.
- [x] Add a usable authenticated local review path and expire assertions at use.
- [x] Preserve auditable operational incident resolution and dead-letter resolution rather than permanently failing all history.
- [x] Validate forced-photometry calibration types/coordinates and candidate association; accurately label asset verification scope.
- [x] Make benchmark temporal blocks explicit and reject unusable singleton budget evaluations.
- [x] Enforce preregistration timing and distinguish prospective enrollment from retrospective reconstruction.
- [x] Integrate bound cohort selection metadata and mature-outcome validation where supported by existing contracts.

## P2 — QUALITY

- [x] Protect reserved recovery evidence fields and normalize time filtering across timezone offsets.
- [x] Improve review queue filtering/pagination, evidence summaries, and responsive layout.
- [x] Produce a self-contained channel-aware light-curve view from real candidate observations.
- [x] Add negative-path and end-to-end tests for modified workflows.
- [x] Run full tests, lint, formatting, strict type checking and dependency checks in a reproducible environment.
- [x] Build and smoke-test an isolated wheel using the documented local analysis/review workflow.
- [x] Perform a second serious audit of the implemented changes and fix newly exposed issues. Evidence: omitted-publication backup regression, interrupted-restore guard, strict benchmark protocol snapshot and schema-5 migration rehearsal.

## P3 — POLISH

- [x] Document new commands/policies, limitations, migration behavior and recovery procedures.
- [x] Align supported Python versions with CI and preserve generated-artifact hygiene.
- [x] Add a reproducible execution/validation record with actual outcomes.
- [x] Inspect final diff for accidental changes and leave staged user work intact.

## External qualification and optional extensions

- [ ] External: acquire representative mature outcomes, verify live broker/catalogue contracts, and run an independent prospective campaign. Requires real data, service access and scientific reviewers.
- [ ] External: authenticate actual reviewers through a trusted issuer and establish deployment key custody. Local signed-assertion support is not an identity provider.
- [ ] External: validate image WCS/calibration against survey products and qualify actual follow-up/report transport. Requires real evidence and facility/service policy.
- [ ] Optional: new survey adapters, automated telescope scheduling, multimodal models and population-selection inference after the main loop is qualified.

## Validation log

Historical baseline: 320 tests and 96 subtests. Completed re-audit validation is recorded below; historical counts are not the final result.

## Expanded audit backlog — specific problems, solutions and acceptance checks

This is a prioritized backlog, not a promise to add every possible feature. **Engineering** means repository work; **External** requires real services/data/identity/scientific decisions; **Optional** requires evidence that the extension is worth its cost. A checked item above is implemented and has targeted validation. An unchecked item below remains open even when a narrower primitive already exists. P0/P1 scientific-release requirements do not imply the local research CLI is unusable.

### A. Product purpose and claims

- [x] A01 · P0 · Misleading promotion semantics → use `siderea.promotion_report.v2`, explicit local-evidence scope and diagnostic/asset/fixture gate names. Acceptance: reports cannot label the result a scientifically promoted deployment; integration test checks schema/status/scope.
- [x] A02 · P1 · Unclear intended user → document transient screener, reviewer and evaluation researcher, with finite review budget as the core decision. Acceptance: current status document names the user and complete intended loop.
- [ ] A03 · P1 · External · No chosen prospective release campaign → freeze one population, endpoint, minimum useful effect, budget and maturity window with scientific owners. Acceptance: preregistration exists before intake opens.
- [x] A04 · P2 · Engineering · No product-level outcome dashboard → aggregate review yield, latency, workload, missing outcomes and disagreement by campaign. Acceptance: totals reconcile with immutable events and show denominators.
- [ ] A05 · P2 · External · No measured reviewer usability → run observed review sessions and record task completion/error rates. Acceptance: evidence inspection and submission can be completed without developer assistance.

### B. Ingestion, measurement and identity

- [ ] B01 · P1 · Engineering + scientific decision · Implicit time scales → version explicit time scale and epoch conversion policy through ingestion, artifacts and models. Acceptance: incompatible scales cannot silently mix.
- [ ] B02 · P1 · Engineering + scientific decision · Implicit flux units/calibration systems → record units, zero-point system and calibration provenance. Acceptance: inconsistent channels fail validation or require an explicit conversion.
- [ ] B03 · P1 · Engineering + scientific decision · Incomplete coordinate-frame/epoch contract → propagate frame, epoch and positional uncertainty. Acceptance: association tests distinguish incompatible frames and moving-source cases.
- [ ] B04 · P1 · Engineering · Candidate aliases can obscure physical identity across surveys → add a source-qualified identity and append-only alias map. Acceptance: a cross-survey duplicate cannot enter a study as two independent entities without an explicit repeated-event policy.
- [ ] B05 · P2 · Engineering · Observation revisions need a policy beyond exact duplicate rejection → define replacement/retraction semantics with original-byte retention. Acceptance: revised measurements produce new evidence versions and preserve the old record.
- [ ] B06 · P2 · Engineering · Raw adapter response provenance is incomplete → archive bounded original response bytes alongside normalized snapshots and parser versions. Acceptance: normalization can be reconstructed without a live query.
- [ ] B07 · P2 · External · Survey quality cuts are not independently qualified → compare accepted/rejected measurements with representative survey products. Acceptance: documented disagreement and failure cases per survey/passband.

### C. Broker operation and catalogue reliability

- [x] C01 · P0 · Cursor race → acquire the write transaction before cursor validation and reject contradictory retry facts. Acceptance: concurrent watermark/replay regression test passes.
- [x] C02 · P1 · Archive presence did not prove replay → re-ingest archived CSV/sidecar bytes in temporary storage. Acceptance: `broker-check` reports failures for corrupt evidence.
- [x] C03 · P1 · Dead letters stayed permanent blockers → append a reason/evidence disposition while retaining original bytes. Acceptance: unresolved count falls while historical count/bytes remain.
- [ ] C04 · P1 · Engineering · No supervised polling worker → add bounded polling, persisted leases, explicit shutdown and retry scheduling. Acceptance: process restart resumes the committed cursor without lost/duplicate scientific events.
- [ ] C05 · P1 · Engineering · No defined late-arrival/backfill behavior → use bounded overlap windows and idempotent observation identities. Acceptance: replay of a delayed observation produces one traceable update.
- [ ] C06 · P1 · Engineering · Fixture storage is not an adapter qualification harness → replay success, malformed, timeout, rate-limit and partial responses through the actual adapters. Acceptance: every service failure produces blocked/error evidence, never clearance.
- [ ] C07 · P0 for scientific release · External · Live contracts unverified → capture sanitized representative broker/catalogue interactions and expected results. Acceptance: service version, query coverage and response interpretation are independently reviewed.
- [ ] C08 · P2 · Engineering · Per-request retries do not define an end-to-end deadline → apply a campaign deadline and shared service budget. Acceptance: a degraded service cannot hold a batch indefinitely.
- [ ] C09 · P2 · Engineering · Repeated catalogue queries can waste quotas → add TTL-aware, query-bound caching with explicit stale states. Acceptance: cache hits preserve identity/radius/epoch/TTL checks.
- [ ] C10 · P2 · Engineering · Schema monitoring is caller-driven → emit contract checks automatically at adapter boundaries. Acceptance: an unexpected schema is logged and blocks intake/verification.

### D. Security, authentication and governance

- [x] D01 · P0 · Nested fixture secrets → recursively reject recognized credential fields, unsafe URLs, cookies and structured/text bodies. Acceptance: sentinel values never appear in saved fixtures or errors in regression tests.
- [ ] D02 · P1 · Engineering + policy · Opaque binary bodies cannot be exhaustively secret-scanned → introduce an allowed capture-format/content policy and documented sanitation provenance. Acceptance: unsupported sensitive formats are refused before publication.
- [x] D03 · P0 · Typed identities could satisfy a purported authenticated policy → bind authentication and trusted key IDs into candidate policy; verify at review/adjudication writes. Acceptance: absent, expired, wrong-role, wrong-key and forged actor identities fail.
- [x] D04 · P1 · Browser decisions lacked signed identity → load a verified principal per request, derive identity/roles and return controlled session failures. Acceptance: HTTP tests cover persistence and unavailable sessions.
- [ ] D05 · P0 for hosted service · External + engineering · HMAC assertion files are not an identity provider → integrate an approved issuer and per-user session boundary. Acceptance: two browser users receive separate verified principals and roles.
- [ ] D06 · P1 · External + engineering · Key custody/rotation/revocation undefined → define operator ownership, expiry, rotation overlap and revocation evidence. Acceptance: a revoked issuer cannot authorize new writes while old decisions remain auditable.
- [ ] D07 · P1 · Engineering · Hosted transport/access policy absent → define TLS gateway, trusted proxy identity contract and access logs before enabling remote service. Acceptance: direct unauthenticated access and spoofed identity headers fail.
- [ ] D08 · P2 · Engineering · Sensitive logging needs a systematic audit → define safe fields and sentinel tests for adapters, CLI and reports. Acceptance: credentials never enter diagnostics, manifests or exception output.
- [ ] D09 · P2 · External · Reviewer independence needs organizational policy → define conflicts, reviewer assignment and signoff ownership. Acceptance: distinct strings/key assertions cannot be mistaken for independently appointed people.
- [ ] D10 · P2 · Engineering · No stated retention policy → document retention/export/redaction rules for identity and operational evidence. Acceptance: a supported retention procedure preserves scientific provenance without silently rewriting it.

### E. Persistence and recovery

- [x] E01 · P0 · Ledger initialization left open runs → include initialization inside terminal-manifest failure handling. Acceptance: injected initialization failure creates a failed manifest.
- [x] E02 · P1 · Old incidents blocked every future report → append incident resolution and count unresolved failures within the requested window. Acceptance: history remains visible and an unresolved failure still blocks.
- [x] E03 · P1 · Recovery status could be overridden → reserve status/name fields and validate incident references. Acceptance: malformed resolution and conflicting drill evidence are rejected.
- [x] E04 · P1 · Backup checks were declarations only → perform read-only SQLite online backup, restore, integrity/FK checks and row-count comparison. Acceptance: corrupt database fails; source bytes remain unchanged.
- [x] E05 · P1 · Engineering · Database backup excludes linked artifacts → implement a consistent database-plus-artifact export with digest inventory. Acceptance: restore into an empty directory reconstructs candidate dossiers, versions and preflight inputs.
- [x] E06 · P1 · Engineering · Migration rehearsal coverage is limited → maintain representative previous-schema fixtures and migration invariants. Acceptance: reviews/outcomes retain original bindings after upgrade; downgrade is explicitly documented.
- [x] E07 · P2 · Engineering · Batch enrollment commits per entity → add an explicit atomic batch API or resumable batch manifest with partial-state reporting. Acceptance: a failed batch can be retried without ambiguous selection totals.
- [ ] E08 · P2 · Engineering · SQLite contention limits unmeasured → exercise realistic simultaneous analysis/review/enrollment workloads. Acceptance: measured throughput and busy-timeout behavior are documented before choosing a replacement database.
- [ ] E09 · P2 · Engineering · Power-loss boundaries not exhaustively exercised → fault-test publication before/after rename and database commit. Acceptance: every visible artifact is complete or explicitly failed/recoverable.

### F. Evidence and reviewer experience

- [x] F01 · P1 · Raw JSON was the main evidence view → add decision summary and per-survey/passband light curves with errors/limits. Acceptance: actual candidate observations render; labels are escaped and numeric extremes have a fallback.
- [x] F02 · P2 · Queue could not be navigated efficiently → add bounded pagination, literal-ID filtering and state filtering. Acceptance: pages do not overlap and SQL-looking input remains literal text.
- [x] F03 · P2 · IPv6 loopback and missing assertion-file handling were incomplete → choose an IPv6 socket family and controlled session errors. Acceptance: socket-family and HTTP regression tests pass.
- [ ] F04 · P1 · Engineering + external data · No image-stamp evidence panel → show verified science/reference/difference cutouts with provenance links. Acceptance: images correspond to the selected version, coordinates, epoch and band.
- [ ] F05 · P2 · Engineering · Review-set context is missing from browser navigation → add next/previous selected candidate, route/rank and remaining-work counts. Acceptance: reviewers can finish one immutable queue without mixing versions.
- [x] F06 · P2 · Engineering · Stale evidence errors can lose user effort → preserve unsent rationale and show an explicit old/new evidence comparison. Acceptance: stale submission cannot overwrite a decision and text can be recovered.
- [x] F07 · P2 · Engineering · Role-restricted forms can still invite unauthorized attempts → hide/disable unavailable actions with an explanation while retaining server checks. Acceptance: a reviewer sees only permitted actionable controls.
- [ ] F08 · P2 · Validation · Responsive CSS is not a complete mobile audit → inspect queue, plots, history and forms at 320/375/768px and desktop. Acceptance: no page-level horizontal overflow and usable labels/targets.
- [ ] F09 · P2 · Validation · Accessibility has only partial automated/structural coverage → keyboard and screen-reader pass, visible focus, headings, errors and chart alternatives. Acceptance: core review completes without a pointer.
- [x] F10 · P2 · Engineering · Large curves are preview-limited → add explicit full-data export and user-controlled zoom/range. Acceptance: capped preview never implies observations were discarded from scientific evidence.
- [ ] F11 · P2 · Engineering · Missing evidence is scattered across payloads → add a prioritized unresolved-evidence inbox. Acceptance: each issue links to its source/version and an appropriate resolution action.

### G. Cohorts, selection and evaluation

- [x] G01 · P0 · Unrelated cohort/benchmark evidence could pass → bind exact identities/labels/policy and recompute derived benchmark metrics. Acceptance: altered labels, summaries, protocol, budget, confidence or seed fail.
- [x] G02 · P1 · Unique timestamps generated one-object budget folds → support explicit time bins and reject singleton evaluation blocks. Acceptance: intended blocks contain competing candidates.
- [x] G03 · P0 · Retrospective timestamps looked prospective → store capture mode/server record time; reject late freezes and retrospective promotion. Acceptance: reconstruction cannot pass the prospective cohort gate.
- [x] G04 · P1 · Selection was detached from review bundles → verify bundle files, exact versions and deterministic queue allocation; import routes/audit metadata via `--review-set`. Acceptance: tampered bundle fails and all supplied candidates are enrolled with matching selection metadata.
- [x] G05 · P1 · Repeated versions could inflate the cohort and exceed budgets → enforce one physical identifier per study and selected UTC-night budget. Acceptance: duplicate entity/version inconsistency and exhausted budget fail.
- [ ] G06 · P0 for scientific release · External · Upstream denominator is not proven complete → reconcile every arrival with enrollment/exclusion records. Acceptance: totals and exclusions are reproducible from the intake archive.
- [ ] G07 · P1 · Engineering + scientific decision · Precomputed scores lack training/feature cutoff proof → bind checkpoint, preprocessing, prediction time and permitted history per block. Acceptance: future-trained or future-observation scores are rejected.
- [ ] G08 · P1 · Engineering · No complete rolling-refit evaluator → refit on each historical origin or enforce a frozen deployable predictor. Acceptance: fold artifacts reconstruct training, inference and metrics without test leakage.
- [ ] G09 · P1 · Scientific decision · Uncertainty model may not match repeated nights/entities → define cluster/time-block resampling and the decision unit. Acceptance: simulation and sensitivity checks justify the interval estimator.
- [ ] G10 · P1 · External · Mature outcome labels are not a curated scientific dataset → define taxonomy, evidence standards, adjudication and disagreement handling. Acceptance: every binary label has reviewed version-bound support.
- [ ] G11 · P1 · Engineering + scientific decision · Censored outcomes are not a binary-negative shortcut → implement a compatible estimator if censorship is the frozen policy. Acceptance: unresolved cases are excluded/reported or modeled exactly as preregistered.
- [ ] G12 · P2 · Engineering + scientific decision · Selection correction is not yet an analysis product → use recorded audit propensities with positivity diagnostics. Acceptance: estimates show weight sensitivity and cannot claim population performance with zero support.
- [ ] G13 · P2 · Engineering · Protocol mutation and artifact schema migrations need wider adversarial coverage → validate canonical protocol digests at all API entry points and test legacy transitions. Acceptance: in-memory or stored mutation cannot change a frozen decision silently.

### H. Injection, calibration and model research

- [x] H01 · P0 · Matched-filter recovery could imply pipeline completeness → explicitly mark the diagnostic as non-qualifying for completeness. Acceptance: output and promotion gate preserve this scope.
- [x] H02 · P2 · Degenerate/mixed curves could distort injection behavior → reject fewer than three distinct epochs and mixed survey/band sources; handle vanishing template norm. Acceptance: direct negative tests pass.
- [ ] H03 · P1 · Engineering + scientific design · No production-path injection experiment → inject into canonical measurements, rerun actual features/eligibility/ranking/finite-budget selection. Acceptance: deliberately degrading the production scorer lowers measured recovery.
- [ ] H04 · P1 · Scientific design · Positive injections alone cannot measure false positives → include zero-injection controls, real backgrounds, cadence gaps and artifacts. Acceptance: recovery and false-selection rates are both reported.
- [ ] H05 · P1 · External · Gaussian pulses are not a population model → define realistic source families, nuisance distributions and coverage. Acceptance: results state the tested population and unsupported regimes.
- [ ] H06 · P2 · Engineering + data · Logistic baseline training lacks a fully integrated deployment path → bind saved preprocessing/calibrator/model to inference artifacts. Acceptance: batch and single-object inference reproduce held-out scores.
- [ ] H07 · P1 before model use · External · JEPA benefit is unproven → compare heuristic, supervised and representation models on the same frozen folds/budget. Acceptance: effect sizes, intervals and failures are published without cherry-picking.
- [ ] H08 · P2 · Engineering + research · JEPA representation choices need ablation → test time/channel encoding, masking, missingness and normalization choices. Acceptance: fixed seeds/splits and negative outcomes are preserved.
- [ ] H09 · P2 · Engineering · Checkpoint resume needs broader reproducibility qualification → verify optimizer, RNG, preprocessing and token contracts on resumed training. Acceptance: expected deterministic equivalence or documented backend tolerance.
- [ ] H10 · P2 · Engineering + data · Drift/collapse monitoring is not operational → monitor token/feature distributions, embedding variance and cohort shifts. Acceptance: controlled drift triggers a visible warning and model-use policy.
- [ ] H11 · P3 · Optional · Retrieval explanations need a curated reference corpus → attach provenance and scientific context to neighbors. Acceptance: duplicates/aliases cannot inflate apparent novelty or evaluation yield.

### I. Scientific assets, host context and follow-up

- [x] I01 · P1 · Calibration metadata lacked enough validation → enforce nonempty units/system fields, finite/ranged coordinates and candidate association. Acceptance: invalid coordinates/foreign positions fail despite valid file hashes.
- [x] I02 · P1 · Bundles could escape their root through linked paths → resolve and constrain asset paths. Acceptance: external symlink test fails verification.
- [ ] I03 · P0 for image-qualified release · Engineering + data · File hashes do not validate FITS/WCS → decode supported formats and check dimensions, WCS, time, band and measurement association. Acceptance: an unrelated image fails scientific validation.
- [ ] I04 · P1 · External · Forced measurements are supplied rather than independently acquired → integrate an approved survey acquisition/calibration workflow. Acceptance: provenance traces each measurement to the survey product and calibration.
- [ ] I05 · P2 · Engineering + data · Host ranking is a standalone geometry primitive → integrate catalogue candidates, densities and positional uncertainty models. Acceptance: ambiguous/missing-uncertainty cases stay ambiguous on known examples.
- [ ] I06 · P2 · Engineering + scientific decision · Follow-up factors are caller-supplied heuristics → compute visibility, urgency and facility constraints with provenance. Acceptance: impossible observations are never recommended as feasible.
- [ ] I07 · P3 · Optional + external · No follow-up request/result lifecycle → add explicit human-approved requests and returned observation/outcome links. Acceptance: request IDs, retries and results are traceable without duplicate telescope actions.
- [ ] I08 · P3 · Optional + external · No report exporter/transport → implement an independently validated exporter behind current preflight, then approved idempotent transport. Acceptance: stale/blocked versions cannot generate authorized submissions; no automatic sending by default.

### J. Performance, architecture and developer experience

- [ ] J01 · P2 · Engineering · Performance limits are unmeasured → profile representative candidate/observation volumes, memory and SQLite query plans. Acceptance: publish measured capacity and bottlenecks before optimizing.
- [ ] J02 · P2 · Engineering · Large payload listings can over-fetch → select queue-summary fields and index measured filter patterns where justified. Acceptance: bounded queue latency at the chosen campaign scale.
- [ ] J03 · P3 · Engineering · CLI is becoming a large command router → extract operations/research/review command families with stable argument contracts. Acceptance: existing command/help/exit-code tests remain unchanged in behavior.
- [ ] J04 · P3 · Engineering · Persistence migrations share large modules with business rules → isolate named, tested migration steps. Acceptance: upgrade invariants are easier to review without rewriting stable APIs.
- [ ] J05 · P3 · Engineering · Historical duplicates may confuse contributors → keep prominent legacy boundaries and a porting map; archive only by explicit repository policy. Acceptance: contributors can identify one canonical source tree.
- [ ] J06 · P2 · Engineering · Declared lower bounds are not a full compatibility matrix → test both minimum-supported and current dependency sets. Acceptance: supported constraints match install/type/test results.
- [ ] J07 · P2 · Engineering · Reproducible releases need an environment record → publish a tested constraints snapshot and dependency provenance per release. Acceptance: a fresh machine can recreate the tested environment.
- [ ] J08 · P2 · Validation · Local package rename left stale build output → use clean sdist-to-wheel builds and inspect wheel members. Acceptance: no retired `iris` package or unrelated artifacts are distributed.
- [ ] J09 · P2 · External/CI · CI matrix has not been run by this session → run all supported Python jobs and dependency audit on the intended release revision. Acceptance: no unresolved CI failures or actionable vulnerabilities.
- [ ] J10 · P3 · Engineering · Generated artifacts need ownership/retention rules → document which data are ignored, versioned, archived or release artifacts. Acceptance: final diff contains only intended code/docs/tests and preserves existing contributor work.

### K. Publication and final release evidence

- [ ] K01 · P0 for scientific release · External · Paper claims may precede current qualification → reconcile every numerical claim with exact run/data/code artifacts. Acceptance: no table or abstract claim relies on synthetic software tests as scientific evidence.
- [ ] K02 · P1 · Engineering + data · Figures can drift from results → regenerate publication plots from a bound results manifest. Acceptance: every plotted value traces to an actual result row and exclusions are visible.
- [ ] K03 · P1 · External · No independent prospective replication → obtain a separately reviewed campaign/replication using the frozen protocol. Acceptance: full positive, null and failed results are retained.
- [ ] K04 · P2 · Engineering + policy · Release claim boundaries need a signed handoff → publish package version, environment, validation commands, data exclusions and remaining blockers. Acceptance: another reviewer can reproduce the local release and understand what it does not establish.

## Recommended implementation order after this session

1. Complete final local validation/docs and clean wheel verification; resolve any concrete failures first.
2. Establish one real campaign and trusted review identity boundary; qualify the existing adapters with a fault replay matrix.
3. Close prediction provenance, complete intake denominator and image validation gaps.
4. Run the production-path injection and frozen prospective comparison.
5. Add reviewer/outcome UX and operational supervision based on measured use.
6. Consider new surveys, retrieval, telescope integration and additional models only after their value can be measured.


## Re-audit execution — 2026-09-08

- [x] Reject an archive that omits a referenced publication file even if its inventory digest is recomputed; verification also works while original files are offline (`test_evidence_backup.py`).
- [x] Reject backup paths with noncanonical/reserved names and invalid file-size metadata; prevent backing up an interrupted restore.
- [x] Rehearse schema-5 migration from the previous implementation's synthetic SQL fixture; preserve all historical rows and avoid inventing authentication (`test_ledger_migration_v5.py`).
- [x] Add complete version-bound JSON evidence downloads, including historical versions, with session checks and explicit 400/404 errors (`test_review_http.py`).
- [x] Snapshot validated preregistration before benchmark binding to avoid using mutable caller policy.
- [x] Qualify recorded TNS requests through the real adapter without network fallback (`test_fixture_qualification.py`). C06 remains open for other adapters and a representative fault matrix.
- [x] Preserve stale-submission rationale and link to current evidence. F06 remains open for a full old/new evidence comparison.
- [x] Export complete observations beyond the plot preview. F10 remains open for interactive range/zoom.
- [ ] Complete the final interactive browser/accessibility pass. Browser policy verification was unavailable on this re-audit; the tool denied access. Earlier responsive checks and current HTTP tests are separate evidence, not a completed screen-reader check.

Validation checkpoint: full suite **386 passed, coverage 77.86%**; subsequent HTTP/authentication/fixture suite **16 passed**. Strict typing passed for **72 source files**. Ruff checks and formatting passed for **103 files**. Final package/workflow verification follows below. No live-service or scientific validation is inferred from these tests.


### Final re-audit validation evidence

- Full regression: `python -m pytest --cov=siderea --cov-report=term-missing` — **387 passed**, **77.95% coverage** (`.test-tmp/finish-validation/pytest-reaudit-final.log`).
- Strict typing: `python -m mypy src/siderea` — **72 source files, no issues**.
- Ruff lint and format check — **PASS**, **103 files formatted**; `pip check` — **no broken requirements**.
- Isolated sdist-to-wheel build — **PASS** (`.test-tmp/reaudit-release/`). Installed wheel resolves from site-packages outside the checkout; retired `iris` package absent.
- Installed CLI smoke — configured `doctor --strict --json`, `config-show`, CSV `analyze`, `review-set`, Python `verify_review_set`, `outcome-summary`, `evidence-backup` and `evidence-backup-verify` all **PASS** (`.test-tmp/installed-reaudit/`).
- Installed `preflight` — expected **exit 3**, real reasons and `ready=false` for synthetic candidates lacking required scientific evidence.
- Default doctor storage check detected that the home-directory default is unwritable in this sandbox; explicit writable storage configuration passed. No permission check was weakened.
- `git diff --check` — **PASS**. User's staged migration preserved; no staging, commit, push or deployment performed.
- Interactive final browser validation — **BLOCKED** by unavailable browser admin-policy verification. Retry through the authorized browser once policy verification works. Current HTTP tests do not substitute for screen-reader testing.

Release assessment: **NOT READY for hosted or scientific production use**. The local research workflow is tested and packageable. Open engineering work in the expanded checklist (including review-set navigation, interactive plot controls, broader adapter qualification and provenance-bound rolling prediction) remains open rather than being relabeled as external. Scientific datasets, live-service evidence, organizational identity and facility policies remain external requirements.

## Final scientific extension and publication pass

- [x] Implement unknown-location Gaussian, asymmetric exponential, Bazin and fallback-shape searches with a jointly fitted constant background and positive amplitudes.
- [x] Calibrate the entire template search, retain finite Monte Carlo p-values and correct channels within objects.
- [x] Support declared covariance with positive-definite/conditioning checks; keep the new scores outside reportability gates.
- [x] Add regression comparisons against weighted and generalized least squares, numeric/input boundaries, repeatability and no-clobber CLI publication.
- [x] Run fixed-design recovery, noise/outlier stress, covariance follow-up, baseline and JEPA smoke experiments and preserve measured failures (`paper/experiments/`; synthetic diagnostics only).
- [x] Update and render the manuscript with current software evidence, model assumptions and actual experiment results (29 pages visually inspected).
- [ ] Complete final package/tests/diff checks and publish the authorized commit without discarding newer remote work.

## Pre-run hardening

- [x] Reject exact duplicate shadow-search measurements to prevent false independence and inflated significance.
- [x] Report evaluated channels, minimum resolvable corrected p-value and explicit insufficient-resolution status.
- [x] Reject oversized correlated-noise inputs before quadratic covariance allocation.
- [x] Add `examples/transient_flux.csv` and `docs/FIRST_RUN.md`; execute the fixed-seed offline example (pulse flagged, constant source unflagged).
- [x] Validate the expanded detector suite: 13 tests passed. Full regression result recorded after completion below.

Pre-run validation completed: **400 tests passed**, **78.10% coverage**
(`.test-tmp/finish-validation/pytest-first-run.log`). Ruff lint and formatting passed
for 105 files; strict typing passed for 73 source files; dependency verification
reported no broken requirements. The actual shadow example returned p=0.001 for
the simulated pulse and p=0.311 for the simulated constant source. These values
are conditional synthetic diagnostics, not discovery probabilities.

## Reviewer and noise-model finishing pass

- [x] Add selected-template observation-deletion influence diagnostics, retaining the
  calibrated decision rule and correctly marginalizing retained correlated errors.
- [x] Complete stale-version comparison and resettable MJD/survey/band preview filters.
- [x] Add an authenticated current-preflight blocker inbox without a dismissal path.
  F11 remains open for priority ordering; the implemented view pages current candidates.
- [x] Run seven fixed null-noise stress cases and retain adverse results; recovery in
  these stress cases remains open under FINAL_TODO M03.
- [x] Reproduce all 30 preserved IID result rows and the per-trial statistics digest.

The earlier notes that F06/F10 were incomplete are historical and superseded by
this pass. The seven HTTP/inspection regression tests passed; final full checks
are recorded separately after completion.

Final finishing-pass local verification: **405 tests and 96 subtests passed**,
**78.35% coverage**, strict typing for **74 source files**, formatting for
**107 files**, lint and compilation all passed. Installed core-only wheel checks
and deterministic replay passed; package and experiment evidence lives under
`paper/research/`. Intermediate failing checks remain preserved locally and are
not used as release results.

Local publication preparation completed at `fd7ec02`; newer remote work was
preserved. Push is blocked by automatic approval review pending explicit approval
of `build-the-future-11/IRIS-Space`, branch `main`. Nothing was pushed. This supersedes
earlier phase-specific statements that no local commit had been created.
