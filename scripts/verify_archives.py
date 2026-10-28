"""Each decoder runs in a fresh interpreter; source is used only by the auditor."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys

names = ['adaptive','jxl-baseline','tissue','fixed16','fixed32','fixed128','fixed256']
source=Path('data/CMU-1.svs')
with source.open('rb') as f:
    expected=hashlib.file_digest(f,'sha256').hexdigest()

def verify(name):
    path=Path(f'results/cmu1-{name}.wjxl')
    code='import json,sys; from wsi_jxl.archive import decode_archive; print(json.dumps(decode_archive(sys.argv[1])))'
    result=subprocess.run([sys.executable,'-c',code,str(path)],check=True,capture_output=True,text=True)
    report=json.loads(result.stdout)
    assert report['sha256']==expected and report['bytes']==source.stat().st_size
    with path.open('rb') as f:
        report['archive_sha256']=hashlib.file_digest(f,'sha256').hexdigest()
    report['archive_bytes']=path.stat().st_size
    print(json.dumps({'archive':name,**report}),flush=True)
    return name,report

with ThreadPoolExecutor(max_workers=2) as pool:
    reports=dict(pool.map(verify,names))
Path('results/full-verification.json').write_text(json.dumps({
    'note':'Fresh decoder process per file. Two concurrent verifications; these timings are not speed benchmarks.',
    'source_sha256':expected,'archives':reports},indent=2)+'\n')
