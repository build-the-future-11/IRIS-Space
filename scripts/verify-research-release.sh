#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 [--allow-dirty] OUTPUT_DIRECTORY" >&2
}

allow_dirty=false
if [[ "${1:-}" == "--allow-dirty" ]]; then
  allow_dirty=true
  shift
fi
if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
output="$1"
python_bin="${PYTHON_BIN:-python3}"

if [[ -e "$output" ]]; then
  echo "release verification output already exists: $output" >&2
  exit 2
fi
mkdir -p "$output/logs" "$output/tmp"
output="$(cd "$output" && pwd)"
cd "$repo_root"

# Keep pytest/sqlite scratch on the output volume. System /tmp on a near-full
# macOS data volume has produced SQLite "disk I/O" failures during release runs.
export TMPDIR="$output/tmp"
export TMP="$output/tmp"
export TEMP="$output/tmp"
export PYTHONPYCACHEPREFIX="$output/tmp/pycache"
mkdir -p "$PYTHONPYCACHEPREFIX"

git rev-parse HEAD >"$output/git-revision.txt"
git status --porcelain=v1 >"$output/git-status.txt"
if [[ -s "$output/git-status.txt" && "$allow_dirty" != true ]]; then
  echo "release verification requires a clean working tree" >&2
  exit 1
fi

run() {
  local name="$1"
  shift
  echo "[$name] $*"
  "$@" >"$output/logs/$name.log" 2>&1
}

run format "$python_bin" -m ruff format --check src tests paper/reconstruct.py \
  paper/experiments/make_tables.py paper/experiments/run_transient_search.py \
  paper/experiments/run_noise_stress.py paper/figures/make_figures.py
run lint "$python_bin" -m ruff check src tests paper/reconstruct.py \
  paper/experiments/make_tables.py paper/experiments/run_transient_search.py \
  paper/experiments/run_noise_stress.py paper/figures/make_figures.py
run mypy "$python_bin" -m mypy src/siderea
run tests "$python_bin" -m pytest -q --cov=siderea --cov-report=term-missing
run compile "$python_bin" -m compileall -q src tests
run doctor env PYTHONPATH=src "$python_bin" -m siderea doctor --strict --json

PYTHONPATH=src "$python_bin" paper/reconstruct.py --output "$output/paper-reconstruction" \
  >"$output/logs/paper-reconstruction.log" 2>&1

PYTHONPATH=src "$python_bin" - "$output" "$allow_dirty" <<'PY'
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

from siderea.manifest import _source_digest

root = pathlib.Path(sys.argv[1])
allow_dirty = sys.argv[2] == "true"
files = sorted(path for path in root.rglob("*") if path.is_file())
digests = {
    str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in files
    if path.name != "release-verification.json"
}
reconstruction = json.loads((root / "paper-reconstruction/reconstruction.json").read_text())
payload = {
    "schema": "siderea.research_release_verification.v1",
    "git_revision": (root / "git-revision.txt").read_text().strip(),
    "dirty": bool((root / "git-status.txt").read_text().strip()),
    "allow_dirty": allow_dirty,
    "code_source_digest": _source_digest(
        pathlib.Path.cwd(), package_root=pathlib.Path.cwd() / "src/siderea"
    ),
    "paper_reconstruction_passed": reconstruction.get("passed") is True,
    "artifact_sha256": digests,
}
(root / "release-verification.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

echo "release verification passed: $output"
