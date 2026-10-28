"""Exploratory panel; all locations fixed by geometry before compression."""
import csv, hashlib, json, time, sys
from pathlib import Path
import imagecodecs, numpy as np, openslide, tifffile
from wsi_jxl.codec import encode_tile, decode_tile

out = Path('results')
source = Path('data/CMU-1.svs')
records=[]
with openslide.OpenSlide(str(source)) as slide:
    w,h = slide.dimensions
    for j,y in enumerate(np.linspace(0,h-512,7,dtype=int)):
        for i,x in enumerate(np.linspace(0,w-512,7,dtype=int)):
            rgb=np.asarray(slide.read_region((int(x),int(y)),0,(512,512)).convert('RGB'))
            baseline,bs=encode_tile(rgb,effort=7)
            candidate,stats=encode_tile(rgb,adaptive=True,effort=7)
            start=time.perf_counter(); decoded=decode_tile(candidate); dec_time=time.perf_counter()-start
            if not np.array_equal(decoded,rgb):raise RuntimeError('Lossless mismatch')
            records.append({'x':int(x),'y':int(y),'rgb_bytes':len(baseline),
                'lift_bytes':stats['lift_bytes'],'selected_bytes':len(candidate),
                'mode':stats['selected_mode'],'baseline_seconds':bs['encode_seconds'],
                'search_seconds':stats['encode_seconds'],'decode_seconds':dec_time,
                'tissue_proxy':float(np.mean(np.min(rgb,axis=2)<200)),
                'pixel_sha256':hashlib.sha256(rgb.tobytes()).hexdigest()})
            if len(records)%7==0:print('pixel tiles',len(records),flush=True)
with (out/'pixel-probe.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=records[0],lineterminator='\n');writer.writeheader();writer.writerows(records)
print('PIXEL_SUMMARY',json.dumps({'baseline_bytes':sum(r['rgb_bytes'] for r in records),
    'adaptive_bytes':sum(r['selected_bytes'] for r in records),
    'lift_wins':sum(r['mode']=='lift' for r in records)}),flush=True)

jpeg_stats=[];all_segments=[];seen={};duplicate_bytes=0
with tifffile.TiffFile(source) as tf,source.open('rb') as f:
    for page_index,page in enumerate(tf.pages):
        for k,(offset,length) in enumerate(zip(page.dataoffsets,page.databytecounts)):
            all_segments.append((int(offset),int(length),page_index,k,int(page.compression)))
    selected=set(np.linspace(0,len(all_segments)-1,96,dtype=int))
    blocks=[]
    for n,(offset,length,page_index,k,compression) in enumerate(sorted(all_segments)):
        f.seek(offset);data=f.read(length);digest=hashlib.sha256(data).digest()
        if digest in seen:duplicate_bytes+=length
        seen[digest]=n
        if n not in selected or compression!=7:continue
        start=time.perf_counter()
        try:
            enc=imagecodecs.jpegxl_encode_jpeg(data,numthreads=1)
            dec=imagecodecs.jpegxl_decode_jpeg(enc,numthreads=1)
            if dec!=data:raise RuntimeError('JPEG reconstruction mismatch')
        except Exception as exc:
            print('TRANSCODE_ERROR',page_index,k,str(exc),flush=True);continue
        secs=time.perf_counter()-start
        jpeg_stats.append({'page':page_index,'segment':k,'jpeg':length,'jxl':len(enc),'seconds':secs})
        blocks.append((data,enc))
    batches=[]
    for start in range(0,len(blocks),16):
        block=blocks[start:start+16]
        def packed(which):
            return b''.join(len(pair[which]).to_bytes(4,'little')+pair[which] for pair in block)
        jpeg=packed(0);jxl=packed(1)
        batches.append({'jpeg':len(jpeg),'jxl':len(jxl),
            'jpeg_zstd':len(imagecodecs.zstd_encode(jpeg,level=9)),
            'jxl_zstd':len(imagecodecs.zstd_encode(jxl,level=9))})
summary={'source_bytes':source.stat().st_size,'segments':len(all_segments),'exact_duplicate_bytes':duplicate_bytes,
    'unique_segments':len(seen),'jpeg_probe':jpeg_stats,'batches':batches,'libjxl':imagecodecs.jpegxl_version(),
    'imagecodecs':imagecodecs.__version__}
(out/'jpeg-probe.json').write_text(json.dumps(summary,indent=2))
print('JPEG_SUMMARY',json.dumps({k:summary[k] for k in ['segments','exact_duplicate_bytes','unique_segments','batches','libjxl']}),flush=True)
