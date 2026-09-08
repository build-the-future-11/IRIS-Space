# Scientific validation plan

## Status and claim boundary

SIDEREA has a scientific-software foundation, not a completed scientific validation.
Unit tests can show that code follows its stated rules; they cannot show that a
ranking improves discovery yield, that an embedding captures astrophysical
phenomena, or that a candidate is new.

The acceptable claim today is:

> SIDEREA implements testable, provenance-rich components for human-supervised
> candidate triage and an experimental irregular-time representation model.

Claims about sensitivity, purity, probability calibration, discovery rate, or
superiority to the legacy I SPY workflow require the studies below. The study
protocol, primary metric, minimum useful effect, exclusion rules, and promotion
thresholds must be frozen before looking at final test results.

## Scientific questions

Validation answers five separate questions. Passing one does not imply the others.

1. **Measurement validity:** Do ingestion and features preserve the physical
   meaning, uncertainty, filter identity, timing, upper limits, and quality state
   of the observations?
2. **Ranking utility:** Under a fixed nightly review budget, does the system place
   more genuinely useful candidates in front of reviewers than declared
   baselines?
3. **Uncertainty validity:** When a downstream model emits a probability, is it
   calibrated for the population, epoch, and survey where it is used?
4. **Operational safety:** Do external outages, schema changes, stale data, and
   partial runs block reporting instead of producing false clearance?
5. **Human-system utility:** Does SIDEREA improve reviewer yield or time without
   reducing safety, diversity, or independent judgment?

TS-JEPA has an additional question: does self-supervised latent prediction add
stable, out-of-time downstream value beyond simpler temporal features?

## Threat model

Every evaluation must explicitly address these failure modes:

- observations from the same astronomical object appearing in both train and test;
- future observations leaking into features intended to represent an earlier alert;
- labels or catalogue state created after the prediction timestamp leaking into
  training inputs;
- repeated aliases or nearby detections of one source crossing splits;
- TNS-confirmed positives being easier or brighter than unlabelled live candidates;
- treating unreviewed or unresolved candidates as negatives;
- broker/classifier output becoming a shortcut for the target label;
- class imbalance making accuracy look high while nightly yield is poor;
- performance measured only on candidates already selected by an older model;
- delayed labels, corrected designations, catalogue updates, and concept drift;
- survey, season, sky-position, band-coverage, or cadence shifts;
- hyperparameter decisions made on the final test set;
- many metric or subgroup comparisons without uncertainty correction;
- reviewer behavior changing because a model score or explanation is visible; and
- high anomaly scores concentrating on corrupt data instead of rare astrophysics.

## Evidence levels

| Level | Required evidence | Permitted use |
|---|---|---|
| L0 — implemented | Code, API contract, unit tests | Development only |
| L1 — technically verified | Reproducible fixtures, property/invariant tests, fault injection | Offline pipeline testing |
| L2 — retrospectively benchmarked | Frozen historical snapshots, leakage audit, locked baselines and metrics | Shadow-mode research |
| L3 — prospectively validated | Time-forward live campaign with complete denominator and outcomes | Assisted candidate prioritization |
| L4 — operationally qualified | Safety drills, monitoring, rollback, reviewer study, change control | Routine supervised operation |

No ML component, including JEPA, may affect reportability. L3 or L4 permits ranking
assistance only; fresh external evidence and independent review remain mandatory.

## 1. Dataset and label protocol

### Immutable raw layer

For each acquisition, retain or reference:

- survey/broker and endpoint/schema version;
- acquisition start/end timestamps and query parameters;
- alert packet or source-object identifiers;
- observation time scale and conversion performed;
- band, calibrated value, uncertainty, detection/upper-limit state, and quality
  fields before feature filtering;
- image/cutout identifiers and checksums when used;
- catalogue query timestamps and raw-response digests; and
- acquisition warnings and partial failures.

Create a `DatasetSnapshot` over all source files. Store the snapshot digest, label
policy, and split policy with every training or backtest result. Input files used
by a released run must be immutable; corrections create a new snapshot.

The implemented local CSV path hashes the same byte snapshot that it parses.
`broker-fetch` writes an `siderea.broker_snapshot.v1` sidecar containing the emitted
photometry SHA-256 plus source/query/retrieval metadata, and later ingestion rejects
a sidecar whose schema or digest does not match the CSV. Local analysis manifests
record the effective ingestion provenance, artifact/config digests, Git state when
available, and a content digest of the local SIDEREA source/config tree even without
Git. Outside a checkout, the code digest falls back to the installed `siderea`
package tree and refuses an empty code identity. After its run directory is
created, local analysis also emits a terminal manifest after a caught processing
failure or user interruption and inventories
already-finalized partial artifacts when possible. These are integrity and
lineage controls, not authentication of an upstream broker or proof of
photometric calibration.

