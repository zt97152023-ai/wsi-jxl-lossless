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


def _fit_color(cube):
    # Per-frequency adaptive coefficients; this is not stain separation. The
    # fixed-point parameters are stored, so decoder results never depend on
    # reproducing this floating-point fit or on having the source image.
    r,g,b=[cube[:,i].reshape(-1,64).astype(np.float64) for i in range(3)]
    mr,mg,mb=[v.mean(0) for v in (r,g,b)]
    r-=mr;g-=mg;b-=mb
    vr=(r*r).mean(0)+1;vg=(g*g).mean(0)+1;rg=(r*g).mean(0)
    gb=(g*b).mean(0);rb=(r*b).mean(0)
    alpha=np.clip(rg/vg,-8,8)
    det=vg*vr-rg*rg
    beta=np.clip((gb*vr-rb*rg)/det,-8,8)
    gamma=np.clip((rb*vg-gb*rg)/det,-8,8)
    return np.rint(np.stack([alpha,mr-alpha*mg,beta,gamma,mb-beta*mg-gamma*mr],axis=1)*256).astype(np.int64)


def _color_prediction(cube,params,inverse=False):
    # Arithmetic is modulo 2**16. Recover the wrapped original first channel
    # before predicting the third, including at signed integer boundaries.
    x=cube.astype(np.int64);p=np.asarray(params,dtype=np.int64)
    if p.shape!=(64,5):raise ValueError('Invalid color prediction parameters')
    pred_r=(x[:,1]*p[:,0]+p[:,1]+128)//256
    if inverse:
        x[:,0]=((x[:,0]+pred_r+32768)&65535)-32768
        pred_b=(x[:,1]*p[:,2]+x[:,0]*p[:,3]+p[:,4]+128)//256
        x[:,2]=((x[:,2]+pred_b+32768)&65535)-32768
    else:
        pred_b=(x[:,1]*p[:,2]+x[:,0]*p[:,3]+p[:,4]+128)//256
        x[:,0]-=pred_r;x[:,2]-=pred_b
    return x.astype(np.int16)


def encode_batch(jpegs,*,layout='frequency',effort=7,color_delta=False,color_fit=False,value_map='zigzag'):
    if not jpegs or layout not in ('frequency','mosaic'):raise ValueError('Invalid batch/layout')
    if value_map not in ('zigzag','bias') or (color_delta and color_fit):raise ValueError('Invalid coefficient transform')
    arrays=[];heads=[];tails=[];reference=None
    for jpeg in jpegs:
        coefficients,shape=read_coefficients(jpeg)
        if reference is None:reference=shape
        if shape!=reference:raise ValueError('Heterogeneous JPEG grids')
        arrays.append(coefficients);head,_,tail=jpeg_parts(jpeg);heads.append(head.hex());tails.append(tail.hex())
    grids=reference['components']
    if len({(x[0],x[1]) for x in grids})!=1:raise ValueError('Subsampled grids are not supported by this experiment')
    width,height=grids[0][:2];channels=len(grids);n=len(jpegs)
    cube=np.stack(arrays).reshape(n,channels,height,width,64)
    template=write_coefficients(jpegs[0],np.zeros_like(arrays[0]))
    for jpeg,coef in zip(jpegs,arrays):
        if jpeg_parts(write_coefficients(template,coef))[1]!=jpeg_parts(jpeg)[1]:
            raise ValueError('JPEG entropy bytes are not reproducible from shared template')
    params=None
    if color_fit:
        if channels!=3:raise ValueError('Color prediction requires three channels')
        params=_fit_color(cube);cube=_color_prediction(cube,params)
    elif color_delta:
        if channels!=3:raise ValueError('Color delta requires three channels')
        cube=cube.astype(np.int32)
        cube[:,0]-=cube[:,1];cube[:,2]-=cube[:,1]
        cube=cube.astype(np.int16)
    integers=cube.astype(np.int32)
    values=(((integers<<1)^(integers>>15)) if value_map=='zigzag' else integers+32768).astype(np.uint16)
    if layout=='frequency':matrix=values.transpose(1,4,0,2,3).reshape(channels*64,n*height*width)
    else:matrix=values.reshape(n,channels,height,width,8,8).transpose(1,4,2,5,0,3).reshape(channels*8*height,8*n*width)
    encoded=imagecodecs.jpegxl_encode(np.ascontiguousarray(matrix),lossless=True,distance=0,effort=effort,numthreads=1)
    info=json.dumps({'n':n,'channels':channels,'width':width,'height':height,'layout':layout,
                     'color_delta':color_delta,'color_params':params.tolist() if params is not None else None,
                     'value_map':value_map,'heads':heads,'tails':tails,
                     'template_bytes':len(template)},separators=(',',':')).encode()
    side=imagecodecs.zstd_encode(info,level=9)
    stored_template=imagecodecs.zstd_encode(template,level=9)
    return HEADER.pack(b'CJT1',len(side),len(info),len(stored_template),len(encoded))+side+stored_template+encoded


def decode_batch(packet):
    with io.BytesIO(packet) as f:
        magic,ns,plain_size,nt,nc=HEADER.unpack(_read(f,HEADER.size))
        if magic!=b'CJT1' or max(ns,plain_size,nt,nc)>MAX_BLOCK:raise ValueError('Invalid coefficient packet')
        info=json.loads(imagecodecs.zstd_decode(_read(f,ns),out=plain_size))
        if not 0<info['template_bytes']<=MAX_BLOCK:raise ValueError('Invalid template size')
        template=imagecodecs.zstd_decode(_read(f,nt),out=info['template_bytes']);encoded=_read(f,nc)
        if f.read(1):raise ValueError('Trailing coefficient packet data')
    n,channels,h,w=(info[x] for x in ('n','channels','height','width'))
    if min(n,channels,h,w)<1 or n*channels*h*w*64>MAX_BLOCK//2:raise ValueError('Coefficient shape too large')
    matrix=imagecodecs.jpegxl_decode(encoded,numthreads=1)
    if matrix.dtype!=np.uint16 or matrix.size!=n*channels*h*w*64:raise ValueError('Coefficient JXL shape mismatch')
    if info['layout']=='frequency':values=matrix.reshape(channels,64,n,h,w).transpose(2,0,3,4,1)
    elif info['layout']=='mosaic':values=matrix.reshape(channels,8,h,8,n,w).transpose(4,0,2,5,1,3).reshape(n,channels,h,w,64)
    else:raise ValueError('Unknown coefficient layout')
    if info.get('value_map','zigzag')=='zigzag':signed=((values.astype(np.int32)>>1)^-(values.astype(np.int32)&1))
    elif info['value_map']=='bias':signed=values.astype(np.int32)-32768
    else:raise ValueError('Unknown coefficient integer map')
    if info.get('color_params') is not None:
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
