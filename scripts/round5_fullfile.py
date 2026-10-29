"""Sequential complete-crop comparison; run after other codec workloads finish."""
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics

import numpy as np
import openslide

from wsi_jxl.archive import decode_archive
from wsi_jxl.joint_archive import encode_joint_archive
from wsi_jxl.reader import ArchiveReader

source = Path('data/CMU-1-Small-Region.svs')
original = source.read_bytes()
order = np.random.default_rng(202610298).permutation(['dc4', 'entropy', 'mc_none_bias', 'weak_ridge']).tolist()
rows = []
for mode in order:
    path = Path(f'results/round5-small-{mode}.wjxl')
    load_before = os.getloadavg()
    result = encode_joint_archive(source, path, policy='adaptive', group_tiles=16,
                                   coefficient_mode=mode, effort=10,
                                   progress=lambda r: print(json.dumps({'mode': mode, **r}), flush=True))
    restored = Path(f'results/round5-small-{mode}-restored.svs')
    restored_result = decode_archive(path, restored)
    assert restored.read_bytes() == original
    times = []
    for repeat in range(3):
        decoded = decode_archive(path)
        assert decoded['verified']
        times.append(decoded['seconds'])
    rng = np.random.default_rng(202610299)
    with ArchiveReader(path) as reader:
        for _ in range(20):
            length = int(rng.integers(1, 8193))
            offset = int(rng.integers(0, len(original) - length + 1))
            reader.seek(offset)
            assert reader.read(length) == original[offset:offset + length]
    with openslide.OpenSlide(str(source)) as a, openslide.OpenSlide(str(restored)) as b:
        assert a.dimensions == b.dimensions and a.level_dimensions == b.level_dimensions
    with path.open('rb') as stream:
        archive_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
    result.update({'archive': str(path), 'restored': str(restored), 'exact': True,
                    'archive_sha256': archive_sha256,
                    'restore_result': restored_result, 'decode_repeat_seconds': times,
                    'median_decode_seconds': statistics.median(times), 'random_reads': 20,
                    'load_before': load_before, 'load_after': os.getloadavg()})
    rows.append(result)
    Path(f'results/round5-small-{mode}.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('rows',)}), flush=True)
baseline = next(r for r in rows if r['coefficient_mode'] == 'dc4')
report = {'source': str(source), 'source_sha256': hashlib.sha256(original).hexdigest(),
          'order': order, 'order_seed': 202610298, 'platform': platform.platform(),
          'note': 'One sequential encode per mode; three warmed decode checks. No other task encoding during this run. OS load/cache not isolated. Complete crop only, not a new independent slide.',
          'summaries': {r['coefficient_mode']: {'bytes': r['archive_bytes'],
                         'saving_vs_dc4_percent': 100 * (1 - r['archive_bytes'] / baseline['archive_bytes']),
                         'encode_seconds': r['seconds'], 'median_decode_seconds': r['median_decode_seconds']}
                        for r in rows}, 'rows': rows}
Path('results/round5-fullfile.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report['summaries']), flush=True)
