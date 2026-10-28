import imagecodecs
import numpy as np
import pytest
from wsi_jxl.coefficients import read_coefficients,write_coefficients,jpeg_parts


@pytest.mark.parametrize('shape',[(64,64,3),(65,97,3)])
def test_coefficients_roundtrip_without_quantization(shape):
    rgb=np.random.default_rng(14).integers(0,256,shape,dtype=np.uint8)
    jpeg=imagecodecs.jpeg_encode(rgb,level=70)
    coefficients,layout=read_coefficients(jpeg)
    restored=write_coefficients(jpeg,coefficients)
    after,after_layout=read_coefficients(restored)
    assert layout==after_layout and np.array_equal(coefficients,after)
    head,entropy,tail=jpeg_parts(jpeg)
    assert head+entropy+tail==jpeg
    assert jpeg_parts(restored)[1]==entropy


def test_coefficients_can_be_decoded_with_a_different_same_parameter_template():
    a=imagecodecs.jpeg_encode(np.full((64,64,3),240,dtype=np.uint8),level=30)
    b=imagecodecs.jpeg_encode(np.random.default_rng(1).integers(0,256,(64,64,3),dtype=np.uint8),level=30)
    coefficients,_=read_coefficients(b)
    generated=write_coefficients(a,coefficients)
    assert jpeg_parts(generated)[1]==jpeg_parts(b)[1]


def test_invalid_jpeg_fails_without_terminating_process():
    with pytest.raises(ValueError):read_coefficients(b'invalid')
