# Space JEPA 2 final execution checklist and roadmap

Date: 2026-09-19  
Status: authoritative prospective execution plan  
Repository baseline: `598da16` on `main`  
System: **SIDEREA transient detection pipeline upgraded with APENic technology**  
Internal engine: **APENic Quaternion Predictive-Memory JEPA (AQPM-JEPA)**

This document is the single execution ledger for Space JEPA 2. A checkbox is marked
complete only when the named artifact exists, its digest verifies, and the stated
acceptance test passes. A command finishing is not scientific success. Failed,
negative and partial results remain in the evidence bundle.

The governing mathematical design is
[`SPACE_JEPA_2_HYPERCOMPLEX_PHYSICS_SPEC_2026-09-19.md`](SPACE_JEPA_2_HYPERCOMPLEX_PHYSICS_SPEC_2026-09-19.md).
The evidence audit and rationale are
[`SPACE_JEPA_2_AUDIT_AND_PLAN_2026-09-19.md`](SPACE_JEPA_2_AUDIT_AND_PLAN_2026-09-19.md).

## 1. Final system definition

Space JEPA 2 is the complete transient detection and discovery pipeline:

```text
survey alerts / archival photometry / TNS records
    -> immutable ingestion and data qualification
    -> calibration, non-detection handling and entity resolution
    -> causal prefix construction
    -> AQPM-JEPA base prediction route
    -> APENic residual-memory correction route
    -> token-level anomaly and physics residual routes
    -> evidence-preserving fusion with incumbent heuristic/template routes
    -> fixed-budget candidate queue
    -> catalogue, identity, provenance and human-review gates
    -> shadow outcome tracking
    -> controlled reporting preflight
```

AQPM-JEPA is an internal engine. It does not replace ingestion, calibration,
catalogue checks, evidence binding, review or reporting authorization. TNS records
may provide input photometry, registry enrichment and matured outcome labels, but a
TNS registry row is not automatically a light curve.

## 2. Definition of complete

The implementation campaign is complete only when all applicable items below hold:

- [ ] The supplied TNS data have a frozen inventory, schema classification, rejection
  ledger and content digest.
- [ ] Every physical source and alias belongs to exactly one data split.
- [ ] Every feature and label has an `available_at_mjd` and passes cutoff-leakage tests.
- [ ] The incumbent TS-JEPA, transient detector and v1 shadow-pilot artifacts replay
  unchanged.
- [ ] Quaternion algebra, causal prefixing, continuous-time prediction, physics,
  memory and evidence artifacts have unit and adversarial tests.
- [ ] The no-memory causal predictor is evaluated before APENic memory is enabled.
- [ ] All required real-valued, quaternion, memory, physics and legacy baselines run
  on the same eligible entities and cutoffs.
- [ ] Every planned model/seed/fold/horizon cell is present or carries a retained,
  reason-coded failure artifact.
- [ ] Development, chronological held-out, shifted-population and prospective shadow
  evidence are reported separately.
- [ ] Candidate ranking is evaluated at a fixed review budget with a complete
  denominator, random-audit reserve and mature outcomes.
- [ ] The final promotion report identifies which components advance, remain
  experimental or are removed.
- [ ] No automated result submits or authorizes a TNS report.

“Perfect” means complete, reproducible and honest under this contract. It does not
mean forcing the proposed model to win.

## 3. One-command execution contract

Implement one resumable top-level runner:

```text
scripts/run-space-jepa-2-campaign.py
```

Final command shape:

```bash
PYTHONPATH=src .venv/bin/python scripts/run-space-jepa-2-campaign.py \
  --protocol configs/space-jepa-2-protocol.json \
  --tns-input <TNS_INPUT_PATH> \
  --survey-input <SURVEY_PHOTOMETRY_PATH> \
  --output runs/space-jepa-2-<RUN_ID> \
  --device <cpu|mps|cuda> \
  --resume
```

The runner will:

- [ ] refuse an existing output directory unless `--resume` is supplied;
- [ ] refuse resume when protocol, data, code or dependency digests differ;
- [ ] write `status.json` before the first expensive operation;
- [ ] update status atomically after every work cell;
- [ ] create one log per phase and one receipt per work cell;
- [ ] continue independent cells after a model-specific failure;
- [ ] stop dependent work after a failed data, leakage or provenance gate;
- [ ] never convert missing cells into zero, ignore them or compute a complete-grid
  result from them;
- [ ] record peak resident memory, wall time, device and package versions;
- [ ] never print TNS credentials, tokens or raw authorization headers;
- [ ] end in exactly one state: `COMPLETED`, `COMPLETED_NEGATIVE`, `PARTIAL_FAILED`,
  `BLOCKED_INPUT`, `BLOCKED_VALIDATION` or `INTERRUPTED`.

The runner does not claim persistence merely because it started. A long run is
launched from a user-owned durable terminal or another verified persistent execution
environment. Resume is based on receipts, not process survival.

