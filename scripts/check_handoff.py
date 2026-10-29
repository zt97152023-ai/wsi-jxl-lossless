"""Validate the frozen writing evidence using only the Python standard library."""
import csv
import hashlib
import json
from pathlib import Path


def check(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'writing/evidence_manifest.json').read_text())
    registered = set()
    for row in manifest['files']:
        path = (root / row['path']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Evidence must be inside the repository')
        data = path.read_bytes()
        if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError(f'Evidence changed; review required: {row["path"]}')
        registered.add(row['path'])

    def number(reference):
        filename, pointer = reference.split('#', 1)
        if filename not in registered:
            raise ValueError(f'Unregistered evidence: {filename}')
        value = json.loads((root / filename).read_text())
        for key in pointer.strip('/').split('/'):
            value = value[key.replace('~1', '/').replace('~0', '~')]
        if type(value) is not int or value <= 0:
            raise ValueError(f'Expected positive integer bytes: {reference}')
        return value

    with (root / 'writing/claims.csv').open(newline='') as f:
        claims = list(csv.DictReader(f))
    ids = set()
    for row in claims:
        if row['claim_id'] in ids:
            raise ValueError('Duplicate claim ID')
        ids.add(row['claim_id'])
        if row['status'] not in ('ALLOW_SCOPED', 'EXPLORATORY_ONLY'):
            raise ValueError('Unknown evidence status')
        if row['research_commit'] != manifest['research_commit'] or not row['limitations']:
            raise ValueError('Missing research version or claim boundary')
        baseline, result = number(row['baseline_evidence']), number(row['result_evidence'])
        if (baseline, result) != (int(row['baseline_bytes']), int(row['result_bytes'])):
            raise ValueError(f'Claim byte counts disagree: {row["claim_id"]}')
        if abs(float(row['saving_percent']) - 100 * (1 - result / baseline)) > 1e-7:
            raise ValueError(f'Claim percentage disagrees: {row["claim_id"]}')
        if any(p not in registered for p in row['verification_files'].split(';')):
            raise ValueError('Verification report is not registered')
    return len(registered), len(claims)


if __name__ == '__main__':
    try:
        files, claims = check(Path(__file__).resolve().parents[1])
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc
    print(f'Verified {files} evidence files and {claims} scoped numerical claims.')
