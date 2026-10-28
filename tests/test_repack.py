import numpy as np
import pytest
import tifffile
from wsi_jxl.archive import encode_archive,decode_archive
from wsi_jxl.repack import repack_archive


@pytest.mark.parametrize('outer',['zstd','brotli','search'])
def test_repacking_groups_restores_every_original_byte(outer,tmp_path):
    source=tmp_path/'in.tif'
    rgb=np.random.default_rng(61).integers(0,256,(111,129,3),dtype=np.uint8)
    tifffile.imwrite(source,rgb,photometric='rgb',tile=(32,32),compression='jpeg')
    expected=source.read_bytes();baseline=tmp_path/'base.wjxl';out=tmp_path/'new.wjxl'
    encode_archive(source,baseline,policy='jxl',group_tiles=2)
    report=repack_archive(source,baseline,out,merge_groups=3,outer=outer)
    source.unlink();baseline.unlink()
    restored=tmp_path/'restored.tif';decode_archive(out,restored)
    assert restored.read_bytes()==expected
    assert report['archive_bytes']==out.stat().st_size
    if outer=='brotli':assert all(x['mode']==4 for x in report['group_records'])


def test_changed_source_rejected_without_publishing(tmp_path):
    source=tmp_path/'in.tif'
    tifffile.imwrite(source,np.zeros((32,32,3),dtype=np.uint8),photometric='rgb')
    baseline=tmp_path/'base.wjxl';out=tmp_path/'new.wjxl'
    encode_archive(source,baseline,policy='jxl')
    b=bytearray(source.read_bytes());b[-1]^=1;source.write_bytes(b)
    with pytest.raises(ValueError):repack_archive(source,baseline,out)
    assert not out.exists()


def test_concurrent_partial_file_is_not_removed(tmp_path,monkeypatch):
    from pathlib import Path
    source=tmp_path/'in.tif'
    tifffile.imwrite(source,np.zeros((16,16,3),dtype=np.uint8),photometric='rgb')
    baseline=tmp_path/'base.wjxl';out=tmp_path/'new.wjxl'
    encode_archive(source,baseline,policy='jxl')
    partial=out.with_name(out.name+'.partial');original_open=Path.open
    def race(path,*args,**kwargs):
        if path==partial and args and args[0]=='xb':
            with original_open(path,'wb') as f:f.write(b'owned by another process')
        return original_open(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',race)
    with pytest.raises(FileExistsError):repack_archive(source,baseline,out)
    assert partial.read_bytes()==b'owned by another process'
