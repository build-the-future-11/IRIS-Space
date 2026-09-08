# SIDEREA final execution checklist

Current local validation: 405 tests and 96 subtests passed, 78.35% coverage; strict typing passed for 74 source files.
The latest first-run example and detector hardening are implemented. This file lists
remaining work, not features already completed. See PROJECT_FINISH_CHECKLIST.md for
historical implementation evidence. An unchecked task is not a claim that its current
implementation is broken; some tasks qualify an existing primitive for a larger use.

Release boundaries:

- Offline synthetic use: follow docs/FIRST_RUN.md now.
- Public research alpha: complete R01–R12 and P01–P06. Explicit limitations are acceptable.
- Real-data scientific claims: additionally complete the applicable D/M/L/U/S tasks.
- Hosted multi-user operation: additionally complete O01–O06.
- X tasks are optional; they are not reasons to delay a properly scoped research alpha.

Every completion needs a test, checked artifact, or recorded external evidence.
Do not convert failed requests to clearances, tune a frozen test set, retroactively
authenticate old decisions, or replace unfinished work with a success flag.

## R — Public research release

- [x] **R01 — Freeze the release scope.** In README.md and release notes, identify local CSV triage, evidence review, and shadow experiments as supported. Name live polling, physical classification and unattended reporting as unqualified or absent. **Done:** CLI help, README and paper make the same claims.
- [x] **R02 — Validate the exact release revision.** Run formatting, lint, strict typing, full coverage tests and compilation from Makefile after the last source edit. **Done:** save command, Python/dependency versions, exit status, test count and coverage; do not reuse the earlier 400-test result for changed code.
- [x] **R03 — Run the actual CI matrix.** Inspect .github/workflows/ci.yml results for Python 3.11, 3.12, 3.13 and 3.14, quality, security and packaging jobs. **Done:** every required job passes on the published revision, or the documented support policy is deliberately revised with evidence.
- [x] **R04 — Rebuild clean distributions.** Build the sdist and then its wheel using `python -m build`; do not reuse build/lib from before the IRIS rename. **Done:** the wheel contains siderea, default.toml and py.typed, contains no retired iris package, and installs in a fresh environment outside the checkout.
- [x] **R05 — Smoke-test the installed wheel.** Execute doctor with explicit writable storage, config-show, example analysis, review-set verification, outcome-summary, backup verification and transient-search. **Done:** outputs are readable; example analysis remains blocked from reporting; pulse/constant shadow outputs retain explicit status and scope.
- [x] **R06 — Rehearse the beginner instructions.** Follow docs/FIRST_RUN.md in a new core-only virtual environment, then repeat with the optional scientific dependencies. **Done:** missing optional packages produce useful diagnostics, every copied command works, and first run needs no private credentials.
- [ ] **R07 — Verify output collisions and interruption messages.** Exercise existing run IDs/output paths, unreadable input, unwritable storage and Ctrl-C in supported long operations. **Done:** existing evidence survives; the user receives an actionable error; a started analysis has a terminal or explicitly recoverable manifest.
- [x] **R08 — Audit the exact publication set for secrets.** Inspect staged changes, example configurations, fixture bytes, notebook/script outputs and paper artifacts. **Done:** only intentional public author metadata and synthetic test credentials remain; real credentials, if found, are rotated and removed through an explicit history policy.
- [x] **R09 — Reconcile the overlapping audit documents.** Update PROJECT_FINISH_CHECKLIST.md, docs/PROJECT_STATUS_2026-09-08.md and paper/AUDIT.md with dated current evidence. **Done:** completed backups/dashboard/atomic cohorts are not described as missing; partial image, covariance and live-service work is not described as complete.
- [x] **R10 — Preserve newer remote work.** Fetch origin, inspect the current divergence and integrate its changes, including the observed cool-stuff-master/requirements.txt update. **Done:** the release contains the intended local migration and the newer remote dependency change; no force push or discarded contributor work.
- [x] **R11 — Create and verify the release commit.** Stage an explicitly inspected set including new source, tests, fixtures, documentation and intended paper outputs. **Done:** review staged diff, run git diff --check, commit with a descriptive message, and inspect git status for unintended leftovers. Do not silently overwrite the pre-existing staged migration.
- [x] **R12 — Publish and verify the commit.** Push the authorized destination normally and read back its commit SHA. **Done:** remote SHA matches the intended commit and CI is checked. Describe the release as experimental research software; package-index publication or journal submission is a separate action.

