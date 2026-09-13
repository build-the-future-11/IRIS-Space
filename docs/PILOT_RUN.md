# Cutoff-bound detector and JEPA pilot

This workflow is a shadow research pilot. It does not establish discovery
probabilities, survey completeness, reportability or production readiness.

## Required input

Use measured, calibrated flux with one row per observation and at least these
columns:

`source_id,survey,band,mjd,flux,flux_error,ra_deg,dec_deg`

The run additionally needs a physical-entity column that resolves aliases, and a
detection-state column for JEPA. An explicit assertion can replace either column,
but only when every source ID is already a physical-event ID or every row is a
detection. Flux units and calibration must be uniform within the prepared input.
Prepare different surveys separately because the current JEPA has no survey
embedding and similarly named filters are not guaranteed to be equivalent.

Every row must be information genuinely available at the declared prediction
cutoff. TNS classifications, follow-up observations and later photometry must not
be copied into a point-in-time input.

## Environment and preflight

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -e '.[ml,dev]'
.venv/bin/python -m siderea doctor --config configs/jepa.toml --json
.venv/bin/python -m pytest -q \
  tests/test_jepa.py tests/test_transient_search.py \
  tests/test_tns_live_qualification.py tests/test_pilot_integration.py
```

TNS registry qualification additionally requires `TNS_API_KEY`, `TNS_BOT_ID`
and `TNS_BOT_NAME`. The current TNS client does not download photometry.

## Prepare one immutable dataset view

```bash
.venv/bin/siderea pilot-prepare raw-photometry.csv runs/pilot-data \
  --prediction-cutoff-mjd 61234.5 \
  --flux-unit uJy \
  --calibration 'survey-release-and-zero-point' \
  --entity-column physical_entity_id \
  --detection-column detected \
  --require-pipeline-view
```

The new directory contains `pipeline_photometry.csv`, `detector_flux.csv`,
`jepa.jsonl`, and `manifest.json`. All three data views use the same canonical
physical entity IDs. The preparation fails on future observations, unknown
passbands, invalid uncertainty, invalid coordinates, multiple surveys per entity,
missing identity, or an existing destination. Preserve the directory without
editing it.

## Run Aadi's operational framework

Run the interpretable feature and heuristic pipeline on its prepared view. It
retains quality state, catalogue gates, candidate versions, and ledger evidence:

```bash
.venv/bin/siderea analyze candidate/pipeline_photometry.csv \
  --output-dir runs/pipeline \
  --ledger runs/outcomes.sqlite
```

Record the emitted `candidates_path`; it is required during combined assembly.
Missing catalogue evidence may block reportability but does not erase review
eligibility.

## Train under strict cutoffs

Training and validation must be separately prepared, entity-disjoint datasets.
The default chronological policy additionally requires every training observation
to precede every validation observation.

```bash
.venv/bin/siderea jepa-train train/jepa.jsonl validation/jepa.jsonl runs/jepa-model \
  --config configs/jepa.toml \
  --require-prediction-cutoffs \
  --epochs 10 --evaluation-masks 20 --device cpu
```

Benchmark a small subset first. This host currently has no CUDA or MPS backend,
so the research configuration runs on CPU.

## Produce separate shadow evidence

Run the detector on the prepared candidate flux and bind the shared cutoff:

```bash
.venv/bin/siderea transient-search candidate/detector_flux.csv runs/transient.json \
  --prediction-cutoff-mjd 61234.5 \
  --null-trials 99999 --seed 20260913 \
  --survey-object-count COMPLETE_PRE_FILTER_DENOMINATOR \
  --planned-looks TOTAL_FIXED_LOOKS --look-index 1
```

The survey count must cover the complete eligible object universe before candidate
filtering. The detector retains its original within-object channel correction and
adds a conservative correction over that object universe and every planned look.
Do not substitute the number of candidates that survived a filter.

Extract embeddings for a training-only anomaly reference population and the
candidate population using the same checkpoint:

```bash
.venv/bin/siderea jepa-embed runs/jepa-model/checkpoint.pt \
  reference/jepa.jsonl runs/reference-embeddings.json
