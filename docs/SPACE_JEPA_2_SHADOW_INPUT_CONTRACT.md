# Space JEPA 2 shadow evidence admission

Status: DEVELOPMENT engineering repair, 10 October 2026.
Parent implementation: `15a52801c424784f63b7ac165ea7b2eaed20b434` (PR #40).
Research status and the population-shift boundary remain those of
`SPACE_JEPA_2_PROTOCOL.md` and `SPACE_JEPA_2_PREPARATION_V2.md`.

## Defect and correction

The assembler indexed evaluation rows with a dictionary comprehension before
checking the cohort. Repeated identities were silently overwritten, including
conflicting evidence; a checksum does not establish uniqueness. `float(...)`
also admitted boolean and string errors into review priorities, and the code
did not check the declared row count or horizon alignment.

Admission now requires a bijection between unique, nonblank string candidate and
evaluation identities. The integer `row_count` must match the evidence rows.
Each row requires unique positive numeric horizons and exactly one finite,
nonnegative numeric absolute error per horizon. Numeric strings and booleans
are rejected. Rejection occurs before a shadow artifact is published.

Compliant evaluation v1 and shadow v1 layouts are unchanged: the evaluation
producer already emits `row_count` and `horizons_days`. The existing minimal
benchmark fixture now includes those actual producer fields. Malformed or
ambiguous hand-built artifacts must be corrected at their source; the assembler
does not select a surviving duplicate or infer a missing horizon.

## Executed evidence

```bash
python -m pytest -q tests/test_space_jepa_v2_shadow_integrity.py tests/test_space_jepa_v2_benchmark.py
python -m ruff check src/siderea/research/space_jepa_v2_pipeline.py tests/test_space_jepa_v2_shadow_integrity.py tests/test_space_jepa_v2_benchmark.py
```

The initial 29-case constructed-artifact test set exposed 25 baseline failures
and retained four passing controls. The final set adds two CLI checks: valid
input publishes a shadow-only report, while duplicate input returns an error,
preserves both input files, and creates no output. The exact-head preparation
workflow includes the new tests alongside its existing bounded tensor checks.

Local verification with CPU PyTorch 2.14.1 passed all 56 tests across the new
shadow cases, the existing benchmark/review tests, and the existing preparation,
training, CLI, prequential and optional-import checks, with zero skips. This
includes a one-epoch constructed train/infer/memory/route/benchmark/shadow CLI
exercise; it is a bounded engineering check, not a scientific training campaign.

These checks test ingestion, association, and priority arithmetic. They do not
establish model performance, scientific discovery, astronomical source
independence, or evidence authenticity. The priority remains predictive surprise,
and `reporting_authorized` remains false. No protected outcome evaluation, source
acquisition, training campaign, frozen protocol amendment, or promotion is part
of this correction.