## D — Measurement contracts and provenance

- [ ] **D01 — Make the time scale explicit.** Extend ingest/schema.py, domain.py, normalized records and archived configuration with the supported scale and conversion provenance. **Done:** a UTC/TDB mismatch cannot silently enter one curve; JD/MJD conversion has a known-reference regression test; changed semantics produce new scientific versions.
- [ ] **D02 — Declare flux units and calibration.** Record unit, zero point/magnitude system when applicable, calibration identifier and whether flux is forced/difference/total. **Done:** incompatible measurements are rejected or explicitly converted; neither ranking nor transient-search silently pools them.
- [ ] **D03 — Preserve coordinate context.** Carry coordinate frame, reference epoch and uncertainty into association requests and evidence bindings. **Done:** frame mismatch, RA wrap, polar positions and epoch-dependent moving-source cases have explicit tested outcomes.
- [ ] **D04 — Version measurement corrections.** Define append-only replacement/retraction records using upstream observation identity and revision. **Done:** corrected photometry creates a new candidate version, while the previous measurement and reviews remain reconstructable.
- [ ] **D05 — Distinguish repeated exposures from duplicates.** Extend ingest and shadow-search validation to use stable survey/exposure/observation IDs when supplied. **Done:** replaying one exposure cannot increase significance; two genuinely distinct same-time observations are not discarded solely because their timestamps match.
- [ ] **D06 — Add audited cross-survey aliases.** Create an append-only alias map with matching evidence and an explicit ambiguity state. **Done:** one physical source cannot enter a cohort twice merely through two broker names; uncertain associations remain unresolved.
- [ ] **D07 — Archive the normalization boundary.** Save sanitized supported raw responses, parser version, exact query and normalized artifact hash. **Done:** a test reconstructs normalized data from archived bytes without contacting the service and detects parser/schema drift.
- [ ] **D08 — Qualify quality cuts on real products.** Assemble reviewed accepted and rejected examples per survey/passband, including saturation, negative difference flux, limits and bad uncertainties. **Done:** publish the disagreement table and exclusions rather than assuming generic cuts are valid everywhere. Requires survey data and scientific review.

## M — Detection mathematics and model reliability

- [x] **M01 — Add an outlier-influence diagnostic.** In research/transients.py, measure how the fitted excess changes when the most influential observation is omitted and report supporting observations/epochs. **Done:** a single corrupted point is visibly distinguishable from distributed support. If this becomes a decision rule, calibrate the entire new rule on separate null data.
- [ ] **M02 — Estimate noise only from eligible background data.** Build a versioned background-noise calibration artifact with selection rules, training interval, covariance parameters and uncertainty diagnostics. **Done:** the target/test curve cannot contribute to fitting its own noise model, and an incompatible artifact is rejected.
- [ ] **M03 — Test noise-model misspecification.** Extend the preserved stress experiment with underestimated errors, heavy tails, changing variance, seasonal gaps and correlation timescales outside calibration. **Done:** publish recovery/false-alarm counts for every prespecified case, including failures; do not report only the oracle-covariance result.
- [ ] **M04 — Account for survey-wide and repeated testing.** Specify the family of objects and monitoring looks before selecting a correction or sequential rule. **Done:** report the hypothesis count, adjusted decision quantity and its assumptions; current within-object p-values must not be described as survey-wide false-alarm control.
- [ ] **M05 — Quantify template-grid loss.** Inject peaks between searched centers, durations below/above the width grid, and events near observing-window edges. **Done:** plot recovery versus mismatch and cadence; report runtime alongside any denser-grid improvement using an untouched evaluation sample.
- [ ] **M06 — Define a censored-data likelihood before adding limits.** Implement a likelihood contribution appropriate to upper limits rather than substituting the limiting flux as a detection. **Done:** likelihood tests match analytic cases, metadata identifies the censoring convention, and the existing measured-flux path remains unchanged.
- [ ] **M07 — Bind shadow outputs to evidence versions.** Add an adapter that links a search report to candidate version, normalized-input digest, code identity, bank and noise-calibration identity. **Done:** a report from another version cannot be displayed as current evidence or satisfy a promotion gate.
- [ ] **M08 — Demonstrate added value before adding families.** Compare heuristic, calibrated logistic baseline, template search and JEPA-derived ranking on the same frozen objects and budget. **Done:** report uncertainty, missing outcomes, runtime and ablations; retain a simpler model if the extra model does not establish useful improvement.

