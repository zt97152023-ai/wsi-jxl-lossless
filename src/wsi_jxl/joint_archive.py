"""Opt-in complete-file archive using independently recoverable coefficient groups.

Source order is retained. Non-JPEG bytes and unsupported grids use the existing
routes. Mode 5 contains a self-contained SCJ1 packet; the ordinary group and
whole-file SHA-256 contracts still apply.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct
import time

import imagecodecs

from .archive import MAGIC, GROUP, MAX_BLOCK, source_spans, _read, _record, _publish
from .coeffpacket import encode_svs_batch, decode_svs_batch


def encode_joint_archive(source, output, *, group_tiles=16, policy='adaptive', effort=10, progress=None):
    if policy not in ('native', 'adaptive', 'coefficient') or not 1 <= group_tiles <= 16:
        raise ValueError('Invalid joint archive policy/group size')
    source, output = Path(source), Path(output)
    temporary = output.with_name(output.name + '.partial')
    if output.exists() or temporary.exists():
        raise FileExistsError(output)
    with source.open('rb') as f:
        expected_hash = hashlib.file_digest(f, 'sha256').hexdigest()
    metadata = {'format': 1, 'source_bytes': source.stat().st_size, 'source_sha256': expected_hash,
                'source_name': source.name, 'joint_coefficient_groups': True}
    header = json.dumps(metadata, sort_keys=True, separators=(',', ':')).encode()
    rows = []; modes = Counter(); digest = hashlib.sha256(); total = 0
    owns_temporary = False
    start = time.perf_counter()
    try:
        with source.open('rb') as original, temporary.open('xb') as dest:
            owns_temporary = True
            dest.write(MAGIC + struct.pack('<I', len(header)) + header)

            def emit(items):
                nonlocal total
                raw = b''.join(data for data, _ in items)
                packed = b''.join(_record(item, effort=9)[0] for item in items)
                candidates = [('raw', 0, raw, len(raw)),
                              ('raw-zstd', 3, imagecodecs.zstd_encode(raw, level=15), len(raw)),
                              ('native-brotli', 4, imagecodecs.brotli_encode(packed, level=11), len(packed))]
                error = None
                if policy != 'native' and all(s.prefix is not None for _, s in items):
                    jpegs = [s.prefix + data[2:] if s.prefix else data for data, s in items]
                    try:
                        packet = encode_svs_batch(jpegs, [len(s.prefix) for _, s in items],
                                                  layout='mosaic', color_context='dc4', effort=effort)
                        if decode_svs_batch(packet) != [data for data, _ in items]:
                            raise RuntimeError('Coefficient candidate failed exact reconstruction')
                        candidate = ('dc4', 5, packet, len(packet))
                        candidates = [candidate] if policy == 'coefficient' else candidates + [candidate]
                    except (ValueError, imagecodecs.JpegxlError) as exc:
                        if policy == 'coefficient':
                            raise
                        error = str(exc)
                name, mode, payload, inner = min(candidates, key=lambda x: len(x[2]))
                if max(len(raw), inner, len(payload)) > MAX_BLOCK:
                    raise ValueError('Joint group size limit exceeded')
                dest.write(GROUP.pack(mode, len(raw), inner, len(payload), hashlib.sha256(raw).digest()))
                dest.write(payload)
                digest.update(raw); total += len(raw); modes[name] += 1
                rows.append({'source_bytes': len(raw), 'stored_bytes': len(payload), 'selected': name,
                             'candidates': {c[0]: len(c[2]) for c in candidates}, 'unsupported_reason': error})
                if progress:
                    progress({'groups': len(rows), 'selected': name, 'seconds': time.perf_counter() - start})

            batch = []; size = 0
            for span in source_spans(source):
                if batch and (span.prefix is None or span.page != batch[0][1].page or
                              len(batch) >= group_tiles or size + span.length > MAX_BLOCK // 4):
                    emit(batch); batch = []; size = 0
                original.seek(span.offset)
                item = (_read(original, span.length), span)
                if span.prefix is None:
                    emit([item])
                else:
                    batch.append(item); size += span.length
            if batch:
                emit(batch)
            if total != metadata['source_bytes'] or digest.hexdigest() != expected_hash:
                raise ValueError('Source changed during joint encoding')
        _publish(temporary, output)
    except BaseException:
        if owns_temporary:
            temporary.unlink(missing_ok=True)
        raise
    return {**metadata, 'policy': policy, 'group_tiles': group_tiles, 'effort': effort,
            'archive_bytes': output.stat().st_size, 'groups': len(rows),
            'selected_modes': dict(modes), 'rows': rows, 'seconds': time.perf_counter() - start}
