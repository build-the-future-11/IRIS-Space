# SIDEREA Research Audit and Roadmap

## Executive assessment

SIDEREA has a credible and unusually careful safety architecture for research
software: models rank, evidence and people decide; external failures close the
gate; and candidate versions, reviews, and outputs have meaningful provenance.
That is a real strength. The central scientific question is not yet answered:

> Given the information available at an alert-time decision point and a fixed
> human review budget, does SIDEREA find more scientifically useful candidates
> than a well-specified broker, heuristic, and supervised baseline without
> increasing harmful false selections?

Today the answer must remain unknown. The repository demonstrates component
correctness and synthetic execution, but not calibrated real-sky utility. The
highest-value work is therefore a disciplined empirical program, not a larger
neural network.

This document challenges the concept, mathematics, implementation, model,
datasets, and experimental plan. It is a roadmap, not evidence that an item is
complete. "Must" items are required before making a performance claim. "Explore"
items are hypotheses that need a preregistered experiment before promotion.

## Scientific contract to freeze first

SIDEREA currently combines three different jobs. They must retain separate
targets, evidence, and success criteria.

| Job | Correct output | Decision unit | Never claim from it alone |
|---|---|---|---|
| Operational triage | Ordered review queue / abstention | Candidate at a fixed alert age | Physical class or discovery probability |
| Statistical search | Null-calibrated excess statistic under a declared likelihood | Object-channel and declared monitoring family | Reality or novelty probability |
| Representation learning | Reusable embedding and uncertainty / OOD diagnostics | Snapshot of a light curve at a cutoff | Scientific utility from low pretext loss |
| Human evidence process | Reproducible review state and blocked/ready status | Exact candidate version | Model performance or source truth |

The primary end point should be **independently adjudicated campaign-relevant
useful outcomes per fixed reviewer hour**, with false-selection, time-to-review,
abstention, and diversity guardrails. Precision at K is a secondary metric, not
the whole scientific objective. A campaign must define "useful" before training:
for example, independently confirmed young extragalactic transient, or a class of
rare event suitable for follow-up. It cannot mean "matched a later broker label."

## Red-team findings and non-negotiable fixes

| Priority | Finding | Why it changes the science | Required response and acceptance evidence |
|---|---|---|---|
| P0 | No frozen, complete, point-in-time real cohort with mature labels. | Retrospective selected labels cannot estimate live-stream utility. | Freeze acquisition snapshots, full eligible denominator, decision timestamp, labels, exclusions, and alias groups before fitting. Reconcile every upstream candidate to inclusion/exclusion/outcome. |
| P0 | Photometric provenance is not yet a physical measurement contract. | A learned or template signal can be an artifact of calibration, subtraction, unit, or time-scale mismatch. | Record flux unit, zero point/system, forced/difference/total semantics, calibration ID, quality flags, time scale, coordinate frame/epoch, and upstream observation revision. Validate against survey products. |
| P0 | Current `main` lacks a current green release verification. | A scientific pipeline needs reproducible executable evidence. | Resolve/reproduce the SQLite `disk I/O` failures in suitable temporary storage and run the clean-tree release verifier on the exact research commit. |
| P0 | The detector controls within-object trials, not the operational family of objects, nights, and repeated looks. | Object p-values do not control a survey or campaign false-discovery rate. | Predeclare monitoring family and stopping/review rule; report family-wise/FDR or online-FDR behavior under realistic null streams. |
| P0 | JEPA has no evidence of incremental real-sky benefit. | A representation loss is not a science metric. | Compare it against strong non-JEPA baselines on frozen future data at identical review budgets, with multi-seed uncertainty and failure reporting. |
| P0 | Real image/cutout and forced-photometry evidence are not validated. | Alert-table-only ranking is exposed to subtraction artifacts and blends. | Add version-bound cutout validation and an image-aware abstention/artifact route; do not imply image qualification before this exists. |

## Core concept and causal framing

### What SIDEREA should be

Treat SIDEREA as a **selective decision-support system under delayed, censored
feedback**, not as a discovery classifier. Its task is to allocate scarce expert
attention while keeping audit candidates and human evidence independent of the
ranker. This framing permits useful research claims even when class labels are
delayed and incomplete.

