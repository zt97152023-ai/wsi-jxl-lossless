# 第五轮：改写系数预测目标与三通道表示

2026-10-29。继续保证**原始 SVS 的所有字节完全恢复**，表达矩阵方法不变。本轮实际实现并比较了熵代理拟合、三通道 JXL 系数布局，以及事后增加的弱正则对照。

完整 `CMU-1-Small-Region.svs` 的最佳归档从上一轮 **1,444,074 B 降至 1,411,900 B，再减少 2.23%**。两个新抽样面板上，熵代理相对第四轮 dc4 基线分别减少 5.80% 和 5.03%；更简单的弱正则事后对照分别减少 6.16% 和 5.25%。这说明新路径有实际收益，但没有证据证明复杂搜索总比简单拟合好。完整大切片 CMU-1 的纪录仍为 **99,009,379 B**。

## 改动在哪一层

代码位于 [operators.py](src/wsi_jxl/operators.py)、[coeffpacket.py](src/wsi_jxl/coeffpacket.py) 和 [joint_archive.py](src/wsi_jxl/joint_archive.py)。改动的是 JXL 之前的**可逆量化 DCT 系数算子、系数表示和归档候选选择**。内部仍使用现有 libjxl 0.12.0 的无损编码器，没有重写其 C++ 预测器、上下文树或 ANS 熵编码核心。

输入保留 JPEG 原有量化系数、头尾、共享表及其余 SVS 字节。每组先检查 JPEG 熵编码字节可以精确重建，才允许进入新路径。所有模型、布局说明和 JPEG 重建信息都计入包大小；不支持的组回退到已有字节保存路径。

### 1. 条件颜色模型改用离散熵代理

第四轮根据保留的 G 通道 DC 系数将 8×8 块分成至多四个亮度状态，每个状态、每个频率分别预测 R 和 B。本轮保留该上下文，并对固定点预测系数作有限搜索。R 由 G 预测；B 由 G 和原始 R 预测，解码先恢复 R 再恢复 B。

对每个频率，搜索原斜率的若干倍数、零预测和通道复制，偏置由中位数确定；原模型也在候选集中。比较目标为：

`残差零阶经验熵的总比特数 + 2 × Σ log2(1 + |固定点模型参数|)`。

这是启发式代理，既不是 JXL 实际上下文码长，也不是实际模型序列化成本。它不能保证最终 JXL 文件更小，因此判断依据始终是**实际完整包字节数**。模型参数以 1/256 固定点保存，残差采用模 2^16 的可逆运算；解码不重新拟合，也不需要原切片或组织掩膜。

### 2. 保留三个系数通道

新增 `mosaic3` 布局，将三个分量按相同频率和块位置对齐，形成 uint16 的三通道图像交给 JXL；对照原来纵向拼接为单通道的布局。比较无外部颜色预测、单模型预测和 dc4 预测，并分别测试 zigzag 与加 32768 的 bias 映射。

三通道方案为 JXL 自身的通道变换提供不同输入表示，但不能据此断言编码器一定选择了某个具体变换。这里的“三通道图像”是系数载体，不是对病理像素进行颜色校正。

### 3. 重要的事后对照：削弱回归正则项

看到熵代理收益后，增加 `weak_ridge`：仅将原回归中加到方差项的正则量从 **1 改为 1e-6**，保留相同亮度状态、频率划分、固定点量化和灰度布局。

旧正则量可能对量化后方差很小的 AC 系数产生过强收缩。例如忽略偏置时，R 对 G 的拟合斜率为 `cov(R,G)/(var(G)+λ)`；当系数方差远小于 1 时，λ=1 会显著压低斜率。精确合成关系 `R=2G` 的测试能展示这一缺陷，而弱正则和熵搜索均能消除该测试中的 R 残差。

真实面板上弱正则也略胜熵搜索，**支持先排查原基线的收缩偏差**。这只是当前证据支持的机制解释，不能证明全部收益来自它，更不能把一般回归改进宣称为病理专属新算法。弱正则是在观察主实验结果后增加的，未改写已冻结的主候选清单。

## 开发筛选与固定规则验证

沿用已有 48 个开发图块，按原 JPEG 长度分成 3 组，每组 16 图块。JXL 系数编码统一 effort 10，原生 JPEG 重压缩对照为 effort 9 后接 Brotli 11。完整包包含模型和 JPEG 重建开销，但抽样汇总不含完整 WSI 目录、未抽中数据及共同集合索引。

