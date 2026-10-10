# Development population preparation v1

Contract recorded 2026-10-10 05:38:53 UTC, before implementation. Parent:
`f336ce1552d5270f3b3ad81682cd2fb0565ea0c2` (draft PR #40). This is a new,
bounded engineering session, independent of the completed Eigen geometry work.

## Question, mechanism and falsifier

The existing Space JEPA 2 protocol declares a metadata-defined population B excluded
from training and model selection, but its preparation API emits only chronological
train/validation/test partitions. Implement an **opt-in development input producer**
that canonicalizes explicitly supplied physical aliases, partitions A independently
of B, and emits a fourth `population_b` tensor file usable by the unchanged model.

The engineering hypothesis is that changing only B measurements, bands, observation
times, availability times or input order cannot alter A's memberships, vocabulary or
training tensor content. Any such alteration, cross-population physical alias,
post-cutoff context measurement, or unbound consumed input falsifies correctness.
Generated examples establish this input property, not astronomy performance.

## Complete narrow input and split contract

- Inputs are one canonical CSV and one strict JSON membership document, read,
  hashed, decoded and archived from the same immutable byte snapshots. No network,
  catalogue lookup, outcome table or inferred alias is accepted.
- Membership schema `siderea.space_jepa_population_membership.v1` requires purpose
  `development`, distinct `population_a`/`population_b` names, a nonempty descriptive
  `population_basis`, a common `measurement` declaration (`value_kind` flux or
  magnitude, and a unit), and an `entities` array. Each entity declares its exact
  `physical_entity_id`, one of the two populations and a nonempty alias array.
  Canonical IDs are also accepted aliases. Identifiers are nonempty exact strings
  without surrounding whitespace. Aliases/canonical IDs may not resolve to different
  physical entities. Duplicate declarations, unknown populations, undeclared CSV
  entities and declared-but-unobserved physical entities fail. Unobserved aliases of
  an observed physical entity are allowed. Every input row is admitted or the entire
  attempt fails; there is no silent row rejection or population inference.
- CSV columns are exactly `entity_id`, `observation_id`, `observed_at_mjd`,
  `available_at_mjd`, `survey`, `band`, `calibration_id`, `value`, `value_error`,
  `is_detection`, `limiting_value`. Detection is literal `true` or `false`.
  Missing optional measurements use an empty cell. Times/measurements must be finite,
  availability cannot predate observation, detections require a value and positive
  uncertainty, and nondetections require a finite limiting value. Every alias is
  resolved before duplicate physical-entity/observation identities are checked.
- All observations of one canonical physical entity stay in one partition. A is
  ordered by its earliest supplied availability time and canonical ID, then split
  by the existing nonempty fraction allocator. B never participates in A's ordering,
  fractions or vocabulary. Require at least three A entities and one B entity.
  This is **entity-enrollment chronology**, not a global label-availability embargo:
  an earlier enrolled entity can have observations later than another partition's
  first epoch. Such observations remain in their physical entity's partition. The
  manifest explicitly says global training-before-evaluation is not established and
  reports observation/availability bounds. A future scientific freeze must resolve
  global as-of model availability; this producer does not call the campaign runner.
- Use the parent's unique-cutoff prequential builder: context requires both observed
  and available time at or before cutoff; targets have observed time in the open-left,
  closed-right horizon. Later target availability is retained in row provenance and
  is never substituted for context eligibility. Missing full multi-horizon cutoffs
  are counted; a partition with no complete rows fails. No imputation, interpolation,
  target clipping, outcome calibration or truncation at another entity's enrollment.
- Fit the passband vocabulary only on A training entities. A channel is the canonical
  JSON pair `[survey, band]`, keeping identically named filters from different surveys
  distinct. Reserve unknown ID zero before inspecting held-out channels. Normalize
  values and errors using each row's context prefix only, with the parent's seven
  input features and numerical checks. Common value units and calibration provenance
  are caller declarations, not inferred or independently attested facts.
- Require CPU default device and float32 default dtype; do not mutate global Torch
  defaults or RNG. Horizons must be strictly increasing positive finite numbers and
  batch size a positive integer. Bound inputs to 8 MiB CSV/2 MiB JSON, 4,096 rows,
  128 physical entities, 128 observations/entity, eight horizons, batch size 64 and
  two million padded floating-point tensor values across all partitions.

## Outputs, compatibility and failure behavior

`python -m siderea.ml.space_jepa_population_v1` is a dedicated entrypoint. Existing
commands, models, training, protocols, checkpoints and memory artifacts are untouched.
The artifact schema is `siderea.space_jepa_population_preparation.v1`, distinct from
the parent's preparation v2. It emits train/validation/test/population_b `.pt` files
using the existing batch dictionary representation, exact input snapshots, per-row
prefix/target identities and availability, partition membership, tensor content
digests, file hashes, effective policy, environment and source-file identities.
Source-file identities describe the immutable checkout; use a fresh interpreter.
They do not attest malicious modifications, monkeypatches or pre-cached dependencies.

Reserve a new destination exclusively. A completed manifest is published last.
On failure retain input snapshots, finalized partial outputs and a failure receipt;
never overwrite a previous attempt. A failure receipt invalidates that attempt even
if a terminal filesystem error also left a manifest. Dataset hashes do not prove
the supplied aliases exhaustive, population metadata authentic, observations
independent, or a split unseen. Real source qualification remains unresolved.

## Finite verification budget

At most four local targeted pytest invocations, 180 seconds total wall time, plus
one independent-review invocation and one retained generated demo attempt of at
most 60 seconds. One CPU thread; zero optimizer steps, paid jobs, scientific
campaigns or protected outcomes. The retained demo is at most 64 generated CSV rows,
two horizons and one tiny untrained model, exercising all four prepared partitions.
Every attempted test/demo and repair is retained. Stop when the discriminating
invariance/admission tests, existing affected preparation checks and demo pass.

## Concurrent work and scientific boundary

PR #40 supplies corrected training-only vocabulary, unique cutoffs, tensor range
checks and checkpoint-v2 model behavior. PRs #36–39, #41–44 retain their benchmark,
cadence, memory and inference work; this branch does not duplicate or merge them.
New branch-local state indexes their histories; integration must reconcile canonical
state explicitly. Protected seeds 1000–1029, old Space-JEPA experiments, successor
freeze receipts and prior negative/invalid results are untouched. Population B here
is generated development data, not a performed protected OOD study.

## Execution and independent review

The first bounded gate retained **45 passing cases and one failing test assertion**
in 8.11 pytest seconds / 10.570 command seconds. The existing-output CLI correctly
returned error status and preserved bytes; its platform error said `File exists`,
while the new test expected `already exists`. The assertion now accepts `exists`.
No data-isolation or model-output test failed. The complete initial source snapshot,
stdout and command receipt are retained as `attempt_01*` under
`research/verification/population_preparation_v1_20261010/`.

Strict Mypy initially could not infer the tensor-writer lambda. A typed callback
now calls the same `torch.save` operation. The demo interpretation string was
shortened for the 100-character lint rule. These corrections and all final source
identities are in `attempt_02.json` and `attempt_02_sources.json`.

The second, final targeted gate passed **46 tests (29 new plus 17 existing)**,
warnings treated as errors, in 4.47 pytest seconds / 5.751 command seconds:

```bash
PYTHONPATH=<isolated-cpu-torch>:src OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  OPENBLAS_NUM_THREADS=1 python -m pytest -q -W error \
  tests/test_space_jepa_population_v1.py \
  tests/test_space_jepa_v2_preparation_integrity.py \
  tests/test_space_jepa_v2_data.py tests/test_prequential.py
```

Both runs used Python 3.12.14 / PyTorch 2.14.1+cpu / NumPy 2.3.5. New-source Ruff
lint and formatting, scoped strict Mypy and patch whitespace checks pass. No full
repository-suite result is claimed by this scoped gate. Two of four local test
commands and 16.321 of 180 command seconds are consumed. The retained generated
demo and final independent review are still pending at this entry.

### Independent review and retained demonstration

Root independently reviewed the full module, all 29 new tests, generated demo,
workflow and user guide and found no blocker. The review explicitly checked the
chronology/alias limitations and required an outer receipt identifying the actual
untrained model source, in addition to the preparation manifest.

The single retained generated demonstration then passed with exit status zero:

```bash
PYTHONPATH=<isolated-cpu-torch>:src OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  OPENBLAS_NUM_THREADS=1 python scripts/demo_space_jepa_population_v1.py \
  research/verification/population_preparation_v1_20261010/demo
```

`demo_attempt_started.json` and `demo_attempt.json` retain the exact executed
command, environment, source-file hashes before and after execution, stdout/stderr
identities, exit code, time and all eleven generated artifact identities. All eight
preparation/model source files remained unchanged. The run used 6.969 command
seconds; the script's internal preparation/inference timer was 0.264 seconds.

The 64 input rows represent eight artificial physical entities. Prepared example
counts were training 15, validation 5, test 10 and population B 10. All batches passed
through the same 610-parameter untrained model with finite, matching forecast/target
shapes and unchanged persistent state. No optimizer step was executed. The prepared
result digest is `0fbd1971b541beff39329056e069bab768d3805f186541efa0eae97fc3e68023`.
No additional demonstration or optional test was run after this success.

This concludes the bounded engineering verification. Draft publication and exact
remote-tree/CI receipts follow separately. Research remains `PROTOCOL_NOT_FROZEN`;
none of these generated results is a protected OOD evaluation or astronomy result.

### Draft publication and complete-tree readback

Published [draft PR #45](https://github.com/build-the-future-11/IRIS-Space/pull/45)
on the unchanged PR #40 branch. The reviewed implementation commit is
`3552d99cd8934091dcea5d407b33a463ec5be08c`, tree
`13e0d5027be7c7d1536401823b074a0c4e1d334b`. All **536 leaf paths, modes and Git
object identities** match the exact parent plus the 32 intended changed paths,
including all four original generated tensor blobs. The draft was re-read as
mergeable; no parent or concurrent branch was moved.

This publication-closure revision changes only state, this development history and
the engineering receipt. Runtime source, tests, workflow and generated evidence
remain unchanged. The initial code-head workflow runs were in progress at closure;
hosted results must be reported for the latest PR head rather than relabeling an
earlier head's result. The PR body records final-head verification separately.
