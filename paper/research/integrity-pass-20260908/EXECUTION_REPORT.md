# SIDEREA execution report — 2026-09-08

## 1. Project

SIDEREA is an evidence-bound, human-supervised astronomy candidate-triage system.
It ingests photometry, ranks candidates, preserves review evidence and gates reporting.
Its separate template-search experiments are shadow diagnostics, not a validated
physical classifier or autonomous discovery/submission service.

## 2. Initial state

The previous local software check passed 421 tests and 96 subtests. The paper had
reproducible synthetic studies and a reconstruction runner, but its table generator
trusted summary JSON and reconstruction checked only trial hashes/row equality.
Real-sky comparative efficacy, live TNS qualification and submission readiness were
not established. Existing unrelated work, including `.coverage`, was preserved.

## 3. Highest-value findings

1. P1: fabricated/inconsistent summary counts could enter a table without comparison
   to their underlying trial statistics.
2. P1: unrecognized noise labels silently selected ordinary Gaussian behavior.
3. P1: experiment provenance could snapshot checkout source while importing a
   different installed detector.
4. P2: non-60-day noise experiments still used fixed 20/40/60-day gap bounds and a
   fixed 30-day variance transition.

## 4. Completed work

Added `src/siderea/research/archives.py` and integrated it into
`paper/experiments/make_tables.py` and `paper/reconstruct.py`. Updated both experiment
runners, Makefile checks, paper instructions and operating checklists. Added 44
regression/behavior tests in `tests/test_research_archives.py` and upgraded the
existing five reconstruction tests to use real archived evidence.

## 5. Bugs fixed

The noise runner's default Gaussian branch previously accepted misspelled scenarios;
validation now rejects unsupported/duplicate scenarios before output creation.
The search runner now rejects declarations of null suites it does not implement.
Both runners compare the loaded detector's source against the source being archived.
Gap and variance transitions now scale with the declared observation duration.

## 6. Features completed

Archive verification checks supported schemas; report, protocol, source and trial
hashes; complete unique declared scenario/method rows; finite vectors with declared
trial counts; sorted calibration statistics; plus-one p-values; detection counts,
fractions and Wilson intervals. The table generator fails before creating output
when verification fails.

## 7. Improvements

Re-hashing an inconsistent report no longer makes it acceptable. Tests change
counts, intervals, fractions, rows, p-values, protocol files and source snapshots.
A small actual 90-day experiment verifies duration-dependent gap behavior and its
result archive. Original adverse results are retained unchanged.

## 8. Architecture

A shared, standard-library verifier provides one contract for reconstruction and
table generation. No detector architecture, public ranking policy, database schema,
reporting gate or frozen scientific protocol was replaced.

## 9. Design and content

Paper instructions explain integrity checks, correct source imports and the limits
of checksum evidence. The manuscript PDF and previous sealed review bundle were
not modified in this pass. That bundle is an earlier snapshot and does not contain
these safeguards. No new visual-interface audit is claimed.

## 10. Automation

`make paper-check` runs both evidence test modules. `make paper-reconstruct` explicitly
uses checkout source. Reconstruction retains command logs, input hashes, runtime
inventory and comparison results rather than overwriting previous runs.

## 11. Validation

- `make check PYTHON=.test-tmp/release-env/bin/python`: 465 tests and 96 subtests pass;
  78.56% coverage, formatting/lint and strict typing for 75 source files pass.
- `make paper-check PYTHON=.test-tmp/release-env/bin/python`: 49 tests pass.
- `PYTHONPATH=src .../python paper/reconstruct.py --output .test-tmp/paper-integrity-reconstruction-final-20260908`:
  historical metrics and 50,000 bootstrap draws reproduced; IID 30, covariance 30,
  noise 7 result rows reproduce exactly, including trial digests; tables identical.
- `.test-tmp/release-env/bin/python -m build`: source distribution and wheel built.
- Importing the new verifier directly from the built wheel verifies all three
  reference archives. Wheel includes `siderea/research/archives.py`, no `iris/` package.