The causal graph should explicitly include: survey/cadence/weather, source class,
measurement process, broker selection, model score, review allocation, reviewer
behavior, follow-up availability, and eventual label. Training only on reviewed or
TNS-confirmed objects creates selection bias. The random-audit reserve is a good
starting primitive; it needs to become a formal logged-propensity evaluation
design.

### Checklist: concept and governance

- [ ] **C01 — Freeze one science use case.** Define target population, alert age,
  follow-up resource, primary useful outcome, harm categories, review budget, and
  minimum useful improvement. Acceptance: a signed preregistration predates the
  first evaluation cohort.
- [ ] **C02 — Separate novelty, reality, class, urgency, and reportability.**
  Represent each as a different typed output with its own labels and uncertainty.
  Acceptance: no UI/API field permits a novelty or anomaly score to be displayed
  as a probability of a real transient.
- [ ] **C03 — Model the feedback loop.** Record selection propensity for every
  eligible candidate, including unreviewed ones, and preserve randomized audit
  allocation. Acceptance: inverse-propensity and sensitivity analyses can be run
  without reconstructing history from logs.
- [ ] **C04 — Define abstention.** Specify low-information, out-of-domain,
  conflicting-evidence, and degraded-service states that route to manual review
  or no recommendation. Acceptance: simulated OOD/low-SNR cases abstain rather
  than receive overconfident ranks.
- [ ] **C05 — Define a change-control policy.** Models, labels, feature schemas,
  prompts, thresholds, and catalogue rules require semantic versions and a shadow
  period. Acceptance: a past decision can be reproduced from an immutable policy
  bundle.

## Measurement, data model, and astronomical semantics

The existing channel-aware design is a helpful safeguard, but passband name and
survey name are only part of the measurement identity. A physically meaningful
observation requires a calibration and provenance lineage. In particular,
difference flux, forced PSF flux, aperture flux, and calibrated total flux should
never be pooled or made interchangeable by a generic normalization.

### Checklist: canonical observation contract

- [ ] **D01 — Promote time to a first-class contract.** Store original time,
  declared time scale (UTC/TAI/TDB), conversion routine/version, observatory or
  barycentric correction status, and uncertainty where supplied. Test JD/MJD
  conversion, leap-second boundaries, and mixed-scale rejection.
- [ ] **D02 — Promote photometric semantics to a first-class contract.** Require
  quantity type, unit, zeropoint and magnitude system when relevant, calibration
  identifier, reference-image identity for difference flux, and whether a point is
  a detection, forced measurement, limit, or missing. Reject incompatible pooling.
- [ ] **D03 — Support censored observations honestly.** Upper limits are not zero
  flux and are not absent data. Add a limit value, likelihood convention, and
  quality state. Verify with analytic censored-Gaussian cases.
- [ ] **D04 — Preserve revisions rather than deduplicating them away.** Stable
  survey/exposure/observation IDs plus revision/retraction lineage must distinguish
  duplicate delivery from corrected photometry and legitimate repeated exposures.
- [ ] **D05 — Build identity as evidence, not a string match.** Maintain an
  append-only alias graph with coordinates, epochs, match evidence, uncertainty,
  and unresolved state. Split by connected physical-identity group, never by
  broker identifier alone.
- [ ] **D06 — Add image-level provenance.** Bind science/template/difference
  cutouts, WCS, PSF/seeing, mask/flag state, and measurement-to-pixel association
  to the candidate version. Test wrong position, wrong epoch, wrong band, corrupted
  FITS/WCS, and unrelated cutouts.
- [ ] **D07 — Create a survey conformance suite.** Each adapter needs complete,
  empty, malformed, rate-limited, timeout, schema-drift, partial, and revised-data
  fixtures from approved sanitized captures. Passing a parser unit test is not
  live-contract qualification.
- [ ] **D08 — Quantify measurement uncertainty.** Compare normalized records and
  derived features on a stratified manually checked sample across SNR, crowding,
  cadence, passband, survey, and subtraction quality. Publish discrepancies.

## Statistical transient-search mathematics

The current template bank is useful as a diagnostic, but it rests on a narrow
observation model: a constant background plus nonnegative phenomenological excess,
finite Monte Carlo nulls, and optionally declared covariance. That is a valid
engineering testbed, not yet a general transient detector.

### Mathematical risks

