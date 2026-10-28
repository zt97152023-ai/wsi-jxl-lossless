"""Analyze coding regions and query a predeclared, spatially spread tile panel."""
from collections import Counter, defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import time

import imagecodecs
import numpy as np
import tifffile
from wsi_jxl.archive import source_spans
from wsi_jxl.reader import ArchiveReader
from wsi_jxl.tissue import tile_features

parser=argparse.ArgumentParser()
parser.add_argument('--sweep',action='store_true')
parser.add_argument('--local',action='store_true')
parser.add_argument('--all-final',action='store_true')
args=parser.parse_args()
source = Path('data/CMU-1.svs')
features, provenance = tile_features(source)
spans = list(source_spans(source))
counts = Counter(x['class'] for x in features.values() if x['page'] == 0)
panel = []
for category in ('background', 'mixed', 'tissue'):
    eligible = [s for s in spans if s.page == 0 and features[s.offset]['class'] == category]
    panel.extend(eligible[i] for i in np.linspace(0, len(eligible)-1, min(24,len(eligible)), dtype=int))
np.random.default_rng(7).shuffle(panel)

with tifffile.TiffFile(source) as tf:
    tables = tf.pages[0].jpegtables
with source.open('rb') as f:
    originals = {}
    for span in panel:
        f.seek(span.offset)
        originals[span.offset] = f.read(span.length)

results = {'feature_provenance': provenance, 'level0_tile_counts': dict(counts),
           'panel': {'selection': '24 geometry-spread tile indices per foreground class; seed=7 query order',
                     'unique_tiles': len(panel), 'repeats': 3,
                     'cache': 'decoded-group cache cleared per query; OS file cache uncontrolled',
                     'timing': 'group read, exact JPEG reconstruction, then RGB decode; metadata setup excluded'},
           'archives': {}}
names = ('adaptive', 'tissue', 'fixed16', 'fixed32', 'fixed128', 'fixed256') if args.sweep else ('adaptive','tissue')
if args.local:
    names = ('fixed16','fixed32','tissue-local')
if args.all_final:
    names = ('adaptive','tissue','fixed16','fixed32','fixed128','fixed256','tissue-local')
for name in names:
    report = json.loads(Path('results/cmu1-encode.json' if name=='adaptive' else f'results/cmu1-{name}-encode.json').read_text())
    by_region = defaultdict(lambda: {'groups':0,'source_bytes':0,'jxl_bytes':0,'selected_bytes':0,'selected_modes':Counter()})
    cursor = 0
    for row in report['group_records']:
        end = row['source_offset'] + row['source_bytes']
        region_features=[]
        while cursor < len(spans) and spans[cursor].offset < end:
            feature = features.get(spans[cursor].offset)
            if feature is not None:
                region_features.append(feature)
            cursor += 1
        fraction = np.mean([x['fraction'] for x in region_features]) if region_features else None
        category = 'associated' if fraction is None else 'background' if fraction <= .05 else 'tissue' if fraction >= .8 else 'mixed'
        stats = by_region[category]
        stats['groups'] += 1
        stats['source_bytes'] += row['source_bytes']
        stats['jxl_bytes'] += row['jxl']
        stats['selected_bytes'] += row['selected_bytes']
        stats['selected_modes'][row['selected_mode']] += 1
    queries=[]
    start=time.perf_counter()
    with ArchiveReader(f'results/cmu1-{name}.wjxl') as reader:
        index_seconds=time.perf_counter()-start
        with tifffile.TiffFile(reader) as tf:
            assert tf.pages[0].shape == (32914,46000,3)
            assert tf.pages[0].jpegtables == tables
        for repeat in range(3):
            for span in panel:
                reader.clear_cache()
                before=(reader.decoded_source_bytes,reader.payload_bytes_read,reader.decoded_groups)
                start=time.perf_counter()
                reader.seek(span.offset)
                jpeg=reader.read(span.length)
                rgb=imagecodecs.jpeg_decode(jpeg,tables=tables)
                elapsed=time.perf_counter()-start
                assert jpeg==originals[span.offset]
                assert np.array_equal(rgb,imagecodecs.jpeg_decode(originals[span.offset],tables=tables))
                queries.append({'repeat':repeat,'segment':span.segment,'class':features[span.offset]['class'],
                                'source_offset':span.offset,'jpeg_bytes':span.length,'seconds':elapsed,
                                'reconstructed_source_bytes':reader.decoded_source_bytes-before[0],
                                'payload_bytes_read':reader.payload_bytes_read-before[1],
                                'groups_decoded':reader.decoded_groups-before[2],
                                'pixel_sha256':hashlib.sha256(rgb.tobytes()).hexdigest()})
        summaries={}
        for category in ('all','background','mixed','tissue'):
            subset=[q for q in queries if category=='all' or q['class']==category]
            summaries[category]={'queries':len(subset),
                'median_ms':float(np.median([q['seconds']*1000 for q in subset])),
                'p95_ms':float(np.percentile([q['seconds']*1000 for q in subset],95)),
                'mean_reconstructed_source_bytes':float(np.mean([q['reconstructed_source_bytes'] for q in subset])),
                'mean_payload_bytes_read':float(np.mean([q['payload_bytes_read'] for q in subset]))}
        results['archives'][name]={'archive_bytes':report['archive_bytes'],'region_group_sums':dict(by_region),
                                  'index_seconds':index_seconds,'index_bytes_read':reader.index_bytes_read,
                                  'query_summaries':summaries,'queries':queries}
report_path = 'results/pathology-local.json' if args.local else 'results/pathology-sweep.json' if args.sweep else 'results/pathology-analysis.json'
if args.all_final:
    report_path = 'results/pathology-final.json'
Path(report_path).write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({**{k:v for k,v in results.items() if k!='archives'},
                  'archives':{k:{a:b for a,b in v.items() if a!='queries'} for k,v in results['archives'].items()}},indent=2))