- Offline `analyze` example: two candidates, zero reportable, as expected from missing
  external evidence. Assertions checked the result.
- `transient-search` example with 999 null trials/seed 20260908: constant p=.311,
  synthetic pulse p=.001; only the pulse flags; reporting qualification remains false.
- `git diff --check`: pass.

An intermediate full run failed two runner-import tests because it overlapped the
addition of the shared protocol validator. It is retained as `intermediate-check.log`.
The complete suite was rerun after source edits, without disabling or weakening tests.

`validated-source-sha256.json` identifies the tested code. `input-manifest.json`
identifies the copied experiment workspace, which predates final error-handling/type
cleanups in the verifier; experimental algorithms/protocols were unchanged afterward.
The final suite and built-wheel checks validate the final verifier. The hashes are
integrity evidence, not signed independent attestation.

## 12. Performance and security

No performance benchmark or new authentication audit is claimed. Evidence loading
now rejects non-finite JSON, duplicate keys, unexpected source inventory and malformed
trial summaries. Source inventory names are fixed before files are opened. Existing
security gates remain intact. No credentials were added and no live services called.

## 13. External blockers

Live TNS qualification requires configured bot credentials and independently inspected
test cases. A stronger scientific claim requires an independently labelled real-data
cohort and frozen evaluation design. Submission needs venue/author confirmation,
rights decisions and independent scientific review. This pass did not push or submit.

## 14. Remaining worthwhile work, ranked

1. Qualify time scales, flux calibration/units and cross-survey physical identity
   before mixing real-survey data. These include local engineering, not just credentials.
2. Freeze and run a complete real-data evaluation with independent labels and common
   finite-budget baselines; preserve failures, exclusions and unresolved outcomes.
3. Complete paper claim/bibliography/equation review and primary TNS record attribution.
4. Finish operational review-set navigation and bounded polling/recovery qualification
   if required for the chosen deployment scope.
5. Freeze a reviewed source revision and permitted release artifacts, then rerun CI.

The larger project checklist is not exhausted. Existing open engineering items are
not reclassified as external blockers to claim completion.

## 15. Provisional quality assessment

These are engineering judgments from repository evidence, not measured certification.

| Aspect | /10 | Principal remaining gap |
|---|---:|---|
| Functionality | 7 | Live and image-qualified workflows remain incomplete |
| Engineering | 8 | Some cross-survey contracts and deployment paths need integration |
| Reliability | 7 | Production service, contention and recovery qualification incomplete |
| Design | 6 | Full current browser/accessibility/usability pass not performed |
| Organization | 7 | Large historical and current evidence collections need release freezing |
| Documentation | 8 | Final claim ledger, bibliography and venue requirements incomplete |
| Maintainability | 7 | Large CLI/persistence modules and research script contracts |
| Overall readiness | 6 | Useful local research system; real-sky and submission gates remain |

## 16. Commands for use

From the repository root, in a suitable Python 3.11+ environment:

```sh
python -m pip install -e '.[all,dev]'
python -m siderea doctor
python -m siderea analyze examples/photometry.csv --output-dir runs/review-analysis --ledger runs/review-ledger.sqlite
python -m siderea review-serve --ledger runs/review-ledger.sqlite
python -m siderea transient-search examples/transient_flux.csv runs/review-shadow.json --null-trials 999 --seed 20260908
make check PYTHON=python
make paper-check PYTHON=python
make paper-reconstruct PYTHON=python PAPER_OUTPUT=/absolute/path/to/new-reconstruction
python -m build
```

Output paths must be new. The installation command above is a user recipe; no fresh
full runtime installation was performed in this pass. Isolated build dependencies
were installed by the successful package build. See `docs/TNS_TESTING.md` for the
separate credentialed, read-only qualification procedure; local examples do not
qualify a production deployment or an astronomical discovery.
