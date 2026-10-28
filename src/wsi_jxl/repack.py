"""Regroup previously encoded JXL records without repeating JPEG-to-JXL search."""
from collections import Counter
import hashlib
from pathlib import Path
import time
import imagecodecs
from .archive import GROUP,MAX_BLOCK,read_metadata,parse_group_header,_read,_publish


def repack_archive(source,baseline,output,*,merge_groups=4,outer='zstd',
                   zstd_levels=(9,15,19),progress=None):
    if merge_groups<1 or outer not in ('zstd','brotli','search'):
        raise ValueError('Invalid merge count or compressor')
    if not zstd_levels or any(n not in range(1,23) for n in zstd_levels):
        raise ValueError('Zstd levels must be between 1 and 22')
    source,baseline,output=map(Path,(source,baseline,output))
    temporary=output.with_name(output.name+'.partial')
    if output.exists() or temporary.exists():raise FileExistsError(output)
    rows=[];modes=Counter();start=time.perf_counter();original_hash=hashlib.sha256()
    owns_temporary=False
    try:
        with baseline.open('rb') as packed_file,source.open('rb') as original,temporary.open('xb') as dest:
            owns_temporary=True
            metadata=read_metadata(packed_file)
            header_size=packed_file.tell();packed_file.seek(0);dest.write(_read(packed_file,header_size))
            raw_parts=[];record_parts=[];raw_bytes=0
            def emit():
                raw=b''.join(raw_parts);packed=b''.join(record_parts)
                if max(len(raw),len(packed))>MAX_BLOCK:raise ValueError('Merged group too large')
                candidates=[]
                if outer in ('zstd','search'):
                    for level in zstd_levels:
                        candidates.append((f'jxl-zstd{level}',2,imagecodecs.zstd_encode(packed,level=level),len(packed)))
                        candidates.append((f'raw-zstd{level}',3,imagecodecs.zstd_encode(raw,level=level),len(raw)))
                    candidates.extend([('jxl',1,packed,len(packed)),('raw',0,raw,len(raw))])
                if outer in ('brotli','search'):
                    candidates.append(('jxl-brotli11',4,imagecodecs.brotli_encode(packed,level=11),len(packed)))
                name,mode,payload,inner=min(candidates,key=lambda x:len(x[2]))
                dest.write(GROUP.pack(mode,len(raw),inner,len(payload),hashlib.sha256(raw).digest()))
                dest.write(payload);modes[name]+=1
                rows.append({'group':len(rows),'input_groups':len(raw_parts),'source_bytes':len(raw),
                             'packed_bytes':len(packed),'winner':name,'mode':mode,'stored_bytes':len(payload),
                             'candidates':{x[0]:len(x[2]) for x in candidates}})
                if progress:progress({'groups':len(rows),'seconds':time.perf_counter()-start,'winner':name})
            while header:=packed_file.read(GROUP.size):
                mode,size,inner,stored,checksum=parse_group_header(header)
                if mode!=1 or inner!=stored:raise ValueError('Repacking requires an unwrapped JXL-record baseline')
                if raw_parts and (len(raw_parts)>=merge_groups or raw_bytes+size>MAX_BLOCK//4):
                    emit();raw_parts=[];record_parts=[];raw_bytes=0
                raw=_read(original,size)
                if hashlib.sha256(raw).digest()!=checksum:raise ValueError('Source does not match baseline')
                original_hash.update(raw)
                raw_parts.append(raw);record_parts.append(_read(packed_file,stored));raw_bytes+=size
            if original.read(1) or original.tell()!=metadata['source_bytes'] or original_hash.hexdigest()!=metadata['source_sha256']:
                raise ValueError('Whole-source input mismatch')
            if raw_parts:emit()
        _publish(temporary,output)
    except BaseException:
        if owns_temporary:temporary.unlink(missing_ok=True)
        raise
    return {**metadata,'baseline':str(baseline),'archive_bytes':output.stat().st_size,
            'merge_groups':merge_groups,'max_source_group_bytes':MAX_BLOCK//4,'outer':outer,
            'zstd_levels':list(zstd_levels),'groups':len(rows),'selected_modes':dict(modes),
            'group_records':rows,'seconds':time.perf_counter()-start,
            'zstd_version':imagecodecs.zstd_version(),'brotli_version':imagecodecs.brotli_version()}