## L — Broker and catalogue operation

- [ ] **L01 — Extend real-parser fixture qualification.** Cover ALeRCE, SkyBoT, SIMBAD and VSX as well as the existing TNS runner. **Done:** each adapter has success, empty, malformed, partial, timeout and rate-limit cases; only a valid complete response can support clearance.
- [ ] **L02 — Obtain reviewed live captures.** Capture approved, sanitized requests/responses with query radius, epoch, service/parser version and expected interpretation. **Done:** independent review establishes that the fixture represents the intended live contract. A caller-supplied live label alone is insufficient.
- [ ] **L03 — Add a bounded polling supervisor.** Build on operations/broker_store.py with persisted lease ownership, retry schedule, cursor checkpoints and graceful shutdown. **Done:** restart and competing-worker tests show no skipped interval or duplicated scientific event; stop/lag states are visible.
- [ ] **L04 — Define backfill and late-arrival behavior.** Use an explicit overlap window and idempotent upstream observation/revision IDs. **Done:** an observation arriving after the first poll updates exactly once and retains its acquisition/arrival provenance.
- [ ] **L05 — Bound whole-batch latency.** Pass a remaining deadline through broker/catalogue calls and cap retry/backoff by that deadline. **Done:** a stalled service cannot indefinitely block a batch, and exhaustion records unknown/error evidence rather than a non-match.
- [ ] **L06 — Couple caching and schema monitoring to adapters.** Cache only exact compatible queries with TTL checks; emit observed schema fingerprints automatically. **Done:** stale, wrong-radius, wrong-epoch or changed-schema responses cannot be silently reused as clear evidence.

## U — Reviewer experience

- [ ] **U01 — Add verified image stamps.** Extend operations/assets.py and review rendering for science/reference/difference images tied to candidate version, sky position, filter and observation epoch. **Done:** wrong-position/version images are rejected and missing images are explicit. Requires representative licensed survey products.
- [ ] **U02 — Preserve immutable review-set context.** Add next/previous navigation, route, rank and remaining count from a verified review-set manifest. **Done:** completing one queue never silently substitutes current candidate versions for the selected archived versions.
- [x] **U03 — Complete stale-evidence comparison.** Keep the existing saved rationale and show added/retracted observations plus changed checks between submitted and current versions. **Done:** users can recover text and inspect the change without an old decision being copied onto new evidence automatically.
- [x] **U04 — Add plot range controls.** Provide resettable time/channel selection and indicate visible versus total observations. **Done:** selection changes only the preview, never stored evidence or scientific calculations; the complete JSON download remains version-bound.
- [ ] **U05 — Finish interactive accessibility verification.** Test queue, candidate, forms, errors and outcomes with keyboard navigation and a screen reader, at 320/375/768px and desktop. **Done:** focus is visible, chart alternatives are available, controls are labelled, and a review can be completed without a pointer.
- [x] **U06 — Build an unresolved-evidence inbox.** Aggregate missing, stale, failed and conflicted evidence by candidate/version with a source link and supported next action. **Done:** resolving an item requires new valid evidence; merely dismissing a UI row cannot clear the scientific gate.

