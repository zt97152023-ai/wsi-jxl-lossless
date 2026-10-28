import json
from pathlib import Path
from wsi_jxl.archive import encode_archive

for size in (16, 32, 128, 256):
    report = encode_archive('data/CMU-1.svs', f'results/cmu1-fixed{size}.wjxl', group_tiles=size,
                            progress=lambda r: print(json.dumps({'group_size':size, **r}),flush=True)
                            if r['groups'] % 100 == 0 else None)
    Path(f'results/cmu1-fixed{size}-encode.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='group_records'}),flush=True)
