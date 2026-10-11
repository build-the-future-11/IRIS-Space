# Space JEPA 2 finite training admission

This bounded engineering continuation starts from draft PR45 at
`8c84939d5c03255722d78f0f313c36f88951672b`. It preserves all earlier source,
scientific protocols, results, budgets and protected-outcome holds.

The actual public trainer was exercised with the unchanged AQPM loss, AdamW,
gradient clipping and EMA path on a generated two-row linear fixture. The input
loss was finite, `0.12598009407520294`, in all three cases. Scale 1 produced a
normal update. Scale 1e20 produced finite gradients of magnitude about 1.25e31,
but an overflowing float32 norm silently erased them and still counted one
optimizer/EMA step. Scale 1e30 produced infinite gradients; clipping generated
NaN weights, and the function returned one completed step with NaN validation
loss. This is an arithmetic correctness witness, not astronomical evaluation.

## Intended correction and falsifier

Reject nonfinite scalar training loss before backward. Ask the existing PyTorch
gradient clipper to reject a nonfinite total norm before it mutates gradients or
the optimizer/EMA state. Reject nonfinite validation loss instead of returning a
successful training receipt. A rejected current step must leave its model
parameters and EMA unchanged. Earlier successful steps are not rolled back.

Finite gradients whose norm overflows are rejected as an explicit numerical
failure; this does not introduce a different clipping algorithm or silently
rescale an experiment. Keep the ordinary finite loss, reduction, clipping,
optimizer, EMA and checkpoint schemas unchanged. Do not import unrelated PR44
inference changes or reinterpret the batch-mean validation objective.

## Finite verification budget

The initial analytic probe above consumed one generated-fixture command. Allow
at most four targeted pytest commands (180 seconds total), one separate source
review, and one focused static check. All inputs are constructed; one numerical
CPU thread. Existing tiny train/checkpoint regressions are engineering fixtures.
No astronomical data, protected seeds 1000–1029, held-out study, paid jobs,
campaign dispatch or scientific fits are authorized. Stop after the focused
regressions, affected existing checks and review pass. Retain all failures.

## Executed verification

The unmodified trainer failed six of seven new cases; the ordinary finite
update control passed. The raw original pytest output remains in `baseline.log`.
The wrapper printed that log after pytest, so its shell status was zero; the
log's six assertion failures are the baseline result, not a successful gate.

After the repair, all **24 focused cases passed**, with warnings treated as
errors, in 2.28 pytest seconds / 3.016 command seconds. These include all seven
new arithmetic cases, the existing real AQPM train/checkpoint round trip, core
model checks and the masked-quaternion regressions. Exact command, source hashes,
environment and exit status are recorded in `candidate.json`; raw stdout is
`candidate.log`. The analytic finite reference produces bit-identical parameter
updates using the original clipping arithmetic. No subsequent test run was
needed. This does not establish full-suite or current hosted-CI success.

On rejection, existing gradients remain inspectable. The current optimizer/EMA
step is not executed. A failure during validation retains any earlier successful
training steps; this is not a transactional rollback or checkpoint-resume change.
Training and evaluation objective reductions and all artifact schemas remain
unchanged for admitted finite execution. Earlier study results remain historical
and are not automatically reclassified or rerun.

Independent root source review accepted the exact production diff and seven
new cases. This guards the demonstrated loss and gradient-norm failure paths;
it is not a guarantee against every possible optimizer-state or aggregate
arithmetic overflow. Byte compilation and whitespace checks passed. Root
approved a leased fast-forward of the existing draft, preserving prior history.
No separate draft, base merge, hosted rerun or scientific execution is needed.
