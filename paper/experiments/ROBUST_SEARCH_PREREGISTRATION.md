# Robust transient-search qualification: prospective v2 study

Authoritative machine-readable artifacts, in order:

1. `robust_search_protocol.v2.json`
2. `robust_search_amendment.v2.0.1.json`
3. `robust_search_amendment.v2.0.2.json`

This Markdown file is a human-readable index of that frozen design. It does not override the machine-readable artifacts. Earlier versions remain in Git history. Both amendments were written before any v2 candidate-development, calibration, locked-evaluation, or generalization-probe performance statistic was generated.

## Claim boundary

This is a prospective synthetic statistical qualification study informed by already observed v1 failures. It is not an independent preregistration of those earlier results.

A passing result would support only this statement:

> A frozen SIDEREA shadow-search statistic controlled per-curve false alarms over the prespecified synthetic nuisance envelope while retaining the prespecified useful recovery relative to declared comparators.

It would not establish astronomical completeness, purity, physical classification, novelty, discovery probability, survey-wide false-discovery control, live broker safety, reportability, or operational readiness. A complete prospective real-data denominator remains a separate requirement.

## Why this study exists

The existing matched-template search is executable, but its nominal significance is conditional on the assumed noise model. Preserved v1 results showed that this is not a minor caveat. An IID-calibrated bank had a 1.3% false-alarm fraction under IID Gaussian noise but 45.4% under AR(1) rho 0.7 and 71.0% after one positive 8-sigma outlier. A bank calibrated to the known AR(1) rho 0.7 covariance moved the failure: 1.1% under the matching null, 41.7% under IID noise, and 80.5% with the isolated outlier. A separate declared-timescale stress test also failed under underestimated errors, heavy tails, changing variance, and correlation-timescale mismatch.

Those results falsify a broad interpretation of the current empirical p-value as a generally reliable significance measure. They do not falsify matched filtering. V2 asks a narrower question: can a deliberately conservative statistic retain useful recovery while controlling false alarms over one finite, frozen family of misspecifications?

## Frozen scientific question

Can a frozen matched-template statistic satisfy all of the following on untouched locked data?

- Every prespecified calibration-envelope null regime has false-alarm fraction `<= 0.01`.
- Every regime's two-sided 95% Wilson upper bound is `<= 0.015`.
- Macro-average paired 4-sigma recovery improves over the envelope-calibrated single-epoch comparator by at least 0.05 absolute, with the 95% paired-bootstrap lower bound above zero.
- Under matched IID Gaussian noise, 4-sigma recovery is no more than 0.10 absolute below the v1 raw bank.

Failure of any safety gate blocks promotion. A failed gate remains a publishable negative result and is not permission to retune against locked data.

## Effective candidate statistics

The base protocol originally listed three candidates. The pre-result v2.0.1 amendment removed the Huberized candidate because its baseline-invariance and heteroskedastic/correlated-error semantics were under-specified. Defining those choices after observing performance would create avoidable researcher degrees of freedom.

V2 therefore has exactly two effective candidates.

### A. Raw bank with nuisance-envelope calibration

Use the existing maximum positive profiled matched-template statistic. The statistic itself is unchanged; only the calibration principle changes. The provisional and final thresholds are the maxima of the corresponding regime-specific 0.995 empirical quantiles.

### B. Selected-template leave-one-observation-out stability

Let `T_full` be the current maximum statistic and retain the template selected by the full curve. Delete each observation in turn, refit the constant background on the retained covariance marginal, and evaluate that same selected template. Define

`T_stable = min(T_full, min_i T_selected_without_i)`.

The template is deliberately not reselected after deletion. If a deletion makes the selected template unidentifiable, the research statistic fails closed. This quantity is an empirically calibrated search statistic, not a Gaussian z-score, chi-square, probability, or physical-class score.

## Development and candidate selection

The base total of 2,000 development null trials per regime is unchanged, but v2.0.1 splits it into two independent halves:

- 1,000 threshold-construction trials per regime; and
- 1,000 feasibility-evaluation trials per regime.

For each candidate, construct a provisional threshold from only the threshold-construction half. Each regime uses the 0.995 empirical quantile with NumPy's `method="higher"`; the candidate's provisional threshold is the maximum over regimes. Apply that threshold only to the independent feasibility half. A candidate is infeasible if any regime has false-alarm fraction above 0.02.

Among feasible candidates, select the one with the highest frozen macro-average 4-sigma recovery. If candidates differ by less than 0.01 absolute, choose the simpler candidate: raw bank before leave-one-out stability. Freeze the selected implementation and source digest before calibration.

Development signal evaluation uses 250 trials for every family x width x noise-regime cell, exactly 10 paired draws on each of the 25 frozen cadences. Signal centers are independent `Uniform(0,60)` days; edge and seasonal-gap misses remain part of end-to-end recovery rather than being conditioned away.

## Calibration and locked threshold

