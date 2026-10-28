"""Decode every persisted experiment packet without reading either source WSI."""
import argparse
import hashlib
import json
from pathlib import Path

import imagecodecs

from wsi_jxl.archive import _unpack
from wsi_jxl.coeffpacket import decode_svs_batch

parser = argparse.ArgumentParser()
parser.add_argument('manifests', nargs='+')
parser.add_argument('--output', default='results/round4-verification.json')
args = parser.parse_args()
rows = []
for filename in args.manifests:
    experiment = json.loads(Path(filename).read_text())
    for batch in experiment['rows']:
        for name, variant in batch['variants'].items():
            packet = Path(variant['packet']).read_bytes()
            restored = decode_svs_batch(packet)
            assert len(packet) == variant['bytes']
            assert list(map(len, restored)) == batch['raw_lengths']
            assert [hashlib.sha256(x).hexdigest() for x in restored] == batch['raw_sha256']
            rows.append({'manifest': filename, 'batch': batch['batch'], 'variant': name,
                         'packet': variant['packet'], 'packet_sha256': hashlib.sha256(packet).hexdigest(),
                         'tiles': len(restored), 'bytes': len(packet), 'exact': True})
        packet = Path(batch['native_packet']).read_bytes()
        restored = _unpack(imagecodecs.brotli_decode(packet))
        assert len(packet) == batch['native_bytes']
        assert len(restored) == sum(batch['raw_lengths'])
        cursor = 0
        for size, expected in zip(batch['raw_lengths'], batch['raw_sha256']):
            assert hashlib.sha256(restored[cursor:cursor + size]).hexdigest() == expected
            cursor += size
        rows.append({'manifest': filename, 'batch': batch['batch'], 'variant': 'native',
                     'packet': batch['native_packet'], 'packet_sha256': hashlib.sha256(packet).hexdigest(),
                     'tiles': len(batch['raw_lengths']), 'bytes': len(packet), 'exact': True})
result = {'source_opened': False, 'verified_packets': len(rows), 'manifests': args.manifests, 'rows': rows}
Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))