### Object identity and de-duplication

Build an alias group before splitting using broker IDs, TNS names, coordinates,
time overlap, and survey cross-matches. All epochs and aliases in a group belong to
one split. Record uncertain merges for manual audit; do not silently resolve them
using the target label.

### Point-in-time examples

Create an example at a declared decision timestamp. Features may use only
observations and metadata available by that timestamp. Label and catalogue queries
may look later only to determine the eventual outcome, and those later fields must
never enter the feature matrix.

Evaluate more than one alert age, for example first eligibility, +1 day, and +3
days. This measures how usefulness changes as the light curve matures and prevents
results based solely on late, easy classifications.

### Label taxonomy

Labels must encode provenance and maturity rather than a single guessed class:

- confirmed campaign-relevant astrophysical transient;
- confirmed astrophysical but outside the campaign target;
- previously reported/duplicate transient;
- known Solar System object;
- known variable or stellar contaminant;
- image/subtraction artifact;
- insufficient evidence;
- unresolved; and
- retracted or corrected label.

Only defensible terminal outcomes become supervised targets. `Unresolved`,
`insufficient evidence`, and unreviewed candidates are not negative examples. A
label should include who or what assigned it, when, the referenced evidence, and a
policy version. Train/evaluate against more than one defensible label definition
when the scientific objective differs, such as “real astrophysical” versus “new
and campaign-relevant.”

### Split protocol

Use object-grouped chronological splits. The supplied `chronological_indices`
helper provides time ordering, but the dataset builder is responsible for grouping
aliases before passing one timestamp per object group.

The implemented baseline CLI makes the identity choice explicit: training requires
either `--entity COLUMN`, which enables cross-partition purging, or the strong
`--assert-unique-entities` assertion that every row is a distinct physical entity.
Its dataset digest includes entity IDs and its metadata records the exact split.
The implemented JEPA CLI independently rejects object-ID and optional
entity/group-ID overlap between its train and validation JSONL files. Its default
chronological policy also requires every training observation to precede every
validation observation; `--split-policy predefined` is only a caller assertion of
an externally audited split.

A minimum evaluation layout is:

- development/train: earliest interval;
- calibration/validation: following interval;
- locked test: latest historical interval; and
- prospective shadow interval: data arriving after all model choices are frozen.

Where data permit, repeat with rolling-origin evaluation across seasons. Report
the exact cutoff times and perform an explicit overlap audit covering object ID,
alias, sky-position/time clusters, and source file hashes.

## 2. Measurement and feature verification

### Current extraction boundary

`siderea.photometry.v4` can extract survey/passband-channel features from magnitude,
limiting-magnitude, and supplied forced/difference-flux columns. If survey identity
is present, equally named filters from different surveys are kept separate and
prior non-detections are paired only within the same survey/passband channel.
Missing survey identity is exposed and isolated in an `unspecified` channel.
Inputs with no survey column retain passband-only channels for compatibility. It
does not request survey photometry, run image subtraction, determine flux calibration, or
verify that a forced-flux series came from the claimed image/position. Until the
acquisition and calibration layers are implemented, a dataset owner must provide
those provenance records and the validation study must independently inspect
them.

The extractor reports missing flux and magnitude uncertainties, and
`siderea.heuristic_priority.v2` penalizes them through its data-quality component.
The current automated local quality gate fails when every detection measurement
uncertainty is missing or invalid. Partial missingness remains visible and
penalized but does not alone fail the gate, and the gate does not impose a minimum
detection significance. In particular, a feature may still have incomplete
comparison-error support when only some uncertainties are present. A prospective
protocol must define conservative eligibility and significance rules explicitly
and must not treat `quality_passed` as evidence that SIDEREA inspected
difference/reference images.

Before any model comparison, establish invariants with synthetic and curated light
curves:

- adding a constant zero-point offset to one survey/passband channel does not
  create cross-channel variability;
- observations in equally named filters from two surveys remain in different
  channels and cannot fabricate variability or prior-non-detection contrast;
- permuting input row order does not change time-sorted features;
- exact duplicate observations and reuse of a non-empty observation ID within one
  source/survey are rejected; survey revisions and near-duplicates follow a
  separately declared and validated survey policy;
