#!/usr/bin/env python3
"""Validate the routine incremental release gate without full reference builds."""
import argparse,json
from pathlib import Path
from bughouse_explorer.opening.incremental_acceptance import validate_incremental_release
p=argparse.ArgumentParser(description=__doc__)
for name in ('source','parent','child','artifact','delta','report'):p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--source-sha256',required=True);p.add_argument('--cutoff',type=int,required=True)
if __name__=='__main__':
 a=p.parse_args()
 if a.report.exists():raise FileExistsError(a.report)
 result=validate_incremental_release(a.source,a.source_sha256,a.cutoff,a.parent,a.child,a.artifact,a.delta)
 a.report.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result,indent=2,sort_keys=True))
