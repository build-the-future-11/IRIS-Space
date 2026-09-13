# SIDEREA — final manuscript and submission checklist

Prepared 2026-09-08 from the manuscript source, paper/AUDIT.md, final-check-rerun.json,
FINAL_TODO.md, and the latest local TNS qualification checks.

**Current verdict:** suitable scope for a software/methods and historical campaign
paper; final submission readiness is not established. Real-sky detection performance,
comparative ML usefulness and physical discovery claims remain unsupported.

A checkbox means its acceptance criteria were verified, not merely that prose was
written. Existing experiments are recorded below as prior evidence; they were not
rerun while preparing this checklist. The execution notes below record subsequent manuscript, tooling and PDF edits.

## A — Freeze the contribution and distinguish evidence sources

- [x] **A01 — State one primary contribution in the abstract and introduction.** Describe auditable, evidence-bound, human-supervised transient triage. State what this adds beyond a ranked candidate list; do not advertise a validated new astrophysical classifier.
- [x] **A02 — Separate four evidence categories throughout.** Label historical I SPY campaign results, current SIDEREA implementation tests, synthetic detector experiments, and proposed prospective evaluation. Acceptance: no historical outcome is attributed to controls or models introduced afterward.
- [x] **A03 — Shorten the abstract around question, method, supported findings and limits.** Retain only headline numbers needed for the contribution; move detailed software counts and operational accounting to their tables where venue rules permit. Acceptance: every remaining number resolves to the claim ledger.
- [ ] **A04 — Freeze the manuscript's software revision.** Choose a tagged/referenced source revision and record its validation evidence. The current manuscript's 405 tests/78.35% describe an earlier check; final-check-rerun.json reports 405/78.34% on 44d2867; later local TNS work passed 416/78.43% and is not yet committed. Preserve these as separate dated records, or update all manuscript references to a newly frozen revision. Do not silently substitute counts across revisions.
- [x] **A05 — Correct historical/current runtime ambiguity.** The limitations section says the audit lacked astronomy dependencies. Tie that statement to its original execution environment; distinguish installed dependencies from an actually executed live integration. Verify environment manifests rather than infer live readiness from installation.
- [x] **A06 — Qualify the injection–recovery limitation.** Change the unqualified 'No injection–recovery analysis was performed' to refer to the historical campaign and/or absence of real-background recovery studies. Explicitly acknowledge the separately reported synthetic experiments.

## B — Reconcile every empirical and historical claim

- [ ] **B01 — Recompute campaign totals from surviving source records.** Reconcile 24 productive runs, 3,824 distinct objects, 424,223 input rows and 223,938 retained rows. Record the duplicate-pull identity and exclusion rule. Separate rows, unique objects, repeated evaluations and productive/failed runs.
- [ ] **B02 — Audit all stage-specific denominators.** Explain exactly why TNS uses 200 evaluations and catalog checking uses 193; preserve missingness and repeated-object caveats. Never divide incompatible stage totals to imply end-to-end purity.
- [x] **B03 — Reproduce the July 5 comparison.** Record pre/post run membership, weighting, statistic, 50,000-draw bootstrap seed and resampling unit; regenerate point estimates and intervals. Describe the discontinuity as confounded observational evidence, not a causal improvement.
- [ ] **B04 — Verify both claimed TNS designations.** Attach dated primary registry references or permitted archived records linking each designation, internal ID, reporter attribution and relevant timestamps. Distinguish historical submission from the current read-only client. Where evidence is incomplete, narrow the statement explicitly.
- [ ] **B05 — Reconcile candidate case studies.** For AT 2026rsp and the withheld, wording-veto, stale and incomplete examples, link each factual assertion to surviving evidence. Do not infer a spectrum, physical class, final disposition or follow-up result that is not recorded.
- [ ] **B06 — Complete the claim-source ledger.** For each abstract/result/conclusion/table claim, record source path, row/field, transformation command, artifact digest, evidence category and limitation. Mark unavailable row-level histories unavailable rather than reconstructing invented observations.

## C — Check mathematics and scientific interpretation

