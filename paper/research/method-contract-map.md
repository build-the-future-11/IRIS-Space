# Manuscript equations and executable contracts

Checked during the September 8 finishing pass. Paths are repository-relative.
This map establishes correspondence, not independent proof of scientific adequacy.

| Manuscript concept | Executable implementation | Validation / interpretation |
|---|---|---|
| Canonical scientific identity | src/siderea/provenance.py stable_json/digest_value; src/siderea/pipeline.py; src/siderea/manifest.py | tests/test_pipeline_ingest.py and ledger-version tests; execution timestamps are distinct from scientific content. |
| Version-bound review | src/siderea/ledger.py; src/siderea/reporting/preflight.py reporting_preflight | tests/test_ledger_versions.py and tests/test_review_http.py; old approvals cannot authorize newer evidence. |
| Evidence conjunction / fail-closed behavior | src/siderea/reporting/preflight.py; src/siderea/validation/binding.py | tests/test_evidence_binding.py; missing, stale or incorrectly bound data cannot establish clearance. This says nothing about catalogue completeness. |
| Finite-capacity queue | src/siderea/ranking.py build_nightly_queue | tests/test_baseline_ranking_host.py; deterministic priority/anomaly/audit allocation. Scores remain priorities, not discovery probabilities. |
| Four transient template families | src/siderea/research/transients.py transient_template | tests/test_transient_search.py; observer-frame phenomenological profiles with unit-peak normalization. |
| Covariance whitening and profiled background | TransientBank.__init__, statistics and fit | Project whitened templates orthogonal to the whitened constant; take the nonnegative bank maximum. Implemented offset subtraction improves numerical stability without changing the fitted-constant model. |
| Monte Carlo plus-one p-value | empirical_pvalue; experiment-runner searchsorted equivalent | Calibration/evaluation random streams separate; count null statistics greater than or equal to the observed statistic. Minimum attainable uncorrected p is 1/(N0+1). |
| Within-source channel correction | search_flux_table | Bonferroni includes all source channels, even unevaluated ones; records insufficient Monte Carlo resolution. No survey-wide or repeated-monitoring error guarantee. |
| Observation influence | TransientBank._influence | Selected template only, refitted background and retained covariance marginal; diagnostic, not an independently calibrated detection veto. |
| Campaign pooled ratios | paper/figures/make_figures.py make_campaign_dynamics | Ratio of sums, not mean of per-run ratios; excludes the documented duplicate pull from additive totals. |
| Campaign uncertainty | make_regime_bootstrap | Seed 20260906; 50,000 draws resampling eligible runs within each regime. Independent runs are an assumption; chronology/policy confounding prevents causal attribution. |
| Synthetic uncertainty | paper/experiments/run_transient_search.py interval | Wilson intervals conditional on the simulated design; shared noise across methods/amplitudes means rows are not independent replications. |
| Future selection function and top-K estimands | Appendix D prospective protocol | Definitions and proposed estimands, not executed population-level estimates. |

The full suite in `.test-tmp/paper-finish-check.log` passed 421 tests and 96 subtests,
78.42% coverage, after the reconstruction regression tests were added. The paper
retains its separately identified 405-test historical snapshot; no test count is
used as evidence of real-sky classification or detection performance.
