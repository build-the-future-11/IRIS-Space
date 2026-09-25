# R07 output-collision and interruption qualification — 2026-09-25

## Scope

This change qualifies the existing SIDEREA failure-handling behavior required by `FINAL_TODO.md` R07. It does not alter scientific protocols, seeds, thresholds, rankings, candidate outcomes, held-out access, or manuscript claims.

## Existing behavior under qualification

The maintained pipeline already:

- creates a unique run directory and refuses to overwrite an existing run ID;
- writes run artifacts through atomic same-directory publication;
- records terminal `failed` manifests when analysis fails after a run starts;
- records terminal `interrupted` manifests on `KeyboardInterrupt`;
- preserves finalized partial artifacts in failed/interrupted manifests where available;
- writes the terminal manifest before publishing candidate state into the outcome ledger.

## Added retained regression coverage

`tests/test_release_r07.py` exercises four release-critical cases:

1. **Output collision:** a second analysis with the same run ID fails closed and leaves the original completed manifest byte-for-byte unchanged.
2. **Unreadable input:** a simulated permission failure at ingestion reaches the CLI as an actionable error and returns the controlled error status.
3. **Unwritable output:** a simulated permission failure during output publication leaves a terminal `failed` manifest containing the concrete exception and partial-artifact count.
4. **Ctrl-C / interruption:** a simulated interrupt after the completed manifest is durable but before ledger publication rewrites that manifest to terminal `interrupted` state and preserves its finalized artifact inventory.

## Closure rule

R07 is complete for the public-research release scope. Exact-head CI run `36158034367` executed on `ca57c212ec0bcb19eb07b7f2ce982c4599824604` and passed quality, security, Python 3.11–3.14 tests, packaging/isolated-wheel verification, and the four retained R07 qualification cases. This is engineering qualification evidence only; it does not authorize scientific release or change P06 licensing status.

P06 remains independently blocked on the explicit copyright-owner code/data/manuscript redistribution decision. No license grant is created by this work.
