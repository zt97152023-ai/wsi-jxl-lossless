import numpy as np
import pytest

from wsi_jxl.operators import fit_context_color, context_color, spatial_predict


@pytest.mark.parametrize('mode', ['dc2', 'dc4', 'texture2', 'dc_texture4'])
def test_context_operator_restores_all_int16_coefficients(mode):
    cube = np.random.default_rng(441).integers(-32768, 32768, (2, 3, 7, 9, 64), dtype=np.int16)
    cube[0, 0, 0, 0, :4] = [-32768, -1, 0, 32767]
    model = fit_context_color(cube, mode)
    residual = context_color(cube, model)
    assert np.array_equal(residual[:, 1], cube[:, 1])
    assert np.array_equal(context_color(residual, model, inverse=True), cube)


def test_constant_contexts_have_finite_reversible_models():
    cube = np.zeros((1, 3, 4, 4, 64), dtype=np.int16)
    cube[:, 0, ..., 0] = 300
    cube[:, 1, ..., 0] = 290
    cube[:, 2, ..., 0] = 310
    for mode in ('dc2', 'dc4', 'texture2', 'dc_texture4'):
        model = fit_context_color(cube, mode)
        assert np.array_equal(context_color(context_color(cube, model), model, inverse=True), cube)


@pytest.mark.parametrize('mode', ['dc_med', 'low_med'])
@pytest.mark.parametrize('shape', [(1, 3, 1, 1, 64), (2, 3, 7, 9, 64)])
def test_spatial_operator_preserves_extremes_and_odd_grids(mode, shape):
    cube = np.random.default_rng(8).integers(-32768, 32768, shape, dtype=np.int16)
    copy = cube.copy()
    residual = spatial_predict(cube, mode)
    assert np.array_equal(spatial_predict(residual, mode, inverse=True), cube)
    assert np.array_equal(cube, copy)
