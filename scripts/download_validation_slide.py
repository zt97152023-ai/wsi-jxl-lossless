"""Fetch a separate public CC0 WSI without replacing any existing slide."""
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
import tifffile

name = 'CMU-2.svs'
url = 'https://storage.googleapis.com/imagebox_test/openslide-testdata/Aperio/' + name
path = Path('data') / name
expected_size = 390750635
if not path.exists():
    temporary = path.with_suffix('.svs.part')
    start = time.monotonic()
    with urllib.request.urlopen(url, timeout=30) as response, temporary.open('xb') as out:
        size = 0
        while chunk := response.read(1024 * 1024):
            out.write(chunk); size += len(chunk)
            if size % (64 * 1024 * 1024) == 0:
                print(json.dumps({'downloaded_bytes': size}), flush=True)
            if size > expected_size or time.monotonic() - start > 240:
                raise ValueError('Download size/time limit exceeded')
    if size != expected_size:
        raise ValueError('Unexpected downloaded WSI size')
    os.link(temporary, path)
    temporary.unlink()
with path.open('rb') as f:
    sha256 = hashlib.file_digest(f, 'sha256').hexdigest()
with path.open('rb') as f:
    md5 = hashlib.file_digest(f, 'md5').hexdigest()
if path.stat().st_size != expected_size or md5 != '4e00a3e05b57d85e37d19a78c4824eca':
    raise ValueError('Public mirror size/ETag content check failed')
manifest = {'file': str(path), 'bytes': path.stat().st_size, 'sha256': sha256, 'md5': md5,
            'original_url': 'https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/' + name,
            'download_url': url, 'license': 'CC0-1.0',
            'license_evidence': 'https://qupath.readthedocs.io/en/0.3/docs/intro/acknowledgements.html',
            'note': 'Separate public slide, not a crop of CMU-1. Same source/vendor, not multi-center validation.'}
with tifffile.TiffFile(path) as t:
    manifest['pages'] = [{'width': p.imagewidth, 'height': p.imagelength,
                          'compression': int(p.compression), 'photometric': int(p.photometric),
                          'tiled': p.is_tiled, 'tiles': len(p.dataoffsets),
                          'tile_width': p.tilewidth, 'tile_height': p.tilelength} for p in t.pages]
Path('results/round4-source-cmu2.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest), flush=True)