| 开发候选 | 包总大小/B | 相对 dc4 减少 |
|---|---:|---:|
| 原 dc4 灰度 zigzag 基线 | 412,369 | — |
| dc4 灰度 bias | 437,523 | −6.10% |
| dc4 熵代理 | 391,700 | 5.01% |
| 三通道，无外部预测，zigzag | 429,190 | −4.08% |
| 三通道，无外部预测，bias | 408,416 | 0.96% |
| 三通道，单模型，zigzag | 413,384 | −0.25% |
| 三通道，单模型，bias | 412,554 | −0.04% |
| 三通道，dc4，zigzag | 408,974 | 0.82% |
| 三通道，dc4，bias | 409,926 | 0.59% |
| 弱正则，事后对照 | **389,839** | **5.46%** |

基线 412,369 B 与第四轮开发结果的 dc4 完全相同。按照预先记录的规则，在主验证之前冻结熵代理和三通道无外部预测 bias 两个候选。协议与记录：[计划](ROUND5-PLAN.md)、[冻结配置](results/round5-frozen.json)、[开发结果](results/round5-pilot.json)、[事后开发对照](results/round5-ridge-control.json)。

CMU-1 新抽 192 个图块，每代理类别 64 个，种子 202610296，排除第三轮开发/留出和第四轮留出。CMU-2 新均匀抽 192 个图块，种子 202610297，排除第四轮已用图块；实际含 140 个背景、30 个混合、22 个组织代理图块。两张切片本身此前都已接触过。

| 方法 | CMU-1 新面板/B | 相对 dc4 减少 | CMU-2 新面板/B | 相对 dc4 减少 |
|---|---:|---:|---:|---:|
| 原始 JPEG | 2,724,283 | — | 1,569,926 | — |
| 匹配原生 JXL+Brotli | 1,878,424 | — | 948,382 | — |
| 第四轮 dc4 基线 | 1,781,758 | — | 918,003 | — |
| 熵代理，冻结候选 | 1,678,422 | 5.80% | 871,795 | 5.03% |
| 三通道 bias，冻结候选 | 1,743,813 | 2.13% | 897,462 | 2.24% |
| 弱正则，事后匹配对照 | **1,671,958** | **6.16%** | **869,780** | **5.25%** |

熵代理在 CMU-1 的 12/12 组、CMU-2 的 8/12 组胜过 dc4；三通道分别为 11/12 和 12/12。弱正则比熵代理分别再小 0.39% 和 0.23%，但它是在**已经使用过的面板**上追加比较，不能作为新的独立留出验证。数据见 [CMU-1](results/round5-holdout.json)、[CMU-2](results/round5-cross-slide.json)、[弱正则 CMU-1](results/round5-ridge-control-holdout.json)、[弱正则 CMU-2](results/round5-ridge-control-cross-slide.json)。

两个面板抽样分布不同，百分比不能相加，也不能外推为整片容量收益。重复图块组不是独立患者；本轮不报告跨患者统计显著性。

## 完整裁剪文件的容量与速度

使用已有 `CMU-1-Small-Region.svs`（1,938,955 B），四种配置均采用源文件顺序、每组至多 16 图块，相同的原字节、Zstd、原生 JXL+Brotli 回退选项。每组只加入表中指定的一种系数候选；没有在四种算子之间同时选最小值。

| 系数候选 | 实际完整归档/B | 比上一轮 dc4 减少 | 编码/s | 三次预热后解码中位数/s |
|---|---:|---:|---:|---:|
| dc4 基线 | 1,444,074 | — | 158.58 | 1.030 |
| 弱正则 | 1,414,479 | 2.05% | 127.29 | 1.128 |
| 三通道 bias | 1,456,099 | −0.83% | 82.97 | 0.602 |
| 熵代理 | **1,411,900** | **2.23%** | 129.05 | 1.144 |

全部大小包括文件头、分组头、校验、所有 JPEG、TIFF 目录、关联图像与其余源字节。dc4 完整归档大小精确复现第四轮的 1,444,074 B；熵代理减少 32,174 B。它在此裁剪文件上比弱正则小 2,579 B，与抽样面板的排名不同。分组采用源顺序、包含不同层级与关联图像，而且会回退，因此不能把这里的差异直接归因于某个病理类别。

四种配置按固定随机种子 202610298 排定顺序串行执行，期间没有其他本任务编码/验证工作并行。每种只计时一次编码，首次恢复后再测三次完整解码；编码包括原生候选和系数候选试编、候选精确恢复检查。**操作系统负载和缓存未隔离**，原始负载记录保留。三通道在本次测量中较快而略大，但不能由一次小裁剪实验宣称稳定加速比、生产吞吐或弱正则比原模型计算更快。[原始记录](results/round5-fullfile.json)

四份归档均实际恢复为 SVS，并在另一个全新进程中重新完整解码验证。四个 `cmp` 均为 0，恢复 SHA-256 均为 `ed92d5a9f2e86df67640d6f92ce3e231419ce127131697fbbce42ad5e002c8a7`；另外各验证 20 个随机字节区间及 OpenSlide 的层级尺寸。[独立复核](results/round5-fullfile-verification.json)

