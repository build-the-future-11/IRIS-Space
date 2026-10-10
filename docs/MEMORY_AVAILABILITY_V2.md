# Residual memory availability contract v2

Status: development implementation repair, 10 October 2026.

The key prefix cutoff and the time at which a residual can be used are different
quantities. A future-target residual is not available merely because its key
prefix occurred before the query. The prior CLI accepted an entry with cutoff
10, `available_at_mjd=20`, and applied that entry at query cutoff 15: the extra
availability field was discarded. This can leak future-target information into
the correction route.

## Required entry metadata

Every new `MemoryEntry` and JSON entry must provide `available_at_mjd`, a finite
numeric MJD at or after `cutoff_mjd`. It is the earliest time **all information
needed for the stored key/residual pair is available**, including every target
measurement used to construct that residual. If the frozen encoder/predictor
was not available until later, its availability must also be included in this
maximum. For a bank correcting several horizons at once, use the latest
availability across the complete stored residual.

The caller must derive that timestamp from retained provenance. Supplying a
timestamp is not proof of its provenance, training-only membership, or proper
predictor construction. Those checks still belong to the scientific data and
model freeze.

Retrieval now requires both the prefix cutoff and residual availability to be
less than or equal to the query cutoff, in addition to the existing source-group,
population and calibration exclusions. Equality is deliberately inclusive.
Unavailable entries are removed before nearest-neighbor selection and weighting.
If no entry is eligible, the gate is zero and the base forecast is retained.

## Artifact and compatibility boundary

- Memory artifacts use `siderea.space_jepa_v2_memory.v2`. The digest binds the
  version, entries including availability, effective metric, temperature and
  neighbor count. Duplicate entry IDs are rejected.
- `EpisodicResidualMemory.to_payload()` and `.from_payload()` preserve the bank
  through JSON and verify its digest before routing. The CLI uses those same
  paths. Tampered availability, keys or residuals are rejected before output.
- Arrays are snapshotted into read-only byte-backed buffers. Mutating a caller
  array cannot change the already-digested bank, and writes cannot be re-enabled
  on entry buffers or effective metric weights.
- Dual-route artifacts use `siderea.space_jepa_v2_dual_route.v2` and record the
  memory digest and query eligibility context when memory is enabled.
- Version 1 artifacts are preserved as historical files. Loading them into the
  corrected route fails with an explicit regeneration message. Do not populate
  availability by copying the prefix cutoff; recover the actual target/model
  availability or leave that bank unsupported. Direct `MemoryEntry` construction
  also requires the new field.

## Bounded verification

Run from the repository with the `ml` extra installed:

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m pytest -q \
  tests/test_memory_availability.py tests/test_episodic_memory.py \
  tests/test_space_jepa_v2_router.py tests/test_space_jepa_v2_cli.py
```

The tests cover before/equal/after availability, an unavailable nearest neighbor,
explicit metadata, JSON round trips, tampering, duplicate identities, immutable
arrays and the real build/route CLI. The existing small train/infer/route fixture
uses generated tensors and synthetic photometry only. The versioned repair is
development evidence; it neither changes protected data nor establishes a model
gain, candidate discovery, or successor protocol freeze.
