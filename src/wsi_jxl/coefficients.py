"""Read/rewrite quantized JPEG coefficients without any pixel-domain transform."""
import ctypes as c
from functools import lru_cache
from pathlib import Path
import numpy as np
from .platform_support import adapter_path


@lru_cache(maxsize=1)
def _library():
    path=adapter_path(Path(__file__).resolve().parents[2])
    if not path.is_file():
        raise RuntimeError('Build the coefficient adapter first: python scripts/build_coefficients.py')
    lib=c.CDLL(str(path))
    p16=c.POINTER(c.c_int16)
    lib.wsi_coefficients.argtypes=[c.c_void_p,c.c_ulong,p16,c.c_size_t,c.POINTER(c.c_uint32)]
    lib.wsi_coefficients.restype=c.c_int64
    lib.wsi_write_coefficients.argtypes=[c.c_void_p,c.c_ulong,p16,c.c_size_t,c.POINTER(c.c_void_p),c.POINTER(c.c_ulong)]
    lib.wsi_write_coefficients.restype=c.c_int
    lib.wsi_free.argtypes=[c.c_void_p];lib.wsi_free.restype=None
    return lib


def read_coefficients(jpeg):
    lib=_library();shape=(c.c_uint32*15)();result=np.empty(1<<20,dtype=np.int16)
    count=lib.wsi_coefficients(jpeg,len(jpeg),result.ctypes.data_as(c.POINTER(c.c_int16)),len(result),shape)
    if count<0:raise ValueError(f'JPEG coefficient extraction failed: {count}')
    if count>len(result):raise ValueError('Research coefficient buffer limit exceeded')
    layout={'width':shape[0],'height':shape[1],
            'components':[[shape[3+3*i],shape[4+3*i],shape[5+3*i]] for i in range(shape[2])]}
    return result[:count].copy(),layout


def write_coefficients(template,coefficients):
    array=np.ascontiguousarray(coefficients,dtype=np.int16)
    lib=_library();pointer=c.c_void_p();size=c.c_ulong()
    status=lib.wsi_write_coefficients(template,len(template),array.ctypes.data_as(c.POINTER(c.c_int16)),
                                       array.size,c.byref(pointer),c.byref(size))
    if status!=0:raise ValueError(f'JPEG coefficient reconstruction failed: {status}')
    try:return c.string_at(pointer,size.value)
    finally:lib.wsi_free(pointer)


def jpeg_parts(jpeg):
    """Return exact header/entropy/trailer for a single sequential JPEG scan."""
    if not jpeg.startswith(b'\xff\xd8'):raise ValueError('Not JPEG')
    cursor=2
    while cursor+4<=len(jpeg):
        if jpeg[cursor]!=255:raise ValueError('Invalid JPEG header')
        marker=jpeg[cursor+1]
        if marker==255:cursor+=1;continue
        size=int.from_bytes(jpeg[cursor+2:cursor+4],'big')
        if size<2 or cursor+2+size>len(jpeg):raise ValueError('Invalid JPEG marker length')
        cursor+=2+size
        if marker==0xda:break
    else:raise ValueError('Missing JPEG scan')
    start=cursor
    while cursor<len(jpeg)-1:
        if jpeg[cursor]!=255:cursor+=1;continue
        marker=jpeg[cursor+1]
        if marker==0 or 0xd0<=marker<=0xd7:cursor+=2;continue
        if marker==0xd9:return jpeg[:start],jpeg[start:cursor],jpeg[cursor:]
        raise ValueError('Multiple scans or unsupported entropy marker')
    raise ValueError('Missing JPEG end marker')
