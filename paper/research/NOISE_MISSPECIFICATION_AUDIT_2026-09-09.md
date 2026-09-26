# SIDEREA noise-model misspecification audit — 2026-09-09

Target base revision: `3e4451fc76809aad8bb4eb0f76defe9e2e2edabf`.

## Scope and authority

This is a derived audit of already-retained synthetic experiment artifacts. It does not rerun an experiment, change a threshold, change a seed, alter a protocol, inspect a held-out real-sky outcome, or reinterpret a preserved negative result as positive evidence. The correlated-noise and isolated-outlier failures remain failures. The covariance follow-up remains adaptive/oracle-covariance evidence rather than a preregistered primary result.

Sources:

- `paper/experiments/transient-search-final/results.json`, protocol digest `88e089a75026394445a4171d5dd8858a45892f8aa2acf10c8ee89b9bd8a48dfd`, trial-statistics SHA-256 `d2035d91699ec061c51718d02dfec22c6dbcf0ce0c77acf40c4eaac7b4a014e2`.
- `paper/experiments/covariance-search-final/results.json`, protocol digest `82eaf5f57fe5b49abc53758adb9dfe29da4837a85d45066f108efcec6035e381`, trial-statistics SHA-256 `7f4f2ede62f023b74aa51faed242dff3fb281249f3e55fe586539d57904a16ed`.

Each reported null row contains 1,000 retained trials and a Wilson interval.

## Cross-calibration matrix

The table below uses only the retained aggregate counts. "Calibration" means the covariance assumption used to construct/calibrate the template-bank statistic in the corresponding retained experiment. It is not an estimate of the true survey covariance.

| Calibration assumption | Evaluation null | Bank detections / trials | False-positive fraction | Retained 95% Wilson interval |
| --- | --- | ---: | ---: | ---: |
| independent Gaussian (`rho=0`) | independent Gaussian | 13 / 1000 | 0.013 | [0.00761, 0.02211] |
| independent Gaussian (`rho=0`) | AR(1), `rho=0.7` | 454 / 1000 | 0.454 | [0.42338, 0.48498] |
| independent Gaussian (`rho=0`) | one positive 8-sigma outlier | 710 / 1000 | 0.710 | [0.68111, 0.73728] |
| AR(1), `rho=0.7` | independent Gaussian | 417 / 1000 | 0.417 | [0.38681, 0.44782] |
| AR(1), `rho=0.7` | AR(1), `rho=0.7` | 11 / 1000 | 0.011 | [0.00615, 0.01959] |
| AR(1), `rho=0.7` | one positive 8-sigma outlier | 805 / 1000 | 0.805 | [0.77930, 0.82837] |

## Scientific conclusion

The retained evidence rules out a strong interpretation of the current template-bank threshold as a covariance-agnostic 1% false-positive controller. Under a matched Gaussian covariance model, the observed null fraction is close to the declared per-curve endpoint at the resolution of 1,000 trials. Under covariance misspecification, however, the same basic search construction can produce false-positive fractions of 41.7%–45.4%, and a single large positive outlier produces 71.0%–80.5% false positives in these retained stresses.

The important failure is therefore not simply "rho should be 0.7 instead of 0." The reciprocal cross-calibration failure shows that choosing either one fixed covariance model is insufficient. The result is consistent with a more general mathematical issue: a statistic calibrated under one null distribution need not preserve its tail probability when the covariance or contamination law changes.

This audit does **not** establish how often any of these null models occur in ZTF/ALeRCE data. It therefore does not estimate a real-survey false-positive rate. It also does not invalidate the retained matched-model synthetic power rows; it limits the domain over which their calibration can be interpreted.

## Strongest defensible next extension

The next methods experiment should test **composite-null robustness**, not add another representation model. Before running it, freeze a development-only null family that contains multiple plausible covariance and contamination regimes, a separate calibration/evaluation RNG split, and the exact per-curve endpoint. Then calibrate a candidate threshold or robustness gate without using evaluation outcomes and evaluate every frozen null member independently.

A defensible acceptance rule is qualitative until the protocol is frozen: every prespecified null regime must satisfy the declared false-positive-control criterion with uncertainty reported; power/recovery must be reported separately on prespecified signal families. If no single threshold can satisfy both robustness and useful recovery, that is a valid negative result and should trigger a change in the statistic or a pre-score contamination/covariance diagnostic rather than post hoc threshold selection.

Survey-wide repeated testing is a separate problem. Even a successful per-curve composite-null experiment would not establish family-wise or false-discovery control across many objects, repeated epochs, or repeated operator looks. That requires the independent M04 multiplicity gate.

## Required artifacts for the prospective extension

1. `composite-null-protocol.json`: frozen null family, signal family, calibration/evaluation split, endpoint, uncertainty rule, seeds, and stopping rule.
2. `composite-null-runner.source.txt` and `composite-null-transients.source.txt`: exact source snapshots used by the run.
3. `composite-null-trial_statistics.json`: all per-trial statistics, with no deletion of failed or inconvenient regimes.
4. `composite-null-results.json`: per-regime false-positive counts/intervals plus separately reported recovery/power.
5. `composite-null-calibration.json`: threshold or gate derivation from calibration data only, with hashes binding it to the protocol and source snapshots.
6. `composite-null-claim-boundary.md`: explicit statement that the experiment is synthetic/per-curve and does not imply real-sky or survey-wide error control.
7. A later, separate M04 protocol for object-population/repeated-look multiplicity once the per-curve statistic is stable.

## Submission consequence

For the current manuscript, keep the existing bounded language: synthetic evidence demonstrates matched-model behavior and exposes severe misspecification failures; it does not establish completeness, purity, a real-survey false-positive rate, or a general discovery advantage. A conference submission is stronger if this failure matrix is explicit than if the covariance follow-up is presented as though it solved robustness.
