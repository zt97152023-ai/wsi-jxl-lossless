import struct
import imagecodecs
import numpy as np
import pytest
from wsi_jxl.archive import RECORD
from wsi_jxl.boxes import factor_boxes, restore_boxes


def test_shared_boxes_restore_exact_record_stream_including_raw_metadata():
    rng=np.random.default_rng(51)
    records=[]
    for i in range(4):
        jpeg=imagecodecs.jpeg_encode(rng.integers(0,256,(32,32,3),dtype=np.uint8))
        jxl=imagecodecs.jpegxl_encode_jpeg(jpeg,numthreads=1)
        records.append(RECORD.pack(1,len(jpeg),0,len(jxl))+jxl)
    raw=b'TIFF metadata\0\xff'*9
    records.insert(2,RECORD.pack(0,len(raw),0,len(raw))+raw)
    packed=b''.join(records)
    factored=factor_boxes(packed)
    assert restore_boxes(factored)==packed
    assert len(factored)<len(packed)


def test_factored_truncation_is_rejected():
    factored=factor_boxes(RECORD.pack(0,3,0,3)+b'abc')
    with pytest.raises(ValueError):restore_boxes(factored[:-1])


def test_invalid_dictionary_reference_is_rejected():
    header=RECORD.pack(1,3,0,12)
    fake=b'BXD1'+struct.pack('<II',0,1)+header+struct.pack('<Hi',1,-1)
    with pytest.raises(ValueError):restore_boxes(fake)
