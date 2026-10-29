# 跨机器交接：从这里开始

当前阶段：**六轮压缩研究已收尾，接下来以整理和论文写作为主。**继续写作不需要重新下载 WSI、编译 C 适配器或重跑实验。

研究冻结提交为 `b22d5086`；之后的交接修改只调整构建路径、证据索引和说明，没有改变压缩算子。当前没有论文主稿，也没有确定期刊模板；旧的 `docs/superpowers/specs/2026-09-29-shared-paper-design.md` 是此前 count 项目的写作工作区设计，不是本项目的实验结果。

## 在另一台机器上

从 GitHub 克隆本仓库，进入根目录后执行：

```bash
python3 scripts/check_handoff.py
```

该检查仅需 Python 3.9+ 标准库，不依赖 NumPy、JPEG XL 或原始切片。先读：

1. [writing/README.md](writing/README.md)：论文问题、证据范围和建议结构。
2. [writing/claims.csv](writing/claims.csv)：允许使用的数字、基线与限定条件。
3. [README.md](README.md)：代码和每轮研究入口。
4. [docs/CODE_MAP.md](docs/CODE_MAP.md)：模块职责与实验脚本索引。
5. [docs/REPRODUCIBILITY.md](docs/REPRODUCIBILITY.md)：需要运行代码时的环境与数据步骤。

写作时创建分支并同步，避免两台机器同时修改主分支：

```bash
git pull --ff-only
git switch -c codex/manuscript-draft
# 编辑稿件后
python3 scripts/check_handoff.py
git add writing/
git commit -m "docs: draft manuscript from verified WSI evidence"
git push -u origin codex/manuscript-draft
```

分支已存在时使用 `git switch codex/manuscript-draft`；不要重新创建同名分支。切换机器前先提交和推送，另一台机器先拉取。未提交的本地编辑不会随 GitHub 同步。

## 目前可以准确表述的结论

- 完整 CMU-1：177,552,579 → **99,009,379 B**，相对原 SVS 减少 **44.24%**；相对 effort 9 的逐图块 JXL 完整归档 111,269,933 B 减少 **11.02%**。收益包含分组和外层 Brotli，不能全归因于新系数算子。
- 第五轮熵代理：完整裁剪文件相对原有 JXL+Brotli 为主的回退路径减少 **5.06%**，相对第四轮 dc4 减少 **2.23%**，为 1,411,900 B。
- 第六轮现有方案逐组择优：完整裁剪文件进一步到 **1,410,920 B**，只多省 **980 B / 0.0694%**。
- 第五轮两张切片各 192 个图块的熵代理包，比匹配 JXL+Brotli 对照分别小 **10.65% / 8.08%**。这是抽样包结果，不是整片比例。
- 弱正则对照与第六轮开发探查的限定语见主张表；不要把二元概率模型评分的下降写成文件压缩率。

完整数据、负结果、测试和独立恢复记录均在 `results/`，其写作关键文件由 [evidence_manifest.json](writing/evidence_manifest.json) 记录 SHA-256。历史测试数量随轮次不同；交接阶段的测试另记在 `results/tests-handoff.log`。

## GitHub 中有什么、没有什么

代码、测试、小型公开测试图块、研究报告、JSON/CSV 测量和日志进入 Git。原始 WSI、虚拟环境、编译库、约 1.35 GB 的不同实验归档及系数数据包不进入普通 Git 历史。

这些大文件不影响查阅结果和写作，但**从 GitHub 克隆后，不能立即重新解码并独立验证历史归档**。需要按数据说明下载原始文件，并按对应轮次脚本重建产物，或另行传输本机保留的归档/数据包。历史校验报告保留原结果，不能冒充在新机器重新验证过。

## 给另一台机器上的助手

> 请先阅读 AGENTS.md、HANDOFF.md、writing/README.md 和 writing/claims.csv，运行 python3 scripts/check_handoff.py。当前研究冻结在第六轮，我现在要继续论文写作，不要自动启动新压缩实验。所有数字追溯到 results/，区分完整 WSI、同源裁剪和抽样面板，区分冻结候选与事后探索，保持原 SVS 全字节无损的研究契约。请先根据已允许的主张整理提纲和证据，再起草正文；未确定的作者、期刊和参考文献细节不要编造。
