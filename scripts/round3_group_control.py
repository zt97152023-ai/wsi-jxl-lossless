"""Post-holdout grouping ablation on the same 144 tiles, without new tuning.

All candidates use the identical frequency-wise predictor and Modular effort 10.
Packet bytes are real; indexed totals include a serialized compressed index,
but are not a whole-SVS archive. None of these are new independent samples.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time

import imagecodecs
import numpy as np

from wsi_jxl.archive import source_spans
from wsi_jxl.coeffpacket import encode_svs_batch, decode_svs_batch
from wsi_jxl.layout import load_records

root = Path('results')
parser = argparse.ArgumentParser()
parser.add_argument('--only-length', action='store_true', help='Append the length control to existing results')
args = parser.parse_args()
out = root / 'round3-packets'
manifest = json.loads((root / 'round3-holdout.json').read_text())
samples = {segment for row in manifest['rows'] for segment in row['segments']}
spans = {s.segment: s for s in source_spans('data/CMU-1.svs')
         if s.page == 0 and s.segment in samples}
_, records = load_records(root / 'cmu1-e9-jxl-baseline.wjxl')
by_offset = {r.offset: r for r in records}
raws = {}
with open('data/CMU-1.svs', 'rb') as f:
    for index, span in spans.items():
        f.seek(span.offset)
        raws[index] = f.read(span.length)
source_order = sorted(samples)
orders = {'region': [s for row in manifest['rows'] for s in row['segments']],
          'source': source_order,
          'shuffle': np.random.default_rng(20261030).permutation(source_order).tolist(),
          'length': sorted(samples, key=lambda i: (len(raws[i]), i))}


def run(task):
    method, batch, indices = task
    name = f'control-{method}-{batch}'
    original = [raws[i] for i in indices]
    jpegs = [spans[i].prefix + raws[i][2:] if spans[i].prefix else raws[i] for i in indices]
    native = imagecodecs.brotli_encode(b''.join(by_offset[spans[i].offset].data for i in indices), level=11)
    start = time.perf_counter()
    packet = encode_svs_batch(jpegs, [len(spans[i].prefix) for i in indices],
                              layout='mosaic', effort=10, color_fit=True, value_map='zigzag')
    seconds = time.perf_counter() - start
    assert decode_svs_batch(packet) == original
    path = out / f'{name}.cjt'
    path.write_bytes(packet)
    native_path = out / f'{name}.jbr'
    native_path.write_bytes(native)
    row = {'method': method, 'batch': batch, 'segments': indices,
           'packet': str(path), 'native_packet': str(native_path),
           'bytes': len(packet), 'native_bytes': len(native),
           'raw_sha256': [hashlib.sha256(x).hexdigest() for x in original],
           'seconds': seconds, 'verified': True}
    print(json.dumps({k: v for k, v in row.items() if k not in ('segments', 'raw_sha256')}), flush=True)
    return row


tasks = [(method, b // 16, order[b:b + 16]) for method, order in orders.items()
         if method != 'region' and (not args.only_length or method == 'length')
         for b in range(0, len(order), 16)]
with ThreadPoolExecutor(max_workers=3) as pool:
    rows = list(pool.map(run, tasks))
if args.only_length:
    previous = json.loads((root / 'round3-group-control.json').read_text())
    rows.extend(r for r in previous['rows'] if r['method'] in ('source', 'shuffle'))
for b, old in enumerate(manifest['rows']):
    item = old['variants']['fit']
    rows.append({'method': 'region', 'batch': b, 'segments': old['segments'],
                 'packet': item['packet'], 'native_packet': old['native_packet'],
                 'bytes': item['bytes'], 'native_bytes': old['native_jxl_brotli11_bytes'],
                 'raw_sha256': old['raw_sha256'], 'seconds': item['seconds'], 'verified': True})
summaries = {}
for method, order in orders.items():
    # The same source offset/length directory and permutation would serve both
    # codecs. Include actual serialized bytes plus eight-byte payload lengths.
    index = json.dumps({'source_segments': source_order,
                        'offsets': [spans[i].offset for i in source_order],
                        'lengths': [spans[i].length for i in source_order],
                        'order': order, 'batch_size': 16}, separators=(',', ':')).encode()
    compressed_index = imagecodecs.zstd_encode(index, level=9)
    (out / f'control-{method}.index.zst').write_bytes(compressed_index)
    subset = sorted((r for r in rows if r['method'] == method), key=lambda r: r['batch'])
    framing = len(compressed_index) + struct.calcsize('<4sII') + 8 * len(subset)
    candidate = framing + sum(r['bytes'] for r in subset)
    native = framing + sum(r['native_bytes'] for r in subset)
    summaries[method] = {'index_and_framing_bytes': framing, 'candidate_indexed_bytes': candidate,
                         'native_indexed_bytes': native, 'saving_percent': 100 * (1 - candidate / native)}
result = {'note': 'Post-holdout matched grouping ablation, same 144 tiles. Indexed byte ledger, not a whole WSI archive.',
          'config': 'all fit, mosaic, zigzag, Modular effort 10, 16 tiles/packet',
          'shuffle_seed': 20261030, 'summaries': summaries, 'rows': rows}
(root / 'round3-group-control.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(summaries), flush=True)
