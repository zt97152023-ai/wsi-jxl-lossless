"""Check downloaded public WSI sizes and SHA-256 without codec dependencies."""
import argparse
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
entries = {e['name']: e for e in json.loads((root / 'data/sources.json').read_text())}
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('names', nargs='*')
args = parser.parse_args()
for name in args.names or entries:
    if name not in entries:
        raise SystemExit(f'Unknown source: {name}')
    entry = entries[name]
    path = root / 'data' / name
    if not path.is_file() or path.stat().st_size != entry['bytes']:
        raise SystemExit(f'Missing file or incorrect size: {path}')
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != entry['sha256']:
        raise SystemExit(f'SHA-256 mismatch: {path}')
    print(f'{name}: verified ({entry["bytes"]} bytes)')
