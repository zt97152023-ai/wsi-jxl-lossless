"""Run from the project root with PYTHONPATH=src .venv/bin/python."""
import argparse
import json
from pathlib import Path
from wsi_jxl.archive import encode_archive, decode_archive

parser = argparse.ArgumentParser()
commands = parser.add_subparsers(dest='command', required=True)
enc = commands.add_parser('encode')
enc.add_argument('source')
enc.add_argument('output')
enc.add_argument('--baseline')
enc.add_argument('--policy', choices=['jxl', 'jxl-zstd', 'adaptive'], default='adaptive')
enc.add_argument('--group-tiles', type=int, default=64)
enc.add_argument('--workers', type=int, default=4)
enc.add_argument('--grouping', choices=['fixed', 'tissue', 'tissue-local'], default='fixed')
enc.add_argument('--report', required=True)
dec = commands.add_parser('decode')
dec.add_argument('archive')
dec.add_argument('--output')
dec.add_argument('--report', required=True)
args = parser.parse_args()
if args.command == 'encode':
    report = encode_archive(args.source, args.output, policy=args.policy,
                            group_tiles=args.group_tiles, workers=args.workers,
                            grouping=args.grouping,
                            baseline_path=args.baseline,
                            progress=lambda p: print(json.dumps(p), flush=True))
else:
    report = decode_archive(args.archive, args.output)
Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'group_records'}), flush=True)
