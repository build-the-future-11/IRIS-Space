# Claim-to-source ledger

| Claim | Source | Date | URL | Confidence / access note |
|---|---|---:|---|---|
| ZTF alert distribution handled up to 1.2 million alerts or about 70 GB per night and used Avro/Kafka. | Patterson et al., *The Zwicky Transient Facility Alert Distribution System* | 2019 | https://arxiv.org/abs/1902.02227 | High; primary system paper, full arXiv text read. |
| ZTF uses image differencing, ML reliability vetting, contextual packets, and typically distributes products within 13 minutes (95th percentile). | Masci et al., *The Zwicky Transient Facility: Data Processing, Products, and Archive* | 2019 | https://arxiv.org/abs/1902.01872 | High; primary system paper. |
| ALeRCE performs ingestion, aggregation, crossmatching, ML classification, and visualization, with separate stamp and light-curve classifiers. | Förster et al., *The ALeRCE Alert Broker* | 2021 | https://arxiv.org/abs/2008.03303 | High; primary broker paper, full arXiv text read. |
| ALeRCE's original stamp classifier used science/reference/difference stamps plus metadata and obtained about 94% accuracy on a balanced test set; experts selected candidates in SN Hunter. | Carrasco-Davis et al., *The Real-time Stamp Classifier* | 2021 | https://arxiv.org/abs/2008.03309 | High within the paper's stated test distribution; not transferable to I SPY. |
| ALeRCE's original light-curve classifier used 152 features and a two-level balanced random forest; subclass performance depended on detections, magnitude, and band coverage. | Sánchez-Sáez et al., *The Light Curve Classifier* | 2021 | https://arxiv.org/abs/2008.03311 | High; primary classifier paper, detailed arXiv text read. |
| AMPEL emphasizes provenance and changing information states and compared more than 200 selection functions on replayed ZTF alerts. | Nordin et al., *Transient processing and analysis using AMPEL* | 2019 | https://arxiv.org/abs/1904.05922 | High; primary framework paper. |
| ANTARES annotates alerts with catalogs, supports filtering, and records provenance. | Matheson et al., *The ANTARES Astronomical Time-Domain Event Broker* | 2021 | https://arxiv.org/abs/2011.12385 | High; primary broker paper. |
| Fink combines ingestion, annotation, filtering, redistribution, and evolving ML science modules. | Möller et al., *Fink, a new generation of broker* | 2021 | https://arxiv.org/abs/2009.10185 | High; primary broker paper. |
| A Fink active-learning experiment reported 89% purity and 54% efficiency, showing that purity and efficiency must be measured on labeled data rather than inferred from candidate yield. | Leoni et al., *Fink: early supernovae Ia classification using active learning* | 2022 | https://arxiv.org/abs/2111.11438 | High for that experiment only; used as methodological comparison. |
| Lasair aggregates alerts into objects and provides light curves and catalog crossmatches. | Smith et al., *Lasair: The Transient Alert Broker for LSST:UK* | 2019 | https://doi.org/10.3847/2515-5172/ab020f | High; primary short system report. |
| ZTF real/bogus classification addresses radiation hits, ghosts, registration/noise errors; braai reported low FNR/FPR on held-out tests. | Duev et al., *Real-bogus classification for ZTF using deep learning* | 2019 | https://arxiv.org/abs/1907.11259 | High within the study's datasets; used to motivate residual inspection. |
| Fixed-radius source association omits positional uncertainties, local priors, and physical information that Bayesian cross-identification can incorporate. | Budavári & Szalay, *Probabilistic Cross-Identification of Astronomical Sources* | 2008 | https://arxiv.org/abs/0707.1611 | High; foundational primary methods paper. |
| ZTF BTS combined a simple filter with human scanning and later removed variables/AGN using point-source coincidence and long-term history. | Fremling et al., *ZTF Bright Transient Survey I* | 2020 | https://arxiv.org/abs/1910.12973 | High; primary survey paper. |
| A magnitude-limited BTS statistical sample reported 97%, 93%, and 75% spectroscopic completeness at <18, <18.5, and <19 mag. | Perley et al., *ZTF Bright Transient Survey II* | 2020 | https://arxiv.org/abs/2009.01242 | High; demonstrates what a controlled completeness claim requires. |
| HiTS estimated recovery by injecting supernova light curves using empirical limiting-magnitude distributions. | Förster et al., *The High Cadence Transient Survey I* | 2016 | https://arxiv.org/abs/1609.03567 | High; primary injection/recovery example. |
| AHA routes ZTF alert anomalies through metadata-, feature-, and representation-based views and evaluates a fixed top-10 review budget. | Iskandarli et al., *Anomaly Hunter for Alerts* | 2026 | https://arxiv.org/abs/2602.12955 | High; primary methods preprint, used to motivate route-specific finite-budget evaluation rather than a performance claim for SIDEREA. |
| Astra-CLR studies multi-scale contrastive attention for astronomical light-curve representations. | Majumder et al., *Multi-Scale Contrastive Attention for Light-Curve Representation Learning* | 2026 | https://arxiv.org/abs/2606.31627 | High; primary methods preprint, cited as related representation-learning work. |
| AstroCo studies self-supervised Conformer-style encoders for light-curve embeddings. | Tan et al., *ASTROCO* | 2025 | https://arxiv.org/abs/2509.24134 | High; primary methods preprint, cited as related representation-learning work. |
| StarEmbed benchmarks time-series foundation models on variable-star observations and was accepted at ICML 2026. | Li et al., *StarEmbed* | 2026 | https://arxiv.org/abs/2510.06200 | High; primary current arXiv record checked on 2026-09-06. No benchmark result is transferred to SIDEREA. |
| Domain-informed multi-view self-distillation applies a JEPA-style objective to irregular astronomical light curves and evaluates on LEAVES, StarEmbed, and PYRREGULAR. | Rui, *Domain-Informed Multi-View Self-Distillation for Astronomical Light-Curve Representation Learning with JEPA* | 2026 | https://arxiv.org/abs/2606.28446 | High at primary arXiv manuscript level; this is the closest direct representation-learning comparator and no result is transferred to SIDEREA. |
| Rubin-era transient discovery increasingly requires automation while preserving scientifically meaningful validation and classification boundaries. | Rehemtulla et al., *The Automation of Optical Transient Discovery and Classification in Rubin-era Time-domain Astronomy* | 2025 | https://arxiv.org/abs/2512.11959 | High; primary review/preprint used for field context, not evidence of SIDEREA performance. |
| The I SPY campaign counts, thresholds, object outcomes, and missing provenance are as recorded locally. | `PIPELINE_OPERATIONS_RECORD.md`, source code, protocol | 2026 | local workspace | High for repository state; historical artifacts are incomplete, so claims are bounded accordingly. |

