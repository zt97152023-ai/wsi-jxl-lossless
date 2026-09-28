# Shared-paper 写作工作区设计

## 1. 目标

在仓库根目录创建 `Shared-paper/`，作为一个可直接启动、可追溯证据、可自动检查的 LaTeX 论文写作工作区。它应将研究边界、核心主张、证据位置、正文、图表与质量检查放在同一条可审计链上。

## 2. 设计边界

- 保留用户指定的七个顶层组件：`AGENTS.md`、`research_brief.md`、`claims.csv`、`manuscript/`、`evidence/`、`figures/` 和 `checks/`。
- 不引入额外的项目管理层、包管理器或第三方 Python 依赖。
- 不填造研究结果、数字、文献或方法。未知内容以明确的占位符和状态字段表示。
- 默认采用通用 IMRaD 结构，日后可根据期刊模板替换 `main.tex` 的文档类，而不改变证据和主张工作流。
- 不改动仓库中现有论文、证据、修订记录或构建产物。

## 3. 组件设计

### 3.1 项目控制文件

`AGENTS.md` 是 Codex 和其他协作者的长期规则，定义权威来源、不得造数据、主张变更要求、引用规则、编译与检查门槛。

`research_brief.md` 是论文语义契约，包含研究问题、读者与目标期刊、预期贡献、明确非主张、数据/方法边界、当前结构、权威来源、术语约定和开放问题。

`claims.csv` 是机器可读的主张台账。字段固定为：

`claim_id,section,claim_text,claim_type,evidence_id,evidence_location,verification_status,scope_limit,owner,last_checked,notes`

其中状态限定为 `UNVERIFIED`、`PROBABLE` 或 `CONFIRMED`；未核验主张不得在摘要、结论或标题中当作已确认结果。

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

1. 先在 `research_brief.md` 锁定问题、贡献与非主张。
2. 把每个核心结论登记到 `claims.csv`，初始为 `UNVERIFIED`。
3. 把结果、配置、日志和源码版本放入 `evidence/`，并在 `manifest.csv` 分配证据 ID。
4. 将证据 ID 和位置写回 `claims.csv`，核验后再提升状态。
5. 仅使用已登记的证据起草结果和总结性文字，然后更新其他受影响的章节。
6. 每轮写作后运行所有检查；发布候选版还需编译并人工检查 PDF。

## 5. 错误与边界处理

- 结构错误、无效 CSV、重复 ID、未知状态、丢失引用键和缺失证据路径均为硬失败。
- 未使用的 BibTeX 条目作为警告，不阻断起草。
- 占位文字可在起草期存在，但不得被标记为已核验或发布就绪。
- 检查脚本只证明结构与链接一致，不替代对科学有效性、统计合理性和引用语义的人工审查。

## 6. 验收标准

- 目录与上述组件完整创建，且未覆盖仓库既有文件。
- `python3 Shared-paper/checks/run_all.py` 在初始模板上成功运行。
- `main.tex` 通过 Codex 内置 LaTeX 编译器编译。
- 至少一个正常样例和一个失败样例验证主张检查器确实能拦截错误。
- 从主张 ID 可追溯到证据清单和具体位置；从正文引用键可追溯到 BibTeX 条目。

## 7. 非目标

- 本轮不迁移或改写现有手稿。
- 不生成论文实质性结果、摘要或参考文献。
- 不绑定特定期刊样式、学科术语或统计流程。
- 不自动判定一项科学主张为真。
