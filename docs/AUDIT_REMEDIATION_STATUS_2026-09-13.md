# SIDEREA Audit Remediation Status

**Date:** 2026-09-13  
**Source audit:** `docs/END_TO_END_RESEARCH_AUDIT_2026-09-13.md`  
**Current commit identity:** `3e4451fc76809aad8bb4eb0f76defe9e2e2edabf` plus preserved working-tree changes

## Completed in this remediation pass

| Audit item | Change | Verification |
|---|---|---|
| P1 benchmark temporal binding | `bind_benchmark` now forwards recorded `time_block_days`; a round-trip regression covers raw singleton timestamps grouped into daily blocks. | `tests/test_research_qualification.py`: targeted suite passed. |
| P1 duplicate CLI handlers | Removed the earlier shadowed transient shard/merge handler pair and retained the byte-bound implementation. | MyPy passed on all 77 source files; CLI and research-qualification tests passed. |
| P1 CI dependency contract | Added Matplotlib to the `dev` extra used by the standard test matrix and added a packaging regression test. | Full suite passed in the complete release environment. |
| P1 closest literature | Added Rui 2026, the direct astronomy light-curve JEPA comparator, to the bibliography, manuscript comparison, and claim-source ledger. | Tectonic/BibTeX build passed; changed related-work page was visually inspected. |
| P1 historical wording | Replaced “confirmed discovery” and the ambiguous 0.026% selectivity statement with a summary-attributed documentation fraction. | Operations record now agrees with the manuscript's evidence boundary. |
| P3 release ergonomics | Added a clean-tree release verifier and Make target; included shell scripts in the source distribution manifest. | Development-audit run completed and emitted a hashed 250-artifact bundle. |
| Packaging release path | Included verification scripts in the sdist and built both sdist and wheel without network isolation from the prepared environment. | The sdist contains `scripts/verify-research-release.sh`; the wheel installed into a fresh environment and passed version/package-data checks. |

## Fresh verification

The development-audit release bundle is
`/tmp/siderea-release-verification-20260913-v1`. It is intentionally not durable
release evidence, but verifies the command and current working tree:

- Ruff formatting and lint: passed.
- MyPy: passed, 77 source files.
- Pytest with branch coverage: the recorded bundle contains 491 tests and 100 subtests
  passing at 77.83% coverage. The subsequently added packaging dependency regression
  passed in its targeted test run.
- Final integrated regression after the uncertainty and prospective-protocol work:
  495 tests and 100 subtests passed in 81.50 seconds.
- Strict dependency doctor: passed for NumPy, pandas, scikit-learn, PyTorch, Astropy,
  Astroquery, ALeRCE, and Matplotlib.
- Byte compilation: passed.
- Isolated paper reconstruction: passed.
- Manuscript Tectonic/BibTeX build: passed, 29 pages; only non-fatal underfull-box
  typography warnings remain.
- Source distribution and wheel build: passed; isolated no-dependency wheel import,
  version, `default.toml`, and `py.typed` checks passed.

## Still blocked on real evidence or owner decisions

These items cannot be truthfully manufactured from repository code:

1. The historical 3,824-object raw cohort, complete rejected/unreviewed population,
   original broker snapshots, and original submission response bytes are unavailable.
2. AT 2026rsp is independently verified against its public TNS page and a structured
   source-bound capture is archived. AT 2026pcz remains summary-attributed because an
   exact public lookup did not return a record and report ID 308376 alone does not
   establish object identity.
3. A preregistered real-data cohort, independent mature labels, blinded real-background
   injections, strong matched baselines, and a later-period test have not been executed.
4. Current live broker/catalog/TNS schema and service behavior require credentials,
   network access, archival permission, and a time-stamped read-only qualification run.
5. Copyright owners must choose code, manuscript, and data redistribution terms. The
   repository remains `LicenseRef-Proprietary`; no license grant was invented.
6. Authors must choose the target venue, approve authorship/affiliations, and approve the
   exact final artifact.
7. The working tree remains dirty because pre-existing work was preserved. A real release
   verifier run will correctly fail until owners reconcile and commit the intended files.

## Every-point progress ledger

Every prioritized audit item has been inspected and either implemented, advanced with an
executable artifact, or assigned a concrete external dependency. “Partial” does not mean
scientifically satisfied.

