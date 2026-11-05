# M11 报告：Maintenance Optimization 与 FTIR Normalization

- 状态：**M11 完成**
- 基线版本：EPR Workflow **v0.2.0**
- Git 基线：`327d5f6`
- 前序测试基线：M10 **622 passed, 1 skipped**
- M11 结果：**631 passed, 1 skipped**
- 日期：2026-11-04
- 旧 EPR 应用：**未修改，仍独立可用**
- Git：**未 commit、未 push、未创建 tag**
- M12 已另行完成；M13–M17：**未实现**

---

## 1. Part A — 维护优化总览

Part A 分为五个阶段，全部完成后才进入 Part B：

1. A1 合并架构测试子进程；
2. A2 消除 FTIR 重复文件读取，限制 probe；
3. A3 canonical 化 FTIR scientific metadata；
4. A4 合并 GUI/CLI 共享逻辑；
5. A5 建立分层测试与开发流程。

Part B 未与 Part A 混在同一次行为修改中。

---

## 2. A1 — 架构测试合并

### 变更

- 新增 [tests/_arch_support.py](../tests/_arch_support.py)：
  - session 级缓存；
  - 五个独立子进程域；
  - 统一 AST/text 扫描 helper；
  - 子进程失败诊断。
- 新增 [tests/test_architecture.py](../tests/test_architecture.py)：20 个测试。
- 删除 11 个 M0–M10 架构测试文件，由新套件覆盖：
  - `test_m0_architecture.py`
  - `test_m1_architecture.py`
  - `test_m2_architecture.py`
  - `test_m3_architecture.py`
  - `test_m4_architecture.py`
  - `test_m5_architecture.py`
  - `test_m6_architecture.py`
  - `test_m7_architecture.py`
  - `test_m8_architecture.py`
  - `test_m9_architecture.py`
  - `test_m10_architecture.py`

### 五个独立子进程域

| Domain | 覆盖 |
| --- | --- |
| `core` | 全部 core 模块导入、无 Qt/legacy/app/techniques/Matplotlib、core registry 为空 |
| `epr` | EPR backend importers/processing、无 Qt/legacy/FTIR |
| `ftir` | FTIR backend importers、无 Qt/Matplotlib/EPR/app/legacy |
| `gui` | composition root、EPR/FTIR panel、registry IDs、无 legacy |
| `cli_legacy` | Qt-free GUI services、app CLI/batch/registry、旧 EPR CLI/GUI/API |

每个域只启动一次；多个测试共享结果。每个域仍在独立 Python 进程内。

### 性能

| 指标 | Before | After |
| --- | --- | --- |
| 架构测试数 | 54 | 20 |
| 架构运行时间 | 约 58.49 秒 | 约 5.36 秒 |
| 子进程启动点 | 27 | 5 |
| 完整测试 | 622 / 约 89 秒（基准） | 631 / release verbose 62.61 秒 |

完整测试时间有机器负载波动；架构目标是明确达到的。全量 release verbose
为 62.61 秒，接近 50–60 秒目标但未在所有运行中严格落在该区间；没有通过
弱化测试来降低时间。

### 覆盖映射

| 原架构文件 | 覆盖位置 |
| --- | --- |
| M0 | legacy Qt/GUI AST、legacy cycle、`cli_legacy` 域 |
| M1 | core AST、core 域、legacy API |
| M2 | core/techniques AST、core registry、importer IDs |
| M3 | core AST/text、core 域（无 Matplotlib） |
| M4 | core/processing AST/text、EPR backend 域 |
| M5 | core/plotting AST/text、core 域 Matplotlib 检查 |
| M6 | app CLI/batch AST、CLI/legacy 域 |
| M7 | 无 legacy import、EPR 域、旧 API |
| M8 | generic GUI/EPR panel AST、qfree/legacy 域、GUI 域 |
| M9 | FTIR AST/backend 域、无 legacy、importer IDs、app-layer |
| M10 | FTIR GUI AST、composition root、GUI 域、app-layer |

