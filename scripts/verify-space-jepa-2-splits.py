#!/usr/bin/env python3
"""Verify prepared Space JEPA 2 split provenance without training or evaluation."""
import argparse,json,sys
from siderea.research.space_jepa_v2_split_integrity import verify_prepared_splits
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__); p.add_argument("prepared"); p.add_argument("source"); p.add_argument("protocol"); a=p.parse_args(argv)
 try: out=verify_prepared_splits(a.prepared,a.source,a.protocol)
 except (OSError,TypeError,ValueError) as e:
  print(json.dumps({"schema":"siderea.space_jepa_v2_split_integrity.v1","status":"FAIL","error":str(e)})); return 2
 print(json.dumps(out,indent=2,sort_keys=True)); return 0
if __name__=="__main__": sys.exit(main())
