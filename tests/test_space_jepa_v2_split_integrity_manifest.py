import json

import pytest

from siderea.provenance import digest_value, stable_json
from siderea.research.space_jepa_v2_split_integrity import verify_prepared_splits
from space_jepa_v2_split_fixture import prepared_fixture


def test_split_integrity_rejects_rebased_wrong_entity_manifest(tmp_path):
    root, source, protocol = prepared_fixture(tmp_path)
    path = root / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["splits"]["validation"]["entities"] = ["e2"]
    identity = dict(manifest)
    identity.pop("result_digest")
    manifest["result_digest"] = digest_value(identity)
    path.write_text(stable_json(manifest) + "\n")
    with pytest.raises(ValueError, match="validation entities differ"):
        verify_prepared_splits(root, source, protocol)


def test_split_integrity_rejects_source_drift(tmp_path):
    root, source, protocol = prepared_fixture(tmp_path)
    source.write_text(source.read_text() + "\n")
    with pytest.raises(ValueError, match="source digest differs"):
        verify_prepared_splits(root, source, protocol)
