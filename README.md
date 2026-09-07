# IRIS — human-supervised astronomical discovery

IRIS is a reproducible candidate-discovery platform being built from the original
**I SPY** optical-transient scripts. It provides typed candidate records,
survey- and filter-aware light-curve features, explainable prioritization, fail-closed
catalogue checks, review and outcome ledgers, reproducibility records, and an
experimental time-series JEPA path.

The governing rule is simple: **models rank; evidence and people decide**. No ML
score can make a candidate reportable, a failed network request is never treated
as a clear catalogue search, and this repository contains no unattended TNS
submission path.

> **Maturity:** research software under active migration. The package components
> under `src/iris/` are covered by unit-level tests, but the full live
> broker-to-report workflow has not yet completed a prospective validation
> campaign. Do not describe IRIS scores as discovery probabilities or use them as
> sole evidence for an astronomical claim.

## What is implemented

- Strict TOML configuration with unknown-key rejection and paths resolved relative
  to the configuration file.
- Strict local CSV ingestion with alias ambiguity checks, coordinate consistency,
  JD-to-MJD conversion, source-file hashes, rejection of exact duplicates and
  reused non-empty observation IDs, and a canonical schema for magnitude,
  limiting-magnitude, and supplied forced/difference-flux measurements. A
  broker snapshot sidecar is accepted only when its photometry digest matches
  the exact CSV bytes being parsed; those same immutable bytes are archived in
  the run rather than reopening a possibly replaced source path.
- An immutable `iris.local_analysis.v4` pipeline with a deterministic scientific
  fingerprint that writes normalized photometry, features, rankings, consolidated
  candidate evidence, a dataset snapshot, a run manifest, and ledger state. Each
  candidate also receives an immutable scientific-evidence digest; missing external
  checks are materialized as pending without making repeated local runs appear to
  have new evidence. The manifest hashes artifacts and effective configuration,
  records Git state when available, and always records a digest of the IRIS code
  used: the source/config tree in a checkout or the installed `iris` package tree
  when no checkout is available. Once a run directory is created, normal
  completion, caught processing failure, and user interruption close a terminal
  manifest; failure/interruption manifests inventory finalized partial artifacts
  when possible.
- A lazy `iris.ingest.alerce.v4` broker adapter behind the common ingestion
  protocol, with an explicit `ztf` or `lsst` survey namespace on every broker
  call. ZTF and Rubin/LSST use separate object-query, photometry, and quality
  contracts; the accepted contract and bounded network policy are retained in
  provenance. Durable live polling, replay, and schema monitoring are not yet
  operational services. The bounded CLI fetch durably publishes a no-clobber
  canonical CSV/provenance pair whose identity and content digest are verified
  on later ingestion.
- Immutable candidate, observation, evidence, and lifecycle records.
- Versioned `iris.photometry.v4` features for magnitudes and supplied
  forced/difference fluxes. When survey identity is present, statistics and prior
  non-detection pairing stay inside a survey/passband channel, so equally named
  filters from different facilities are never pooled. The flux path exposes
  unit-scale-invariant excursions, significance, normalized rates, and
  same-channel prior non-detection contrasts; missing survey identity,
  uncertainties, and quality rejections remain visible.
- A versioned, bounded, decomposed heuristic priority score that records whether
  magnitude evidence or a forced-flux fallback supplied each component and is
  explicitly labelled as **not a probability**. TOML ranking weights name these
  exact components and are applied directly by the pipeline.
- Retry-aware SkyBoT, SIMBAD, VSX, and read-only TNS search clients with explicit
  `clear`, `match`, `error`, `disabled`, `stale`, and `pending` outcomes. TNS
  success responses with an absent or malformed result array become errors, never
  empty clearances. TNS clearance attests both the internal-name and position-cone
  response in one two-stage provenance record.
- A fail-closed reportability gate requiring fresh, explicit clear results from
  every mandatory service, with completed evidence bound to the candidate identity,
  sky position, required cone radius, configured TTL, and every distinct usable
  detection epoch required by the SkyBoT coverage policy.