M9 的“FTIR 无 processing 模块”是 M9 范围限制；M11 Part B 正式加入
`techniques/ftir/normalization.py`。该模块仍 Qt-free，并继续被架构扫描覆盖。

---

## 3. A2 — 单次稳定字节快照与 bounded probe

### 文件

- [src/spectralab/core/importers/sources.py](../src/spectralab/core/importers/sources.py)
- [src/spectralab/techniques/ftir/importers/_generic.py](../src/spectralab/techniques/ftir/importers/_generic.py)

### 实现

- 新增 `source_file_from_bytes(path, raw, role=..., format_id=...)`；
- `source_file()` 委托给该 helper；
- FTIR parser 的同一 `raw` 用于：
  - 解析；
  - 文件大小；
  - SHA-256；
  - `SourceFile` provenance。
- `_read_stable_bytes()` 只打开一次文件，比较读取前后的 `st_size` 和
  `st_mtime_ns`；若发生变化，抛出 `source_changed_during_import`。
- probe 改用 `PROBE_READ_LIMIT = 64 * 1024`，只读取前 64 KiB；
- 若 prefix 被截断但不足两行，probe 仅将文件视为候选，不宣称完整有效。

### 测量

- 成功导入完整文件读取次数：**1**；
- probe 最大读取：**65536 bytes**；
- SHA-256 算法和定义未改变；
- 4350 点真实样本仍通过。

### 测试

- `test_source_file_from_bytes_matches_source_file`
- `test_successful_import_reads_one_stable_snapshot`
- `test_probe_read_is_bounded`
- `test_file_mutation_during_read_is_detected`
- 原有空文件、单行、CSV/TXT 和 4350 点测试继续通过。

---

## 4. A3 — Canonical FTIR metadata

### 最终结构

| 字段 | Canonical 位置 |
| --- | --- |
| X quantity/unit | `Axis1D.quantity` / `Axis1D.unit` |
| Y semantics/unit | `Signal1D.semantics` / `Signal1D.unit` |
| Acquisition mode / ATR status | `SpectrumMetadata.acquisition` |
| Format / column mapping / header fields | `SpectrumMetadata.technique_metadata` |
| Requested options / resolved mapping | `Provenance.format_metadata` |

### 删除的重复项

- `technique_metadata["ftir_metadata"]`
- `technique_metadata["resolved_import_options"]`
- `technique_metadata["acquisition_mode"]`
- `technique_metadata["atr_correction_status"]`
- `technique_metadata["signal_semantics"]`
- `technique_metadata["axis_quantity"]`
- `technique_metadata["axis_unit"]`
- `column_mapping` 中重复的 `x_name` / `y_name`
- `format_metadata` 中重复的 `x_column` / `y_column` / `header_fields`

现有 `technique_metadata` 只保留：

```text
format_id
column_mapping: {x, y}
header_fields
```

### 保留的区别

- `format_metadata["import_options"]`：requested options；
- `format_metadata["resolved_mapping"]`：实际解析的列索引；
两者不是重复字段，保留。

### 兼容性影响

- M9/M10 内部测试和 GUI 对旧 key 的读取已更新；
- `FTIRMetadata` 类仍保留为兼容工具，但不再序列化到 `SpectrumMetadata`；
- batch summary 的 `resolved_import_options` 改名为 `import_options`，内容仍是
  requested options；
- M3 CSV/JSON export schema 未改变；axis/signal 仍从核心模型导出；
- 真实样本的 scientific values 不变。

### 验证

- technique metadata 只剩三个 key；
- metadata view 不再重复显示 `ftir_metadata` / `resolved_import_options`；
- provenance requested/resolved 仍存在；
- batch JSON 的 axis/signal 仍正确；
- 真实样本 4350 点和 metadata 值不变。

---

## 5. A4 — GUI/CLI 共享逻辑

### Column parsing

- 新增 `parse_column_reference()` 到 FTIR mapping；
- CLI 与 GUI 共用；
- 保留索引/名称/空值行为；
- 参数化测试覆盖空值、数字、符号、名称和空白。

