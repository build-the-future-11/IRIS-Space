# Space JEPA 2 preparation v2

This is a development preprocessing repair. Existing prepared data, frozen
protocols, candidate claims and scientific results are preserved. Version 2
must be evaluated as a new development preprocessing version before any
confirmatory protocol can adopt it.

## Corrected behavior

- Fit the passband vocabulary from training entities only, reserving `unknown`
  at index zero in advance. A validation/test-only passband maps to that bucket;
  it cannot change the vocabulary size or the training token coordinates.
- Generate one prequential example per physical entity, cutoff time and horizon.
  Simultaneous multiband rows share a cutoff rather than duplicating its examples.
- Reserve at least one entity for each partition when rounding valid positive
  train/validation/test fractions. The manifest retains the requested fractions
  and actual entity assignments.
- Hash the exact byte snapshot parsed to build tensors. A pathname changed during
  preprocessing cannot make the manifest identify unrelated bytes.
- Reject tokens outside the finite float32 range before tensor conversion.

The tensor manifest schema is `siderea.space_jepa_v2_tensor_batches.v2`.
The seven token fields and the existing scalar band-coordinate representation
are retained. The vocabulary policy changes its coordinates relative to v1,
so v1 checkpoints and newly prepared v2 tensors must not be silently paired.

## Scope of disjointness

Partitions are disjoint by supplied physical entity identity and ordered by first
availability time. This does not certify raw-source independence or impose a
global observation cutoff on every training entity. Authentic source provenance,
population-shift evaluation and complete scientific protocol review remain
separate requirements.

## Reproduce the development checks

```bash
python -m pytest -q tests/test_prequential.py tests/test_space_jepa_v2_data.py tests/test_space_jepa_v2_preparation_integrity.py
```

The tensor checks require the optional PyTorch dependency. Fixtures contain
constructed photometry only; they establish data-path behavior, not astronomical
performance, discovery, or a candidate-yield improvement.
