# IRIS document evidence binding — 26 September 2026

Related: issue #26 and the existing `CLAIM_LEDGER.md`.

## What this closes

The manifest maps all **16 existing ledger rows**, without changing their wording or
status, to four retained documentation files at source snapshot
`ec7a1903dcaf3c68c27f3dc8caa90f10cefa6d4f`. Each file has its exact repository path
and Git blob identifier. The checker generates SHA-256 receipts for the bytes it
actually reads and rejects changed or missing files, missing/reordered ledger rows,
changed ledger statuses, invalid references, and accidental approval flags.

This is a **document-integrity slice of B06**, not completion of B06, a scientific
review, an experiment replay, or submission authorization. In particular, binding
the text of an assertion does not establish that the assertion is scientifically
true or that its primary evidence has been independently reconciled.

## Run from the repository root

```sh
python3 submission/iris-2026-27/verify_evidence.py \
  --root . \
  --manifest submission/iris-2026-27/DOCUMENT_EVIDENCE_MANIFEST.json
python3 -m unittest discover -s tests -p test_iris_submission_evidence.py -v
```

The integrity command prints its JSON report to stdout. It makes no writes, fetches
no network resources, invokes no subprocesses, and runs no research code.

Exit meanings:

- **0:** the document binding check passed; submission is still `BLOCKED`.
- **1:** malformed input, missing/changed evidence, or a binding/guard failure.
- **2:** `--require-ready` was requested and the package is not submission-ready.

Use `--require-ready` when a caller must fail rather than treat a document-integrity
PASS as submission readiness. This v1 draft checker deliberately cannot authorize
scientific execution or submission. Ordinary source review remains necessary:
anybody able to edit both a document and its manifest can rebind them. The recorded
commit identity was obtained through the GitHub connector; this offline command
checks document bytes against the recorded blob IDs, not the Git history itself.

## Source inventory

| Document | Recorded Git blob |
|---|---|
| `submission/iris-2026-27/CLAIM_LEDGER.md` | `5d5d5f3e98cbf4c0a68dfc8b3a95b66e30cbd619` |
| `PIPELINE_OPERATIONS_RECORD.md` | `17d5577e49ed9791c7972da332a190d11e2bf14d` |
| `paper/AUDIT.md` | `57ead27c1522d0f53716200ccc203e01e9eecf82` |
| `paper/research/software-verification-2026-09-13.json` | `d8885d966d48c57b87f879bb15ea03246cf7568c` |

## Findings retained rather than upgraded

The **499 tests and 103 subtests** belong to the dated verification of
`4e084a795be316ca991b213e2f8309b6143e7f9f`, not the current source snapshot or this
change. That historical test count is not replaced with this checker's test count.

The operations table contains 24 productive-run rows. Removing only its explicitly
marked duplicate reprocessing row, `run_20260614T014019Z`, leaves 23 table rows and
changes the summed input/clean rows from **438,610 / 231,688** to
**424,223 / 223,938**. This is arithmetic on an already-retained summary, not a new
scientific run. It does not prove the remaining objects are mutually disjoint and
does not reconstruct the **3,824 unique objects** from primary cached identities.
B01 therefore remains partial.

The operations headline lists two historical designations, while its defensible-
claims section narrows to one detailed surviving summary and still requires primary
registry verification. This check does not resolve that discrepancy. B04 remains
open; no verified-discovery or spectroscopic-classification claim is upgraded.

The primary figure/bootstrap/trial files for C05–C07 and C11–C12 have not been bound
by this documentation-only pass. Their exact retained artifacts, transformations,
source revisions, and review still need to be linked before quantitative export.
The adverse noise results and the prohibited real-sky/superiority claims remain.

## Verification performed in this pass

- Four captured document files matched all four Git blob identifiers returned by
  the connector at the exact source snapshot.
- The real document manifest passed: 16 claim rows, four verified document files,
  `source_integrity=PASS`, `submission_readiness=BLOCKED`.
- Targeted tests on Python 3.13.5: **36 tests plus 11 subtests passed**.
- The `--require-ready` command returned **2**, as intended.
- Byte-compilation of the new Python files succeeded.

The container could not clone the repository because GitHub DNS resolution was
unavailable there. Connector reads supplied the four captured documents, whose
Git blob hashes were then verified locally. The full repository suite, hosted CI,
Ruff formatting/lint, and other Python versions were not run by this local pass.
Do not reinterpret these targeted checks as full-repository certification.

## Remaining human and primary-evidence gates

Issue #26 still owns eligibility, individual/team contribution ownership, primary
historical and registry evidence, exact result/figure lineage, final paper/video,
independent/author review, and final submission approval/receipt. No historical
result, seed, threshold, protocol, experiment permission, deployment, or production
database is changed by this addition.
