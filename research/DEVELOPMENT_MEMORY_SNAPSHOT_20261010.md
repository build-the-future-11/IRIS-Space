# Development record: immutable episodic residual memory

Date: 2026-10-10. Base: `7f14c66f9018db0e15d4e87d713bbe47d9479b10`.
Scope: generated-array implementation tests only; no astronomical outcome.

## Reproduced failure and implemented change

The previous frozen `MemoryEntry` dataclass held writable NumPy arrays. A caller
could change `entry.residual` or `entry.key` after the bank digest was computed;
retrieval then changed while the evidence identity stayed constant. The bank's
metric and temperature could also be reassigned. This violated its documented
immutable-query contract.

Keys, residuals and metric weights now own byte-backed snapshots whose write flag
cannot be re-enabled. The bank itself is frozen. Its digest uses the explicit
`siderea.episodic_residual_memory.v2` schema; old digests and artifacts remain
historical and are not rewritten. Cached arrays feed a vectorized weighted
quaternion-distance kernel, replacing the Python loop over candidate distances.
Nearest-neighbor ordering remains distance first and entry ID second.

Metric weights are normalized after scaling by their maximum. Two valid weights
of `1e308` previously overflowed their mean and collapsed both metric weights to
zero; they now preserve the same geometry as weights `[1, 1]`. Empty quaternion
channels, complex or boolean arrays, duplicate entry IDs and fractional neighbor
counts are rejected. Invalid forced gates fail consistently even with no eligible
neighbors. Overflowing distances/corrections fail explicitly instead of returning
NaN retrievals.

The distance is the channel mean of each squared quaternion distance times its
normalized positive weight. Neighbor logits subtract the minimum distance before
temperature scaling; their softmax weights average residuals. The existing gate
formula and source/time/population/calibration eligibility rules are preserved.

## Verification

`PYTHONPATH=src python -m pytest -q tests/test_episodic_memory.py tests/test_episodic_memory_integrity.py`

**20 tests passed**. The numerical regression compares a 31-entry vectorized bank
with an independently written scalar sum, including exact neighbor IDs and
`1e-13` numerical tolerance. Other tests attack external mutation, write-flag
re-enabling, ties across reordered inputs, extreme weights, invalid input and
the original time/source/population filters. Ruff checks and formatting pass.
The combined memory and quaternion suite passed **27 tests**. A direct read-only
probe of the main-source implementation reproduced the original defect: changing
the residual moved the correction from 0.5 to 4.5 while the digest was unchanged.
Independent source review found no blocking correctness issue.

These results establish implementation behavior on generated arrays. They do not
establish training-only provenance, availability time of a measured residual,
calibration, source-population generalization, astrophysical discovery, or a
retrieval advantage. Those require their own data and scientific protocols.

## Preserved boundaries

The October 5 successor freeze audit and its missing requirements remain intact.
The prospective Space JEPA 2 protocol, held-out data and supplied protected seed
lock remain intact. No source-population holdout was run. Existing PR #36 ranking
work and PR #40 dataset preparation work are separate. This patch changes neither
the retained paper nor its results and does not open any reporting/promotion gate.