- A SQLite outcome ledger and reporting preflight requiring one screener and the
  configured reviewer approvals, including at least one different person. Reviews
  bind to an explicitly supplied exact immutable candidate version—the ledger API
  and CLI do not infer a current version; preflight also verifies that its
  checks, quality/manual flags, mandatory-service policy, and binding context match
  the evidence reviewers saw. Ambiguous catalogue context can be resolved only by
  a reason-coded adjudication bound to that same version, and downstream outcomes
  are likewise bound to the exact current candidate version and hashed evidence.
  The v4 ledger retains an append-only first-seen snapshot for every candidate
  version, exposes version-history lookup, and rejects orphan version references,
  so an older review/outcome remains reconstructable after the current candidate
  advances.
- Portable candidate dossiers, atomic review-set bundles, run manifests, hashed
  dataset snapshots, chronological evaluation helpers, anomaly scoring, embedding
  similarity, and follow-up prioritization primitives. Persisted similarity
  indexes require encoder, token-contract, and dataset-snapshot SHA-256 provenance,
  and queries against those indexes must present matching encoder and
  token-contract digests.
- A loopback-only local review queue with bounded form input, per-process CSRF
  protection, reason-coded decisions, and no reporting endpoint. It is a research
  UI, not an authenticated multi-user service.
- A leakage-aware logistic-regression baseline with time-blocked
  train/calibration/test partitions, a required entity-ID purging policy or an
  explicit unique-entity assertion, held-out sigmoid calibration, and explicit
  calibrated-versus-uncalibrated score semantics.
- Reproducible nightly queue allocation with separate anomaly and randomized-audit
  reserves and a stable identifier tie-break. Random-audit entries record their
  replay seed, eligible population, uniform inclusion probability, and per-entry
  selection propensity; the default audit reserve is zero until a campaign opts in.
  The `review-set` command atomically binds a queue to exact ranking/candidate
  snapshots and writes a dossier for every selected candidate. Geometric
  host-association utilities explicitly report a chance-coincidence statistic
  rather than a host posterior; automatic
  acceptance requires positive transient and host positional uncertainties, and a
  scientific tie remains ambiguous even though its display order is deterministic.
- An optional irregular-time TS-JEPA implementation with contiguous temporal
  masking, context-only re-normalization after masking, an explicit missing-error
  sentinel, an EMA target encoder, checkpointing, chronological or explicitly
  asserted predefined splits, deterministic algorithms by default, repeated-mask
  held-out evaluation, and representation-collapse diagnostics. Flux-token
  records require explicit detection flags. Each tokenized curve carries the
  versioned `iris.light_curve_tokens.v3` contract and its SHA-256; batching rejects
  mixed, incomplete, or internally inconsistent known token contracts (while
  retaining support for an entirely legacy/unprovenanced batch). Training,
  repeated-mask evaluation, and embedding extraction propagate one run-level
  contract digest and reject mid-run provenance changes. The CLI additionally
  requires matching train/validation contracts and records the contract in its
  checkpoint and summary. It is shadow research only.

The implemented forced-flux path is **extraction from measurements already present
in an input table**. IRIS does not yet request forced photometry from a survey,
calibrate it, or independently validate its image-level provenance. Those
acquisition and qualification steps remain future operational work.

The operational gaps and evidence needed before scientific deployment are tracked
in [`docs/ROADMAP.md`](docs/ROADMAP.md) and
[`docs/SCIENTIFIC_VALIDATION.md`](docs/SCIENTIFIC_VALIDATION.md). The complete
0.2.0 implementation and adversarial audit is recorded in
[`docs/AUDIT_2026-09-06.md`](docs/AUDIT_2026-09-06.md); the final executed
verification and prioritized handoff are in
[`docs/PROJECT_EXECUTION_REPORT.md`](docs/PROJECT_EXECUTION_REPORT.md).
Development and disclosure procedures are in [`CONTRIBUTING.md`](CONTRIBUTING.md)
and [`SECURITY.md`](SECURITY.md).

## Install

Python 3.11 or newer is required. `pyproject.toml` is the canonical dependency and
packaging definition for the new platform.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'

