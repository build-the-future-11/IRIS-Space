# Prospective mask and gradient correction

Status: DEVELOPMENT implementation correction, 10 October 2026.
Parent: `62a3470bbdb2411f88c14f720ed69a6c3766d299`, PR #40.
The prior preparation and shadow-evidence repairs are preserved.

## Reproduced defects

The quaternion radial gate computes `x * sigmoid(a * norm(x) + b)`. At `x=0`,
its analytic input Jacobian is `sigmoid(b) * I`: one half of the identity at
initialization. The square/sum/square-root implementation instead produced NaN
input gradients through the undefined norm derivative. The zero-epsilon norm
now uses PyTorch's norm operator, which supplies its zero subgradient at zero.
The positive-epsilon norm remains unchanged.

The encoder accepted a boolean token mask but chose `sum(mask)-1` as the summary
index. That indexes padding or an earlier observation for left padding or gaps.
It now selects the largest actual valid index. Both context and target encoders
use this rule. An independently compacted sequence provides the comparison
oracle because the model has no separate index-position embedding.

The encoder also projected padded NaN/Infinity values before multiplying by the
mask. Zero multiplication cannot remove those values or their effect on linear
weight gradients. Padding is now excluded before projection; live tokens must
be finite real floating-point values. Empty axes and device-mismatched masks
are rejected explicitly. The mask decides which observations are real; this
does not relax the data pipeline's strict source-value admission.

## Version and use

These are prospective scientific implementation corrections. New checkpoint
metadata uses `siderea.space_jepa_v2_checkpoint.v2`; the current loader rejects
v1 metadata before constructing a model. No checkpoint is relabeled, converted,
or silently migrated. Historical v1 inference remains reproducible by checking
out its original revision and environment. Newly trained v2 checkpoints use the
existing training, save/load and CLI entry points. Tensor preparation remains
v2, and the existing evaluation/shadow artifact formats remain v1.

No existing protected protocol, scientific result, source cohort, submission,
or prior negative result is replaced. In particular, this correction does not
complete the AQPM successor freeze or authorize a real-sky population test.

## Executed checks

The initial seven-case regression set had six failures and one passing attention
control. It exposed the zero-input analytic Jacobian error, two non-prefix masks,
and three nonfinite padding values. The final twelve new tests additionally
cover nonfinite live values, the target encoder and legacy-checkpoint refusal.
The actual CPU PyTorch suite also retains quaternion algebra, causal attention,
training/checkpoint roundtrip, preparation and the constructed one-epoch CLI
train/infer/memory/route/benchmark/shadow fixture. The dedicated exact-head
workflow includes all of these checks.

```bash
python -m pytest -q tests/test_quaternion_mask_gradients.py tests/test_quaternion.py tests/test_space_jepa_v2.py tests/test_space_jepa_v2_train.py
```

This demonstrates mathematical and execution contracts. It does not establish
forecasting improvement, training stability at research scale, astronomical
discovery, raw-source independence or model-promotion readiness.
