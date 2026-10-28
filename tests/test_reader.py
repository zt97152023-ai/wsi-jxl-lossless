import io
import numpy as np
import pytest
import tifffile
from wsi_jxl.archive import encode_archive
from wsi_jxl.reader import ArchiveReader


def test_random_reads_and_tiff_metadata_without_original(tmp_path):
    source = tmp_path / 'source.tif'
    rgb = np.random.default_rng(7).integers(0, 256, (111, 173, 3), dtype=np.uint8)
    tifffile.imwrite(source, rgb, tile=(32, 32), compression='jpeg', photometric='rgb')
    expected = source.read_bytes()
    archive = tmp_path / 'archive.wjxl'
    encode_archive(source, archive, group_tiles=3)
    source.unlink()
    with ArchiveReader(archive, cache_groups=1) as reader:
        for offset, length in [(2, 7), (len(expected)-20, 100), (100, 12345), (0, len(expected))]:
            assert reader.seek(offset) == offset
            assert reader.read(length) == expected[offset:offset+length]
        reader.seek(-10, io.SEEK_END)
        assert reader.read() == expected[-10:]
        assert reader.read() == b''
        reader.seek(0)
        with tifffile.TiffFile(reader) as tf:
            assert tf.pages[0].shape == rgb.shape
            assert tf.pages[0].asarray().shape == rgb.shape
        with pytest.raises(ValueError): reader.seek(-1)


def test_truncated_archive_rejected_at_indexing(tmp_path):
    source = tmp_path / 'source.tif'
    tifffile.imwrite(source, np.zeros((16,16,3),dtype=np.uint8), photometric='rgb')
    archive = tmp_path / 'a.wjxl'
    encode_archive(source, archive)
    archive.write_bytes(archive.read_bytes()[:-1])
    with pytest.raises(ValueError): ArchiveReader(archive)


def test_invalid_cache_size_does_not_leave_a_broken_reader(tmp_path):
    with pytest.raises(ValueError):ArchiveReader(tmp_path/'unused',cache_groups=-1)
