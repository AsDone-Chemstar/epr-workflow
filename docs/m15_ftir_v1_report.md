# M15 报告：FTIR v1.0 导出、来源、双语与端到端加固

- 状态：**M15 完成**
- 基线：M14
- Git HEAD：`fae60edc970c67014f921dfddd58dce0ff62d603`
- 前序测试基线：M14 **724 passed, 1 skipped**
- M15 结果：**750 passed, 1 skipped**
- 日期：2026-11-05
- Git：**未 commit、未 push、未创建 tag**
- M16：**未开始**
- 验收：**PASS**

---

## 1. 实现摘要

M15 完成 FTIR v1.0 工作流：

```text
Import
→ Display
→ Normalization
→ Baseline Correction
→ Peak Detection
→ Difference Spectrum
→ Export
```

新增：

1. 单谱 CSV：raw 或 processed X/Y 数据 + JSON metadata sidecar。
2. 单谱 JSON：数据、元数据、来源、处理历史、峰参数。
3. 单谱 PNG：publication-quality 谱图。
4. 差谱专用 CSV：`x, a, b, difference`。
5. 差谱专用 JSON：两个源数据集、SHA-256、处理历史、插值设置、provenance。
6. 差谱专用 PNG：A、B、插值 B、A−B。
7. FTIR GUI 的 Export 标签页。
8. 差谱标签页中的 CSV/JSON/PNG 导出控件。
9. 中英文导出控件、状态和错误消息。
10. 默认拒绝覆盖已有文件，可显式勾选允许覆盖。
11. 批量导入的每文件 mapping/parsing 记录。
12. 端到端测试：导入 → 处理 → 峰 → 差谱 → 导出。

未实现：

- M16 多光谱比较；
- 全 EPR GUI 迁移；
- 完整批处理 GUI；
- 差谱原始 B 的独立 CSV 列；
- 峰结果表单独导出；
- 自动处理、自动插值、自动对齐、自动单位推断。

---

## 2. 修改与新增文件

### 新增

- [src/spectralab/app/ftir_export.py](../src/spectralab/app/ftir_export.py)
- [tests/test_ftir_export.py](../tests/test_ftir_export.py)
- [tests/test_ftir_export_gui.py](../tests/test_ftir_export_gui.py)
- [tests/test_m15_end_to_end.py](../tests/test_m15_end_to_end.py)
- 本报告

### 修改

- [src/spectralab/app/gui/ftir_panel.py](../src/spectralab/app/gui/ftir_panel.py)
- [src/spectralab/app/gui/ftir_translations.py](../src/spectralab/app/gui/ftir_translations.py)
- [src/spectralab/app/batch.py](../src/spectralab/app/batch.py)
- [src/spectralab/core/export/paths.py](../src/spectralab/core/export/paths.py)
- [src/spectralab/core/export/__init__.py](../src/spectralab/core/export/__init__.py)
- [src/spectralab/core/export/provenance.py](../src/spectralab/core/export/provenance.py)
- [src/spectralab/techniques/ftir/difference.py](../src/spectralab/techniques/ftir/difference.py)
- [tests/test_ftir_difference.py](../tests/test_ftir_difference.py)
- [tests/test_ftir_difference_gui.py](../tests/test_ftir_difference_gui.py)
- [docs/architecture_proposal.md](architecture_proposal.md)
- [docs/spectralab_project_status.md](spectralab_project_status.md)

### 未修改

- `src/epr_workflow/`
- `requirements.txt`
- `data/raw/`
- `Test data/`
- `results/`（除测试日志，且被忽略）
- `config/`
- `.venv/`
- `S-BSAPEG-10.0.dpt`

无新增第三方依赖。无删除文件。

---

## 3. 导出架构

### 3.1 层位置

```text
app → techniques → core
```

- CSV/JSON 数据构建属于可复用导出逻辑；
- PNG 渲染需要 Matplotlib；
- 架构测试禁止 `techniques/` 导入 Matplotlib；
- 因此统一的 FTIR 导出入口放在 app 层：

```text
src/spectralab/app/ftir_export.py
```

该模块不导入 Qt，CSV/JSON 可独立于 GUI 使用；PNG 使用 Matplotlib `Figure`，不依赖 PySide6。

### 3.2 单谱导出

输入：

```python
Spectrum1D            # raw
ProcessedSpectrum     # current processed
```

输出：

| 格式 | 内容 |
| --- | --- |
| CSV | `x,y` + sibling `_metadata.json` |
| JSON | 数据、元数据、来源、处理历史、峰参数 |
| PNG | 选定 raw 或 processed 谱图 |

- CSV 使用原始点序和 shortest round-trip float64 文本。
- JSON 使用严格 JSON，不允许 NaN/Infinity。
- PNG 只绘制所选数据，不混入另一状态。
- processed 选择使用 `ProcessingSession.current`，不会导出未应用的 preview。

### 3.3 差谱导出

输入：

