# IRIS National Fair 2026 application packet

Status: submission-ready positioning draft; do not submit until team eligibility, contribution ownership, and anonymity checks are complete.

## Opportunity fit

IRIS National Fair 2026–27 is open to Indian-origin students in Classes 5–12 who reside and study in India. Projects may be individual or teams of exactly two. Work must be original research with experimental data or a novel engineering improvement, and experimental data must be no more than 12 months old. The live registration portal lists the submission window as 1 August 2026, 4:00 pm through 3 October 2026, 6:00 pm. Required components are an abstract, introduction/objective, innovation statement, methodology, results/conclusions, acknowledgements/references, a full research paper, and a project video of at most 90 seconds.

Official registration: https://register.irisnationalfair.org/
Official rules: https://iris.exstemplar.com/guidelines.html

Important: the current SIDEREA manuscript is co-authored. The safest competition route is a two-person team submission if both contributors meet IRIS eligibility. Do not convert the project to a solo entry unless the contribution record clearly supports individual ownership of the submitted work.

## Recommended category

Primary: **PHYS — Physics & Astronomy**

Why: the scientific question is time-domain astronomical transient triage and detection under irregular sampling. The software exists to answer an astronomy research question rather than as a general-purpose software product.

Backup if reclassified by the SRC: **SFTD — Systems Software**.

## Recommended title

**SIDEREA: Evidence-Bound, Human-Supervised Triage of Optical Transient Alerts**

This title is strong because it names the scientific domain, the safety/reproducibility contribution, and the human-supervised boundary without claiming autonomous discovery.

## Abstract — 234 words / 250 max

Time-domain surveys generate more astronomical alerts than small research teams can inspect manually. We developed SIDEREA, a human-supervised system for triaging optical transient alerts while separating candidate ranking from scientific evidence and reporting decisions. The project grew from an audit of a small Zwicky Transient Facility search using public alerts distributed by the ALeRCE broker. SIDEREA combines survey-aware light-curve features, immutable candidate versions, time-limited catalog evidence, reproducible review queues, and a fail-closed decision gate in which missing or malformed evidence cannot count as clearance. The historical campaign contained 24 productive runs and 3,824 distinct broker objects; after removal of one duplicated pull, 223,938 of 424,223 detection rows passed recorded quality cuts. Two submitted objects received Transient Name Server designations, including ZTF26abdqbqw = AT 2026rsp. To test whether information distributed across irregular observations can improve detection, we also implemented a calibrated template-bank statistic over four transient morphologies and compared it with a separately calibrated single-epoch statistic. In matched independent-Gaussian simulations, the bank recovered 707/1000 Gaussian 2-sigma pulses versus 136/1000 for the comparator, but failed badly under unmodelled correlated noise and isolated outliers. A covariance-aware follow-up restored nominal null behavior only when the assumed noise model matched the data. The result is not a discovery classifier or survey-completeness measurement; it is an auditable workflow showing that transient ranking can gain sensitivity from temporal structure while scientific validity depends critically on explicit uncertainty, provenance, and human review.

## Introduction & Objective — 110 words / 100–150

Wide-field transient surveys can produce hundreds of thousands of alerts in a night, while expert review remains limited. Automated scores can help prioritize candidates, but a high score does not establish that an object is new, that a catalog query succeeded, or that a physical classification is justified. This project asks whether a small research team can make transient triage more reproducible and safer by separating ranking from evidence-bound decision making. The objective was to build and audit a human-supervised pipeline for irregular optical light curves, quantify its historical behavior, and test whether a calibrated multi-epoch transient statistic can improve recovery over a single-epoch comparator without hiding its failure modes.

## Innovation — 80 words / 50–100

SIDEREA treats ranking and scientific clearance as different computational problems. Candidate priority can use light-curve features or learned representations, but reportability requires fresh, explicitly successful catalog and registry checks bound to the exact candidate version plus human approval. The experimental extension adds a covariance-aware template-bank statistic for irregular light curves and calibrates the maximum over all searched shapes by simulation rather than interpreting a local score as global significance. The design records failures instead of converting missing evidence into confidence.

## Methodology — 185 words / 150–250

We first audited a historical optical-transient campaign that queried Zwicky Transient Facility objects through ALeRCE, cleaned light curves, ranked candidates, and then used independent registry, variable-star, moving-object, image, and human-review checks. We reconstructed run-level counts, deduplicated one repeated pull, and compared operational fractions before and after a recorded policy change without treating the association as causal. We then implemented SIDEREA with typed records, content-addressed candidate versions, immutable run manifests, time-limited external evidence, reproducible review queues, and fail-closed reportability rules.

For the synthetic detection study, each curve contained 64 irregular epochs over 60 days with heterogeneous uncertainties. We searched 252 nonnegative templates: 21 centers, three widths, and four transient morphologies. For each template, a constant background and nonnegative amplitude were profiled under a declared covariance model; the test statistic was the maximum standardized improvement across the bank. Separate random streams generated 4,095 null calibration curves and 1,000 evaluation curves per scenario. A maximum positive single-epoch residual was independently calibrated as the comparator. We tested matched Gaussian noise, correlated noise, isolated outliers, and a covariance-aware follow-up. All per-trial statistics, protocols, source snapshots, and plotting code were retained.

