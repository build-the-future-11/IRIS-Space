# Prospective Study Intake

`examples/prospective_study_protocol.DRAFT.json` is a machine-valid draft, not a
preregistration and not evidence that a study has begun. Its `DRAFT`/`REPLACE` values,
zero digests, dates, effect size, budget, and thresholds require accountable owner and
independent statistical approval before freezing.

## Required owner decisions

1. Name the physical target population and acquisition windows.
2. Choose one primary scientific endpoint, reference score, comparison score, review
   budget, useful effect, uncertainty unit, and stopping rule.
3. Supply the clean release version and exact configuration digest.
4. Name the protocol owner, independent statistician, outcome adjudicators, and trusted
   identity keys.
5. Confirm the outcome taxonomy, maturity delay, censoring/missingness policy, alias
   grouping rule, and whether repeated decisions on one object are in the estimand.
6. Approve data retention, privacy, broker/catalog terms, image permissions, and public
   release fields.

## Required immutable inputs

- Complete broker response bytes or permitted content-addressed references, including
  failed/partial acquisitions and query parameters.
- Observation schema/version, UTC acquisition time, observation time standard, survey,
  passband, calibration/zeropoint, detection/upper-limit semantics, uncertainty, and
  quality state.
- Physical-entity alias map frozen before train/test assignment.
- Full eligible denominator with selected, rejected, audit-sampled, unreviewed, and
  unresolved records.
- Independent outcome evidence with candidate version, evidence time, adjudicator,
  label policy, and digest.
- Locked score-producing artifacts with training cutoff, input columns, preprocessing,
  calibration, code/config/data identities, and random seeds.

## Freeze and verification

After replacing every draft value and obtaining approvals:

```bash
siderea study-freeze prospective-study.json frozen-study.json
```

The freeze must precede `cohort.opens_at`. Preserve the command log and hash both files.
Use `bootstrap_unit=time_block` for the primary paired operational interval unless the
independent statistician records a different estimand and justified unit. Never treat an
unreviewed, unresolved, stale, or missing outcome as a negative unless the frozen policy
explicitly says so and the resulting estimand is stated.

The study is complete only when cohort totals reconcile, model/data cutoffs pass an
independent leakage audit, all prespecified methods are evaluated on the same entities,
adverse/null results are included, and the clean-tree release verifier passes on the exact
paper artifact.
