# P04 experiment-reconstruction closure — 2026-09-09

Target revision audited: `3e4451fc76809aad8bb4eb0f76defe9e2e2edabf` (`main` at the start of this pass).

## Scope

This is an independent submission-readiness evidence audit for `FINAL_TODO.md` P04 only. It does not change a protocol, regenerate a scientific result, promote SIDEREA to real-sky validation, or reinterpret a negative/mixed result. The preserved correlated-noise and isolated-outlier failures remain failures. The covariance follow-up remains adaptive/oracle-covariance evidence. JEPA and supervised learning artifacts remain synthetic smoke tests unless a separate frozen prospective evaluation establishes otherwise.

## P04 criterion-to-artifact map

| P04 requirement | Retained evidence | Audit conclusion |
| --- | --- | --- |
| Protocols | `paper/experiments/transient-search-final/protocol.json`; `paper/experiments/noise-stress-final/protocol.json`; `paper/experiments/covariance-search-final/protocol.json` | Present. The primary transient-search protocol explicitly declares a synthetic diagnostic scope, a 1% per-curve null endpoint, `master_seed=20260908`, and states that the design record was written before the diagnostic run but was not externally preregistered. |
| Exact runner snapshot | `paper/experiments/transient-search-final/runner.source.txt`; `paper/experiments/noise-stress-final/runner.source.txt`; `paper/experiments/covariance-search-final/runner.source.txt` | Present beside the retained outputs. |
| Exact model/search implementation snapshot | `paper/experiments/transient-search-final/transients.source.txt`; `paper/experiments/noise-stress-final/transients.source.txt`; `paper/experiments/covariance-search-final/transients.source.txt` | Present. The source snapshots are retained separately from later implementation changes. |
| Dependency versions | `paper/experiments/runtime-dependencies.json` | Present as an explicit package/version inventory, including NumPy, SciPy, Matplotlib, scikit-learn, PyTorch and the installed SIDEREA package version. |
| Seeds/design parameters | The three protocol files plus their runner snapshots | Present. The primary experiment records its master seed and separate calibration/evaluation design; the retained runner source is the authority for derived RNG streams. |
| Per-trial statistics | `paper/experiments/transient-search-final/trial_statistics.json`; `paper/experiments/noise-stress-final/trial_statistics.json`; `paper/experiments/covariance-search-final/trial_statistics.json` | Present rather than only aggregate success counts. |
| Summary outputs | Each final experiment directory contains `results.json`; manuscript-facing derived material includes `paper/experiments/search_results_table.tex` and `paper/experiments/search_section.tex` | Present. Submission claims should resolve to these retained outputs, not regenerated prose. |
| Figure outputs | `paper/experiments/transient-search-final/search_diagnostic.png`; `paper/experiments/noise-stress-final/noise_stress.png`; `paper/experiments/covariance-search-final/search_diagnostic.png` | Present as retained generated artifacts. |
| Independent reconstruction check | `paper/research/experiment-reconstruction.json` | Present: `results_equal=true`, `trial_statistics_sha256_equal=true`, 30 reconstructed IID rows, retained trial-statistics SHA-256 `d2035d91699ec061c51718d02dfec22c6dbcf0ce0c77acf40c4eaac7b4a014e2`. It records both old and new source hashes and states that the later influence diagnostic did not change the preserved search statistics or counts. |
| Claim/source reconciliation | `paper/research/claim-source-ledger.md`; `paper/AUDIT.md` | Present. The ledger distinguishes local/synthetic evidence from literature context and explicitly refuses to transfer external benchmark performance to SIDEREA. |

## Gate decision

**P04 is supported for closure as a submission-packaging/reconstruction gate.** The retained bundle contains the protocol, source snapshots, environment inventory, seeds/design authority, per-trial statistics, summaries and figures, and a later reconstruction receipt showing equality of the preserved primary statistics and counts after implementation evolution.

This closure is deliberately narrower than scientific validation. It does **not** establish real-sky completeness, purity, physical classification, survey-wide false-alarm control, JEPA utility, operational broker qualification, or a prospective model advantage. Those remain governed by the open D/M/L/S validation tasks and must not be inferred from P04.

## Submission risks that remain after P04

1. `P06` remains open: the public research bundle still needs a clean release-package audit covering author/title/contact metadata, bibliography/source inclusion, release commit identity, data-availability wording, and especially license compatibility. `docs/RESEARCH_ALPHA_RELEASE.md` currently states `LicenseRef-Proprietary` and explicitly says public visibility is not an open-source redistribution grant.
2. `R07` remains open: collision/interruption behavior is not fully qualified across existing paths, unreadable input, unwritable storage and user interruption, even though current `main` adds additional collision/race hardening.
3. Real-data scientific claims remain out of scope until the applicable measurement/provenance, noise/repeated-testing, live-adapter and prospective-campaign gates are completed. In particular, no synthetic artifact in this bundle may be used as evidence of real-sky discovery yield.
4. The current `main` revision is newer than the September 8 manuscript verification receipt. Any submission that claims the paper was rebuilt from the exact final submission SHA needs a fresh manuscript/release receipt after the submission commit is frozen.

## Single next closure action

Freeze one submission-candidate SHA after this evidence-only change, then execute `P06` against that exact SHA: build a clean source/research bundle, verify bibliography/source/figure inclusion and data-availability language, and resolve the redistribution/license decision without inventing permissions. Only after that exact revision is fixed should the manuscript verification receipt be refreshed.