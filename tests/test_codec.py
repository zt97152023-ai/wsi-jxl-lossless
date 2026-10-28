import numpy as np
import pytest
from wsi_jxl.codec import encode_tile, decode_tile


@pytest.mark.parametrize('kind', ['random', 'gradient', 'constant'])
def test_adaptive_packet_is_exact_and_no_larger_than_identity(kind):
    rng = np.random.default_rng(77)
    if kind == 'random':
        x = rng.integers(0, 256, (35, 61, 3), dtype=np.uint8)
    elif kind == 'gradient':
        g = np.broadcast_to(np.arange(61, dtype=np.uint8), (35, 61))
        x = np.stack((g, g * 2, g * 3), axis=-1)
    else:
        x = np.full((35, 61, 3), 247, dtype=np.uint8)
    baseline, _ = encode_tile(x, adaptive=False, effort=3)
    candidate, stats = encode_tile(x, adaptive=True, effort=3)
    np.testing.assert_array_equal(decode_tile(candidate), x)
    assert len(candidate) <= len(baseline)
    assert stats['selected_mode'] in ('rgb', 'lift')


def test_unknown_or_incomplete_packet_is_rejected():
    with pytest.raises(ValueError):
        decode_tile(b'bad')
    with pytest.raises(ValueError):
        decode_tile(b'WJT1\x02anything')
