# Shared-paper 写作工作区设计

## 1. 目标

在仓库根目录创建 `Shared-paper/`，作为一个可直接启动、可追溯证据、可自动检查的 LaTeX 论文写作工作区。它应将研究边界、核心主张、证据位置、正文、图表与质量检查放在同一条可审计链上。

## 2. 设计边界

- 保留用户指定的七个顶层组件：`AGENTS.md`、`research_brief.md`、`claims.csv`、`manuscript/`、`evidence/`、`figures/` 和 `checks/`。
- 不引入额外的项目管理层、包管理器或第三方 Python 依赖。
- 不填造研究结果、数字、文献或方法。未知内容以明确的占位符和状态字段表示。
- 项目第一轮固定为“论文审计”：识别当前主稿、抽取主张、追溯证据与版本、标记缺失和冲突。该轮不重写或润色手稿。
- 默认采用通用 IMRaD 结构，日后可根据期刊模板替换 `main.tex` 的文档类，而不改变证据和主张工作流。
- 不改动仓库中现有论文、证据、修订记录或构建产物。

## 3. 组件设计

### 3.1 项目控制文件

`AGENTS.md` 是 Codex 和其他协作者的长期规则，定义权威来源、不得造数据、主张变更要求、引用规则、编译与检查门槛。它还要强制“审计与改写分离”：在主稿和主张—证据表未冻结前，不得开始全文重写。

`research_brief.md` 是论文语义契约，包含研究问题、读者与目标期刊、预期贡献、明确非主张、数据/方法边界、当前结构、权威来源、术语约定和开放问题。

`claims.csv` 是机器可读的主张—证据表。字段固定为：

`claim_id,manuscript_version,manuscript_location,candidate_claim,claim_type,required_evidence,prohibited_substitute,evidence_id,evidence_location,evidence_version,code_version,experiment_version,verification_status,claim_decision,permitted_wording,scope_limit,conflict,owner,last_checked,notes`

证据状态限定为 `UNVERIFIED`、`PROBABLE` 或 `CONFIRMED`；写作决定限定为 `ALLOW`、`DOWNGRADE`、`HOLD` 或 `REJECT`。未核验主张不得在摘要、结论或标题中当作已确认结果。`required_evidence` 记录该主张必须获得什么，`prohibited_substitute` 记录什么看似相关但不能代替所需证据。

初始模板预置以下候选主张，全部以 `UNVERIFIED,HOLD` 开始；预置不代表核验通过：

| 候选主张 | 必须找到的证据 | 不能用什么替代 |
|---|---|---|
| Shared 在指定比较中实现更小的完整归档 | 匹配恢复对象、配置和成本范围的实际归档大小 | 负对数似然或 count stream 大小 |
| 参数共享改善了压缩与模型成本的权衡 | 与论文主张相匹配的共享方式对照及成本分解 | 仅比较 Shared 与一个外部方法 |
| 空间上下文提供了额外净收益 | 同版本的受控上下文消融，并计入必要图、模型和其他上下文开销 | 仅展示空间相关性 |
| 约定对象能够精确恢复 | 对应运行版本的独立解码与逐项一致性验证 | 仅凭编码程序没有报错 |

### 3.2 手稿

`manuscript/main.tex` 是唯一入口，使用 `\input{}` 按顺序组合：

1. `sections/00_abstract.tex`
2. `sections/01_introduction.tex`
3. `sections/02_methods.tex`
4. `sections/03_results.tex`
5. `sections/04_discussion.tex`
6. `sections/05_conclusion.tex`
7. `sections/06_data_code_availability.tex`
8. `sections/07_acknowledgements.tex`

`references.bib` 提供注释化的 BibTeX 条目示例，不将示例伪装为真实引用。正文每个核心段落用 LaTeX 注释标记其功能、主张、证据和边界，便于按写作契约起草。

### 3.3 证据

`evidence/README.md` 规定证据保存方式。`evidence/manifest.csv` 记录证据 ID、类型、文件路径、生成命令、配置、源码版本、数据版本、哈希、创建日期和状态。下设 `results/`、`configs/`、`logs/` 和 `source_versions/` 子目录，分离产物与来源。

### 3.4 图表