1. **Null misspecification:** heteroscedastic Gaussian errors, fixed or known
covariance, and sign-symmetric residual blocks are often violated by subtraction
artifacts, seasonal systematics, blending, and calibration changes.
2. **Multiplicity:** template center, width, family, channel, object, nightly
stream, and repeated monitoring all create look-elsewhere effects. Correcting only
within an object is insufficient for a triage claim.
3. **Censoring and selection:** non-detections, detection thresholds, and broker
preselection affect both likelihood and population denominator.
4. **Template adequacy:** the four templates are morphology probes, not a generative
population model. A fitted fallback-like tail does not identify a TDE; a poor fit
does not establish non-transient status.
5. **Post-selection inference:** interpreting a p-value after the same object was
selected because it looked unusual creates an unreported selection pathway.

### Checklist: detector and inference

- [ ] **M01 — Write a declared likelihood catalogue.** Include independent
  heteroscedastic Gaussian, robust/heavy-tailed alternatives, calibrated correlated
  residual model, censored observations, and explicit invalid-data behavior. Every
  score records its likelihood ID and fitted nuisance parameters.
- [ ] **M02 — Fit noise only on eligible background data.** Build versioned
  survey/field/season/channel background artifacts that cannot use target/test
  events. Acceptance: incompatible calibration artifacts are rejected.
- [ ] **M03 — Run a full null stress matrix.** Vary error underestimation,
  heavy tails, correlation length, seasonal gaps, seeing/background correlations,
  blending, bad subtractions, cadence, and missingness. Report false selection and
  calibration failures, not only favorable conditions.
- [ ] **M04 — Implement campaign-level error control.** Compare preregistered
  Bonferroni/Holm, Benjamini-Hochberg/FDR, and online-FDR or alpha-investing rules
  appropriate to repeated alert streams. Measure realized false-selection behavior
  under simulations and real negative controls.
- [ ] **M05 — Quantify grid and template loss.** Inject off-grid peaks, edge events,
  multimodal/rebrightening events, durations outside the bank, and chromatic
  evolution. Report power/runtime curves and retain a simple detector when added
  flexibility does not help.
- [ ] **M06 — Separate detection from ranking.** Use detector statistic, null
  calibration, rank score, and decision threshold as distinct versioned artifacts.
  Never combine a p-value and an anomaly score by multiplication or informal
  "confidence" language.
- [ ] **M07 — Evaluate sequentially.** Recompute only using information available
  at each declared alert age; report first-crossing time, repeated-look policy, and
  latency. A final full-light-curve result is a retrospective analysis, not alert
  performance.
- [ ] **M08 — Explore hierarchical models only after M01--M07.** A hierarchical
  Bayesian/Gaussian-process residual model, state-space model, or learned simulator
  may better express survey/field effects, but must be judged by predictive
  calibration, robustness, and operational latency rather than elegance.

## JEPA and representation-learning audit

### Current design

The implementation is a compact irregular-time transformer. A token carries delta
time, normalized value, normalized error, band ID, detection flag, and
value-present flag. A contiguous physical elapsed-time target block is masked by
default, with index-count masking retained as an ablation; an online
encoder predicts EMA-target representations with Smooth-L1 loss; embeddings are
mean pooled. It includes useful controls: chronological/group separation, target
leakage-aware context rebasing, contract digests, repeated-mask evaluation, and
amplitude/effective-rank diagnostics.

### Key limitations to challenge

- Elapsed-time and observation-count masking are implemented, but neither has yet
  beaten random, multiscale, change-point, or cross-band alternatives on a frozen
  real-sky benchmark.
- One global survey-agnostic band vocabulary risks treating filters with the same
  label as scientifically comparable despite different throughput/calibration.
- Mean pooling erases where the informative rise, color change, gap, or anomaly
  occurred. It is a sensible baseline, not the final sequence readout.
- Latent prediction can learn cadence, SNR, field, source brightness, or survey
  shortcuts. Low loss can coexist with poor class, novelty, OOD, or early-alert
  utility.
- The target teacher, mask policy, EMA schedule, encoder depth, embedding width,
  and normalization are all hypotheses. No published performance follows from the
  current defaults.
- Light-curve-only embeddings omit image morphology, contextual catalog features,
  host environment, quality masks, and survey state. These may be decisive for
  artifact rejection, but must be added without leaking labels or future data.

### Checklist: representation data and architecture

- [ ] **J01 — Build a pretraining corpus card.** State every survey, release,
  object count, observation count, time coverage, filters, units, quality cuts,
  license, known selection bias, alias policy, and train/validation/test cutoff.