# Add every live-astronomy, visualization, and ML extra.
.venv/bin/python -m pip install -e '.[all,dev]'
```

The minimal package installs NumPy and pandas. Extras can be selected separately
as `astronomy`, `visualization`, `ml`, or together as `all`. The astronomy extra
requires `alerce>=2.2.1,<3`; that is the qualified client-family floor for the
legacy-ZTF/multi-survey session and LSST query contracts used by adapter v4.
Scikit-learn is needed for the supervised baseline and optional Isolation Forest.
PyTorch is needed for TS-JEPA training or embedding extraction. For
accelerator-specific PyTorch builds, use the installation method appropriate to
that machine. The rest of IRIS remains importable without the ML extra.

## Local checks

```bash
# Works from a source checkout without installation.
PYTHONPATH=src python3 -m iris doctor
PYTHONPATH=src python3 -m iris config-show

# With the editable development install.
.venv/bin/python -m pytest
.venv/bin/ruff check src tests
.venv/bin/python -m mypy src/iris

# Equivalent release-oriented local gate.
make check PYTHON=.venv/bin/python
```

`doctor --strict` returns a non-zero status when a dependency in its current
scientific readiness inventory is missing. That inventory covers NumPy, pandas,
scikit-learn, PyTorch, Astropy, astroquery, ALeRCE, and Matplotlib. `doctor --json` emits
machine-readable readiness results. A warning from `doctor` is a readiness
signal, not permission to weaken a validation gate.

## Command surface

Run `iris COMMAND --help` for all arguments.

| Command | Purpose | Important boundary |
|---|---|---|
| `doctor` | Check config, storage, and listed science dependencies | `--strict` fails on missing optional science packages |
| `config-show` | Print the resolved, validated config | Output contains the selected profile and resolved absolute storage paths |
| `analyze INPUT` | Normalize and analyze a local photometry CSV | Missing external checks become `pending`; analysis alone is not reportability |
| `broker-fetch OUTPUT` | Fetch a bounded ALeRCE snapshot and provenance sidecar | Networked; `--survey` is explicitly `ztf` or `lsst`, and a durable, commit-ordered CSV/sidecar publication refuses to overwrite either output |
| `verify ID RA DEC MJD` | Run fail-closed TNS/SkyBoT/SIMBAD/VSX checks | Repeat `--skybot-mjd` for every additional distinct usable detection epoch; non-reportable outcomes return exit code `3` |
| `queue INPUT` | Allocate a reproducible finite review queue | Supports `triage` or `gate-clear` eligibility plus separate anomaly and seeded random-audit reserves; audit propensity is recorded |
| `review-set RANKING CANDIDATES OUTPUT` | Atomically package a queue, exact inputs, manifest, and selected dossiers | Refuses overwrite and remains review selection only, never reporting authorization |
| `dossier CANDIDATES_JSON ID` | Render portable JSON/HTML evidence | Decision support only |
| `review-add ID` | Append a reason-coded human decision | Candidate must exist in the ledger and `--candidate-version` must name its exact current immutable version |
| `adjudication-add ID` | Resolve or reject ambiguous catalogue context | Requires a reason and the exact current `--candidate-version`; it cannot waive a quality or known-object veto |
| `review-serve` | Serve the loopback-only local review UI | Loopback Host validation and CSRF are enforced, but there is no identity authentication and no report endpoint |
| `preflight ID` | Re-evaluate exact-version scientific evidence and approval readiness | Read-only; returns `0` only when ready and `3` when blocked, and never drafts or submits a report |
| `outcome-add ID` | Record a mature downstream outcome | Requires the exact current `--candidate-version`; does not infer or submit an outcome |
| `baseline-train INPUT OUTPUT` | Fit, calibrate/evaluate, and save the chronological logistic baseline | Exactly one of `--entity` or `--assert-unique-entities` is required; load trusted joblib bundles only |
| `jepa-train TRAIN VALIDATION OUTPUT` | Train/evaluate a TS-JEPA checkpoint | Enforces chronological splits by default, uses repeated masks and deterministic algorithms, and remains shadow-only |

### Safe local analysis flow

Start with local analysis. The input needs source ID, coordinates, time, and
passband plus at least one of magnitude, limiting magnitude, or flux. Any table
with no finite magnitudes—including one whose magnitude column exists but is
entirely empty—requires an explicit, non-missing `is_detection` value for every
row. Supply measurement uncertainties whenever they exist: they are never invented
as zero. Partial missingness stays visible and reduces the heuristic quality
component; if every detection uncertainty is missing or invalid, the automated
local quality gate fails. Input fluxes must already have a declared,
scientifically meaningful calibration and provenance outside this extractor. The
output JSON prints a new immutable run directory and its deterministic scientific
fingerprint:

```bash
iris analyze photometry.csv --config configs/default.toml
```

The fingerprint identifies scientific content and policy. The manifest separately
records the single wall-clock instant used for all freshness decisions in that
run; reporting preflight rechecks freshness at execution time. Normalized CSV
values use round-trip-safe float64 serialization. Numeric passbands default to
ZTF/ALeRCE `fid` semantics when no survey column is available. With survey
identity present, that numeric mapping is applied only to configured ZTF/ALeRCE
survey names; another survey's numeric filters remain distinct. Library callers
can disable the mapping or supply an explicit JEPA vocabulary.

The first run intentionally records mandatory remote checks as pending. The
default `triage` queue policy admits quality-passing candidates with incomplete
external evidence while still excluding known-object and failed-quality vetoes;
`--eligibility-policy gate-clear` admits only a clear gate or a candidate needing
catalogue-context adjudication. Allocate the finite review budget directly, or
atomically package the exact ranking and candidate evidence with every selected
dossier:

```bash
iris queue var/iris/runs/RUN_ID/ranked_candidates.csv \
  --audit-slots 2 --audit-seed CAMPAIGN_NIGHT_SEED \
  --output var/iris/review-queues/NIGHT_ID.json

