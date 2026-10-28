"""Experimental byte-exact TIFF archive, with independently checked groups.

JXL JPEG reconstruction is an existing libjxl feature. This module adds TIFF
shared-table handling, complete source-byte coverage, and grouped route search.
The result is a custom archive, not a standard standalone .jxl image.
"""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import struct
import time

import imagecodecs
import tifffile

MAGIC = b'WJXL001\n'
GROUP = struct.Struct('<BQQQ32s')  # mode, source size, inner size, stored size, hash
RECORD = struct.Struct('<BQII')  # mode, source size, injected prefix size, payload size
MAX_BLOCK = 128 * 1024 * 1024
TISSUE_LIMITS = {
    'tissue': {'background': 256, 'mixed': 32, 'tissue': 64, 'associated': 64},
    'tissue-local': {'background': 64, 'mixed': 8, 'tissue': 32, 'associated': 32},
}


@dataclass(frozen=True)
class Span:
    offset: int
    length: int
    prefix: bytes | None
    page: int = -1
    segment: int = -1


def _read(stream, size):
    result = stream.read(size)
    if len(result) != size:
        raise ValueError('Truncated archive or source')
    return result


def _publish(temporary, destination):
    # Both paths share a directory/filesystem. link() never replaces a file that
    # another process created after our initial existence check.
    os.link(temporary, destination)
    temporary.unlink()


def source_spans(source):
    """Partition every source byte; unsupported image data remains an opaque gap."""
    source = Path(source)
    segments = {}
    with tifffile.TiffFile(source) as tf:
        for pi, page in enumerate(tf.pages):
            if int(page.compression) != 7:
                continue
            tables = page.jpegtables
            if tables and (not tables.startswith(b'\xff\xd8') or not tables.endswith(b'\xff\xd9')):
                continue  # Retain unusual table forms as original bytes.
            prefix = tables[:-2] if tables else b''
            for si, (offset, length) in enumerate(zip(page.dataoffsets, page.databytecounts)):
                key = (int(offset), int(length))
                if not key[1]:
                    continue
                span = Span(*key, prefix, pi, si)
                if key in segments and segments[key].prefix != prefix:
                    raise ValueError('Shared JPEG segment has conflicting tables')
                segments[key] = span
    cursor = 0
    size = source.stat().st_size
    for (offset, length), span in sorted(segments.items()):
        if offset < cursor or offset + length > size:
            raise ValueError('Overlapping or invalid JPEG extents')
        while cursor < offset:
            n = min(offset - cursor, 4 * 1024 * 1024)
            yield Span(cursor, n, None)
            cursor += n
        yield span
        cursor = offset + length
    while cursor < size:
        n = min(size - cursor, 4 * 1024 * 1024)
        yield Span(cursor, n, None)
        cursor += n


def _record(item, *, effort=None):
    raw, span = item
    payload, mode, skip, error = raw, 0, 0, None
    if span.prefix is not None and raw.startswith(b'\xff\xd8'):
        complete = span.prefix + raw[2:] if span.prefix else raw
        try:
            if effort is None:
                payload = imagecodecs.jpegxl_encode_jpeg(complete, numthreads=1)
            else:
                from .native import encode_jpeg
                payload = encode_jpeg(complete, effort=effort)
            mode, skip = 1, len(span.prefix)
        except (ValueError, imagecodecs.JpegxlError) as exc:
            error = str(exc)
    return RECORD.pack(mode, len(raw), skip, len(payload)) + payload, error


def _unpack(packed):
    result = bytearray()
    cursor = 0
    while cursor < len(packed):
        if cursor + RECORD.size > len(packed):
            raise ValueError('Truncated record header')
        mode, original_size, skip, size = RECORD.unpack_from(packed, cursor)
        cursor += RECORD.size
        if cursor + size > len(packed) or original_size > MAX_BLOCK:
            raise ValueError('Invalid record length')
        payload = packed[cursor:cursor + size]
        cursor += size
        if mode == 0 and skip == 0:
            raw = payload
        elif mode == 1:
            complete_size = original_size + (skip - 2 if skip else 0)
            if skip > MAX_BLOCK or not 0 < complete_size <= MAX_BLOCK:
                raise ValueError('Invalid reconstructed JPEG size')
            complete = imagecodecs.jpegxl_decode_jpeg(payload, numthreads=1, out=complete_size)
            if skip > len(complete) or (skip and skip < 2):
                raise ValueError('Invalid JPEG prefix length')
            raw = b'\xff\xd8' + complete[skip:] if skip else complete
        else:
            raise ValueError('Unknown record mode')
        if len(raw) != original_size or len(result) + len(raw) > MAX_BLOCK:
            raise ValueError('Decoded record size mismatch')
        result.extend(raw)
    return bytes(result)


