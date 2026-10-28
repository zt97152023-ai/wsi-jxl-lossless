# 第四轮：8×8 块上下文条件颜色算子

2026-10-29。本轮实现了可逆的条件颜色预测、空间预测和频率重排算子。亮度条件预测在两张公开切片的抽样验证中进一步减少了体积；纹理分组和额外空间预测没有取得稳定优势。已有完整 CMU-1 最佳归档仍为 **99,009,379 B**，本轮没有生成新的完整大切片归档。

新算子位于原始 JPEG 量化系数与 JXL Modular 之间，标准 JXL 负责无损整数载荷。**没有修改 libjxl 内部的 MA 决策树、ANS 或 JPEG XL 标准**；新增算子与重建参数由自定义包负责解释。它是能够运行的算子原型，尚非已证明新颖的病理专用编码标准。

## 算子如何利用图像结构

第三轮每个图块组、每个 DCT 频率只有一套颜色预测关系。本轮检验：同一图块内亮度不同的局部块，是否需要不同的关系。深染与浅染等病理外观差异是动机，但状态只由整数系数确定，不对应经过标注的细胞类型。

对每个 8×8 块，保留 G 分量的所有原始量化系数，以其 DC 系数确定二分位或四分位状态：

```text
s = bin(G_DC; 已存入包的阈值)
R残差[k] = wrap16(R[k] − round_fixed(a[s,k]·G[k] + b[s,k]))
B残差[k] = wrap16(B[k] − round_fixed(c[s,k]·G[k] + d[s,k]·R[k] + e[s,k]))
```

参数采用 1/256 固定点。解码先由保留的 G 计算相同状态，再恢复 R，然后恢复 B，所有回绕在 16 位整数域中可逆。**不需要传输逐块组织掩膜**，但阈值、各状态的预测参数、JPEG 头尾、重建模板和 SVS 补表移除规则都传输并计费。参数拟合使用当前编码组的数据；因为完整参数存入包，解码不依赖浮点拟合的跨平台重现，也不依赖原始切片。

对应代码：[算子](src/wsi_jxl/operators.py)、[版本化数据包](src/wsi_jxl/coeffpacket.py)。新增功能使用 `CJT2`，旧 `CJT1` 仍可解码；旧解码器不能解释新算子。

## 开发筛选与冻结验证

协议见 [ROUND4-PLAN.md](ROUND4-PLAN.md)。沿用第三轮 48 个开发图块，按原 JPEG 长度排序，每 16 个一组，统一 Modular effort 10。比较的是完整包大小。所有候选都做逐字节恢复检查。

| 开发候选 | 相对第三轮单模型再减少 |
|---|---:|
| DC 四状态条件颜色 | **1.91%** |
| DC 二状态条件颜色 | **1.81%** |
| DC×纹理四状态条件颜色 | 1.39% |
| zigzag 频率重排 | 0.76% |
| 二维频率平面布局 | −0.06% |
| DC 的 MED 空间预测 | −0.09% |
| 纹理二状态条件颜色 | −0.14% |
| 三个低频的 MED 空间预测 | −2.52% |

按实际总大小选出 DC 四状态（dc4）和二状态（dc2），在 [冻结配置](results/round4-frozen.json) 中记录后再运行验证。两个验证面板没有重新选择参数规则或布局。传统 MED、频率扫描、整数提升不是本项目新发明；普通空间预测失败的一个可能原因是 JXL 已有相近工具，但当前实验没有单独证明这个解释。

第一组验证是 CMU-1 的另外 192 个 level-0 图块，排除第三轮 48 个开发图块和 144 个留出图块，每个区域代理抽 64 个，种子 `202610294`。第二组来自**另外一张 CMU-2.svs**，从全部 level-0 图块中均匀抽 192 个，种子 `202610295`，包含 131 个背景、41 个混合和 20 个组织代理图块。

