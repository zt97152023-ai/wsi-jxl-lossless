"""Reversible coefficient operators; contexts are decoder-reconstructible proxies."""
import numpy as np


def _fit_color(cube):
    # Per-frequency adaptive coefficients; this is not stain separation. The
    # fixed-point parameters are stored, so decoder results never depend on
    # reproducing this floating-point fit or on having the source image.
    r,g,b=[cube[:,i].reshape(-1,64).astype(np.float64) for i in range(3)]
    mr,mg,mb=[v.mean(0) for v in (r,g,b)]
    r-=mr;g-=mg;b-=mb
    vr=(r*r).mean(0)+1;vg=(g*g).mean(0)+1;rg=(r*g).mean(0)
    gb=(g*b).mean(0);rb=(r*b).mean(0)
    alpha=np.clip(rg/vg,-8,8)
    det=vg*vr-rg*rg
    beta=np.clip((gb*vr-rb*rg)/det,-8,8)
    gamma=np.clip((rb*vg-gb*rg)/det,-8,8)
    return np.rint(np.stack([alpha,mr-alpha*mg,beta,gamma,mb-beta*mg-gamma*mr],axis=1)*256).astype(np.int64)


def _color_prediction(cube,params,inverse=False):
    # Arithmetic is modulo 2**16. Recover the wrapped original first channel
    # before predicting the third, including at signed integer boundaries.
    x=cube.astype(np.int64);p=np.asarray(params,dtype=np.int64)
    if p.shape!=(64,5):raise ValueError('Invalid color prediction parameters')
    pred_r=(x[:,1]*p[:,0]+p[:,1]+128)//256
    if inverse:
        x[:,0]=((x[:,0]+pred_r+32768)&65535)-32768
        pred_b=(x[:,1]*p[:,2]+x[:,0]*p[:,3]+p[:,4]+128)//256
        x[:,2]=((x[:,2]+pred_b+32768)&65535)-32768
    else:
        pred_b=(x[:,1]*p[:,2]+x[:,0]*p[:,3]+p[:,4]+128)//256
        x[:,0]-=pred_r;x[:,2]-=pred_b
    return x.astype(np.int16)


def _signals(cube):
    if cube.ndim != 5 or cube.shape[1] != 3 or cube.shape[-1] != 64:
        raise ValueError('Context color requires three 64-coefficient channels')
    green = cube[:, 1].astype(np.int64)
    return green[..., 0].ravel(), np.abs(green[..., 1:]).sum(-1).ravel()


def _labels(cube, model):
    dc, energy = _signals(cube)
    mode = model['mode']
    if mode not in ('dc2', 'dc4', 'texture2', 'dc_texture4'):
        raise ValueError('Unknown context color operator')
    d = np.searchsorted(model['dc_thresholds'], dc, side='right')
    e = np.searchsorted(model['energy_thresholds'], energy, side='right')
    return d + (len(model['dc_thresholds']) + 1) * e