## 4. Required run-directory contract

Every campaign produces this structure:

```text
runs/space-jepa-2-<RUN_ID>/
  status.json
  run-manifest.json
  protocol/
    protocol.json
    protocol.sha256
    environment.json
    source-tree.json
  data/
    inventory.json
    accepted-photometry.parquet
    rejected-rows.parquet
    entities.parquet
    tns-records.parquet
    alias-map.parquet
    split-manifest.json
    response-curves/
  checkpoints/
  memory/
  forecasts/
  anomaly/
  benchmarks/
  shadow/
  review/
  promotion/
  logs/
  failures/
```

Every JSON artifact has a schema identifier, creation timestamp, input digests,
source digest, configuration digest and content digest. Large tabular assets are
bound through SHA-256 entries in `run-manifest.json`. Paths are relative to the run
root so that a verified bundle can be moved.

## 5. Frozen protocol values

The first protocol uses these values unless the data inventory proves a value is
undefined or impossible. Any revision occurs before outcome inspection and receives
a new protocol identity.

| Item | Frozen initial value |
|---|---|
| Observer-frame horizons | 1, 3, 7 and 14 days |
| Seeds | 17, 29, 43, 71 and 101 |
| Split unit | Canonical physical entity plus all known aliases |
| Split ordering | Earliest point-in-time availability for each entity |
| Population-A partition | Earliest 60% train, next 20% validation, latest 20% chronological test |
| Population-B partition | Metadata-defined shifted population, completely excluded from training and model selection |
| Quaternion width | 64 channels, equivalent to 256 real components |
| Encoder | 6 blocks, 8 attention heads, dropout 0.10 |
| Predictor | 3 blocks |
| Target EMA | Cosine schedule from 0.996 to 0.9999 |
| Optimizer | AdamW, learning rate `3e-4`, weight decay `1e-4` |
| Gradient clip | 1.0 |
| Primary ranking budget | `min(200, max(25, ceil(0.01 * N_test)))` |
| Secondary budgets | 25, 50, 100 and 200, where eligible |
| Clustered bootstrap | 10,000 resamples, deterministic seed 1701 |
| Confidence level | 95% |
| Numeric precision | float32 model; float64 metrics, covariance and physics checks |

Population B must be definable from source metadata without examining model errors or
target outcomes. If no scientifically defensible shifted population has enough
entities, the run records `BLOCKED_INPUT` for the shift claim and continues the
within-population development work.

## 6. Phase 0: protect and fingerprint the incumbent pipeline

### 0.1 Repository and environment

- [ ] Record `git rev-parse HEAD`, branch, remotes and `git status --porcelain=v1`.
- [ ] Record Python, PyTorch, NumPy, pandas, scikit-learn and astronomy-package
  versions.
- [ ] Record CPU, accelerator, RAM and free filesystem capacity.
- [ ] Compute the SIDEREA source-tree digest with the existing manifest machinery.
- [ ] Bind this checklist, the audit, mathematical specification and frozen protocol
  into the run manifest.
- [ ] Refuse release certification from a dirty tree; permit explicitly labelled
  development runs with the dirty diff digest retained.

### 0.2 Incumbent replay

- [ ] Replay `runs/integrated-shadow-smoke-v1` without altering it.
- [ ] Run the current TS-JEPA fixture training and embedding path.
- [ ] Run the current transient-search fixture.
- [ ] Run the current shadow assembly and queue allocation.
- [ ] Compare generated schemas and deterministic fields with archived receipts.
- [ ] Store `incumbent-replay.json` with pass/fail and all differences.

Acceptance: no existing checkpoint format, CLI meaning, schema or historical artifact
changes. Any difference blocks integration until explained and fixed.

## 7. Phase 1: TNS and survey-data inventory

### 1.1 Locate and classify inputs

- [ ] Discover the user-provided TNS assets without modifying them.
- [ ] Classify every asset as public-object table, Get Object response, photometry,
  spectra, classification record, cross-match table or unknown.
- [ ] Record path, byte size, modification time, SHA-256, row count and parse status.
- [ ] Detect compression, delimiter, encoding, nested JSON layout and schema variants.
- [ ] Record query timestamps and TNS response metadata when available.
- [ ] Produce `data/inventory.json`; unknown assets remain listed and rejected.

### 1.2 Normalize photometry

- [ ] Implement `src/siderea/ingest/tns_data.py` for offline TNS data ingestion.
- [ ] Add `src/siderea/clients/tns_object.py` only if live Get Object retrieval is
  actually needed.
- [ ] Preserve the existing `src/siderea/clients/tns.py` search behavior.
- [ ] Normalize time to MJD while retaining original value and time scale.
- [ ] Normalize coordinates to ICRS degrees while retaining original coordinates.
- [ ] Preserve `survey`, `band`, response-curve version, magnitude system, zeropoint,
  unit, calibration identity and reduction provenance.
