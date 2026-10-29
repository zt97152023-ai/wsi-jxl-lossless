"""Build the optional coefficient adapter on macOS or Linux."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
from wsi_jxl.platform_support import compile_command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jpeg-prefix', type=Path, default=os.environ.get('WSI_JPEG_PREFIX'))
    parser.add_argument('--compiler', default=os.environ.get('CC', 'cc'))
    args = parser.parse_args()
    prefix = args.jpeg_prefix
    if prefix is None and sys.platform == 'darwin' and shutil.which('brew'):
        prefix = Path(subprocess.check_output(['brew', '--prefix', 'jpeg-turbo'], text=True).strip())
    if prefix is not None and not (prefix / 'include/jpeglib.h').is_file():
        raise SystemExit('jpeglib.h is missing under --jpeg-prefix/include')
    (root / 'build').mkdir(exist_ok=True)
    command = compile_command(root, compiler=args.compiler, jpeg_prefix=prefix)
    subprocess.run(command, check=True)
    print(command[-1])


if __name__ == '__main__':
    main()
