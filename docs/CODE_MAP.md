# 代码与实验地图

保留现有模块和脚本名称，避免破坏历史报告中的复现命令。代码根目录为 `src/wsi_jxl/`。

| 组件 | 职责 |
|---|---|
| `archive.py` | SVS 完整字节分区、JPEG 表处理、基础归档、组/全文件校验 |
| `reader.py` | 可 seek 的按组恢复接口；局部访问只验证访问到的组 |
| `native.py` | imagecodecs 所带 libjxl 0.12.0 的 JPEG 重压缩 effort 接口 |
| `repack.py` | 重用已有 JXL 记录，比较外层 Zstd/Brotli 和分组 |
| `tissue.py`, `layout.py` | 病理外观代理、正确 RGB 特征、图块顺序与实验布局 |
| `coefficients.py`, `native/jpeg_coefficients.c` | libjpeg 原始量化系数读写；不做像素变换 |
| `operators.py` | 可逆颜色、条件颜色、空间预测和编码端拟合 |
| `coeffpacket.py` | CJT/SCJ 自包含系数包；JXL 编码无损整数载荷 |
| `joint_archive.py` | 把系数候选接入完整文件的可选模式 5 |
| `platform_support.py` | 系数适配器构建与加载共用的平台路径 |
| `codec.py`, `transforms.py`, `boxes.py` | 保留的像素/整数变换与 box 探索工具；不是当前整片最佳路径 |

## 稳定使用入口

- `scripts/archive_cli.py encode/decode`：完整文件基础归档与恢复。
- `wsi_jxl.joint_archive.encode_joint_archive`：可选系数路径；默认 `dc4`，显式候选见 README。
- `scripts/build_coefficients.py`：在当前机器编译原生系数适配器。
- `scripts/check_handoff.py`：仅验证写作证据快照，Python 标准库即可运行。

## 历史研究脚本

| 脚本 | 对应材料 |
|---|---|
| `probe*.py`, `sweep_groups.py`, `analyze_pathology.py` | 第一/二轮开发和分组实验 |
| `round2_repack.py`, `verify_round2.py` | 第二轮完整文件与强基线 |
| `round3_*.py`, `verify_round3_packets.py` | 第三轮系数、外观与对照 |
| `round4_operators.py`, `freeze_round4.py` | 第四轮；第五轮必须显式加 `--round 5` |
| `round4_fullfile.py`, `round5_fullfile.py` | 各轮完整裁剪文件比较 |
| `round5_ridge_control.py` | 事后弱正则对照 |
| `round6_*.py` | 第六轮开发诊断与已有载荷组合 |
| `verify_round4.py` | 通用系数包独立验证；不同轮次务必指定 `--output` |

历史研究脚本依赖相应输入、先前轮次清单和忽略的大载荷；不把它们包装成一键运行全部实验。运行前阅读对应轮次报告，结果路径使用新的实验目录。
