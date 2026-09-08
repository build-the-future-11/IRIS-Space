# Robust transient-search qualification: frozen prospective follow-up

Machine-readable protocol: `robust_search_protocol.v2.json`

## Status

This document freezes the next synthetic statistical qualification study before any v2 development execution. It is a **prospective follow-up informed by already observed failures**, not an independent preregistration of the earlier experiments. The earlier IID-calibrated, covariance-calibrated, and noise-stress results remain part of the record and must not be hidden, overwritten, or relabelled as holdout evidence.

The study is intentionally narrow. A successful result would support only this statement:

> A frozen SIDEREA shadow-search statistic controlled per-curve false alarms over the prespecified synthetic nuisance envelope while retaining the prespecified useful recovery relative to declared comparators.

It would **not** establish astronomical completeness, purity, physical classification, novelty, a discovery probability, live broker safety, survey-wide false-discovery control, or reportability. Real-sky evidence and a complete prospective denominator remain separate requirements.

## Why this is the highest-priority statistical problem

The current matched-template search is executable and useful as a software diagnostic, but its nominal significance is conditional on the assumed noise model. The prior experiments show that this condition is not a minor technicality.

The IID-calibrated bank produced a 1.3% false-alarm fraction on IID Gaussian nulls, close to the nominal 1% target, but 45.4% under an AR(1) null with rho 0.7 and 71.0% after one positive 8-sigma outlier. The follow-up bank calibrated to the known AR(1) rho 0.7 covariance recovered the matching null at 1.1%, but its false-alarm fraction became 41.7% on IID noise and 80.5% for the isolated outlier. A separate declared-timescale stress experiment again behaved near nominal under its matched model while failing badly when errors were underestimated, tails were heavy, variance changed over time, or the correlation timescale was wrong.

Those results falsify a broad interpretation of the current empirical p-value as a generally reliable significance measure. They do **not** falsify matched filtering itself. They show that model-specific calibration can move the failure from one noise regime to another.

The next question is therefore not “can another covariance be guessed?” It is:

> Can a deliberately conservative search rule retain useful transient recovery while controlling false alarms across a frozen family of plausible misspecifications?

That is a sharper, falsifiable claim and a more valuable prerequisite for any real-data shadow study.

## Core assumptions being challenged

### 1. A single Gaussian covariance model is sufficient

It is not supported by the current synthetic evidence. The protocol therefore treats covariance uncertainty, scale error, heavy tails, nonstationarity, isolated outliers, and cadence changes as first-class nuisance conditions rather than optional post hoc plots.

### 2. A large maximum matched-template score is enough evidence

A maximum over many correlated templates is particularly vulnerable to one abnormal epoch or a misspecified covariance. The v2 candidates include a leave-one-observation-out stability statistic that explicitly asks whether the selected template remains supported when the most consequential observation is removed.

This stability quantity is a **search statistic**, not a calibrated z-score. Its null behavior will be measured empirically.

### 3. Robustness can be claimed from one cadence realization

The previous studies were conditional on one synthetic cadence. V2 therefore uses multiple independently generated irregular cadences plus separate seasonal-gap cadences. Results will be reported by cadence as well as in aggregate.

### 4. A threshold can be tuned until the stress plot looks good

The protocol separates development, calibration, and locked evaluation by seeds and generated data. Candidate choice occurs only in development. Threshold selection occurs only in calibration. Locked evaluation is run once for the frozen implementation and frozen threshold. Adverse holdout results remain adverse results.

### 5. Passing known stress cases implies distribution-free validity

It does not. The nuisance envelope is finite and declared. Three additional generalization probes are excluded from threshold selection to test whether the method merely overfits the named calibration family. Even success on those probes does not create a distribution-free guarantee.

## Frozen scientific question

**Primary question:** Can a frozen matched-template statistic achieve a false-alarm fraction no greater than 1% in every prespecified calibration-envelope null regime, with each 95% Wilson upper bound no greater than 1.5%, while improving macro-average 4-sigma recovery over the single-epoch baseline by at least five absolute percentage points with a paired-bootstrap lower confidence bound above zero?

A second non-inferiority condition protects against obtaining robustness only by making the method scientifically inert: under matched IID Gaussian noise, 4-sigma recovery may not fall more than ten absolute percentage points below the existing v1 raw bank.

Failure of a safety criterion blocks promotion even if recovery is excellent.

## Candidate statistics

Only three candidates may enter development.

### A. Raw bank with nuisance-envelope calibration

The search statistic is the existing maximum positive profiled matched-template statistic. The change is statistical rather than architectural: instead of calibrating against one assumed null, the final threshold is the most conservative threshold required by every calibration-envelope regime.

This candidate tests the simplest possibility: perhaps the current statistic is acceptable if its threshold acknowledges noise uncertainty.

### B. Selected-template leave-one-observation-out stability

Let `T_full` be the current maximum statistic and let the selected template be the one achieving that maximum. For each observation, delete that observation, refit the constant background on the retained covariance marginal, and recompute the selected-template statistic. Define

`T_stable = min(T_full, min_i T_selected_without_i)`.

