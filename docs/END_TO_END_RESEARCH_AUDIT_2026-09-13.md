# End-to-End Research Audit of SIDEREA / I SPY

**Audit date:** 2026-09-13  
**Audited checkout:** `3e4451fc76809aad8bb4eb0f76defe9e2e2edabf`, with a materially dirty working tree  
**Reviewer stance:** scientific, mathematical, machine-learning, reproducibility, software-engineering, and top-conference review  
**Scope:** tracked and untracked source, tests, configurations, manuscript source/PDF, experiment archives, generated outputs, documentation, CI, packaging, and a fresh local execution audit.

**Remediation update:** the benchmark-binding defect, duplicate CLI handlers, test-extra
dependency mismatch, closest-work citation gap, and contradictory historical wording were
repaired after this audit. A complete development-mode release verification then passed.
Subsequent remediation also added a paired whole-time-block bootstrap, a machine-valid
but unmistakably unfrozen prospective-study draft, and an external evidence intake
contract.
See `docs/AUDIT_REMEDIATION_STATUS_2026-09-13.md` for the post-audit state; the findings
below preserve what the audit observed before those repairs.

## 1. Executive verdict

SIDEREA is **not a fake or pseudocode repository**. Its main evidence-governance system is a substantial, typed implementation with unusually good fail-closed behavior: immutable candidate versions, content digests, freshness-bound external evidence, append-only decisions, authenticated review records, atomic artifact writes, explicit reportability predicates, deterministic replay, and a review-budget queue are all implemented and extensively tested. The manuscript is also notably honest: it calls the detector experiments synthetic, the JEPA results smoke tests, the historical policy comparison confounded, and the historical campaign incomplete.

The strongest and most defensible contribution is therefore **a compact, evidence-bound decision contract for human-supervised transient triage**, not a new transient detector, classifier, or astronomical discovery result. This is a meaningful software/process contribution, but it overlaps substantially with the provenance, replay, evolving information-state, and human-review concerns already addressed by systems such as AMPEL, ALeRCE/SN Hunter, ANTARES, Fink, Lasair, and BTS. The narrower novelty is the particular binding of candidate version, evidence freshness/failure state, permitted report wording, and exact human approval into a fail-closed local record. That can support a software, methods, or operations paper after evidence reconciliation and release hardening. It is not presently a strong algorithmic novelty claim.

The detector and ML paths are **real but scientifically unvalidated**. The template bank and Monte Carlo testing are mathematically coherent under their stated null, and the irregular-time JEPA is a genuine EMA-target representation learner. However, the detector's checked-in recovery study is a matched-template synthetic diagnostic, while its own noise stress tests show severe false-alarm inflation under plausible misspecification. The JEPA archive contains two training and two validation entities and cannot establish representation quality. A June 2026 paper already studies an astronomy-specific JEPA on real benchmarks, making the missing direct citation and comparison especially important ([Rui 2026](https://arxiv.org/abs/2606.28446)).

The repository is **not conference-ready in its current checkout**. The principal blockers are: (1) the historical 3,824-object cohort and primary registry/submission evidence are absent, so major historical counts and both designation claims cannot be independently reconstructed; (2) the current tree is unfrozen and heavily modified, with the final PDF not bound to a clean revision; (3) current CI semantics are broken because `.[dev,ml]` omits Matplotlib although archive tests import it; (4) MyPy fails on duplicate CLI definitions; and (5) `bind_benchmark` drops `time_block_days` during recomputation, preventing correct binding of explicitly binned benchmarks. A fresh isolated reconstruction of the **synthetic** experiments passed, but explicitly does not reconstruct live science.

**Conference assessment:** reject as a top-tier ML/astronomy performance paper; weak reject in current form as a reproducibility/software paper because the empirical historical record and release identity remain incomplete; potentially acceptable after P0/P1 work for a software, workflow, or domain-methods venue. The architecture is promising and the claim discipline is better than the empirical foundation.

## 2. Audit method and fresh evidence

I inspected the canonical `src/siderea` package, all test modules, root and package configuration, workflow files, manuscript source and bibliography, historical operations record, experiment protocols/results/trial statistics, reconstruction tooling, and generated PDF. I rendered all 29 PDF pages and inspected a contact sheet for clipping, missing figures, and layout failures. The PDF is visually complete and consistent, although dense, untagged, and likely too long for many conference formats.

Fresh execution produced the following results:

| Check | Result | Interpretation |
|---|---:|---|
| `.venv/bin/python -m pytest -q` | 480 passed, 100 subtests, 10 failed | Eight failures are real dependency-contract failures: archive runners import Matplotlib, but the tested `dev` environment lacks it. Two HTTP failures were caused by the audit sandbox denying loopback sockets. |
| HTTP tests with loopback permission | 3 passed | The review HTTP failures are environmental, not application defects. |
| Ruff lint | passed | Canonical source, tests, reconstruction, experiments, and figure generator pass. |
| Ruff format check | 120 files formatted | Formatting is clean for the audited paths. |
| MyPy on `src/siderea` | 2 errors | Duplicate `_command_transient_shard` and `_command_transient_merge` definitions in `src/siderea/cli.py`. |
| Fresh `paper/reconstruct.py` run | passed | Reproduced historical figures and synthetic IID, supplied-covariance, noise-stress, and table artifacts in an isolated copied workspace. Scope is explicitly `historical_figure_and_synthetic_reconstruction_not_live_science`. |
| `pip check` in `.venv` | unavailable | The environment has no `pip` module; this is environment hygiene, not proof of a dependency conflict. |

