# AQPM-JEPA / Space-JEPA 2 successor gate

Issue #31 defines a successor architecture with three proposed increments:
quaternion structure, jump-flow dynamics, and residual memory. As of the
5 October 2026 audit, none of those successor implementation identities or
their data/split manifests are present in this repository. The current state is
therefore **PROTOCOL_NOT_FROZEN**, not "experiment ready."

`FREEZE_STATUS_2026-10-05.json` is a non-result-bearing receipt of that state.
It authorizes neither scientific execution nor protected-outcome access.

## What must exist before any successor outcome

A future freeze artifact must pass
`scripts/verify_aqpm_successor_freeze.py`. The verifier requires all of the
following before it can emit `VERIFIED_PRE_OUTCOME_FREEZE`:

- a 40-hex successor source commit plus a separately identified base reference;
- byte-bound implementation and config files;
- byte-bound data and split manifests;
- entity-disjoint and chronological split identities, with distinct train,
  validation, and test hashes;
- prose definitions of each incremental mechanism;
- the full eight-cell factorial over quaternion, jump-flow, and residual-memory
  switches, including a matched-capacity all-off control;
- development-only readout/selection rules and a sealed-test access rule;
- a primary transient metric, calibration metric, false-alert metric, and the
  fixed robustness axes cadence, missingness, and population shift;
- predeclared ceilings for parameters, training cost, inference cost, and
  human-review cost;
- explicit separation of SIDEREA integration from model-ranking evidence; and
- explicit prohibitions on transferring old Space-JEPA/IRIS evidence or rescue
  tuning after a frozen-gate failure.

The verifier recomputes SHA-256 for every bound repository artifact and fails
closed on missing/tampered files, malformed hashes, incomplete factorial cells,
unsafe split declarations, prior protected-outcome access, or any permission to
rescue-tune after failure.

## Scientific boundary

Passing the freeze verifier would establish only that the successor experiment
was specified before outcome access. It would not establish efficacy and would
not by itself authorize the protected run.

If the eventual frozen successor fails its gate, preserve that negative result.
Do not retrofit the mechanism matrix, readout, split, metric, or resource
ceiling after seeing the outcome.