## Results & Conclusions — 111 words / 100–150

The audited campaign contained 24 productive runs and 3,824 distinct broker objects; 223,938 of 424,223 detection rows passed recorded quality cuts after removing one duplicate pull. Two submitted candidates received Transient Name Server designations. In synthetic independent-Gaussian tests, the template bank detected 707/1000 Gaussian, 336/1000 exponential, 621/1000 Bazin, and 552/1000 fallback 2-sigma pulses, versus 136, 60, 101, and 87 for the single-epoch comparator. However, diagonal calibration under correlated noise produced 454/1000 false alarms, and an 8-sigma outlier triggered 710/1000. With correctly supplied AR(1) covariance, false alarms fell to 11/1000. Temporal integration improves sensitivity, but robustness depends on valid noise assumptions; therefore automated ranking cannot substitute for evidence checks and human review.

## Acknowledgement & References — 80 words / 50–100

We acknowledge the public Zwicky Transient Facility alert stream, the ALeRCE broker, the Transient Name Server, SIMBAD, SkyBoT, and the AAVSO Variable Star Index for the data and external services used in this work. Key references include Bellm et al. (2019) and Masci et al. (2019) for ZTF, Förster et al. (2021) for ALeRCE, and relevant transient-template and broker literature cited in the full paper. All software, protocols, and retained experimental artifacts were developed and audited by the project team.

## 90-second video script — ~201 words

Every night, time-domain surveys can produce more astronomical alerts than a small team can inspect. The obvious response is to rank them with software. But a high score does not prove that an object is new, that a catalog query succeeded, or that the evidence is reliable.

We built SIDEREA to separate those questions. It analyzes irregular optical light curves, ranks promising candidates, records the exact evidence used, and then fails closed: missing, stale, or malformed checks cannot become scientific clearance.

We also tested a second question. Can evidence spread across several observations reveal faint transient signals better than looking for one extreme point? In matched Gaussian simulations, our calibrated template bank recovered 707 of 1,000 two-sigma Gaussian pulses, compared with 136 for a separately calibrated single-epoch method.

But the more important result was a failure. When the noise was correlated but we calibrated as if it were independent, false alarms rose to 454 out of 1,000. Supplying the correct covariance reduced that to 11.

So our conclusion is not that automation can discover transients by itself. It is that temporal structure can improve sensitivity, but only when uncertainty, provenance, and human review are treated as part of the scientific method.

## Submission visuals to build

1. **Problem-to-decision figure:** alert stream → ranking → independent evidence checks → human review → reportability gate. Make the separation between ranking and clearance visually dominant.
2. **Synthetic recovery figure:** four pulse families, bank versus single-epoch comparator at the same calibrated rule.
3. **Failure-mode figure:** matched independent noise, correlated-noise misspecification, one-outlier stress, correctly specified covariance. The point is to show that the method exposes its own failure conditions.
4. **Reproducibility panel:** immutable candidate version, evidence timestamps/hashes, protocol/source snapshot, and human approval binding.

## Anonymity scrub before upload

IRIS explicitly prohibits school name, city name, or state in the project video, paper, project report, presentation, or abstract. Create a dedicated IRIS submission copy rather than uploading the repository manuscript unchanged.

Remove from the submission copy:
- school name and affiliation;
- city/state/location references that could identify the students;
- personal email addresses;
- author bios or identity-bearing acknowledgements not required by the application portal;
- repository screenshots containing account names if they appear in the video or paper.

Keep scientific data-source names such as ZTF, ALeRCE, TNS, SIMBAD, SkyBoT, and VSX because they are research infrastructure, not student identity.

## Scientific claim boundary

Do not claim:
- autonomous astronomical discovery;
- measured survey completeness or purity;
- a global false-positive rate for real survey operations;
- that the template bank is robust to unknown covariance;
- that a TNS designation is a spectroscopic classification;
- that a software score establishes novelty.

The defensible contribution is: an auditable human-supervised transient-triage system plus a calibrated synthetic study showing both the sensitivity benefit of temporal integration and the failure of that benefit under noise-model misspecification.

## Exact next execution gate

Before submission:

- [ ] Confirm both project contributors satisfy IRIS 2026–27 eligibility if entering as a team.
- [ ] Freeze a contribution statement for each team member so ownership is clear to judges.
- [ ] Produce an anonymized IRIS paper copy from `paper/siderea_transient_triage.tex`; do not modify the archival research manuscript solely for competition formatting.
- [ ] Re-run the archived experiment artifact checks and record the exact commit SHA used for every numeric result quoted above.
- [ ] Build the four submission visuals from retained experiment artifacts.
- [ ] Record the 90-second video without school/city/state disclosure.
- [ ] Maintain a dated research data book linking hypotheses, protocol decisions, experiment runs, failures, and source/result hashes.
- [ ] Submit through the live portal before **3 October 2026, 6:00 pm**; treat this portal deadline as authoritative even if stale public copy elsewhere mentions a later date.