Older archived reports claiming fully passing suites are evidence about earlier snapshots, not this checkout. The current commit is `3e4451f`, while many critical modules, tests, paper files, and the final PDF are modified or untracked. Reusing earlier pass counts as current release evidence would be invalid.

## 3. Component classification

The labels below use the requested vocabulary. “Complete/real” means executable substantive code, not that its scientific validity is complete.

| Component | Classification | Evidence and scope |
|---|---|---|
| Core domain, state, identity, provenance, atomic I/O (`src/siderea/domain.py`, `state.py`, `identity.py`, `provenance.py`, `atomic.py`, `manifest.py`) | **complete/real** | Typed records, canonical serialization, content digests, state transitions, collision checks, and atomic replacement are exercised by core, identity, ledger, and reproducibility tests. |
| Ingestion (`src/siderea/ingest/*`, `data/snapshot.py`) | **complete/real**, **partial** for survey coverage | CSV, snapshot, schema, and ALeRCE paths are implemented. Real current broker acquisition was not executed in this audit; multi-survey units/calibration contracts are missing. |
| Photometry/features/legacy scoring (`features/photometry.py`, `scoring/*`, `bands.py`) | **complete/real**, **hardcoded shortcut** | Feature computation and legacy/current heuristic scores execute. Thresholds and weights are hand-set rather than learned or externally calibrated; legacy score includes batch-relative time. |
| Pipeline and campaign orchestration (`pipeline.py`, `campaigns.py`, `followup.py`, `host.py`) | **complete/real**, **partial** | Substantive orchestration exists. No tracked representative live campaign demonstrates current end-to-end behavior. |
| External clients (`clients/base.py`, `catalogs.py`, `tns.py`) | **complete/real**, **untested** live | Retry/error/freshness and read-only lookup behavior are tested with transports/fixtures. Current live service correctness, schema drift, credentials, rate limits, and image/WCS paths are not established. |
| Evidence binding and report preflight (`evidence_context.py`, `reporting/preflight.py`, `integrity.py`) | **complete/real** | Missing, failed, stale, malformed, or wrong-version evidence fails closed. This is the most mature scientific-safety component. |
| Ledger and review (`ledger.py`, `review/*`) | **complete/real**, **partial** identity assurance | Versioned/append-only decisions, dossier assembly, metrics, and HTTP review work. HMAC authentication is local integrity/authentication, not an institutional identity provider or key-custody solution. |
| Ranking, anomaly, similarity (`ranking.py`, `anomaly.py`, `similarity.py`) | **complete/real**, **hardcoded shortcut**, **untested** scientifically | Deterministic allocation, robust feature anomaly scores, optional Isolation Forest, and embedding similarity execute. Thresholds and utility are not validated on a held-out sky cohort. |
| Logistic baseline (`ml/baseline.py`) | **complete/real**, **partial**, **untested** scientifically | Median imputation with indicators, scaling, class weights, chronological partitions, entity purge, optional held-out sigmoid calibration, and trusted-load guard are implemented. Checked-in data are tiny smoke fixtures, not a credible baseline result. |
| JEPA dataset/token contract (`ml/dataset.py`) | **complete/real**, **partial** | Deterministic irregular-time tokens, context-only normalization, missingness/error handling, hashes, and bounded vocabulary are implemented. Unknown filters collapse together and survey identity/calibration are absent. |
| JEPA model/training/evaluation (`ml/jepa.py`, `train.py`, `evaluate.py`) | **complete/real**, **partial**, **untested** scientifically | Transformer encoder, masked context, EMA target, predictor, Smooth-L1 latent loss, checkpointing, collapse diagnostics, and deterministic smoke training execute. The archive has only 2 train/2 validation entities; no downstream held-out utility, scaling, or strong baseline comparison exists. |
| Transient template search (`research/transients.py`) | **complete/real**, **partial** | Positive-amplitude generalized least-squares template bank, floating constant, optional supplied covariance, plus-one Monte Carlo p-values, and multiplicity fields are real. The null/noise/campaign model is not learned or validated on real residuals. |
| Injection diagnostic (`research/injection.py`) | **complete/real**, **hardcoded shortcut**, **partial** | Injects known Gaussian pulses into fixed residual curves and reports Wilson intervals. Injection and recovery use the same family and known center/width; no new noise realization or end-to-end selection is included. The module correctly labels itself non-population validation. |
| Preregistration/cohort (`research/preregistration.py`, `cohort.py`) | **complete/real** infrastructure, **missing** executed study | Protocol freezing, enrollment, maturity, explicit outcomes, and missingness rules exist. No representative frozen real cohort is included. |
| Rolling benchmark (`research/benchmark.py`) | **complete/real**, **partial** statistics | Time-blocked evaluation, tie-aware top-K metrics, bootstrap intervals, and reproducible inputs exist. Scores are supplied rather than trained under enforced cutoffs; entity-within-fold bootstrap is conditional on observed nights. |
| Benchmark binding (`research/qualification.py`) | **broken** | `bind_benchmark` reconstructs from `evaluation_inputs` but omits `time_block_days`, so explicitly binned results cannot be faithfully rebound. |
| Promotion (`promotion.py`) | **complete/real**, **partial**, **hardcoded shortcut** | Gates bind cohort, benchmark, matched-filter diagnostic, reviews, assets, broker archive, and incidents. “Recorded service fixture coverage” trusts fixture metadata and does not execute adapters; passing means local evidence readiness, not deployment validity. |
| Operations (`operations/assets.py`, `backup.py`, `broker_store.py`, `fixtures.py`, `observability.py`, `qualification.py`, `recovery.py`) | **complete/real**, **partial** operational proof | Real integrity, archive, dead-letter, backup/recovery, and observability code with tests. Live-service and disaster-recovery rehearsals are not evidenced for the target deployment. |
| Integrated pilot and overnight tooling (`research/pilot.py`, `research/overnight.py`, `scripts/overnight-shadow-pilot.sh`, `docs/PILOT_RUN.md`) | **partial**, **untested** end to end | Integration and sharding code plus targeted tests exist; the shell orchestration is untracked and has no completed representative overnight run. Required real inputs and services are absent. |
| CLI (`cli.py`, `__main__.py`) | **complete/real**, **broken**, **unused/dead** section | Broad command surface is implemented and tested, but duplicate transient shard/merge function definitions break MyPy; the earlier pair is shadowed dead code. |
| Configurations (`configs/*.toml`, `src/siderea/default.toml`) | **complete/real**, **partial** | Parsed and validated. JEPA production config points to data not present; scientific thresholds remain uncalibrated. |
| Example data (`examples/*.csv`, `examples/*.jsonl`) | **placeholder/stub/mock** for scientific evidence | Useful executable fixtures, including tiny JEPA and integrated-pilot examples. They are synthetic/demo inputs and cannot support claims. |
| Historical raw data, complete candidate cohort, labels, broker snapshots, TNS correspondence | **missing** | Data availability text and checklist acknowledge these are not tracked. The 3,824-object funnel cannot be independently replayed object by object. |
| Paper synthetic runners and archives (`paper/experiments/*`) | **complete/real** synthetic evidence | Protocols, seeds, source snapshots, trial statistics, digests, plots, and tables reconstruct successfully. Matched/supplied-model scope limits inference. |
| Learning smoke archive (`paper/experiments/learning-smoke-results.json`) | **complete/real** smoke, **placeholder/stub/mock** as research result | Explicitly says synthetic execution smoke only; sample size is scientifically negligible. |
| Historical figures (`paper/figures/*`) | **complete/real** transformation, **partial** provenance | Figures regenerate from surviving summary records. They cannot recover missing row-level primary records. |
| Reconstruction (`paper/reconstruct.py`, `research/archives.py`) | **complete/real**, **partial** scope | Fresh reconstruction passed in a copied workspace and detects semantic/digest drift. It excludes live data and model training by design. |
| Manuscript source/PDF (`paper/siderea_transient_triage.tex/.pdf`) | **complete/real**, **partial** submission readiness | A coherent 29-page paper with clear caveats and visually intact output. Revision is unfrozen; primary evidence and direct 2026 JEPA comparison are missing; venue/author/license gates remain open. |
| Final checklist and evidence ledgers (`paper/FINAL_PAPER_CHECKLIST.md`, `paper/research/*`) | **complete/real** audit records, **partial** completion | They candidly identify open items. Multiple P0/P1 items remain unchecked, including revision freeze, campaign reconciliation, designation verification, release, and real-data evaluation. |
| Root legacy scripts and `cool-stuff-master/` | **unused/dead**, **hardcoded shortcut**, **untested** | Quarantined/excluded from canonical Ruff scope; duplicate historical workflow with hardcoded assumptions. It is context, not supported product code. |
| Tests (`tests/*`) | **complete/real**, **partial** coverage | Broad invariant and failure-path coverage. Missing tests allowed the `time_block_days` binding defect and duplicate CLI definitions; many integrations are mocks/fixtures. |
| CI (`.github/workflows/ci.yml`) | **broken** on current tree | Quality, test, security, and package jobs are well structured, but the test job installs `.[dev,ml]`; archive tests import Matplotlib, which only visualization/all declares. MyPy also currently fails. |
| Packaging/licensing (`pyproject.toml`, `MANIFEST.in`) | **partial**, **broken** release contract | Wheel/sdist checks exist. `LicenseRef-Proprietary` is declared but no repository license text was found; publication/reuse and data terms are unresolved. |
| Unattended TNS submission and physical classification | **missing** deliberately | The system stops before submission and does not infer spectroscopic class. This is a safety boundary, not an accidental implementation omission, but claims must retain it. |