- [ ] **J02 — Fix token semantics before scale-up.** Add survey/instrument and
  calibrated channel embeddings; represent limits/censoring and quality flags;
  encode observation-time uncertainty where relevant. Preserve an explicit unknown
  state rather than collapsing heterogeneous filters into one bucket.
- [ ] **J03 — Make masking time-aware.** Ablate index-count blocks against elapsed-
  time windows, multiscale windows, random points, event/change-point masking, and
  cross-band masking. Hold context count and physical duration distributions
  comparable. Event-focused masking is a plausible hypothesis for irregular series
  but must not be assumed beneficial.[9]
- [ ] **J04 — Add observation-process inputs cautiously.** Cadence, depth,
  seeing, airmass, moon, field, and quality can explain missingness; include them
  only when they are available at inference and test whether they create survey
  shortcuts. Compare with a model that excludes them.
- [ ] **J05 — Compare readouts.** Mean pool, attention pool, query/CLS pool,
  event-local pooling, and multi-resolution pooling should be evaluated on the
  same frozen tasks. Inspect whether representations retain alert-age information
  without relying on future observations.
- [ ] **J06 — Build multiband interaction explicitly.** Test asynchronous
  cross-attention, channel-specific encoders plus fusion, and shared encoder with
  survey/channel embeddings. Recent multiband work reports gains over independent
  single-band treatment, but its transferability must be tested on SIDEREA's
  surveys and objective.[6]
- [ ] **J07 — Add uncertainty/OOD outputs.** Use ensemble or checkpoint variance,
  distance-to-reference, density/typicality, and conformal risk-control candidates.
  Evaluate OOD by survey, season, cadence, SNR, source family, and artifact type;
  route uncertain cases to abstention or audit, not a fabricated class probability.
- [ ] **J08 — Improve collapse diagnostics.** Track feature variance/effective rank
  per survey, band, length, magnitude/SNR, epoch, seed, and checkpoint; add nearest-
  neighbor label purity and representation stability under benign augmentations.
- [ ] **J09 — Secure reproducibility.** Check deterministic/resume equivalence,
  optimizer/RNG/data-loader state, mixed-precision tolerances, and checkpoint
  compatibility. Run at least five seeds for each serious comparison.

### Checklist: objectives and baselines

- [ ] **J10 — Establish a non-neural floor.** Compare engineered features plus
  regularized logistic regression, gradient boosting with missingness indicators,
  random ranking, broker scores, and legacy I SPY ordering.
- [ ] **J11 — Establish domain representation comparators.** Compare TS-JEPA to
  ASTROMER-style masked/transformer embeddings, a contrastive TS2Vec-style
  objective, sequence autoencoding/forecasting, and a current astronomy foundation
  model where licensing and inputs permit.[2][5][8]
- [ ] **J12 — Separate pretext success from downstream success.** Report mask loss
  and reconstruction/forecast diagnostics, but choose models only on a frozen
  downstream validation objective. Require positive value on more than one task:
  early classification, retrieval, OOD/artifact detection, and budgeted ranking.
- [ ] **J13 — Test label efficiency.** Run 1%, 5%, 10%, 25%, and full-label
  fine-tuning/linear-probe curves. The central self-supervision hypothesis is a
  better sample-efficiency or OOD trade-off, not merely a higher in-sample score.
- [ ] **J14 — Explore multimodal fusion late.** A two-tower light-curve/cutout
  model, cross-attention with host/context metadata, and retrieval-augmented review
  are good extensions. First benchmark each modality alone and enforce exact
  timestamp/provenance binding; never let later catalog or image products leak.

## Dataset program

Use a layered dataset strategy. One dataset cannot establish all claims.

| Layer | Purpose | Candidate sources | Main limitation |
|---|---|---|---|
| Unit/physics fixtures | Parser, likelihood, calibration, edge cases | Hand-built analytic cases and survey-conformance captures | Not population performance |
| Controlled simulation | Rare-class coverage, counterfactual cadence/noise, false-alarm stress | Rubin DP0/DC2, `rubin_sim`, PLAsTiCC/ELAsTiCC-style simulations | Simulator mismatch and label prior mismatch |
| Historical real survey | Representation pretraining, retrospective point-in-time benchmark | ZTF/ALeRCE, MACHO, OGLE, ATLAS, Kepler where licenses allow | Selection and late-label bias |
| Early Rubin | Contract, cadence, and domain-shift qualification | DP1/DP2 and approved broker products | Small/atypical sky/cadence and evolving schemas |
| Prospective campaign | Primary utility/safety result | Frozen live broker denominator plus independent outcomes | Expensive and delayed labels |

