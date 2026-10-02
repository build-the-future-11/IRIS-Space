"""Read-only provenance verifier for prepared Space JEPA 2 splits."""
import json
from pathlib import Path
from siderea.provenance import digest_file,digest_value
from siderea.research._space_jepa_v2_split_verify import expected_splits
N=("train","validation","test")
def verify_prepared_splits(prepared,source,protocol):
 r=Path(prepared); s=Path(source); m=json.loads((r/"manifest.json").read_text())
 x=dict(m); d=x.pop("result_digest",None)
 if d!=digest_value(x): raise ValueError("manifest digest differs")
 if m.get("input_sha256")!=digest_file(s): raise ValueError("source digest differs")
 p,e=expected_splits(s,protocol)
 if m.get("horizons_days")!=list(p.horizons_days): raise ValueError("horizons differ")
 z=m.get("splits")
 if not isinstance(z,dict) or set(z)!=set(N): raise ValueError("split manifest differs")
 seen=set(); out={}
 for n in N:
  a=z[n].get("entities")
  if not isinstance(a,list) or tuple(a)!=e[n]: raise ValueError(f"{n} entities differ")
  if seen&set(a): raise ValueError("split entity overlap")
  seen.update(a); h=digest_file(r/f"{n}.pt")
  if z[n].get("sha256")!=h: raise ValueError(f"{n}.pt digest differs")
  out[n]={"entities":len(a),"sha256":h}
 return {"schema":"siderea.space_jepa_v2_split_integrity.v1","status":"PASS","protocol_digest":p.protocol_digest,"pairwise_entity_disjoint":True,"splits":out}
