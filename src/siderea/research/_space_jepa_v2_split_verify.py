"""Internal source/protocol reconstruction for Space JEPA 2 split checks."""
import pandas as pd
from siderea.ml.space_jepa_v2_data import _observations,chronological_entity_split
from siderea.research.space_jepa_v2_protocol import load_space_jepa_v2_protocol
def expected_splits(source,protocol):
 p=load_space_jepa_v2_protocol(protocol); q=p.payload["split"]
 obs,_=_observations(pd.read_csv(source))
 return p,chronological_entity_split(obs,train_fraction=float(q["train_fraction"]),validation_fraction=float(q["validation_fraction"]),test_fraction=float(q["test_fraction"]))