Rubin now offers simulated DP0 releases and early DP1/DP2 products, but early
data have commissioning/survey-validation limitations; they are excellent for
adapter and shift tests, not automatic proof of full-operations performance.[11]
The public alert/cutout and prompt-product access rules also need explicit legal
and access review before inclusion in a redistributable corpus.[12]

### Checklist: dataset construction

- [ ] **DS01 — Create immutable dataset manifests.** Every snapshot records raw
  object/alert IDs, source URLs/queries, byte hashes, schema/parser version,
  retrieval timestamp, licensing/access restriction, corrections, and derived
  artifact lineage.
- [ ] **DS02 — Build a label ledger, not a single target column.** Include label
  source, timestamp, maturity, evidence reference, adjudicator, confidence policy,
  censoring state, and retraction history. Preserve ambiguous and unresolved cases.
- [ ] **DS03 — Preserve the full denominator.** Store every eligible arrival,
  selection probability, review decision, missing reason, and outcome maturity.
  Negative labels cannot be inferred from non-review.
- [ ] **DS04 — Make point-in-time views.** Materialize an example at first
  eligibility, +1 day, +3 days, and any operational deadline. Cut all photometry,
  catalog context, broker features, cutouts, and metadata at the decision time.
- [ ] **DS05 — Define group/time/sky splits.** Group aliases and close repeated
  detections; use chronological held-out periods and rolling origins. Add survey,
  field/sky, season, cadence, brightness, and class-shift tests.
- [ ] **DS06 — Audit representativeness.** Compare cohort versus full incoming
  stream across SNR, magnitude, Galactic latitude, cadence, band, broker class,
  alert age, and missingness. Report where labels have no support.
- [ ] **DS07 — Add negative controls deliberately.** Curate artifacts, variables,
  movers, AGN, duplicates, non-events, and bad subtractions. These are not an
  afterthought: they are the actual competing population at review time.
- [ ] **DS08 — Use simulations as stress instruments.** Simulate survey cadence,
  limiting magnitude, noise, host/background blending, extinction, redshift,
  missing bands, and label noise. Calibrate simulation parameters against held-out
  real distributions; do not transfer simulated precision as a real-sky claim.
- [ ] **DS09 — Publish data cards and split manifests.** A peer should be able to
  identify what is public, access-controlled, derived, synthetic, withheld, or
  nonredistributable and reproduce every reported count.

## Benchmark, experiment, and ablation design

### A. Tasks

Run each task at fixed information cutoffs and retain all predictions.

1. **Budgeted prioritization:** useful outcomes at K / reviewer-hour, with audit
   propensity correction and false-selection guardrails.
2. **Early class/reality prediction:** only if labels and targets are defined;
   report calibrated probabilities, selective risk, and abstention.
3. **Anomaly/OOD detection:** detect unknown or shifted populations without
   relabeling novelty as error; report precision-at-inspection-budget and discovery
   case studies with blinded expert review.
4. **Retrieval:** leave-one-object-group-out neighbor relevance, label purity,
   diversity, and temporal availability of retrieved examples.
5. **Template detection:** false-alarm and recovery at declared family level over
   realistic null and injection streams.
6. **Human system:** time, error, disagreement, trust calibration, override rate,
   and outcome under score-blinded versus score-visible review.

### B. Evaluation protocol

- [ ] **E01 — Preregister one primary endpoint and one promotion criterion.**
  Example: the lower 95% paired block-bootstrap confidence bound for useful outcomes
  per 100 reviewer-hours exceeds zero and the point estimate exceeds a practical
  minimum. All other analyses are secondary/exploratory.
- [ ] **E02 — Use nested time-aware model selection.** Hyperparameters, feature
  decisions, threshold rules, augmentation, and calibration are finalized on
  development/validation periods. The latest historical test is opened once;
  the prospective period is never used for iteration.
- [ ] **E03 — Compare equal resources.** Same eligible population, cutoff,
  inference latency, reviewer budget, random-audit allocation, and follow-up
  policy. Do not compare a full light-curve JEPA result to a first-alert heuristic.
