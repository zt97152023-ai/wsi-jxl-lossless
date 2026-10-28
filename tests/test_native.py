import imagecodecs
import numpy as np
import pytest
from wsi_jxl.native import encode_jpeg


@pytest.mark.parametrize('effort',[7,9,10])
def test_native_effort_keeps_exact_jpeg_bitstream(effort):
    rgb=np.random.default_rng(17).integers(0,256,(65,97,3),dtype=np.uint8)
    jpeg=imagecodecs.jpeg_encode(rgb,level=85)
    encoded=encode_jpeg(jpeg,effort=effort)
    assert imagecodecs.jpegxl_decode_jpeg(encoded)==jpeg


def test_default_effort_matches_existing_reference_size():
    rgb=np.full((64,64,3),240,dtype=np.uint8)
    jpeg=imagecodecs.jpeg_encode(rgb,level=85)
    assert encode_jpeg(jpeg,effort=7)==imagecodecs.jpegxl_encode_jpeg(jpeg,numthreads=1)


def test_out_of_range_effort_is_rejected():
    with pytest.raises(ValueError):encode_jpeg(b'not an image',effort=99)


@pytest.mark.parametrize('cfl',[0,1])
def test_jpeg_predictors_preserve_original_coefficients_and_bitstream(cfl):
    rgb=np.random.default_rng(91).integers(0,256,(32,49,3),dtype=np.uint8)
    jpeg=imagecodecs.jpeg_encode(rgb,level=35)
    jxl=encode_jpeg(jpeg,effort=9,cfl=cfl)
    assert imagecodecs.jpegxl_decode_jpeg(jxl)==jpeg
