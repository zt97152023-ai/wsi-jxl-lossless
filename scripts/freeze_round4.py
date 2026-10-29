"""Freeze the two smallest pilot configurations before subsequent validation."""
import hashlib
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--round', dest='round_number', type=int, choices=(4, 5), default=4)
args = parser.parse_args()
path = Path(f'results/round{args.round_number}-pilot.json')
pilot = json.loads(path.read_text())
selected = sorted((k for k in pilot['summaries'] if k != 'baseline'),
                  key=lambda k: pilot['summaries'][k]['bytes'])[:2]
if args.round_number == 5:
    selected = [k for k in selected if pilot['summaries'][k]['bytes'] < pilot['summaries']['baseline']['bytes']]
frozen = {
    'stage': 'before additional holdout and second-slide evaluation',
    'pilot_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
    'selection': 'two smallest complete-packet aggregate sizes on fixed 48-tile development panel',
    'candidates': {k: pilot['configs'][k] for k in selected},
    'settings': {'layout': 'mosaic', 'effort': 10, 'value_map': 'zigzag',
                 'grouping': 'original JPEG length, 16 tiles'},
    'model_adaptation': 'Threshold quantiles and color coefficients fitted within each encoded group; all parameters stored. Rules frozen; no encoder-only hidden state.',
    'optional_adaptive_policy': 'For each fixed group choose the smallest complete packet among baseline and the frozen candidates. Choice is represented by the packet layout and stored model; includes all packet bytes. Also retain fixed-mode comparisons.',
    'cross_slide_protocol': {'source': 'CMU-2.svs', 'tiles': 192,
                             'sampling': 'uniform without replacement from all level-0 JPEG tiles',
                             'seed': 202610295 if args.round_number == 4 else 202610297,
                             'note': 'Same-vendor previously studied slide; not independent-center validation. No balanced class resampling.'},
}
if args.round_number == 5:
    frozen['settings']['note'] = 'Candidate options override these defaults; CMU-1 seed 202610296; exclude prior panels on both slides.'
Path(f'results/round{args.round_number}-frozen.json').write_text(json.dumps(frozen, indent=2) + '\n')
print(json.dumps(frozen['candidates']))