这仍是同一张切片的裁剪文件，不是第三张独立 WSI，也不能更新完整 CMU-1 的 99.009 MB 纪录。

## 验证与证据边界

- **83 项测试通过**，覆盖三通道布局的两种整数映射、不同预测模式、真正进入熵搜索分支的系数往返、精确颜色关系、弱正则常量/共线情况，以及四种完整归档模式在删除源文件后的恢复和随机访问。
- 本轮 **153 个不同数据包**在独立验证进程中、不读取源 WSI，逐 JPEG 长度与 SHA-256 校验通过。主实验 126 个包，事后验证 54 条记录中有 27 个重复的原生对照，去重后为 153，不能相加成 180。[主实验](results/round5-verification.json)、[对照](results/round5-ridge-verification.json)
- 新解码器重新验证第四轮 **126 个旧包**。[兼容性](results/round5-backcompat.json) 汇总与代码哈希见 [validation](results/round5-validation.json)。
- 两张整片都标注 Aperio、**JPEG/RGB Q=30**，Photometric=2；源描述也给出相同 ScanScope ID。本轮没有不同扫描来源、压缩质量或颜色采样条件的验证。[输入范围审计](results/round5-source-scope.json)
- DC 状态只是亮度代理，既不是细胞核分割，也不是 H&E 染色浓度。没有自然图像对照，不能认定改进只适用于病理图像，更不能说病理信息已被用尽。
- 新系数路径仍要求可重建的 JPEG 和一致分量网格，色度降采样等不支持的情况回退。无损契约相对于输入 SVS；不能恢复原始 JPEG 首次量化前已经丢失的信息。
- `.wjxl` 是本项目实验容器，需要相应解码器。未完成生产安全审计、资源上限评估或跨平台编码复现评估。默认系数模式仍为 dc4，新模式均显式选择。

## 接下来的决策

保留熵代理和弱正则两条可选路径；当前证据不足以确立单一赢家。下一步优先对不同 JPEG 质量、颜色采样和扫描来源进行冻结规则验证，区分“纠正过强正则”与真正来自病理结构的收益，再在全尺寸 WSI 上与已有 99,009,379 B 的大分组强基线比较。更细的频率自适应正则、按真实包字节选择算子和跨尺度条件预测仍是待验证方向，没有在本轮结果中计入。

## 复现

沿用锁定环境与已构建的 libjpeg 系数适配器。主实验需要两份 WSI、第三/四轮抽样清单、正确的 RGB 特征缓存和既有原生 JXL 基线；数据下载方法见前轮报告。以下命令会重写对应测量清单，完整文件编码要求输出不存在，复现时应使用独立工作目录。

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q -W error
PYTHONPATH=src .venv/bin/python scripts/round4_operators.py pilot --round 5
.venv/bin/python scripts/freeze_round4.py --round 5
PYTHONPATH=src .venv/bin/python scripts/round4_operators.py holdout --round 5
PYTHONPATH=src .venv/bin/python scripts/round4_operators.py cross-slide --round 5
PYTHONPATH=src .venv/bin/python scripts/round5_ridge_control.py --stage pilot
PYTHONPATH=src .venv/bin/python scripts/round5_ridge_control.py --stage holdout
PYTHONPATH=src .venv/bin/python scripts/round5_ridge_control.py --stage cross-slide
PYTHONPATH=src .venv/bin/python scripts/verify_round4.py \
  results/round5-pilot.json results/round5-holdout.json results/round5-cross-slide.json \
  --output results/round5-verification.json
PYTHONPATH=src .venv/bin/python scripts/verify_round4.py \
  results/round5-ridge-control.json results/round5-ridge-control-holdout.json \
  results/round5-ridge-control-cross-slide.json --output results/round5-ridge-verification.json
PYTHONPATH=src .venv/bin/python scripts/round5_fullfile.py
PYTHONPATH=src .venv/bin/python scripts/archive_cli.py decode \
  results/round5-small-entropy.wjxl --report results/round5-small-entropy-decode.json
cmp data/CMU-1-Small-Region.svs results/round5-small-entropy-restored.svs
```

完整文件可选 API：`encode_joint_archive(source, output, coefficient_mode='entropy', group_tiles=16, effort=10)`；另可显式选择 `dc4`、`weak_ridge`、`mc_none_bias`。研究脚本保留 round4 默认行为；运行第五轮必须给出 `--round 5`。

实现依据：[imagecodecs 的 JXL 编码接口](https://github.com/cgohlke/imagecodecs/blob/master/imagecodecs/_jpegxl.pyx)、[libjxl 编码 API](https://github.com/libjxl/libjxl/blob/main/lib/include/jxl/encode.h)。这些资料支持接口与无损编码路径的实现方式，不构成本方法新颖性或病理效果的证据。本轮未完成新的全面文献检索或与已有病理重压缩模型的公平复现比较。
