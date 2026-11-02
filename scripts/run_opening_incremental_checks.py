#!/usr/bin/env python3
"""Routine post-export checks. Never builds or waits for independent full references.

Start only after the existing incremental export writer has finished. Keep every
partial output; use fresh paths for interrupted repack/delta stages. An already
completed delta/repack is validated and reused, not regenerated.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','parent','child','v1','v2','delta','evidence'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--source-sha256',required=True);p.add_argument('--cutoff',type=int,required=True)
    a=p.parse_args();root=Path(__file__).resolve().parents[1]
    a.evidence.mkdir(parents=True,exist_ok=False)
    with (a.child/'writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        def run(name,args):
            started=time.monotonic()
            with (a.evidence/f'{name}.log').open('x') as log:
                subprocess.run([sys.executable,*map(str,args)],cwd=root,env={**os.environ,'PYTHONPATH':str(root)},stdout=log,stderr=subprocess.STDOUT,check=True)
            with (a.evidence/'events.jsonl').open('a') as f:f.write(json.dumps({'stage':name,'passed':True,'seconds':time.monotonic()-started})+'\n')
        # No deletion or overwrite; partial outputs fail instead of being silently reused.
        if not (a.v2/'manifest.json').exists():run('repack',['scripts/repack_opening_position_graph_v2.py',a.v1,a.v2])
        if not (a.delta/'report.json').exists():run('delta',['scripts/report_opening_incremental_delta.py',a.child,a.delta])
        run('acceptance',['scripts/validate_opening_incremental_release.py','--source',a.source,'--source-sha256',a.source_sha256,'--cutoff',a.cutoff,'--parent',a.parent,'--child',a.child,'--artifact',a.v2,'--delta',a.delta,'--report',a.evidence/'acceptance.json'])
        manifest=json.loads((a.v2/'manifest.json').read_text())
        run('v1-v2-metadata',['scripts/compare_opening_position_graphs.py',a.v1,a.v2,'--states','10000','--games',manifest['games']])
        run('regression',['-m','pytest','-q'])
        run('graph',['scripts/benchmark_opening_position_graph.py',a.v2,'--repeats','20','--result',a.evidence/'graph.json'])
        (a.evidence/'result.json').write_text(json.dumps({'policy':'incremental-integrity-v1','candidate':str(a.v2.resolve()),'dataset_version':manifest['dataset_version'],'pending':['local HTTP oracle','desktop/mobile browser','frontend validation evidence','release approval if requested'],'full_rebuild_comparison':'not required for routine updates'},indent=2)+'\n')

if __name__=='__main__':main()
