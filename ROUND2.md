# 第二轮：100.85 MB 之后还能压多少

2026-10-28；同一张 CMU-1 完整 SVS，继续保持原文件逐字节恢复。

本轮实际生成的最小归档为 **99,009,379 字节（99.009 MB）**。相对于上一轮的 100,848,801 字节，再减少 **1,839,422 字节，约 1.82%**；相对于原始 177,552,579 字节 SVS，总共减少 **44.24%**。

## 完整归档结果

| 配置 | 实际归档字节数 | MB | 解码分组数 |
|---|---:|---:|---:|
| 上轮：JXL effort 7，256 图块组，Zstd 9 | 100,848,801 | 100.849 | 98 |
| 仅提高 JXL effort 到 9，保持 256 图块组 | 99,946,131 | 99.946 | 98 |
| effort 7，大分组，Zstd 9 | 100,516,440 | 100.516 | 7 |
| effort 9，大分组，Zstd 9 | 99,267,232 | 99.267 | 7 |
| effort 9，大分组，逐组压缩器搜索 | **99,009,379** | **99.009** | **7** |

大分组以约 4,096 图块为目标，同时设置 32 MiB 原始 SVS 字节上限；实际 7 组分别覆盖约 5.6–31.7 MB 原始压缩字节。两个 effort 的输入基线分组粒度不同，达到字节上限时的切分可能略有区别；最干净的 effort 消融是表中的前两行，它们具有相同的 98 个分组。

最后一行在相同大分组内比较 JXL 记录的 Zstd 9/15/19、原文件片段的 Zstd 9/15/19、原始记录、原始文件片段，以及 JXL 记录的 Brotli 11。7 组均选择了 Brotli。所有大小均包含完整容器、原始非 JPEG 数据、记录和校验信息。

## 收益来源与代价

沿 effort 9 路线分解，相比上轮依次节省：

1. **JXL 更充分的编码搜索：902,670 B。** 原来的 imagecodecs JPEG 重压缩接口没有开放 effort 参数；本轮通过 libjxl C API 使用 effort 9。仍走 JPEG 码流重构路径，不先解码像素再重编码 JPEG。
2. **扩大分组：678,899 B。** 扩大重复信息搜索的上下文，同时减少分组开销。
3. **外层压缩器选择：257,853 B。** 这部分是组合压缩器的贡献，不能算作 JXL 核心算法改进。

本次 effort 9 的整片编码记录为 88.6 秒；重用其 JXL 记录进行最终外层候选搜索为 276.9 秒。这些是本机探索运行时间，不是受控的跨算法性能比较。仅用大分组 Zstd 9 的重封装约 1.54 秒，比最终搜索多占约 0.26 MB，是值得保留的实用配置。

压缩收益已有递减趋势。7 个大组有利于归档容量，但局部查询可能需要恢复数十 MB 的原始压缩字节，不能把最小归档作为交互式病理查看或 spot patch 访问的默认配置。上一轮固定 16/32 图块的小组方案仍然有用途。本轮没有重新宣称 ROI 加速。

## 已验证、但没有采用的方向

- **effort 并非越大越好。** 同一几何面板的 96 个 JPEG 图块，effort 7/8/9/10 的 JXL 总载荷分别为 537,419 / 532,466 / 528,950 / 530,246 B；91 个图块在 effort 9 下最小。因此没有直接选 effort 10。
- **显式共享相同 JXL box 没有带来新增收益。** 全片 effort 7 记录中，`jbrd` box 共占 6,022,412 B，但仅有一种 242 B 内容。将重复 box 改为字典引用可以把未压缩记录从 113,703,901 B 减至 107,040,236 B；再做 Zstd 后却从 100,843,057 B 增至 101,412,031 B。已有 Zstd 已利用了大量重复信息，显式改写反而不利。这是载荷消融，不是额外生成的获胜归档。
- **颜色相关性预测已被现有 JXL 利用。** 96 个图块在 effort 9 的默认设置与显式打开 CFL 下都是 528,950 B；关闭 CFL 增至 616,107 B。不能将“开启颜色相关性预测”宣称为本项目的新病理算法。
- **外层参数不能只看数值大小。** 12 个分组的初筛中，Zstd 19/22 未稳定胜过 9/15；LZMA 6 也未胜出。Brotli 11 小幅更好，但计算明显更慢，随后才扩展到整片验证。
- 最新主分支文档中的 JPEG 重构低频平滑选项在本机 libjxl 0.12.0 返回不支持，未纳入实现，也没有用有损图像平滑代替。

## 无损与兼容性

`results/round2-verification.json` 由 `scripts/verify_round2.py` 产生：每个新增归档均在新的 Python 进程中完整恢复，核对 177,552,579 个字节对应的 SHA-256。另有一个随机图块读取的功能检查，不能当作 ROI 性能基准。

源文件 SHA-256：

`00a3d54482cd707abf254fe69dccc8d06b8ff757a1663f1290c23418c480eb30`

所有金字塔、原 JPEG 字节、ICC、标签图和其他原文件内容均保留。原 SVS 自身已经 JPEG 压缩；无损保证的基准仍是该输入文件。

本轮容器新增组模式 `4`，表示 Brotli 压缩的 JXL 记录，需使用本轮解码器。旧归档仍可读取。JXL 码流仍遵守现有标准，`.wjxl` 仍是项目自定义外层容器，尚未成为原生 OpenSlide 支持的文件类型。

## 复现

```bash
# 得到 effort 9 的实际归档和可复用的 JXL 记录基线
PYTHONPATH=src .venv/bin/python scripts/archive_cli.py encode \
  data/CMU-1.svs results/cmu1-e9-g256.wjxl \
  --jpeg-effort 9 --group-tiles 256 \
  --baseline results/cmu1-e9-jxl-baseline.wjxl \
  --report results/cmu1-e9-g256-encode.json

# 大分组和外层压缩器搜索，输出目标必须不存在
PYTHONPATH=src .venv/bin/python scripts/round2_repack.py

# 独立进程完整验证
PYTHONPATH=src .venv/bin/python scripts/verify_round2.py
```

筛选脚本：`scripts/probe_round2.py`、`scripts/probe_round2_structure.py`。相关代码：`native.py`、`repack.py`；`boxes.py` 保留作为未奏效的可复现实验，没有进入获胜归档路径。正确性测试见 `results/tests-round2.log`。

原生接口目前明确限定为已测试的 libjxl 0.12.0，并要求 imagecodecs 安装包附带可定位的共享库。参数含义依据 [libjxl 编码接口](https://github.com/libjxl/libjxl/blob/main/lib/include/jxl/encode.h) 和 [effort 说明](https://github.com/libjxl/libjxl/blob/main/doc/encode_effort.md)；默认 Python 包装器的参数范围见 [imagecodecs JPEG XL 实现](https://github.com/cgohlke/imagecodecs/blob/master/imagecodecs/_jpegxl.pyx)。主分支文档可能包含本机版本尚不支持的选项，实际支持情况以本轮调用与往返验证为准。

目前得到的是同片探索中的进一步压缩，不是跨切片结果，也不是新颖性证明。若继续追求明显高于这 1.82% 的收益，应研究不同组织区域的 JPEG 系数统计、上下文共享和二维邻域布局，并与已充分调参的 JXL 基线比较，而不能只与默认配置比较。