- [ ] **E04 — Report paired uncertainty.** Pair methods on the same candidate/night;
  resample at the preregistered independent unit (object-within-time-block or whole
  time block). Include training, label, and acquisition uncertainty where feasible.
- [ ] **E05 — Perform error taxonomy review.** Blindly audit false positives,
  false negatives, abstentions, and model disagreements by astrophysicist reviewers.
  Report concrete failure modes, not only aggregate metrics.
- [ ] **E06 — Test distribution shift.** Hold out survey, season, field, cadence,
  filter configuration, brightness/SNR range, and novelty family. A random split is
  only a diagnostic, never the headline result.
- [ ] **E07 — Measure compute and latency.** Record CPU/GPU, memory, throughput,
  energy where possible, queue latency, failure recovery, and cost per reviewed
  useful candidate. A more accurate model that misses the operational window loses.
- [ ] **E08 — Freeze and archive all outputs.** Save per-object predictions,
  abstentions, logits/scores, model/checkpoint/data/policy digests, code revision,
  seeds, environment, and failures. No report should rely only on aggregate tables.

### C. Minimum ablation matrix

| Axis | Required variants |
|---|---|
| Representation objective | TS-JEPA; masked reconstruction; contrastive; forecasting; engineered features only |
| Masking | Count-contiguous; elapsed-time-contiguous; random; multiscale; event/change-point focused |
| Inputs | Flux only; +uncertainties; +band; +survey/calibration; +quality/cadence; image/context separately |
| Multiband | Independent channels; shared encoder; fused cross-band architecture |
| Pooling | Mean; attention; event-local; multiscale |
| Normalization | Per-curve robust; context-only; survey-calibrated; explicit ablations for brightness retention |
| Downstream head | Linear probe; calibrated logistic; gradient boosting; shallow neural head; retrieval/anomaly route |
| Data regime | 1/5/10/25/100% labels; in-survey; cross-survey; temporal; OOD |
| Decision policy | Rank only; selective rank/abstain; random-audit mixture; no model score visible to reviewers |
| Detector | Current bank; robust null; background-calibrated covariance; campaign-level correction |

Use a fractional factorial screening stage to eliminate weak choices, then confirm
the few surviving variants with 5+ seeds and locked tests. Do not tune every cell
against the same final benchmark.

## Candidate research extensions

These are useful hypotheses, not committed scope.

1. **Self-supervised pretraining at scale:** pretrain on unlabeled, provenance-safe
historical curves; test transfer across survey and task. FALCO, ASTROMER, AstroCo,
and StarEmbed make this a timely comparison space, but most evidence is still
preprint/benchmark-specific and should be reproduced rather than trusted by name.[2][3][4][5]
2. **Physics-aware but not physics-pretending representations:** add passband
response, redshift/extinction/host context only when measured and versioned; use
physics as soft constraints or auxiliary tasks, not labels inferred from flux alone.
3. **Generative simulation-to-real calibration:** use a survey-aware simulator for
stress and representation pretraining; adversarially measure simulator gap with
held-out real backgrounds before relying on synthetic ranking results.
4. **Active learning with audit protection:** choose some follow-up actions for
expected information gain while reserving randomized audit candidates to retain
identifiability of performance.
5. **Conformal/selective decisions:** construct prediction sets or abstention rules
with empirical coverage/risk monitoring under time/survey shift. Coverage must be
measured on the operational population, not assumed from IID theory.
6. **Multimodal artifact triage:** use cutouts and image-quality metadata primarily
to detect artifacts and provenance conflicts, with late fusion so image failure can
cause abstention without erasing light-curve evidence.
7. **Human-AI interaction experiment:** randomize whether and how scores,
explanations, and analogs are shown. The objective is improved independent review,
not higher agreement with the system.

## Sequenced plan

### Phase 0 — Make the artifact executable (0--4 weeks)

- [ ] Repair/reproduce the current SQLite verification failures on adequate
  temporary storage; obtain a clean release bundle for the exact commit.
- [ ] Freeze C01--C05 and design the prospective campaign, label taxonomy, and
  audit allocation with scientific owners.
- [ ] Implement D01--D05 and DS01--DS04 before adding model complexity.
- [ ] Establish the baseline harness and complete E01--E08 scaffolding.

### Phase 1 — Retrospective evidence (1--3 months)

- [ ] Build real, point-in-time historical snapshots with group/time splits,
  denominator documentation, and real negative controls.