- [ ] Convert AB magnitude to flux density only when the magnitude system is known.
- [ ] Preserve signed difference flux.
- [ ] Represent non-detections with a detection flag and limiting value; never write
  them as zero-flux detections.
- [ ] Reject non-finite measurements, nonpositive uncertainties, impossible dates,
  unsupported units and ambiguous calibration with reason codes.
- [ ] Write accepted and rejected rows separately.

### 1.3 Resolve physical entities

- [ ] Normalize TNS, survey and broker identifier namespaces.
- [ ] Build a many-alias-to-one-entity mapping.
- [ ] Use probabilistic sky matching with positional uncertainties where aliases are
  absent.
- [ ] Retain ambiguous matches as ambiguous; do not choose the nearest object by
  default.
- [ ] Prevent one physical entity or alias family from crossing splits.
- [ ] Record host associations and their probabilities separately from transient
  identities.

### 1.4 Enforce point-in-time availability

- [ ] Populate `observed_at_mjd` and `available_at_mjd` for every observation.
- [ ] Populate `classification_mjd`, `redshift_available_mjd` and catalogue query
  times for TNS metadata.
- [ ] Exclude classifications, redshifts and host facts that were unavailable at a
  scoring cutoff.
- [ ] Flag records whose historical availability cannot be reconstructed.
- [ ] Prevent outcome labels from entering tokens, memory keys, memory gates or
  normalization.

### 1.5 Data-readiness report

- [ ] Report counts of entities with at least 2, 3, 5, 10 and 20 usable epochs.
- [ ] Report detections and upper limits by band, survey, calibration and year.
- [ ] Report cadence, time-span, S/N, missingness and uncertainty distributions.
- [ ] Report classifications and redshifts available at each candidate cutoff.
- [ ] Report alias ambiguity, duplicate exposure and conflicting-calibration counts.
- [ ] Report eligible counts for each horizon and proposed split.
- [ ] Report whether blackbody/physics inference is identifiable by population.
- [ ] Emit a machine decision: `READY_FULL`, `READY_EMPIRICAL_ONLY`,
  `READY_REGISTRY_LABELS_ONLY` or `NOT_READY`.

Acceptance: no model training starts until the inventory and rejection ledger verify.

## 8. Phase 2: preregistration and split freeze

Create:

- [ ] `docs/SPACE_JEPA_2_PROTOCOL.md`;
- [ ] `configs/space-jepa-2-protocol.json`;
- [ ] `src/siderea/research/space_jepa_v2_protocol.py`;
- [ ] `tests/test_space_jepa_v2_protocol.py`.

Freeze before inspecting test outcomes:

- [ ] scientific questions and component claims;
- [ ] inclusion, exclusion and minimum-history rules;
- [ ] canonical entity and alias policy;
- [ ] train/validation/test A and shifted test B entity lists;
- [ ] prediction cutoffs and target-window construction;
- [ ] horizons, seeds, review budgets and random-audit allocation;
- [ ] primary, secondary and safety metrics;
- [ ] every baseline and ablation;
- [ ] model-selection rule and maximum development trials;
- [ ] useful-effect thresholds and non-inferiority margins;
- [ ] failure, missing-cell and multiple-comparison policy;
- [ ] bootstrap dependence unit;
- [ ] resource ceiling and numerical tolerances;
- [ ] promotion gates G0 through G6.

The validator rejects overlapping entities, unfrozen lists, missing digests, mutable
paths, missing horizons, absent baselines, undefined outcomes and unbounded tuning.

## 9. Phase 3: causal data and prequential examples

Create:

- [ ] `src/siderea/ml/prequential.py`;
- [ ] `tests/test_prequential.py`;
- [ ] `tests/fixtures/space_jepa_v2/` with detection, limit, sparse, multiband,
  duplicate, ambiguous-alias and delayed-label cases.

Implement:

- [ ] physical-time prefix/target sampling at 1, 3, 7 and 14 days;
- [ ] prefix-only robust center and scale;
- [ ] explicit cadence, elapsed time, uncertainty, band, detection and missingness
  channels;
- [ ] target-availability masks distinct from padding masks;
- [ ] causal interpolation using only prefix samples;
- [ ] long-curve sampling that retains early limits, first detection, extrema and
  recent observations;
- [ ] deterministic batching and example identifiers;
- [ ] a token-contract digest extending, rather than mutating,
  `siderea.light_curve_tokens.v3`.

Adversarial acceptance tests:

- [ ] changing any post-cutoff value leaves the prefix byte-identical;
- [ ] inserting a future classification or redshift leaves the prefix byte-identical;
- [ ] permuting input rows does not change the sorted example;
- [ ] an alias-equivalent source cannot enter another split;
- [ ] a non-detection never becomes a measured zero;
- [ ] future interpolation points are inaccessible;
- [ ] normalization contains no target-window statistics.

