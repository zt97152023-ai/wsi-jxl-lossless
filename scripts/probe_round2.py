"""Bounded effort and outer-compressor screening before full-slide experiments."""
from collections import Counter
import hashlib,json,lzma,time
from pathlib import Path
import imagecodecs,numpy as np
from wsi_jxl.archive import GROUP,RECORD,read_metadata,source_spans
from wsi_jxl.native import encode_jpeg

source=Path('data/CMU-1.svs')
spans=[s for s in source_spans(source) if s.prefix is not None]
panel=[spans[i] for i in np.linspace(0,len(spans)-1,96,dtype=int)]
efforts=[]
with source.open('rb') as f:
    for span in panel:
        f.seek(span.offset);raw=f.read(span.length)
        jpeg=span.prefix+raw[2:] if span.prefix else raw
        row={'page':span.page,'segment':span.segment,'source_bytes':len(raw),'options':{}}
        for effort in (7,8,9,10):
            start=time.perf_counter();jxl=encode_jpeg(jpeg,effort=effort);elapsed=time.perf_counter()-start
            assert imagecodecs.jpegxl_decode_jpeg(jxl,numthreads=1)==jpeg
            row['options'][effort]={'bytes':len(jxl),'seconds':elapsed}
        efforts.append(row)
    print('EFFORT',json.dumps({e:{'bytes':sum(r['options'][e]['bytes'] for r in efforts),'seconds':sum(r['options'][e]['seconds'] for r in efforts)} for e in (7,8,9,10)}),flush=True)

groups=[];box_totals=Counter();box_unique={}
with Path('results/cmu1-jxl-baseline.wjxl').open('rb') as f:
    read_metadata(f)
    while header:=f.read(GROUP.size):
        mode,raw_size,inner_size,size,checksum=GROUP.unpack(header)
        assert mode==1
        packed=f.read(size);groups.append(packed)
        cursor=0
        while cursor<len(packed):
            tag,_,_,n=RECORD.unpack_from(packed,cursor);cursor+=RECORD.size
            payload=packed[cursor:cursor+n];cursor+=n
            if tag!=1:continue
            pos=0
            while pos<len(payload):
                length=int.from_bytes(payload[pos:pos+4],'big');kind=payload[pos+4:pos+8]
                if length==0:length=len(payload)-pos
                if length<8 or pos+length>len(payload):raise ValueError('Unexpected JXL box layout')
                box=payload[pos:pos+length];pos+=length
                label=kind.decode('latin1')
                box_totals[label]+=len(box)
                box_unique.setdefault(label,{})[hashlib.sha256(box).hexdigest()]=len(box)
box_summary={k:{'total_bytes':v,'unique_bytes':sum(box_unique[k].values()),'unique_boxes':len(box_unique[k])} for k,v in box_totals.items()}
print('BOXES',json.dumps(box_summary),flush=True)

compressors={**{f'zstd{level}':lambda b,level=level:imagecodecs.zstd_encode(b,level=level) for level in (9,15,19,22)},
             'lzma6':lambda b:lzma.compress(b,preset=6),
             'brotli11':lambda b:imagecodecs.brotli_encode(b,level=11)}
outer=[]
for index in np.linspace(0,len(groups)-1,12,dtype=int):
    packed=groups[index];row={'group':int(index),'input_bytes':len(packed),'options':{}}
    for name,compress in compressors.items():
        start=time.perf_counter();encoded=compress(packed);elapsed=time.perf_counter()-start
        decoded=imagecodecs.zstd_decode(encoded) if name.startswith('zstd') else lzma.decompress(encoded) if name.startswith('lzma') else imagecodecs.brotli_decode(encoded)
        assert decoded==packed
        row['options'][name]={'bytes':len(encoded),'seconds':elapsed}
    outer.append(row)
    print('outer groups',len(outer),flush=True)
result={'effort_panel':efforts,'box_summary':box_summary,'outer_panel':outer}
Path('results/round2-probe.json').write_text(json.dumps(result,indent=2)+'\n')
print('OUTER',json.dumps({k:{'bytes':sum(r['options'][k]['bytes'] for r in outer),'seconds':sum(r['options'][k]['seconds'] for r in outer)} for k in compressors}),flush=True)
