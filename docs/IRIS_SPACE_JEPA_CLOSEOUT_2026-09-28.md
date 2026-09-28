# IRIS / Space JEPA publication boundary — 2026-09-28

Documentation-only closeout for `main@ec7a1903dcaf3c68c27f3dc8caa90f10cefa6d4f`.
This note does not authorize an experiment, scientific promotion, or TNS reporting.

## Current engineering evidence

Main CI run `36211292989` is green across quality, security, Python 3.11–3.14,
and packaging. The Python 3.13 job reports 612 passed tests, 103 passed subtests,
and 77.50% branch-aware coverage. This is engineering evidence only.

## Keep the publication scopes separate

The current SIDEREA manuscript is a bounded methods/software paper: historical
campaign accounting, evidence/reportability architecture, and synthetic detector
diagnostics. It explicitly does not establish completeness, purity, classifier
accuracy, or comparative real-sky detection performance. Learned routes remain
shadow-only.

Space JEPA 2 is a prospective study governed by
`configs/space-jepa-2-protocol.json`. Its frozen design includes horizons
1/3/7/14 days; seeds 17/29/43/71/101; entity-disjoint chronological 60/20/20
splits; a predeclared held source population; fixed review budgets; paired
bootstrap uncertainty; required baselines/ablations; and fail-closed retention
of negative/failed cells.

## Source-population provenance gap

The current prepared-data manifest binds the raw input hash, accepted/rejected
rows, entity split membership, tensor hashes, horizons, bands, and an overall
result digest. It does not bind a concrete source-population assignment.
Likewise, the protocol freezes the policy
`metadata_defined_before_outcome_inspection` but not the actual Population B
metadata rule.

Before any population-shift result is admissible, freeze a separate artifact that
binds the exact metadata fields/catalog versions, deterministic population rule,
complete entity-to-population assignment (or reproducible equivalent), alias
resolution, missing/ambiguous handling, input/cohort digest, and protocol digest.
Do not choose the held population from model outcomes.

## External guidance

Draft PR #18 implements Steven Dillmann's source-population-shift recommendation
and Umaa Rebbapragada's time-to-detection recommendation as evaluation methods.
Treat both as attributed methodological guidance, not validation of a result.
PR #18 head `7e9b532b27acdfdc1eabdc177bba13cf7653e434` had green CI, but it was built
from an old main and should be restacked and reverified before integration.

## Remaining release gates

For the bounded SIDEREA paper: resolve the P06 redistribution/license decision;
freeze one final exact SHA; rebuild manuscript/research-bundle receipts from that
SHA; restack any conference-short delta; confirm final author/venue metadata; and
preserve all claim boundaries. R07 is already merged and is no longer an open gate.

For a Space JEPA 2 empirical claim: freeze population/cohort provenance; integrate
the shift evaluator on current main; execute the complete frozen comparison grid
without test tuning; keep chronological/population-shift/injection/shadow evidence
separate; report calibration, rare-family, review-budget, detection-rate and timing
outcomes; and obtain independent scientific and operational review.

Until those empirical gates are satisfied, Space JEPA 2 remains prospective and
shadow-only.
