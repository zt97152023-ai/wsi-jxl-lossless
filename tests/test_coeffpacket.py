import imagecodecs
import numpy as np
import pytest
from wsi_jxl.coeffpacket import encode_batch,decode_batch
from wsi_jxl.coeffpacket import encode_svs_batch,decode_svs_batch
from pathlib import Path


def test_joint_coefficient_packet_restores_each_jpeg_exactly():
    rng=np.random.default_rng(72)
    jpegs=[imagecodecs.jpeg_encode(rng.integers(0,256,(32,32,3),dtype=np.uint8),level=40,subsampling='444') for _ in range(3)]
    for layout in ('frequency','mosaic'):
        for color_delta in (False,True):
            packet=encode_batch(jpegs,layout=layout,effort=3,color_delta=color_delta)
            assert decode_batch(packet)==jpegs
    for value_map in ('zigzag','bias'):
        packet=encode_batch(jpegs,layout='mosaic',effort=3,color_fit=True,value_map=value_map)
        assert decode_batch(packet)==jpegs


def test_svs_prefix_recipe_is_stored_in_packet():
    jpeg=(Path(__file__).parent/'fixtures/cmu1-rgb-background.jpg').read_bytes()
    skip=jpeg.index(b'\xff\xc0')
    packet=encode_svs_batch([jpeg],[skip],layout='mosaic',color_delta=True,effort=3)
    assert decode_svs_batch(packet)==[b'\xff\xd8'+jpeg[skip:]]


def test_svs_encoder_rejects_a_prefix_that_cannot_restore_soi():
    jpeg=(Path(__file__).parent/'fixtures/cmu1-rgb-background.jpg').read_bytes()
    with pytest.raises(ValueError,match='prefix'):
        encode_svs_batch([jpeg],[1],effort=3)


def test_subsampled_input_is_explicitly_rejected():
    jpeg=imagecodecs.jpeg_encode(np.zeros((32,32,3),dtype=np.uint8),subsampling='420')
    with pytest.raises(ValueError,match='Subsampled'):
        encode_batch([jpeg],effort=3)


def test_fixed_point_prediction_is_reversible_at_int16_boundaries():
    from wsi_jxl.coeffpacket import _color_prediction
    rng=np.random.default_rng(13)
    cube=rng.integers(-32768,32768,(2,3,2,2,64),dtype=np.int16)
    cube[0,0,0,0,:4]=[-32768,-1,0,32767]
    params=rng.integers(-2048,2049,(64,5),dtype=np.int64)
    residual=_color_prediction(cube,params)
    assert np.array_equal(_color_prediction(residual,params,inverse=True),cube)


@pytest.mark.parametrize('options', [
    {'color_context': 'dc2'}, {'color_context': 'dc4'},
    {'color_context': 'texture2'}, {'color_context': 'dc_texture4'},
    {'color_fit': True, 'spatial': 'dc_med'},
    {'color_context': 'dc2', 'spatial': 'low_med'},
    {'color_fit': True, 'layout': 'planes'},
    {'color_fit': True, 'layout': 'zigzag'},
    {'color_context': 'dc4', 'color_objective': 'entropy'},
])
def test_new_operators_restore_jpeg_bytes_and_use_versioned_packets(options):
    rng = np.random.default_rng(102)
    jpegs = [imagecodecs.jpeg_encode(rng.integers(0, 256, (40, 56, 3), dtype=np.uint8),
                                    level=45, subsampling='444') for _ in range(2)]
    packet = encode_batch(jpegs, effort=3, **options)
    assert packet[:4] == b'CJT2'
    assert decode_batch(packet) == jpegs
    with pytest.raises(ValueError):
        decode_batch(b'CJT1' + packet[4:])


def test_zigzag_layout_follows_jpeg_diagonal_frequency_order():
    from wsi_jxl.coeffpacket import ZIGZAG
    assert ZIGZAG[:10].tolist() == [0, 1, 8, 16, 9, 2, 3, 10, 17, 24]


@pytest.mark.parametrize('mapping', ['zigzag', 'bias'])
@pytest.mark.parametrize('color', [{}, {'color_fit': True}, {'color_context': 'dc4'}])
def test_three_channel_coefficients_preserve_jpeg_bytes(mapping, color):
    rng = np.random.default_rng(182)
    jpegs = [imagecodecs.jpeg_encode(rng.integers(0, 256, (40, 56, 3), dtype=np.uint8),
                                    level=45, subsampling='444') for _ in range(2)]
    packet = encode_batch(jpegs, layout='mosaic3', value_map=mapping, effort=3, **color)
    assert packet[:4] == b'CJT2'
    assert decode_batch(packet) == jpegs