### File suffixes

- 新增 [techniques/ftir/formats.py](../src/spectralab/techniques/ftir/formats.py)：
  - `FTIR_CSV_SUFFIXES`
  - `FTIR_TXT_SUFFIXES`
  - `FTIR_ENTRY_SUFFIXES`
- `GenericCSVImporter` / `GenericTXTImporter` 从常量取后缀；
- GUI `FTIR_FILE_PATTERNS` 从同一常量生成；
- 测试验证 lower/upper patterns 与 importer suffixes 一致。

### Translation registration

- 删除 FTIR panel/widget/dialog 内部的 catalog 注册；
- 只在 MainWindow/composition root 通过 descriptor 注册一次；
- `register_ftir_translations()` 保留给独立组件测试 fixture；
- 运行时语言切换仍更新所有 FTIR 文本。

### File filter

- 新增 [src/spectralab/app/gui/file_filter.py](../src/spectralab/app/gui/file_filter.py)：
  `build_file_filter()`；
- MainWindow 与 `FtirImportDialog` 共用。

### 小清理

- `FtirPanel.open_file()` 直接调用 `import_file()`，避免重复构造 options；
- 合并重复的真实样本 GUI 测试；
- 保留现有 option aliases（`x_col`、`x_index`、`include_header`、`skip_lines`）
  以维持兼容性；未无证据删除。

---

## 6. A5 — Layered workflow

新增：

- [scripts/check.ps1](../scripts/check.ps1)
- [docs/development_workflow.md](development_workflow.md)

支持：

```powershell
.\scripts\check.ps1 -Mode fast
.\scripts\check.ps1 -Mode gui
.\scripts\check.ps1 -Mode arch
.\scripts\check.ps1 -Mode regression
.\scripts\check.ps1 -Mode full
.\scripts\check.ps1 -Mode release -Milestone m11
```

`release` 运行：

1. 完整 verbose；
2. `-W error::UserWarning`；
3. 原 EPR 14 文件回归。

日志沿用：

```text
results/logs/pytest_m11_20261104_verbose.txt
results/logs/pytest_m11_20261104_userwarning.txt
results/logs/pytest_m11_20261104_original.txt
```

`fast` 最终实测 443 passed / 1 skipped / 约 36 秒，明显快于 full；
`release` 不省略任何层。

---

## 7. Part B — FTIR Normalization

### 实现位置

[src/spectralab/techniques/ftir/normalization.py](../src/spectralab/techniques/ftir/normalization.py)

### 方法

| Method | 公式 |
| --- | --- |
| `min_max` | `(y - min(y)) / (max(y) - min(y))` |
| `max_abs` | `y / max(abs(y))` |
| `l2` | `y / sqrt(sum(y^2))` |

全部使用 float64。

### 错误

- `ftir_normalization_method`
- `ftir_normalization_input`
- `ftir_normalization_nonfinite_input`
- `ftir_normalization_zero_denominator`
- `ftir_normalization_nonfinite_denominator`
- `ftir_normalization_nonfinite_output`

零分母、非有限输入/输出、空数组、复数输入均明确失败。

### 保持不变量

- X 轴对象和值不变；
- 点序不变；
- signal semantics 和 unit 不变；
- 原始源 `Spectrum1D` 不变；
- 不使用自动方法选择；
- 不执行 baseline、ATR、Smoothing 或 peak detection。

### Generic session preview

`ProcessingSession` 新增：

```python
preview(operation) -> OperationOutput
```

- 执行并验证 operation；
- 不修改 `_applied`、`_redo`、history 或 raw spectrum；
- `apply()` 和 `preview()` 共享内部 `_execute()`，没有复制验证/错误逻辑。

### GUI

FTIR panel 新增：

- 方法选择；
- Preview；
- Apply（必须先有预览）；
- Cancel preview；
- Undo / Redo / Reset to raw；
- processing history 状态；
- preview/processed 曲线标签；
- 运行时语言切换。

Preview/apply/undo/redo/reset 行为：

