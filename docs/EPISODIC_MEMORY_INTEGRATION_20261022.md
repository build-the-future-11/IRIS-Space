# Episodic memory integration, 22 October 2026

Status: DEVELOPMENT engineering integration; independent review and exact-head
hosted checks remain pending. This combines PRs #40–43 with the already merged
#44 mask/evaluation correction. Exact source identities and executed evidence
are retained in `research/ENGINEERING_MEMORY_INTEGRATION_20261022.json`.

## Combined contract

The bank stores immutable bytes and exposes a fresh read-only NumPy view on each
access. This applies to entry keys/residuals, normalized and original metric
weights, and the stacked key/residual caches. Changing a returned array's shape
or dtype cannot change the bank, its serialization, its neighbor selection or
its recorded digest. Bank entries and numerical settings are frozen as well.

This distinction repairs a concrete defect in PR #42: read-only array contents
alone did not prevent metadata mutation. Reinterpreting the exposed metric as
unsigned integers changed a constructed distance from 4 to approximately
1.84e19 while retaining its original digest. The corrected implementation keeps
PR #41's stronger fresh-view design and PR #42's vectorized kernel.

Eligibility uses both the key prefix cutoff and the complete residual's explicit
`available_at_mjd`. Both must be at or before the query cutoff. Source-group,
population and calibration exclusions apply before vectorized neighbor ranking;
ties remain ordered by entry identity. Unsupported queries keep the base
forecast. Invalid policy controls are rejected even when no neighbor is eligible.

The v2 serializer verifies the complete schema, entry count, settings and digest.
Unknown entry or bank fields are rejected. The CLI passes query identities to
the same strict validator without converting booleans, numbers or nulls to text.
Entry updates can be constructed through `MemoryEntry.from_mapping()` using an
explicitly amended `entry.to_mapping()`; private byte fields are not input data.

## Version and history

The canonical memory version is `siderea.space_jepa_v2_memory.v2`, retaining
PR #43's availability-bound digest. An independently imported exact #43 source
produced an identical payload, digest and prediction for the recorded constructed
nonuniform-metric fixture; its JSON artifact replays exactly through the
integrated parser. The alternative #42 digest namespace is preserved in its
historical source and development record rather than being silently relabeled.

The v1 compatibility description in the original #41 document describes that
historical revision. The integrated parser, including `from_artifact()`, requires
v2. Existing v1 files remain untouched: users must recover actual residual/model
availability before generating a new bank. Prefix cutoffs are not substituted
for missing availability.

The preparation manifest and checkpoint contracts remain v2 as specified by
#40. The shared encoder retains #44's corrected masking and evaluation behavior
plus #40's empty-axis/device validation and checkpoint version. The zero-input
quaternion gradient and shadow-admission corrections remain included.

## Executed engineering checks

- All 254 cases in the bounded 21-file affected suite passed on CPU, with no
  skips. This includes generated memory arrays, an independent scalar retrieval
  oracle, analytic gradient checks, preparation, masking and the existing
  one-epoch constructed train/infer/memory/route/benchmark/shadow fixture.
- The 25 added integration cases cover metadata mutation and read-only buffers,
  strict CLI identities, unknown schema fields and the legacy parser alias.
  All nine new CLI type cases failed against the original #43 CLI.
- Ruff lint and formatting passed on all 126 materialized source/test Python
  files. Local Mypy was unavailable; hosted strict typing remains a gate.
- An initial sparse-checkout fixture omission caused two CLI failures with
  240 passes. Restoring the unchanged protocol fixture resolved those failures;
  the final complete affected run passed. Earlier source/test receipts remain
  retained as historical observations.

The exact-head CPU workflow now includes all affected memory, preparation,
masking and CLI contracts. Previous green checks certify their original heads;
the combined head requires its own hosted checks and independent review.

## Scientific boundary

These checks establish implementation behavior on constructed inputs. They do
not establish training-only membership, authentic point-in-time availability,
population-shift validity, astronomy performance, discovery or promotion. The
successor remains `PROTOCOL_NOT_FROZEN`; protected outcomes and seeds 1000–1029
remain closed, and `reporting_authorized` remains false. No paid compute,
scientific campaign, protected execution or change to retained results occurs
in this integration.