## 10. Phase 4: verified quaternion core

Create:

- [ ] `src/siderea/ml/quaternion.py`;
- [ ] `tests/test_quaternion.py`.

Implement:

- [ ] quaternion representation as four real components;
- [ ] conjugate, norm, inverse for nonzero inputs and Hamilton product;
- [ ] batched left and right multiplication;
- [ ] quaternion linear layer with exact real-matrix reference expansion;
- [ ] direction-preserving radial gate;
- [ ] quaternion RMS normalization;
- [ ] quaternion projections and real-logit causal attention;
- [ ] serialization and dtype/device movement;
- [ ] deterministic initialization and parameter counting.

Acceptance tests:

- [ ] multiplication table for `1`, `i`, `j`, `k`;
- [ ] noncommutativity with explicit `i*j=k` and `j*i=-k`;
- [ ] associativity within numerical tolerance;
- [ ] `q*conj(q)=norm(q)^2`;
- [ ] norm multiplicativity;
- [ ] pure-quaternion product recovers negative dot and positive cross components;
- [ ] quaternion layers equal their real-component reference;
- [ ] autograd passes double-precision gradient checks;
- [ ] padded or future tokens receive zero attention probability;
- [ ] CPU and available accelerator agree within frozen tolerance.

## 11. Phase 5: no-memory AQPM-JEPA base predictor

Create:

- [ ] `src/siderea/ml/space_jepa_v2.py`;
- [ ] `src/siderea/ml/space_jepa_v2_train.py`;
- [ ] `src/siderea/ml/space_jepa_v2_evaluate.py`;
- [ ] `tests/test_space_jepa_v2.py`;
- [ ] `tests/test_space_jepa_v2_train.py`;
- [ ] `tests/test_space_jepa_v2_evaluate.py`.

Implement in this order:

- [ ] quaternion causal encoder retaining every valid token;
- [ ] explicit causal summary token;
- [ ] multi-horizon predictor;
- [ ] EMA target encoder with no optimizer gradients;
- [ ] SmoothL1 latent objective;
- [ ] variance and covariance anti-collapse objectives;
- [ ] optional observable forecast distribution;
- [ ] hybrid continuous-time jump-flow route;
- [ ] transformer-only time-conditioned route as a required simpler comparator;
- [ ] checkpoint save/load bound to data, protocol, code and token-contract digests;
- [ ] exact resume including optimizer, scheduler, EMA, RNG and epoch state;
- [ ] row-level forecast artifact containing base predictions and uncertainty.

Training acceptance:

- [ ] repeated same-seed fixture runs reproduce the frozen tolerance;
- [ ] resume and uninterrupted training produce the same state;
- [ ] target encoder receives no gradient;
- [ ] EMA schedule reaches its recorded endpoints;
- [ ] effective rank and variance diagnostics detect constructed collapse;
- [ ] a shuffled-future dataset destroys forecasting skill;
- [ ] no-memory results are frozen before memory development begins.

## 12. Phase 6: mandatory comparison models

Run every model on identical eligible examples, horizons and cutoffs:

- [ ] incumbent SIDEREA heuristic score;
- [ ] incumbent statistical template detector;
- [ ] persistence forecast;
- [ ] linear extrapolation;
- [ ] quadratic extrapolation;
- [ ] matched GRU;
- [ ] matched real-valued causal Transformer;
- [ ] real-valued predictive JEPA;
- [ ] quaternion predictive JEPA without continuous flow;
- [ ] quaternion predictive JEPA with continuous flow;
- [ ] nearest-neighbor residual correction using the eventual memory bank.

For learned comparisons, match information, training entities, optimizer steps and
selection budget. Provide both parameter-matched and compute-matched real controls.
Record trainable parameters, floating-point operation estimate, wall time and peak
memory. No model gains access to labels or metadata unavailable to another model at
the same cutoff.

## 13. Phase 7: physics-informed route

Create:

- [ ] `src/siderea/ml/physics.py`;
- [ ] `src/siderea/data/passbands.py`;
- [ ] `tests/test_space_jepa_v2_physics.py`;
- [ ] versioned passband assets and their licenses/digests.

Implement:

- [ ] AB magnitude/flux-density conversion;
- [ ] rest/observer time and frequency transforms;
- [ ] luminosity distance interface with declared cosmology;
- [ ] Planck SED and isotropic photosphere luminosity;
- [ ] photon- and energy-counting passband integration;
- [ ] Milky Way and optional host extinction interfaces;
- [ ] expanding-photosphere/diffusion surrogate;
- [ ] distributional physical state rather than point-only parameters;
- [ ] Student-t detection likelihood;
- [ ] Student-t censored upper-limit likelihood;
- [ ] compatibility and identifiability masks;
- [ ] reason-coded `physics_not_identifiable` output;
- [ ] physics residuals retained separately from predictive surprise.

