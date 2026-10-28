"""A deterministic coarse foreground proxy for coding experiments, not diagnosis.

Pyramid pixels guide encoder grouping only. No source pixels or bytes are
discarded, replaced, normalized, or inferred from this proxy at decoding time.
"""
import numpy as np
import tifffile


def foreground_mask(rgb):
    lo, hi = rgb.min(axis=2), rgb.max(axis=2)
    return ((lo < 220) & (hi.astype(np.int16) - lo > 20)) | (hi < 180)


def tile_features(source):
    """Map each tiled JPEG extent to its footprint in the smallest tiled page.

Assumes aligned pyramid pages, as in the tested Aperio SVS. Reject a missing
bounded overview rather than decoding a whole gigapixel image into memory.
"""
    features = {}
    with tifffile.TiffFile(source) as tf:
        tiled = [(i, p) for i, p in enumerate(tf.pages)
                 if p.is_tiled and len(p.shape) == 3 and p.shape[2] == 3]
        if not tiled:
            raise ValueError('No RGB tiled pyramid page available')
        overview_index, overview = min(tiled, key=lambda pair: pair[1].shape[0] * pair[1].shape[1])
        if overview.shape[0] * overview.shape[1] > 16_000_000:
            raise ValueError('Tissue grouping needs a bounded, aligned pyramid overview')
        rgb = overview.asarray()
        mask = foreground_mask(rgb)
        integral = np.pad(mask.astype(np.int64).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        mh, mw = mask.shape
        for pi, page in tiled:
            if int(page.compression) != 7:
                continue
            h, w = page.shape[:2]
            th, tw = page.tilelength, page.tilewidth
            columns = (w + tw - 1) // tw
            for si, offset in enumerate(page.dataoffsets):
                row, col = divmod(si, columns)
                x0, y0 = col * tw * mw // w, row * th * mh // h
                x1 = min(mw, (min(w, (col + 1) * tw) * mw + w - 1) // w)
                y1 = min(mh, (min(h, (row + 1) * th) * mh + h - 1) // h)
                count = integral[y1, x1] - integral[y0, x1] - integral[y1, x0] + integral[y0, x0]
                fraction = float(count / ((y1 - y0) * (x1 - x0)))
                category = 'background' if fraction <= 0.05 else 'tissue' if fraction >= 0.8 else 'mixed'
                features[int(offset)] = {'page': pi, 'segment': si, 'x': col * tw, 'y': row * th,
                                         'fraction': fraction, 'class': category}
    return features, {'overview_page': overview_index, 'overview_shape': list(rgb.shape),
                      'foreground_fraction': float(mask.mean()), 'diagnostic_segmentation': False,
                      'foreground_rule': '(min<220 and max-min>20) or max<180',
                      'background_max_fraction': 0.05, 'tissue_min_fraction': 0.8,
                      'assumption': 'tiled RGB pages share the same aligned field of view'}
