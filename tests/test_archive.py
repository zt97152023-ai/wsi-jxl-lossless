from pathlib import Path
import numpy as np
import pytest
import tifffile
from wsi_jxl.archive import encode_archive, decode_archive


def make_slide(path):
    rng=np.random.default_rng(3)
    rgb=rng.integers(0,256,(73,95,3),dtype=np.uint8)
    with tifffile.TiffWriter(path) as tif:
        tif.write(rgb,photometric='rgb',tile=(32,32),compression='jpeg',description='All metadata must survive')
        tif.write(rgb[:19,:23],photometric='rgb',compression='deflate',description='Non-JPEG associated image')
    with path.open('ab') as f:f.write(b'UNPARSED TRAILING BYTES\x00\xff')


@pytest.mark.parametrize('policy',['jxl','jxl-zstd','adaptive'])
def test_entire_tiff_bytes_restore_without_source(policy,tmp_path):
    source=tmp_path/'input.tif';make_slide(source);expected=source.read_bytes()
    archive=tmp_path/'out.wjxl';restored=tmp_path/'restored.tif'
    report=encode_archive(source,archive,policy=policy,group_tiles=4)
    source.unlink()
    decoded=decode_archive(archive,restored)
    assert restored.read_bytes()==expected
    assert report['source_sha256']==decoded['sha256']
    assert report['archive_bytes']==archive.stat().st_size


def test_corruption_rejected_and_output_not_published(tmp_path):
    source=tmp_path/'input.tif';make_slide(source)
    archive=tmp_path/'out.wjxl';out=tmp_path/'restored.tif'
    encode_archive(source,archive,group_tiles=4)
    data=bytearray(archive.read_bytes());data[-1]^=0xff;archive.write_bytes(data)
    with pytest.raises((ValueError,RuntimeError)):
        decode_archive(archive,out)
    assert not out.exists()


def test_existing_outputs_are_not_overwritten(tmp_path):
    source=tmp_path/'input.tif';make_slide(source)
    archive=tmp_path/'out.wjxl';archive.write_bytes(b'keep')
    with pytest.raises(FileExistsError):encode_archive(source,archive)
    assert archive.read_bytes()==b'keep'


def test_destination_created_during_encode_is_preserved(tmp_path, monkeypatch):
    import wsi_jxl.archive as module
    source=tmp_path/'input.tif';make_slide(source)
    archive=tmp_path/'out.wjxl'
    original=module._record
    def concurrent_creation(item):
        archive.write_bytes(b'created by someone else')
        return original(item)
    monkeypatch.setattr(module,'_record',concurrent_creation)
    with pytest.raises(FileExistsError):encode_archive(source,archive,workers=1)
    assert archive.read_bytes()==b'created by someone else'
    assert not archive.with_name(archive.name+'.partial').exists()


def test_truncation_at_group_boundary_is_rejected(tmp_path):
    from wsi_jxl.archive import GROUP, read_metadata
    source=tmp_path/'input.tif';make_slide(source)
    archive=tmp_path/'out.wjxl';encode_archive(source,archive,group_tiles=2)
    with archive.open('rb') as f:
        read_metadata(f)
        header=f.read(GROUP.size)
        size=GROUP.unpack(header)[3]
        end=f.tell()+size
    archive.write_bytes(archive.read_bytes()[:end])
    with pytest.raises(ValueError,match='Whole-source'):decode_archive(archive)