Acceptance tests:

- [ ] magnitude/flux round trip;
- [ ] frequency/wavelength Jacobian agreement;
- [ ] redshift transforms on analytic cases;
- [ ] synthetic band flux against an independent trusted implementation;
- [ ] Stefan-Boltzmann, expansion and energy residuals vanish on constructed cases;
- [ ] difference photometry excludes host flux;
- [ ] sparse one-band cases do not emit confident radius/temperature estimates;
- [ ] incompatible populations bypass physics without disabling empirical detection.

Physics advances only if it improves calibrated observable forecasts or useful
diagnostics on compatible validation entities. Plausible parameter curves alone do
not pass.

## 14. Phase 8: APENic episodic residual memory

Create:

- [ ] `src/siderea/ml/episodic_memory.py`;
- [ ] `tests/test_episodic_memory.py`.

Implement:

- [ ] detached training-only quaternion keys;
- [ ] per-horizon residual values from the frozen base predictor;
- [ ] learned positive diagonal quaternion metric;
- [ ] temperature-controlled masked retrieval;
- [ ] source, alias, cutoff, calibration and population exclusion masks;
- [ ] retrieval entropy, nearest distance and coverage diagnostics;
- [ ] context-only route gate;
- [ ] base and corrected forecast retention;
- [ ] deterministic capacity and replacement policy;
- [ ] memory digest bound into every corrected forecast.

Mandatory controls:

- [ ] memory off;
- [ ] gate fixed closed;
- [ ] gate fixed open;
- [ ] fixed uniform metric;
- [ ] shuffled residual values;
- [ ] shuffled keys;
- [ ] wrong-population bank;
- [ ] source-exclusion attack test;
- [ ] same-bank nearest-neighbor kernel regression.

Acceptance: validation and test sources never write to memory, a source cannot
retrieve itself through an alias, unavailable future entries are masked, and every
retrieved neighbor can be reconstructed from its immutable training receipt.

## 15. Phase 9: anomaly evidence and queue policy

Create:

- [ ] `src/siderea/ml/space_jepa_v2_anomaly.py`;
- [ ] `tests/test_space_jepa_v2_anomaly.py`.

Retain per token and horizon:

- [ ] base Mahalanobis predictive surprise;
- [ ] memory-corrected surprise;
- [ ] quaternion angular disagreement;
- [ ] oriented spectral disagreement;
- [ ] nearest-memory distance;
- [ ] retrieval entropy and effective neighbor count;
- [ ] base/corrected route disagreement;
- [ ] normalized physical residual;
- [ ] uncertainty, cadence, depth and availability flags.

Derive object summaries from retained rows:

- [ ] maximum;
- [ ] 95th percentile;
- [ ] time integral;
- [ ] consecutive threshold-exceedance length;
- [ ] per-band maxima;
- [ ] earliest threshold-crossing time.

Any scalar queue policy is monotone, versioned and trained only on development data.
It is labelled `review_priority`, never `discovery_probability`. Reviewers can always
inspect the component scores and temporal rows that generated it.

## 16. Phase 10: integration into the transient detection pipeline

Add CLI commands without changing existing command behavior:

- [ ] `space-jepa-2-data-audit`;
- [ ] `space-jepa-2-protocol-verify`;
- [ ] `space-jepa-2-train`;
- [ ] `space-jepa-2-infer`;
- [ ] `space-jepa-2-memory-build`;
- [ ] `space-jepa-2-benchmark`;
- [ ] `space-jepa-2-shadow-assemble`;
- [ ] `space-jepa-2-campaign-verify`.

Integration work:

- [ ] extend `src/siderea/cli.py` with explicit v2 commands;
- [ ] export stable public objects from `src/siderea/ml/__init__.py`;
- [ ] add a new v2 evidence schema in `src/siderea/research/pilot.py` or a versioned
  sibling without changing v1 replay;
- [ ] bind AQPM evidence to `candidates.json`, pipeline manifest, cutoff identity and
  TNS/survey data digests;
- [ ] add separate queue routes for base surprise, memory unsupportedness, spectral
  disagreement, physics residual, incumbent detector and random audit;
- [ ] preserve incumbent heuristic/template fields;
- [ ] route evidence through the existing fixed-budget allocator;
- [ ] keep reporting preflight and human authorization unchanged;
- [ ] reject incomplete or digest-mismatched evidence fail closed.

The integrated candidate artifact must answer: what was observed, what was predicted,
when it was predicted, why it was anomalous, which memories influenced it, which
physics assumptions applied, which legacy detectors agreed, and which evidence was
unavailable.

## 17. Phase 11: reviewer-facing evidence

Add a shadow-only panel to the existing review system showing:

