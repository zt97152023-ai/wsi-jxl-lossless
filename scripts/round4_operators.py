"""Operator screening and frozen same-slide validation with matched length groups."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import imagecodecs
import numpy as np

from wsi_jxl.archive import source_spans, RECORD
from wsi_jxl.coeffpacket import encode_svs_batch, decode_svs_batch, HEADER
from wsi_jxl.layout import load_records, appearance_features
from wsi_jxl.native import encode_jpeg

ROOT = Path('results')
CONFIGS = {
    'baseline': {'color_fit': True},
    'dc2': {'color_context': 'dc2'},
    'dc4': {'color_context': 'dc4'},
    'texture2': {'color_context': 'texture2'},
    'dc_texture4': {'color_context': 'dc_texture4'},
    'dc_med': {'color_fit': True, 'spatial': 'dc_med'},
    'low_med': {'color_fit': True, 'spatial': 'low_med'},
    'planes': {'color_fit': True, 'layout': 'planes'},
    'zigzag': {'color_fit': True, 'layout': 'zigzag'},
}
CONFIGS5 = {
    'baseline': {'color_context': 'dc4'},
    'gray_bias': {'color_context': 'dc4', 'value_map': 'bias'},
    'entropy': {'color_context': 'dc4', 'color_objective': 'entropy'},
    **{f'mc_{predictor}_{mapping}': {'layout': 'mosaic3', 'value_map': mapping, **options}
       for predictor, options in [('none', {}), ('fit', {'color_fit': True}), ('dc4', {'color_context': 'dc4'})]
       for mapping in ('zigzag', 'bias')},
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('pilot', 'holdout', 'cross-slide'))
    parser.add_argument('--round', dest='round_number', type=int, choices=(4, 5), default=4)
    args = parser.parse_args()
    prefix = f'round{args.round_number}'
    output_directory = ROOT / f'{prefix}-packets'
    output_directory.mkdir(exist_ok=True)
    configurations = CONFIGS5 if args.round_number == 5 else CONFIGS
    cross_slide = args.stage == 'cross-slide'
    source = 'data/CMU-2.svs' if cross_slide else 'data/CMU-1.svs'
    source_sha256 = (json.loads((ROOT / 'round4-source-cmu2.json').read_text())['sha256'] if cross_slide
                     else '00a3d54482cd707abf254fe69dccc8d06b8ff757a1663f1290c23418c480eb30')
    features = {} if cross_slide else {int(k): v for k, v in json.loads((ROOT / 'round3-features-rgb.json').read_text()).items()}
    development = json.loads((ROOT / 'round3-coefficient-refine.json').read_text())
    dev_ids = {i for row in development['rows'] for i in row['segments']}
    spans = [s for s in source_spans(source) if s.page == 0]
    if args.stage == 'pilot':
        chosen = [s for s in spans if s.segment in dev_ids]
        configs = configurations
        selection_note = 'Reused 48 development tiles; exploratory configuration selection.'
    elif not cross_slide:
        protocol = json.loads((ROOT / f'{prefix}-frozen.json').read_text())
        configs = {'baseline': configurations['baseline'], **protocol['candidates']}
        prior = json.loads((ROOT / 'round3-holdout.json').read_text())
        excluded = dev_ids | {i for row in prior['rows'] for i in row['segments']}
        seed = 202610294 if args.round_number == 4 else 202610296
        if args.round_number == 5:
            round4 = json.loads((ROOT / 'round4-holdout.json').read_text())
            excluded |= {i for row in round4['rows'] for i in row['segments']}
        rng = np.random.default_rng(seed)
        chosen = []
        for category in ('background', 'mixed', 'tissue'):
            eligible = [s for s in spans if s.segment not in excluded and label(features[s.offset]) == category]
            chosen.extend(eligible[int(i)] for i in rng.choice(len(eligible), 64, replace=False))
        selection_note = f'192 same-slide tiles excluded from prior panels; 64 per proxy stratum; seed {seed}.'
    else:
        protocol = json.loads((ROOT / f'{prefix}-frozen.json').read_text())
        configs = {'baseline': configurations['baseline'], **protocol['candidates']}
        seed = 202610295 if args.round_number == 4 else 202610297
        if args.round_number == 5:
            round4 = json.loads((ROOT / 'round4-cross-slide.json').read_text())
            excluded = {i for row in round4['rows'] for i in row['segments']}
            spans = [s for s in spans if s.segment not in excluded]
        rng = np.random.default_rng(seed)
        chosen = [spans[int(i)] for i in rng.choice(len(spans), 192, replace=False)]
        selection_note = f'CMU-2: 192 uniformly sampled level-0 tiles, seed {seed}; frozen configs from CMU-1. Previously studied slide; same vendor/source.'
    chosen.sort(key=lambda s: (s.length, s.segment))
    by_offset = {}
    if not cross_slide:
        _, records = load_records(ROOT / 'cmu1-e9-jxl-baseline.wjxl')
        by_offset = {r.offset: r for r in records}
    tasks = []
    with open(source, 'rb') as f:
        for batch in range(0, len(chosen), 16):
            group = chosen[batch:batch + 16]
            raws = []
            for span in group:
                f.seek(span.offset); raws.append(f.read(span.length))
            tasks.append((batch // 16, group, raws))

    def run(task):
        batch, group, raws = task
        name = f'{args.stage}-{batch}'
        jpegs = [s.prefix + raw[2:] if s.prefix else raw for s, raw in zip(group, raws)]
        if cross_slide:
            native_records = []
            for s, raw, jpeg in zip(group, raws, jpegs):
                payload = encode_jpeg(jpeg, effort=9)
                assert imagecodecs.jpegxl_decode_jpeg(payload) == jpeg
                native_records.append(RECORD.pack(1, len(raw), len(s.prefix), len(payload)) + payload)
                features[s.offset] = appearance_features(imagecodecs.jpeg_decode(jpeg, colorspace='RGB', outcolorspace='RGB'))
            native = imagecodecs.brotli_encode(b''.join(native_records), level=11)
        else:
            native = imagecodecs.brotli_encode(b''.join(by_offset[s.offset].data for s in group), level=11)
        native_path = output_directory / f'{name}.jbr'; native_path.write_bytes(native)
        row = {'batch': batch, 'segments': [s.segment for s in group],
               'categories': [label(features[s.offset]) for s in group],
               'raw_lengths': list(map(len, raws)),
               'raw_sha256': [hashlib.sha256(raw).hexdigest() for raw in raws],
               'native_bytes': len(native), 'native_packet': str(native_path), 'variants': {}}
        for method, config in configs.items():
            options = {'layout': 'mosaic', 'effort': 10, 'value_map': 'zigzag', **config}
            start = time.perf_counter()
            packet = encode_svs_batch(jpegs, [len(s.prefix) for s in group], **options)
            elapsed = time.perf_counter() - start
            assert decode_svs_batch(packet) == raws
            path = output_directory / f'{name}-{method}.cjt'; path.write_bytes(packet)
            _, side, plain, template, payload = HEADER.unpack_from(packet, 8 + 4 * len(group))
            row['variants'][method] = {'bytes': len(packet), 'packet': str(path),
                                       'seconds': elapsed, 'side_bytes': side, 'side_plain_bytes': plain,
                                       'template_bytes': template, 'jxl_payload_bytes': payload,
                                       'verified': True}
            print(json.dumps({'batch': batch, 'method': method, **row['variants'][method]}), flush=True)
        return row

    with ThreadPoolExecutor(max_workers=2 if cross_slide else 3) as pool:
        rows = list(pool.map(run, tasks))
    totals = {method: sum(r['variants'][method]['bytes'] for r in rows) for method in configs}
    native = sum(r['native_bytes'] for r in rows)
    summaries = {method: {'bytes': total, 'saving_vs_previous_percent': 100 * (1 - total / totals['baseline']),
                          'saving_vs_native_percent': 100 * (1 - total / native)} for method, total in totals.items()}
    result = {'selection': selection_note, 'configs': configs, 'grouping': 'original JPEG length; 16/packet',
              'note': 'Actual complete packets. All methods share the same source offsets/order; common collection index/full-SVS framing excluded.',
              'source_sha256': source_sha256,
              'native_bytes': native, 'summaries': summaries, 'rows': rows}
    (ROOT / f'{prefix}-{args.stage}.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(summaries), flush=True)


def label(feature):
    value = feature['foreground']
    return 'background' if value <= .05 else 'tissue' if value >= .8 else 'mixed'


if __name__ == '__main__':
    main()