```python
DifferenceResult
source_a: Spectrum1D
source_b: Spectrum1D
processed_a / processed_b: ProcessedSpectrum | None
```

输出：

| 格式 | 内容 |
| --- | --- |
| CSV | `x, a, b, difference` + metadata sidecar |
| JSON | 差谱数据、两个源、来源哈希、处理历史、插值设置 |
| PNG | A、B、插值 B、A−B |

重要定义：

- 精确匹配时，`b` 是 B 在共同 X 轴上的值；
- 插值时，`b` 是 **B 线性插值到 A 目标轴后的值**；
- CSV sidecar 明确记录 `b_column` 的含义和 B 原始点数；
- 差谱 JSON 同时记录插值方法、目标数据集、重叠区间、端点策略和 `extrapolation: none`。

### 3.4 结果模型扩展

为了导出 `x, a, b, difference`，M14 的 `DifferenceResult` 增加：

- `aligned_a_signal`
- `aligned_b_signal`

它们与结果轴等长，是只读 `Signal1D` 副本。M14 的算术定义、来源选择和缓存历史不变；所有 M14 测试继续通过。

### 3.5 路径安全

复用核心：

- `check_output_path`
- `atomic_write_text`
- 新增 `atomic_write_bytes`

规则：

- 默认 `overwrite=False`；
- 已存在文件拒绝覆盖；
- 输出路径与任一源文件相同或指向同一文件时拒绝；
- 先检查所有目标，再序列化，再写入；
- 二进制 PNG 通过 sibling temp file + `os.replace` 原子替换。

---

## 4. Provenance 设计

单谱 JSON / CSV sidecar 记录：

- `dataset_id`、技术、源格式、点数；
- `source_selection`（raw/processed）；
- 源文件路径、大小、SHA-256、canonical SHA-256；
- importer id/version、导入时间（若有）；
- `format_metadata.import_options`、`resolved_mapping`；
- X 轴 quantity/unit/name/direction/point_count；
- Y 信号 semantics/unit/name/point_count；
- instrument vendor/model；
- acquisition mode、ATR correction status；
- 完整 processing history：
  - operation id、name、version；
  - parameters；
  - diagnostics；
  - warnings/assumptions；
  - input/output state id；
  - input dataset id；
- peak detection 参数（若提供且 dataset/source 匹配）；
- 导出 schema id/version/status；
- 实际 UTC 导出时间；
- Python/NumPy/SciPy/Matplotlib/SpectraLab 版本。

差谱 JSON 额外记录：

- A/B 各自 dataset id、source selection；
- A/B 各自 provenance、源文件 SHA-256、导入参数；
- A/B 各自 processing history（processed 时）；
- A/B 各自 peak detection（若提供且匹配）；
- 差谱算术定义 `A - B`；
- axis match、插值方法、目标数据集、重叠区间、端点策略；
- `result_role`：`preview` 或 `applied`。

未知字段保持 `null`/空集合，不推断、不补默认值。

---

## 5. GUI 与双语

FTIR 底部现在有四个标签页：

```text
Import options
Peak picking
Difference
Export
```

### Export 标签页

- 数据来源：Raw / Current processed；
- 格式：CSV / JSON / PNG；
- 是否允许覆盖；
- 导出按钮；
- 状态标签。

### Difference 标签页

新增：

- 导出格式：CSV / JSON / PNG；
- 是否允许覆盖；
- 导出按钮；
- 导出状态标签。

行为：

- 没有差谱结果时按钮禁用；
- 导出 preview 或 applied 结果均可，`result_role` 记录实际状态；
- 导出不修改源谱、ProcessingSession、峰结果或差谱结果；
- 导出失败时显示 coded error；
- 覆盖失败不会留下部分 CSV/metadata（先 preflight，再写）。

中英文覆盖：

- Export 标签页标题；
- 来源、格式、覆盖、按钮；
- 差谱导出控件；
- 成功/失败/取消消息；
- 文件对话框标题。

PNG 字体：若系统有 Microsoft YaHei / SimHei / DengXian / SimSun / Noto Sans CJK，则优先使用，避免中文标签缺字。

---

## 6. 批量导入映射

现有批量/CLI 已支持：

- `x_column` / `y_column`
- `header`
- `delimiter`
- `decimal`
- `encoding`
- `skip_rows`
- `comment`
- FTIR 语义/采集模式/ATR 状态/仪器信息

M15 在 batch summary 的每个成功文件记录中增加：

```json
{
  "resolved_mapping": {"x": 0, "y": 1, "requested_x": 0, "requested_y": 1},
  "parsing": {
    "delimiter": ",",
    "decimal_separator": ".",
    "encoding": "utf-8-sig",
    "header": false,
    "comment_markers": [],
    "skip_rows": 0,
    "defaulted_two_column_mapping": true
  },
  "import_options": {...}
}
```

这样每个导入文件都有独立的 mapping/parsing 记录，而不是只记录整批选项。

没有新增批处理 GUI。

---

## 7. 科学完整性审计

已验证：

