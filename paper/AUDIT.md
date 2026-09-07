# Scientific and production audit

Audit date: 2026-09-06

## Executive assessment

The manuscript's main contribution is the explicit separation of ranking, evidence, reportability, registry status, and physical classification. The historical campaign record documents missing denominators, configuration drift, stale registry checks, and the distinction between a TNS designation and a spectroscopic type. These limitations determine the scope of the claims made in the paper.

The principal weakness was a mismatch between manuscript and repository maturity. The paper described the legacy I SPY scripts, while the repository already contained the newer IRIS architecture: canonical band-aware measurements, immutable scientific identities, evidence binding, deterministic queues, version-bound review, reporting preflight, and shadow-only learned representations. The revised paper describes the transition from I SPY to IRIS and keeps historical and current claims separate.

## What is already strong

- The claim boundary is explicit: operational selectivity is not completeness, purity, or classifier accuracy.
- Failed external queries remain unknown instead of becoming false non-matches.
- Alert, detection, object, evaluation, packet, designation, and physical class are defined separately.
- The 24-run campaign accounting is reproducible from the checked-in operations record.
- The paper exposes the July 5 policy discontinuity instead of pooling incompatible regimes.
- Representative positive, withheld, wording-veto, stale, and incomplete cases are all discussed.
- The validation plan includes temporal splitting, injection-recovery, ablation, audit sampling, censoring, calibration, cross-identification, and reviewer reliability.
- Figures are generated from source records and contain no invented sky measurements.

## What was going wrong

1. **Architecture drift:** the manuscript did not document the implemented IRIS evidence and review controls.
2. **Measurement mismatch:** the paper's pooled-passband legacy feature description could be mistaken for the current band-aware implementation.
3. **Weak uncertainty model:** pre/post fractions were reported without a dependence-aware interval.
4. **Missing software evidence:** the paper described reproducibility goals without reporting the current test, lint, dependency, or replay status.
5. **Incomplete current literature:** 2025-2026 work on anomaly routing and self-supervised light-curve representations was absent.
6. **Configuration ambiguity:** an appendix labeled legacy thresholds as current despite the checked-in IRIS policy having different radii, TTLs, review rules, and shadow-model controls.
7. **Code-quality defects:** the audit found an input-validation-order defect in the supervised baseline, an unsafe aggregation path that could hide a displaced SkyBoT client response, a misplaced significance assertion, a clock-dependent fixture, and several import/line-format violations.
8. **Evidence ceiling:** no closed row-level historical cohort, live integration run, injection-recovery result, or prospective reviewer study exists. No rewrite can manufacture those missing data.

## Improvements implemented

- Retitled the paper **IRIS: An Auditable Pipeline for Human-Supervised Optical Transient Triage** and replaced the descriptive subtitle with a conventional preprint label.
- Rewrote the abstract, introduction, implementation overview, limitations, operational discussion, and conclusion in a restrained methods-paper style.
- Added both authors' contact addresses and a conventional bold title treatment.
- Corrected the XeTeX font setup so the title, headings, emphasis, and monospaced text use actual embedded font faces instead of silent regular-weight substitutions.
- Replaced the claim-boundary infographic with a compact evidence-to-decision schematic.
- Rebuilt the IRIS architecture as coupled scientific-data, external-evidence, and human-decision planes, with interpretation left to the caption rather than embedded slogans.
- Retained explicit policy-regime bands, resampling distributions, point estimates, and intervals while removing presentation-style titles from the empirical figures.
- Rewrote the abstract, introduction, discussion, limitations, conclusion, and software statement around the historical/current distinction.
- Added a current IRIS architecture figure with an explicit non-authoritative shadow-learning route.
- Added a canonical observation tuple and band-aware feature contract.
- Added a SHA-256 candidate-version formalism separating scientific identity from execution provenance.
- Added the exact reportability predicate and a fail-closed monotonicity proposition.
- Added the deterministic finite-budget queue equation with an explicit anomaly reserve.
- Added a 50,000-draw run-cluster bootstrap. Estimated changes are:
  - early-veto fraction: -0.518, 95% interval [-0.812, -0.282];
  - shortlist fraction: +0.134, 95% interval [0.098, 0.171].
- Added a software-verification section and machine-readable audit record.
- Added paired top-K shadow evaluation, route-overlap analysis, and safety non-inferiority criteria to the prospective protocol.
- Added recent arXiv literature on AHA, Astra-CLR, AstroCo, StarEmbed, and Rubin-era automation.
- Split the appendix into final legacy thresholds and current IRIS safety defaults.
- Bound each SkyBoT epoch result before aggregation so a displaced client response cannot be replaced by the requested coordinates and clear the gate.
- Repaired all remaining static-analysis defects found during the audit.
- Made the broker-fetch path assertion compare canonical paths so the suite is stable across macOS's `/tmp` to `/private/tmp` alias.

## Verification performed

- Full suite: 212 tests and 54 subtests passed at the audit freeze with the temporary directory placed on the workspace volume.
- Targeted photometry suite after the assertion repair: 14 tests passed.
- Static analysis: clean across `src`, `tests`, and the figure generator.
- Deterministic replay: two executions of `examples/photometry.csv` produced the same scientific fingerprint (`analysis-f9b8a923ad21af66`), byte-identical normalized/features/ranking artifacts, and identical candidate versions.
- Fail-closed replay: both candidates remained blocked and zero were reportable because all mandatory external services were pending.
- Environment inventory: NumPy, pandas, scikit-learn, PyTorch, and Matplotlib were available; Astropy, astroquery, and ALeRCE were absent, so live integration was not claimed. The nearly full macOS temporary volume produced SQLite I/O errors; the unchanged suite passed when temporary files were placed on the external workspace volume.

## Remaining evidence required

The next defensible scientific extension is a frozen, object-grouped, time-forward replay cohort containing every eligible and rejected object. It must archive point-in-time broker state, raw or hashed external responses, image-review labels, policy version, review time, and matured outcomes. Only that cohort can support completeness, precision, gate ablation, learned-model comparison, and selection-function claims. Until then, IRIS should remain human supervised and all learned routes should remain shadow-only.