## S — Real scientific evaluation

- [ ] **S01 — Choose and freeze one campaign.** Specify population, dates, eligibility, primary endpoint, minimum useful effect, review budget, outcome maturity delay and responsible scientific reviewers before intake. **Done:** the validated preregistration predates the intake window.
- [ ] **S02 — Preserve the full intake denominator.** Record every upstream eligible arrival, exclusion reason and enrollment decision, including objects never reviewed. **Done:** broker archive, enrollment and exclusion totals reconcile without unexplained missing objects.
- [ ] **S03 — Define outcome labels.** Specify what constitutes real transient, artifact, known variable, duplicate report, uncertain and censored; define any binary mapping separately. **Done:** every evaluated label has version-bound evidence and adjudication, and unknown outcomes are never silently negative.
- [ ] **S04 — Bind prediction-time information.** Record checkpoint, preprocessing, training cutoff, latest allowed observation, prediction time and input identity for each score. **Done:** a future-trained model or future observation is rejected even if the score file otherwise matches the cohort.
- [ ] **S05 — Implement rolling-origin refits or a frozen predictor.** Extend research/benchmark.py and ML integration so each fold reconstructs permitted training and inference. **Done:** entity disjointness and time cutoffs are tested, preprocessing fits only eligible training data, and fold artifacts reproduce the scores.
- [ ] **S06 — Choose the uncertainty unit before evaluation.** Specify object/night/campaign clustering, dependence assumptions, bootstrap method and handling of repeated sources. **Done:** synthetic coverage/sensitivity checks support the estimator; results disclose when sample size cannot resolve the useful effect.
- [ ] **S07 — Execute a shadow campaign without promotion.** Run all declared methods on the same frozen arrivals, preserving the incumbent action policy and recorded audit sampling. **Done:** compare useful outcomes per fixed review budget, false positives, missing outcomes, reviewer minutes and safety escapes with intervals.
- [ ] **S08 — Obtain an independent scientific decision.** Review cohort completeness, label evidence, leakage, adverse cases and prespecified endpoints. **Done:** an authorized scientific signoff cites exact artifacts and either accepts the supported claim or records why promotion failed. Software tests cannot substitute for this decision.

## O — Hosting, operational safety and recovery

- [ ] **O01 — Add real per-user hosted sessions before hosting.** Integrate an approved identity issuer, role assignment and expiry enforcement. **Done:** two browser users have distinct principals; replayed, expired and wrong-role sessions fail. A shared HMAC assertion file remains a local-session mechanism.
- [ ] **O02 — Define key custody and revocation.** Record issuer ownership, storage, rotation overlap and revocation checks. **Done:** a revoked key cannot authorize new writes while historical signed decisions remain auditable; no key is shipped in configuration examples.
- [ ] **O03 — Specify the authenticated transport boundary.** Document and test TLS termination, direct-access restrictions, trusted-proxy handling and permitted origins. **Done:** direct unauthenticated access and forged identity headers fail; loopback-only defaults remain intact.
- [ ] **O04 — Add safe operational telemetry.** Emit run completion/failure, broker lag, deadline exhaustion, unresolved incidents and backup age with allowlisted fields. **Done:** injected secret sentinels never appear in logs, and alert delivery is tested separately from event recording.
- [ ] **O05 — Exercise contention and interruption.** Test simultaneous analysis/review/cohort operations and interruptions around file publication/database commits, using task-owned temporary storage. **Done:** no lost events, silently partial evidence or false completed backups; report measured latency and busy-timeout behavior.
- [ ] **O06 — Define coordinated recovery and retention.** Document which ledgers, broker archives, models, dossiers and identity records must be captured together, plus retention and rollback procedures. **Done:** rehearse restoration on a disposable environment and verify candidate versions, event counts and preflight inputs. The current one-ledger backup is not mislabeled as a distributed snapshot.

## P — Paper and research artifacts