- rise and fade signs agree with the magnitude convention;
- a prior non-detection is paired with a later detection in the same
  survey/passband channel;
- large-error, flagged, and missing measurements affect quality and missingness
  outputs rather than becoming clean zeros;
- multiplying every flux and flux uncertainty in a channel by the same positive
  factor leaves fractional excursions, significances, and normalized rates
  unchanged;
- negative and zero difference-flux measurements remain signed measurements and
  never determine detection status implicitly;
- tables with no finite magnitude values, including an entirely empty magnitude
  column, are rejected unless every row has explicit detection semantics;
- flux and magnitude pathways have separately verified peak, slope, uncertainty,
  and missingness conventions;
- same-channel forced-flux prior contrasts use paired finite positive uncertainties,
  and remain undefined rather than fabricated when those errors are absent;
- limiting magnitudes are not treated as detections;
- time conversions preserve order and sub-day intervals; and
- features remain finite or explicitly undefined for empty, one-point, constant,
  and pathological inputs.

Compare a stratified random sample against an independent notebook or reference
implementation. The reviewer should see raw rows, normalized rows, and final
features. Record discrepancy counts and resolutions.

## 3. Baselines and evaluation metrics

### Baselines

The current logistic baseline is not permitted to silently assume row
independence. Its CLI requires a physical-entity column for chronological purging
or an explicit assertion that every row is a different entity. The latter is
appropriate only after an independent identity audit; it is not evidence that
SIDEREA discovered aliases automatically.

Every learned model must be compared with all applicable low-complexity baselines:

1. random ranking under the same eligibility rules;
2. broker-provided ranking or class probability, frozen as observed at decision
   time;
3. the legacy I SPY ordering, where its inputs can be reproduced;
4. the SIDEREA explainable heuristic;
5. a regularized supervised linear/logistic model on frozen engineered features;
6. a tree/boosting baseline with missingness indicators; and
7. for JEPA, the same downstream head with no JEPA embeddings.

Hyperparameter search uses training and validation only. The locked test set is
run once per preregistered candidate model.

### Primary operational metrics

SIDEREA works under a finite nightly review budget, so threshold-independent accuracy
is not enough. The implemented evaluation module supports:

- precision at review budget `K`;
- recall at `K`;
- average precision;
- Brier score; and
- expected calibration error.

Add these campaign-level measures to the evaluation record:

- useful candidates per night and per reviewer-hour;
- fraction of eligible nights with at least one useful candidate;
- time from alert eligibility to review and follow-up decision;
- rejection-reason distribution;
- duplicate, moving-object, variable-star, and artifact escape rates;
- fraction blocked by unavailable or stale evidence;
- diversity across class, magnitude, cadence, sky region, and anomaly route; and
- follow-up yield and eventual designation/confirmation rate.

Brier score and calibration error apply only to a model explicitly trained and
evaluated as a probability estimator. Do not calculate or report calibration for
the heuristic priority or raw JEPA loss/embeddings.

### Uncertainty

Report counts and confidence intervals, not only point estimates. Resample at the
independent unit—normally night or object group—not individual observations.
Preserve temporal blocks when autocorrelation is material. For rare-positive
subgroups, show exact numerator/denominator and avoid strong conclusions from a
wide interval.

For promotion, require the lower bound of the preregistered confidence interval on
the primary improvement to exceed zero and the point estimate to exceed a declared
minimum useful effect. Correct or clearly label exploratory multiple subgroup
comparisons. Publish negative and null results.

## 4. Probability calibration

The implemented logistic baseline only labels output as a probability when its
sigmoid calibrator was fitted on the later held-out calibration partition; otherwise
its metadata calls the output an uncalibrated model score. If this or a future
supervised model emits `probability_real` or `probability_novel`:

1. fit the classifier on the training interval;
2. fit calibration on the later calibration interval only;
3. evaluate once on the locked later test interval;
4. plot reliability by probability bin with counts and uncertainty;
5. report Brier score, log loss, calibration slope/intercept, and ECE;
6. stratify by survey, alert age, band coverage, magnitude, missingness, and season;
7. define abstention behavior outside the training support; and
8. recalibrate or withdraw the model when monitored drift exceeds a preregistered
   limit.

A calibrated output remains conditional on its labelled population. Selection
bias can make a well-calibrated retrospective model invalid on the full broker
stream; prospective audit sampling is required.

