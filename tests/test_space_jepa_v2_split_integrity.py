import json
import pytest
from siderea.research.space_jepa_v2_split_integrity import verify_prepared_splits as verify
from space_jepa_v2_split_fixture import make_split_fixture as fixture,rewrite_manifest
def test_split_integrity_passes_bound_fixture(tmp_path):
 r,s,p=fixture(tmp_path); x=verify(r,s,p)
 assert x["status"]=="PASS" and x["pairwise_entity_disjoint"]
 assert {k:v["entities"] for k,v in x["splits"].items()}=={"train":3,"validation":1,"test":2}
def test_split_integrity_rejects_tensor_drift(tmp_path):
 r,s,p=fixture(tmp_path); q=r/"train.pt"; q.write_bytes(q.read_bytes()+b"drift")
 with pytest.raises(ValueError,match="train.pt digest differs"): verify(r,s,p)
def test_split_integrity_rejects_rebased_entity_drift(tmp_path):
 r,s,p=fixture(tmp_path); q=r/"manifest.json"; m=json.loads(q.read_text())
 m["splits"]["validation"]["entities"]=["e2"]; rewrite_manifest(r,m)
 with pytest.raises(ValueError,match="validation entities differ"): verify(r,s,p)
def test_split_integrity_rejects_source_drift(tmp_path):
 r,s,p=fixture(tmp_path); s.write_text(s.read_text()+"\n")
 with pytest.raises(ValueError,match="source digest differs"): verify(r,s,p)