- [ ] **C01 — Check equations against executable behavior.** Map ranking, candidate identity, reportability, queue allocation and detector equations to functions/tests. Define every symbol, unit, range and relevant assumption; explicitly separate legacy and current formulas.
- [x] **C02 — Bound the safety proposition.** State that fail-closed monotonicity follows from the defined conjunction of predicates. Separate mathematical behavior of that gate from correctness/completeness of catalog contents, human judgment and astrophysical validity.
- [x] **C03 — Describe the template search completely.** Specify template families, amplitude/background fits, timing/width bank, units, error model, covariance conditioning and numerical failure behavior. Label phenomenological shapes as such; do not infer physical parameters without the required calibration and astrophysical inputs.
- [x] **C04 — State exactly what p-values control.** Document the Monte Carlo null, full-bank statistic, plus-one rank construction, simulation count, resolution floor and within-source channel correction. Explicitly exclude unestablished survey-wide and repeated-look false-alarm control.
- [x] **C05 — Disclose the known-covariance assumption.** Describe covariance-assisted experiments as supplied/oracle covariance and adaptive follow-up where applicable. Do not equate that result with estimating unknown real-sky noise successfully.
- [x] **C06 — Preserve adverse noise results prominently.** Reconcile every correlated-noise, isolated-outlier, heavy-tail, error-scale and nonstationarity result against the archived trial statistics. Present null failures next to recovery results; no selective figure or abstract claim that hides them.
- [x] **C07 — Keep uncertainty interpretations separate.** Distinguish run-cluster bootstrap intervals, finite Monte Carlo uncertainty and JEPA repeated-mask variation. Explain dependence and what each interval does not include; do not call mask variation a generalization interval.
- [x] **C08 — Keep baseline and JEPA claims at smoke-test scope.** Report the tiny sample/split sizes and reason calibration was withheld. State that three-epoch execution and repeatable loss establish numerical operation, not superiority or useful astronomical representations.

## D — Make experiments and figures independently reproducible

- [ ] **D01 — Assemble a self-contained experiment bundle.** Include protocol, exact source revision, dependency inventory, seeds, command lines, inputs or acquisition instructions, trial statistics, summaries and figure generators. Acceptance: every manuscript experiment resolves to these components without private workspace paths.
- [ ] **D02 — Rehearse reconstruction outside the working tree.** Build/install the frozen package, rerun each reported synthetic experiment into a fresh directory and compare semantic outputs and digests. Explain expected timestamp/platform differences; preserve failed runs separately.
- [x] **D03 — Rebuild figures from recorded measurements.** Each figure must have a reproducible command and source-data reference. Mark simulations explicitly; prohibit illustrative or manually chosen values from appearing as measured results.
- [ ] **D04 — Check figure/caption completeness.** Include units, sample size, denominator, method, uncertainty meaning and exclusions. Make axes readable at final size, distinguish curves without color alone, and verify tables match plotted data.
- [x] **D05 — Add a compact evidence-status table.** Columns: question, evidence actually available, supported conclusion, missing validation. Include software invariants, historical operations, synthetic detection, live services and real-sky performance.
- [x] **D06 — Keep a compact reproducibility entry point.** Provide a single documented sequence that generates the supported tables/figures and reports missing inputs explicitly. Do not claim unavailable historical raw data can be reconstructed.

## E — Position the work and improve the manuscript

- [ ] **E01 — Sharpen comparison with astronomy workflows.** Explain where SIDEREA fits relative to ALeRCE/SN Hunter, BTS, AMPEL and relevant anomaly/representation work. Compare task, review role, evidence handling and demonstrated evaluation; support novelty claims with primary sources.
- [ ] **E02 — Verify the bibliography.** Check author/title/year/version/DOI or arXiv identifier for every entry against the primary publication. Identify preprints accurately and ensure each citation supports its associated claim.
- [ ] **E03 — Borrow experimental discipline, not unrelated architecture.** Adapt shared baselines, component ablations and held-out transfer tests from the YCRG comparison. Do not add a graph VAE or biology-specific likelihood merely to increase apparent sophistication. Cite their work only if a substantive method or artifact is actually used.
- [x] **E04 — Reduce roadmap dominance.** Keep the main prospective-evaluation section focused on the primary question and decisive design choices. Move detailed unexecuted protocols to an appendix/supplement; use future tense consistently.
- [ ] **E05 — Make the paper understandable without the repository.** Define SIDEREA, IRIS, I SPY, broker, detection, object, reportability, designation and physical classification on first use. Include one end-to-end example with explicit historical/synthetic/current provenance.
- [x] **E06 — Audit operational promises.** Describe TNS testing as read-only search qualification; no submission transport, photometry acquisition, image/WCS qualification or hosted identity system is implied. Document any live evidence only after execution.

