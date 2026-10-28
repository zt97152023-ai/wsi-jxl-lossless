import hashlib,json,time
from pathlib import Path
import imagecodecs,numpy as np,tifffile
source=Path('data/CMU-1.svs');segments=[]
with tifffile.TiffFile(source) as tf:
    for pi,p in enumerate(tf.pages):
        if int(p.compression)!=7:continue
        for k,(off,n) in enumerate(zip(p.dataoffsets,p.databytecounts)):
            segments.append((int(off),int(n),pi,k,p.jpegtables))
segments.sort();selected=np.linspace(0,len(segments)-1,96,dtype=int)
records=[];blocks=[]
with source.open('rb') as f:
    for i in selected:
        off,n,pi,k,table=segments[i];f.seek(off);raw=f.read(n)
        prefix=table[:-2] if table else b''
        complete=prefix+raw[2:] if prefix else raw
        start=time.perf_counter()
        jxl=imagecodecs.jpegxl_encode_jpeg(complete,numthreads=1)
        encsec=time.perf_counter()-start
        decoded=imagecodecs.jpegxl_decode_jpeg(jxl,numthreads=1)
        restored=b'\xff\xd8'+decoded[len(prefix):] if prefix else decoded
        if restored!=raw:raise RuntimeError('Exact JPEG mismatch')
        records.append({'page':pi,'segment':k,'jpeg_bytes':len(raw),'jxl_bytes':len(jxl),'encode_seconds':encsec})
        blocks.append((raw,jxl))
summary={'libjxl':imagecodecs.jpegxl_version(),'n':len(records),'jpeg_bytes':sum(x['jpeg_bytes'] for x in records),'jxl_bytes':sum(x['jxl_bytes'] for x in records),'records':records,'batches':[]}
for i in range(0,len(blocks),16):
    batch=blocks[i:i+16]
    def pack(k):return b''.join(len(p[k]).to_bytes(4,'little')+p[k] for p in batch)
    a,b=pack(0),pack(1)
    summary['batches'].append({'jpeg':len(a),'jxl':len(b),'jpeg_zstd':len(imagecodecs.zstd_encode(a,level=9)),'jxl_zstd':len(imagecodecs.zstd_encode(b,level=9))})
Path('results/jpeg-probe-with-tables.json').write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='records'}))
