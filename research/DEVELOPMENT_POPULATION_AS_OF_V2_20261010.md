# Development population preparation with global as-of boundaries

Parent: `5b4b6ec4ab5bc90e0e74e0f14941c7415c17fc04`, draft #45.
This contract is recorded before implementation or new generated outcomes.

## Missing property and falsifier

The existing producer keeps physical entities separate and orders their first
availability. An early entity can nevertheless contribute training targets or a
passband vocabulary entry that became available after a validation forecast.
The retained v1 manifest explicitly does not establish global chronology.

Add an opt-in, separately identified preparation policy with two finite,
caller-declared MJD boundaries: `fit_available_through_mjd = F` and
`selection_available_through_mjd = S`, with `F < S`. Do not infer these boundaries
from outcomes. The preparation schema is v2 only when both are supplied; omitted
boundaries preserve v1 tensor behavior and policy.

The falsifier is any admitted training measurement or vocabulary source available
after F, any admitted validation forecast at or before F, any admitted validation
target available after S, or any final test/B forecast at or before S. Altering
post-F training-only channels or values must not alter admitted training tensors
or vocabulary. Changing B must not affect A membership or tensors.

## Exact algorithm

Resolve the unchanged explicit physical aliases and A/B membership, then retain
the unchanged entity-enrollment split. Fit the training vocabulary on A training
entity observations whose availability is at or before F. Construct full candidate
prequential examples from the supplied observations using the existing generator;
do not clip a target sequence to make it pass admission.

Admit only complete multi-horizon groups satisfying all applicable conditions:

- Train: the entire declared forecast horizon ends at or before F, and every
  supplied target in every horizon is available at or before F.
- Validation: forecast cutoff is strictly after F, the entire declared forecast
  horizon ends at or before S, and every supplied target is available at or before S.
- Test and population B: forecast cutoff is strictly after S.

Existing prefix construction already requires observation and availability at or
before each forecast cutoff. Retain all excluded complete-group identities,
cutoffs, horizon ends, latest target availability and every failed admission rule.
Keep incomplete groups separately counted. A partition with no admitted rows
fails, retaining input snapshots and its admission receipt. The old API is not
silently reinterpreted and no frozen runner invokes the new policy.

The complete manifest binds the declared policy, all admission receipts and source
identities. Its chronology claims concern these prepared data only: no model was
fit or selected, and actual operational model availability is not attested. Input
metadata and measurement completeness remain caller declarations. This does not
establish a protected split, an exhaustive catalogue, or scientific efficacy.

## Bounded verification and execution boundary

Fresh session `population-as-of-v2-20261010`: at most six local focused pytest
commands, 180 command seconds total; one CPU thread; generated fixtures with at
most 80 observations; no optimizer steps, scientific campaigns, downloaded data,
paid compute, or protected outcomes. At most one additional independent focused
review run. Retain test failures and final source-bound receipts. Stop once the
counterexample, exact-boundary, late-availability, incomplete-horizon, isolation,
failure-retention and unchanged-v1 compatibility cases pass.

Prior v1 records, its completed budget, frozen seeds 1000–1029, prospective protocol
files and historical negative/mixed/invalid outcomes remain unchanged. This is a
new development data policy and must be named in any future scientific freeze.

## Usage and observed verification

Both boundary options are required together. For a separately declared development
input with fit freeze at MJD 60000 and selection freeze at MJD 60100:

```bash
PYTHONPATH=src python -m siderea.ml.space_jepa_population_v1 \
  --photometry input.csv --membership membership.json --output prepared-as-of \
  --horizons-days 1 3 7 14 \
  --fit-available-through-mjd 60000 --selection-available-through-mjd 60100
```

These dates are an example, not a recommended scientific protocol. Declare the
actual boundaries from the intended operational study before outcome inspection.
The CLI preserves each input snapshot, four tensor files, rows, four admission
receipts and the v2 manifest. A boundary that leaves a partition empty fails; it is
not relaxed automatically. Omitting both options retains v1 tensor behavior and
policy. New source hashes mean full manifests need not be byte-identical to v1
outputs from an earlier source revision.

The first focused run produced **62 passes and one failure**: the new empty-output
message had unnecessarily changed the legacy v1 error text. Restoring that exact
v1 message fixed the compatibility regression. Its raw output and exact source
identities are retained in `research/verification/population_as_of_v2_20261010/`.
The corrected gate passes **63 tests: 17 new and 46 existing**, with warnings treated
as errors. It consumed 6.665 command seconds; the two total commands consumed
12.968 seconds. Ruff and scoped Mypy pass. No additional tests were run after the
successful gate.

Root independently reviewed the implementation and regressions without running
additional tests. The review checked strict forecast boundaries, inclusive label
boundaries, context maturity, vocabulary exclusion, full-group rejection and
retained failures; no scoped blocker was found. This is source review, not
astronomy or operational model validation. The final source hash and commands
are bound in `receipt.json`. No new model-fit, efficacy or protected result exists.