- Preview 只绘制 raw + preview，不写 history；
- Apply 显式提交，写入 `ProcessingOperation`，metadata view 显示处理历史；
- Cancel 清除 preview，恢复已提交显示；
- 切换方法自动取消 preview；
- Undo/Redo 使用 session 存储状态，不重放算法；
- Reset 清除全部历史和 redo。

---

## 8. Part B 测试与科学验证

新增 [tests/test_ftir_normalization.py](../tests/test_ftir_normalization.py)：25 个测试。

覆盖：

- 三种公式的独立预期值（用 `math.sqrt` / 字面值计算，不调用实现）；
- 正负值、constant、all-zero、near-zero；
- 非有限输入/分母、空数组、复数；
- float64 dtype；
- 原始数组不变；
- X 轴、方向和点序；
- operation order、parameters、technique/version；
- preview 不修改 history/redo/raw；
- apply/undo/redo/reset；
- GUI preview/apply/cancel/undo/redo/reset（在 `test_ftir_gui.py`）；
- 方法切换取消 preview；
- 中文/英文 preview labels；
- 真实 4350 点样本归一化。

真实样本验证：

- Min-Max preview 的期望值；
- Max-abs 归一化后 `max(abs(y)) == 1`；
- 4350 点、X 顺序和原始 source 不变；
- history 记录 `ftir.normalize.max_abs`；
- 源 SHA-256 不变。

---

## 9. 最终测试结果

```text
M11 release 完整 verbose：
631 passed, 1 skipped in 62.61s
exit code 0

M11 release warnings-as-errors：
631 passed, 1 skipped in 78.14s
exit code 0

M11 release 原 EPR 14 文件回归：
298 passed, 1 skipped in 96.88s
exit code 0
```

日志：

- `results/logs/pytest_m11_20261104_verbose.txt`
- `results/logs/pytest_m11_20261104_userwarning.txt`
- `results/logs/pytest_m11_20261104_original.txt`

Part A gate 日志（Part B 前）：

- `results/logs/pytest_m11_part_a_20261104_verbose.txt`
- `results/logs/pytest_m11_part_a_20261104_userwarning.txt`
- `results/logs/pytest_m11_part_a_20261104_original.txt`

测试数变化：

- M10：622 passed / 1 skipped
- 删除 54 个重复架构测试，新增 20 个合并架构测试
- 新增 A2/A4/Part B 测试
- M11：631 passed / 1 skipped
- 原 EPR：298 passed / 1 skipped

完整测试时间受机器负载影响；架构测试从约 58.5 秒降至约 5.4 秒。全量 release
verbose 为 62.61 秒，接近但未严格达到所有运行中的 50–60 秒目标；没有删减
覆盖或弱化断言来达到时间。

---

## 10. 新增与修改文件

### 新增

- `tests/_arch_support.py`
- `tests/test_architecture.py`
- `tests/test_ftir_normalization.py`
- `src/spectralab/techniques/ftir/formats.py`
- `src/spectralab/techniques/ftir/normalization.py`
- `src/spectralab/app/gui/file_filter.py`
- `scripts/check.ps1`
- `docs/development_workflow.md`
- 本报告

### 修改

- `src/spectralab/core/importers/sources.py`
- `src/spectralab/core/importers/__init__.py`
- `src/spectralab/core/processing/session.py`
- `src/spectralab/techniques/ftir/importers/_generic.py`
- `src/spectralab/techniques/ftir/importers/mapping.py`
- `src/spectralab/techniques/ftir/importers/generic_csv.py`
- `src/spectralab/techniques/ftir/importers/generic_txt.py`
- `src/spectralab/techniques/ftir/importers/__init__.py`
- `src/spectralab/techniques/ftir/__init__.py`
- `src/spectralab/app/cli.py`
- `src/spectralab/app/gui/main_window.py`
- `src/spectralab/app/gui/ftir_panel.py`
- `src/spectralab/app/gui/ftir_import_dialog.py`
- `src/spectralab/app/gui/ftir_options_widget.py`
- `src/spectralab/app/gui/ftir_translations.py`
- `src/spectralab/app/batch.py`
- FTIR/batch/GUI 测试
- `docs/architecture_proposal.md`
- `docs/m9_ftir_importer_report.md`
- `docs/m10_ftir_gui_report.md`

