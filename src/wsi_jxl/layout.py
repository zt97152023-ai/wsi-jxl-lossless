"""Encoder-only appearance features and lossless permutations of JXL records.

These features are color/texture proxies, not cell counts or pathology labels.
The decoder needs only the stored permutation, never the image classifier.
"""
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import numpy as np
import imagecodecs
import tifffile
from .archive import GROUP,RECORD,read_metadata,parse_group_header,_read,MAX_BLOCK


@dataclass(frozen=True)
class Record:
    index:int
    offset:int
    length:int
    data:bytes


def load_records(baseline):
    records=[];offset=0
    with Path(baseline).open('rb') as f:
        metadata=read_metadata(f)
        while header:=f.read(GROUP.size):
            mode,original_size,inner,stored,_=parse_group_header(header)
            if mode!=1 or inner!=stored:raise ValueError('Unwrapped JXL record baseline required')
            packed=_read(f,stored);cursor=0;group_bytes=0
            while cursor<len(packed):
                if cursor+RECORD.size>len(packed):raise ValueError('Truncated record')
                _,length,_,size=RECORD.unpack_from(packed,cursor)
                end=cursor+RECORD.size+size
                if end>len(packed) or length<1:raise ValueError('Invalid record bounds')
                records.append(Record(len(records),offset,length,packed[cursor:end]))
                offset+=length;group_bytes+=length;cursor=end
            if group_bytes!=original_size:raise ValueError('Group source coverage mismatch')
    if offset!=metadata['source_bytes']:raise ValueError('Incomplete source coverage')
    return metadata,records


def appearance_features(rgb):
    # Full decoded tile contributes to these statistics; no downsampling of the
    # archived data takes place. Intensity thresholds are fixed before screening.
    lo=rgb.min(axis=2);hi=rgb.max(axis=2)
    foreground=((lo<220)&(hi.astype(np.int16)-lo>20))|(hi<180)
    gray=rgb.astype(np.float32).mean(axis=2)
    gradient=(float(np.abs(np.diff(gray,axis=0)).mean())+
              float(np.abs(np.diff(gray,axis=1)).mean()))/2 if min(gray.shape)>1 else 0.
    means=rgb.mean(axis=(0,1)).astype(float)
    od=-np.log((means+1)/256)
    return {'foreground':float(foreground.mean()),'dark':float((gray<120).mean()),
            'brightness':float(gray.mean()),'gradient':gradient,
            'red_green':float(od[0]-od[1]),'blue_green':float(od[2]-od[1])}


def extract_features(source,*,workers=4,progress=None):
    tasks=[]
    with tifffile.TiffFile(source) as tf,Path(source).open('rb') as f:
        for pi,p in enumerate(tf.pages):
            if int(p.compression)!=7 or not p.is_tiled:continue
            if int(p.photometric) not in (2,6):continue
            colorspace='RGB' if int(p.photometric)==2 else 'YCbCr'
            cols=(p.imagewidth+p.tilewidth-1)//p.tilewidth
            for si,(offset,size) in enumerate(zip(p.dataoffsets,p.databytecounts)):
                f.seek(offset);jpeg=_read(f,size)
                row,col=divmod(si,cols)
                tasks.append((int(offset),pi,col*p.tilewidth,row*p.tilelength,jpeg,p.jpegtables,colorspace))
    def describe(task):
        offset,page,x,y,jpeg,tables,colorspace=task
        rgb=imagecodecs.jpeg_decode(jpeg,tables=tables,colorspace=colorspace,outcolorspace='RGB')
        return offset,{'page':page,'x':x,'y':y,**appearance_features(rgb)}
    features={}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i,(offset,feature) in enumerate(pool.map(describe,tasks)):
            features[offset]=feature
            if progress and (i+1)%4000==0:progress({'features':i+1})
    return features


def morton(x,y):
    result=0
    for bit in range(32):
        result|=((int(x)>>bit)&1)<<(2*bit)
        result|=((int(y)>>bit)&1)<<(2*bit+1)
    return result


def make_order(records,features,method):
    if method=='original':return list(range(len(records)))
    if method=='shuffle':return np.random.default_rng(7).permutation(len(records)).tolist()
    if method not in ('morton','length','appearance','appearance_fine'):
        raise ValueError('Unknown layout')
    def key(record):
        feature=features.get(record.offset)
        if feature is None:return (-1,record.index)
        page=feature['page'];space=morton(feature['x'],feature['y'])
        if method=='morton':return (page,space)
        if method=='length':return (page,len(record.data),record.index)
        region=0 if feature['foreground']<=.05 else 2 if feature['foreground']>=.8 else 1
        scale=2 if method=='appearance_fine' else 1
        return (page,region,int(feature['brightness']*scale/8),
                round(feature['red_green']*scale*16),round(feature['blue_green']*scale*16),
                int(feature['gradient']*scale/2),int(feature['dark']*scale*16),space)
    return [r.index for r in sorted(records,key=key)]


def partition(records,order,*,max_records=4096,max_source_bytes=32*1024*1024):
    groups=[];batch=[];size=0
    for index in order:
        record=records[index]
        if batch and (len(batch)>=max_records or size+record.length>max_source_bytes):
            groups.append(batch);batch=[];size=0
        if record.length>MAX_BLOCK:raise ValueError('Oversized record')
        batch.append(index);size+=record.length
    if batch:groups.append(batch)
    return groups


def pack_index(records,order,groups):
    raw=json.dumps({'lengths':[r.length for r in records],'order':order,
                    'groups':[len(g) for g in groups]},separators=(',',':')).encode()
    return raw,imagecodecs.zstd_encode(raw,level=9)