CMU-2 下载来源及 SHA-256 见 [数据清单](results/round4-source-cmu2.json)：390,750,635 B，78,000×30,462，约 23.76 亿像素。它与 CMU-1 同属 OpenSlide Aperio 公共数据，不能代替多医院、多扫描仪或独立患者队列。CMU-1-Small-Region 是同源裁剪，不算第三张独立切片。

所有验证方法使用**同样的 JPEG 长度分组**，每组 16 个。上一轮强基线为单一逐频率颜色模型＋JXL Modular effort 10；另保留原生 JPEG→JXL effort 9＋Brotli 11 对照。不同路径的 effort 数值不代表等计算成本。

| 验证面板 | 原生 JXL+Brotli/B | 第三轮强基线/B | dc4/B | dc4 比强基线再减少 | dc4 比原生对照减少 |
|---|---:|---:|---:|---:|---:|
| CMU-1，192 图块 | 1,909,595 | 1,834,353 | 1,808,327 | **1.42%** | 5.30% |
| CMU-2，192 图块 | 1,091,772 | 1,072,444 | 1,063,242 | **0.86%** | 2.61% |

dc2 相对强基线分别改善 1.14% 和 0.71%，略弱于 dc4。固定 dc4 在 CMU-1 的 12 组中胜出 9 组，在背景较多的 CMU-2 中只胜出 4 组；不应只报告总计而隐藏简单区域上的倒退。

冻结协议另允许逐组选择基线/dc2/dc4 中最小的**实际完整包**。选择可由包内版本、模型字段解释，无需隐藏分类器；对应总数为 1,807,361 B 和 1,060,372 B，相对强基线改善 1.47% 和 1.13%。这需要执行多个候选编码，有计算代价。

这些样本包包含所有模型与 JPEG 重建信息，但不包含完整切片目录、未抽中的数据、全片置换索引等共同开销。两个面板的抽样方式不同，不能把百分比相加、视作整片压缩比，或直接当作跨中心泛化结论。数据见 [开发结果](results/round4-pilot.json)、[同片留出结果](results/round4-holdout.json)、[另一切片结果](results/round4-cross-slide.json)。

## 完整文件接入与字节恢复

新增可选 [完整文件编码器](src/wsi_jxl/joint_archive.py)，保留源文件字节顺序，JPEG 组可使用新模式 5，其他数据及不支持的系数网格沿用原字节/Zstd/JXL+Brotli。普通分组 SHA-256 和整文件 SHA-256 契约继续有效，`ArchiveReader` 可按需恢复新模式。

在已有 `CMU-1-Small-Region.svs` 上进行了**完整裁剪文件**的端到端实验：

| 文件 | 实际大小/B |
|---|---:|
| 原始 SVS | 1,938,955 |
| 相同源顺序分组的传统编码路径 | 1,487,165 |
| 传统路径与 dc4 比较后选择 | **1,444,074** |

包括文件头、分组头、校验、所有 JPEG、TIFF 目录、关联图像及其余字节，总体减少 **43,091 B（2.90%）**。18 个组中，10 个使用 dc4，5 个用 JXL+Brotli，2 个用原字节 Zstd，1 个保持原字节。

这里比较的是完整裁剪文件的原生路径与 dc4 混合路径，**不是**前表的“单模型系数包 vs 条件模型系数包”；分组也采用源顺序。该小样证明容器接入可行，不能更新完整 CMU-1 的 99.01 MB 纪录。

两个归档分别在新进程中写出 SVS，再执行 `cmp`，均逐字节一致。恢复 SHA-256 为 `ed92d5a9f2e86df67640d6f92ce3e231419ce127131697fbbce42ad5e002c8a7`。另外验证了 50 个随机字节区间和 OpenSlide 打开后的尺寸（2220×2967）。见 [完整文件实验](results/round4-fullfile.json)、[新模式解码](results/round4-small-adaptive-decode.json)、[随机访问](results/round4-fullfile-access.json)。

