"""Coding cost of joint coefficients versus native JPEG reconstruction packets."""
import argparse,json,time
from pathlib import Path
import numpy as np,imagecodecs
from wsi_jxl.layout import load_records
from wsi_jxl.archive import source_spans
from wsi_jxl.coeffpacket import encode_batch,decode_batch

parser=argparse.ArgumentParser();parser.add_argument('--refine',action='store_true');args=parser.parse_args()
features={int(k):v for k,v in json.loads(Path('results/round3-features-rgb.json').read_text()).items()}
_,records=load_records('results/cmu1-e9-jxl-baseline.wjxl');by_offset={r.offset:r for r in records}
spans=[s for s in source_spans('data/CMU-1.svs') if s.page==0]
rows=[]
with open('data/CMU-1.svs','rb') as f:
    for category in ('background','mixed','tissue'):
        def label(s):
            q=features[s.offset]['foreground']
            return 'background' if q<=.05 else 'tissue' if q>=.8 else 'mixed'
        eligible=[s for s in spans if label(s)==category]
        selected=[eligible[i] for i in np.linspace(0,len(eligible)-1,16,dtype=int)]
        jpegs=[];originals=[]
        for s in selected:
            f.seek(s.offset);raw=f.read(s.length);originals.append(raw)
            jpegs.append(s.prefix+raw[2:] if s.prefix else raw)
        baseline=b''.join(by_offset[s.offset].data for s in selected)
        row={'category':category,'segments':[s.segment for s in selected],
             'source_bytes':sum(map(len,originals)),
             'native_jxl_brotli11_bytes':len(imagecodecs.brotli_encode(baseline,level=11)),
             'native_jxl_zstd15_bytes':len(imagecodecs.zstd_encode(baseline,level=15)),'candidates':[]}
        configs=[{'layout':l,'color_delta':d,'effort':7} for l in ('frequency','mosaic') for d in (False,True)]
        if args.refine:
            configs=[{'layout':'mosaic','color_delta':not fit,'color_fit':fit,'value_map':mapping,'effort':9}
                     for fit in (False,True) for mapping in ('zigzag','bias')]
        index=0
        while index<len(configs):
            config=configs[index];index+=1
            start=time.perf_counter();packet=encode_batch(jpegs,**config)
            elapsed=time.perf_counter()-start
            decoded=decode_batch(packet)
            assert decoded==jpegs
            recovered=[b'\xff\xd8'+jpeg[len(s.prefix):] if s.prefix else jpeg for s,jpeg in zip(selected,decoded)]
            assert recovered==originals
            row['candidates'].append({**config,'packet_bytes':len(packet),
                                       'bytes_with_prefix_lengths':len(packet)+4*len(selected),
                                       'encode_seconds':elapsed,'verified_jpeg_bytes':True})
            print(json.dumps({'category':category,**row['candidates'][-1]}),flush=True)
            if args.refine and index==4:
                best=min(range(4),key=lambda i:row['candidates'][i]['packet_bytes'])
                configs.append({**configs[best],'effort':10})
        rows.append(row)
Path('results/round3-coefficient-refine.json' if args.refine else 'results/round3-coefficient-probe.json').write_text(json.dumps({'rows':rows,
    'note':'48 distinct tiles, 16 per proxy class. Includes complete template/side information and 4 bytes per tile for SVS-prefix removal; excludes common outer archive framing on both sides. Pilot only, not full-slide size.'},indent=2)+'\n')
