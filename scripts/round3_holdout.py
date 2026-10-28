"""Frozen coefficient configurations, new tiles, matched generic-color controls."""
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,time
from pathlib import Path
import numpy as np,imagecodecs
from wsi_jxl.layout import load_records
from wsi_jxl.archive import source_spans
from wsi_jxl.coeffpacket import encode_svs_batch,decode_svs_batch

root=Path('results');out=root/'round3-packets';out.mkdir(exist_ok=True)
features={int(k):v for k,v in json.loads((root/'round3-features-rgb.json').read_text()).items()}
dev=json.loads((root/'round3-coefficient-refine.json').read_text())
excluded={i for row in dev['rows'] for i in row['segments']}
_,records=load_records(root/'cmu1-e9-jxl-baseline.wjxl');by_offset={r.offset:r for r in records}
spans=[s for s in source_spans('data/CMU-1.svs') if s.page==0 and s.segment not in excluded]
rng=np.random.default_rng(20261029);tasks=[]
with open('data/CMU-1.svs','rb') as f:
    for category in ('background','mixed','tissue'):
        def label(s):
            value=features[s.offset]['foreground']
            return 'background' if value<=.05 else 'tissue' if value>=.8 else 'mixed'
        eligible=[s for s in spans if label(s)==category]
        selected=[eligible[int(i)] for i in rng.choice(len(eligible),48,replace=False)]
        for batch in range(3):
            group=selected[batch*16:(batch+1)*16];jpegs=[];raws=[]
            for s in group:
                f.seek(s.offset);raw=f.read(s.length);raws.append(raw);jpegs.append(s.prefix+raw[2:] if s.prefix else raw)
            tasks.append((category,batch,group,jpegs,raws))

def run(task):
    category,batch,spans,jpegs,raws=task;name=f'{category}-{batch}'
    native=b''.join(by_offset[s.offset].data for s in spans)
    native=imagecodecs.brotli_encode(native,level=11)
    (out/f'{name}.jbr').write_bytes(native)
    options={'layout':'mosaic','effort':10,'value_map':'zigzag'}
    variants={'delta':{'color_delta':True},'fit':{'color_fit':True}}
    if batch==0:variants['none']={}
    row={'category':category,'batch':batch,'segments':[s.segment for s in spans],
         'native_jxl_brotli11_bytes':len(native),'native_packet':str(out/f'{name}.jbr'),
         'raw_lengths':[len(x) for x in raws],
         'raw_sha256':[hashlib.sha256(x).hexdigest() for x in raws],
         'concat_sha256':hashlib.sha256(b''.join(raws)).hexdigest(),'variants':{}}
    for variant,extra in variants.items():
        start=time.perf_counter()
        packet=encode_svs_batch(jpegs,[len(s.prefix) for s in spans],**options,**extra)
        elapsed=time.perf_counter()-start
        assert decode_svs_batch(packet)==raws
        path=out/f'{name}-{variant}.cjt';path.write_bytes(packet)
        row['variants'][variant]={'bytes':len(packet),'packet':str(path),'seconds':elapsed,'verified':True}
    row['frozen_choice']='delta' if category=='background' else 'fit'
    print(json.dumps({k:v for k,v in row.items() if k not in ('raw_lengths','raw_sha256','segments')}),flush=True)
    return row

with ThreadPoolExecutor(max_workers=3) as pool:rows=list(pool.map(run,tasks))
summaries={}
for category in ('background','mixed','tissue','all'):
    subset=[r for r in rows if category=='all' or r['category']==category]
    baseline=sum(r['native_jxl_brotli11_bytes'] for r in subset)
    selected=sum(r['variants'][r['frozen_choice']]['bytes'] for r in subset)
    summaries[category]={'tiles':len(subset)*16,'native_bytes':baseline,'frozen_candidate_bytes':selected,
                         'saving_percent':100*(1-selected/baseline),
                         'delta_bytes':sum(r['variants']['delta']['bytes'] for r in subset),
                         'fit_bytes':sum(r['variants']['fit']['bytes'] for r in subset)}
result={'source_sha256':'00a3d54482cd707abf254fe69dccc8d06b8ff757a1663f1290c23418c480eb30',
        'seed':20261029,'excluded_development_tiles':sorted(excluded),
        'frozen_config':'mosaic, zigzag, JXL Modular effort 10; background delta, mixed/tissue frequency-wise fit',
        'note':'144 tiles excluded from the 48-tile coefficient configuration-development panel, from the SAME slide, not independent-slide validation. Three equally sized proxy strata. All packet/template/model/prefix bytes included; common full-archive framing and permutation index excluded on both sides.',
        'summaries':summaries,'rows':rows}
(root/'round3-holdout.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(summaries),flush=True)
