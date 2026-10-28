import numpy as np
import pytest
import tifffile

from wsi_jxl.archive import decode_archive
from wsi_jxl.joint_archive import encode_joint_archive
from wsi_jxl.reader import ArchiveReader


def test_new_operator_archive_restores_whole_tiff_and_random_access_without_source(tmp_path):
    source = tmp_path / 'source.tif'
    rgb = np.random.default_rng(71).integers(0, 256, (57, 71, 3), dtype=np.uint8)
    with tifffile.TiffWriter(source) as t:
        t.write(rgb, photometric='rgb', tile=(32, 32), compression='jpeg', subsampling=(1, 1),
                compressionargs={'outcolorspace': 'RGB'}, description='Preserve original metadata')
        t.write(rgb[:9, :17], photometric='rgb', compression='deflate')
    with source.open('ab') as f:
        f.write(b'EXACT ARBITRARY TRAILER\x00\xff')
    expected = source.read_bytes()
    archive = tmp_path / 'new.wjxl'
    report = encode_joint_archive(source, archive, policy='coefficient', group_tiles=3, effort=3)
    assert report['selected_modes'].get('dc4', 0) > 0
    source.unlink()
    restored = tmp_path / 'restored.tif'
    assert decode_archive(archive, restored)['verified']
    assert restored.read_bytes() == expected
    with ArchiveReader(archive) as reader:
        reader.seek(173)
        assert reader.read(333) == expected[173:506]


def test_joint_archive_preserves_an_existing_partial_file(tmp_path):
    source = tmp_path / 'input.tif'
    target = tmp_path / 'result.wjxl'
    partial = tmp_path / 'result.wjxl.partial'
    partial.write_bytes(b'owned by another process')
    with pytest.raises(FileExistsError):
        encode_joint_archive(source, target)
    assert partial.read_bytes() == b'owned by another process'


def test_unsupported_coefficient_grids_fall_back_without_losing_bytes(tmp_path):
    source = tmp_path / 'subsampled.tif'
    pixels = np.random.default_rng(6).integers(0, 256, (64, 64, 3), dtype=np.uint8)
    tifffile.imwrite(source, pixels, photometric='rgb', tile=(32, 32), compression='jpeg', subsampling=(2, 2))
    expected = source.read_bytes()
    archive = tmp_path / 'fallback.wjxl'
    report = encode_joint_archive(source, archive, policy='adaptive', effort=3)
    assert any(row['unsupported_reason'] for row in report['rows'])
    source.unlink()
    restored = tmp_path / 'restored.tif'
    decode_archive(archive, restored)
    assert restored.read_bytes() == expected