.venv/bin/siderea jepa-embed runs/jepa-model/checkpoint.pt \
  candidate/jepa.jsonl runs/candidate-embeddings.json
```

Assemble the evidence:

```bash
.venv/bin/siderea shadow-assemble \
  runs/transient.json \
  runs/candidate-embeddings.json \
  runs/reference-embeddings.json \
  runs/shadow-evidence.json \
  --pipeline-candidates runs/pipeline/RUN_ID/candidates.json
```

Assembly verifies all input digests, checkpoint/token/code identities, prediction
cutoff, exact candidate entity coverage, embedding width, and candidate/reference
disjointness. Detector p-values and JEPA anomaly ranks remain separate. No fused
probability or automatic reporting decision is generated.

Allocate the finite review budget through explicit, non-overlapping routes:

```bash
.venv/bin/siderea shadow-rank runs/shadow-evidence.json runs/shadow-queue.json \
  --budget 30 \
  --detector-slots 8 \
  --jepa-slots 8 --jepa-threshold 0.80 \
  --audit-slots 4 --audit-seed CAMPAIGN_FIXED_RANDOM_SEED
```

The remaining slots use Aadi's operational heuristic. Detector slots require the
campaign-corrected template excess, JEPA slots require a valid novelty score above
the frozen threshold, and audit slots sample from the complete review-eligible
population. Empty reserves flow back to heuristic priority. The output contains no
combined score and cannot affect the reporting gate.

## Overnight launcher

`scripts/overnight-shadow-pilot.sh` runs the full cutoff-bound workflow into a
new `runs/` directory. It requires all scientific inputs and campaign constants
to be named explicitly, so it cannot accidentally run against a fixture or reuse
an existing output directory. For example:

```bash
RAW_PHOTOMETRY=/data/candidate-photometry.csv \
TRAIN_JSONL=/data/train/jepa.jsonl \
VALIDATION_JSONL=/data/validation/jepa.jsonl \
REFERENCE_JSONL=/data/reference/jepa.jsonl \
PREDICTION_CUTOFF_MJD=61234.5 \
FLUX_UNIT=uJy \
CALIBRATION='survey-release-and-zero-point' \
SURVEY_OBJECT_COUNT=10000 \
PLANNED_LOOKS=1 \
AUDIT_SEED=campaign-fixed-seed \
bash scripts/overnight-shadow-pilot.sh
```

Optional settings include `RUN_ID`, `RUN_ROOT`, `EPOCHS`, `NULL_TRIALS`,
`NULL_METHOD`, `WILD_BLOCK_SIZE`, `BUDGET`, route allocations, and `PYTHON_BIN`.
The launcher is shadow-only;
completion produces a review queue, never a reporting decision.

The dated `paper/research/overnight-smoke-20260913-v3` fixture run completed every
launcher stage with one training epoch and two mask repeats. Earlier immutable
attempts are retained: the first exposed an invalid fixed-target-count invariant
under multiscale masks, and the second rejected an understated object universe.
They are adverse engineering evidence, not successful runs.

For a credential-free engineering qualification at representative local volume,
run `python scripts/run-scale-qualification.py OUTPUT`. It generates a deterministic
500-entity, 16,000-row workload by default and records wall time, per-shard latency,
peak resident memory, artifact growth, quota rejection, digest-corruption detection,
and exact restart from completed shard artifacts. This is a synthetic systems test;
it does not qualify survey noise, external-service quotas, or scientific recovery.

## Required experiment record before interpretation

- Freeze the campaign, eligible population, label taxonomy, primary metric,
  review budget and minimum useful effect before evaluation.
- Include same-survey negative controls, artifacts, variables and unresolved
  outcomes; TNS discoveries alone are not an evaluation population.
- Reserve a model-selection set and one untouched final test set.
- Run multiple JEPA seeds and retain every result.
- Compare heuristic-only, detector-only, JEPA-only and prespecified combined
  ranking at the same review budget.
- Declare the complete survey-object denominator and number of looks before the
  first `transient-search`; never revise them after seeing results.
- Report false selections, misses, censored outcomes, reviewer effort and
  object/night/campaign-aware intervals.
- Obtain independent label and scientific review before making a performance or
  promotion claim.
