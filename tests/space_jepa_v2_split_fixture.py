import json
from pathlib import Path
from siderea.provenance import digest_file,digest_value,stable_json
def make_split_fixture(tmp_path):
 source=tmp_path/"survey.csv"
 source.write_text("entity_id,observation_id,observed_at_mjd,available_at_mjd,band,value,value_error,is_detection\n"+"".join(f"e{i},o{i},{60000+i},{60000+i},g,1.0,0.1,True\n" for i in range(6)))
 root=tmp_path/"prepared"; root.mkdir()
 groups={"train":["e0","e1","e2"],"validation":["e3"],"test":["e4","e5"]}
 splits={}
 for name,entities in groups.items():
  path=root/f"{name}.pt"; path.write_bytes((name+"-tensor").encode())
  splits[name]={"entities":entities,"batch_count":1,"sha256":digest_file(path)}
 m={"schema":"siderea.space_jepa_v2_tensor_batches.v1","input_sha256":digest_file(source),"input_dim":7,"horizons_days":[1.0,3.0,7.0,14.0],"band_to_id":{"g":0},"accepted_observations":6,"rejected_rows":0,"splits":splits}
 m["result_digest"]=digest_value(m)
 (root/"manifest.json").write_text(stable_json(m)+"\n")
 return root,source,Path("configs/space-jepa-2-protocol.json")
def rewrite_manifest(root,m):
 x=dict(m); x.pop("result_digest",None); m["result_digest"]=digest_value(x)
 (root/"manifest.json").write_text(stable_json(m)+"\n")