- [ ] Qualify at least one live/broker adapter through approved capture/replay.
- [ ] Execute the baseline suite, detector stress matrix, and minimal JEPA
  comparator/ablation screen; publish all null and adverse results.

### Phase 2 — Prospective shadow campaign (3--9 months)

- [ ] Freeze models and thresholds; run without influencing reportability.
- [ ] Preserve all arrivals, propensity, reviewer events, service state, and mature
  independent outcomes.
- [ ] Compare methods at identical review and follow-up budgets; conduct blinded
  error review and independent scientific audit.

### Phase 3 — Assisted prioritization (only after Phase 2)

- [ ] Permit the proven model to order an explicitly bounded review queue while
  retaining random audit, abstention, human vetoes, evidence gates, drift alarms,
  rollback, and immutable change control.
- [ ] Continue prospective monitoring. A model that degrades under new cadence,
  survey, or label distributions returns to shadow mode.

## Research readiness definition

SIDEREA is ready for a limited scientific claim only when all of the following
exist: a clean reproducible release; a frozen point-in-time cohort and full
denominator; calibrated measurement/provenance contract; strong equal-resource
baselines; group/time/OOD evaluation; prespecified uncertainty and multiplicity;
independent labels; real-background detector calibration; a prospective shadow
campaign; and independent scientific review. It remains a human-supervised
decision-support system even then: no learned score substitutes for evidence,
catalogue checks, or expert judgment.

## Sources

1. Assran et al. (2023), [Self-Supervised Learning from Images with a Joint-Embedding Predictive Architecture](https://arxiv.org/abs/2301.08243). The JEPA source paper motivates large targets and informative context; it does not validate count-based masking for irregular astronomical time series.
2. Donoso-Oliva et al. (2022), [ASTROMER: A transformer-based embedding for the representation of light curves](https://arxiv.org/abs/2205.01677).
3. Zuo et al. (2025), [FALCO: a Foundation model of Astronomical Light Curves for time dOmain astronomy](https://arxiv.org/abs/2504.20290). Preprint; results are task/data specific.
4. Tan et al. (2025), [ASTROCO: Self-Supervised Conformer-Style Transformers for Light-Curve Embeddings](https://arxiv.org/abs/2509.24134). Preprint; use as a comparator hypothesis, not settled evidence.
5. Li et al. (2025), [StarEmbed: Benchmarking Time Series Foundation Models on Astronomical Observations of Variable Stars](https://arxiv.org/abs/2510.06200). Preprint benchmark on ZTF variable-star tasks.
6. Chiong, Becker, and Protopapas (2025), [Multivariate Time-series Transformer Embeddings for Light Curves](https://arxiv.org/abs/2506.11637). Preprint reporting multiband-fusion gains on its stated data/tasks.
7. Fraga et al. (2024), [Transient Classifiers for Fink: Benchmarks for LSST](https://arxiv.org/abs/2404.08798). Uses ELAsTiCC simulations and explicitly notes adaptation needed for Rubin operations.
8. Yue et al. (2021), [TS2Vec: Towards Universal Representation of Time Series](https://arxiv.org/abs/2106.10466). A general time-series contrastive baseline family.
9. Patel et al. (2024), [EMIT: Event-Based Masked Auto Encoding for Irregular Time Series](https://arxiv.org/abs/2409.16554). Irregular-series masking idea from a non-astronomy domain; requires astronomical validation.
10. Pruzhinskaya et al. (2024), [Anomaly Detection and Approximate Similarity Searches of Transients in Real-time Data Streams](https://arxiv.org/abs/2404.01235). A real-time anomaly/retrieval comparator and operational case study.
11. Rubin Observatory, [Early Science Program](https://rubinobservatory.org/for-scientists/resources/early-science) and [Technical Documentation](https://rubinobservatory.org/for-scientists/documentation/tech-docs). Current product availability and early-data context.
12. Rubin Observatory, [RDO-013 Data Policy](https://docushare.lsst.org/docushare/dsweb/Get/RDO-013). Access and redistribution constraints for alert and prompt products.
13. Kessler et al. (2018), [The Photometric LSST Astronomical Time-series Classification Challenge data set](https://arxiv.org/abs/1810.00001), and Malz et al. (2018), [PLAsTiCC metric selection](https://arxiv.org/abs/1809.11145). Useful controlled benchmarks, not a substitute for a prospective real-stream cohort.