## F — Required only for a stronger detection-performance paper

These are an expansion of the scientific claim, not prerequisites for honestly
presenting the existing methods/historical-audit contribution. They cannot be
replaced by software tests or additional prose.

- [ ] **F01 — Preregister a real-data evaluation.** Freeze population, eligibility, chronological windows, primary endpoint, useful effect size, review budget, outcome delay and stopping rule before looking at test outcomes.
- [ ] **F02 — Preserve the complete eligible population.** Include rejected and unreviewed objects; reconcile exclusions, duplicate identities and missing outcomes. TNS nonappearance alone is not a negative astrophysical label.
- [ ] **F03 — Obtain independent, evidence-backed labels.** Define real transient, artifact, variable, duplicate, uncertain and censored outcomes. Preserve adjudication and inter-reviewer disagreement; obtain image/spectral evidence as required by each label.
- [ ] **F04 — Compare methods under the same information budget.** Evaluate significance, heuristic, template search, logistic baseline and JEPA using identical eligible inputs and review budgets. Fit preprocessing/calibration only on allowed training data; group object aliases and preserve temporal cutoffs.
- [ ] **F05 — Execute prespecified ablations.** Remove multi-band information, prior non-detections, temporal templates, covariance treatment or embeddings one at a time. Keep safety gates enforced operationally and distinguish retrospective research scoring from live action policy.
- [ ] **F06 — Inject signals into real background measurements.** Freeze amplitude/timescale/cadence/host-context strata; include unmodified nulls, gaps, artifacts and uncertain error scales. Report recovery and false alarms jointly, with dependence-aware uncertainty.
- [ ] **F07 — Evaluate a held-out later period.** Freeze the method before that period. Add cross-survey transfer only after units, time systems, passbands and calibration contracts are qualified.
- [ ] **F08 — Report the actual outcome, including failure.** Present precision/recall at the review budget, delay, false alerts, missing outcomes and review cost. Include intervals and a justified uncertainty unit; report inconclusive or negative results without tuning on the frozen test set.

## G — Final release and submission gate

- [ ] **G01 — Confirm target venue and author details.** Obtain the current template, limits and submission requirements; confirm names/order, affiliations, contacts and corresponding author. Do not invent affiliation or infer a venue-specific requirement without checking.
- [ ] **G02 — Resolve reuse and availability terms.** Copyright owners must decide code/data/manuscript terms; pyproject.toml currently declares LicenseRef-Proprietary. Check third-party data/figure permissions and describe inaccessible historical records honestly.
- [ ] **G03 — Produce a stable cited research release.** Freeze code, paper source, evidence manifests and permitted data; record commit/tag and immutable archive identifier where available. Make the code/data availability statement point to that actual release.
- [x] **G04 — Rebuild the final PDF after all edits.** Compile from the release bundle; resolve missing references/citations and check fonts, page count, figure placement, tables and appendix numbering. Inspect every page visually; save source/PDF digests and exact build command.
- [ ] **G05 — Obtain an independent scientific review.** Have a reviewer inspect claim scope, denominators, uncertainty, adverse cases, evidence attribution and limitations. Resolve substantive objections or disclose the unresolved limitation before submission.
- [ ] **G06 — Perform the final consistency pass.** Compare abstract, tables, conclusions, README, claim ledger, software record and PDF against the same frozen revision. No stale 'current' counts, unsupported discoveries, demo figures presented as results or completed-tense descriptions of planned studies.
- [ ] **G07 — Obtain author approval and submit the exact reviewed artifact.** Retain final approval, submission receipt and file identities. A GitHub push is not a paper submission or acceptance.

## Prior verified evidence to preserve

- [x] The manuscript already separates ranking from reportability and physical classification.
- [x] Historical policy drift and the missing closed cohort are explicitly disclosed.
- [x] Earlier synthetic IID/covariance/noise reruns reproduced archived results; final-check-rerun.json records their actual revision and digests.
- [x] Latest local TNS preparation checks passed 416 tests and 96 subtests with 78.43% coverage; the 18 qualification tests use simulated transport, not live TNS evidence.

## Execution order and external dependencies

