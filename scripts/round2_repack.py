import json
from pathlib import Path
from wsi_jxl.repack import repack_archive

configs=[('e7-large','results/cmu1-jxl-baseline.wjxl',64,'zstd',(9,)),
         ('e9-large','results/cmu1-e9-jxl-baseline.wjxl',16,'zstd',(9,)),
         ('e9-search','results/cmu1-e9-jxl-baseline.wjxl',16,'search',(9,15,19))]
for name,baseline,merge,outer,levels in configs:
    report=repack_archive('data/CMU-1.svs',baseline,f'results/cmu1-{name}.wjxl',
                          merge_groups=merge,outer=outer,zstd_levels=levels,
                          progress=lambda r: print(json.dumps({'experiment':name,**r}),flush=True))
    Path(f'results/cmu1-{name}-encode.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='group_records'}),flush=True)
