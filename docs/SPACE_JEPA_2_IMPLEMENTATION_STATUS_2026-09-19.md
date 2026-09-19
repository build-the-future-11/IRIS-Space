# Space JEPA 2 implementation status

Date: 2026-09-19

Space JEPA 2 is implemented as a development-grade, shadow-only upgrade to the
SIDEREA transient detection pipeline. Its internal engine is the APENic
Quaternion Predictive-Memory JEPA (AQPM-JEPA). The implementation does not add a
TNS submission endpoint and cannot authorize an astronomical report.

## Implemented software

- Frozen protocol validation, canonical digests and immutable protocol copies.
- Read-only TNS registry/object acquisition plus deterministic data inventory.
- Strict photometry normalization with row-level rejection evidence.
- Point-in-time prefix construction, prefix-only normalization and chronological,
  physical-entity-disjoint train/validation/test partitions.
- Deterministic tensor preparation for the 1, 3, 7 and 14 day horizons.
- Hamilton products, conjugates, norms, inverse, real block matrices,
  quaternion linear maps, gates, RMS normalization and causal attention.
- Quaternion causal encoder, left/right jump-flow predictor, EMA target encoder,
  variance/covariance regularization and deterministic checkpointing.
- GRU, causal real Transformer and real predictive JEPA neural controls, plus
  persistence, linear and quadratic extrapolation controls.
- Training-only APENic residual memory with source, time, population and
  calibration exclusion rules, entropy-aware gating and immutable digests.
- Predictive surprise, corrected surprise, quaternion angular disagreement,
  spectral wedge, memory support and anomaly-trace diagnostics.
- AB flux conversion, Planck spectra, flat-LambdaCDM luminosity distance,
  redshifted blackbody flux, passband integration, Student-t/censored likelihood,
  diffusion derivatives and explicit physics-identifiability outcomes.
- A dual-route assembler preserving the base prediction, memory-corrected
  prediction, anomaly components and physics evidence. It emits a composite
  ranking only when the caller supplies frozen non-negative weights.
- Fixed-budget, entity-level benchmark metrics with bootstrap comparisons and a
  complete-grid verifier that retains failed cells.
- Shadow-only joining to incumbent candidate evidence and a reviewer panel.
- A resumable campaign runner that prepares data, trains every frozen seed,
  evaluates validation and test partitions, freezes checkpoints and forecasts,
  and binds source, protocol, data, code and status digests.

## Command surface

```bash
python -m siderea space-jepa-2-data-audit INPUT OUTPUT.json
python -m siderea space-jepa-2-protocol-verify configs/space-jepa-2-protocol.json
python -m siderea space-jepa-2-prepare PROTOCOL INPUT.csv PREPARED_DIR
python -m siderea space-jepa-2-train PROTOCOL TRAIN.pt VALIDATION.pt MODEL.pt --input-dim 7
python -m siderea space-jepa-2-infer MODEL.pt TEST.pt EVALUATION.json
python -m siderea space-jepa-2-memory-build ENTRIES.json MEMORY.json
python -m siderea space-jepa-2-route ROUTING_INPUT.json ROUTED.json --memory MEMORY.json
python -m siderea space-jepa-2-benchmark SCORES.csv BENCHMARK.json \
  --entity entity_id --label label --scores incumbent aqpm --review-budget 100
python -m siderea space-jepa-2-shadow-assemble CANDIDATES.json EVALUATION.json SHADOW.json
python -m siderea space-jepa-2-campaign PROTOCOL TNS_INPUT SURVEY.csv RUN_DIR
python -m siderea space-jepa-2-campaign-verify RUN_DIR
```

The campaign's `COMPLETED` state means its predictive-core work cells completed.
The status always keeps `scientific_promotion_authorized` and
`tns_reporting_authorized` false. Promotion still requires the frozen baseline,
memory-control, calibration, rare-family, population-shift and human-review grids.

## Verification receipt

- `ruff format --check src tests scripts`: passed, 157 files formatted.
- `ruff check src tests scripts`: passed.
- `mypy src/siderea`: passed, 96 source files.
- `python -m compileall -q src tests scripts`: passed.
- Full test and coverage run: 557 passed and 103 subtests passed.
- Total branch-aware coverage: 77.52%, above the configured 70% gate.
- Source distribution and wheel: built successfully; the wheel contains every
  Space JEPA 2 module.

## Efficiency pass

- Quaternion linear maps contract through the equivalent 4 by 4 real block
  representation, avoiding the broadcast
  `[batch, time, output_channel, input_channel, 4]` Hamilton-product activation.
- Causal attention reuses a non-persistent triangular mask and grows it only when
  a longer sequence or different device requires one.
- Training constructs its trainable parameter tuple once instead of rebuilding
  parameter lists for every gradient-clipping step.
- Tensor preparation precomputes horizon and entity membership sets.
- Fixed-budget bootstrap recall is evaluated in bounded vectorized chunks and no
  longer computes unused average precision inside every resample.

Local CPU checks on this machine measured a 15.74x quaternion-linear speedup for
an 8 by 32 by 32 input with 32 input/output quaternion channels, and a 2.13x
bootstrap speedup for 500 entities and 2,000 resamples. These timings demonstrate
the implementation effect only; they are not scientific efficacy evidence.

## Current evidence boundary

No repository asset is a genuine model-ready TNS time series with an explicit
point-in-time `available_at_mjd` column. Existing examples are synthetic or
previous shadow artifacts. They are suitable for execution tests and are not
evidence of discovery performance. A real campaign must therefore start with the
actual TNS registry/labels plus survey photometry that records both observation
time and availability time. Until that input is present, there is no empirical
basis for a claim that AQPM-JEPA improves transient recall, calibration, workload
or discovery yield.

Professor feedback is represented in the frozen protocol as source-population
shift testing, post-intervention evolution testing and survey-specific
filter/cadence/depth fidelity. Attribution remains limited to the recovered notes;
the broader architecture is the project's synthesis.
