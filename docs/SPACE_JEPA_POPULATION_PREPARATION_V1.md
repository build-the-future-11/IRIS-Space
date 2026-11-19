# Development input preparation for a separate source population

Space JEPA 2's prospective protocol calls for a metadata-defined population B that
does not enter training or model selection. This opt-in producer turns that input
partition into an executable tensor path. It is separate from the existing campaign
and does not perform or authorize a protected population-shift evaluation.

## Bounded generated walkthrough

With the repository's ML dependencies installed, run from a fresh interpreter:

```bash
PYTHONPATH=src OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python scripts/demo_space_jepa_population_v1.py runs/generated-population-demo
```

Choose a new output path. The script writes exactly 64 artificial measurements for
six population-A and two population-B physical entities, including two declared
aliases per entity. It prepares all four partitions, then executes their inputs
and targets through the same tiny **untrained** model. The receipt records finite
outputs, shapes and unchanged persistent model state. It runs zero optimizer steps
and reports no accuracy comparison or astronomy efficacy estimate.

The preparation interface itself is:

```bash
PYTHONPATH=src python -m siderea.ml.space_jepa_population_v1 \
  --photometry runs/generated-population-demo/generated-inputs/photometry.csv \
  --membership runs/generated-population-demo/generated-inputs/membership.json \
  --output runs/generated-population-replay \
  --horizons-days 1 3 --fractions 0.6 0.2 0.2 --batch-size 4
```

The generated JSON/CSV are complete input examples. The exact required fields,
numerical limits and compatibility decisions are specified in
[`DEVELOPMENT_POPULATION_PREPARATION_V1_20261010.md`](../research/DEVELOPMENT_POPULATION_PREPARATION_V1_20261010.md).
This path requires CPU default device and float32 default dtype and preserves
Torch's global RNG/defaults. Use an immutable checkout and a fresh Python process;
source-file hashes do not attest arbitrary pre-cached or monkeypatched code.

## What the producer establishes

Every supplied identity resolves through an explicit physical-entity/alias map
before partitioning. A physical entity cannot belong to two populations, and every
declared physical entity must have supplied photometry. A is ordered by earliest
availability and split into nonempty training, validation and test entity cohorts;
B stays outside that ordering. The same exact survey/filter pair can receive a
training-vocabulary ID only if it occurs in A's training cohort. Unknown held-out
channels map to the reserved ID zero.

Normalization uses each example's observed and available context prefix. Target
measurements may arrive later; their availability is retained per horizon. All
observations of one physical entity, including its late observations, remain in
that entity's partition. The manifest explicitly records
`global_training_before_evaluation_established=false`: enrollment ordering alone
does not ensure every training label was available before every evaluation cutoff.

The output contains `train.pt`, `validation.pt`, `test.pt`, `population_b.pt`, exact
input snapshots, `rows.jsonl` and a final `manifest.json`. Tensor dictionaries are
consumable by the existing model functions. Each split records its physical units,
entities with and without complete multi-horizon windows, row counts, time bounds,
unknown-channel counts, tensor-content digest and file hash. Row provenance binds
the tensor example ID to the physical entity, original aliases/CSV records, cutoff,
prefix normalization and the identities/availability of every target observation.

The producer reserves a fresh directory and never overwrites it. Invalid inputs
leave a `failure.json` receipt and every finalized snapshot/partial output; a failed
attempt is not a completed dataset. A partition with no complete rows fails, while
an entity with no complete rows remains explicitly accounted for inside a nonempty
partition. Never silently remove such units from a future scientific denominator.

## Remaining scientific requirements

Metadata, common measurement units, calibrations and exhaustive aliases remain
caller declarations. Hashes preserve exactly what was supplied; they do not prove
astrophysical identity, raw-source independence, real population shift or unseen
outcomes. A real study still needs qualified source/label provenance, an as-of
training/readout rule, a pre-outcome population selection contract and the full
successor freeze. Existing protected seeds, retained results, checkpoint versions,
model controls and reporting gates are unchanged.
