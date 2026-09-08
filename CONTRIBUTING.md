# Contributing to SIDEREA

SIDEREA treats scientific claims, failure semantics, and reproducibility metadata as
part of the public API. A change is complete only when the code, tests, schemas,
documentation, and stated evidence boundary agree.

## Development setup

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[all,dev]'
.venv/bin/python -m siderea doctor --strict
make check PYTHON=.venv/bin/python
```

Run a focused test while iterating, then run `make check` before handing off. A
release candidate must additionally pass `python -m build`, install the wheel into
a fresh virtual environment, expose `default.toml` and `py.typed`, and run
`siderea doctor --json` plus `siderea config-show` from outside the checkout.

## Change discipline

- Preserve fail-closed behavior. An error, timeout, disabled service, stale result,
  malformed payload, or missing digest must never become catalogue clearance.
- Keep ranking separate from authorization. Heuristics, anomaly scores,
  supervised models, similarity, and JEPA may prioritize review; none may waive
  quality, external-evidence, human-review, or reporting-preflight gates.
- Add an adversarial regression test for every corrected defect. Do not weaken a
  test to make a change pass, and do not use a toy fixture as evidence of
  scientific performance.
- Treat schemas and scientific fingerprints as contracts. When semantics change,
  version the affected schema or contract and document migration behavior.
- Keep optional imports lazy so the minimal NumPy/pandas package remains usable.
  Use explicit dependency extras and never hide a required dependency behind a
  broad exception.
- Use UTC timestamps, deterministic terminal tie-breaks, atomic/no-clobber
  publication, and content digests for persisted scientific artifacts.
- Keep secrets and private data out of source, configuration, examples, tests,
  logs, and generated dossiers. Follow `SECURITY.md` for private disclosure.

## Evidence expected in a review

State the problem and root cause, list the exact files and schema effects, and
include the commands that verified the change. Clearly separate executed evidence
from assumptions, expected warnings, unavailable live-service validation, and
future work. If a result came from synthetic data, label it synthetic beside the
number rather than in a distant caveat.
