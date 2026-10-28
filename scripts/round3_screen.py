"""Whole-slide layout screening including every permutation/index byte."""
import json,time
from pathlib import Path
import imagecodecs
from wsi_jxl.archive import GROUP
from wsi_jxl.layout import load_records,extract_features,make_order,partition,pack_index

metadata,records=load_records('results/cmu1-e9-jxl-baseline.wjxl')
cache=Path('results/round3-features-rgb.json')
if cache.exists():features={int(k):v for k,v in json.loads(cache.read_text()).items()}
else:
    features=extract_features('data/CMU-1.svs',progress=lambda r:print(json.dumps(r),flush=True))
    cache.write_text(json.dumps(features,separators=(',',':'))+'\n')
metadata['format']=2
header_size=12+len(json.dumps(metadata,sort_keys=True,separators=(',',':')).encode())
rows=[]
for method in ('original','morton','length','appearance','appearance_fine','shuffle'):
    start=time.perf_counter();order=make_order(records,features,method);groups=partition(records,order)
    raw_index,index=pack_index(records,order,groups)
    fixed=header_size+16+len(index)+len(groups)*GROUP.size
    total={'zstd15':fixed,'brotli9':fixed};group_rows=[]
    for group in groups:
        packed=b''.join(records[i].data for i in group)
        a=imagecodecs.zstd_encode(packed,level=15)
        b=imagecodecs.brotli_encode(packed,level=9)
        assert imagecodecs.zstd_decode(a)==packed
        assert imagecodecs.brotli_decode(b)==packed
        total['zstd15']+=len(a);total['brotli9']+=len(b)
        group_rows.append({'records':len(group),'source_bytes':sum(records[i].length for i in group),
                           'jxl_record_bytes':len(packed),'zstd15':len(a),'brotli9':len(b)})
    row={'method':method,'archive_bytes':total,'index_bytes':len(index),'groups':len(groups),
         'seconds':time.perf_counter()-start,'group_records':group_rows}
    rows.append(row);print(json.dumps({k:v for k,v in row.items() if k!='group_records'}),flush=True)
Path('results/round3-layout-screen-rgb.json').write_text(json.dumps({'source_sha256':metadata['source_sha256'],
    'feature_source':'Full decoded RGB of all tiled JPEG pages; TIFF Photometric honored. Fixed color/darkness/gradient proxies, no diagnostic labels',
    'records':len(records),'rows':rows,'note':'Exact byte accounting for planned indexed container; finalists require actual emission and whole-file recovery.'},indent=2)+'\n')
