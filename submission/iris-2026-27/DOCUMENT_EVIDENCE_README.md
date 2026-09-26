# IRIS evidence binding and historical reconciliation — 26 September 2026

Related: issue #26 and Draft PR #30. This is a partial claim-source audit, not a submission authorization.

## Completed scope

The manifest preserves all **16 existing claim-ledger rows and statuses** and binds **six retained files** to exact repository paths and Git blob identifiers at snapshot `ec7a1903dcaf3c68c27f3dc8caa90f10cefa6d4f`. The two additions are the archived derived metrics and the dated AT 2026rsp registry extraction.

`verify_evidence.py` checks document identities, claim coverage/order, references and false approval flags. `reconcile_historical_evidence.py` additionally parses the retained operations table and matches **15 deterministic fields** against the archived metrics. It preserves the documented duplicate exclusion, incomplete-stage exclusions, existing pre/post cutoffs and ratio-of-sums calculation.

Neither program fetches live data, imports model or experiment code, runs a bootstrap, changes results, or grants submission approval. A PASS means the stated local integrity/arithmetic checks passed. It is not an independent scientific review.

## Reproduction commands

Run from the repository root with Python 3.11 or newer:

```sh
python3 submission/iris-2026-27/verify_evidence.py \
  --root . \
  --manifest submission/iris-2026-27/DOCUMENT_EVIDENCE_MANIFEST.json
python3 submission/iris-2026-27/reconcile_historical_evidence.py \
  --root . \
  --manifest submission/iris-2026-27/DOCUMENT_EVIDENCE_MANIFEST.json
python3 -m pytest -q tests/test_iris_submission_evidence.py tests/test_iris_historical_reconciliation.py
```

Both commands write JSON to stdout. Exit **0** means the specified audit passed, **1** means invalid/missing/changed evidence or a failed check, and **2** means `--require-ready` was requested but submission readiness remains blocked. Both always keep scientific execution and submission authorization false.

The commands verify local bytes against recorded blob IDs, not independently fetched Git history. An editor able to change both evidence and manifest can deliberately rebind them; ordinary source review remains necessary.

## Exact source inventory

| Retained source | Git blob identifier |
|---|---|
| `submission/iris-2026-27/CLAIM_LEDGER.md` | `5d5d5f3e98cbf4c0a68dfc8b3a95b66e30cbd619` |
| `PIPELINE_OPERATIONS_RECORD.md` | `17d5577e49ed9791c7972da332a190d11e2bf14d` |
| `paper/AUDIT.md` | `57ead27c1522d0f53716200ccc203e01e9eecf82` |
| `paper/research/software-verification-2026-09-13.json` | `d8885d966d48c57b87f879bb15ea03246cf7568c` |
| `paper/figures/derived_run_metrics.json` | `38dfaff8b5b6e5117c804a161410e8df3fb2c760` |
| `paper/research/primary-registry/AT2026rsp.public-record.json` | `af4d9249464c0e46104b66dc7a9ef8baaa8523bd` |

## Findings and boundaries

The 24-entry table sums to **438,610 detection rows / 231,688 clean rows**. Excluding only the marked repeat `run_20260614T014019Z` of `run_20260614T013847Z` leaves 23 pull entries and **424,223 / 223,938** rows. Seven remaining entries lack a complete pair of stage counts. The unchanged comparison uses ten pre-regime and six post-regime entries. These are run-table quantities, not proof of independent objects or reconstruction of the **3,824 unique objects** reported by the historical summary.

The source contract is the existing `load_runs` and `make_campaign_dynamics` logic in `paper/figures/make_figures.py`, blob `51cb5e40308e3daeb59e61a999f8a35eb2940291`. This pass read its relevant source sections but did not run the plotting or bootstrap functions. The retained bootstrap intervals are now bound by the derived-metrics file; they were **not rerun**.

The **499 tests / 103 subtests** remain the 13 September verification of `4e084a795be316ca991b213e2f8309b6143e7f9f`. They are not this change's tests. The distinct **30/200 registry / 55/193 catalog** counts still lack a reconciled shared denominator; the seven-evaluation difference is unresolved.

The registry extraction is dated **13 September 2026** and records **AT 2026rsp, object 212592, AT report 312644, reporter Aadi Ajeesh Nair**. Its own capture method is search-index extraction, not raw registry response bytes. A fresh 26 September page request returned HTTP 403; direct search returned no result. Neither result disproves object existence. The extraction is now linked, but current registry verification, the second designation, physical classification, and personal discovery attribution are not certified.

## Verification actually performed

- Local Python **3.13.5**: **61 targeted tests and 20 subtests passed**, including the real six-file manifest and all 15 deterministic comparisons.
- New captures match their connector-returned Git blob identifiers; every retained file in the manifest passes the byte-identity check.
- Both `--require-ready` paths return **2**; submission remains `BLOCKED`.
- The preceding PR head `5ec913784106615f4180fdf650f4e5dcdc386868` passed hosted workflow **36212790331**: quality, security, Python 3.11–3.14 tests, and packaging. That result belongs to that preceding head, not this follow-up commit.
- GitHub cloning was unavailable in the local container because DNS resolution failed. Targeted local checks used connector-fetched, hash-verified captures. A local Ruff package was unavailable. Fresh hosted checks for this follow-up remain a separate receipt.

## Submission-copy changes

The abstract is **234 whitespace-delimited words**. Introduction/objective, innovation, methodology and results sections are 123, 79, 169 and 121 words respectively; acknowledgements are 63 words. The spoken video body is **170 words**, excluding the still-unconfirmed entrant introduction. These counts are writing checks, not live portal verification or measured video duration.

The revised copy now attributes historical summary counts, dates the software evidence, preserves adverse synthetic findings and avoids claiming sole authorship. It remains review copy: no PDF or video recording was produced by this pass, no portal was submitted, and no approval checkbox was marked complete.

Issue #26 continues to own raw historical/registry evidence, synthetic trial/figure provenance, contribution and eligibility decisions, independent review, final export inspection and submission approval. The original paper, archived data, experiments, protocols, seeds, thresholds and claim-ledger statuses are unchanged.