iris review-set var/iris/runs/RUN_ID/ranked_candidates.csv \
  var/iris/runs/RUN_ID/candidates.json \
  var/iris/review-sets/NIGHT_ID \
  --audit-slots 2 --audit-seed CAMPAIGN_NIGHT_SEED
```

Omit `--audit-seed` to have the CLI generate and record one. Preserve that value
to replay the sample. The emitted uniform propensity describes only the seeded
random-audit route; it does not turn priority/anomaly selections into a random
sample. A review-set directory is new and immutable by convention: the command
refuses to overwrite it, archives the exact input bytes, verifies that ranking and
candidate ID/version sets agree, and writes artifact hashes plus the review-only
safety boundary in `manifest.json`.

After inspecting the photometry and images, run live validation. Supply
`--quality-passed` only when the upstream quality review actually passed:

```bash
iris verify CANDIDATE_ID RA_DEG DEC_DEG PEAK_MJD \
  --skybot-mjd OTHER_DETECTION_MJD \
  --skybot-mjd ANOTHER_DETECTION_MJD \
  --quality-passed \
  --output verification.json
```

The positional peak MJD is included automatically. Repeat `--skybot-mjd` for
every other distinct detection epoch that must be cleared. SkyBoT is queried once
per epoch; the aggregate is clear only if every query is clear. A match at any
epoch vetoes, while an error, disabled, stale, or pending component blocks. When
verification JSON is imported, the local pipeline requires the top-level
`iris.verification.v1` schema, a valid candidate ID/checks array, a boolean manual
review flag, and complete, exactly shaped provenance fields; it does not
synthesize missing timestamps, attempts, or service metadata. It also
independently requires coverage of every distinct usable detection MJD in that
candidate's normalized photometry.

TNS duplicate search requires all three runtime variables: `TNS_API_KEY`,
`TNS_BOT_ID`, and `TNS_BOT_NAME`. With none configured, or with
`--disable-network`, IRIS writes explicit disabled evidence and blocks the gate.
An HTTP-level success with a missing, differently shaped, or non-object TNS result
array is recorded as an error and also blocks. Imported TNS clearance is accepted
only with service version `tns-two-stage-search.v1`, the ordered internal-name and
position-cone methods, the matching candidate identity, and the declared two-stage
coverage policy. A clear result hashes both responses. Never convert exit code
`3` into success merely to continue a workflow.

Bind the verification artifact into a new immutable analysis run before collecting
approvals. Equivalent scientific inputs share a fingerprint, but executions never
overwrite one another. Copy the candidate's new `candidate_version` from
`ranked_candidates.csv` or `candidates.json`; it covers the normalized observations,
features, score, quality, checks, automated gate decision, and relevant scientific
policy.
Checks that are matched, failed, disabled, malformed, unbound, or expired remain
blocked:

```bash
iris analyze photometry.csv --checks-json verification.json
```

If the resulting candidate has `manual_review_required: true`, catalogue context
must first be adjudicated against that exact version. Use `clear_context` only
after a scientific reviewer has actually resolved the ambiguity; `reject` remains
blocking, and without an active `clear_context` the ambiguity remains unresolved:

```bash
iris adjudication-add CANDIDATE_ID --candidate-version CANDIDATE_VERSION \
  --adjudicator ADJUDICATOR_NAME --verdict clear_context \
  --reason "Inspected catalogue association and resolved the host context"
