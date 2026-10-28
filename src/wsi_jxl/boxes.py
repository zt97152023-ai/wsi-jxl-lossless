"""Reversible dictionary factoring of identical JXL container boxes in a group."""
from collections import Counter
import io
import struct
from .archive import RECORD,MAX_BLOCK,_read

U32=struct.Struct('<I')
I32=struct.Struct('<i')
U16=struct.Struct('<H')


def _split_boxes(payload):
    boxes=[];cursor=0
    while cursor<len(payload):
        if cursor+8>len(payload):raise ValueError('Truncated JXL box')
        size=int.from_bytes(payload[cursor:cursor+4],'big')
        minimum=8
        if size==1:
            if cursor+16>len(payload):raise ValueError('Truncated extended box')
            size=int.from_bytes(payload[cursor+8:cursor+16],'big');minimum=16
        elif size==0:
            size=len(payload)-cursor
        if size<minimum or cursor+size>len(payload):raise ValueError('Invalid JXL box size')
        boxes.append(payload[cursor:cursor+size]);cursor+=size
    return boxes


def factor_boxes(packed):
    records=[];frequencies=Counter()
    with io.BytesIO(packed) as stream:
        while header:=stream.read(RECORD.size):
            if len(header)!=RECORD.size:raise ValueError('Truncated record')
            mode,_,_,size=RECORD.unpack(header)
            payload=_read(stream,size)
            parts=_split_boxes(payload) if mode==1 else [payload]
            if mode==1:frequencies.update(parts)
            records.append((header,mode,parts))
    shared=[box for box,n in frequencies.items() if n>1 and len(box)>8]
    indices={box:i for i,box in enumerate(shared)}
    result=bytearray(b'BXD1'+struct.pack('<II',len(shared),len(records)))
    for box in shared:result.extend(U32.pack(len(box))+box)
    for header,mode,parts in records:
        result.extend(header)
        if mode!=1:
            result.extend(parts[0]);continue
        result.extend(U16.pack(len(parts)))
        for box in parts:
            if box in indices:result.extend(I32.pack(-indices[box]-1))
            else:result.extend(I32.pack(len(box))+box)
    return bytes(result)


def restore_boxes(factored):
    result=bytearray()
    with io.BytesIO(factored) as stream:
        if _read(stream,4)!=b'BXD1':raise ValueError('Unknown box dictionary format')
        count,records=struct.unpack('<II',_read(stream,8))
        if count>len(factored)//4 or records>len(factored)//RECORD.size:
            raise ValueError('Invalid dictionary or record count')
        shared=[]
        for _ in range(count):
            size,=U32.unpack(_read(stream,4))
            if size>MAX_BLOCK:raise ValueError('Box too large')
            shared.append(_read(stream,size))
        for _ in range(records):
            header=_read(stream,RECORD.size)
            mode,_,_,expected=RECORD.unpack(header)
            if expected>MAX_BLOCK:raise ValueError('Record too large')
            if mode!=1:payload=_read(stream,expected)
            else:
                parts=[];total=0
                count,=U16.unpack(_read(stream,2))
                for _ in range(count):
                    token,=I32.unpack(_read(stream,4))
                    if token<0:
                        index=-token-1
                        if index>=len(shared):raise ValueError('Invalid shared-box reference')
                        box=shared[index]
                    else:
                        if token>MAX_BLOCK:raise ValueError('Box too large')
                        box=_read(stream,token)
                    total+=len(box)
                    if total>expected:raise ValueError('Box sequence exceeds record size')
                    parts.append(box)
                payload=b''.join(parts)
            if len(payload)!=expected or len(result)+RECORD.size+len(payload)>MAX_BLOCK:
                raise ValueError('Restored record length mismatch')
            result.extend(header+payload)
        if stream.read(1):raise ValueError('Trailing box dictionary data')
    return bytes(result)
