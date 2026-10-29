"""Bounded research probe: reuse the four already encoded crop archives."""
import hashlib
import io
import json
from pathlib import Path

from wsi_jxl.archive import GROUP, _publish, _read, decode_archive, parse_group_header, read_metadata

root = Path('results')
sources = []
for mode in ('entropy', 'weak_ridge', 'dc4', 'mc_none_bias'):
    path = root / f'round5-small-{mode}.wjxl'
    data = path.read_bytes()
    previous = json.loads((root / f'round5-small-{mode}.json').read_text())
    digest = hashlib.sha256(data).hexdigest()
    assert digest == previous['archive_sha256']
    stream = io.BytesIO(data)
    metadata = read_metadata(stream)
    prefix = data[:stream.tell()]
    groups = []
    while stream.tell() < len(data):
        header = _read(stream, GROUP.size)
        kind, original, inner, size, checksum = parse_group_header(header)
        groups.append({'header': header, 'payload': _read(stream, size),
                       'original': original, 'checksum': checksum, 'kind': kind})
    sources.append({'mode': mode, 'path': str(path), 'sha256': digest,
                    'prefix': prefix, 'metadata': metadata, 'groups': groups})

base = sources[0]
assert all(s['prefix'] == base['prefix'] and len(s['groups']) == len(base['groups']) for s in sources)
selected = []
for i, reference in enumerate(base['groups']):
    assert all((s['groups'][i]['original'], s['groups'][i]['checksum']) ==
               (reference['original'], reference['checksum']) for s in sources)
    source = min(sources, key=lambda s: len(s['groups'][i]['payload']))
    selected.append((source['mode'], source['groups'][i]))

output = root / 'round6-small-selected.wjxl'
temporary = output.with_name(output.name + '.partial')
if output.exists() or temporary.exists():
    raise FileExistsError(output)
owns_temporary = False
try:
    with temporary.open('xb') as f:
        owns_temporary = True
        f.write(base['prefix'])
        for _, group in selected:
            f.write(group['header'])
            f.write(group['payload'])
    decoded = decode_archive(temporary)
    _publish(temporary, output)
except BaseException:
    if owns_temporary:
        temporary.unlink(missing_ok=True)
    raise

baseline_bytes = Path(base['path']).stat().st_size
report = {'note': 'Post-hoc complete-payload selection among four existing archives with identical source partitions. Reuses stored model/mode headers. Does not measure candidate encoding cost.',
          'sources': [{k: s[k] for k in ('mode', 'path', 'sha256')} for s in sources],
          'output': str(output), 'archive_bytes': output.stat().st_size,
          'archive_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
          'baseline_bytes': baseline_bytes,
          'saved_bytes': baseline_bytes - output.stat().st_size,
          'saved_percent': 100 * (1 - output.stat().st_size / baseline_bytes),
          'verification': decoded,
          'groups': [{'source_mode': mode, 'archive_kind': group['kind'],
                       'stored_bytes': len(group['payload']), 'source_bytes': group['original']}
                      for mode, group in selected]}
(root / 'round6-group-selection.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k not in ('sources', 'groups')}))
