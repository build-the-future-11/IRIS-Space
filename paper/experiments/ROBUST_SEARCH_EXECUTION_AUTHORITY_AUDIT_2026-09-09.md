# SIDEREA robust-search v2 execution-authority audit — 2026-09-09

Status: **pre-outcome reproducibility audit; no scientific result generated or inspected**.

Target branch: `research/robust-search-prereg-20260908`.

## Scope

This audit challenges the remaining execution assumptions of the prospective robust-search v2 study without changing any frozen protocol value, amendment, seed, cadence, reported-error vector, trial allocation, candidate statistic, threshold rule, endpoint, promotion gate, or claim boundary.

The preserved v1 negative/mixed evidence remains unchanged. In particular, the covariance-misspecification and isolated-outlier failures remain failures. No v2 development, calibration, locked-evaluation, generalization-probe, or compound-nuisance outcome was generated or inspected while preparing this audit.

## Current authoritative chain

The machine-readable execution authority is now broader than the older human preregistration index. A future performance runner must bind, in order, at least:

1. `robust_search_protocol.v2.json` — frozen scientific question, nuisance envelope, candidates, endpoints, promotion rules, and phase seeds.
2. `robust_search_amendment.v2.0.1.json` — independent development feasibility split and effective two-candidate set.
3. `robust_search_amendment.v2.0.2.json` — exact cadence/signal allocation, weighting, comparator calibration, bootstrap mechanics, and secondary simultaneous diagnostic.
4. `robust_search_amendment.v2.0.3.json` — canonical cadence-identifier erratum only.
5. `robust_search_amendment.v2.0.4.json` — order-independent semantic per-trial RNG identity.
6. `robust_search_amendment.v2.0.5.json` — frozen phase/role vocabulary, local trial-index semantics, complete trial accounting, and plan-digest rule.
7. `robust_search_cadences.v2.json` — materialized cadence bytes, already required to reproduce the frozen cadence SHA-256.
8. `robust_search_reported_errors.v2.json` — frozen reported-error generation lock.
9. `robust_trial_plan_lock.v2.json` — complete 415,375-key semantic plan with zero duplicate keys and sorted-key SHA-256 `09228f6174e44c49154900ca8329bf8f3a89bea3adc695e0626498cf87530911`.
10. The immutable phase-receipt chain implemented by `siderea.research.robust_phase_receipts`.

Narrative Markdown is an index only and must not override these machine-readable artifacts.

## Audit finding 1 — the scientific core is no longer blocked by pseudocode

The current branch contains real implementations for protocol verification, exact cadence materialization, deterministic reported-error generation, semantic trial RNGs, complete trial-plan accounting, a research-only leave-one-observation-out candidate, and fail-closed phase receipts. The highest-value remaining work is therefore not adding another model or replacing scaffolding. It is making the eventual performance runner incapable of drifting outside the frozen execution authority.

## Audit finding 2 — syntactically canonical RNG keys are not the same as authorized trial identities

`siderea.research.robust_trial_rng.canonical_trial_key(...)` intentionally implements the v2.0.4 key format. It accepts any non-empty `phase` and `role` that satisfy the canonical JSON schema. `_validate_canonical_trial_key(...)` checks that a key is structurally complete and canonical, but it does not by itself prove that the key belongs to the v2.0.5 frozen 415,375-row plan.

That separation is reasonable at the low-level RNG module, but it creates an execution hazard if a future runner constructs semantic keys ad hoc. A typo, renamed role, omitted cell, extra cell, or otherwise structurally valid but unauthorized key could receive a perfectly deterministic PCG64 stream while still violating the frozen study.

Therefore **deterministic RNG identity is necessary but not sufficient for protocol compliance**.

## Strongest defensible execution extension — plan-derived execution only

Do not let the performance runner invent semantic trial keys.

The runner should obtain its stochastic work exclusively from the exact frozen plan produced by `siderea.research.robust_trial_plan.iter_trial_plan(protocol)`, verify the complete plan against `robust_trial_plan_lock.v2.json`, and then execute phase/role subsets of those already-authorized keys.

Recommended invariant:

> A stochastic v2 data-generation call is authorized only when its canonical key is present in the verified frozen trial plan for the requested phase/role; no ad-hoc canonical key may create a scientific outcome.

This is an execution-integrity rule, not a new scientific amendment. It changes no allocation or RNG stream; it prevents implementation drift from creating outcomes outside the already frozen allocation.

### Patch-ready design

Add an execution-layer helper rather than weakening or overloading the v2.0.4 RNG primitive:

```text
load_verified_trial_plan(protocol, trial_plan_lock) -> VerifiedTrialPlan

VerifiedTrialPlan must:
- reproduce the complete role counts and total 415,375 keys;
- reproduce the frozen sorted-key SHA-256;
- contain zero duplicates;
- expose phase/role subsets by filtering the verified frozen rows;
- refuse unknown phase/role names;
- refuse caller-supplied keys absent from the verified set;
- expose the full-plan digest and subset count in every phase receipt.
```

