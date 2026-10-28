"""Experimental joint integer-DCT packet, encoded with lossless JXL Modular.

Only uniform component grids and reproducible sequential JPEG scans are
accepted. Template, exact per-image headers/trailers, layout and coefficients
are all stored; failure to reproduce an input JPEG rejects the candidate.
"""
import io,json,struct
import numpy as np
import imagecodecs
from .archive import _read,MAX_BLOCK
from .coefficients import read_coefficients,write_coefficients,jpeg_parts

HEADER=struct.Struct('<4sIIII')


from .operators import _fit_color, _color_prediction, fit_context_color, context_color, spatial_predict

ZIGZAG = np.array(sorted(range(64), key=lambda k: (k//8+k%8, k//8 if (k//8+k%8)%2 else -(k//8))))


def encode_batch(jpegs,*,layout='frequency',effort=7,color_delta=False,color_fit=False,value_map='zigzag',
                 color_context=None,spatial=None,color_objective='variance'):
    if not jpegs or layout not in ('frequency','mosaic','planes','zigzag','mosaic3'):raise ValueError('Invalid batch/layout')
    if value_map not in ('zigzag','bias') or sum(map(bool,(color_delta,color_fit,color_context)))>1:
        raise ValueError('Invalid coefficient transform')
    if color_objective not in ('variance','entropy') or (color_objective!='variance' and not color_context):
        raise ValueError('Color objective requires a context model')
    arrays=[];heads=[];tails=[];reference=None
    for jpeg in jpegs:
        coefficients,shape=read_coefficients(jpeg)
        if reference is None:reference=shape
        if shape!=reference:raise ValueError('Heterogeneous JPEG grids')
        arrays.append(coefficients);head,_,tail=jpeg_parts(jpeg);heads.append(head.hex());tails.append(tail.hex())
    grids=reference['components']
    if len({(x[0],x[1]) for x in grids})!=1:raise ValueError('Subsampled grids are not supported by this experiment')
    width,height=grids[0][:2];channels=len(grids);n=len(jpegs)
    if layout=='mosaic3' and channels!=3:raise ValueError('Three-channel layout requires three components')
    cube=np.stack(arrays).reshape(n,channels,height,width,64)
    template=write_coefficients(jpegs[0],np.zeros_like(arrays[0]))
    for jpeg,coef in zip(jpegs,arrays):
        if jpeg_parts(write_coefficients(template,coef))[1]!=jpeg_parts(jpeg)[1]:
            raise ValueError('JPEG entropy bytes are not reproducible from shared template')
    params=None;context=None
    if color_context:
        context=fit_context_color(cube,color_context,objective=color_objective);cube=context_color(cube,context)
    elif color_fit:
        if channels!=3:raise ValueError('Color prediction requires three channels')
        params=_fit_color(cube);cube=_color_prediction(cube,params)
    elif color_delta:
        if channels!=3:raise ValueError('Color delta requires three channels')
        cube=cube.astype(np.int32)
        cube[:,0]-=cube[:,1];cube[:,2]-=cube[:,1]
        cube=cube.astype(np.int16)
    if spatial:cube=spatial_predict(cube,spatial)
    integers=cube.astype(np.int32)
    values=(((integers<<1)^(integers>>15)) if value_map=='zigzag' else integers+32768).astype(np.uint16)
    if layout=='frequency':matrix=values.transpose(1,4,0,2,3).reshape(channels*64,n*height*width)
    elif layout=='planes':matrix=values.transpose(1,4,2,0,3).reshape(channels*64*height,n*width)
    elif layout=='mosaic3':
        matrix=values.reshape(n,channels,height,width,8,8).transpose(4,2,5,0,3,1).reshape(8*height,8*n*width,channels)
    else:
        if layout=='zigzag':values=values[...,ZIGZAG]
        matrix=values.reshape(n,channels,height,width,8,8).transpose(1,4,2,5,0,3).reshape(channels*8*height,8*n*width)
    encoded=imagecodecs.jpegxl_encode(np.ascontiguousarray(matrix),lossless=True,distance=0,effort=effort,numthreads=1)
    info={'n':n,'channels':channels,'width':width,'height':height,'layout':layout,
                     'color_delta':color_delta,'color_params':params.tolist() if params is not None else None,
                     'value_map':value_map,'heads':heads,'tails':tails,
                     'template_bytes':len(template)}
    extended=bool(context or spatial or layout in ('planes','zigzag','mosaic3'))
    if extended:info['operators']={'context_color':context,'spatial':spatial}
    info=json.dumps(info,separators=(',',':')).encode()
    side=imagecodecs.zstd_encode(info,level=9)
    stored_template=imagecodecs.zstd_encode(template,level=9)
    return HEADER.pack(b'CJT2' if extended else b'CJT1',len(side),len(info),len(stored_template),len(encoded))+side+stored_template+encoded


def decode_batch(packet):
    with io.BytesIO(packet) as f:
        magic,ns,plain_size,nt,nc=HEADER.unpack(_read(f,HEADER.size))
        if magic not in (b'CJT1',b'CJT2') or max(ns,plain_size,nt,nc)>MAX_BLOCK:raise ValueError('Invalid coefficient packet')
        info=json.loads(imagecodecs.zstd_decode(_read(f,ns),out=plain_size))
        if (magic==b'CJT2')!=('operators' in info):raise ValueError('Coefficient operator version mismatch')
        if not 0<info['template_bytes']<=MAX_BLOCK:raise ValueError('Invalid template size')
        template=imagecodecs.zstd_decode(_read(f,nt),out=info['template_bytes']);encoded=_read(f,nc)
        if f.read(1):raise ValueError('Trailing coefficient packet data')
    n,channels,h,w=(info[x] for x in ('n','channels','height','width'))
    if min(n,channels,h,w)<1 or n*channels*h*w*64>MAX_BLOCK//2:raise ValueError('Coefficient shape too large')
    matrix=imagecodecs.jpegxl_decode(encoded,numthreads=1)
    if matrix.dtype!=np.uint16 or matrix.size!=n*channels*h*w*64:raise ValueError('Coefficient JXL shape mismatch')
    if info['layout']=='frequency':values=matrix.reshape(channels,64,n,h,w).transpose(2,0,3,4,1)
    elif info['layout']=='planes':values=matrix.reshape(channels,64,h,n,w).transpose(3,0,2,4,1)
    elif info['layout']=='mosaic3':
        if channels!=3 or matrix.shape!=(8*h,8*n*w,3):raise ValueError('Three-channel coefficient shape mismatch')
        values=matrix.reshape(8,h,8,n,w,3).transpose(3,5,1,4,0,2).reshape(n,channels,h,w,64)
    elif info['layout'] in ('mosaic','zigzag'):
        values=matrix.reshape(channels,8,h,8,n,w).transpose(4,0,2,5,1,3).reshape(n,channels,h,w,64)
        if info['layout']=='zigzag':values=values[...,np.argsort(ZIGZAG)]
    else:raise ValueError('Unknown coefficient layout')
    if info.get('value_map','zigzag')=='zigzag':signed=((values.astype(np.int32)>>1)^-(values.astype(np.int32)&1))
    elif info['value_map']=='bias':signed=values.astype(np.int32)-32768
    else:raise ValueError('Unknown coefficient integer map')
    operators=info.get('operators',{})
    if operators.get('spatial'):signed=spatial_predict(signed.astype(np.int16),operators['spatial'],inverse=True)
    if operators.get('context_color'):
        signed=context_color(signed.astype(np.int16),operators['context_color'],inverse=True)
    elif info.get('color_params') is not None:
        signed=_color_prediction(signed,info['color_params'],inverse=True)
    elif info['color_delta']:
        signed[:,0]+=signed[:,1];signed[:,2]+=signed[:,1]
    coefficients=signed.astype(np.int16).reshape(n,-1)
    if len(info['heads'])!=n or len(info['tails'])!=n:raise ValueError('JPEG side information count mismatch')
    output=[]
    for i,coef in enumerate(coefficients):
        entropy=jpeg_parts(write_coefficients(template,coef))[1]
        output.append(bytes.fromhex(info['heads'][i])+entropy+bytes.fromhex(info['tails'][i]))
    return output


def encode_svs_batch(jpegs,prefix_sizes,**options):
    if len(jpegs)!=len(prefix_sizes):raise ValueError('Prefix count mismatch')
    if any(n<0 or n==1 or n>len(jpeg) for n,jpeg in zip(prefix_sizes,jpegs)):
        raise ValueError('Invalid injected prefix size')
    prefix=struct.pack('<4sI',b'SCJ1',len(jpegs))
    prefix+=struct.pack('<'+'I'*len(prefix_sizes),*prefix_sizes)
    return prefix+encode_batch(jpegs,**options)


def decode_svs_batch(packet):
    with io.BytesIO(packet) as f:
        magic,count=struct.unpack('<4sI',_read(f,8))
        if magic!=b'SCJ1' or count>(len(packet)-8)//4:raise ValueError('Invalid SVS coefficient packet')
        prefixes=struct.unpack('<'+'I'*count,_read(f,count*4))
        jpegs=decode_batch(f.read())
    if len(jpegs)!=count:raise ValueError('SVS packet count mismatch')
    result=[]
    for jpeg,size in zip(jpegs,prefixes):
        if size>len(jpeg) or size==1:raise ValueError('Invalid JPEG prefix')
        result.append(b'\xff\xd8'+jpeg[size:] if size else jpeg)
    return result