## 5. TS-JEPA validation

### Current leakage-control boundary

The implemented tokenizer first robustly scales each complete light curve for
numerical stability. For every masked example, the model then re-bases values and
uncertainties using unmasked context only—detected context when available, otherwise
all context—so hidden target values cannot determine the visible context
normalization. Supplied errors must be strictly positive, and normalized error `0`
is therefore an explicit missing-error sentinel rather than an imputation from the
masked target window. Flux is the default value kind and requires explicit
detection flags; only magnitude inputs may infer detection from finite values.
Each curve now records the canonical `siderea.light_curve_tokens.v3` contract and a
SHA-256 over its token fields, value semantics, band vocabulary/policy,
normalization, truncation, ordering, and missing-value/error behavior. The sixth
`value_present` field keeps a measured zero or finite non-detection distinct from
an epoch with no value, closing a masked-target normalization shortcut. Batch collation
recomputes known digests and rejects mixed known contracts, mixed known/missing
provenance, and mismatches. An all-legacy batch remains loadable but does not gain
v3 provenance by implication.
Training, repeated-mask evaluation, and embedding extraction enforce one observed
contract digest across all batches and return it. The CLI requires equal
train/validation contracts, verifies both runtime-reported digests, and persists
the full contract and digest with the checkpoint/summary. This binds token
interpretation to an experiment; it still does not validate that interpretation
scientifically.

The training command rejects duplicate or overlapping train/validation object IDs
and overlapping optional entity/group IDs. Its default chronological policy
requires the complete training time extent to precede validation; `predefined`
records an external-split assertion rather than proving the split is leakage-free.
Model construction, data loading, and masks are seeded and deterministic PyTorch
algorithms are requested by default, with an explicit nondeterministic opt-out.
Held-out loss uses at least two independently seeded masks (five by CLI default)
and reports the repeat losses, standard deviation, and a 95% half-width. This
quantifies mask-sampling variation only; it is not a full scientific uncertainty
interval, and deterministic settings do not guarantee bitwise identity across all
hardware/software stacks.

These controls narrow one leakage route; they do not validate the corpus, prove
that other shortcuts are absent, calibrate an embedding, or establish scientific
utility. The current implementation and CLI outputs remain shadow-only.

### What the objective establishes

Low held-out latent-prediction loss shows that the model predicts its target
encoder representations for masked temporal windows. It does not by itself show
that the representation captures class, novelty, physical parameters, or
scientific value.

### Required technical diagnostics

For every checkpoint and seed, record:

- train and repeated-mask held-out loss with per-repeat target-token counts,
  mask seeds, dispersion, and the stated interval interpretation;
- mean and minimum target-feature standard deviation;
- collapsed-feature fraction and representation RMS;
- learning-rate and EMA schedules;
- mask fraction and window-length distribution;
- gradient and parameter norms;
- embedding norm and effective-rank diagnostics;
- nearest-neighbor duplication/alias audit; and
- snapshot, config, code, seed, and checkpoint digests.

Stop a run on non-finite loss, empty usable masks, data leakage, or clear
representation collapse. A non-collapsed representation is necessary, not
sufficient.

### Required ablations

Compare across multiple fixed seeds:

- engineered features only;
- randomly initialized frozen encoder;
- trained JEPA frozen embeddings plus a linear probe;
- trained JEPA embeddings plus the same supervised head used by the baseline;
- optional end-to-end fine-tuning, reported separately;
- shuffled observation times;
- removed or shuffled band identity;
- detections only versus detections plus non-detections;
- alternate contiguous mask fractions and durations; and
- matched-capacity autoencoding or next-step prediction where feasible.

Time or band shuffling that does not reduce the relevant metric is evidence that
the model is ignoring that structure. JEPA is promotable only if it adds stable,
out-of-time value over both engineered-feature and matched downstream baselines,
not merely over random ranking.

### Downstream tasks

Evaluate embeddings on tasks with independent labels or physically meaningful
targets:

- real-versus-artifact triage;
- known-versus-novel candidate ranking;
- coarse transient class retrieval;
- masked/next-window prediction;
- anomaly enrichment among audited candidates; and
- nearest-neighbor consistency after removing aliases and duplicates.

Report the full eligible denominator. Interesting nearest neighbors are qualitative
examples, not a substitute for retrieval metrics and blinded expert assessment.
When an analogue index is persisted, the implemented `siderea.embedding_index.v2`
format requires SHA-256 identifiers for the encoder, token contract, and dataset
snapshot, rejects missing/legacy provenance on load, and requires matching encoder
and token-contract digests for each query. Validation must still
verify the referenced artifacts, duplicate policy, label maturity, and producer;
well-formed caller-supplied digests do not establish scientific validity.