def read_metadata(stream):
    if _read(stream, len(MAGIC)) != MAGIC:
        raise ValueError('Unknown archive format')
    size, = struct.unpack('<I', _read(stream, 4))
    if size > 1024 * 1024:
        raise ValueError('Metadata too large')
    metadata = json.loads(_read(stream, size))
    if metadata.get('format') != 1 or metadata.get('source_bytes', -1) < 0:
        raise ValueError('Invalid archive metadata')
    return metadata


def parse_group_header(header):
    if len(header) != GROUP.size:
        raise ValueError('Truncated group header')
    mode, original_size, inner_size, size, checksum = GROUP.unpack(header)
    if mode not in (0, 1, 2, 3, 4, 5) or max(original_size, inner_size, size) > MAX_BLOCK or original_size == 0:
        raise ValueError('Invalid group mode or size')
    return mode, original_size, inner_size, size, checksum


def decode_group(stream, header):
    mode, original_size, inner_size, size, checksum = parse_group_header(header)
    payload = _read(stream, size)
    if mode in (2, 3):
        try:
            payload = imagecodecs.zstd_decode(payload, out=inner_size)
        except imagecodecs.ZstdError as exc:
            raise ValueError('Invalid compressed group') from exc
    elif mode == 4:
        try:
            payload = imagecodecs.brotli_decode(payload, out=inner_size)
        except imagecodecs.BrotliError as exc:
            raise ValueError('Invalid Brotli group') from exc
    if len(payload) != inner_size:
        raise ValueError('Inner group size mismatch')
    if mode == 5:
        from .coeffpacket import decode_svs_batch
        raw = b''.join(decode_svs_batch(payload))
    else:
        raw = _unpack(payload) if mode in (1, 2, 4) else payload
    if len(raw) != original_size or hashlib.sha256(raw).digest() != checksum:
        raise ValueError('Group reconstruction checksum mismatch')
    return raw


