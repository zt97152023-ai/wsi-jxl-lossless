"""One new encoder-only candidate on the existing 48-tile development panel."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time

from wsi_jxl.archive import source_spans
from wsi_jxl.coeffpacket import encode_svs_batch, decode_svs_batch

root = Path('results')
pilot = json.loads((root / 'round5-pilot.json').read_text())
ridge = json.loads((root / 'round5-ridge-control.json').read_text())
out = root / 'round6-packets'
out.mkdir(exist_ok=True)
source = Path('data/CMU-1.svs')
spans = {s.segment: s for s in source_spans(source) if s.page == 0}


def run(row):
    group = [spans[i] for i in row['segments']]
    raw = []
    with source.open('rb') as f:
        for s in group:
            f.seek(s.offset)
            raw.append(f.read(s.length))
    jpegs = [s.prefix + b[2:] if s.prefix else b for s, b in zip(group, raw)]
    start = time.perf_counter()
    packet = encode_svs_batch(jpegs, [len(s.prefix) for s in group], layout='mosaic',
                              color_context='dc4', color_objective='weak_entropy', effort=10)
    elapsed = time.perf_counter() - start
    assert decode_svs_batch(packet) == raw
    path = out / f"pilot-{row['batch']}-weak_entropy.cjt"
    with path.open('xb') as f:
        f.write(packet)
    result = copy.deepcopy(row)
    result['variants'] = {'weak_entropy': {'packet': str(path), 'bytes': len(packet),
                                          'seconds': elapsed, 'verified': True}}
    print(json.dumps({'batch': row['batch'], **result['variants']['weak_entropy']}), flush=True)
    return result


with ThreadPoolExecutor(max_workers=3) as pool:
    rows = list(pool.map(run, pilot['rows']))
total = sum(r['variants']['weak_entropy']['bytes'] for r in rows)
report = {'note': 'Exploratory development-only probe. Same 48 previously used tiles. No independent validation or full-file integration of this operator. Timing includes concurrent encoding.',
          'config': {'layout': 'mosaic', 'color_context': 'dc4',
                     'color_objective': 'weak_entropy', 'effort': 10},
          'bytes': total, 'weak_ridge_bytes': ridge['bytes'],
          'entropy_bytes': pilot['summaries']['entropy']['bytes'],
          'saved_vs_weak_ridge_percent': 100 * (1 - total / ridge['bytes']),
          'saved_vs_entropy_percent': 100 * (1 - total / pilot['summaries']['entropy']['bytes']),
          'rows': rows}
(root / 'round6-weak-entropy.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'rows'}), flush=True)
