# Space JEPA 2 benchmark: schema v2

The existing fixed-budget benchmark is now invariant to input row order when
scores tie. It rejects fractional labels before integer conversion and binds the
complete normalized cohort to the report with a digest.

## Metric contract

When the review budget cuts through a tied score group, all higher scores are
selected and the remaining slots receive the tied group's expected positive
count under uniform selection. The report therefore uses
`expected_true_positive`, which can be fractional. Precision and recall are
expectations under this declared policy; they are not a claim that a fractional
object can be reviewed.

Average precision groups equal scores at one threshold. Paired bootstrap recall
uses the same cutoff-tie rule as the point estimates. Rows are sorted by their
trimmed physical-entity ID before seeded paired resampling, so a CSV reordering
does not change its result or confidence interval.

The v2 report records the tie policy, average-precision policy, resampling order,
and a SHA-256 cohort digest over entity IDs, binary labels, and all score values.
Changing scores changes that digest even if the summary metrics stay identical.
Each paired comparison reports `observed_recall_difference` on the actual cohort
separately from `bootstrap_mean_recall_difference`, the mean across resampled
cohorts. They need not agree: the retained four-row fixture has an observed
difference of 0.25 and a bootstrap mean of about 0.3067.

## Input validation

- One nonempty, unique physical-entity ID per row, after whitespace normalization.
- Finite real binary labels checked before conversion to integers.
- Finite real ranking scores; booleans are not scores. Complex values are rejected
  before a conversion could discard their imaginary component.
- Distinct entity, label, and score columns; the label cannot be its own baseline.
- Positive integral review budget, at least 100 integral bootstrap repeats, and a
  nonnegative integer seed. Booleans are not integer options.
- A finite confidence level strictly between zero and one.

## Reproduce the engineering fixture

```bash
python -m siderea space-jepa-2-benchmark examples/space_jepa_2_tie_fixture.csv /tmp/space-jepa-2-tie-report.json \
  --entity entity_id --label label --scores incumbent candidate --review-budget 1 --bootstrap-repeats 100
python -m pytest tests/test_space_jepa_v2_benchmark.py tests/test_science_platform.py -q
```

The existing CLI requires a new output path. On the four-row synthetic fixture,
the all-tied incumbent has expected precision 0.5, expected recall 0.25, and average
precision 0.5. These are a transparent arithmetic example, not astronomy data or
evidence that a model improves discovery. The
[retained example output](evidence/space-jepa-2-tie-report-2026-10-07.json) can be
compared with a new CLI run.

## Compatibility and scientific boundary

The schema changes from `siderea.space_jepa_v2_benchmark.v1` to `.v2`; consumers
must replace `true_positive` with `expected_true_positive` and respect the policy
fields. The ambiguous v1 `mean_recall_difference` becomes
`bootstrap_mean_recall_difference`, alongside the observed difference.
Existing v1 artifacts are preserved. Their values are not silently
reinterpreted or rewritten.

The paired percentile bootstrap is descriptive under its entity-resampling
assumption. It does not automatically correct for shared survey, night, family,
or population effects. Deployment still requires the frozen protocol's real
point-in-time photometry, independent labels, baseline/control grids, calibration,
population-shift checks, and human review. This repair authorizes no model
promotion, astronomical discovery report, or efficacy claim. See the existing
[implementation status](SPACE_JEPA_2_IMPLEMENTATION_STATUS_2026-09-19.md).
