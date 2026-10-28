"""Self-describing reversible RGB/lift packets with standard JXL payloads."""
import time
import imagecodecs
import numpy as np
from .transforms import fit_lift, lift_forward, lift_inverse, pack_params, unpack_params

MAGIC = b'WJT1'


def _jxl(rgb, effort):
    return imagecodecs.jpegxl_encode(np.ascontiguousarray(rgb), lossless=True,
                                    distance=0, effort=effort, numthreads=1)


def encode_tile(rgb, *, adaptive=False, effort=7):
    start = time.perf_counter()
    baseline = MAGIC + b'\x00' + _jxl(rgb, effort)
    stats = {'rgb_bytes': len(baseline), 'selected_mode': 'rgb'}
    selected = baseline
    if adaptive:
        params = fit_lift(rgb)
        lifted = MAGIC + b'\x01' + pack_params(params) + _jxl(lift_forward(rgb, params), effort)
        stats['lift_bytes'] = len(lifted)
        if len(lifted) < len(baseline):
            selected, stats['selected_mode'] = lifted, 'lift'
    stats['encode_seconds'] = time.perf_counter() - start
    return selected, stats


def decode_tile(packet):
    if len(packet) < 6 or packet[:4] != MAGIC:
        raise ValueError('Invalid or truncated tile packet')
    mode = packet[4]
    if mode == 0:
        return imagecodecs.jpegxl_decode(packet[5:], numthreads=1)
    if mode == 1 and len(packet) > 25:
        params = unpack_params(packet[5:25])
        return lift_inverse(imagecodecs.jpegxl_decode(packet[25:], numthreads=1), params)
    raise ValueError('Unknown mode or truncated lift parameters')
