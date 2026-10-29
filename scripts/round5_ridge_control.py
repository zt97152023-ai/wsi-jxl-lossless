"""Post-hoc mechanism control: weak ridge alone on an already evaluated panel."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import time

from wsi_jxl.archive import source_spans
from wsi_jxl.coeffpacket import encode_svs_batch, decode_svs_batch

root = Path('results')
parser = argparse.ArgumentParser()
parser.add_argument('--stage', choices=('pilot', 'holdout', 'cross-slide'), default='pilot')
args = parser.parse_args()
pilot = json.loads((root / f'round5-{args.stage}.json').read_text())
source = 'data/CMU-2.svs' if args.stage == 'cross-slide' else 'data/CMU-1.svs'
spans = {s.segment: s for s in source_spans(source) if s.page == 0}


def run(row):
    group = [spans[i] for i in row['segments']]
    raws = []
    with open(source, 'rb') as f:
        for s in group:
            f.seek(s.offset); raws.append(f.read(s.length))
    jpegs = [s.prefix + raw[2:] if s.prefix else raw for s, raw in zip(group, raws)]
    start = time.perf_counter()
    packet = encode_svs_batch(jpegs, [len(s.prefix) for s in group], layout='mosaic',
                              color_context='dc4', color_objective='weak_ridge', effort=10)
    seconds = time.perf_counter() - start
    assert decode_svs_batch(packet) == raws
    path = root / f"round5-packets/{args.stage}-{row['batch']}-weak_ridge.cjt"
    path.write_bytes(packet)
    output = copy.deepcopy(row)
    output['variants'] = {'weak_ridge': {'packet': str(path), 'bytes': len(packet),
                                        'seconds': seconds, 'verified': True}}
    print(json.dumps({'batch': row['batch'], **output['variants']['weak_ridge']}), flush=True)
    return output


with ThreadPoolExecutor(max_workers=2 if args.stage == 'cross-slide' else 3) as pool:
    rows = list(pool.map(run, pilot['rows']))
total = sum(r['variants']['weak_ridge']['bytes'] for r in rows)
result = {'note': f'Post-hoc mechanism control on existing {args.stage} panel after observing entropy results. Not a newly held-out panel.',
          'config': {'color_context': 'dc4', 'regularizer': 1e-6, 'layout': 'mosaic', 'effort': 10},
          'bytes': total, 'saving_vs_baseline_percent': 100 * (1 - total / pilot['summaries']['baseline']['bytes']),
          'saving_vs_entropy_percent': 100 * (1 - total / pilot['summaries']['entropy']['bytes']), 'rows': rows}
suffix = '' if args.stage == 'pilot' else '-' + args.stage
(root / f'round5-ridge-control{suffix}.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'rows'}), flush=True)
