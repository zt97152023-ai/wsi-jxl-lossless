"""Reversible, integer-only decoder for a fitted triangular color lift.

Encoder fitting is floating point; the transmitted coefficients are integers.
All reconstructed pixels are exact even when a prediction is poor.
"""
import struct
import numpy as np

PARAMS = struct.Struct('<5i')


def _check(rgb):
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[-1] != 3 or not rgb.size:
        raise ValueError('Expected a nonempty H x W x 3 uint8 RGB array')


def fit_lift(rgb):
    _check(rgb)
    samples = rgb.reshape(-1, 3)[::max(1, rgb.shape[0] * rgb.shape[1] // 8192)]
    r, g, b = samples.astype(np.float64).T
    # Ridge on slopes only stabilizes nearly constant/collinear channels.
    def fit(a, y):
        penalty = np.eye(a.shape[1]) * 1e-3
        penalty[-1, -1] = 0
        beta = np.linalg.solve(a.T @ a + penalty, a.T @ y)
        beta[:-1] = np.clip(beta[:-1], -8, 8)
        beta[-1] = np.mean(y - np.sum(a[:, :-1] * beta[:-1], axis=1))
        return tuple(np.rint(beta * 256).astype(np.int64).tolist())
    return fit(np.column_stack((g, np.ones_like(g))), r) + fit(
        np.column_stack((g, r, np.ones_like(g))), b)


def pack_params(params):
    if len(params) != 5:
        raise ValueError('Expected five fixed-point coefficients')
    return PARAMS.pack(*params)


def unpack_params(data):
    return PARAMS.unpack(data)


def lift_forward(rgb, params):
    _check(rgb)
    a, c, d, e, f = params
    r, g, b = np.moveaxis(rgb.astype(np.int64), -1, 0)
    pred_r = (a * g + c + 128) >> 8
    pred_b = (d * g + e * r + f + 128) >> 8
    return np.stack((g, (r - pred_r + 128) & 255,
                     (b - pred_b + 128) & 255), axis=-1).astype(np.uint8)


def lift_inverse(encoded, params):
    _check(encoded)
    a, c, d, e, f = params
    g, u, v = np.moveaxis(encoded.astype(np.int64), -1, 0)
    r = (u - 128 + ((a * g + c + 128) >> 8)) & 255
    b = (v - 128 + ((d * g + e * r + f + 128) >> 8)) & 255
    return np.stack((r, g, b), axis=-1).astype(np.uint8)
