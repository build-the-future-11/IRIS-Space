# Implementation checklist — September 9, 2026

This assessment builds on the existing architecture and September 8 review. It
records this pass separately because the working tree contains ongoing TNS and
paper reconstruction work. Working means executable local behavior; scientific
validation requires separate evidence. This is not a claim of line-by-line review
of every module in this pass.

## What works and what remains

| Subsystem | Assessment | Change, extension or evidence needed |
| --- | --- | --- |
| CSV analysis and immutable runs | Working local workflow; previous fresh-install rehearsal produced two blocked example candidates | Add explicit time scale, flux calibration and coordinate context; version changed measurement semantics |
| Catalogue gates and review preflight | Real fail-closed implementation with version-bound evidence | Expand real-parser fault fixtures and reviewed live captures beyond TNS |
| SQLite review/outcome history | Real persistence and archived evidence versions | Exercise competing writes and coordinated recovery across stores |
| Review UI and outcome summaries | Working local inspection and current-version metrics | Preserve verified review-set order and archived versions in navigation; perform keyboard/mobile usability checks |
| Retry executor | Real implementation, defective maximum-delay enforcement | Fixed jitter cap and overflow in long retry sequences in this pass |
| Atomic publication | Real no-overwrite implementation; late collision detection wastes writer work | Added early existing-name rejection and meaningful race-collision errors; retained atomic final publication |
| Logistic baseline and JEPA | Executable training/evaluation, shadow research | Bind prediction-time inputs and training cutoffs; compare methods on a frozen cohort |
| Template search | Executable numerical search with synthetic evidence | Bind reports to candidate versions; qualify noise estimates and repeated-testing policy |
| Follow-up ranking | Real formula over caller-supplied factors; limited integration | Facility visibility, scientifically justified utility and human request tracking |
| Broker archive and operations tools | Working storage/replay primitives | Bounded polling supervisor, leases, late-arrival policy and operational event wiring |
| Image bundles | Integrity and metadata packaging | Actual scientific image/WCS validation against representative survey products |
| Legacy scripts and duplicate tree | Historical code; not a second supported product | Preserve provenance; relocate only after checking historical references |
| Paper/TNS qualification additions | Existing uncommitted work, under development | Verify separately before treating new reports as release evidence |

## Pseudocode and scaffolding inventory

- No `TODO`, `FIXME`, or `NotImplemented` body was found in the active package scan.
- The anomaly scoring protocol's ellipsis declares an interface. It is not a missing implementation.
- Exception-handler `pass` sites require context; their presence alone does not indicate fake behavior.
- Follow-up, campaign sketches, image packaging and broker operations are narrower
  than complete operational features. Their missing integration must remain visible.
- Test fixtures and fake astronomy modules exercise contracts; they do not prove
  compatibility with current live services.

## Executed work

- [x] Preserve the existing dirty working tree and identify overlapping work.
- [x] Make the retry maximum include jitter.
- [x] Avoid unbounded exponential integer growth during long retry sequences.
- [x] Reject existing output names before invoking a binary writer, including dangling symlinks.
- [x] Keep final no-clobber publication safe against a competing writer.
- [x] Report the requested destination rather than an internal temporary filename on collisions.
- [x] Add regression cases for retry exhaustion, delay bounds, dangling symlinks and competing publication.

Verification: `python -m pytest -q tests/test_atomic.py tests/test_clients.py
tests/test_reproducibility.py tests/test_pipeline_ingest.py tests/test_evidence_backup.py
tests/test_transient_search.py` passed 74 tests and 6 subtests using
`.test-tmp/release-env/bin/python`. Ruff lint and format checks passed for the four
changed Python files; strict mypy passed for the two changed source modules.
`git diff --check` passed. These are targeted checks, not a full release rerun.

## Next implementation sequence

- [ ] Integrate immutable review-set navigation with manifest verification and stale-version handling.
- [ ] Bind shadow search outputs to exact candidate and normalized-input versions.
- [ ] Extend parser replay to SkyBoT, SIMBAD, VSX and ALeRCE failure cases.
- [ ] Add explicit measurement time/flux contracts with compatibility/version tests.
- [ ] Add bounded broker supervision using the existing archive and cursor transactions.
- [ ] Extend prediction provenance before running comparative scientific evaluation.

The first three are extensions implied by existing artifacts and workflows. The
measurement and supervision items improve reliability across subsystems. A later
point-in-time retrieval explanation using eligible archived candidates could add
distinctive scientific value, once identity aliases and outcome leakage are controlled.
