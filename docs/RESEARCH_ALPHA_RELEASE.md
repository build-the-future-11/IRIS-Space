# Research-alpha release scope

## Audited release identity

The first audited candidate is commit
`b69f011c8cdfc26012f51d63b355312294caad58`, annotated tag
`v0.3.0-research-alpha.1`. Its clean verifier recorded `allow_dirty=false`, source
digest `af49d00db88f38cdbe74872a1f48854a4179d37a4f37150e8aad5c67a63bf7e7`,
497 passing tests plus 101 subtests, 77.91% branch coverage, strict doctor success,
and a passing isolated paper reconstruction. This identifies a research-alpha
software artifact, not a validated astronomical-performance result.

Supported locally: CSV ingestion, channel-aware features and ranking, immutable
run artifacts, version-bound review, reporting preflight, outcome summaries,
single-ledger evidence backup/verification, and shadow transient-search experiments.
Use `docs/FIRST_RUN.md` for an offline example without private credentials.

The transient bank includes Gaussian, asymmetric exponential, Bazin-like and
fallback-shaped templates. These are phenomenological shapes, not physical
classifications. Reported p-values depend on declared noise assumptions. The
preserved correlated-noise and isolated-outlier failures remain material limitations.
The new observation-deletion influence diagnostic does not change the decision rule.

Reviewer improvements include version comparisons after rejected stale submissions,
resettable plot filters, complete version-bound downloads and a read-only inbox
driven by actual reporting-preflight requirements. None bypasses approval or evidence.

Not qualified for this release: unattended reporting, physical identification,
real-sky completeness/purity, sustained live polling, hosted per-user identity,
scientific image-stamp verification, or a prospectively validated model comparison.
Synthetic experiments and software tests cannot establish these capabilities.

Release verification and remaining work are recorded in `FINAL_TODO.md` and
`PROJECT_FINISH_CHECKLIST.md`. A successful local check is not a claim that remote
CI passed or that a commit was pushed. Journal submission and package-index
publication are separate actions.

Run the fail-closed release verifier only from the exact candidate checkout:

```bash
make research-release-check PYTHON=.venv/bin/python \
  RELEASE_OUTPUT=/absolute/path/to/new-release-verification
```

The destination must not exist. The command requires a clean Git tree, runs formatting,
lint, MyPy, the coverage suite, byte compilation and strict dependency checks, then
reconstructs the paper experiments in an isolated copied workspace. It writes the Git
revision, clean-state evidence, logs, reconstruction record, and SHA-256 identities to
`release-verification.json`. `--allow-dirty` exists only for development audits and is
recorded in the result; an output with `dirty: true` is not a release candidate.

Package metadata retains `LicenseRef-Proprietary`. The repository has no approved
open-source license grant; public visibility must not be described as permission
to redistribute the project under an open-source license. A reusable public
research bundle needs the copyright owners' explicit license decision. No license
terms or third-party redistribution permissions were invented in this pass.
