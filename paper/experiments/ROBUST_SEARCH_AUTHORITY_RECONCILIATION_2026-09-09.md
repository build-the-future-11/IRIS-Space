# Robust-search v2 authority reconciliation — 2026-09-09

This note is a human-readable reconciliation of the current pre-outcome authority chain. It does **not** override any machine-readable protocol or amendment. If this note and a frozen machine-readable artifact disagree, the frozen machine-readable artifact controls.

## Outcome-access status

No v2 candidate-development, calibration, locked-evaluation, generalization-probe, or compound-nuisance performance outcome is authorized by this note or reported here. Existing v1 negative/mixed robustness results remain preserved and unchanged.

## Authoritative pre-outcome chain

1. `robust_search_protocol.v2.json`
2. `robust_search_amendment.v2.0.1.json`
3. `robust_search_amendment.v2.0.2.json`
4. `robust_search_amendment.v2.0.3.json`
5. `robust_search_amendment.v2.0.4.json`
6. `robust_search_amendment.v2.0.5.json`
7. `robust_search_cadence_lock.v2.json`
8. `robust_search_cadences.v2.json`
9. `robust_search_reported_errors.v2.json`
10. `robust_trial_plan_lock.v2.json`

V2.0.4 freezes order-independent semantic RNG identity. V2.0.5 freezes the phase/role vocabulary and complete stochastic allocation, separating global width-allocation bookkeeping from local semantic-cell RNG indexing.

## Frozen trial-plan accounting

The complete stochastic design contains exactly **415,375** canonical data-generation identities and **0 duplicate canonical keys**:

- development threshold null: 14,000
- development feasibility null: 14,000
- development signal: 12,000
- calibration null: 140,000
- v1 raw-bank comparator calibration: 102,375
- locked null: 70,000
- locked signal: 48,000
- generalization probe: 15,000

The frozen sorted-key SHA-256 is:

`09228f6174e44c49154900ca8329bf8f3a89bea3adc695e0626498cf87530911`

A future performance runner must reproduce that digest and all role counts before generating the first development curve.

## Cadence materialization status

`robust_search_cadences.v2.json` is now materialized from the already-frozen input-only generator. The required canonical SHA-256 remains:

`5abfdaa328f5793e92bed7aa6dcfaade44ac1a54a1996b8c310e51112dc72451`

The materialization repair changes no seed, cadence-generation rule, trial count, statistic, threshold, endpoint, promotion gate, claim boundary, or result.

## Pre-result inferential limits

The frozen v2 design reuses the same 25 cadence geometries across development, calibration, and locked evaluation. Independent phase seeds therefore create independent stochastic trial streams, **not** an independent sample of cadence geometries. Any successful v2 result is conditional on the frozen synthetic 25-cadence panel and the prespecified nuisance envelope; it is not population-level evidence for arbitrary real survey cadences.

The frozen safety gate also contains one mathematically non-binding condition at the fixed locked sample size: with 5,000 null trials per regime, the point-FPR cap `<= 0.01` permits at most 50 false alarms, and the two-sided 95% Wilson upper endpoint at 50/5000 is approximately 0.01316, already below the frozen 0.015 Wilson cap. Both conditions must remain reported exactly as preregistered, but the Wilson condition must not be described as an additional effective rejection barrier.

## Human-index drift identified

`ROBUST_SEARCH_PREREGISTRATION.md` currently stops its authority list at v2.0.3 and still says the cadence manifest needs materialization. Those statements are now stale relative to the machine-readable authority chain above. This reconciliation note records the current state without rewriting frozen science; the human preregistration index should be updated in a later documentation-only change once the current CI repair branch is green.

## Current execution gate

Before any v2 performance statistic is generated:

1. exact-head repository CI must be green;
2. the public predevelopment verifier must pass on that same exact head;
3. the complete 415,375-key trial plan and frozen digest must reproduce;
4. the future runner must consume only authorized semantic trial identities and must fail closed on phase skipping, duplicate keys, or authority drift.

## Strongest defensible extension after v2

The highest-value scientific extension is a **separately preregistered external-cadence validation study**, not another in-v2 candidate. It should use cadence geometries independent of the frozen 25-cadence panel, define the target cadence population and sampling frame before outcomes are inspected, carry the v2-selected method forward without hidden retuning, and report v2 synthetic qualification and external-cadence validation as distinct evidence layers.

This note changes no scientific parameter, candidate, threshold, seed, cadence, trial identity, trial count, promotion criterion, frozen negative result, or outcome-access rule.