- [ ] calibrated observed points and upper limits;
- [ ] prediction cutoff and unavailable future region;
- [ ] base and memory-corrected forecasts with uncertainty;
- [ ] token-level anomaly components over time;
- [ ] retrieved training analogues with identities, cutoffs and distances;
- [ ] physics fit and explicit compatibility/identifiability status;
- [ ] incumbent heuristic/template evidence;
- [ ] cadence, band, calibration and population-support warnings;
- [ ] complete provenance and digest links.

No UI state marks catalogue evidence complete, approves a report or changes a ledger
decision. Rendered values must round-trip to the underlying artifact within display
precision.

## 18. Phase 12: development benchmark grid

Create:

- [ ] `src/siderea/research/space_jepa_v2_benchmark.py`;
- [ ] `tests/test_space_jepa_v2_benchmark.py`.

The grid crosses:

- all required models and controls;
- seeds 17, 29, 43, 71 and 101;
- horizons 1, 3, 7 and 14 days;
- declared rolling-origin folds;
- population A validation strata;
- cadence, depth, band-count and class-family slices.

Forecast metrics:

- [ ] latent SmoothL1 by horizon;
- [ ] flux MAE and RMSE in physical and normalized units;
- [ ] Student-t negative log likelihood;
- [ ] CRPS when a predictive distribution is available;
- [ ] interval coverage and width at 50%, 80%, 90% and 95%;
- [ ] calibration error;
- [ ] effective latent rank and component variance;
- [ ] solver failures and runtime.

Detection metrics:

- [ ] recall and precision at the primary fixed review budget;
- [ ] recall at each secondary budget;
- [ ] average precision and ROC AUC as secondary, not operational, summaries;
- [ ] rare-family macro recall;
- [ ] time from first eligible observation to first review selection;
- [ ] alerts reviewed per recovered useful transient;
- [ ] false alerts by survey, cadence, magnitude, band and artifact family;
- [ ] random-audit estimates for candidates below threshold.

Statistics:

- [ ] paired comparisons on identical entity/cutoff rows;
- [ ] 10,000 clustered bootstrap resamples;
- [ ] confidence intervals reported with point estimates and denominators;
- [ ] multiple-comparison family declared in the protocol;
- [ ] absolute as well as relative effects;
- [ ] per-seed results retained;
- [ ] no aggregate result until completeness verification passes.

## 19. Phase 13: component promotion rules

Apply each decision independently:

### 13.1 Quaternion arithmetic

- [ ] Advance only if the quaternion model improves the frozen primary validation
  forecast endpoint by at least 2% relative to both parameter-matched and
  compute-matched real models, with the 95% clustered interval excluding zero.
- [ ] Require calibration error to worsen by no more than 0.01 absolute.
- [ ] Otherwise use the stronger real-valued encoder in the final pipeline.

### 13.2 Continuous-time flow

- [ ] Advance only if it improves the primary endpoint by at least 2% relative while
  adding no more than the frozen runtime ceiling.
- [ ] Otherwise use the transformer-only time-conditioned predictor.

### 13.3 Physics route

- [ ] Advance only on compatible sources when observable NLL or CRPS improves by at
  least 2%, calibration remains within 0.01, and posterior predictive checks pass.
- [ ] Never promote because inferred parameters merely look plausible.

### 13.4 APENic memory

- [ ] Advance only if corrected forecasts improve the primary endpoint by at least
  2% over no-memory and the same-bank kernel baseline.
- [ ] Require shuffled-value and wrong-population controls to destroy the gain.
- [ ] Require source-exclusion and cutoff-leakage attacks to pass.
- [ ] Otherwise ship the no-memory route and preserve the negative APENic result.

### 13.5 End-to-end ranking

Advance a new queue policy only if at least one prespecified condition holds:

- [ ] recall at the fixed primary budget improves by at least 0.03 absolute and the
  95% clustered interval excludes zero; or
- [ ] the review workload falls by at least 20% while the lower 95% confidence bound
  on recall difference remains above the frozen `-0.02` non-inferiority margin.

In either case:

- [ ] rare-family macro recall may not fall by more than 0.03 absolute;
- [ ] no protected source population may exhibit an unexplained catastrophic drop;
- [ ] every gain must survive chronological evaluation;
- [ ] the random-audit route remains active during shadow operation.

These are initial protocol thresholds. They may be changed only before test outcomes
are inspected, justified by a recorded power analysis, and assigned a new protocol
digest.

## 20. Phase 14: held-out and shifted-population evaluation

After development decisions are frozen:

- [ ] lock selected architecture, checkpoint-selection rule and queue policy;
- [ ] seal development artifacts;
- [ ] run chronological population-A test once;
- [ ] run population-B shift test once;
- [ ] prohibit threshold, seed, horizon or model changes after either result;
- [ ] report cadence/depth/calibration slices;
- [ ] report all failed and unsupported cases;
- [ ] record `out_of_population_support` where appropriate;
- [ ] produce a signed test-evaluation manifest.