### Shadow-mode promotion gate

The supplied JEPA research profile uses `shadow_mode = true`. Promotion requires:

- L2 retrospective evidence with leakage audit and all required ablations;
- stable results across seeds and at least two out-of-time intervals;
- no material degradation in safety, calibration, diversity, or latency;
- a prospective L3 campaign where JEPA output is logged but initially hidden from
  reviewers;
- a second, controlled assisted-review phase if the blinded shadow phase passes;
- model-card review documenting population, failure modes, and withdrawal rules;
  and
- explicit human approval of the versioned checkpoint.

Even after promotion, JEPA may alter ranking only. It never satisfies a catalogue,
quality, human-review, or reporting gate.

## 6. Prospective shadow campaign

Retrospective data are selected by past systems and human attention. A prospective
campaign must capture the denominator before ranking:

1. log every candidate that satisfies frozen eligibility rules;
2. record features, all model outputs, failures, and latency before outcomes are
   known;
3. allocate the normal review budget using the control policy;
4. reserve preregistered random-audit and anomaly slots to observe candidates the
   control would miss;
5. hide experimental scores from reviewers during the first phase;
6. use a locked review rubric and record review duration and uncertainty;
7. mature outcomes for a declared interval before analysis; and
8. publish the complete flow diagram from eligible objects to mature labels.

The random-audit sample is essential for estimating missed-positive rate and
selection bias. The implemented `siderea.nightly_queue.v2` can reserve that route
from the complete eligible population using a recorded seed and uniform
without-replacement sampling. It logs the eligibility policy, audit population,
requested/used slots, inclusion probability, and the same propensity on every
random-audit entry. The CLI generates and records a seed if none is supplied;
campaigns must preserve it and preregister the slot count. Priority and anomaly
entries have no audit propensity and must not be analyzed as if randomized. If an
assisted phase follows, randomize nights or candidate slots between control and
assisted ranking where operationally safe. Analyze by assigned arm and report
crossovers.

`siderea review-set` packages the exact ranking and `siderea.candidates.v1` bytes, the
selected queue, per-candidate versions/dossiers, and artifact hashes in an atomic
`siderea.review_set.v1` directory. This makes a nightly review denominator portable,
but it does not establish that upstream eligibility captured the full broker
stream; the campaign still needs an immutable pre-ranking intake log.

## 7. Human-review validation

The dossier should be evaluated with representative reviewers and candidates.
The implemented loopback review service is suitable for local workflow studies,
but its typed reviewer name is not authenticated identity and therefore is not
evidence of production-grade separation of duties. Its ledger binds each decision
to an exact immutable candidate version and excludes stale-version approvals, but
cryptographic version binding is not user authentication.

Ledger schema v4 also archives the first candidate snapshot seen for every version
and prevents update/deletion of that history. Version lookup can therefore recover
the payload referenced by an older review, adjudication, or outcome after the
current candidate advances, and database guards reject orphan version references.
This establishes local reconstructability, not authenticated authorship, backup,
or long-term retention; those still require operational qualification.

The ledger/CLI now has a separate append-only, exact-version adjudication event for
`manual_review_required` catalogue context. Preflight considers the ambiguity
resolved only with at least one active `clear_context` and no active `reject`;
without an active clearance, no event or `needs_more_data` remains blocking. An
adjudication cannot override failed quality, a catalogue match, missing external
evidence, or ordinary separation-of-duty approvals, and it becomes inapplicable
when the candidate version changes. The adjudicator string is also only an audit
label until production authentication and authorization exist.

Measure:

- time to first decision and total handling time;
- agreement before and after adjudication;
- vetoes or warnings overlooked;
- confidence and abstention rates;
- effect of showing versus hiding model explanations;
- whether unusual candidates are systematically deprioritized; and
- correctness of separation-of-duty enforcement.

Use at least two independent reviewers for the agreement study. Reviewer identity
is needed for independence and audit but must be handled under an appropriate
access and retention policy. Never use reviewer agreement alone as astrophysical
ground truth.

## 8. Operational safety qualification

