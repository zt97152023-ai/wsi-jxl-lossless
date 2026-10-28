"""Decode saved packets in a fresh process, without opening the source WSI."""
import hashlib
import json
import time
from pathlib import Path

import imagecodecs

from wsi_jxl.archive import _unpack
from wsi_jxl.coeffpacket import decode_svs_batch


def digest(data):
    return hashlib.sha256(data).hexdigest()


manifest = json.loads(Path('results/round3-holdout.json').read_text())
lengths = {segment: size for row in manifest['rows']
           for segment, size in zip(row['segments'], row['raw_lengths'])}
control = json.loads(Path('results/round3-group-control.json').read_text())
for row in control['rows']:
    manifest['rows'].append({
        'raw_lengths': [lengths[i] for i in row['segments']],
        'raw_sha256': row['raw_sha256'],
        'variants': {'fit': {'packet': row['packet'], 'bytes': row['bytes']}},
        'native_packet': row['native_packet'],
        'native_jxl_brotli11_bytes': row['native_bytes']})
verified = []
seen = set()
for row in manifest['rows']:
    for name, variant in row['variants'].items():
        path = Path(variant['packet'])
        if path in seen:
            continue
        seen.add(path)
        packet = path.read_bytes()
        start = time.perf_counter()
        raw = decode_svs_batch(packet)
        elapsed = time.perf_counter() - start
        assert len(packet) == variant['bytes']
        assert [len(x) for x in raw] == row['raw_lengths']
        assert [digest(x) for x in raw] == row['raw_sha256']
        if 'concat_sha256' in row:
            assert digest(b''.join(raw)) == row['concat_sha256']
        verified.append({'packet': str(path), 'bytes': len(packet),
                         'packet_sha256': digest(packet), 'jpeg_byte_exact': True,
                         'tiles': len(raw), 'decode_seconds': elapsed})
    path = Path(row['native_packet'])
    if path in seen:
        continue
    seen.add(path)
    packet = path.read_bytes()
    start = time.perf_counter()
    raw = _unpack(imagecodecs.brotli_decode(packet))
    elapsed = time.perf_counter() - start
    assert len(packet) == row['native_jxl_brotli11_bytes']
    assert len(raw) == sum(row['raw_lengths'])
    if 'concat_sha256' in row:
        assert digest(raw) == row['concat_sha256']
    cursor = 0
    for size, expected in zip(row['raw_lengths'], row['raw_sha256']):
        assert digest(raw[cursor:cursor + size]) == expected
        cursor += size
    verified.append({'packet': str(path), 'bytes': len(packet),
                     'packet_sha256': digest(packet), 'jpeg_byte_exact': True,
                     'tiles': len(row['raw_lengths']), 'decode_seconds': elapsed})

result = {'source_opened': False, 'verification': 'fresh-process stored-packet decode',
          'distinct_tiles': 144, 'verified_packets': len(verified), 'rows': verified}
Path('results/round3-packet-verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'rows'}))