A test failure is reported as a negative result. It is not repaired by relabelling the
test set as development data.

## 21. Phase 15: injection and adversarial studies

- [ ] Inject transients into archived backgrounds before feature extraction.
- [ ] Preserve the true injected onset, morphology, bands and amplitude.
- [ ] Measure recovery and time-to-detection across cadence, depth and host background.
- [ ] Run null injections to estimate false triggers.
- [ ] Attack missing bands, long gaps, calibration shifts, underestimated errors,
  duplicate alerts and bad upper limits.
- [ ] Attack alias collisions and near-neighbor source confusion.
- [ ] Attack memory with duplicate, mislabeled and wrong-population entries.
- [ ] Confirm synthetic recovery is reported separately from real-event retrieval.

Synthetic success can diagnose mechanisms. It cannot by itself establish real
astronomical discovery performance.

## 22. Phase 16: prospective shadow operation

- [ ] Run incumbent and AQPM routes simultaneously on the same incoming denominator.
- [ ] Store predictions before outcomes are known.
- [ ] Keep all detector paths active during the study.
- [ ] Allocate the frozen review budget and random-audit reserve.
- [ ] Track unresolved, known, artifact and scientifically useful outcomes.
- [ ] Wait for the protocol-defined maturity window before final scoring.
- [ ] Estimate the counterfactual consequence of skipping expensive incumbent stages.
- [ ] Report missed-event families, not only aggregate yield.
- [ ] Bind each reviewed decision to the evidence version shown to the reviewer.
- [ ] Do not submit TNS reports automatically.

Shadow operation passes only when the full denominator, audit sample and matured
outcomes are present. A pilot command completing is not a pass.

## 23. Phase 17: full software verification

Run targeted tests while implementing, then run the complete gate once the source is
stable:

```bash
.venv/bin/python -m ruff format --check src tests scripts
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python -m mypy src/siderea
.venv/bin/python -m pytest -q --cov=siderea --cov-report=term-missing
.venv/bin/python -m compileall -q src tests scripts
UV_CACHE_DIR=/tmp/iris-space-jepa-2-uv-cache uv build
```

Additional verification:

- [ ] install the wheel into a clean temporary environment;
- [ ] import every new public module from the installed wheel;
- [ ] run the synthetic end-to-end campaign from the installed wheel;
- [ ] inspect wheel contents for required configs, package data and type marker;
- [ ] verify no retired or duplicate package is included;
- [ ] run `scripts/verify-research-release.sh` into a new output directory;
- [ ] run the Space JEPA 2 campaign verifier against the final bundle;
- [ ] record every command, exit code and log digest.

Coverage must remain at or above the repository's 70% gate. More importantly, all
new causality, memory-exclusion, physics-unit and artifact-integrity branches require
direct tests even if total coverage already passes.

## 24. Phase 18: final scientific and operational package

Produce:

- [ ] `promotion/component-decisions.json`;
- [ ] `promotion/common-cohort-report.json`;
- [ ] `promotion/shift-report.json`;
- [ ] `promotion/shadow-report.json`;
- [ ] `promotion/failure-register.json`;
- [ ] `promotion/reproducibility-manifest.json`;
- [ ] human-readable final report with tables generated from row-level artifacts;
- [ ] model card describing intended use, exclusions and failure modes;
- [ ] data statement describing TNS/survey provenance and label timing;
- [ ] exact reproduction commands;
- [ ] final release-verification receipt;
- [ ] independent scientific sign-off or explicit `NOT_APPROVED` state.

The final report has separate conclusions for:

1. quaternion structure;
2. continuous-time flow;
3. physics supervision;
4. APENic memory;
5. anomaly scoring;
6. fixed-budget transient retrieval;
7. shifted-population behavior;
8. prospective shadow efficiency; and
9. operational readiness.

No aggregate sentence may imply that all components worked when only one passed.

## 25. File-by-file implementation map