`figures/README.md` 规定一张正式图必须能追溯到绘图脚本、输入证据、配置和生成命令。下设 `scripts/` 和 `generated/`；脚本与正式图分开。

### 3.5 检查

`checks/` 包含一个统一入口和三项标准库检查：

- `run_all.py`：顺序执行全部检查，任一失败即返回非零状态。
- `check_claims.py`：校验 `claims.csv` 表头、唯一 ID、枚举状态、必填字段和证据路径。
- `check_citations.py`：比对 `.tex` 中使用的引用键与 `references.bib`，报告缺失键和未使用条目。
- `check_structure.py`：检查必需文件、`main.tex` 分节引入和证据清单的存在性。

`checks/README.md` 记录直接执行方式：`python3 checks/run_all.py`。LaTeX 编译使用 Codex 内置编译器验证，不强制本机安装 TeX。

## 4. 工作流

### 4.1 第一轮：只做论文审计

1. 检索所有手稿候选，对比项目状态、版本登记、决策记录、文件内版本标记和时间戳。若它们不一致，将冲突显式列出，不自动以“最新文件”取代作者确认。
2. 确定当前主稿后，登记路径、版本 ID、日期和 SHA-256；其他稿件标为历史或候选。
3. 从标题、摘要、Results、Discussion、图表题注和结论性陈述中抽取核心主张，但不编辑这些文本。
4. 为每项主张先填写所需证据和不可替代项，再寻找源码、配置、原始/处理结果、日志、恢复记录或文献。
5. 对主稿版本、源码版本、配置版本、实验 ID、数据清单、归档散列和验收记录做同版本连接。任一链节无法绑定时，状态不得为 `CONFIRMED`。
6. 为每项主张给出 `ALLOW`、`DOWNGRADE`、`HOLD` 或 `REJECT`，并记录允许表述、边界、缺失和冲突。
7. 交付主张—证据表和审计摘要。本轮不得修改 `manuscript/`。

### 4.2 审计后写作

1. 先在 `research_brief.md` 锁定问题、贡献、非主张和审计得出的表述上限。
2. 把结果、配置、日志和源码版本放入 `evidence/`，并在 `manifest.csv` 分配证据 ID。
3. 仅使用 `ALLOW` 的主张起草相应强度的文字；`DOWNGRADE` 必须使用台账中的限定表述，`HOLD/REJECT` 不得进入总结性位置。
4. 主张或证据发生实质变化时，同步更新 Results、Discussion、Abstract、Conclusion、图表和补充材料。
5. 每轮写作后运行所有检查；发布候选版还需编译并人工检查 PDF。

## 5. 错误与边界处理

- 结构错误、无效 CSV、重复 ID、未知状态、丢失引用键和缺失证据路径均为硬失败。
- `CONFIRMED` 主张若缺少主稿版本、证据版本、实验版本或检查日期，为硬失败。
- 新版源码、当前安装环境或事后重构脚本不得无提示地替代生成旧实验的实际版本。
- 未使用的 BibTeX 条目作为警告，不阻断起草。
- 占位文字可在起草期存在，但不得被标记为已核验或发布就绪。
- 检查脚本只证明结构与链接一致，不替代对科学有效性、统计合理性和引用语义的人工审查。

## 6. 验收标准

- 目录与上述组件完整创建，且未覆盖仓库既有文件。
- `python3 Shared-paper/checks/run_all.py` 在初始模板上成功运行。
- `main.tex` 通过 Codex 内置 LaTeX 编译器编译。
- 至少一个正常样例和一个失败样例验证主张检查器确实能拦截错误。
- 从主张 ID 可追溯到证据清单和具体位置；从正文引用键可追溯到 BibTeX 条目。
- 初始 `claims.csv` 包含四项候选主张及其“必需证据/不可替代项”，且未核验前不得默认放行。
- 检查器能拦截缺失版本字段的 `CONFIRMED` 记录，并能在主稿路径或散列变化时提示重审。
- 第一轮审计交付物只更新主张—证据表、证据索引和审计摘要，不改动手稿源文件。

## 7. 非目标

- 本轮不迁移或改写现有手稿。
- 不生成论文实质性结果、摘要或参考文献。
- 不绑定特定期刊样式、学科术语或统计流程。
- 不自动判定一项科学主张为真。
