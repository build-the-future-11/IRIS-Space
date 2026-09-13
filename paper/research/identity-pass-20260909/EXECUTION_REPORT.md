# SIDEREA observation-identity execution — 2026-09-09

## 1. Project

SIDEREA supports evidence-bound astronomy candidate triage and human review.
Its separate shadow detector searches measured light curves; it does not establish
physical classifications or authorize discovery reports.

## 2. Initial state

The previous local validation passed 465 tests and 96 subtests. Ingestion already
had observation-ID validation, but normalized missing IDs too late. Shadow search
ignored observation IDs entirely and the CSV command inferred numeric identifier
types. Historical and current source work was preserved, including unrelated `.coverage`.

## 3. Ranked findings

1. P1: a changed-value replay with the same observation ID could enter shadow search.
2. P1: identical but distinct identified exposures were rejected by value-only checks.
3. P1: missing-ID spelling differences bypassed ingestion's exact-duplicate check.
4. P1: CSV type inference collapsed `001` and `1` identifiers.
5. P2: survey case/whitespace created inconsistent identity namespaces in shadow search.

## 4. Work completed

Updated `src/siderea/ingest/schema.py`, `src/siderea/research/transients.py`, and
`src/siderea/cli.py`. Added regression coverage in `tests/test_pipeline_ingest.py`
and `tests/test_transient_search.py`. Updated `docs/TRANSIENT_SEARCH.md`,
`FINAL_TODO.md`, and `PROJECT_FINISH_CHECKLIST.md`.

## 5. Root causes fixed

Validation now canonicalizes identity before duplicate checks. Shadow search checks
source/survey/observation identity independently of measurement values. CSV parsing
preserves textual identifiers. A second review found known/unknown-ID pairs could
still repeat identical evidence; both paths now reject this ambiguity.

## 6. Functionality completed

Distinct identified same-time measurements are retained, including equal-valued
ones. Reused IDs fail even if measurement values or bands differ. Missing-ID variants
are equivalent and cannot evade duplicate checks. Survey names are normalized before
shadow grouping and identity checks.

## 7. Improvements

Added 14 net regression cases to the full suite. Actual wheel execution verified
five observations across four epochs, preservation of source ID `001`, and rejection
of a changed-value replay with exit 2 and no output artifact. The implementation does
not silently deduplicate or invent replacement/retraction semantics.

## 8. Architecture

Preserved the ingestion, detector, ledger and reporting architecture. No new dependency,
database migration or model was introduced. The change aligns existing validation
boundaries without adding a new identity service.

## 9. Design/content

Documented identity scope, missing-ID ambiguity, textual identifiers and the distinction
between exposure and observation IDs. Distinct IDs do not prove independent noise.
No UI redesign or fresh visual/accessibility verification is claimed.

## 10. Automation

Existing full-suite and reconstruction commands exercise the new behavior. No scheduler,
live polling worker or external automation was added.

## 11. Executed verification

- `make check PYTHON=.test-tmp/release-env/bin/python`: PASS; 479 tests, 99 subtests,
  78.60% coverage; formatting, lint, strict typing and compilation pass.
- `python -m pytest -q tests/test_transient_search.py tests/test_pipeline_ingest.py`:
  PASS; 55 tests and 3 subtests in the task environment.
- `.test-tmp/release-env/bin/python -m build`: PASS, source distribution and wheel.
- `PYTHONPATH=src .../python paper/reconstruct.py --output .test-tmp/identity-reconstruction-20260909`:
  PASS; historical metrics/50,000 bootstrap draws and all 67 synthetic result rows
  reproduced; trial hashes and both generated tables agree with the references.
- Built-wheel `transient-search`: valid identified input evaluated; replay exited 2;
  explicit assertions verified five rows, source identity and absent replay output.
- `git diff --check`: PASS.

The reconstruction input manifest identifies its exact copied workspace, made before
the final missing-ID ambiguity guard. The final full suite and wheel exercise that
last guard. The experiment algorithms and frozen protocols were not changed.
An initial targeted test used the wrong IngestionBatch attribute; it was corrected
to the existing `observations` contract and rerun, without changing production behavior
to accommodate the test. Logs and final source hashes accompany this report.

## 12. Security/performance

This pass strengthens evidence integrity. It adds no permissions, weakens no reporting
gates and makes no external requests. No new throughput/security certification is
claimed. Existing protocols and archived adverse scientific results remain intact.

## 13. External blockers

Live TNS qualification needs bot credentials and independently checked cases. Real-sky
claims require representative data, independent labels and frozen evaluation. Paper
submission still needs venue/author confirmation, rights decisions and scientific review.
No GitHub push or paper submission was performed.

## 14. Remaining work by impact

1. Qualify survey-specific exposure/observation namespaces and cross-survey aliases.
2. Implement explicit time-scale, flux-calibration and coordinate-context contracts.
3. Freeze and execute the independently labelled real-data evaluation.
4. Complete paper claim, bibliography and primary-registry verification.
5. Complete the applicable operational polling, recovery and review-navigation work.

The larger checklist is not exhausted. Some remaining items are local engineering,
not external blockers. D05 remains partially open for exposure-ID qualification.

## 15. Provisional quality scores

Judgments based on repository evidence, not independent certification:

| Aspect | /10 | Main remaining gap |
|---|---:|---|
| Functionality | 7 | Live/image-qualified paths incomplete |
| Engineering | 8 | Explicit cross-survey contracts incomplete |
| Reliability | 7 | Production service/recovery qualification incomplete |
| Design | 6 | Interactive usability/accessibility audit still needed |
| Organization | 7 | Historical/current evidence needs a frozen release |
| Documentation | 8 | Paper source/claim/venue verification unfinished |
| Maintainability | 7 | Large CLI and persistence modules |
| Overall readiness | 6 | Local research workflows pass; science/deployment gates remain |

## 16. Commands

From the repository root; select new output paths:

```sh
python -m pip install -e '.[all,dev]'
python -m siderea doctor
python -m siderea analyze examples/photometry.csv --output-dir runs/identity-analysis --ledger runs/identity.sqlite
python -m siderea review-serve --ledger runs/identity.sqlite
python -m siderea transient-search examples/transient_flux.csv runs/identity-shadow.json --null-trials 999 --seed 20260909
make check PYTHON=python
make paper-check PYTHON=python
make paper-reconstruct PYTHON=python PAPER_OUTPUT=/absolute/path/to/new-reconstruction
python -m build
```

Installation is a usage recipe, not a fresh full-runtime install performed this pass.
Build dependencies were obtained by the isolated build. Commands support local use;
there is no claim of qualified hosted deployment or automatic reporting.