- [x] **P01 — Correct stale verification claims.** Update the abstract, software-verification paragraph/table and conclusion in paper/siderea_transient_triage.tex. They still cite 320 tests/96 subtests and earlier module/coverage values. **Done:** use the exact final-revision evidence; distinguish the latest Python 3.11 run from historical multi-interpreter runs.
- [x] **P02 — Reconcile replay and audit records.** Update the manuscript fingerprint from the matching archived replay artifact; reconcile paper/research/software-verification.json, paper/AUDIT.md and the claim-source ledger. **Done:** every numerical software/replay claim resolves to its actual dated input, command and result, without erasing historical records.
- [x] **P03 — Preserve the experimental claim boundary.** Keep the original correlated-noise and outlier failures, identify the covariance follow-up as adaptive/oracle-covariance, and label baseline/JEPA runs as tiny synthetic smoke tests. **Done:** no sentence turns recovery on simulated pulses into real-sky completeness or physical classification.
- [ ] **P04 — Make experiment reconstruction self-contained.** Include protocols, exact runner/model source snapshots, dependency versions, seeds, per-trial statistics, summary generation and figure generation in the research bundle. **Done:** rerun into a new directory and reconcile counts/digests; record intentional numerical differences across environments.
- [x] **P05 — Rebuild and visually inspect the final manuscript.** Compile after the last text/table update, inspect citations and all pages, and check figures/tables at reading size. **Done:** no stale result table, undefined reference, clipping or unreadable plot labels. Document or remove OS-specific font dependencies rather than silently accepting platform-dependent layout.
- [ ] **P06 — Prepare the public research bundle.** Verify author/title/contact details, data/code availability, bibliography, source/figure inclusion, license compatibility and release commit identity. **Done:** a clean source bundle rebuilds and accurately states unavailable data; external journal/conference submission and repository publication are tracked separately.

## X — Optional extensions after the evaluation foundation

- [ ] **X01 — Facility-aware follow-up.** Replace caller-supplied observability factors with tested site/time/target calculations, horizon/Sun/Moon constraints and provenance. **Done:** compare known cases with an independent ephemeris; output remains a recommendation until a facility workflow is separately authorized.
- [ ] **X02 — Physically interpreted multi-band models.** Add redshift/time-dilation, extinction, passband integration and calibration contracts before fitting luminosity/temperature parameters. **Done:** recover known synthetic parameters, report degeneracy and reject missing physical inputs; do not infer them from arbitrary flux units.
- [ ] **X03 — Leakage-safe retrieval explanations.** Show similar archived examples with identity, temporal eligibility, label provenance and distance semantics. **Done:** no test-object alias or later outcome can leak into a purported point-in-time explanation.
- [ ] **X04 — Probability calibration at adequate sample size.** Train and assess calibration on separate eligible data, with reliability curves, proper scoring rules and uncertainty. **Done:** insufficient class counts retain uncalibrated-score labels; neither JEPA distance nor a template p-value is renamed a discovery probability.
- [ ] **X05 — Add another survey only after the common contract is proven.** Implement its channel, units, time, quality, identity and replay fixture mappings. **Done:** existing conformance tests plus real reviewed fixtures pass without weakening the current survey contracts.

## Recommended execution order

1. R01–R09 and P01–P06: finish a truthful, reproducible public research package.
2. R10–R12: integrate remote history, commit, push and verify CI.
3. D01–D08, L01–L02 and U01: establish trustworthy real-data/evidence boundaries.
4. M01–M07 and S01–S06: establish the detection/evaluation contract before collecting outcomes.
5. S07–S08 and M08: run and judge the real comparison without promising a positive result.
6. Remaining L/U tasks and O01–O06 when sustained or hosted operation is actually required.
7. X01–X05 only where measurements justify the additional scope.

## Execution evidence — finishing pass

P06 licensing dependency: `pyproject.toml` explicitly declares
`LicenseRef-Proprietary`, and no root license grant exists. Copyright owners must
approve the intended code/data/manuscript redistribution terms before this can be
called an openly reusable research bundle. The current declaration is preserved.