| Priority / item | Status | Work performed | Remaining acceptance evidence |
|---|---|---|---|
| P0 freeze exact research object | **partial** | Added clean-tree verifier, code-source digest, isolated reconstruction, logs and artifact hashes. | Owners reconcile the dirty tree, commit/tag it, run without `--allow-dirty`, and archive durably. |
| P0 reconcile historical claims | **partial / evidence-blocked** | Searched the repository for row-level data and primary TNS artifacts; only summary/legacy copies exist. Narrowed discovery/selectivity wording. | Recover permitted primary cohort and registry records or retain summary-attributed claims permanently. |
| P0 preserve no-performance boundary | **complete** | Paper, release scope, validation plan, and promotion semantics explicitly prohibit unsupported classifier/completeness claims. | Independent final claim review at submission. |
| P1 benchmark temporal binding | **complete** | Bound `time_block_days`; added rehashed-tamper rejection and round-trip tests. | None locally. |
| P1 green quality/test gate | **complete** | Removed duplicate CLI handlers, fixed test extra, added dependency regression. | Remote CI on the eventual clean commit. |
| P1 prospective real-data evaluation | **partial / data-blocked** | Added machine-valid draft protocol and owner/data intake contract. | Replace all draft values, approve and freeze before cohort opening, then acquire/mature data. |
| P1 matched strong baselines | **partial / data-blocked** | Existing benchmark enforces same-entity paired rankings; validation plan now specifies direct astronomy and general time-series comparators. | Locked real score artifacts, training cutoffs, compute matching, multi-seed later-period results. |
| P1 real-background injections | **partial / data-blocked** | Existing matched diagnostic remains explicitly non-qualifying; intake requires blinded real residuals and joint null/recovery reporting. | Permitted frozen residual backgrounds, blind, execution, and stratum-wise calibration. |
| P1 live dependency qualification | **partial / credential-blocked** | Existing parsers and fixtures were verified. On 2026-09-13 all required TNS credential variables were absent, so no unauthenticated request was attempted. | Supply approved credentials out of band; execute and archive the two-stage read-only qualification. |
| P1 literature and legal gates | **partial** | Added direct Rui 2026 comparison and ledger entry; preserved proprietary/no-grant boundary. | Full bibliography metadata audit and copyright-owner license/data/figure decision. |
| P2 uncertainty | **partial, major code complete** | Added deterministic paired whole-time-block bootstrap, retained conditional entity bootstrap, recorded/bound uncertainty unit. | Independent choice of estimand; hierarchical training/label/acquisition uncertainty and simulation coverage study. |
| P2 JEPA validation | **partial / data-compute blocked** | Existing leakage controls, collapse diagnostics, ablation matrix, downstream tasks, and promotion boundary were verified; draft protocol names the real endpoint. | Versioned corpus/checkpoints, multiple seeds, strong baselines, ablations and later-period test. |
| P2 photometric semantics | **partial / provenance-blocked** | Existing schema separates survey/passband channels, detection/limit state, uncertainty, time conversion, and token contract; intake enumerates required calibration lineage. | Dataset-owner calibration/passband/time provenance and cross-survey holdout results. |
| P2 human operational benefit | **partial / cohort-blocked** | Existing metrics report review events, disagreement, missing outcomes, latency and conditional yield without converting missing labels to negatives. | Prospective reviewer-duration/rubric data and prespecified clustered analysis. |
| P2 realistic scale/failure benchmark | **partial** | A 500-entity/16,000-row run completed in five shards: 6.11 s wall, 114,704,384-byte peak RSS, quota rejection, corruption detection and exact restart passed. The full fixture orchestration also completed. | Repeat for target duration and real volume/hardware; add live-service quota/latency and process-kill recovery. |
| P3 paper/accessibility | **partial** | Added closest work, rebuilt with BibTeX/Tectonic, visually inspected changed page and full 29-page document. | Venue selection/length reduction, tagged accessible PDF/alt text, author approval. |
| P3 legacy quarantine | **partial** | Canonical package boundary and legacy-quarantine tests exist; legacy content remains excluded from maintained lint paths. | Owner decision to archive/remove duplicate tree and release-manifest cleanup. |
| P3 experiment ergonomics | **complete** | One fail-closed command runs quality, coverage, strict doctor, compilation and isolated paper reconstruction and emits hashed evidence. | Clean-tree durable execution for the release candidate. |

**Measured progress:** 18/18 items received concrete work or dependency verification;
4 are locally complete, 10 are materially partial, and 4 are blocked on unavailable
primary data, credentials, compute/workload, or owner decisions. Counting partial items
at half weight gives **55% end-to-end audit remediation**. Repository-local engineering
is approximately **85% complete**; defensible real-sky scientific validation remains
approximately **20% complete** because the required cohort and outcomes do not exist yet.

## Next evidence-producing execution

Once real inputs and owner decisions exist, the correct sequence is:

1. Freeze a clean commit and immutable raw acquisition snapshot.
2. Freeze the prospective protocol before the test cohort opens.
3. Run shadow acquisition and preserve the full eligible denominator.
4. Mature outcomes using independent evidence without treating unresolved cases as negatives.
5. Run paired fixed-budget baselines, blinded real-background injections, and JEPA ablations.
6. Execute the clean-tree release verifier into a durable archive and build the reviewed PDF
   from that copied workspace.