### 删除

- 11 个 M0–M10 架构测试文件（覆盖已合并到 `tests/test_architecture.py`）。

### 未修改

- `src/epr_workflow/`
- 旧 EPR GUI/CLI/batch/preprocessing/export
- M3 schema
- 原始数据
- `requirements.txt`

---

## 11. 架构与科学完整性

- core 仍不导入 Qt/app/techniques/legacy/Matplotlib；
- EPR/FTIR backend 仍 Qt-free；
- FTIR normalization 是 technique-specific 且 Qt-free；
- generic MainWindow/Controller 无 FTIR 归一化专用分支；
- 无 `epr_workflow` 运行时 import；
- 无循环导入；
- 架构测试仍保留五个独立子进程；
- 原始数组只读且未被修改；
- 预处理/归一化全部显式触发；
- requested options 与 resolved mapping 保持分离；
- 真实样本 SHA-256 不变；
- 无新增依赖。

---

## 12. Git 状态

HEAD：

```text
327d5f633c701cb07c3279754d35427dfc6b8bb0
```

- 未 commit；
- 未 push；
- 未创建 tag；
- 未重写历史；
- 未修改 raw data；
- 未修改 `requirements.txt`；
- `S-BSAPEG-10.0.dpt` 仍为未跟踪用户文件，内容未修改；
- M0–M11 SpectraLab 文件仍未跟踪。

---

## 13. 剩余技术债

1. 全量测试时间仍受机器负载影响，未稳定落在 50–60 秒；架构测试目标已达成。
2. 归一化不写 JSON/CSV 处理导出；只存在于 GUI 内存和 `ProcessedSpectrum`。
3. 归一化 timestamp 未记录，因为现有 `ProcessingOperation` 没有 timestamp 字段。
4. 归一化保留 signal unit/semantics；数学结果虽为无量纲缩放，但未擅自改写单位。
5. 没有归一化参数持久化或批处理归一化。
6. M11 没有 M12 基线；M12 已另行完成，仍没有 M13 峰检测、M14 差谱或 M15 导出加固。
7. 真实样本测试仍依赖本机未跟踪文件。
8. option aliases 保留以维持兼容性，未做全面删除。
9. 旧 M0–M10 架构测试文件已删除；覆盖映射依赖本报告和
   `tests/test_architecture.py` 维护。
10. 预览只支持单个 operation；多步预览链尚未设计。

---

## 14. 完成清单

- [x] 架构测试 54 → 20
- [x] 架构时间约 58.5 → 5.4 秒
- [x] 子进程域 27 → 5
- [x] 覆盖映射与五域隔离
- [x] 单次稳定字节快照
- [x] probe 最大 64 KiB
- [x] 文件变化检测
- [x] canonical FTIR metadata
- [x] requested/resolved 保留
- [x] GUI/CLI helper 合并
- [x] translation 单点注册
- [x] 分层测试脚本
- [x] Min-Max
- [x] Max-abs
- [x] L2
- [x] 零/非有限/空/复数错误
- [x] float64
- [x] raw/X/点序不变
- [x] preview 不写 history
- [x] apply/cancel/undo/redo/reset
- [x] 方法切换取消 preview
- [x] 中英文预览
- [x] 真实 4350 点归一化
- [x] 原 EPR 298 passed / 1 skipped
- [x] 完整 631 passed / 1 skipped
- [x] warnings-as-errors 通过
- [x] M11 范围停在 M12 之前（M12 已另行完成）
- [x] 未 commit、未 push

**M11 完成。** Part A 的维护优化已通过功能验收，Part B 的三种归一化已按显式
预览/应用流程实现。M12 已完成，见
[M12 FTIR Baseline 报告](m12_ftir_baseline_report.md)；M13 尚未开始。