- M01: analytic observation-deletion diagnostics are checked against refitting with
  retained covariance marginals; isolated-outlier and broad-support regressions pass.
- U03/U04/U06: `tests/test_review_http.py` and `tests/test_review_inspection.py`
  passed all seven tests after constructing changed evidence through real analysis.
  Filters, stale rationale/comparison, exact-version downloads, authentication and
  the absence of an inbox dismissal endpoint are exercised.
- M03 is **partial**: seven prespecified null stress scenarios were executed and
  all counts/intervals/trial statistics retained in `paper/experiments/noise-stress-final`.
  Signal recovery under these same stress conditions is still open.
- The preserved IID experiment reproduced all 30 result rows and the exact trial
  statistics digest (`paper/research/experiment-reconstruction.json`).
- A clean wheel built and passed core-only CLI smoke checks; the backup harness
  initially selected a forbidden destination inside the artifact root, then passed
  with the correct external destination. The containment check was preserved.

Unchecked engineering items remain open; they are not relabeled as credential
blockers. The research-alpha scope does not imply completion of the real-data,
hosted-operation or optional-extension requirements.

Final local check: `make check PYTHON=.test-tmp/release-env/bin/python` passed
with 405 tests, 96 subtests and 78.35% coverage on Python 3.11.15. Formatting
(107 files), lint, strict typing (74 source files) and compilation passed.
`paper/research/software-verification.json` binds the source/test trees, environment
and preserved log; it does not claim a new multi-interpreter local run.

Manuscript: Tectonic build passed with TeX-distributed fonts; all 29 pages were
rendered and inspected, with detailed inspection of verification/results and
appendix tables. The bibliography intermediate is retained. Remaining underfull
box warnings concern spacing; no undefined citations or clipped content were found.
Publication-pattern scan inspected 220 text files and found only an intentional
`SENTINEL` credential URL in a negative test; `.env.example` contains empty values.
This is a bounded publication audit, not a guarantee against all possible secrets.

Publication status: implementation commit `fd7ec02` was created locally and rebased
on `origin/main`, preserving `01e20b6` and its requests dependency update. Source
and test trees still match the recorded validation digests. R12 is **blocked**:
automatic approval review rejected exporting the broad source/research commit to
`https://github.com/build-the-future-11/IRIS-Space` because the destination lacked
explicit user approval. Exact repository/branch approval has been requested. No
push occurred. R03 remains pending until the published revision can run CI. The
existing remote revision passed CI; that is not evidence for this local commit.

## Published revision recheck

The earlier push-approval blocker is resolved: the user approved publication and
`44d286784c62fdecef391b5647450f7ff19b3385` was pushed to the named GitHub main
branch. CI run 34222812198 passed quality, security, Python 3.11/3.12/3.13/3.14
tests and packaging. The new local run passed 405 tests and 96 subtests with
78.34% coverage, plus formatting, lint, typing, compilation and a fresh build.
All three search experiments reproduced exact result rows and trial digests;
all 20 baseline predictions and JEPA training/validation matched. Full evidence:
`paper/research/final-check-rerun.json`. No source changes were needed.

R06 was subsequently rehearsed in a new Python 3.14.7 virtual environment. A
core-only editable install completed without credentials; `doctor` reported NumPy
and pandas available and each optional science dependency as a warning. The copied
analysis command produced two candidates, both correctly blocked by missing
external evidence, with scientific fingerprint `analysis-7d203c8f40012eb4`.
The copied shadow-search command evaluated the synthetic constant and pulse,
flagged only the pulse, and produced result digest
`684af0a5de0baa26517fae63068d6fc2291f84c67f0dd3e9863a371ee89f5d4a`.
After installing `.[all]`, strict doctor and `pip check` passed; repeating both
commands produced the same fingerprint, decisions and result digest. Temporary
outputs remain under the gitignored `.test-tmp/first-run-core-20260908/` directory.