Several fail-closed behaviors are already implemented: missing mandatory-service
policy blocks; external clear evidence without an explicit valid expiry is not
fresh; invalid timezone/expiry metadata is rejected; missing, disabled, pending,
error, and expired mandatory checks block; a known-object match rejects; and the
latest timestamped result is selected when a service has multiple evidence
records. Disagreeing records tied at that latest timestamp block regardless of
input order. Claimed clearance also requires an attempt and response digest, no
embedded match/error, and query binding to candidate identity/position, cone
radius, TTL policy, and every candidate reference epoch for SkyBoT. Verification
queries each distinct requested MJD, binds each response to that epoch, and emits
an `all_distinct_detection_epochs` aggregate. It is clear only if every component
is clear; a match at any epoch vetoes and any error, disabled, stale, or pending
component blocks. On import, the local pipeline independently requires coverage of
every distinct usable detection MJD in normalized photometry. Malformed TNS
success payloads become errors. Imported evidence requires the top-level
`siderea.verification.v1` schema, valid candidate/checks fields, a boolean manual
review flag, and the complete exact check-provenance shape; no timestamp, attempt
count, or service version is synthesized. Imported TNS clear
evidence additionally requires `tns-two-stage-search.v1`, the ordered internal-name
and cone methods, matching identity, and the two-stage coverage policy. Reviews
must be written with an explicitly supplied immutable candidate version—the
ledger and CLI never infer it—and reporting preflight recomputes a digest over its
bound checks, quality/manual flags, mandatory-service set, and binding context
before considering approval. The append-only candidate-version archive preserves
the first payload for each referenced version and guards new child records against
unknown versions. Unit tests cover the core no-TTL,
malformed/internally inconsistent clearance, error, match, disabled-TNS,
multi-epoch query binding, host ambiguity/adjudication, and independent-review
paths.

This is an implemented coverage contract, not proof that the chosen usable
detection epochs, cone radius, ephemeris service, or time tolerance are sufficient
for every campaign. Those policy choices still require recorded-fixture and live
scientific qualification.

Operational qualification is broader than those unit tests. Recorded-fixture and
fault-injection tests must demonstrate that each of the following yields `blocked`,
not `clear` or `reportable`:

- DNS/connectivity failure and timeout;
- HTTP error and rate limit;
- authentication failure;
- missing optional client dependency;
- empty-but-malformed response;
- schema/field change;
- non-finite coordinate or epoch;
- missing service result or empty mandatory-service policy;
- disabled mandatory service;
- invalid or absent expiry;
- expired evidence or an older clear result superseded by a newer failure;
- partial run or interrupted artifact write;
- missing screener/reviewer approval;
- the same person approving in both roles;
- approval attached to a stale or different candidate version;
- fresh clearance for another candidate, position, radius, or an incomplete or
  different set of SkyBoT epochs;
- a substituted quality/manual flag or mandatory-service policy at preflight;
- missing, rejecting, or stale-version manual-context adjudication; and
- a TNS HTTP success whose application payload has no accepted result array.

Also verify that a genuine known-object match wins over simultaneous errors from
other services and remains visible in the rejection reason. Run these drills
regularly against recorded fixtures so correctness does not depend on live service
availability.

The mandatory operational threshold is zero fail-open outcomes in the safety
suite. Any fail-open defect withdraws reporting readiness until fixed and
requalified.

## 9. Drift and change control

Monitor input and outcome distributions over time:

- alert rate and eligibility rate;
- band/cadence/uncertainty/missingness distributions;
- broker class mixture and schema version;
- feature and embedding distributions;
- model score and abstention distributions;
- external-service error/staleness rate;
- reviewer approval/rejection reasons; and
- delayed outcome yield.

Define warning and withdrawal thresholds before deployment. A schema change,
material population shift, revised label policy, new survey, changed feature
definition, or retrained model creates a new version and requires the appropriate
revalidation. Do not silently overwrite a checkpoint or dataset snapshot.

## 10. Promotion record

Every component promoted beyond shadow mode needs a signed review record containing:

- scientific question and intended campaign;
- eligibility and label policies;
- dataset snapshot and leakage-audit results;
- code/config/model digests;
- baselines, primary metric, minimum useful effect, and uncertainty method;
- all locked test and prospective results, including adverse subgroup results;
- operational safety-suite result;
- exact candidate version plus taxonomy/evidence digests for any outcomes used as
  labels;
- known limitations and abstention/withdrawal rules;
- reviewer names and independent approval; and
- effective date and rollback version.

Until this record exists, SIDEREA remains an experimental prioritization aid. A
candidate-specific evidence package and human scientific judgment are always
required for an external claim.