After candidate selection, generate an independent calibration set using the calibration seed namespace. For the frozen selected statistic, estimate each null regime's 0.995 `higher` empirical quantile and take the maximum as one locked threshold. Detection uses `statistic >= threshold`; ties are not jittered and calibration tie counts are retained.

The threshold cannot be changed after any locked-evaluation statistic is observed.

The primary single-epoch comparator is calibrated under the same nuisance-envelope principle on the same independent v2 calibration curves. This prevents the primary utility comparison from being confounded by deliberately different false-alarm calibration philosophies.

## Prespecified nuisance envelope

The calibration envelope contains:

- IID Gaussian noise;
- AR(1) rho 0.3, 0.5, and 0.7;
- OU-like covariance with 80% correlated variance at 1-, 6-, and 20-day timescales;
- measurement errors underestimated by a factor of 1.5;
- Student-t(3) noise scaled to unit variance;
- variance doubling in the second half of the curve;
- one positive 6-sigma outlier;
- one positive 8-sigma outlier;
- two positive 5-sigma outliers; and
- a seasonal-gap cadence under matched Gaussian noise.

The envelope is deliberately adverse but finite. It is not asserted to span real astronomical systematics.

## Locked generalization probes

Only after statistic and threshold freeze, evaluate:

- AR(1) rho 0.85;
- 1% contaminated Gaussian noise with a sigma-8 contamination component; and
- linear variance drift from 0.75x to 1.75x nominal variance.

Each probe uses 5,000 trials, 250 on each of the 20 ordinary cadences. Probe results cannot alter candidate selection, threshold calibration, promotion gates, or primary endpoint definitions.

## Cadence and reported-error locks

The study uses 20 ordinary irregular cadences and 5 seasonal-gap cadences, each with 64 epochs over 60 days. The exact arrays are deterministic children of `SeedSequence(2026091120)` and are bound by `robust_search_cadence_lock.v2.json` to canonical manifest SHA-256

`5abfdaa328f5793e92bed7aa6dcfaade44ac1a54a1996b8c310e51112dc72451`.

The exact manifest still needs to be materialized as `robust_search_cadences.v2.json` before performance execution. The generator and digest are already frozen.

Each cadence also has one fixed 64-element reported-error vector generated from the reserved child streams 25 through 49, with values drawn from `Uniform(0.7,1.3)`. The deterministic complete error manifest is bound by `robust_search_reported_errors.v2.json` to SHA-256

`c047f7c56138ba562ad41e960d8ee52b8c773d199c9347e64e0db39bde857bd7`.

## Locked signal design and weighting

The base value of 1,000 locked signal trials per family x amplitude x signal-noise-regime cell remains the total sample size; width is a prespecified within-cell factor rather than a multiplier of that count.

Every such cell uses exactly 40 paired draws on each of 25 cadences. Widths 1, 3, and 10 days are assigned deterministically from global trial index and cell index, yielding 334/333/333 trials per width with the extra trial rotating across cells.

For the primary 4-sigma utility endpoint, compute recovery separately within each cadence for all 4 families x 3 widths x 4 signal-noise regimes, take the unweighted mean of those 48 cell recoveries, then take the unweighted mean across the 25 cadence-level values. The paired effect is selected-statistic macro recovery minus single-epoch macro recovery using the same trials and aggregation.

## Comparators

### Primary utility comparator

Maximum positive standardized residual after fitting the constant baseline, envelope-calibrated on the independent v2 calibration curves with the same max-over-regime 0.995 threshold principle.

### Matched-IID non-inferiority comparator

The v1 raw bank is used only for the matched-IID 4-sigma non-inferiority gate and descriptive matched-IID comparisons. On each frozen cadence it reproduces the v1 4,095-curve IID calibration and empirical-p rule, with comparator-calibration streams disjoint from v2 envelope-calibration streams.

### Oracle covariance reference

The existing covariance-aware bank may be reported when the true simulated covariance is supplied. It is an oracle reference, not an operational comparator, and does not imply that a deployed search can know the correct covariance.

## Uncertainty and safety diagnostics

Primary false-alarm intervals remain the preregistered marginal two-sided 95% Wilson intervals, with exact numerator and denominator shown for every regime. The primary paired recovery interval is a cadence-level paired percentile bootstrap with 10,000 replicates from `numpy.random.default_rng(2026091104)`.

Because 14 separate marginal Wilson intervals do not themselves provide simultaneous 95% family coverage, v2.0.2 additionally requires a secondary conference-facing table of one-sided exact-binomial upper bounds using Bonferroni family-wise alpha `0.05/14`. This diagnostic does not alter the frozen promotion gate.

## Phase integrity

The eventual runner must enforce the following state progression:

`development_complete -> selection_frozen -> calibration_complete -> threshold_frozen -> locked_evaluation_complete -> generalization_complete`

