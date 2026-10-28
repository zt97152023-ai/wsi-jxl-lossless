import unittest
import numpy as np
from wsi_jxl.transforms import fit_lift, lift_forward, lift_inverse, pack_params, unpack_params


class ReversibleLiftTests(unittest.TestCase):
    def test_extreme_and_random_rgb_round_trip(self):
        rng = np.random.default_rng(84027)
        cases = [rng.integers(0, 256, (31, 47, 3), dtype=np.uint8),
                 np.zeros((5, 7, 3), dtype=np.uint8),
                 np.full((7, 3, 3), 255, dtype=np.uint8),
                 np.array([[[0, 255, 0], [255, 0, 255]]], dtype=np.uint8)]
        for original in cases:
            with self.subTest(shape=original.shape, first=original.flat[0]):
                params = unpack_params(pack_params(fit_lift(original)))
                restored = lift_inverse(lift_forward(original, params), params)
                self.assertEqual(restored.dtype, original.dtype)
                np.testing.assert_array_equal(restored, original)

    def test_arbitrary_predictors_and_overflow_remain_reversible(self):
        rng = np.random.default_rng(42)
        original = rng.integers(0, 256, (23, 19, 3), dtype=np.uint8)
        for params in [(0, 0, 0, 0, 0), (-2048, 65536, 2048, -2048, -65536),
                       (256, 0, 0, 256, 0)]:
            np.testing.assert_array_equal(
                lift_inverse(lift_forward(original, params), params), original)

    def test_rejects_silent_dtype_conversion(self):
        with self.assertRaises(ValueError):
            fit_lift(np.ones((3, 4, 3), dtype=np.float32))


if __name__ == '__main__':
    unittest.main()
