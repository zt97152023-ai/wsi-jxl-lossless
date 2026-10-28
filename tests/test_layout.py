import numpy as np
from wsi_jxl.layout import appearance_features,morton,make_order,Record
from pathlib import Path
import tifffile
from wsi_jxl.layout import extract_features


def test_appearance_features_distinguish_glass_color_and_texture():
    glass=np.full((32,32,3),245,dtype=np.uint8)
    colored=np.full((32,32,3),[180,90,150],dtype=np.uint8)
    textured=colored.copy();textured[::2,::2]=[40,30,60]
    a,b,c=map(appearance_features,[glass,colored,textured])
    assert a['foreground']==0 and b['foreground']==1
    assert c['gradient']>b['gradient']
    assert c['dark']>b['dark']


def test_all_layouts_are_complete_permutations():
    records=[Record(i,i*4,4,b'abcd') for i in range(5)]
    features={0:{'page':0,'x':32,'y':0,**appearance_features(np.full((8,8,3),240,dtype=np.uint8))},
              8:{'page':0,'x':0,'y':32,**appearance_features(np.zeros((8,8,3),dtype=np.uint8))}}
    for name in ('original','morton','length','appearance','appearance_fine','shuffle'):
        order=make_order(records,features,name)
        assert sorted(order)==list(range(5))
    assert morton(0,0)<morton(1,0)<morton(0,1)


def test_rgb_tiff_declaration_overrides_ambiguous_jpeg_color_space(tmp_path):
    jpeg=(Path(__file__).parent/'fixtures/cmu1-rgb-background.jpg').read_bytes()
    path=tmp_path/'rgb.tif'
    tifffile.imwrite(path,iter([jpeg]),shape=(256,256,3),dtype=np.uint8,
                     photometric='rgb',tile=(256,256),compression='jpeg',
                     compressionargs={'outcolorspace':'RGB'})
    with tifffile.TiffFile(path) as tf:assert int(tf.pages[0].photometric)==2
    features=extract_features(path)
    feature=next(iter(features.values()))
    assert feature['foreground']<.05
    assert feature['brightness']>230
