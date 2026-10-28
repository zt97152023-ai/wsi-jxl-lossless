"""Reproduce the box-factoring and chroma-from-luma ablations."""
import json
from pathlib import Path
import imagecodecs,numpy as np
from wsi_jxl.archive import GROUP,read_metadata,source_spans
from wsi_jxl.boxes import factor_boxes,restore_boxes
from wsi_jxl.native import encode_jpeg

blocks=[]
with Path('results/cmu1-jxl-baseline.wjxl').open('rb') as f:
    read_metadata(f)
    while header:=f.read(GROUP.size):
        mode,_,_,n,_=GROUP.unpack(header)
        assert mode==1
        blocks.append(f.read(n))
rows=[]
for i in range(0,len(blocks),4):
    packed=b''.join(blocks[i:i+4]);factored=factor_boxes(packed)
    assert restore_boxes(factored)==packed
    rows.append({'group':i//4,'packed':len(packed),'factored':len(factored),
                 'zstd9':len(imagecodecs.zstd_encode(packed,level=9)),
                 'box_zstd9':len(imagecodecs.zstd_encode(factored,level=9))})
result={'groups':rows,'sums':{k:sum(x[k] for x in rows) for k in ('packed','factored','zstd9','box_zstd9')}}
Path('results/round2-box-probe.json').write_text(json.dumps(result,indent=2)+'\n')

spans=[s for s in source_spans('data/CMU-1.svs') if s.prefix is not None]
rows=[]
with open('data/CMU-1.svs','rb') as f:
    for i in np.linspace(0,len(spans)-1,96,dtype=int):
        s=spans[i];f.seek(s.offset);raw=f.read(s.length)
        jpeg=s.prefix+raw[2:] if s.prefix else raw;sizes={}
        for cfl in (None,0,1):
            jxl=encode_jpeg(jpeg,effort=9,cfl=cfl)
            assert imagecodecs.jpegxl_decode_jpeg(jxl)==jpeg
            sizes[str(cfl)]=len(jxl)
        rows.append({'page':s.page,'segment':s.segment,'bytes':sizes})
result={'records':rows,'totals':{k:sum(r['bytes'][k] for r in rows) for k in sizes},
        'unsupported_probe':'JPEG_RECON_LFS setting 42 rejected by installed libjxl 0.12.0 with error 128; omitted, not silently emulated'}
Path('results/round2-predictors.json').write_text(json.dumps(result,indent=2)+'\n')
