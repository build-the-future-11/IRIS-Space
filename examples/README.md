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
fixtures, not a scientifically useful training population. Use a smaller JEPA
configuration for a quick smoke run; the repository profile is intended for real
experiments. Their entity IDs are disjoint and their validation times follow the
training times, so they satisfy the default chronological split contract.

```bash
PYTHONPATH=src python -m siderea jepa-train --config configs/jepa.toml \
  examples/jepa_train.jsonl examples/jepa_validation.jsonl \
  /tmp/siderea-jepa-smoke --epochs 1 --batch-size 2 \
  --evaluation-masks 2 --device cpu
```

The resulting checkpoint remains a shadow-research artifact and cannot satisfy a
catalogue, human-review, or reporting gate.