This is intentionally conservative. A candidate whose apparent significance depends on one measurement will have a low stability statistic. The template is **not reselected** after deletion, preventing the diagnostic from quietly turning into another multiple-template search. The existing influence calculation already contains the necessary selected-template leave-one-out primitive; v2 must expose and test the statistic without changing current v1 output semantics.

### C. Huberized stability

This is the only development candidate requiring a new robust residual transformation. Standardized residuals are robustly centered, divided by `max(1, 1.4826 * MAD)`, and clipped to `[-4, 4]` before applying the template bank and the same selected-template leave-one-out minimum.

Because the transformation changes the sampling distribution, the result must not be called a Gaussian z-score or chi-square. It is an empirically calibrated ranking/search statistic.

No additional clipping constants, robust estimators, covariance grids, neural models, or template families may be added after development starts without a versioned amendment.

## Candidate-selection rule

Development data are used only to choose among the three frozen candidates.

1. Construct the provisional threshold for each candidate from development nulls using the same worst-regime principle planned for calibration.
2. Mark a candidate infeasible if any development calibration-envelope regime has false-alarm fraction above 2%.
3. Among feasible candidates, choose the one with the largest macro-average 4-sigma recovery across frozen signal families and signal-noise regimes.
4. If two candidates differ by less than one absolute percentage point in that recovery metric, select the simpler candidate in this order: raw bank, leave-one-out stability, Huberized stability.
5. Freeze the selected implementation, source digest, template contract, and statistic name before calibration begins.

Development results remain publishable as development results but cannot be combined with locked evaluation counts.

## Calibration rule

For the frozen statistic, generate an independent calibration set for each prespecified null regime. Within each regime, estimate its 99.5th percentile statistic. The **single locked threshold** is the maximum of these regime-specific thresholds.

The 0.5% calibration tail is deliberately more conservative than the 1% evaluation target, leaving margin for Monte Carlo uncertainty and between-regime variation.

The threshold cannot be changed after any locked-evaluation statistic is observed.

## Prespecified calibration-envelope null regimes

The envelope contains:

- IID Gaussian noise;
- AR(1) rho 0.3, 0.5, and 0.7;
- OU-like covariance with 80% correlated variance at 1-, 6-, and 20-day timescales;
- measurement errors underestimated by a factor of 1.5;
- Student-t noise with 3 degrees of freedom, scaled to unit variance;
- variance doubling in the second half of the curve;
- one positive 6-sigma outlier;
- one positive 8-sigma outlier;
- two positive 5-sigma outliers; and
- a seasonal-gap cadence under matched Gaussian noise.

These are not asserted to span real astronomical systematics. They are a deliberately adverse synthetic family motivated by the failures already observed.

## Locked generalization probes

The following are generated only after the statistic and threshold are frozen and are not used in candidate or threshold selection:

- AR(1) rho 0.85;
- 1% contaminated Gaussian noise with a sigma-8 contamination component; and
- a linear variance drift from 0.75x to 1.75x nominal scale.

Results on these probes are secondary. Severe failure must be reported and should narrow any robustness language even if the primary envelope passes.

## Signal study

The signal bank retains the four phenomenological families already used by the repository: Gaussian, exponential, Bazin, and fallback-shaped profiles. These remain templates, not physical-class probabilities.

Signal amplitudes are 2, 4, and 8 sigma with widths 1, 3, and 10 days. Signal evaluations are repeated under IID Gaussian, AR(1) rho 0.7, Student-t3, and 1.5x error-underestimation conditions. Each method receives the identical simulated cadence, noise, signal family, signal parameters, and signal realization so method differences are paired rather than confounded by different random samples.

The 4-sigma macro-average is primary for utility. The 2-sigma and 8-sigma rows are secondary sensitivity curves.

## Cadence design

Use 20 independently seeded irregular 64-epoch cadences over 60 days and 5 additional seasonal-gap cadences. The exact times and seeds must be written before any method is evaluated on them and included in the artifact bundle.

The primary false-alarm table reports exact numerator/denominator and Wilson intervals by null regime. A second table reports the distribution across cadence realizations so a pooled count cannot hide one cadence family with pathological behavior.

Recovery differences use a paired bootstrap over cadence realizations, preserving the same simulated examples across compared methods.

## Comparators

Every locked result table includes:

1. the maximum positive single-epoch standardized residual after profiling the constant baseline;
2. the current v1 IID-calibrated raw bank; and
3. the current covariance-aware bank when the true simulated covariance is supplied as an **oracle reference**.

The oracle comparator is not an operational baseline. Its purpose is to separate “matched filtering can work when the noise model is known” from “the deployed method can know the correct noise model.”

## Primary acceptance gates

### Safety gate

For **every** calibration-envelope null regime:

- locked false-alarm point estimate `<= 0.01`; and
- two-sided 95% Wilson upper bound `<= 0.015`.

If one regime fails, the statistic does not pass synthetic robustness qualification.

### Utility gate

Across the frozen 4-sigma signal evaluation:

- macro-average paired recovery improvement over the single-epoch comparator `>= 0.05` absolute; and
- the 95% paired-bootstrap lower bound for that improvement is `> 0`.

### Matched-noise non-inferiority gate

Under IID Gaussian noise, 4-sigma recovery cannot be more than 0.10 absolute below the current v1 raw bank.

### Interpretation of failure

A failed gate is not permission to retune on locked data. It produces a negative robustness result. Any later redesign becomes v3, with a written amendment stating exactly which v2 results were already known.

## Reproducibility requirements

Before locked evaluation, archive:

- this Markdown document;
- `robust_search_protocol.v2.json`;
- protocol digest;
- exact selected implementation source and digest;
- Python, NumPy, and relevant dependency versions;
- cadence arrays and generation seeds;
- template-bank identity/digest;
- development summary;
- calibration trial statistics and selected threshold; and
- a machine-readable statement of the claim boundary.

After evaluation, additionally archive:

- per-trial locked null statistics;
- per-trial paired signal outcomes;
- exact counts and intervals for every regime;
- cadence-level summaries;
- generalization-probe results;
- runtime and memory summary; and
- a result digest binding all of the above.

No failed stress case may be deleted from the final artifact set.

## Implementation checklist

### P0 — freeze and integrity

- [x] Freeze the v2 machine-readable protocol before any v2 development run.
- [x] Record the already observed v1 failures as prior evidence rather than holdout evidence.
- [ ] Add a protocol-digest verification test so an experiment runner refuses a modified protocol unless its expected digest is deliberately updated.
- [ ] Generate and commit the exact 20 irregular and 5 seasonal-gap cadence definitions before development evaluation.

### P1 — statistic implementation

- [ ] Add a public, explicitly named stability-statistic helper that uses the existing selected-template leave-one-out primitive without changing v1 `fit()` semantics.
- [ ] Add unit tests showing a one-epoch injected outlier collapses the stability statistic while a multi-epoch supported signal can remain nonzero.
- [ ] Implement Huberized stability only behind the research namespace, with tests for zero MAD, missing/non-finite inputs, extreme values, deterministic behavior, and scale equivariance where applicable.
- [ ] Ensure robust statistics are never labelled `z`, `sigma`, `chi_square`, or probability in machine-readable outputs.

### P2 — experiment runner

- [ ] Build a v2 runner that has explicit `development`, `calibration`, and `locked_evaluation` modes and refuses to use the same seed namespace for more than one phase.
- [ ] Materialize exact source snapshots alongside results, as the current experiments already do.
- [ ] Enforce the candidate-selection rule mechanically rather than by manual spreadsheet choice.
- [ ] Enforce the max-over-regime calibration threshold mechanically.
- [ ] Emit per-trial statistics so aggregate counts can be independently recomputed.

### P3 — locked statistical run

- [ ] Execute development once and freeze the selected candidate plus source digest.
- [ ] Execute independent calibration once and freeze the threshold.
- [ ] Execute the locked null envelope once.
- [ ] Execute the locked paired signal evaluation once.
- [ ] Execute the three generalization probes only after all preceding artifacts are frozen.
- [ ] Produce Wilson intervals, paired cadence bootstrap intervals, and exact counts from source trial records.

### P4 — manuscript integration

- [ ] Add one compact robustness table containing every primary null regime; do not cherry-pick only the matching covariance row.
- [ ] Add a recovery-vs-robustness figure using locked signal results.
- [ ] State explicitly that the nuisance envelope is finite and synthetic.
- [ ] Preserve the prior catastrophic misspecification results as motivation, not as results that were “fixed away.”
- [ ] If v2 fails, write the negative result directly into the manuscript and keep the search shadow-only.

### P5 — real-data evidence after synthetic qualification

Regardless of whether v2 passes, conference-grade scientific claims still require a frozen, object-grouped, time-forward real cohort containing the complete eligible denominator and mature outcomes. That cohort must retain point-in-time broker state, source identity/aliases, image-review evidence, catalogue-response provenance, policy version, review allocation route, reviewer time, and matured outcome.

The real-data comparison should then evaluate the SIDEREA heuristic, logistic baseline, JEPA-derived score, and any qualified robust transient statistic under the **same arrivals and the same fixed review budget**, with experimental scores hidden during the first prospective phase. Random-audit slots are required to estimate what the control ranking misses.

Synthetic robustness is therefore a prerequisite to a stronger shadow experiment, not the endpoint of the research program.

## Conference-readiness decision rule

The software/methods paper is already strongest when it states exactly what evidence exists. For a stronger empirical conference submission, the next defensible progression is:

1. complete v2 synthetic robustness qualification without retuning on locked results;
2. publish a full failure table even if v2 does not pass;
3. freeze the real cohort protocol and capture the complete denominator prospectively;
4. compare methods under a shared finite review budget with object-grouped, time-forward outcomes; and
5. keep all model outputs shadow-only until the prospective evidence supports ranking assistance.

A clean negative v2 result plus a rigorous prospective cohort can be scientifically stronger than a superficially impressive detector whose nominal p-values fail under ordinary misspecification.
