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


@pytest.mark.parametrize('objective', ['entropy', 'weak_entropy'])
def test_entropy_proxy_fitted_model_remains_byte_reversible(objective):
    cube = np.random.default_rng(251).integers(-512, 513, (2, 3, 16, 17, 64), dtype=np.int16)
    model = fit_context_color(cube, 'dc4', objective=objective)
    assert model['fit_objective'] == objective + '_proxy'
    residual = context_color(cube, model)
    assert np.array_equal(context_color(residual, model, inverse=True), cube)


def test_entropy_search_removes_exact_ac_color_relation_residuals():
    green = np.random.default_rng(72).integers(-3, 4, (2, 16, 17, 64), dtype=np.int16)
    cube = np.stack((2 * green, green, 3 * green), axis=1)
    previous = context_color(cube, fit_context_color(cube, 'dc4'))
    model = fit_context_color(cube, 'dc4', objective='entropy')
    residual = context_color(cube, model)
    assert np.count_nonzero(previous[:, 0, ..., 1:]) > 0
    assert np.count_nonzero(residual[:, 0, ..., 1:]) == 0
    assert np.array_equal(context_color(residual, model, inverse=True), cube)


def test_weak_ridge_control_handles_constant_and_collinear_channels():
    for green in (np.zeros((2, 16, 17, 64), dtype=np.int16),
                  np.random.default_rng(12).integers(-3, 4, (2, 16, 17, 64), dtype=np.int16)):
        cube = np.stack((2 * green, green, 3 * green), axis=1)
        model = fit_context_color(cube, 'dc4', objective='weak_ridge')
        assert np.isfinite(model['params']).all()
        residual = context_color(cube, model)
        assert np.count_nonzero(residual[:, 0]) == 0
        assert np.array_equal(context_color(residual, model, inverse=True), cube)