1. A and B: fix claim/revision boundaries and reconcile existing evidence.
2. C, D and E: verify methods, reproduce artifacts and edit the narrative.
3. G: resolve venue/authorship/licensing, freeze, render, review and submit.
4. F: execute before adding real-sky performance or comparative-ML claims.

External inputs: venue choice and author confirmation; redistribution decisions;
missing historical primary evidence; live-service credentials if live qualification
is claimed; representative photometry/labels and independent scientific reviewers
for the expanded evaluation. Unavailable evidence must narrow claims, not be filled
with plausible values. Sections A–E contain substantial executable local work and
are not classified as credential blockers.


## Executed finishing pass — 2026-09-08

- Rewrote abstract and contribution statement; separated dated software snapshot,
  historical summaries, simulations and planned studies. Clarified the scope of
  missing historical injection studies and astronomy-client availability.
- Narrowed historical TNS/discovery language consistently across results, table,
  case study, discussion and conclusion. Primary registry access was unavailable;
  B04 remains open. The 3,824-object total is summary-attributed, not independently
  regenerated from an unavailable cached inventory; B01 remains partial.
- Reproduced all historical derived metrics and 50,000-draw bootstrap exactly.
  Reproduced 30 IID rows, 30 supplied-covariance rows and seven noise rows, with
  identical per-trial statistic digests. Added generated tables for recovery and
  every adverse null result; tables compare byte-for-byte with their generators.
- Added paper/reconstruct.py, an allowlisted source-copy workspace, input hashes,
  runtime dependency inventory, per-command logs, strict scientific comparisons,
  failure reports and no-clobber output. Added five regression tests. The command
  uses copied source; a fresh independently installed-package reconstruction and
  a locked cross-platform environment are not claimed, so D01/D02 remain partial.
- Added an evidence-status table and moved the detailed unexecuted protocol to
  Appendix D. Improved float placement after inspecting excessive empty space.
- Rechecked metadata/abstract alignment for five recent primary arXiv sources;
  corrected the claim ledger's AHA author attribution. Full bibliography audit
  E02 remains open. See claim-source-ledger.md and method-contract-map.md.
- Full make check passed: 421 tests, 96 subtests, 78.42% coverage, strict typing,
  lint, formatting and compilation. make paper-check passed all five new tests
  and lint of the reconstruction/figure/experiment tools.

Evidence: research/paper-final-reconstruction.json,
research/paper-final-input-manifest.json, research/paper-final-runtime-dependencies.txt,
research/paper-finishing-checks.txt and research/paper-finishing-build.txt.
Final PDF inspection and release-bundle results are recorded separately in
research/manuscript-verification.json. Submission approval and real-data performance
remain open; unchecked items have not been renamed complete merely by documenting them.

Additional inspection corrected the rendered queue equation typo and replaced its
simplified allocator with the actual audit-first, thresholded-anomaly and backfill
contract. The general equation audit C01 remains open beyond the mapped checks.

Final PDF: 29 pages, rebuilt with Tectonic; all pages visually inspected, with
updated equations and tables checked at reading size. No undefined references,
overfull boxes, clipping or overlap found; underfull spacing warnings remain.
G04 is validated for the local immutable review bundle. Venue-specific changes will require another build and inspection.

The copied review bundle independently compiled; all 29 pages render identically
at 0.75 scale. PDF container bytes differ, so no binary-identical-PDF claim is made.
The final compressed bundle is integrity-checked against its per-file SHA-256 manifest.

### Subsequent evidence-integrity pass — 2026-09-08

The paper's tables and reconstruction now use the same archive verifier. It checks
all report/protocol/source/trial digests, complete unique experiment rows, plus-one
ranks and derived counts/fractions/Wilson intervals. All 67 archived result rows and
the two manuscript tables remain unchanged after independent recomputation.
Unsupported noise scenario labels now fail instead of silently simulating ordinary
Gaussian noise. Both runners reject mismatched installed detector source; non-60-day
noise studies use the declared duration for their gap and variance boundary.

`make paper-check` passes 49 tests, including adversarial re-hashed reports, protocol
validation, output preservation and an actual 90-day small experiment. The original
frozen protocols, manuscript PDF and previous sealed review bundle remain unchanged.
The prior bundle is an earlier snapshot and does not contain these new safeguards.
This pass strengthens C06/D03/D06; it does not mark the remaining external or scientific
gates complete. Detailed source identities and verification logs are recorded in
`research/integrity-pass-20260908/`.
