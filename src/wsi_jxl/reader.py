"""Seekable original-TIFF byte view with bounded decoded-group caching.

Indexes group headers without decompressing the entire source. Each accessed
group is checksum verified; full-source verification remains decode_archive's job.
"""
from bisect import bisect_right
from collections import OrderedDict
import io
from pathlib import Path

from .archive import GROUP, read_metadata, parse_group_header, decode_group


class ArchiveReader(io.RawIOBase):
    def __init__(self, archive, *, cache_groups=2):
        super().__init__()
        self._stream = None
        self._cache = OrderedDict()
        if cache_groups < 0:
            raise ValueError('Cache size must be non-negative')
        self._stream = Path(archive).open('rb')
        self.name = str(archive)
        self._cache_limit = cache_groups
        self._position = 0
        self._offsets, self._entries = [], []
        self.decoded_groups = self.decoded_source_bytes = self.payload_bytes_read = 0
        try:
            self.metadata = read_metadata(self._stream)
            self.size = self.metadata['source_bytes']
            self.index_bytes_read = self._stream.tell()
            total, archive_size = 0, Path(archive).stat().st_size
            while header := self._stream.read(GROUP.size):
                _, original_size, _, payload_size, _ = parse_group_header(header)
                payload_offset = self._stream.tell()
                if payload_offset + payload_size > archive_size:
                    raise ValueError('Truncated group payload')
                self._offsets.append(total)
                self._entries.append((payload_offset, header, payload_size))
                total += original_size
                self.index_bytes_read += GROUP.size
                self._stream.seek(payload_size, io.SEEK_CUR)
            if total != self.size:
                raise ValueError('Indexed source size mismatch')
        except BaseException:
            self._stream.close()
            raise

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        self._checkClosed()
        return self._position

    def seek(self, offset, whence=io.SEEK_SET):
        self._checkClosed()
        if whence not in (io.SEEK_SET, io.SEEK_CUR, io.SEEK_END):
            raise ValueError('Invalid seek mode')
        position = offset + {io.SEEK_SET: 0, io.SEEK_CUR: self._position, io.SEEK_END: self.size}[whence]
        if position < 0:
            raise ValueError('Negative seek position')
        self._position = position
        return position

    def clear_cache(self):
        self._cache.clear()

    def _group(self, index):
        if index in self._cache:
            self._cache.move_to_end(index)
            return self._cache[index]
        offset, header, size = self._entries[index]
        self._stream.seek(offset)
        decoded = decode_group(self._stream, header)
        self.decoded_groups += 1
        self.decoded_source_bytes += len(decoded)
        self.payload_bytes_read += size
        if self._cache_limit:
            self._cache[index] = decoded
            while len(self._cache) > self._cache_limit:
                self._cache.popitem(last=False)
        return decoded

    def read(self, size=-1):
        self._checkClosed()
        remaining = max(0, self.size - self._position)
        remaining = remaining if size is None or size < 0 else min(size, remaining)
        chunks = []
        while remaining:
            index = bisect_right(self._offsets, self._position) - 1
            decoded = self._group(index)
            start = self._position - self._offsets[index]
            take = min(remaining, len(decoded) - start)
            chunks.append(decoded[start:start + take])
            remaining -= take
            self._position += take
        return b''.join(chunks)

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    def close(self):
        if not self.closed:
            if self._stream is not None:
                self._stream.close()
            self._cache.clear()
        super().close()