`siderea.research.robust_phase_receipts` now provides fail-closed immutable receipts for that sequence. Every receipt binds exact artifact SHA-256 digests; every phase after development must bind the immediately preceding verified receipt. Mutated artifacts, overwritten receipts, skipped phases, duplicate artifact paths, cycles, and paths outside the study root fail closed.

The researcher-facing `verify_robust_search_predevelopment.py` entrypoint now verifies the base protocol, v2.0.1 amendment, v2.0.2 amendment, and reported-error lock together. A subprocess regression test executes that entrypoint directly so stale CLI/script wiring cannot escape coverage merely because its helper function passes unit tests.

No phase-control artifact computes a candidate statistic, threshold, false-alarm count, or recovery value.

## Reproducibility bundle

Before locked evaluation, retain at minimum:

- base protocol and both amendments with exact digests;
- exact cadence manifest and reported-error lock;
- exact selected implementation source and digest;
- environment and dependency inventory;
- template-bank identities;
- complete development per-trial records and selection receipt;
- complete calibration per-trial records and threshold receipt; and
- a machine-readable claim-boundary record.

After evaluation, additionally retain:

- every locked null per-trial statistic;
- every paired signal trial and method outcome;
- exact counts, marginal Wilson intervals, and the secondary simultaneous safety table;
- cadence-level utility summaries and paired bootstrap samples/summary;
- all generalization-probe records;
- runtime and memory summaries;
- source/environment/result digests; and
- a final result manifest binding the complete bundle.

No failed stress case may be removed from the final artifact set.

## Current implementation status

### Completed before performance execution

- [x] Base v2 protocol frozen and byte-locked.
- [x] Prior v1 failures preserved explicitly as prior information.
- [x] V2.0.1 fixes the same-sample feasibility flaw and removes the under-specified Huber candidate.
- [x] V2.0.2 freezes signal/cadence allocation, weighting, bank centers, comparator calibration, bootstrap mechanics, generalization allocation, and secondary family-wise safety reporting.
- [x] Deterministic cadence generator and canonical manifest digest frozen.
- [x] Deterministic reported-error generator and canonical manifest digest frozen.
- [x] Selected-template leave-one-out statistic implemented in the research namespace without changing v1 semantics.
- [x] Research statistic tests cover one-point outlier collapse, supported multi-epoch signal, covariance use, constant curves, and validation behavior.
- [x] Predevelopment verifier checks both amendments and the reported-error lock.
- [x] Researcher-facing verifier entrypoint is exercised by an end-to-end subprocess regression test.
- [x] Fail-closed phase receipt chain implemented and tested.

### Still required before the first performance statistic

- [ ] Exact-head CI must pass after the latest integrity changes.
- [ ] Materialize and commit `robust_search_cadences.v2.json`; its bytes must reproduce the frozen SHA-256.
- [ ] Reconcile any cadence-identifier wording with the canonical generated manifest before a runner depends on string IDs; never silently reinterpret a frozen text field after seeing results.
- [ ] Implement the v2 runner with explicit development/calibration/locked/generalization modes, exact allocation checks, disjoint seed namespaces, source snapshots, per-trial output, and mandatory phase receipts.
- [ ] Add tests for exact null allocations, locked width assignment, pairing, comparator calibration, seed disjointness, and refused phase skipping.

### Then execute exactly once per frozen phase

- [ ] Development; freeze candidate and source digest.
- [ ] Independent calibration; freeze selected threshold and comparator thresholds.
- [ ] Locked null and paired signal evaluation.
- [ ] Generalization probes only after the locked-evaluation receipt exists.
- [ ] Aggregate results solely from retained per-trial records.

## Core assumption still at risk

Leave-one-observation-out stability directly tests dependence on a single corrupted measurement. The nuisance envelope deliberately also includes two positive 5-sigma outliers. Two mutually supporting contaminated observations may survive every one-point deletion and therefore expose a real limitation of the v2 candidate. That outcome should not be designed away inside v2.

If v2 reveals this failure, the clean follow-up is a separately preregistered v3 candidate based on fixed-selected-template bounded `k=2` deletion stability, calibrated and evaluated on new data. It must not be added to v2 after locked behavior is observed. A robust Student-t or other heavy-tailed likelihood is another possible v3 direction, but it requires fully specified heteroskedastic/correlation semantics before evaluation.

## Conference-readiness boundary

A complete v2, including a failed v2, can support a serious synthetic robustness/methods result if the full protocol, per-trial records, adverse regimes, code identity, uncertainty analysis, and reconstruction bundle are published without cherry-picking.

It still cannot support real-sky completeness or discovery-performance claims. Those require the broader repository work on measurement contracts, time/flux/coordinate provenance, background-noise calibration, survey-wide/repeated-testing error control, template-grid loss, evidence-version binding, and a complete object-grouped prospective real cohort with mature outcomes and fixed review budget.

The scientifically strongest path is therefore: finish v2 without retuning; publish the full success/failure surface; then freeze and execute the prospective real-data cohort as a separate stage.