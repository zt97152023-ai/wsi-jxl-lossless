"""Build paths shared by the optional coefficient adapter and its loader."""
from pathlib import Path
import shlex
import sys


def adapter_path(root, system=None):
    system = system or sys.platform
    if system == 'darwin':
        suffix = '.dylib'
    elif system.startswith('linux'):
        suffix = '.so'
    else:
        raise RuntimeError('The coefficient adapter supports macOS/Linux; use WSL on Windows.')
    return Path(root) / 'build' / ('jpeg_coefficients' + suffix)


def compile_command(root, system=None, *, compiler='cc', jpeg_prefix=None):
    system = system or sys.platform
    root = Path(root)
    output = adapter_path(root, system)
    command = shlex.split(compiler) + ['-O2', '-Wall', '-Wextra', '-Werror', '-fPIC',
                                      '-dynamiclib' if system == 'darwin' else '-shared']
    if jpeg_prefix is not None:
        prefix = Path(jpeg_prefix)
        command += ['-I' + str(prefix / 'include'), '-L' + str(prefix / 'lib')]
    return command + [str(root / 'native/jpeg_coefficients.c'), '-ljpeg', '-o', str(output)]
