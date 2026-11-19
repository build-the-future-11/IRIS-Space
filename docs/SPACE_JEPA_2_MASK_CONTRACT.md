# Space JEPA 2 masked-sequence and evaluation contract

## Valid observation order

`QuaternionEncoder` accepts floating-point tokens with shape `[batch, time,
input_dim]` and a boolean mask with shape `[batch, time]`. Every sequence must
contain at least one valid token. Valid observations retain their supplied
chronological order. The mask can represent right padding, left padding or
interleaved gaps; it is not required to be a contiguous prefix.

Each valid token must be finite. Invalid slots are replaced with zero **before**
input projection, so masked NaN or infinite padding cannot contaminate valid
representations or their gradients. The encoder selects the last valid position
as its summary, rather than interpreting the number of valid positions as an
array index. The same encoder behavior applies to the EMA target path.

Padding does not create, delete or infer observation timestamps. Supplied token
features continue to carry elapsed-time and cadence information. Packing the
same valid token features in the same order must preserve the summary and
forecast, and their input and model-parameter gradients within floating-point
precision. Causal attention still excludes later valid observations.

## Evaluation identity

The evaluator validates all row identities before executing the model. Explicit
`example_ids` must be a sequence with one nonblank string per row, unique across
the entire evaluation. A bare string, boolean, number or blank identity is
rejected rather than coerced. The existing `batch-N-row-M` fallback remains for
batches that omit identities, and collisions with explicit IDs are rejected.

Forecasts, target latents, losses and emitted per-horizon errors must be finite.
The real inference CLI publishes no evaluation artifact when these checks fail.
These checks cannot establish that an upstream physical-entity mapping is
scientifically correct; they prevent ambiguous rows within the supplied cohort.

## Compatibility and evidence

The evaluation v1 field names, batch-mean loss definition, checkpoint shapes and
parameters are unchanged. Correct finite right-padded inputs retain the prior
outputs. This is a repair of accepted mask and row-identity behavior, not a new
architecture or outcome metric. Earlier checkpoints and frozen results remain
untouched; reproducing old defective-mask behavior requires its recorded source
revision rather than overwriting old evidence.

`tests/test_space_jepa_v2_masked_evaluation.py` exercises packed/right/left/gapped
values and gradients, masked versus observed nonfinite values, causality,
identity collisions and the actual checkpoint-load/inference CLI publication
boundary. All inputs and checkpoints in those tests are constructed fixtures.
They do not establish astronomical performance or change the successor freeze,
population-shift, scientific-promotion or reporting gates.
