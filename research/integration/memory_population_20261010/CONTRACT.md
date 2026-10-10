# Memory availability and population preparation integration

This is a mechanical development integration recorded before local verification.
The proposal identities are PR45 `fb85b497afff0d626a16800c8b30d2e7874e7a34`,
PR43 `fa004bccc0aa75565898ef13c434c584f7c24ea0`, and common ancestor
`7f14c66f9018db0e15d4e87d713bbe47d9479b10`. PR45 retains its PR40 baseline
`f336ce1552d5270f3b3ad81682cd2fb0565ea0c2` and population as-of v2 implementation.

All three changed production files (CLI, episodic memory, memory router) are exact
PR43 blobs because their PR45 versions match the common ancestor. The sole
three-way source/test reconciliation is the CLI test: retain PR45's prepared-v2
schema assertion and PR43's explicit residual availability. Other imported donor
code, tests and documentation are byte-exact. Root state keeps every prior PR45
history entry; exact donor state and instructions are retained in `source_proposals/`.
A two-parent integration commit preserves both proposal histories. No scientific
mechanism, frozen configuration, historical output or model selection rule changes.

## Bounded verification declared before execution

Use existing generated-input correctness tests for memory availability and policy,
router/CLI compatibility, population preparation/as-of bounds, and the PR40
preparation/quaternion regression baseline. At most five pytest invocations,
120 seconds each and 300 seconds total, one numerical thread. No new test module.
The existing CLI test includes one tiny generated-tensor training epoch, inference,
memory routing, four-row benchmark and shadow assembly; these are correctness
fixtures, not a model comparison or scientific result. Other selected tests execute
only generated arrays, tensors and photometry. Keep each failure and command result.
Stop after a passing scoped gate. Existing research budgets are not reopened.

## Remaining boundaries

Successor protocol status remains NOT FROZEN. Supplied timestamps are not proof of
real target/model availability, source membership or physical-entity completeness.
Actual population provenance, method controls, scientific freeze and protected
execution still require their existing gates. Memory JSON v1 must be retained and
explicitly regenerated from provenance for the corrected v2 route; copying the
prefix cutoff into residual availability is not permitted.

PR43 freezes array backing bytes, not every Python attribute or NumPy view-metadata
mutation surface. PR41's separate full-immutability hardening remains unintegrated.
Do not describe this composition as full memory-object immutability or as scientific
validation. No protected/population outcome file is read, no hosted campaign is
launched, no reporting authority is granted and no draft is merged into its base.

## Verification and independent review

The integrated gate passes **131 existing tests**, with warnings treated as errors,
no failures or skips (pytest 13.34 seconds; command wall time 26.669 seconds).
The one generated CLI training epoch remains a correctness fixture. The first
command failed before collection because the wrapper resolved the virtualenv
interpreter symlink to a system interpreter without pytest; its raw failure and
command are retained. The corrected command path required no code/test change.
Two invocations consumed 26.738 command seconds, within the declared budget.
No additional tests were run after the successful gate.

The root agent independently reviewed the exact production diff and merged CLI
test, including availability validation/filter ordering and digest-bound schema
migration. No blocker was found for this scope; PR41's stronger immutability
contract remains a separate integration. `receipt.json` binds proposal identities,
source hashes, environment, commands, raw logs and review scope. Current hosted
checks are not claimed.
