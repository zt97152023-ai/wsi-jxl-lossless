"""Small libjxl C-API adapter exposing JPEG-recompression effort.

imagecodecs' JPEG-to-JXL helper does not expose this option. No pixel-domain
conversion or JPEG re-encoding occurs here; reconstruction metadata is mandatory.
API reference: libjxl lib/include/jxl/encode.h, tested with bundled libjxl 0.12.0.
"""
import ctypes as c
from functools import lru_cache
from pathlib import Path
import imagecodecs


@lru_cache(maxsize=1)
def _library():
    package=Path(imagecodecs.__file__).parent
    candidates=list((package/'.dylibs').glob('libjxl.*.dylib'))
    if not candidates:
        candidates=list((package.parent/'imagecodecs.libs').glob('libjxl-*.so*'))
    if len(candidates)!=1:
        raise RuntimeError('A unique bundled libjxl shared library is required')
    lib=c.CDLL(str(candidates[0]))
    ptr, integer, size = c.c_void_p, c.c_int, c.c_size_t
    byteptr=c.POINTER(c.c_uint8)
    declarations={
        'JxlEncoderVersion':(c.c_uint32,[]),
        'JxlEncoderCreate':(ptr,[ptr]),
        'JxlEncoderDestroy':(None,[ptr]),
        'JxlEncoderFrameSettingsCreate':(ptr,[ptr,ptr]),
        'JxlEncoderFrameSettingsSetOption':(integer,[ptr,integer,c.c_int64]),
        'JxlEncoderUseContainer':(integer,[ptr,integer]),
        'JxlEncoderStoreJPEGMetadata':(integer,[ptr,integer]),
        'JxlEncoderAddJPEGFrame':(integer,[ptr,byteptr,size]),
        'JxlEncoderCloseInput':(None,[ptr]),
        'JxlEncoderProcessOutput':(integer,[ptr,c.POINTER(byteptr),c.POINTER(size)]),
        'JxlEncoderGetError':(integer,[ptr]),
    }
    for name,(result,args) in declarations.items():
        function=getattr(lib,name)
        function.restype=result
        function.argtypes=args
    if lib.JxlEncoderVersion()!=12000:
        raise RuntimeError('This research adapter is validated only with libjxl 0.12.0')
    return lib


def encode_jpeg(jpeg, *, effort=7, cfl=None):
    if effort not in range(1,11):
        raise ValueError('Effort must be between 1 and 10')
    if cfl not in (None,0,1):
        raise ValueError('JPEG CFL option must be 0, 1, or None')
    lib=_library()
    encoder=lib.JxlEncoderCreate(None)
    if not encoder:
        raise MemoryError('Cannot allocate JXL encoder')
    def check(status):
        if status!=0:
            raise ValueError(f'libjxl encoding error {lib.JxlEncoderGetError(encoder)}')
    try:
        settings=lib.JxlEncoderFrameSettingsCreate(encoder,None)
        if not settings:
            raise MemoryError('Cannot allocate JXL frame settings')
        check(lib.JxlEncoderFrameSettingsSetOption(settings,0,effort))
        if cfl is not None:
            check(lib.JxlEncoderFrameSettingsSetOption(settings,30,cfl))
        check(lib.JxlEncoderUseContainer(encoder,1))
        check(lib.JxlEncoderStoreJPEGMetadata(encoder,1))
        source=(c.c_uint8*len(jpeg)).from_buffer_copy(jpeg)
        check(lib.JxlEncoderAddJPEGFrame(settings,source,len(jpeg)))
        lib.JxlEncoderCloseInput(encoder)
        chunks=[]
        total=0
        while True:
            buffer=(c.c_uint8*65536)()
            pointer=c.cast(buffer,c.POINTER(c.c_uint8))
            available=c.c_size_t(len(buffer))
            status=lib.JxlEncoderProcessOutput(encoder,c.byref(pointer),c.byref(available))
            produced=len(buffer)-available.value
            total+=produced
            if total>128*1024*1024:
                raise ValueError('Encoded JPEG exceeds research adapter output limit')
            chunks.append(bytes(buffer[:produced]))
            if status!=2:
                check(status)
                return b''.join(chunks)
    finally:
        lib.JxlEncoderDestroy(encoder)