def encode_archive(source, output, *, policy='adaptive', group_tiles=64,
                   workers=4, baseline_path=None, progress=None, grouping='fixed',
                   jpeg_effort=None, zstd_level=9):
    if policy not in ('jxl', 'jxl-zstd', 'adaptive'):
        raise ValueError('Unknown encoding policy')
    if group_tiles < 1 or workers < 1:
        raise ValueError('Positive group size and worker count required')
    if jpeg_effort is not None and jpeg_effort not in range(1,11):
        raise ValueError('JPEG effort must be 1..10')
    if zstd_level not in range(1,23):
        raise ValueError('Zstd level must be 1..22')
    if grouping != 'fixed' and grouping not in TISSUE_LIMITS:
        raise ValueError('Unknown grouping strategy')
    source, output = Path(source), Path(output)
    destinations = [output] + ([Path(baseline_path)] if baseline_path else [])
    if len({p.resolve() for p in destinations}) != len(destinations):
        raise ValueError('Output destinations must differ')
    temporary = [p.with_name(p.name + '.partial') for p in destinations]
    for p in destinations + temporary:
        if p.exists():
            raise FileExistsError(p)
    start = time.perf_counter()
    features, feature_provenance = {}, None
    if grouping in TISSUE_LIMITS:
        from .tissue import tile_features
        features, feature_provenance = tile_features(source)
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    metadata = {'format': 1, 'source_name': source.name,
                'source_bytes': source.stat().st_size, 'source_sha256': digest}
    encoded_metadata = json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode()
    header = MAGIC + struct.pack('<I', len(encoded_metadata)) + encoded_metadata
    alternatives = {k: len(header) for k in ('jxl', 'jxl-zstd', 'raw-zstd', 'adaptive')}
    rows, errors, modes, handles, published = [], Counter(), Counter(), [], []
    try:
        for p in temporary:
            f = p.open('xb')
            handles.append(f)
            f.write(header)
        with ThreadPoolExecutor(max_workers=workers) as pool, source.open('rb') as stream:
            def emit(batch):
                raw = b''.join(item[0] for item in batch)
                encode_record = _record if jpeg_effort is None else partial(_record, effort=jpeg_effort)
                records = list(pool.map(encode_record, batch))
                for _, error in records:
                    if error:
                        errors[error] += 1
                packed = b''.join(record for record, _ in records)
                if max(len(raw), len(packed)) > MAX_BLOCK:
                    raise ValueError('Group exceeds format limit; use smaller source segments')
                jz = imagecodecs.zstd_encode(packed, level=zstd_level)
                rz = imagecodecs.zstd_encode(raw, level=zstd_level)
                candidates = [(1, packed, len(packed)), (2, jz, len(packed)),
                              (3, rz, len(raw)), (0, raw, len(raw))]
                best = min(candidates, key=lambda x: len(x[1]))
                chosen = {'jxl': candidates[0], 'jxl-zstd': candidates[1], 'adaptive': best}[policy]
                mode, payload, inner_size = chosen
                checksum = hashlib.sha256(raw).digest()
                handles[0].write(GROUP.pack(mode, len(raw), inner_size, len(payload), checksum))
                handles[0].write(payload)
                if len(handles) == 2:
                    handles[1].write(GROUP.pack(1, len(raw), len(packed), len(packed), checksum))
                    handles[1].write(packed)
                for key, n in zip(alternatives, (len(packed), len(jz), len(rz), len(best[1]))):
                    alternatives[key] += GROUP.size + n
                rows.append({'group': len(rows), 'source_offset': batch[0][1].offset,
                             'source_bytes': len(raw), 'jpeg_tiles': sum(s.prefix is not None for _, s in batch),
                             'pages': sorted({s.page for _, s in batch if s.page >= 0}),
                             'jxl': len(packed), 'jxl_zstd': len(jz), 'raw_zstd': len(rz),
                             'selected_mode': mode, 'selected_bytes': len(payload)})
                if features:
                    labels = [features[s.offset] for _, s in batch if s.offset in features]
                    rows[-1]['tissue_classes'] = dict(Counter(x['class'] for x in labels))
                    rows[-1]['mean_foreground_fraction'] = sum(x['fraction'] for x in labels) / len(labels) if labels else None
                modes[mode] += 1
                if progress and len(rows) % 25 == 0:
                    progress({'groups': len(rows), 'seconds': time.perf_counter() - start})

            batch, tile_count, byte_count, group_key = [], 0, 0, None
            for span in source_spans(source):
                feature = features.get(span.offset)
                key = (span.page, feature['class'] if feature else 'associated')
                if grouping in TISSUE_LIMITS and span.prefix is not None and batch and tile_count and key != group_key:
                    emit(batch)
                    batch, tile_count, byte_count = [], 0, 0
                if span.prefix is not None:
                    group_key = key
                if stream.tell() != span.offset:
                    raise ValueError('Source partition is not contiguous')
                raw = _read(stream, span.length)
                batch.append((raw, span))
                tile_count += span.prefix is not None
                byte_count += span.length
                limit = group_tiles
                if grouping in TISSUE_LIMITS:
                    category = group_key[1] if group_key else 'associated'
                    limit = TISSUE_LIMITS[grouping][category]
                if tile_count >= limit or byte_count >= MAX_BLOCK // 4:
                    emit(batch)
                    batch, tile_count, byte_count = [], 0, 0
            if batch:
                emit(batch)
        for f in handles:
            f.close()
        for temp, dest in zip(temporary, destinations):
            _publish(temp, dest)
            published.append(dest)
    except BaseException:
        for f in handles:
            f.close()
        for p in temporary[:len(handles)]:
            p.unlink(missing_ok=True)
        for p in published:
            p.unlink(missing_ok=True)
        raise
    return {**metadata, 'policy': policy, 'group_tiles': group_tiles, 'workers': workers,
            'jpeg_effort': jpeg_effort if jpeg_effort is not None else 7, 'zstd_level': zstd_level,
            'grouping': grouping, 'feature_provenance': feature_provenance,
            'tissue_group_limits': TISSUE_LIMITS.get(grouping),
            'archive_bytes': output.stat().st_size, 'candidate_archive_bytes': alternatives,
            'selected_modes': dict(modes), 'fallback_errors': dict(errors),
            'groups': len(rows), 'group_records': rows, 'seconds': time.perf_counter() - start,
            'libjxl': imagecodecs.jpegxl_version(), 'imagecodecs': imagecodecs.__version__,
            'baseline_path': str(baseline_path) if baseline_path else None}


def decode_archive(archive, output=None):
    """An output-less call independently reconstructs and hashes every source byte."""
    start = time.perf_counter()
    output = Path(output) if output is not None else None
    temporary = output.with_name(output.name + '.partial') if output else None
    if output and (output.exists() or temporary.exists()):
        raise FileExistsError(output)
    dest, total, groups, digest = None, 0, 0, hashlib.sha256()
    try:
        if temporary:
            dest = temporary.open('xb')
        with Path(archive).open('rb') as stream:
            metadata = read_metadata(stream)
            while first := stream.read(GROUP.size):
                raw = decode_group(stream, first)
                total += len(raw)
                if total > metadata['source_bytes']:
                    raise ValueError('Source size exceeded')
                groups += 1
                digest.update(raw)
                if dest:
                    dest.write(raw)
        if total != metadata['source_bytes'] or digest.hexdigest() != metadata['source_sha256']:
            raise ValueError('Whole-source reconstruction checksum mismatch')
        if dest:
            dest.close()
            _publish(temporary, output)
    except BaseException:
        if dest:
            dest.close()
            temporary.unlink(missing_ok=True)
        raise
    return {'sha256': digest.hexdigest(), 'bytes': total, 'groups': groups,
            'seconds': time.perf_counter() - start, 'verified': True,
            'saved_output': str(output) if output else None}