完整裁剪文件传统路径记录耗时约 7.58 s，带新候选搜索的路径约 128.58 s。运行时的并行负载不同，这不是受控速度比较，且新路径包含候选试编码；只能据此提示当前原型计算成本较高，不能宣称生产可用的速度。图块验证的计时也不作为性能排名。

## 校验、局限与后续路线

- 全部 **126 个**开发、留出、另一切片的候选及对照数据包，在独立进程中、无需读取原始 WSI 解码，逐图块长度和 SHA-256 一致。[记录](results/round4-verification.json)
- 新解码器还重新验证了第三轮 **84 个旧包**，保持向后读取兼容。[记录](results/round4-backcompat.json)
- **69 项测试通过**，包括 int16 极值、奇数尺寸、空间预测边界、版本误标拒绝、标准 zigzag 次序、JPEG 精确恢复、删除源文件后恢复完整 TIFF、随机访问、非支持网格回退和已存在临时文件保护。
- 当前新算子针对相同分量网格的顺序 JPEG；色度降采样等不支持的组回退。不是任意 WSI/JPEG 的统一算子，也未完成恶意输入安全审计。
- DC 亮度状态不是细胞核、组织类型或染色组分标注。没有自然图像对照，不能宣称收益只属于病理领域；也没有证明四状态、当前阈值或回归目标最优。
- 下一步应在已冻结基线上研究**直接优化码长的模型参数/上下文分裂**，加入保留通道关系的多通道 JXL 表示对照，再考虑将有效逻辑迁入 C++ 或编码器上下文。金字塔条件预测仍未实现，需要显式规定坐标映射和解码依赖。
- 在扩展到更多公开切片、完成全尺寸归档及受控资源测试之前，不报告新整片容量纪录或接近压缩极限的结论。

## 复现

环境沿用固定的 imagecodecs/libjxl 和可选 libjpeg 系数适配器，见第三轮有效性清单。所有命令从项目根目录执行；实验脚本会写对应结果文件，完整归档输出必须不存在。

```bash
.venv/bin/python scripts/build_coefficients.py
PYTHONPATH=src .venv/bin/python -m pytest -q -W error
PYTHONPATH=src .venv/bin/python scripts/round4_operators.py pilot
.venv/bin/python scripts/freeze_round4.py
PYTHONPATH=src .venv/bin/python scripts/round4_operators.py holdout
.venv/bin/python scripts/download_validation_slide.py
PYTHONPATH=src .venv/bin/python scripts/round4_operators.py cross-slide
PYTHONPATH=src .venv/bin/python scripts/verify_round4.py \
  results/round4-pilot.json results/round4-holdout.json results/round4-cross-slide.json
PYTHONPATH=src .venv/bin/python scripts/round4_fullfile.py
PYTHONPATH=src .venv/bin/python scripts/archive_cli.py decode \
  results/round4-small-adaptive.wjxl --output results/round4-small-adaptive-restored.svs
cmp data/CMU-1-Small-Region.svs results/round4-small-adaptive-restored.svs
```

`round4_operators.py` 的前两阶段还需要已有 CMU-1、第三轮开发/留出清单、正确 RGB 特征缓存及第二轮原生 JXL 记录基线。验证脚本仅需要结果清单和保存的数据包。大载荷、WSI、编译产物不进入 Git。

参考边界：libjxl 自身已有梯度预测、加权预测与上下文决策树，见 [v0.12.0 官方预测器实现](https://github.com/libjxl/libjxl/blob/v0.12.0/lib/jxl/modular/encoding/context_predict.h)。已有病理 DCT 上下文重压缩研究包括 [ULRFM，Medical Image Analysis 2026](https://www.sciencedirect.com/science/article/pii/S1361841526002215)，本轮未复现该模型或完成全面新颖性检索，不能宣称首创或超过其结果。
