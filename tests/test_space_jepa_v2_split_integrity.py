import pytest

from siderea.research.space_jepa_v2_split_integrity import verify_prepared_splits
from space_jepa_v2_split_fixture import prepared_fixture


def test_split_integrity_binds_exact_prepared_files(tmp_path):
    root, source, protocol = prepared_fixture(tmp_path)
    report = verify_prepared_splits(root, source, protocol)
    assert report["status"] == "PASS"
    assert report["pairwise_entity_disjoint"] is True
    assert report["scope"] == "integrity_only_no_model_execution"


def test_split_integrity_rejects_post_manifest_tensor_drift(tmp_path):
    root, source, protocol = prepared_fixture(tmp_path)
    path = root / "train.pt"
    path.write_bytes(path.read_bytes() + b"drift")
    with pytest.raises(ValueError, match="train.pt digest differs"):
        verify_prepared_splits(root, source, protocol)