| File | Required responsibility |
|---|---|
| `src/siderea/ingest/tns_data.py` | Offline TNS schema recognition and normalized import |
| `src/siderea/clients/tns_object.py` | Optional read-only Get Object client with caching and provenance |
| `src/siderea/data/passbands.py` | Versioned passband loading and digest validation |
| `src/siderea/ml/prequential.py` | Causal prefixes, target windows and token contract |
| `src/siderea/ml/quaternion.py` | Hamilton algebra and quaternion neural layers |
| `src/siderea/ml/space_jepa_v2.py` | AQPM encoder, target encoder, predictor and jump-flow model |
| `src/siderea/ml/physics.py` | Physical state, photometric synthesis and censored likelihood |
| `src/siderea/ml/episodic_memory.py` | APENic residual bank, metric, retrieval and gate |
| `src/siderea/ml/space_jepa_v2_train.py` | Deterministic training, resume and checkpointing |
| `src/siderea/ml/space_jepa_v2_evaluate.py` | Forecast and diagnostic evidence generation |
| `src/siderea/ml/space_jepa_v2_anomaly.py` | Token/object anomaly components and summaries |
| `src/siderea/research/space_jepa_v2_protocol.py` | Protocol parsing, validation and freeze |
| `src/siderea/research/space_jepa_v2_benchmark.py` | Fold-local training, full grid and statistics |
| `src/siderea/research/space_jepa_v2_campaign.py` | Resumable campaign orchestration and completeness |
| `src/siderea/cli.py` | New explicit v2 commands |
| `src/siderea/research/pilot.py` or v2 sibling | Evidence-preserving pipeline integration |
| `src/siderea/review/inspection.py` | Shadow-only forecast/anomaly inspection view |
| `scripts/run-space-jepa-2-campaign.py` | One-command entry point |
| `scripts/verify-space-jepa-2-campaign.py` | Independent bundle verifier |
| `configs/space-jepa-2-protocol.json` | Frozen experiment contract |
| `docs/SPACE_JEPA_2_PROTOCOL.md` | Human-readable preregistration |

Existing `src/siderea/ml/jepa.py`, its checkpoint format and existing v1 shadow
artifacts remain unchanged except for imports that are proven backward compatible.

## 26. Exact implementation sequence

Execute in this dependency order:

1. [ ] Fingerprint and replay the incumbent system.
2. [ ] Inventory and classify TNS/survey inputs.
3. [ ] Normalize data, resolve entities and prove cutoff availability.
4. [ ] Freeze protocol, splits, metrics, seeds, budgets and claims.
5. [ ] Implement causal prequential examples and leakage attacks.
6. [ ] Implement and verify quaternion algebra.
7. [ ] Implement the no-memory causal predictor.
8. [ ] Implement simple, recurrent, real-valued and quaternion baselines.
9. [ ] Freeze the no-memory development result.
10. [ ] Implement physics and identifiability gating.
11. [ ] Implement APENic residual memory and destructive controls.
12. [ ] Implement anomaly components and frozen queue policy.
13. [ ] Integrate v2 evidence into the existing transient pipeline.
14. [ ] Add reviewer-facing evidence without changing reporting authority.
15. [ ] Run the complete development grid and apply component gates.
16. [ ] Freeze the selected system.
17. [ ] Run chronological and shifted-population tests once.
18. [ ] Run injection and adversarial studies.
19. [ ] Run prospective shadow evaluation with a random-audit reserve.
20. [ ] Run complete software, package and artifact verification.
21. [ ] Produce the final component-by-component promotion report.
22. [ ] Obtain independent scientific/operational review before any production
   component skipping or reporting use.

## 27. Fail-closed rules

- [ ] Missing TNS photometry never becomes fabricated survey photometry.
- [ ] Registry discovery magnitude never becomes a light curve.
- [ ] Missing redshift never becomes zero redshift.
- [ ] Upper limits never become detections.
- [ ] Ambiguous aliases never cross splits or silently resolve.
- [ ] Future classifications never become model inputs.
- [ ] Validation/test entities never write to episodic memory.
- [ ] Failed grid cells never disappear from summaries.
- [ ] A dirty source tree never produces a clean release claim.
- [ ] A synthetic or smoke run never becomes astronomical efficacy evidence.
- [ ] A local test pass never becomes prospective shadow evidence.
- [ ] A shadow score never becomes permission to report to TNS.
- [ ] Negative results are preserved and cited in the final decision.

## 28. Final decision matrix

| Evidence reached | Allowed conclusion | Operational state |
|---|---|---|
| Software tests only | Implementation executes and contracts hold | Development only |
| Development grid passes | Component survived internal selection | Experimental |
| Chronological test passes | Component generalizes later within population A | Research candidate |
| Population-B test passes | Component survived declared source shift | Shadow candidate |
| Prospective shadow passes | Fixed-budget operational value supported | Eligible for independent review |
| Independent G6 approval | Approved components may be promoted | Controlled production change |

Anything below G6 keeps incumbent detector paths and human reporting controls active.

## 29. Campaign closeout

The campaign closes only after:

- [ ] `status.json` has a terminal state;
- [ ] every planned cell is successful or reason-coded failed;
- [ ] every listed artifact digest verifies;
- [ ] the exact source revision and dirty state are recorded;
- [ ] the final report distinguishes development, held-out, shifted and shadow
  evidence;
- [ ] rejected components are removed from the proposed production configuration;
- [ ] retained components have an explicit rollback path;
- [ ] unresolved external inputs or scientific limitations are listed without being
  converted into success claims.

The end result is either a verified Space JEPA 2 transient-detection upgrade, a
verified simpler upgrade with unsupported components removed, or a reproducible
negative result showing that the incumbent pipeline remains stronger. All three are
valid completions of this roadmap.
