# 公开 WSI 数据

全部来源为公开 CC0 OpenSlide 测试数据。Small-Region 是 CMU-1 裁剪，不能计作新的独立切片。Git 只保存本清单，不保存 WSI。

| 文件 | 字节数 | 下载 | SHA-256 |
|---|---:|---|---|
| CMU-1-Small-Region.svs | 1,938,955 | [镜像](https://raw.githubusercontent.com/libvips/libvips/master/test/test-suite/images/CMU-1-Small-Region.svs) / [原始入口](https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/CMU-1-Small-Region.svs) | `ed92d5a9f2e86df67640d6f92ce3e231419ce127131697fbbce42ad5e002c8a7` |
| CMU-1.svs | 177,552,579 | [镜像](https://storage.googleapis.com/imagebox_test/openslide-testdata/Aperio/CMU-1.svs) / [原始入口](https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/CMU-1.svs) | `00a3d54482cd707abf254fe69dccc8d06b8ff757a1663f1290c23418c480eb30` |
| CMU-2.svs | 390,750,635 | [镜像](https://storage.googleapis.com/imagebox_test/openslide-testdata/Aperio/CMU-2.svs) / [原始入口](https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/CMU-2.svs) | `fb6df83bfd91a252185c9652aebeb00deff84e49329f7ff8f75744f31f475b08` |

下载到 `data/` 后校验，例如：

```bash
python3 scripts/verify_data.py CMU-1-Small-Region.svs
```

省略文件名会检查全部三份数据。校验脚本只读取文件，不下载、不覆盖。镜像位置可能变化，文件内容以本清单大小和 SHA-256 为准。历史完整元数据保留在 `results/source-manifest.json` 和 `results/round4-source-cmu2.json`。

许可依据：[OpenSlide 测试数据入口](https://openslide.cs.cmu.edu/download/openslide-testdata/)、[QuPath 对 CC0 测试数据的说明](https://qupath.readthedocs.io/en/0.3/docs/intro/acknowledgements.html)。
