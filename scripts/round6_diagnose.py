"""Measure actual packet overhead and exploratory zero-event predictability."""
import json
from pathlib import Path
import struct

import imagecodecs
import numpy as np
import tifffile

from wsi_jxl.archive import source_spans
from wsi_jxl.coefficients import read_coefficients
from wsi_jxl.coeffpacket import HEADER
from wsi_jxl.operators import context_color, _labels

root = Path('results')

pages = []
for name in ('CMU-1.svs', 'CMU-2.svs', 'CMU-1-Small-Region.svs'):
    path = Path('data') / name
    with tifffile.TiffFile(path) as f:
        rows = [{'page': i, 'shape': list(p.shape), 'compression': p.compression.name,
                 'tiled': p.is_tiled, 'image_bytes': sum(p.databytecounts),
                 'share_of_source_percent': 100 * sum(p.databytecounts) / path.stat().st_size}
                for i, p in enumerate(f.pages)]
    pages.append({'file': name, 'source_bytes': path.stat().st_size, 'pages': rows})
(root / 'round6-page-budgets.json').write_text(json.dumps({
    'note': 'Original encoded image bytecounts, not current WJXL compressed sizes. Associated images are not interchangeable pyramid levels. No layers can be dropped under original-file losslessness.',
    'rows': pages}, indent=2) + '\n')


def parts(path):
    packet = Path(path).read_bytes()
    magic, count = struct.unpack_from('<4sI', packet)
    assert magic == b'SCJ1'
    offset = 8 + 4 * count
    version, side, plain, template, payload = HEADER.unpack_from(packet, offset)
    assert version in (b'CJT1', b'CJT2')
    framing = offset + HEADER.size
    assert framing + side + template + payload == len(packet)
    info = json.loads(imagecodecs.zstd_decode(packet[framing:framing + side], out=plain))
    return {'bytes': len(packet), 'side_bytes': side, 'template_bytes': template,
            'jxl_bytes': payload, 'framing_bytes': framing}, info


budgets = []
for stage in ('pilot', 'holdout', 'cross-slide'):
    main = json.loads((root / f'round5-{stage}.json').read_text())
    suffix = '' if stage == 'pilot' else '-' + stage
    ridge = json.loads((root / f'round5-ridge-control{suffix}.json').read_text())
    for method, experiment in [('entropy', main), ('weak_ridge', ridge)]:
        total = {}
        for row in experiment['rows']:
            sizes, _ = parts(row['variants'][method]['packet'])
            for k, v in sizes.items():
                total[k] = total.get(k, 0) + v
        budgets.append({'stage': stage, 'method': method, **total,
                        'non_jxl_percent': 100 * (1 - total['jxl_bytes'] / total['bytes'])})


def heldout_zero_bits(zero, labels, extra, states, train, test, base_probability=None):
    # Only binary probability estimates are fitted to the training tiles.
    index = labels * states + extra
    size = 4 * states
    counts = np.bincount(index[train].ravel(), minlength=size)
    successes = np.bincount(index[train].ravel(), weights=zero[train].ravel(), minlength=size)
    probability = (successes + 1) / (counts + 2)
    if base_probability is not None:
        empty = counts == 0
        probability[empty] = np.repeat(base_probability, states)[empty]
    p = probability[index[test]]
    bits = -np.where(zero[test], np.log2(p), np.log2(1 - p)).sum()
    return float(bits), probability


def magnitude_bins(x):
    return np.searchsorted([1, 2, 4], np.abs(x.astype(np.int32)), side='right')


pilot = json.loads((root / 'round5-pilot.json').read_text())
spans = {s.segment: s for s in source_spans('data/CMU-1.svs') if s.page == 0}
diagnostics = []
for row in pilot['rows']:
    arrays = []
    with open('data/CMU-1.svs', 'rb') as f:
        for segment in row['segments']:
            span = spans[segment]
            f.seek(span.offset)
            raw = f.read(span.length)
            coefficients, shape = read_coefficients(span.prefix + raw[2:] if span.prefix else raw)
            arrays.append(coefficients)
    width, height = shape['components'][0][:2]
    cube = np.stack(arrays).reshape(len(arrays), 3, height, width, 64)
    _, info = parts(root / f"round5-packets/pilot-{row['batch']}-weak_ridge.cjt")
    model = info['operators']['context_color']
    residual = context_color(cube, model)
    assert np.array_equal(context_color(residual, model, inverse=True), cube)
    labels = _labels(cube, model).reshape(len(arrays), height, width)
    bits = {'dc_frequency': 0., 'plus_same_frequency_channels': 0., 'plus_causal_neighbors': 0.}
    count = 0
    for channel in (0, 2):
        for frequency in range(1, 64):
            target = residual[:, channel, ..., frequency]
            zero = target == 0
            g = magnitude_bins(cube[:, 1, ..., frequency])
            extra = g if channel == 0 else g * 4 + magnitude_bins(cube[:, 0, ..., frequency])
            states = 4 if channel == 0 else 16
            neighbors = np.zeros(target.shape, dtype=np.int32)
            neighbors[:, 1:, :] += target[:, :-1, :] != 0
            neighbors[:, :, 1:] += target[:, :, :-1] != 0
            for fold in (0, 1):
                train = np.arange(len(arrays)) % 2 == fold
                test = ~train
                b, p = heldout_zero_bits(zero, labels, np.zeros_like(labels), 1, train, test)
                bits['dc_frequency'] += b
                b, _ = heldout_zero_bits(zero, labels, extra, states, train, test, p)
                bits['plus_same_frequency_channels'] += b
                b, _ = heldout_zero_bits(zero, labels, extra * 3 + neighbors, states * 3, train, test, p)
                bits['plus_causal_neighbors'] += b
            count += target.size
    stats = {'batch': row['batch'], 'segments': row['segments'], 'binary_events': count,
             'raw_ac_zero_percent': 100 * float((cube[..., 1:] == 0).mean()),
             'residual_ac_zero_percent': 100 * float((residual[..., 1:] == 0).mean()),
             'two_fold_binary_logloss_bits': bits}
    diagnostics.append(stats)
    print(json.dumps({k: v for k, v in stats.items() if k != 'segments'}), flush=True)

report = {'note': 'Exploratory existing 48-tile development panel. Actual JXL byte budgets; binary zero-event logloss is a separate diagnostic, NOT a coding gain estimate. Transmitted residual model uses the whole original group; only binary probability estimates use disjoint training/test tiles.',
          'probability_protocol': 'Two folds by alternating tile position within each existing length group; AC frequencies 1..63, R/B residuals; DC context is the stored dc4 model. Laplace smoothing; empty refined contexts back off to training-only parent. Channel magnitude bins: 0,1,2..3,4+. Neighbor feature: count of nonzero left/top residuals, zero at tile boundaries. Each event scored once. No model-transmission or arithmetic-coder costs counted.',
          'byte_budgets': budgets, 'zero_diagnostics': diagnostics,
          'total_binary_logloss_bits': {k: sum(r['two_fold_binary_logloss_bits'][k] for r in diagnostics) for k in bits},
          'binary_events': sum(r['binary_events'] for r in diagnostics)}
(root / 'round6-diagnostics.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'budgets': budgets, 'binary_bits': report['total_binary_logloss_bits']}), flush=True)