```

The latest decision from each normalized adjudicator is active. Any active
`reject` blocks; at least one active `clear_context` is required to resolve the
manual flag. This event resolves only the catalogue-context gate—it cannot waive
a known-object match, failed quality, missing service evidence, or independent
approval. Like reviewer names in the loopback UI, the CLI adjudicator name is an
audit label, not authenticated identity.

Then record a screener and the configured number of reviewer approvals, including
at least one reviewer different from the screener, against that exact version, or
use the local UI for ordinary reviews. The CLI rejects a stale or missing version;
changing photometry, evidence, or scientific policy creates a new version for
which old reviews and adjudications do not count:

```bash
iris review-add CANDIDATE_ID --candidate-version CANDIDATE_VERSION \
  --reviewer SCREEN_NAME --role screener --verdict approve \
  --reason "Reviewed light curve and image sequence"

iris review-add CANDIDATE_ID --candidate-version CANDIDATE_VERSION \
  --reviewer REVIEW_NAME --role reviewer --verdict approve \
  --reason "Independent evidence review complete"

iris review-serve
```

Finally, run the read-only preflight against the same immutable version. It
reloads the evidence from the ledger, re-verifies the completed run manifest and
candidate artifact, rebinds service results, rechecks freshness, and counts only
valid approvals for that version. A blocked result is emitted as structured JSON
with exit code `3`; no report material is created:

```bash
iris preflight CANDIDATE_ID --candidate-version CANDIDATE_VERSION
```

`review-add` and `adjudication-add` append ledger evidence; neither rewrites an
already completed run. To emit a later local run whose candidate record reflects
those workflow events, repeat the identical scientific analysis with a new
execution ID. The candidate version remains the same because neither the execution
ID nor the later workflow state changes the underlying scientific evidence:

```bash
iris analyze photometry.csv --checks-json verification.json \
  --run-id approved-CANDIDATE_ID
```

This can update local workflow/reportability state only. The separate `preflight`
command is the authoritative readiness check at execution time. IRIS still has no
production report transport or unattended submission path.

When a downstream outcome has genuinely matured, bind the taxonomy and optional
evidence object to the exact current candidate version. The ledger hashes that
evidence and rejects stale versions:

```bash
iris outcome-add CANDIDATE_ID --candidate-version CANDIDATE_VERSION \
  --outcome confirmed_transient --taxonomy-version iris.outcome.v1 \
  --evidence-json outcome-evidence.json
```

### Broker and model research commands

`broker-fetch` stages and fsyncs a canonical CSV plus `.provenance.json` sidecar
on the destination filesystem and refuses to overwrite either name. It publishes
the sidecar first, fsyncs the directory, then publishes the CSV as the commit
point and fsyncs again. Handled failures and interruption remove only the links
created by that invocation. Consequently a visible CSV cannot precede its complete
sidecar; an uncatchable process/filesystem failure can at worst leave a sidecar-only
residue that makes the next invocation fail closed. The CSV carries a snapshot
identity marker, and the sidecar binds that identity to the CSV SHA-256 and broker
metadata. `iris analyze` rejects a missing, mixed, malformed, or altered pair.
Direct local CSV inputs are also hashed and registered as source artifacts in the
local run manifest. Broker query/retrieval metadata is retained in ingestion
provenance and therefore in the run record:

```bash
iris broker-fetch broker-snapshot.csv --config configs/hunt.toml

