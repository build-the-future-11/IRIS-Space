# IRIS 2026–27 — Abstract and Synopsis Draft

**Project title:** SIDEREA: Evidence-Bound and Human-Supervised Triage of Optical Transient Alerts  
**Working category:** Physics & Astronomy  
**Entry type:** TBD pending authorship/team eligibility check.

> Do not add school name, city, or state to the final project materials unless the current 2026–27 portal explicitly requires it.

## Project Abstract (200–500 words)

Modern sky surveys generate far more transient alerts than a person can inspect manually, but a high ranking score is not the same thing as evidence that an event is new, real, or scientifically reportable. This project develops SIDEREA, a human-supervised workflow for optical-transient triage that separates candidate ranking from evidence checks and reportability. Each candidate version is bound to the external evidence inspected, the software/policy revision used, and the human decision made from that evidence. Missing, failed, stale, or malformed checks are treated as unknown rather than as a false “clear,” so incomplete evidence cannot silently authorize a report.

The design was motivated by an audit of a historical transient-search campaign. Surviving records contain 24 productive runs and 3,824 distinct broker objects. Among recorded downstream stages, 30 of 200 registry checks identified an existing Transient Name Server object, while 55 of 193 catalog evaluations identified a known or suspected variable. These are stage-specific operational counts, not estimates of population purity or completeness. A major policy change during the campaign was also preserved rather than hidden: the early-veto fraction decreased and the shortlist fraction increased, but policy, time, and input population changed together, so the difference is not interpreted causally.

SIDEREA adds immutable candidate identities, evidence binding, fail-closed external checks, version-bound human review, deterministic review queues, and non-authoritative shadow learning. Software tests and deterministic replay verify these implementation invariants. Separate synthetic template-search experiments show both conditional recovery of injected signals and severe false-alarm inflation when the noise model is misspecified, demonstrating why apparent detections require careful uncertainty modeling.

The completed evidence supports a methods and scientific-audit contribution. It does not establish real-sky completeness, classifier accuracy, or superiority over existing transient brokers. A future time-forward cohort with complete outcomes and independent labels is required for those stronger claims.

## Introduction and Objective

Wide-field surveys such as the Zwicky Transient Facility produce streams of alerts for changing astronomical sources. Brokers can rank and classify these alerts, but downstream reporting still requires independent checks: an apparent candidate may already be registered, match a known variable or moving object, arise from a subtraction artifact, or remain uncertain because an external service failed.

The objective of this work is to design and audit a triage workflow in which a candidate can advance only when the evidence required for that exact candidate version is valid and current. The project asks a methodological question: **how can transient-search software allocate limited human attention without allowing ranking scores, missing data, or stale external checks to become unsupported scientific claims?**

## Innovation

SIDEREA separates five concepts that are often collapsed in automated pipelines: ranking, evidence completion, reportability, registry status, and physical classification. Its central safety rule is fail-closed: a failed or missing required check remains unknown and blocks report preparation rather than being interpreted as “no match.”

The workflow also binds external evidence and human review to immutable candidate versions, so a later data or policy change cannot silently inherit an earlier approval. Learned representations are permitted only for review-queue ordering in shadow mode; they are not allowed to override the reportability predicate.

## Methodology

The historical campaign used ZTF alerts accessed through the ALeRCE broker. The audit distinguishes detections, broker objects, unique objects, repeated candidate evaluations, prepared packets, registry designations, and physical classifications.

The current SIDEREA implementation standardizes observations, versions candidates with content hashes, records policy and execution provenance, binds external queries to position/epoch/radius and freshness, and requires completion of TNS, SkyBoT, SIMBAD, and VSX checks before automated clearance. Human image and wording review remains separate from automated ranking.

Three evidence classes are intentionally kept distinct:

1. **Historical campaign evidence:** surviving run-level records and stage-specific downstream counts.
2. **Software verification:** tests, deterministic replay, state-machine checks, and fail-closed behavior.
3. **Synthetic scientific experiments:** controlled template-search studies under known and misspecified noise.

No prospective real-sky cohort is opened by this submission package.

## Results and Conclusions

The surviving campaign record contains 24 productive runs covering 3,824 distinct broker objects. In the recorded downstream checks, 30 of 200 registry evaluations matched an existing TNS object and 55 of 193 catalog evaluations matched a known or suspected variable. These denominators belong to different stages and cannot be combined into an end-to-end accuracy estimate.

The clean software snapshot reported 499 tests plus 103 parameterized subtests and deterministic reconstruction of archived numerical studies. Synthetic experiments showed that the search could recover signals under some controlled conditions, but also produced severe false-alarm inflation when the assumed noise model was wrong. This adverse result is part of the conclusion, not an excluded failure.

The main conclusion is therefore methodological: reliable transient triage requires explicit evidence states and provenance, not merely a higher ranking score. The present evidence supports the SIDEREA workflow and its auditability, but not real-sky completeness, purity, or classifier-superiority claims.

## Limitations

The repository does not contain a complete row-level reconstruction of the historical campaign. Original campaign photometry, some selection rows, and submission response bytes were intentionally not retained. Historical policy, date, and query composition are confounded. The existing campaign also lacks the complete labeled rejected population required to estimate false negatives.

A stronger detection-performance claim would require a preregistered time-forward cohort, complete eligible and rejected objects, independent labels, held-out evaluation, injection–recovery, and matched comparisons under the same information/review budget.

## Acknowledgements and Reference Path

The scientific manuscript contains the complete bibliography and acknowledgements:
`paper/siderea_transient_triage.tex`

Project repository:
https://github.com/build-the-future-11/IRIS-Space

Primary systems/resources described in the paper include ZTF, ALeRCE, the Transient Name Server, SIMBAD/VizieR/VSX, and SkyBoT. The final IRIS export should carry the paper bibliography rather than inventing shortened citations here.
