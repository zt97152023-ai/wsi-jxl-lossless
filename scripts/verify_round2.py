"""Verify each newly emitted archive in a separate Python process."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
from wsi_jxl.reader import ArchiveReader
from wsi_jxl.archive import source_spans

reports={}
expected=json.loads(Path('results/cmu1-encode.json').read_text())['source_sha256']
for name in ('e9-g256','e7-large','e9-large','e9-search'):
    path=Path(f'results/cmu1-{name}.wjxl')
    code='import json,sys; from wsi_jxl.archive import decode_archive; print(json.dumps(decode_archive(sys.argv[1])))'
    run=subprocess.run([sys.executable,'-c',code,str(path)],capture_output=True,text=True,check=True)
    report=json.loads(run.stdout)
    assert report['sha256']==expected and report['bytes']==177552579
    with path.open('rb') as f:report['archive_sha256']=hashlib.file_digest(f,'sha256').hexdigest()
    report['archive_bytes']=path.stat().st_size
    reports[name]=report
    print(json.dumps({'archive':name,**report}),flush=True)

# One explicit highest-resolution JPEG tile access checks the new Brotli path
# through the same seekable interface; this is a functionality check, not a benchmark.
span=next(s for s in source_spans('data/CMU-1.svs') if s.page==0 and s.segment==10000)
with open('data/CMU-1.svs','rb') as original:
    original.seek(span.offset);jpeg=original.read(span.length)
with ArchiveReader('results/cmu1-e9-search.wjxl') as reader:
    reader.seek(span.offset);assert reader.read(span.length)==jpeg
    roi={'page':span.page,'tile':span.segment,'jpeg_bytes':span.length,
         'reconstructed_source_bytes':reader.decoded_source_bytes,'groups_decoded':reader.decoded_groups,
         'equal':True,'note':'single-tile functionality check, not representative ROI timing'}
result={'source_sha256':expected,'archives':reports,'roi_check':roi}
Path('results/round2-verification.json').write_text(json.dumps(result,indent=2)+'\n')
