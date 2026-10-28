"""Complete SVS smoke test on the existing same-slide crop, all bytes retained."""
import json
from pathlib import Path

from wsi_jxl.joint_archive import encode_joint_archive

source = 'data/CMU-1-Small-Region.svs'
rows = []
for policy in ('native', 'adaptive'):
    path = Path(f'results/round4-small-{policy}.wjxl')
    result = encode_joint_archive(source, path, policy=policy, group_tiles=16, effort=10,
                                   progress=lambda r: print(json.dumps(r), flush=True))
    result['archive'] = str(path)
    rows.append(result)
    Path(f'results/round4-small-{policy}.json').write_text(json.dumps(result, indent=2) + '\n')
report = {'note': 'Whole-file smoke test; CMU-1 crop is not a new independent slide. Source-order 16-tile groups, not sorted sample groups.',
          'saving_percent': 100 * (1 - rows[1]['archive_bytes'] / rows[0]['archive_bytes']), 'rows': rows}
Path('results/round4-fullfile.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'rows'}), flush=True)