## Current local implementation and synthetic evidence

- Software counts/coverage/type scope: `software-verification.json` and its bound
  `software-verification-execution.txt`, Python 3.11.15, September 8. Historical
  multi-interpreter results remain in `software-verification-2026-09-07.json`.
- Two identical scientific replays and zero reportable synthetic candidates:
  `replay-execution.json`, with runner snapshot and input digest.
- Transient recovery and original noise/outlier failures:
  `../experiments/transient-search-final/results.json`; adaptive oracle covariance
  follow-up: `../experiments/covariance-search-final/results.json`.
- Seven prespecified null stresses: `../experiments/noise-stress-final/results.json`.
  These measure conditional simulated false alarms, not real survey performance.
- Exact reproduction of all 30 IID rows and trial digest:
  `experiment-reconstruction.json`. Tiny learning smoke tests:
  `../experiments/learning-smoke-results.json`; no representation-usefulness claim.


## Manuscript finishing pass — 2026-09-08

| Claim | Exact local evidence / transformation | Qualification |
|---|---|---|
| 24 productive runs; 23 distinct pulls; 424,223 input / 223,938 clean rows | PIPELINE_OPERATIONS_RECORD.md productive-run table → paper/figures/make_figures.py load_runs / make_campaign_dynamics → derived_run_metrics.json | Duplicate run 20260614T014019Z excluded from row totals; no object-level denominator reconstruction. |
| 3,824 distinct objects | PIPELINE_OPERATIONS_RECORD.md, Headline figures | Surviving summary attributes this to cached files; raw cached inventory is not public, so this number is summary-attributed. |
| 30/200 TNS and 55/193 variable rejections | PIPELINE_OPERATIONS_RECORD.md §4 | Different stage-specific evaluation denominators; missing join keys preclude explaining all seven unmatched evaluations. No end-to-end purity inference. |
| AT 2026rsp designation and report metadata | TNS public object page; `paper/research/primary-registry/AT2026rsp.public-record.json` | Independently registry-verified on 2026-09-13: object ID 212592, AT report 312644, reporter, coordinates, discovery datum, and internal ZTF identity. The structured capture is not raw page/API bytes or the historical cohort. |
| AT 2026pcz designation | `PIPELINE_OPERATIONS_RECORD.md` §5 and headline table | Summary-attributed only. Exact public lookup did not return a record on 2026-09-13, and report number 308376 alone is insufficient to infer object identity. |
| Pre/post differences and intervals | make_regime_bootstrap, seed 20260906, 50,000 run-cluster draws, ratio of sums | Ten eligible pre runs and six post runs; duplicates/incomplete stage records excluded. Descriptive, confounded policy/time/population contrast. |
| Dated 405/96 software test snapshot; 78.35% coverage | software-verification.json → source/test digests and bound execution log | Preserved historical verification snapshot, not a statement about later source revisions. |
| Newer local 416/96 result; 78.43% | TNS_TESTING_CHECKLIST.md and .test-tmp/tns-check.log | Later uncommitted TNS preparation; not substituted into the manuscript's older snapshot. |
| Synthetic signal/null counts | experiments/*-final/results.json and trial_statistics.json | Conditional simulation results, including adverse outcomes; no real-sky recovery claim. |

Primary arXiv metadata and abstract-level claim alignment rechecked for AHA
(2602.12955v1), Astra-CLR (2606.31627v1), AstroCo (2509.24134v1), StarEmbed
(2510.06200v4), astronomy JEPA (2606.28446v1), and Rubin-era automation
(2512.11959) in this pass. Corrected the
ledger's mistaken AHA first-author attribution; the bibliography already used
Iskandarli. This is not a fresh full-text verification of every bibliography entry.
