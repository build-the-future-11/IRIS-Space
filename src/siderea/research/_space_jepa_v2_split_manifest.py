"""Load and bind a prepared Space JEPA 2 manifest."""

import json
from pathlib import Path

from siderea.ml.space_jepa_v2_data import SPACE_JEPA_V2_TENSOR_SCHEMA
from siderea.provenance import digest_file, digest_value


def load_bound_manifest(prepared: str | Path, source: str | Path):
    root = Path(prepared)
    src = Path(source)
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("schema") != SPACE_JEPA_V2_TENSOR_SCHEMA:
        raise ValueError("prepared manifest schema differs")
    identity = dict(manifest)
    stored = identity.pop("result_digest", None)
    if stored != digest_value(identity):
        raise ValueError("prepared manifest digest differs")
    if manifest.get("input_sha256") != digest_file(src):
        raise ValueError("prepared source digest differs")
    return root, src, manifest, stored
