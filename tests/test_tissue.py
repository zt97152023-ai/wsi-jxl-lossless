import numpy as np
import pytest
import tifffile
from wsi_jxl.tissue import foreground_mask, tile_features
from wsi_jxl.archive import encode_archive, decode_archive


def test_foreground_proxy_keeps_pale_glass_separate_from_colored_or_dark_pixels():
    rgb = np.array([[[245, 245, 245], [180, 90, 160], [110, 110, 110]]], dtype=np.uint8)
    assert foreground_mask(rgb).tolist() == [[False, True, True]]


@pytest.mark.parametrize('grouping',['tissue','tissue-local'])
def test_spatial_features_and_adaptive_grouping_do_not_change_source(tmp_path,grouping):
    rgb = np.full((64, 128, 3), 245, dtype=np.uint8)
    rgb[:, 64:] = [180, 90, 160]
    source = tmp_path / 'two-regions.tif'
    tifffile.imwrite(source, rgb, photometric='rgb', tile=(32, 32), compression='jpeg')
    expected = source.read_bytes()
    features, provenance = tile_features(source)
    assert sorted(x['class'] for x in features.values()) == ['background'] * 4 + ['tissue'] * 4
    archive = tmp_path / 'regions.wjxl'
    report = encode_archive(source, archive, grouping=grouping)
    source.unlink()
    restored = tmp_path / 'restored.tif'
    decode_archive(archive, restored)
    assert restored.read_bytes() == expected
    assert report['grouping'] == grouping
    assert provenance['diagnostic_segmentation'] is False
