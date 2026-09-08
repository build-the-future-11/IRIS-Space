# Shadow transient search

`siderea transient-search flux.csv search.json --null-trials 4095 --seed 20260908`

The input contains `source_id,survey,band,mjd,flux,flux_error`. Each row must be an
actual measured flux with a finite positive uncertainty in the same channel units.
Signed difference flux is supported. Magnitudes and censored limiting magnitudes
are not automatically converted into Gaussian flux. If `is_detection` is supplied,
only true rows are accepted; omit that classification for measured forced flux.
Channels with fewer than four distinct epochs are explicitly unevaluated.

The search is a diagnostic alongside the existing pipeline. It does not modify
ranking, candidate versions, catalogue gates, review requirements or reportability.
An excess is not a physical classification or a discovery probability.

## Model and statistic

Four unit-peak families are searched over declared observer-frame centers and widths:
Gaussian, asymmetric exponential (rise timescale one-third of decay), Bazin with
fall/rise ratio three, and a Gaussian rise joined to a `(1+t/width)^(-5/3)` tail.
These are phenomenological morphology templates. They are not supernova explosion
simulations, bolometric models or unique TDE identifiers. In particular, debris
fallback need not map directly to optical luminosity. Sources: Bazin et al. (2009),
[the SNLS core-collapse rate](https://www.aanda.org/articles/aa/pdf/2009/21/aa11847-09.pdf),
and Miles, Coughlin & Nixon (2020), [partial TDE fallback](https://arxiv.org/abs/2006.09375).

For measured flux y, template h, covariance C, and a constant background, whiten
both design vectors with a Cholesky factor and project the constant out of h.
The normalized projected-template inner product z estimates the amplitude's local
significance. Nonnegative amplitude constrains the likelihood improvement to
`delta_chi_square = max(0,z)^2`. The reported statistic maximizes z over the whole
bank. It must not be interpreted as a global Gaussian sigma or use a one-template
chi-square reference distribution.

Independent simulations rerun the entire search. The finite Monte Carlo p-value is
`(1 + number of null maxima >= observed maximum)/(N_null + 1)`. It is never zero.
A conservative Bonferroni correction covers channels within an object, including
unevaluated channels. It does not cover all survey objects or repeated monitoring.
Calibration trial counts must be large enough to resolve the requested threshold.

The default covariance is diagonal. `--noise-timescale-days TAU` explicitly selects
`R_ij = 0.8 exp(-abs(t_i-t_j)/TAU) + 0.2 I_ij`, with the supplied uncertainties
remaining marginal errors. The CLI does not fit TAU from the target. The Python
`TransientBank` API also accepts a full declared correlation matrix; it rejects
nonfinite, asymmetric, non-unit-diagonal, singular or poorly conditioned matrices.
Correlation must be independently justified on suitable background data.

Exact duplicate measurements are rejected because repeated rows must not be treated
as independent evidence. Object summaries report the number of evaluated channels,
the smallest resolvable corrected p-value, and an explicit status when the null
simulation count cannot resolve the requested threshold. An unevaluated source is
not evidence of absence. Correlated inputs exceeding 2,048 epochs are rejected
before allocating a quadratic covariance matrix.

## Evidence and limitations

Outputs bind the input bytes, bank design, seed, null trial count, noise assumptions
and results with SHA-256 identities. Output files cannot be overwritten. Searches
are bounded to 100 channels, 10,000 templates and 10 million design elements;
correlated designs are limited to 2,048 epochs. Default grids can miss narrow or
off-grid events. Baseline and covariance misspecification, outliers, calibration
errors, saturation, season gaps and nonstationarity can cause false positives.

The checked-in experiments preserve both improvements and failures. Gaussian-noise
calibration failed badly on correlated noise and isolated positive outliers. Known
covariance is a conditional repair, not evidence that real survey covariance is known.
No automated report should use this score without a frozen prospective evaluation.

Each fitted channel also reports an `influence` diagnostic: the local significance
remaining after omitting each observation and refitting the constant background for
the selected template. With correlated noise, deletion uses the covariance marginal
of the retained observations. The report identifies the most influential row/epoch
and records unidentifiable deletions explicitly. A large drop can expose a result
supported by one corrupted measurement. This is neither a recalibrated p-value nor
a veto: template selection is not repeated and the decision rule is unchanged.

## Reproduce the experiments

```bash
PYTHONPATH=src python paper/experiments/run_transient_search.py --output /tmp/new-iid-search
PYTHONPATH=src python paper/experiments/run_transient_search.py --protocol paper/experiments/covariance_protocol.json --output /tmp/new-correlated-search
PYTHONPATH=src python paper/experiments/run_noise_stress.py --output /tmp/new-noise-stress
```

Destinations must be new. Each result directory includes the design, per-trial
statistics/p-values, summaries, intervals, plot and source snapshots. The initial
September 8 diagnostic is preserved separately from final-source reruns and the
adaptive covariance follow-up. None is an externally preregistered clinical or
astronomical trial. Wilson intervals are marginal conditional Monte Carlo intervals,
not uncertainty over the astronomical population or over a learned covariance.

The separate noise-stress follow-up retains all seven prespecified null scenarios.
With 1,000 evaluation curves each, the matched case gave 11 false alarms, compared
with 337 for underestimated standard errors (factor 1.5), 104 for correlated
unit-variance Student-t(3) innovations, 118 for doubled late variance, 10 for a
matched seasonal gap, and 129/2 for true one-/20-day correlation timescales while
assuming six days. These are conditional synthetic counts, not survey estimates.
Recovery under the same stress scenarios remains unmeasured.