## 4. Scientific idea and novelty

### Hypothesis, claim, and actual contribution

The implicit operational hypothesis is: **binding each decision to an immutable candidate version and explicit fresh evidence states reduces unsafe or irreproducible report preparation while allocating scarce human review attention.** The paper's explicit claim is narrower: it presents that contract, audits a historical campaign that motivated it, and verifies software invariants. The actual implemented contribution matches that narrow claim.

What is not established is the causal part of the hypothesis: there is no prospective comparison showing fewer erroneous submissions, better reviewer agreement, faster decisions, higher top-K yield, or lower risk than an ordinary broker filter plus checklist. The historical system predates many current safeguards, and policy/time/population changed together. Software tests prove logical enforcement, not real-world benefit.

### Closest prior work

AMPEL is the closest systems-level comparator because it already emphasizes provenance, replay, user-defined analysis, and changing information states, and it evaluated over 200 selection functions on archived ZTF alerts ([Nordin et al. 2019](https://arxiv.org/abs/1904.05922)). ALeRCE is a production broker with ingestion, crossmatching, ML classification, visualization, and large-scale real alert results ([Förster et al. 2020](https://arxiv.org/abs/2008.03303)); its light-curve classifier was trained and evaluated on real labeled data ([Sánchez-Sáez et al. 2020](https://arxiv.org/abs/2008.03311)). SIDEREA is much smaller and downstream, but its exact evidence-to-permitted-action binding is more explicit.

For anomaly triage, AHA evaluates three modalities on a 5,294-object labeled dataset and a 25-day live stream, with top-rank review and manual follow-up ([Iskandarli et al. 2026](https://arxiv.org/abs/2602.12955)). SIDEREA's separate queue routes are compatible with this idea but have no comparable empirical evaluation. For self-supervised light curves, ASTROMER pretrained on millions of sequences and showed downstream gains ([Donoso-Oliva et al. 2022](https://arxiv.org/abs/2205.01677)); AstroCo reports multi-seed downstream comparisons and GPU-scale training ([Tan et al. 2025](https://arxiv.org/abs/2509.24134)); StarEmbed supplies about 40,000 expert-labeled curves and standardized clustering/classification/OOD tasks ([Li et al. 2025](https://arxiv.org/abs/2510.06200)). Most importantly, Rui (2026) directly applies domain-informed JEPA/self-distillation to astronomical light curves and evaluates on LEAVES, StarEmbed, and PYRREGULAR ([Rui 2026](https://arxiv.org/abs/2606.28446)). That work is absent from the bibliography and makes any astronomy-JEPA novelty claim untenable without direct differentiation.

The meaningful novelty is thus **contract composition and safety semantics**, not the heuristic score, template search, anomaly model, transformer, JEPA objective, or human review itself. The paper should include a feature-by-feature comparison table against AMPEL and operational review systems, and treat the ML path as an application/extension rather than a contribution until benchmarked.

## 5. Mathematics and scientific validity

### Verified formulations

1. **Legacy amplitude and significance.** `A = m_med - m_peak` is positive for brightening in magnitudes and is dimensionless in the conventional logarithmic magnitude scale. Dividing by the quadrature magnitude uncertainty gives a dimensionless heuristic significance. This is not a likelihood-ratio statistic because the median's uncertainty, intrinsic variability, covariance, censoring, and selection of the peak are ignored.

2. **Current heuristic score.** A weighted sum of bounded feature maps remains bounded when nonnegative weights sum to one. The implementation is transparent and deterministic. It has no probabilistic interpretation, calibration guarantee, or optimality result.

3. **Fail-closed reportability.** The reportability condition is a conjunction of binary predicates. Adding a required predicate can only shrink the accepted set; the paper's monotonicity proposition is correct. It is a tautological property of the chosen Boolean contract, not proof that inputs, catalogs, human judgments, or astrophysical conclusions are correct.

4. **Template-bank statistic.** The code whitens observations under diagonal errors or a supplied positive-definite correlation matrix, projects templates away from the whitened constant, and maximizes the one-sided normalized correlation. This is a valid positive-amplitude generalized least-squares score with a fitted constant under the supplied Gaussian covariance model. Explicit condition checks and a bounded bank reduce numerical failure risk.

5. **Monte Carlo p-values.** `(1 + number(null >= observed))/(B + 1)` is a valid conservative randomization/Monte Carlo p-value under exchangeability with the simulated null. Computing the maximum over the full bank within each null draw correctly incorporates template search. Bonferroni channel/object/look multipliers are valid family-wise controls when the declared family is complete, although conservative.

6. **Tie-aware ranking metrics.** Grouping average precision by score ties and assigning expected positives at a top-K cutoff tie avoids dependence on arbitrary row order. Brier score is proper for genuinely probabilistic predictions; the implementation appropriately requires an explicit calibration attestation.

7. **Prospective estimators.** The proposed Hájek inverse-probability estimator, Kaplan-Meier treatment of delayed outcomes, and paired non-inferiority framing are standard coherent choices. They are plans, not results, and require positivity, correct inclusion probabilities, independent outcome ascertainment, and a prespecified uncertainty unit.

### Invalid or weak inferences to avoid

- **Batch-relative legacy score:** the recency term uses a batch maximum time, so an object's score can change when unrelated objects enter the batch. It is an operational priority, not a stable object property.
- **Multiplicity resolution:** with `B=999`, the smallest p-value is 0.001. After channel and campaign corrections, many nominal 0.01 decisions are impossible to resolve. Trial counts must be chosen from the full multiplicity denominator before execution; the overnight documentation's larger count is more credible.
- **Noise model:** the optional covariance is supplied, not estimated. The synthetic OU-like mixture is only one correlated process. Heavy tails, isolated outliers, underestimated errors, nonstationarity, subtraction artifacts, and cadence-dependent systematics invalidate Gaussian-null calibration, as the archived adverse tests demonstrate.
- **Injection optimism:** signal and recovery template match, location/width are known, and injections reuse fixed residual backgrounds without drawing new measurement noise. Wilson intervals quantify conditional Monte Carlo trial variation, not population generalization or full-pipeline completeness.
- **Bootstrap scope:** the rolling benchmark resamples entities within observed folds. It does not capture between-night variation, acquisition-policy uncertainty, label adjudication, or model-training randomness. A hierarchical/night-block or repeated-period analysis is needed depending on the estimand.
- **Precomputed scores:** the benchmark cannot itself prove that score fitting, normalization, calibration, and model selection used training data only. Model artifacts and training-cutoff digests must be bound.
- **JEPA objective:** predicting target representations with an EMA teacher is coherent, but low latent loss does not imply anomaly usefulness. Mean pooling can dilute brief transients; per-token normalization can remove amplitude information; the fixed band vocabulary can conflate cross-survey semantics. These require ablations and downstream evaluation.
- **Queue optimization:** the additive expected-value formulation assumes separable candidate utility and known/estimable review value. Reviewer fatigue, diversity, correlated candidates, and information gained from one candidate about another violate this abstraction.

No dimensional inconsistency was found in the implemented template statistic or reported magnitude heuristics. The deeper issue is not algebraic error but the gap between conditional model validity and real-sky inference.

## 6. Data, experiments, and evaluation

### Data audit

The repository has executable synthetic/example inputs but no complete raw historical cohort. Provenance for the public ZTF/ALeRCE ecosystem is described, yet acquisition timestamps, raw responses, full rejected population, object aliases, image cutouts, catalog snapshots, outcome evidence, and TNS submission correspondence are missing for the reported campaign. The manuscript correctly says that live outputs and cached curves are unavailable, but that means stage counts, denominators, duplication corrections, and case-study attributes remain summary-attributed.

The operations record is internally inconsistent in presentation: it reports two submitted/designated objects and 0.052% selectivity (`PIPELINE_OPERATIONS_RECORD.md:91,139`), then its “defensible claims” section says one confirmed discovery and 0.026% (`:237-242`). The manuscript handles this more carefully by distinguishing two summary-attributed designations from one detailed surviving narrative (`paper/siderea_transient_triage.tex:532-540`), but neither designation is independently verified in tracked primary evidence. “Confirmed discovery” is especially unsafe wording because TNS designation is not physical classification and attribution is unresolved.

No license inventory is provided for reconstructed broker/catalog records, figures, or future released data. There is no evidence of contamination screening between any future pretraining corpus and downstream evaluation. Survey passbands, zero points, time standards, upper limits, forced versus alert photometry, and cross-survey filter identity need explicit versioned contracts before multi-survey learning.

### Experiment audit

The synthetic detector work is reproducible and commendably includes adverse results. It tests implementation behavior and null sensitivity, not the operational hypothesis. The strongest missing control is injection into frozen real difference-photometry residuals with artifact/gap/error strata, followed by the entire acquisition, eligibility, scoring, review, and outcome path.

The logistic and JEPA experiments are smoke tests. There is no fair, compute/parameter-matched comparison against heuristic ranking, logistic/gradient-boosted features, ASTROMER/AstroCo, general-purpose time-series embeddings, AHA-like modality autoencoders, or the 2026 astronomy JEPA. There are no multi-seed real-data results, learning curves at meaningful scale, hyperparameter protocol, architecture ablations, calibration curves, subgroup analysis, or held-out later period.

The historical July 5 pre/post comparison is appropriately described as confounded. It does not identify a causal policy effect. The 24 productive runs are not a randomized or stationary sample; failed API runs, targeted intake, repeat objects, and changing policy preclude population estimates.

### Evaluation audit

Precision/recall at fixed review budget, average precision, top-K expected positives under ties, Brier score, and ECE are implemented sensibly for one row per entity. The principal problem is not metric code but absent representative labels and weak uncertainty. Accuracy should remain secondary under severe imbalance. Report PR curves/PR-AUC, recall at K, precision at K, workload, time-to-decision, false-report preparations, abstention/censoring, reviewer disagreement, and calibration only where probabilities are genuinely calibrated. Use paired entity-level comparisons on the same test cohort and report confidence intervals whose resampling unit matches deployment variation (at least nights/blocks, with training seeds nested where relevant).

## 7. Paper audit and claim trace

| Paper claim/component | Verdict | Evidence/action |
|---|---|---|
| Abstract's evidence-bound workflow claim | Supported | Directly implemented and broadly tested. Keep. |
| 24 runs / 3,824 objects / stage counts | Summary-supported only | Derived from surviving operations summary/figures, not reconstructible raw cohort. Label as attributed archival counts everywhere. |
| Two submitted/designated objects | Not independently verified | Paper already qualifies this. Add primary TNS/archived evidence or remove from quantitative headline. |
| One detailed AT 2026rsp narrative | Partial | Narrative exists; row photometry and submission artifacts do not. Do not call spectroscopically confirmed or independently credited. |
| Policy discontinuity | Descriptive only | Time, policy, and population are confounded; current wording is appropriate. |
| Software invariants | Supported for specific snapshots | Fresh current suite is not fully green. Bind exact source tree, environment, command, and results. |
| Synthetic detector recovery | Supported conditionally | Reconstructed; valid only under matched/supplied noise and templates. Keep adverse null results adjacent. |
| JEPA numerical operation | Supported as smoke | Tiny archive proves execution only. No representation or discovery claim. |
| Comparative performance | Missing | Abstract/conclusion correctly disclaim it. Do not imply competitiveness elsewhere. |
| Related work | Good but incomplete | Add direct Rui 2026 astronomy-JEPA comparison and a feature-level AMPEL/SIDEREA distinction. Verify every bibliography entry against primary metadata. |
| Methods/equations | Mostly correct | Clearly separate implemented equations, historical formulas, conceptual decision theory, and future estimators. |
| Figures/tables | Visually sound, provenance partial | Synthetic figures reconstruct. Historical figures inherit summary-data limitations. Add accessible text/metadata and venue-sized versions. |
| Limitations/data availability | Strong and candid | Preserve. Make the lack of object-level reconstruction prominent in abstract/table notes if historical numbers remain. |
| Submission readiness | Not established | The repository's own final checklist leaves revision, data, bibliography, release, license, venue, and author approval open. |

## 8. End-to-end reproducibility trace

| Stage | Status | Reproducibility break |
|---|---|---|
| Raw alert/broker acquisition | **missing** historical; **partial** current client | No complete frozen raw responses, acquisition manifest, or accessible campaign cache. |
| Preprocessing and identity | **complete/real** code | Historical inputs unavailable; current cross-survey/unit contract incomplete. |
| Split/cohort freeze | **complete/real** infrastructure; **missing** study | No representative preregistered cohort with full eligible/rejected/unreviewed population. |
| Training | **complete/real** code; **placeholder** evidence | Only tiny example/smoke data; no real pretrained checkpoint or multi-seed training archive. |
| Checkpoint/provenance | **complete/real** | Hashing and token-contract binding are good; no scientifically qualified checkpoint exists. |
| Inference/ranking | **complete/real** | No prospective deployment archive showing stable behavior under actual stream conditions. |
| External evidence | **complete/real** contract; **untested** live | Fixtures and simulated transports do not prove present live schema/service behavior. |
| Evaluation | **complete/real** metrics; **missing** labels | No independent representative test labels or complete outcome handling. |
| Plots/tables | **complete/real** synthetic; **partial** historical | Synthetic reconstruction passed; historical plots originate from incomplete summaries. |
| Paper result | **partial** | PDF builds and synthetic semantics reproduce, but current PDF/source/code are not a frozen clean release and live/historical science does not reconstruct. |

The honest reproducible chain today is **synthetic protocol → synthetic trials → detector metrics → plots/tables**, plus **example data → smoke training/inference**. The requested real chain **raw sky data → complete cohort → trained method → held-out outcomes → paper claims** is missing.

## 9. Critical findings

| Severity | File/component | Problem and evidence | Scientific impact | Exact fix |
|---|---|---|---|---|
| P0 | Historical campaign/data | No row-level 3,824-object cohort, full rejected population, primary registry records, or submission artifacts; checklist B01/B02/B04/B05 remains open. | Historical denominators and outcomes cannot be independently verified; no false-negative/completeness claim is possible. | Recover and checksum permitted raw records, or narrow every claim to “surviving summary attributes”; publish a claim-source ledger with field-level provenance. |
| P0 | Release identity | Dirty tree includes modified code, tests, paper, and PDF plus untracked core modules; paper checklist A04/G03 is open. | No reviewer can identify which code produced the submitted artifact; prior test counts are stale. | Freeze a clean commit/tag, build from an exported source archive, record dependency lock, commands, input/output digests, and archive DOI. |
| P0 | Scientific performance claim boundary | No representative real cohort, independent outcomes, or held-out end-to-end evaluation. | Any claim that SIDEREA improves discovery, ranking, or classification would be unsupported. | Keep current narrow claim, or execute preregistered real-data study with complete eligibility, outcomes, matched baselines, and later-period test. |
| P1 | `src/siderea/research/qualification.py:162-174` | `bind_benchmark` omits `time_block_days` when reproducing the benchmark. | Valid binned benchmark evidence can fail binding or be recomputed under a different temporal unit. | Pass `time_block_days=inputs["time_block_days"]`; add round-trip tests with singleton raw timestamps requiring explicit bins. |
| P1 | `src/siderea/cli.py:1743-1761,2050-2074` | Duplicate shard/merge definitions; later definitions shadow earlier; MyPy reports two redefinitions. | Current quality gate fails and behavior ownership is ambiguous. | Retain one implementation of each, add CLI output/byte-input regression tests, rerun MyPy. |
| P1 | `pyproject.toml:41-57`, `.github/workflows/ci.yml` | Test job installs `.[dev,ml]`, but archive tests import Matplotlib declared only in visualization/all; 8 fresh failures. | CI is expected to fail on current tree and cannot serve as release evidence. | Move Matplotlib to the relevant test extra or install `.[all,dev]` in test jobs; ensure experiment imports are lazy where plotting is optional. |
| P1 | `PIPELINE_OPERATIONS_RECORD.md:91,139,237-242` | Two-designation/0.052% and one-discovery/0.026% narratives conflict. | Encourages selective reporting and ambiguous numerator semantics. | Define `submitted`, `designated`, `credited`, `detailed`, and `classified`; verify each with primary evidence and use one table of noninterchangeable outcomes. |
| P1 | `paper/references.bib`, related work | Direct astronomy-JEPA work from June 2026 is absent. | Weakens novelty assessment and risks rediscovery/priority criticism. | Cite and compare Rui 2026 on objective, data, views, regularization, baselines, scale, and downstream results. |
| P1 | Injection/detector evidence | Same-family known-location injection into fixed residuals; supplied covariance; adverse misspecification results. | Recovery intervals are optimistic and do not estimate operational completeness or real false-alarm rate. | Inject blinded signals into frozen real residuals, include null artifacts/gaps/error strata, rerun full selection, and report recovery and false alarms jointly. |
| P1 | JEPA evidence | Two training and two validation entities; no real benchmark or useful checkpoint. | No evidence that embeddings improve top-K discovery or even preserve relevant transient morphology. | Train on a versioned real corpus, compare against strong astronomy/general baselines, use multiple seeds, later-period test, pooling/view/loss ablations, and downstream queue metrics. |
| P1 | Live qualification/promotion | Fixture gate checks labels/status metadata rather than executing adapter/parser behavior; no current live service proof. | “Promoted” could be misread as deployment/scientific readiness. | Rename status to local-evidence readiness; add scheduled read-only contract tests, archived responses, schema assertions, and explicit expiry. |
| P1 | Licensing | `LicenseRef-Proprietary` with no found repository license text; data/figure rights unresolved. | External reviewers cannot determine legal reproducibility or reuse. | Add authoritative LICENSE/data-use statements and third-party asset/data inventory before release. |
| P2 | Benchmark uncertainty | Entity bootstrap within folds conditions on observed nights and supplied scores. | Intervals understate operational and training variation. | Bind model/training artifacts and cutoffs; use paired block/night bootstrap or hierarchical resampling plus multiple training seeds. |
| P2 | Cross-survey token semantics | Unknown filters collapse; survey identity, zeropoint, time-system, forced-photometry semantics absent. | Embeddings can learn incompatible numeric meanings or distribution artifacts. | Version a survey/passband/unit schema, separate unknown categories, calibrate flux/time, and test leave-survey-out transfer. |
| P2 | Paper/PDF | 29 dense, untagged pages; final venue not frozen. | Readability, accessibility, and venue compliance risk. | Confirm venue, shorten main text, move protocols to supplement, tag PDF/add alt text, and visually recheck every final page. |

## 10. Missing research

- A preregistered, chronologically split, representative real-alert cohort preserving the complete eligible population, exclusions, aliases, unreviewed candidates, delayed outcomes, censoring, and adjudicator disagreement.
- Independent outcome evidence appropriate to each claim: image vetting for artifacts, registry evidence for novelty, and spectra or defensible labels for physical class.
- A direct safety-effect evaluation: stale/wrong-version/failed-evidence incidents, erroneous report preparations, reviewer disagreement, review time, and before/after or controlled comparator.
- Fair top-K comparisons against current heuristic, simple statistical significance, logistic and boosted-tree features, AHA-style modalities, ASTROMER/AstroCo, StarEmbed-tested general models, and Rui 2026 astronomy JEPA.
- Detector calibration on real residuals with blinded injections, empirical nulls, cadence/gap/host/signal strata, covariance estimation without leakage, robustness to heavy tails/outliers/error scaling, and campaign-wide repeated-look control.
- JEPA scaling curves, compute/parameter accounting, multi-seed uncertainty, representation collapse diagnostics at scale, view/mask/normalization/pooling/band ablations, nearest-neighbor audits, linear probes, OOD detection, and contribution to final review yield.
- Causal or quasi-experimental analysis of workflow changes; the existing historical discontinuity cannot identify effect.
- Sensitivity analysis for heuristic weights, veto radii, freshness windows, thresholds, review budgets, audit reserve, and missing-outcome policy.
- A threat model and human-factors study covering credential/key custody, reviewer independence, correlated errors, audit trail mutation, service compromise, and alert fatigue.
- Compute/memory/latency benchmarks at realistic Rubin-scale loads, including shard merge, archive growth, failure recovery, and cost per reviewed candidate.

## 11. Prioritized improvement checklist

### P0 — scientifically invalid or broken

- [ ] **WHAT:** Freeze the exact research object; current code/paper/PDF are a dirty mixture. **WHY:** results cannot be attributed to a revision. **HOW:** reconcile changes, commit/tag, export a clean archive, lock dependencies, record machine/seed/command/input/output digests. **WHERE:** repository root, `pyproject.toml`, paper manifest/reconstruction records, CI release job. **VERIFY:** clone/extract on a clean machine; hash matches; all release commands pass; rebuilt PDF and semantic experiment outputs match.
- [ ] **WHAT:** Reconcile or explicitly demote historical claims lacking primary data. **WHY:** 3,824-object accounting and designation yields are not independently reproducible. **HOW:** recover permitted cohort/registry/submission records; otherwise rewrite all numbers as archival-summary attributions and remove “confirmed discovery.” **WHERE:** `PIPELINE_OPERATIONS_RECORD.md`, manuscript abstract/results/cases/conclusion, claim-source ledger. **VERIFY:** an independent reviewer can trace every number to immutable fields or sees an explicit unavailable marker.
- [ ] **WHAT:** Preserve the no-performance-claim boundary until a real test exists. **WHY:** synthetic recovery and tiny smoke runs cannot support astronomy/ML effectiveness. **HOW:** either keep the paper strictly as a software/audit paper or preregister and execute the study specified below. **WHERE:** title, abstract, contributions, results, conclusion, README. **VERIFY:** automated claim scan plus independent review finds no superiority/completeness/precision implication unsupported by real held-out outcomes.

### P1 — required for credible research

- [ ] **WHAT:** Fix benchmark temporal recomputation. **WHY:** evidence binding can change the analysis unit. **HOW:** forward `time_block_days` and validate it against preregistration. **WHERE:** `src/siderea/research/qualification.py`, `tests/test_research_qualification.py`. **VERIFY:** a benchmark with singleton raw timestamps and explicit daily bins round-trips byte/semantic-equivalently through binding.
- [ ] **WHAT:** Restore a green current quality/test gate. **WHY:** release evidence cannot rest on failing CI. **HOW:** remove duplicate CLI definitions; align Matplotlib/test extras; ensure optional plotting imports are scoped; install and run declared environments. **WHERE:** `src/siderea/cli.py`, `pyproject.toml`, `.github/workflows/ci.yml`, archive runners/tests. **VERIFY:** Ruff, MyPy, all Python matrix tests, compileall, pip check, security audit, sdist/wheel smoke, and paper reconstruction pass at the frozen revision.
- [ ] **WHAT:** Execute a preregistered real-data evaluation. **WHY:** this is necessary for any discovery/ranking claim. **HOW:** freeze eligibility/window/K/primary endpoint/effect size/missingness/stopping rule before outcomes; preserve all candidates and use independent labels. **WHERE:** `research/preregistration.py`, `cohort.py`, benchmark configs, released data manifest. **VERIFY:** protocol digest predates test outcomes; enrollment reconciles; no entity or temporal leakage; later-period results reproduce.
- [ ] **WHAT:** Compare strong baselines under identical information and review budgets. **WHY:** current novelty/effectiveness is unknown. **HOW:** fit only on training history; compare heuristic, GLS, logistic, boosted features, ASTROMER/AstroCo/general TSFM, AHA-like modality models, and Rui-style JEPA where licenses allow. **WHERE:** new versioned experiment package and `research/benchmark.py`. **VERIFY:** paired top-K metrics, multi-seed intervals, compute/parameter table, and negative results are published.
- [ ] **WHAT:** Replace oracle injection evidence with real-background end-to-end trials. **WHY:** current diagnostic overstates attainable recovery. **HOW:** blind locations/families, inject into frozen real residuals, include null controls, rerun full queue/review path, estimate covariance only from allowed data. **WHERE:** `research/injection.py`, transient protocols/runners, released background manifest. **VERIFY:** coverage/null calibration by stratum; recovery and false alarms reported jointly; analyst remains blind until freeze.
- [ ] **WHAT:** Qualify live dependencies rather than fixture labels. **WHY:** service/schema drift can silently invalidate evidence. **HOW:** run read-only contract probes, replay captured success/failure responses through actual parsers, bind timestamps/schema/version, expire results. **WHERE:** clients, `operations/fixtures.py`, `promotion.py`, CI/scheduled qualification. **VERIFY:** deliberate schema, timeout, stale, auth, and malformed-response changes fail closed in integration tests and recorded live rehearsal.
- [ ] **WHAT:** Resolve literature and legal release gates. **WHY:** missing closest work undermines novelty; unclear rights block reproducibility. **HOW:** add Rui 2026/direct comparison, primary-source bibliography audit, LICENSE, data/asset rights inventory, venue and author approval. **WHERE:** bibliography, related work, `LICENSE`, data availability, final checklist. **VERIFY:** metadata/link checker passes and release contains explicit code/data/manuscript terms.

### P2 — major quality improvements

- [ ] **WHAT:** Strengthen uncertainty. **WHY:** current intervals omit night/policy/training variation. **HOW:** define estimand and resample the deployment unit, use paired block bootstrap/hierarchical models, include training seeds and label uncertainty. **WHERE:** `research/benchmark.py`, paper statistics section. **VERIFY:** simulation-based coverage tests and sensitivity across resampling units.
- [ ] **WHAT:** Validate JEPA representations at scale. **WHY:** latent loss is not scientific utility. **HOW:** version a real corpus/checkpoint; run pooling, mask, view, loss, normalization, band, and architecture ablations; assess collapse, linear probes, similarity, OOD, and top-K queue gain. **WHERE:** `ml/*`, configs, new experiment archive. **VERIFY:** held-out later-period multi-seed results with frozen model selection and reproducible checkpoints.
- [ ] **WHAT:** Formalize photometric semantics. **WHY:** survey/filter/unit conflation causes spurious learning and invalid comparisons. **HOW:** encode survey, passband response/version, flux unit/zeropoint, time standard, censoring, forced-photometry flag, calibration lineage. **WHERE:** ingest schema, band vocabulary, dataset token contract, manifests. **VERIFY:** round-trip unit tests, cross-survey invariance tests, and leave-survey-out evaluation.
- [ ] **WHAT:** Measure human and operational benefit. **WHY:** logical safeguards are useful only if they change real decisions/cost. **HOW:** record review time, overrides, disagreement, stale-evidence blocks, false preparations, incidents, and audit-sample outcomes. **WHERE:** review metrics, ledger, prospective protocol. **VERIFY:** predefined paired/clustered analysis with privacy-preserving released aggregates.
- [ ] **WHAT:** Add realistic scale/failure benchmarks. **WHY:** overnight and Rubin-scale readiness are unproven. **HOW:** benchmark throughput, peak memory, archive growth, sharding, retries, service quotas, checkpoint resume, and recovery. **WHERE:** benchmark scripts/CI artifacts/operations docs. **VERIFY:** repeatable load report with target budgets and fault-injection recovery evidence.

### P3 — polish and optimization

- [ ] **WHAT:** Reduce and accessibility-check the paper. **WHY:** 29 dense untagged pages risk venue and reader failure. **HOW:** move detailed future protocols/evidence inventories to supplement, add alt text/tagging, tighten tables, verify color-independent figures. **WHERE:** manuscript, figure scripts, build pipeline. **VERIFY:** venue checklist, PDF accessibility check, and page-by-page visual inspection.
- [ ] **WHAT:** Quarantine legacy code more explicitly. **WHY:** duplicate root workflows confuse supported behavior. **HOW:** move to an archive with a manifest or remove from release artifacts; document canonical entry points. **WHERE:** root scripts, `cool-stuff-master/`, MANIFEST, README. **VERIFY:** package/source archive contains only intended supported code and no documentation links to legacy entry points.
- [ ] **WHAT:** Improve experiment ergonomics. **WHY:** many manual manifests/checklists invite drift. **HOW:** add one release command that creates the environment report, runs checks/reconstruction, compares semantic outputs, builds PDF, and emits a signed summary without overwriting evidence. **WHERE:** Makefile/scripts/reconstruction tooling. **VERIFY:** one clean-machine command produces a complete immutable release candidate or a precise fail-closed report.

## 12. Bottom line

SIDEREA has a real, thoughtful core and unusually strong epistemic hygiene in its prose and safety contracts. The project should resist the temptation to turn that into an unsupported detector/ML paper. Its best path is to freeze and repair the software release, reconcile or demote the historical claims, add the missing closest work, and then run one decisive preregistered prospective study. A negative result from that study would still be valuable if the evidence contract demonstrably prevents stale, failed, or misbound evidence from authorizing action. At present, the repository proves that the contract can be enforced in software and that synthetic experiments can be reconstructed; it does not yet prove that the system improves astronomical discovery.
