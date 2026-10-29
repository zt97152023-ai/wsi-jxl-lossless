from pathlib import Path

import pytest

from wsi_jxl.platform_support import adapter_path, compile_command


@pytest.mark.parametrize('system,suffix,link_flag', [('darwin', '.dylib', '-dynamiclib'),
                                                   ('linux', '.so', '-shared')])
def test_build_and_loader_agree_on_platform_output(system, suffix, link_flag):
    root = Path('/tmp/project with spaces')
    output = adapter_path(root, system)
    command = compile_command(root, system, compiler='cc', jpeg_prefix=Path('/tmp/jpeg prefix'))
    assert output.suffix == suffix
    assert command[command.index('-o') + 1] == str(output)
    assert link_flag in command
    assert '-I/tmp/jpeg prefix/include' in command
    assert str(root / 'native/jpeg_coefficients.c') in command


def test_unsupported_platform_has_actionable_error():
    with pytest.raises(RuntimeError, match='WSL'):
        adapter_path(Path('/tmp/project'), 'win32')
