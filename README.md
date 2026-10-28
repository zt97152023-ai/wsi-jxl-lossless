# WSI × JPEG XL 严格无损实验

这是针对病理全切片的可运行研究原型：利用 JPEG XL 精确重压缩 SVS 中的 JPEG 图块，再利用跨图块重复信息和组织空间分布，比较归档大小与局部读取成本。表达矩阵继续使用用户原有的 [Shared count codec](https://github.com/zt97152023-ai/shared-st-count-codec)，本项目没有改动该方法。

实验结果见 [RESULTS.md](RESULTS.md)，原始测量与逐图块查询记录保存在 `results/`。这是单张公开切片上的探索实验，尚无跨切片泛化或新颖性结论。

第二轮进一步压到 **99.009 MB**，比第一轮最小归档再减少 **1.82%**；使用更高 JXL 编码搜索强度、大分组和外层 Brotli，适合容量优先的归档实验。消融、计算代价和独立校验见 [ROUND2.md](ROUND2.md)。第一轮报告保留原始结果，不覆盖历史记录。

第三轮进入量化 DCT 系数的联合无损编码：冻结配置后，同一切片的 144 个新图块中，组织内部比匹配的原生 JXL+Brotli 再小 **4.88%**，混合区域小 **0.63%**，背景却增大 **3.56%**。区域分组的匹配消融也有收益，但这些尚不是新整片归档；当前整片纪录仍为 99.009 MB。机制、负结果、颜色解释修复和复现见 [ROUND3.md](ROUND3.md)。

## 无损契约

最终解码必须恢复**整个原始 SVS 文件的所有字节**，包括所有金字塔层、ICC、标签图、宏观图、TIFF 目录、原始 JPEG 码流和未解释的字节。每个分组有 SHA-256，完整恢复还校验源文件长度和 SHA-256。分类器判断错了只能影响压缩率或速度，不能改变内容。

CMU-1 原文件已经使用 JPEG Q30；本项目保证相对于该输入文件不增加任何损失，不能恢复扫描仪在首次 JPEG 压缩前丢失的信息。

输出 `.wjxl` 是本项目的实验归档容器，内部使用标准 JXL 载荷；它不是可直接交给通用 JXL 查看器或 OpenSlide 打开的 `.jxl` 文件。恢复的 `.svs` 可以由 OpenSlide 打开。`ArchiveReader` 提供按需恢复的 Python 文件接口，可供 tifffile 读取目录和图块。

## 病理特点如何进入编码

| 病理切片的特点 | 实际实现 | 信息保留方式 |
|---|---|---|
| 大面积玻片背景与稀疏组织 | 连续图块分组，比较 JXL、JXL+Zstd、原字节+Zstd、原字节四条路 | 背景像素和扫描噪声全部保留 |
| 组织内部与组织边界访问需求不同 | 从现有低分辨率金字塔得到前景比例，选择分组边界和大小 | 只影响编码分组，解码不依赖分类器 |
| SVS 共享 JPEG 表 | 补齐共享表后调用 JXL JPEG 重压缩，恢复时移除补入前缀 | 原图块字节及原始表均恢复 |
| 多尺度、标签图、ICC 和复杂目录 | 对源文件字节空间做连续、无遗漏的分区 | 不重建 TIFF 目录，不丢弃金字塔 |
| spot/patch 局部访问 | 扫描小型分组头建立索引，只解码命中的分组 | 已访问分组逐组校验 |
| 染色图像的颜色相关性与区域同质性 | 第三轮增加分组的逐频率整数 DCT 颜色预测候选 | 模型和残差全部保存；尚未加入整片归档路径，不是染色分离 |

前景判据为 `(min(R,G,B)<220 且 max-min>20) 或 max(R,G,B)<180`；图块前景比例 ≤0.05 为背景，≥0.8 为组织，其余为混合/边界代理。这是粗略编码特征，不能当作医学标注或可靠的组织分割结果。当前金字塔映射假定各 tiled RGB page 视野对齐，已在本次 Aperio 样本上使用，未验证其他厂商多场景文件。

## 运行

从项目根目录运行；开发环境为 macOS arm64 / Python 3.13。依赖版本在 `requirements.lock.txt`。

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
# 新增系数实验测试需要本机已安装 Homebrew jpeg-turbo
.venv/bin/python scripts/build_coefficients.py
.venv/bin/python -m pytest -q -W error
```

公开数据原始入口为 [OpenSlide Aperio 测试数据](https://openslide.cs.cmu.edu/download/openslide-testdata/Aperio/)，文件为 `CMU-1.svs`，CC0。已下载文件位于 `data/CMU-1.svs`；镜像地址、源文件 SHA-256、金字塔信息见 `results/source-manifest.json`。不要将 Small-Region 裁剪图当作独立整张切片。

编码和恢复（目标文件必须不存在）：

```bash
PYTHONPATH=src .venv/bin/python scripts/archive_cli.py encode \
  data/CMU-1.svs results/example.wjxl \
  --group-tiles 64 --report results/example-encode.json

PYTHONPATH=src .venv/bin/python scripts/archive_cli.py decode \
  results/example.wjxl --output results/example-restored.svs \
  --report results/example-decode.json

cmp data/CMU-1.svs results/example-restored.svs
```

不指定 `decode --output` 时仍会逐字节重构并完整校验，只是不写出第二份 SVS。

实验配置：

- `--grouping fixed --group-tiles N`：固定分组，已测 N=16/32/64/128/256。
- `--grouping tissue`：在页面和粗分类改变处断组，背景/混合/组织上限为 256/32/64 图块。
- `--grouping tissue-local`：后续局部访问候选，上限为 64/8/32，参数是在同一切片的探索过程中调整的。
- `--baseline path.wjxl`：同时实际写出相同分组方式的逐图块 JXL 基线归档。
- `--jpeg-effort 9 --zstd-level 15`：设置 JPEG 重压缩搜索强度和外层 Zstd 参数；原生 effort 接口目前限定 libjxl 0.12.0。
- 每种 `policy` 的当前编码实现都会执行候选比较，不能将其总编码时间解释为单独 JXL 基线耗时。

```python
import tifffile
from wsi_jxl.reader import ArchiveReader

with ArchiveReader('results/example.wjxl') as stream:
    with tifffile.TiffFile(stream) as tif:
        page = tif.pages[0]
        offset, count = page.dataoffsets[0], page.databytecounts[0]
        stream.seek(offset)
        original_jpeg_tile = stream.read(count)
```

局部查询只验证所访问的分组；全文件一致性需要运行 `decode`。当前索引是在打开归档时扫描分组头建立，尚未实现持久化的二维 ROI 索引、HTTP Range 或查看器插件。

## 结果复核与继续研究

`scripts/verify_archives.py` 为每个归档启动独立解码进程。`scripts/analyze_pathology.py --sweep` 使用预先定义的每类 24 个图块面板，重复查询 3 次；逐次清空解码分组缓存，操作系统文件缓存未控制。`--local` 比较后续组织分组与固定 16/32 图块。所有像素对照使用相同 JPEG 解码器，避免把不同解码器的舍入差异误判为压缩失真。

JPEG XL 自身已有 JPEG 码流精确恢复和 Modular 无损工具；这些不是本项目的新发明。完整归档路径目前围绕 WSI 封装、分组、编码路由和局部访问优化；第三轮另有系数预测实验，还未修改 libjxl 的核心熵编码器。要提出编码器层面的新算法，需要与通用特征分组及已有病理 JPEG 重压缩方法在相同无损契约下比较。

参考：[libjxl 格式说明](https://github.com/libjxl/libjxl/blob/main/doc/format_overview.md)、[OpenSlide Aperio 结构](https://openslide.org/formats/aperio/)、[WISE，CVPR 2025](https://arxiv.org/abs/2503.18074)。WISE 的像素压缩比不能直接与本项目相对于已压缩 SVS 字节的比例相比较。
