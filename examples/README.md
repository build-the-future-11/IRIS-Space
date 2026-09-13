# SIDEREA examples

`photometry.csv` exercises local, offline analysis:

```bash
PYTHONPATH=src python -m siderea analyze examples/photometry.csv
```

`baseline_training.csv` is a tiny synthetic CLI fixture—not scientific training
data—for exercising the chronological supervised-baseline command:

```bash
PYTHONPATH=src python -m siderea baseline-train \
  examples/baseline_training.csv /tmp/siderea-baseline-smoke \
  --label is_target --time decision_mjd --entity object_id \
  --features amplitude significance missing_fraction \
  --train-fraction 0.60 --calibration-fraction 0.20 --review-budget 2
```

The tiny calibration partition cannot support calibration, so this smoke is
expected to emit an explicitly uncalibrated model score. Its perfect toy ranking
must not be reported as scientific performance.

The two JSONL files demonstrate the TS-JEPA record contract. They are tiny API
fixtures, not a scientifically useful training population. Use
`configs/jepa-smoke.toml` for a quick CPU execution check; the larger
`configs/jepa.toml` profile is intended for separately designed experiments. Their
entity IDs are disjoint and their validation times follow the training times, so
they satisfy the default chronological split contract. Both files include explicit
physical entity IDs and prediction cutoffs for the strict pilot commands.

```bash
PYTHONPATH=src python -m siderea jepa-train --config configs/jepa-smoke.toml \
  examples/jepa_train.jsonl examples/jepa_validation.jsonl \
  /tmp/siderea-jepa-smoke --epochs 1 --batch-size 2 \
  --evaluation-masks 2 --device cpu --require-prediction-cutoffs
```

The resulting checkpoint remains a shadow-research artifact and cannot satisfy a
catalogue, human-review, or reporting gate.

`integrated_pilot_flux.csv` is the smallest three-path contract fixture. It carries
coordinates, measured flux, detection state, observation identity, and two physical
entity IDs so `pilot-prepare --require-pipeline-view` can feed the operational
heuristic pipeline, template search, and JEPA without an identity translation.

See [the combined JEPA/pipeline guide](../README_JEPA_PIPELINE.md) for the architecture
and boundaries between these separate synthetic fixtures.