def _rate_refine(cube, params):
    """Finite encoder-only search using zero-order entropy plus a model proxy.

    This is not JXL's contextual bit cost. Only complete encoded packet sizes
    can establish improvement. Stored fixed-point models keep decode unchanged.
    """
    r, g, b = [cube[:, i].reshape(-1, 64).astype(np.int64) for i in range(3)]
    result = params.copy()

    def score(residual, model):
        residual = ((residual + 32768) & 65535) - 32768
        _, counts = np.unique(residual, return_counts=True)
        n = len(residual)
        bits = n * np.log2(n) - np.sum(counts * np.log2(counts))
        return bits + 2 * np.log2(1 + np.abs(np.asarray(model))).sum()

    scales = (0, .5, .75, 1, 1.25, 1.5, 2)
    for k in range(64):
        target = r[:, k]; green = g[:, k]
        a, intercept, beta, gamma, offset = params[k].tolist()
        candidates = [(a, intercept)]
        slopes = {int(np.clip(round(a * s), -2048, 2048)) for s in scales} | {256}
        for slope in sorted(slopes):
            bias = int(np.rint(np.median(target * 256 - slope * green)))
            candidates.append((slope, bias))
        result[k, :2] = min(candidates, key=lambda p: score(target - (green * p[0] + p[1] + 128) // 256, p))
        blue = b[:, k]
        candidates = [(beta, gamma, offset)]
        pairs = {(int(np.clip(round(beta * s), -2048, 2048)),
                  int(np.clip(round(gamma * s), -2048, 2048))) for s in scales}
        pairs |= {(256, 0), (0, 256), (0, 0), (beta, 0), (0, gamma)}
        for slope_g, slope_r in sorted(pairs):
            bias = int(np.rint(np.median(blue * 256 - slope_g * green - slope_r * target)))
            candidates.append((slope_g, slope_r, bias))
        result[k, 2:] = min(candidates, key=lambda p: score(blue - (green * p[0] + target * p[1] + p[2] + 128) // 256, p))
    return result


def fit_context_color(cube, mode, *, objective='variance'):
    """Fit fixed-point color models, including every model in the packet."""
    dc, energy = _signals(cube)
    if mode not in ('dc2', 'dc4', 'texture2', 'dc_texture4'):
        raise ValueError('Unknown context color operator')
    if objective not in ('variance', 'entropy'):
        raise ValueError('Unknown color fitting objective')
    def thresholds(values, quantiles):
        return np.unique(np.floor(np.quantile(values, quantiles)).astype(np.int64)).tolist()
    model = {'mode': mode, 'dc_thresholds': [], 'energy_thresholds': []}
    if mode.startswith('dc'):
        model['dc_thresholds'] = thresholds(dc, [.25, .5, .75] if mode == 'dc4' else [.5])
    if mode in ('texture2', 'dc_texture4'):
        model['energy_thresholds'] = thresholds(energy, [.5])
    labels = _labels(cube, model)
    blocks = cube.transpose(0, 2, 3, 1, 4).reshape(-1, 3, 1, 1, 64)
    fallback = _fit_color(cube).tolist()
    model['params'] = []
    count = (len(model['dc_thresholds']) + 1) * (len(model['energy_thresholds']) + 1)
    for label in range(count):
        selected = blocks[labels == label]
        if len(selected) >= 32:
            params = _fit_color(selected)
            if objective == 'entropy':
                params = _rate_refine(selected, params)
            model['params'].append(params.tolist())
        else:
            model['params'].append(fallback)
    if objective == 'entropy':
        model['fit_objective'] = 'entropy_proxy'
    return model


def context_color(cube, model, inverse=False):
    labels = _labels(cube, model)
    blocks = cube.transpose(0, 2, 3, 1, 4).reshape(-1, 3, 1, 1, 64).copy()
    count = (len(model['dc_thresholds']) + 1) * (len(model['energy_thresholds']) + 1)
    if len(model['params']) != count or count > 4:
        raise ValueError('Invalid context model count')
    for label, params in enumerate(model['params']):
        mask = labels == label
        if mask.any():
            blocks[mask] = _color_prediction(blocks[mask], params, inverse=inverse)
    n, c, h, w, k = cube.shape
    return blocks.reshape(n, h, w, c, k).transpose(0, 3, 1, 2, 4)


def spatial_predict(cube, mode, inverse=False):
    """Per-tile causal MED lifting on DC or three low frequencies; modulo 2**16."""
    if mode not in ('dc_med', 'low_med'):
        raise ValueError('Unknown spatial operator')
    indices = [0] if mode == 'dc_med' else [0, 1, 8]
    values = cube[..., indices].astype(np.int32)
    if inverse:
        for y in range(values.shape[2]):
            for x in range(values.shape[3]):
                north = values[:, :, y - 1, x] if y else 0
                west = values[:, :, y, x - 1] if x else 0
                corner = values[:, :, y - 1, x - 1] if x and y else 0
                prediction = np.clip(north + west - corner, np.minimum(north, west), np.maximum(north, west))
                values[:, :, y, x] = ((values[:, :, y, x] + prediction + 32768) & 65535) - 32768
    else:
        north = np.zeros_like(values); west = np.zeros_like(values); corner = np.zeros_like(values)
        north[:, :, 1:] = values[:, :, :-1]
        west[:, :, :, 1:] = values[:, :, :, :-1]
        corner[:, :, 1:, 1:] = values[:, :, :-1, :-1]
        prediction = np.clip(north + west - corner, np.minimum(north, west), np.maximum(north, west))
        values -= prediction
    result = cube.copy()
    result[..., indices] = values.astype(np.int16)
    return result
