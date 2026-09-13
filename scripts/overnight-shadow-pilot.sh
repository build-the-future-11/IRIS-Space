#!/usr/bin/env bash
# Run the cutoff-bound shadow pilot with only explicit, externally supplied inputs.
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"

python_bin=${PYTHON_BIN:-.venv/bin/python}
run_id=${RUN_ID:-"overnight-$(date -u +%Y%m%dT%H%M%SZ)"}
run_root=${RUN_ROOT:-"runs/$run_id"}

required=(RAW_PHOTOMETRY TRAIN_JSONL VALIDATION_JSONL REFERENCE_JSONL PREDICTION_CUTOFF_MJD FLUX_UNIT CALIBRATION SURVEY_OBJECT_COUNT PLANNED_LOOKS AUDIT_SEED)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    printf 'Missing required environment variable: %s\n' "$name" >&2
    exit 2
  fi
done
for path_var in RAW_PHOTOMETRY TRAIN_JSONL VALIDATION_JSONL REFERENCE_JSONL; do
  if [[ ! -f "${!path_var}" ]]; then
    printf '%s is not a readable file: %s\n' "$path_var" "${!path_var}" >&2
    exit 2
  fi
done
if [[ ! -x "$python_bin" ]]; then
  printf 'PYTHON_BIN is not executable: %s\n' "$python_bin" >&2
  exit 2
fi
if [[ -e "$run_root" ]]; then
  printf 'Run output already exists and will not be overwritten: %s\n' "$run_root" >&2
  exit 2
fi

epochs=${EPOCHS:-10}
evaluation_masks=${EVALUATION_MASKS:-20}
null_trials=${NULL_TRIALS:-99999}
null_method=${NULL_METHOD:-gaussian}
wild_block_size=${WILD_BLOCK_SIZE:-1}
seed=${SEED:-20260913}
budget=${BUDGET:-30}
detector_slots=${DETECTOR_SLOTS:-8}
jepa_slots=${JEPA_SLOTS:-8}
audit_slots=${AUDIT_SLOTS:-4}
jepa_threshold=${JEPA_THRESHOLD:-0.80}
selection_policy=${REFERENCE_SELECTION_POLICY:-'frozen training-only anomaly reference cohort'}

mkdir -p "$run_root"
printf '%s\n' "$run_id" > "$run_root/run-id.txt"
env | LC_ALL=C sort | grep -E '^(AUDIT_SEED|BUDGET|CALIBRATION|DETECTOR_SLOTS|EPOCHS|EVALUATION_MASKS|FLUX_UNIT|JEPA_|NULL_TRIALS|PLANNED_LOOKS|PREDICTION_CUTOFF_MJD|REFERENCE_|RUN_ID|SEED|SURVEY_OBJECT_COUNT)=' > "$run_root/invocation.env"

"$python_bin" -m siderea doctor --config configs/jepa.toml --json > "$run_root/doctor.json"
"$python_bin" -m siderea pilot-prepare "$RAW_PHOTOMETRY" "$run_root/prepared" --prediction-cutoff-mjd "$PREDICTION_CUTOFF_MJD" --flux-unit "$FLUX_UNIT" --calibration "$CALIBRATION" --entity-column "${ENTITY_COLUMN:-physical_entity_id}" --detection-column "${DETECTION_COLUMN:-detected}" --require-pipeline-view > "$run_root/pilot-prepare.json"
"$python_bin" -m siderea analyze "$run_root/prepared/pipeline_photometry.csv" --output-dir "$run_root/pipeline" --ledger "$run_root/outcomes.sqlite" --run-id "$run_id" > "$run_root/analyze.json"
"$python_bin" -m siderea jepa-train "$TRAIN_JSONL" "$VALIDATION_JSONL" "$run_root/jepa-model" --config configs/jepa.toml --require-prediction-cutoffs --epochs "$epochs" --evaluation-masks "$evaluation_masks" --device cpu > "$run_root/jepa-train.json"
"$python_bin" -m siderea jepa-reference-freeze "$REFERENCE_JSONL" "$run_root/reference-cohort.json" --cohort-id "$run_id-reference" --selection-policy "$selection_policy"
"$python_bin" -m siderea transient-search "$run_root/prepared/detector_flux.csv" "$run_root/transient.json" --prediction-cutoff-mjd "$PREDICTION_CUTOFF_MJD" --null-trials "$null_trials" --null-method "$null_method" --wild-block-size "$wild_block_size" --seed "$seed" --survey-object-count "$SURVEY_OBJECT_COUNT" --planned-looks "$PLANNED_LOOKS" --look-index 1
"$python_bin" -m siderea jepa-embed "$run_root/jepa-model/checkpoint.pt" "$REFERENCE_JSONL" "$run_root/reference-embeddings.json" --reference-cohort "$run_root/reference-cohort.json" --device cpu
"$python_bin" -m siderea jepa-embed "$run_root/jepa-model/checkpoint.pt" "$run_root/prepared/jepa.jsonl" "$run_root/candidate-embeddings.json" --device cpu
"$python_bin" -m siderea shadow-assemble "$run_root/transient.json" "$run_root/candidate-embeddings.json" "$run_root/reference-embeddings.json" "$run_root/shadow-evidence.json" --pipeline-candidates "$run_root/pipeline/$run_id/candidates.json" --pipeline-manifest "$run_root/pipeline/$run_id/manifest.json" --pilot-manifest "$run_root/prepared/manifest.json" --reference-cohort "$run_root/reference-cohort.json"
"$python_bin" -m siderea shadow-rank "$run_root/shadow-evidence.json" "$run_root/shadow-queue.json" --budget "$budget" --detector-slots "$detector_slots" --jepa-slots "$jepa_slots" --jepa-threshold "$jepa_threshold" --audit-slots "$audit_slots" --audit-seed "$AUDIT_SEED"

printf 'Completed shadow-only overnight run: %s\n' "$run_root"