# Qualified Rubin/LSST profile: SN, stamp_classifier_rubin_beta 2.0.1.
# IRIS aborts if the broker returns a different classifier contract.
iris broker-fetch rubin-snapshot.csv --config configs/hunt.toml --survey lsst
```

The LSST default is deliberately narrower than the ZTF hunt configuration: it
queries `SN` with `n_det` using the qualified `stamp_classifier_rubin_beta`
2.0.1 contract. Its locally qualified taxonomy is `SN`, `AGN`, `VS`, `asteroid`,
and `bogus`; an unsupported class for that classifier is rejected before a
request. `--classifier` and `--classifier-version` expose an explicit custom
contract, while repeated `--class` arguments override the class set. A custom
classifier requires an explicit version. Returned LSST objects must echo the
requested class, classifier name and version and must satisfy the integer minimum
`n_det`; otherwise ingestion fails rather than trusting a silently ignored filter.

Rubin/LSST detections map `band_name`, signed `psfFlux`, and `psfFluxErr` directly.
Adapter v4 validates the PSF-fit, mask, injection, and withdrawal fields and marks
an epoch unusable when any declared adverse flag is set. `isNegative` is validated
but is not a quality failure: a significant negative difference flux remains a
signed measurement. The current upstream LSST endpoint supplies no non-detection
or limiting-magnitude contract; an unexpected non-empty LSST non-detection response
is treated as schema drift and rejected.

ZTF object search retains the legacy `ndet` filter and defaults to
`lc_classifier_transient`. Its detection path intentionally uses raw difference
photometry (`magpsf`, `sigmapsf`, `fid`) rather than ALeRCE's corrected-magnitude
fields, and only a recognized positive `isdiffpos` row is quality-eligible for
features. `corrected`/`dubious` describe the optional total-flux correction, so
they do not veto this raw path. ZTF non-detections map the broker's 5-sigma
`diffmaglim` upper limit and are quality-eligible after the canonical row contract
validates; no independent per-row non-detection quality flag is supplied. This
does not establish artifact purity, and adapter v4 deliberately applies no
unqualified `rb`/`drb` threshold.

For the internally created ALeRCE client, IRIS requires the expected survey client
session, appends the configured user agent, applies the configured per-request
timeout, and retries each broker operation at most `max_retries + 1` times with
bounded exponential backoff. An injected test/deployment client may lack that
session hook, but provenance then records that the network policy was not enforced.

The supervised baseline requires explicit binary label, decision-time, and
feature columns plus exactly one entity policy. Prefer `--entity COLUMN`, which
purges repeated physical sources across chronological partitions:

```bash
iris baseline-train labelled-features.csv var/iris/models/baseline-v1 \
  --label is_target --time decision_mjd --entity object_id \
  --features amplitude cadence significance missing_fraction
```

Use `--assert-unique-entities` only when every row is independently known to be a
different physical entity. It is a strong caller assertion, not an identity check
performed by IRIS. Baseline metadata records the chosen policy, dataset and exact
split digests, and whether entity purging was applied.

JEPA consumes one JSON object per line with `object_id`, `times`, `values`,
`errors`, and `bands` arrays. `value_kind` defaults to `flux`; flux records require
an explicit `detections` array, while magnitude records may omit it and infer
detection from finite values. Arrays must align. Train and validation object IDs
and optional `entity_id`/`group_id` groups must not overlap, and the output
directory must be new. Missing uncertainty uses a zero sentinel because a supplied
uncertainty must be strictly positive. Initial per-curve scaling is re-based from
the unmasked context only for each masked example, so hidden target values cannot
set the context's normalization:

```bash
iris jepa-train train.jsonl validation.jsonl var/iris/models/jepa-v1 \
  --config configs/jepa.toml --epochs 10 \
  --split-policy chronological --evaluation-masks 5