The performance runner should iterate those verified rows and pass each row's canonical key to `trial_rng(...)`. It should not rebuild role strings, local trial indices, width allocation, or cadence membership independently.

### Required regression tests before the first development curve

1. A structurally canonical key with role `null_threshold` must be rejected by the execution layer because the frozen role is `development_threshold_null`.
2. Removing one authorized development key must fail the expected role count and/or subset digest before data generation.
3. Adding one extra canonical key must fail before data generation.
4. Reordering the same authorized plan must preserve the frozen sorted-key digest.
5. Forward/reverse/batched execution of the same verified subset must assign identical RNG streams to every semantic key.
6. A requested phase/role combination inconsistent with v2.0.5 must fail closed.
7. The development runner must refuse to start unless the predevelopment receipt binds the exact cadence digest, reported-error digest, v2.0.4 identity, v2.0.5 plan identity, and full-plan digest.

## Audit finding 3 — current CI remains a hard gate

The exact branch head must be green before any performance runner is allowed to materialize development outcomes. A formatting failure is mechanical; a Python-test failure must be diagnosed from the first causal traceback and corrected without changing frozen scientific values simply to satisfy CI.

Until that gate is green, work should remain limited to control-plane/reproducibility repairs, authority-chain reconciliation, and tests that do not generate candidate performance.

## Audit finding 4 — the human preregistration index is stale

`ROBUST_SEARCH_PREREGISTRATION.md` still describes only amendments v2.0.1 through v2.0.3 in several places and still says the exact cadence manifest needs materialization. The machine-readable chain now contains v2.0.4/v2.0.5 and a frozen 415,375-key trial-plan lock, and the exact cadence manifest has been materialized.

Before execution, reconcile that Markdown index so a researcher following the human instructions cannot accidentally omit the semantic RNG/trial-plan authority or rematerialize an already frozen artifact. This is documentation reconciliation only; machine-readable artifacts remain authoritative.

## Scientific-validity boundaries that remain open

Even a perfectly executed v2 cannot by itself justify:

- real-sky completeness or purity;
- survey-wide FWER/FDR control;
- robustness to nuisance mechanisms outside the finite frozen envelope;
- population-level generalization to arbitrary survey cadence distributions;
- equal-realized-FPR sensitivity superiority unless locked null evidence supports it;
- a claim that the Wilson `<=1.5%` condition adds an independent rejection barrier at `n=5000` when the frozen `<=1%` point-FPR gate is already stricter;
- robustness to arbitrary combinations of nuisance mechanisms.

The separately frozen compound-nuisance extension is therefore valuable only as a secondary post-lock stress study, and its failures must constrain the manuscript rather than feed back into v2 calibration.

## Conference-readiness decision

The project is strong enough to support a serious methods/reproducibility submission even if v2 fails, provided the final paper reports the full prespecified success/failure surface, retains every adverse regime, binds code/result identity, and keeps the synthetic/conditional claim boundary explicit.

The immediate conference-readiness risk is not lack of another novel architecture. It is an execution-authority mismatch: a deterministic but unauthorized trial is still a protocol violation.

## Prioritized next gates

1. **P0 — get exact-head CI green without changing frozen science.** Diagnose formatting separately from the first causal Python-test failure.
2. **P0 — enforce plan-derived execution.** Add the execution-layer verified-plan abstraction and the seven regression tests above; generate no outcomes yet.
3. **P0 — reconcile `ROBUST_SEARCH_PREREGISTRATION.md`.** Include v2.0.4/v2.0.5, the materialized cadence artifact, the 415,375-key plan lock, and current predevelopment gate.
4. **P1 — implement development-only runner.** It may consume only the verified `development_threshold_null`, `development_feasibility_null`, and `development_signal` subsets and must freeze complete per-trial records plus a `development_complete` receipt.
5. **P1 — freeze candidate selection receipt.** No calibration data may be generated until the selected implementation/source digest is frozen and bound as `selection_frozen`.
6. **P1 — execute calibration once.** Preserve every regime, threshold tie count, selected-statistic threshold, and independently calibrated single-epoch comparator threshold.
7. **P1 — execute locked evaluation once.** No retuning. Report per-regime selected/comparator FPR side by side so the recovery delta is not misrepresented as automatically equal-FPR.
8. **P2 — run original generalization probes and the separately frozen compound-nuisance extension only after locked-evaluation receipt exists.** Failures remain failures.
9. **P2 — external-cadence validation as a separate future preregistration.** Use independent cadence geometries and keep it distinct from v2 rather than appending it post hoc.
10. **P2 — survey-wide multiplicity and real-data measurement/provenance remain separate gates** before any real-sky discovery-performance claim.

## Single best next action

Close the **plan-derived execution invariant** before implementing the development runner: make it mechanically impossible for a future outcome-producing path to use a canonical RNG key that is not one of the exact 415,375 identities already frozen by v2.0.5 and `robust_trial_plan_lock.v2.json`.
