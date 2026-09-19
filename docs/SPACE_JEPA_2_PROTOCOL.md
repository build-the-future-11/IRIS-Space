# Space JEPA 2 protocol

Status: prospective and frozen before outcome inspection  
Machine contract: `configs/space-jepa-2-protocol.json`

## System under test

Space JEPA 2 is the SIDEREA transient detection pipeline upgraded with the APENic
Quaternion Predictive-Memory JEPA engine. The system retains calibration, identity,
catalogue, evidence, review and reporting gates. Model output is shadow evidence and
never authorizes a TNS report.

## Primary question

Does AQPM-JEPA improve useful transient retrieval at a fixed review budget, or reduce
review workload without exceeding the frozen recall non-inferiority margin, on an
object-grouped chronological cohort and a separately declared shifted population?

## Frozen design

- Horizons: 1, 3, 7 and 14 observer-frame days.
- Seeds: 17, 29, 43, 71 and 101.
- Split unit: canonical physical entity with every known alias.
- Population A: earliest 60% train, next 20% validation, latest 20% test.
- Population B: defined from metadata before outcome inspection and excluded from
  training and model selection.
- Primary review budget: 1% of test entities, bounded to 25 through 200.
- Secondary budgets: 25, 50, 100 and 200 where the cohort permits.
- Uncertainty: 10,000 paired bootstrap resamples at 95% confidence, seed 1701.

The machine contract also freezes the professor-guided stress design: source
population change is the primary OOD test; a finite-duration forcing period is
followed by evaluation of autonomous evolution in both zero-shot and limited-example
settings; and every astronomy result is sliced by actual filter, cadence and depth.

## Required comparisons

The grid includes incumbent heuristic and template scores; persistence, linear and
quadratic extrapolation; matched GRU and causal Transformer; real predictive JEPA;
quaternion JEPA with and without continuous flow; AQPM-JEPA with and without memory
and physics; and same-bank kernel residual retrieval.

## Promotion rules

Quaternion, flow, physics and memory claims are decided independently. A component
must improve its frozen primary validation endpoint by at least 2%, with the paired
95% interval excluding zero, and may worsen calibration by no more than 0.01.
APENic memory must also beat the same-bank kernel baseline and fail shuffled-value
and wrong-population controls.

End-to-end ranking advances only if recall at the primary budget improves by at least
0.03 absolute with its interval excluding zero, or workload falls by at least 20%
while the recall difference lower bound remains above -0.02. Rare-family macro recall
may not fall by more than 0.03.

## Evidence boundary

Development, chronological test, population-shift, injection and prospective shadow
results are kept separate. Incomplete grids do not produce aggregate conclusions.
Negative outcomes remain part of the final evidence package. Independent scientific
and operational review is required before an incumbent detector stage can be skipped.