```

The default split requires every training observation to precede every validation
observation. `--split-policy predefined` is an explicit assertion that an external
split has already been audited; it is not an automatic leakage check. Held-out
loss is evaluated over at least two independently seeded masks (five by default),
with repeat losses, dispersion, and a 95% half-width recorded. Deterministic
PyTorch algorithms and seeds are used by default; `--allow-nondeterministic` is an
explicit opt-out and does not change the shadow-only status. Deterministic intent
does not guarantee bit-identical results across every hardware/software stack.

These commands establish reproducible experiments, not evidence that either model
is scientifically superior. Follow the validation plan before changing a review
policy.

## Configuration

In a source checkout, the default profile is
[`configs/default.toml`](configs/default.toml). Additional profiles separate a
larger candidate hunt, external-validation settings, and the JEPA research path:

- [`configs/hunt.toml`](configs/hunt.toml)
- [`configs/validation.toml`](configs/validation.toml)
- [`configs/jepa.toml`](configs/jepa.toml)

Pass an explicit file with `--config`, or set `IRIS_CONFIG`. The checkout profiles
resolve runtime data to `var/iris/` in the repository. An installed package used
outside a checkout falls back to its bundled profile, whose storage root is
`~/.iris`; run manifests in that mode hash the installed `iris` package tree so
code provenance does not collapse to an empty digest. `doctor` and `config-show`
reveal the selected file and resolved paths.
The `general.campaign` value is an artifact label; enforced thresholds and
services come from the rest of that TOML file. `iris.campaigns` exposes only
advisory research sketches and does not activate or override operational policy.
Keep credentials outside configuration files and generated artifacts.

## Safety contract

A candidate is not reportable unless all of the following are true:

1. Every configured mandatory external check completed, returned an explicit
   clear result, its auditable response provenance is intact, its query is bound to
   this candidate and policy, and its evidence has not expired.
2. No known-object or variable-source veto matched.
3. The configured candidate-quality gate passed.
4. No unresolved host/catalogue ambiguity remains. The current local workflow has
   a separate exact-version adjudication ledger: at least one active
   `clear_context` and no active `reject` are required when
   `manual_review_required` is true. Ordinary approvals alone do not resolve it.
5. A screener and the configured number of reviewers approved this exact immutable
   candidate version in the ledger, with at least one reviewer different from the
   screener; reporting preflight recomputes the reviewed evidence binding.

Missing credentials, missing dependencies, timeouts, malformed responses,
disabled services, and stale evidence all block reporting. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the implementation boundaries.
The current automated local quality gate checks the configured minimum count of
valid detections, the presence of at least one valid passband, and whether all
measurements lack critical fields. It also fails when every detection measurement
uncertainty is missing or invalid. Partial uncertainty missingness remains visible
and lowers the heuristic quality component but does not alone fail this local gate.
A production campaign must still define a calibrated uncertainty/significance
policy and require explicit difference/reference-image review before external
reporting; `verify --quality-passed` is a human/upstream assertion, not an
image-analysis result computed by IRIS.

## TS-JEPA: research and shadow mode only

IRIS includes a joint-embedding predictive architecture for irregular light
curves. It learns to predict representations of hidden contiguous time windows
from the remaining observations. The supplied configuration keeps it disabled by
default; the research profile enables it with `shadow_mode = true`. For each mask,
value and uncertainty scaling is re-derived from unmasked context (detected context
when available), and missing uncertainty is represented by an explicit zero
sentinel rather than imputed from the hidden window. Flux inputs require explicit
detection flags. The training command enforces chronological separation by default,
uses deterministic algorithms unless explicitly opted out, and evaluates multiple
seeded masks rather than treating one random mask as a stable estimate. Tokenized
curves declare `iris.light_curve_tokens.v3`, the ordered token fields, band
vocabulary/policy, value kind/direction, normalization, truncation, ordering, and
missing-value/error semantics in a hashed per-curve contract. An explicit
`value_present` token field distinguishes a measured zero or finite non-detection
from an epoch with no value; collation refuses to mix
different or partially missing contract provenance. Training, evaluation, and
embedding extraction also reject a contract change between batches and return the
observed run-level digest. `jepa-train` requires the train and validation digests
to match, verifies the runtime-reported digests, and embeds the full contract and
SHA-256 in checkpoint metadata.

JEPA embeddings may support analogue retrieval, anomaly triage, or a later
supervised model. They do **not** bypass deterministic checks, alter reportability,
or establish that an event is astrophysical. Promotion beyond shadow mode requires
chronological backtests, ablations, calibration of any downstream predictor, and
a prospective campaign as defined in the scientific validation plan.

## Repository layout

| Path | Purpose |
|---|---|
| `src/iris/` | New modular platform; canonical target for development |
| `configs/` | Validated TOML run profiles |
| `tests/` | Unit and safety-regression tests |
| `docs/` | Architecture, validation, migration, and roadmap |
| root `*.py` scripts | Original I SPY workflow retained for comparison during migration |
| `cool-stuff-master/` | Read-only historical duplicate; not a second implementation target |
| `paper/` | Research-paper material, separate from executable evidence |

## Legacy I SPY workflow

The original scripts remain available so prior campaigns can be understood and
reproduced where their upstream services still permit it:

| Legacy stage | Script | Historical role |
|---|---|---|
| Sweep | `run_1000_candidate_hunt.py` | Wrapper for a broker candidate sweep |
| Intake | `ai_candidate_hunter.py` | ALeRCE selection and legacy feature ranking |
| Fetch | `fetch_alerce_detections.py` | ALeRCE/ZTF detection download |
| Features | `optical_transient_pipeline.py` | Single-target light-curve analysis |
| Catalogue screen | `catalog_validation_engine.py` | Stellar/variable-source screening |
| Verification | `verify_candidates.py` | SkyBoT, broker, and TNS checks |
| Final gate | `final_candidate_filter.py` | Legacy reportability filter |
| Draft package | `build_tns_report.py` | Retired, fail-closed tombstone; never constructs report material |

These scripts are not the canonical IRIS architecture and should not be mixed
stage-by-stage with new package outputs without an explicit schema adapter. In
particular, legacy scores are not interchangeable with the new heuristic priority.
Follow [`docs/MIGRATION.md`](docs/MIGRATION.md) for a safe transition.

The root and archived-duplicate `build_tns_report.py` entry points are deliberately
disabled. Every invocation exits before reading candidate data, making network calls,
or writing files. The pre-IRIS implementation is retained only as non-executable
provenance in [`legacy_build_tns_report_historical.md`](legacy_build_tns_report_historical.md);
it predates exact candidate-version binding and the current reporting preflight. IRIS
does not currently expose a TNS report builder or submission transport.

The historical operating procedures remain useful context:

- [`TRANSIENT_DETECTION_PLAYBOOK.md`](TRANSIENT_DETECTION_PLAYBOOK.md)
- [`ISPY_SUBMISSION_PROTOCOL.md`](ISPY_SUBMISSION_PROTOCOL.md)
- [`PIPELINE_OPERATIONS_RECORD.md`](PIPELINE_OPERATIONS_RECORD.md)

Reporting group: **I Spy** (historically documented as TNS group ID `204`). Verify
all live service identifiers and reporting policy with the service before use.

## Data sources and credentials

The legacy workflow references the public ZTF alert stream through ALeRCE, IRSA
ZTF light curves, IMCCE SkyBoT, JPL small-body data, SIMBAD, VSX, and TNS. Live
availability, schemas, rate limits, and terms are external operational
dependencies. TNS credentials must be supplied at runtime and never committed;
the new `TNSClient` implements search only, not submission.

## Further documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — components, boundaries, state,
  and safety invariants.
- [`docs/AUDIT_2026-09-06.md`](docs/AUDIT_2026-09-06.md) — strengths, resolved
  defects, remaining limits, verification evidence, and extension priorities.
- [`docs/SCIENTIFIC_VALIDATION.md`](docs/SCIENTIFIC_VALIDATION.md) — the evidence
  required before scientific or operational claims.
- [`docs/MIGRATION.md`](docs/MIGRATION.md) — staged migration from the root scripts.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — prioritized work from platform foundation
  to prospective operation and beyond.
# IRIS-Space
