# IRIS 2026–27 — Abstract and Synopsis Draft

**Project title:** SIDEREA: Evidence-Bound and Human-Supervised Triage of Optical Transient Alerts  
**Working category:** Physics & Astronomy  
**Entry type:** Unconfirmed; resolve individual/team eligibility and contribution ownership before submission.  
**Status:** Revised source for author and scientific review, not an approved submission.

Keep school, city and state identifiers out of the review copy. Confirm the live portal's requirements before final export. The abstract below is deliberately within the overlapping 200–250-word range of the differing requirements recorded in issue #26; this is not fresh rule verification.

## Project Abstract

A high ranking score does not establish that an astronomical alert is new, physically understood, or ready to report. SIDEREA is a human-supervised optical-transient triage workflow that separates ranking from evidence completion and reportability. It binds candidate versions to external checks and review decisions. A missing, failed, stale, or malformed required check remains unknown rather than silently becoming a clear result.

The methods study combines a historical campaign audit, software verification, and separate synthetic experiments. The retained operations table contains 24 productive run entries, including one explicitly documented repeat. Excluding that repeat gives 23 pull entries, totaling 424,223 detection rows and 223,938 clean rows. These are table-derived counts, not independent objects. The historical summary reports 3,824 distinct broker objects; that count has not been independently reconstructed from the original cached identities. Downstream summaries record 30 existing registry objects among 200 checks and 55 known or suspected variables among 193 catalog evaluations. Their different denominators cannot establish end-to-end accuracy.

Retained software tests and deterministic replay support the implementation's evidence-handling invariants. Separate archived synthetic studies report conditional signal recovery alongside severe false-alarm inflation under misspecified noise. Those failures remain part of the result.

The contribution is an auditable workflow and a diagnosis of the evidence needed for defensible transient reporting. It does not demonstrate real-sky completeness, classifier superiority, or physical discovery. Stronger claims require a prospectively frozen, time-forward cohort with complete selection records and independent outcomes.

## Introduction and Objective

Optical-transient searches must distinguish an interesting alert from an adequately checked candidate. An object may already be registered, resemble a known variable, require moving-object checks, or remain unresolved because an external service failed. A ranking score alone does not answer those questions.

SIDEREA addresses the transition from automated prioritization to human-supervised reporting. The objective is to preserve which observations, external evidence, policy version, and review decision support each candidate version. Required evidence must remain current and attributable before that version can advance.

The study asks: how can transient-search software allocate limited reviewer attention without turning missing checks, stale approvals, or changes in selection policy into unsupported scientific claims? It evaluates that question through retained historical records, implementation tests, and explicitly separate synthetic studies.

## Innovation

The design contribution is the explicit separation of ranking, evidence completion, reportability, registry designation, and physical classification. Content-bound candidate versions prevent an earlier review from silently approving later, changed evidence. Required checks fail closed: an unknown result blocks clearance rather than being interpreted as a negative match. Learned representations remain non-authoritative shadow components; they cannot override reporting requirements. This is a workflow and auditability contribution, not a claim of a new validated astrophysical classifier or superiority over established brokers.

## Methodology

The historical campaign used ZTF observations accessed through the ALeRCE broker. Its audit distinguishes detection rows, broker objects, repeated run entries, downstream evaluations, report packets, and registry records. The productive-run table is reconciled using its existing duplicate marker. The pre/post comparison retains the established regime cutoffs and excludes entries missing either downstream stage count; fractions are ratios of summed counts, not averages of per-run percentages.

The SIDEREA implementation standardizes observations, versions candidates, records policy and execution provenance, and binds external checks to the evidence requested. TNS, SkyBoT, SIMBAD, and VSX checks remain distinct from human image and wording review. Missing or stale required evidence cannot provide automated clearance.

Evidence is assessed in three separate classes: historical operational summaries, dated software tests and deterministic replay, and archived synthetic template-search experiments. The current reconciliation recomputes deterministic table quantities only. It does not rerun bootstrap simulations, retrain models, open held-out evaluations, or generate new scientific outcomes. A dated registry extraction is treated as retained documentation, not as a freshly verified registry response.

## Results and Conclusions

The 24-entry productive-run table reduces to 23 pull entries after excluding its documented repeat, yielding 424,223 detection rows and 223,938 clean rows. Fifteen deterministic quantities agree with the archived derived metrics. The separately reported 3,824-object total remains summary-attributed. The 30/200 registry and 55/193 catalog counts refer to different downstream stages, not a shared accuracy denominator.

A clean software verification dated 13 September 2026 records 499 tests and 103 parameterized subtests at its frozen revision. This is historical implementation evidence, not a current test count or astronomical-performance estimate. Archived synthetic studies retain adverse false-alarm behavior under noise misspecification.

The evidence supports auditable, human-supervised triage and identifies limits of the available records. It does not establish representative-sky completeness, physical classifications, or learned-model superiority.

## Limitations

The table reconciliation does not reconstruct the historical object-level selection cohort or establish independence between runs. The two downstream summaries lack a reconciled shared denominator; their seven-evaluation difference must not be filled with invented matches. Policy, time and input population are confounded in the pre/post comparison.

The retained 13 September structured extraction for AT 2026rsp is not raw registry HTML or an API response. It records one object's metadata, not two independently verified discoveries. A fresh page request on 26 September returned HTTP 403; an empty search result is not evidence that an object does not exist. No current classification or reporter status is inferred from that failed request.

Synthetic trial-level provenance, primary historical evidence, contribution ownership, eligibility, independent review, final paper/video inspection and submission approval remain separate checks. None is replaced by a passing software or document-integrity test.

## Acknowledgements and Reference Path

The existing manuscript and bibliography are the authoritative sources for scientific references and recorded contributors. Confirm acknowledgements, contribution statements, author order, and the eligible entrant or entrants with the authors before export. Do not attribute historical discoveries, reporting, observations, or another contributor's implementation to the entrant solely because this submission copy was prepared. Preserve attribution to the underlying surveys, brokers, registries and catalogs.

## Internal evidence map — exclude from the portal abstract

Source snapshot: `ec7a1903dcaf3c68c27f3dc8caa90f10cefa6d4f`.

| Statement | Retained evidence | Boundary |
|---|---|---|
| 24 entries; 23 after the stated repeat; row totals | `PIPELINE_OPERATIONS_RECORD.md`, productive-run table; `paper/figures/derived_run_metrics.json` | Arithmetic verified; no unique-object reconstruction |
| Fifteen deterministic quantities agree | `reconcile_historical_evidence.py` and its generated JSON report | No bootstrap rerun or new scientific outcome |
| 3,824 distinct objects | Operations record, headline summary | Summary-attributed |
| 30/200 and 55/193 | Operations record, rejection-funnel section | Different stage denominators |
| 499 tests and 103 subtests | `paper/research/software-verification-2026-09-13.json` | Revision `4e084a795be316ca991b213e2f8309b6143e7f9f`, not current head |
| Conditional synthetic recovery and adverse noise behavior | Existing `CLAIM_LEDGER.md`, `paper/AUDIT.md`, and manuscript's archived experiment references | Qualitative retained result; trial-level binding remains separate |
| AT 2026rsp metadata | `paper/research/primary-registry/AT2026rsp.public-record.json` | Retained search-index extraction, not fresh primary-response verification |

The original research manuscript, protocols, source data, numerical results and claim-ledger statuses are unchanged by this copy revision. This document is not permission to submit.
