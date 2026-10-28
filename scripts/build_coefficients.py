"""Build the optional coefficient-research adapter against Homebrew libjpeg."""
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
prefix=Path('/opt/homebrew/opt/jpeg-turbo')
if not (prefix/'include/jpeglib.h').exists():raise SystemExit('Homebrew jpeg-turbo headers are required')
(root/'build').mkdir(exist_ok=True)
subprocess.run(['/usr/bin/clang','-O2','-Wall','-Wextra','-Werror','-dynamiclib',
                '-I'+str(prefix/'include'),str(root/'native/jpeg_coefficients.c'),
                '-L'+str(prefix/'lib'),'-ljpeg','-o',str(root/'build/jpeg_coefficients.dylib')],check=True)