1. 原始实验数据只读；导出前后 SHA-256 不变。
2. 导出不运行任何处理；processed 必须是已经存在的 `ProcessingSession.current`。
3. 未应用的 processing preview 不会被导出。
4. 不自动对齐、不自动插值、不外推。
5. 不排序、不反转源数组。
6. 不推断单位、语义、采集模式或仪器。
7. 未知信息保持 `null`/空集合。
8. 处理历史与峰/差谱 provenance 保持分离。
9. 差谱结果不写入 ProcessingSession。
10. 导出不修改 ProcessingSession、峰结果、差谱结果。
11. 默认拒绝覆盖；拒绝覆盖源文件。
12. 真实 DPT 样本未修改。

真实样本：

```text
S-BSAPEG-10.0.dpt
4350 点
wavenumber / cm^-1 / decreasing
absorbance
SHA-256:
501fe570b175d8f2a089c21c17f469b1a087d654040f72986c5ba9fe9bffe761
```

---

## 8. 测试结果

新增 **26 个 M15 测试**：

- [tests/test_ftir_export.py](../tests/test_ftir_export.py)：15
- [tests/test_ftir_export_gui.py](../tests/test_ftir_export_gui.py)：10
- [tests/test_m15_end_to_end.py](../tests/test_m15_end_to_end.py)：1

覆盖：

### 单谱

- raw / processed CSV；
- raw / processed JSON；
- raw / processed PNG；
- CSV sidecar；
- 处理历史；
- metadata / instrument / ATR；
- 源 SHA-256；
- peak 参数；
- 时间戳和软件版本。

### 差谱

- 精确匹配 CSV/JSON/PNG；
- 插值 CSV/JSON/PNG；
- `x,a,b,difference` 列；
- 插值 B 含义；
- 两源 dataset id / SHA / provenance；
- A/B processed history；
- preview/applied role；
- 源不匹配拒绝；
- processed 源缺失拒绝；
- processed B；
- 中文 PNG 标签。

### GUI

- Export 标签页；
- 四标签页结构；
- raw/processed 选择；
- CSV/JSON/PNG 导出；
- 差谱导出；
- 覆盖保护；
- 成功/失败状态；
- 无结果时按钮禁用；
- 导出不修改 processing/peak/difference 状态；
- 中英文切换。

### 批量

- 每文件 mapping；
- 每文件 parsing 参数；
- 每文件 import options。

### 端到端

```text
导入 → 归一化 → 峰检测 → 差谱 → CSV/JSON/PNG 导出
```

最终 release gate：

```text
完整 verbose：
750 passed, 1 skipped in 64.16s

warnings-as-errors：
750 passed, 1 skipped in 67.36s

原始 EPR 回归：
298 passed, 1 skipped in 41.22s

架构：
20 passed in 12.12s
```

唯一 skip 是既有 Windows `.DTA` 大小写歧义测试。

日志：

- `results/logs/pytest_m15_final2_20261105_verbose.txt`
- `results/logs/pytest_m15_final2_20261105_userwarning.txt`
- `results/logs/pytest_m15_final2_20261105_original.txt`

M14 → M15：724 → **750 passed**。

---

## 9. 剩余限制

1. `spectralab` 尚未有独立发布版本号；导出 JSON 记录 `"spectralab": "unversioned"`。
2. 差谱 CSV 只包含对齐后的 B；原始 B 的完整数组不放进同一 CSV（长度可能不同）。JSON 记录原始点数和插值信息。
3. 差谱导出 API 需要 `DifferenceResult` 加两个源 `Spectrum1D`；单靠结果对象无法恢复源文件哈希。
4. 没有 M16 多光谱比较。
5. 没有完整 EPR GUI 迁移。
6. 没有批处理 GUI。
7. 峰结果表没有单独的导出文件；峰参数只进入匹配的 JSON provenance。
8. 单谱 PNG 只画选定的 raw 或 processed，不同时叠加两者。
9. 导出 PNG 的 CJK 字体取决于系统已安装字体；无 CJK 字体时中文标签可能缺字。
10. 导出 schema 状态仍为 `initial`，未来版本可能需要兼容迁移。
11. 没有自动处理、自动对齐、自动插值、自动单位转换。

---

## 10. Git 状态

```text
HEAD = fae60edc970c67014f921dfddd58dce0ff62d603
```

- M14 + M15 代码、测试、文档尚未提交；
- 未 push；
- 未创建 tag；
- 未 amend/rebase/reset/clean；
- 未修改 `requirements.txt`；
- 未修改 legacy `epr_workflow`；
- 未修改 `S-BSAPEG-10.0.dpt`；
- **M16 未开始**。

---

## 11. 验收决定

**PASS**

M15 要求的单谱 CSV/JSON/PNG、差谱 CSV/JSON/PNG、provenance、双语 GUI、覆盖保护、批量 mapping 和端到端测试均已实现并通过 release gate。未扩大范围到 M16 或 EPR GUI 迁移。
