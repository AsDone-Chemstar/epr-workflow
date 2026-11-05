# M0 基线报告：现有 EPR v0.2.0 行为特征化

- 状态：**M0 完成**
- 基线版本：EPR Workflow **v0.2.0**
- Git 提交：`327d5f6`
- 日期：2026-11-02
- 范围：只做数值、导出、GUI/工作流和架构边界基线；不实现 Spectrum1D、importer 注册表、FTIR 或 ATR-FTIR
- 生产代码：**未修改**
- 现有测试：**未修改**

本报告与 [架构提案](architecture_proposal.md) 配合使用。M0 的目标是先把
v0.2.0 的科学数值、输出结构和当前架构边界固定下来，为后续 M1 迁移提供回归门禁。

---

## 1. 执行摘要

M0 新增了：

- 一份机器可读数值基线：`tests/fixtures/m0_baseline.json`
- 数值与导出基线测试：`tests/test_m0_baseline.py`
- 架构边界测试：`tests/test_m0_architecture.py`
- GUI“加载但不自动处理”基线测试：`tests/test_m0_gui_baseline.py`
- 本报告

没有修改：

- `src/` 下的任何生产代码
- 任何现有测试
- CSV/JSON schema
- GUI 行为
- 原始数据
- 项目名称、包名、仓库、CLI、配置目录

测试结果：

| 运行 | 结果 |
| --- | --- |
| 原测试集（排除新增 M0 测试） | **298 passed, 1 skipped** |
| 完整测试集（含 M0） | **308 passed, 1 skipped** |
| `pytest -q -W error::UserWarning` | **308 passed, 1 skipped** |

新增 10 个通过测试；原有 298 passed / 1 skipped 保持不变。

---

## 2. M0.1 数值基线

### 2.1 机器可读记录

文件：`tests/fixtures/m0_baseline.json`

内容只保存摘要值，不保存原始光谱数组或原始文件内容：

- 源文件相对路径；
- 点数；
- 轴首值、末值、最小值、最大值、方向；
- 强度首值、末值、最小值、最大值、前 5 点、后 5 点；
- 源文件大小；
- 规范 SHA-256 和 `source_hashes`；
- 格式、警告、拒绝行/缺失/非有限/重复计数；
- BES3T 的轴定义、二进制类型/字节序和描述符版本。

### 2.2 ASC 真实数据基线

源文件：`data/raw/BSA3T275.ASC`

| 属性 | 值 |
| --- | --- |
| 点数 | 1024 |
| 轴 | 3280.0 → 3380.0 G |
| 轴方向 | strictly increasing |
| 强度首值 | 400.088 |
| 强度末值 | -181.85 |
| 强度最小/最大 | -5294.82 / 7642.7 |
| 文件大小 | 52276 bytes |
| SHA-256 | `e1ff52bae09fc05a9cc09234b8214fc0e5049f9483ad1466d5977dec81f18403` |
| 警告/拒绝行/缺失/非有限/重复 | 0 / 0 / 0 / 0 / 0 |

前 5 个强度值：

```text
400.088, 272.312, 364.536, -29.2404, 185.984
```

后 5 个强度值：

```text
250.255, -65.5214, 82.7025, -162.074, -181.85
```

ASC 的 `ImportResult.source_hashes` 当前为空；规范哈希使用
`ImportResult.sha256`。基线文件将其规范化为 `{"source": "<sha256>"}`。

### 2.3 BES3T 真实数据基线

源文件：`Test data/BSA3mal1h.DSC` + `Test data/BSA3mal1h.DTA`

| 属性 | 值 |
| --- | --- |
| 点数 | 1024 |
| 轴 | 3310.0 → 3410.0 G |
| 轴方向 | strictly increasing |
| 轴步长 | 100 / 1023 = 0.09775171065484756 G |
| 强度首值 | -76.0 |
| 强度末值 | -84.0 |
| 强度最小/最大 | -9903.0 / 10078.0 |
| 轴单位 | G |
| 数值类型/字节序 | `>f8` / BIG |
| 文件大小（DSC + DTA） | 2597 + 8192 = 10789 bytes |
| 组合 SHA-256 | `25200bf80d6b002be315f48e34644b59bed0c306442c499077cadb65eba71c1e` |

源文件哈希：

```text
DSC: 7c52452974547d0eddcaf9c01a4f341d34ec43602648db946f2afd8634ce13ce
DTA: 80a56acbdc779790f570a3c99315aedb032b3e761bf4941efeda214f6a987eda
```

轴定义记录：

```text
XTYP=IDX
linspace(XMIN=3310.0, XMIN+XWID=3410.0, XPTS=1024)
端点包含；不重新采样
```

前 5 个强度值：

```text
-76.0, -69.0, -67.0, -74.0, -69.0
```

后 5 个强度值：

```text
-77.0, -90.0, -74.0, -79.0, -84.0
```

### 2.4 回归测试

`tests/test_m0_baseline.py::test_real_dataset_matches_recorded_numerical_baseline`

- 参数化覆盖 ASC 与 BES3T；
- 逐项比较点数、轴端点/方向、强度首末值/最小最大/首末 5 点；
- 比较格式、文件大小、规范 SHA-256、`source_hashes`、警告与计数；
- BES3T 额外比较 `axis`、`binary` 和 `descriptor_version`；
- 在读取前后重新计算源文件 SHA-256，确认文件未被修改。

真实原始文件不随仓库分发；文件缺失时测试跳过，基线 JSON 仍然记录期望值。

### 2.5 如何重新生成基线

基线由当前 v0.2.0 的 `read_dataset()` 生成，提取字段与
`tests/fixtures/m0_baseline.json` 一致。重新生成时应：

1. 使用当前版本的 `read_asc()` / `read_bes3t()` / `read_dataset()`；
2. 只读取源文件，不写入原始目录；
3. 提取点数、轴首末/最小最大、方向、强度首末/最小最大/首末 5 点；
4. 记录 `sha256`、`source_hashes`、`file_size_bytes`；
5. 对 BES3T 额外提取 `axis`、`binary`、`descriptor_version`；
6. 与现有基线 JSON 比较；任何差异都必须解释，不能直接覆盖。

不建议用脚本自动覆盖基线；应通过 code review 确认差异是预期变化。

---

## 3. M0.2 导出基线

### 3.1 原始 CSV

ASC 原始 CSV（`<sample>_raw.csv`）列顺序：

```text
index, field_G, intensity
```

BES3T 原始 CSV 列顺序：

```text
index, field_G, intensity, source_format
```

`source_format` 恒为 `BES3T`。ASC 不增加该列。

类型与单位：

- `index`：有效整数时写为整数，否则保留原值，不强制取整；
- `field_G`：float，单位 G；
- `intensity`：float，原始强度，单位未文档化（original/arbitrary units）；
- `source_format`：文本，仅 BES3T。

### 3.2 处理结果 CSV

仅线性基线校正：

```text
index, field_G, intensity_raw, intensity_corrected, baseline_removed
```

含 Savitzky–Golay 平滑：

```text
index, field_G, intensity_raw, intensity_corrected, difference_from_raw
```

BES3T 处理结果在末尾追加：

```text
source_format
```

含义：

- `intensity_raw`：原始强度；
- `intensity_corrected`：处理后强度；
- `baseline_removed`：原始减处理后（基线校正）；
- `difference_from_raw`：原始减处理后（总变化，不是单独拟合基线）；
- 所有强度保持 original/arbitrary units；不做归一化；
- `field_G` 仍为 G；不反转、不排序。

### 3.3 JSON 结构

原始导入 JSON 的共同顶层字段：

```text
source_file, source_path, file_size_bytes, sha256,
import_timestamp_utc, software_versions, data, outputs,
processing, rejected_row_details, rejected_row_details_truncated,
validation_warnings, assumptions, raw_file_unchanged
```

`data` 包含：有效点数、拒绝行数、缺失列行数、非有限值数量、重复磁场数量、
磁场最小/最大/跨度、磁场方向、索引连续性、信号最小/最大/均值/标准差。

`processing` 包含：

```text
applied_in_this_run: {
  smoothing: false,
  baseline_correction: false,
  normalisation: false,
  field_axis_reversal: false
}
plot: { figsize_inch, dpi, line_width }
description
```

`outputs` 只记录本次运行实际生成的 CSV、PNG、JSON 路径。

BES3T 额外字段：

```text
source_format = "BES3T"
sha256_definition
file_size_bytes_definition
source_files: [
  {role, path, filename, sha256, size_bytes, sha256_after, unchanged},
  ...
]
format_metadata: {
  descriptor_version, descriptor_text, descriptor_sections,
  parsed_parameters, inferred_parameters, raw_parameters,
  axis, binary, diagnostics
}
```

ASC JSON 当前不包含 `source_format`；这是现有 schema 的不对称，M0 不改变它。

### 3.4 来源与哈希

- ASC：`sha256` = ASC 文件字节哈希；`source_hashes` 当前为空；
- BES3T：`sha256` = `SHA256("BES3T:" + DSC_SHA256 + ":" + DTA_SHA256)`；
  `source_hashes` 分别记录 DSC 和 DTA；
- 批处理记录包含 `source_sha256_before/after`、`source_unchanged`；
- 处理导出在写盘前重新校验源文件；任一源文件变化则拒绝；
- 原始文件保持不变是导出成功的必要条件。

### 3.5 覆盖保护

现有行为：

- 原始/批量输出存在时默认拒绝覆盖，需要显式 `--overwrite` 或 GUI 勾选；
- 处理结果输出存在时默认拒绝；
- 写入 `data/raw` 或覆盖源文件被拒绝，包括 BES3T 的 DSC 与 DTA；
- Plot Editor PNG 导出默认拒绝覆盖，并保护 DSC/DTA。

已有测试覆盖：

- `tests/test_batch.py::test_existing_outputs_are_not_overwritten_silently`
- `tests/test_batch.py::test_single_file_mode_also_protects_outputs`
- `tests/test_processed_export.py` 覆盖保护
- `tests/test_plot_export.py::test_existing_plot_is_not_overwritten_by_default`
- `tests/test_gui_plot_editor.py::test_plot_export_refuses_overwrite_until_allowed`
- `tests/test_gui_plot_editor.py::test_plot_export_is_disabled_during_preview`

### 3.6 回归测试

`tests/test_m0_baseline.py::test_real_raw_export_matches_recorded_schema_and_provenance`

- 对真实 ASC/BES3T 执行 `main()`；
- 检查 CSV 列名/顺序/首末值；
- 检查 JSON 必需字段、来源、哈希、输出路径、`processing` 标志；
- 确认 ASC 没有 `source_format`，BES3T 有；
- 检查 BES3T `source_files` 角色与 `format_metadata`；
- 确认导出前后源文件哈希不变。

---

## 4. M0.3 GUI 与工作流基线

### 4.1 现有自动测试覆盖

| 工作流 | 现有测试 |
| --- | --- |
| ASC 加载/显示 | `tests/test_gui_controller.py::test_load_spectrum_returns_view`；`tests/test_gui_widgets.py::test_window_constructs_and_displays_spectrum` |
| BES3T 加载/显示 | `tests/test_gui_bes3t.py::test_gui_loads_bes3t_and_reports_format` |
| 加载不自动处理 | 新增 `tests/test_m0_gui_baseline.py::test_gui_load_does_not_apply_any_processing` |
| 预处理预览 | `tests/test_gui_preprocessing.py::test_preview_shows_three_curves_and_writes_nothing` |
| 应用/撤销/重置 | `tests/test_gui_preprocessing.py::test_undo_and_reset_return_to_raw`；`test_apply_commits_step_and_keeps_raw_data` |
| Savitzky 默认关闭 | `tests/test_gui_preprocessing.py::test_smoothing_is_off_by_default` |
| 处理导出 | `tests/test_gui_preprocessing.py::test_export_writes_files_and_updates_open_buttons` |
| Plot Editor | `tests/test_gui_plot_editor.py` 全套 |
| PNG 导出 | `tests/test_gui_plot_editor.py::test_plot_export_writes_png_and_leaves_scientific_outputs_unchanged` |
| 源文件覆盖保护 | `tests/test_gui_plot_editor.py::test_plot_export_refuses_overwrite_until_allowed`；`tests/test_gui_bes3t.py::test_gui_plot_export_cannot_overwrite_dta` |
| 错误翻译/缺失文件 | `tests/test_gui_widgets.py::test_error_message_is_retranslated`；`test_gui_bes3t.py::test_gui_reports_missing_dta_in_both_languages` |
| 语言切换不重读/不重算 | `tests/test_gui_widgets.py::test_switch_updates_metadata_and_plot_without_reload`；`test_gui_bes3t.py::test_gui_metadata_retranslates_bes3t` |
| 源文件不变 | `tests/test_gui_preprocessing.py::test_full_workflow_does_not_modify_sources`；新增 GUI 基线测试 |

### 4.2 新增 GUI 基线测试

`tests/test_m0_gui_baseline.py` 对 ASC 与 BES3T 各执行一次：

- 加载后 `_current_view` 存在；
- `_preview_result is None`；
- `_session.has_steps is False`，`steps == ()`；
- `_active_result() is None`；
- 画布只有一条原始曲线；
- Plot Editor 仅提供 `raw` 曲线；
- 加载前后源文件 SHA-256 不变。

这直接锁定“导入本身不执行基线、平滑或归一化”。

### 4.3 手工验证程序（自动化失败时的后备）

1. 运行 `.\.venv\Scripts\python.exe run_gui.py`。
2. 打开一个 ASC 文件：确认原始谱显示、无处理步骤、元数据出现。
3. 打开一个 BES3T DSC 文件：确认格式、DSC/DTA 来源、轴、数据类型显示。
4. 在预处理面板选择两个基线区间，点击“预览”：应出现原始/差异/处理三条曲线；
   不应写任何文件。
5. 取消预览，确认恢复原始单曲线。
6. 应用、撤销、重置：确认原始数据不变，状态文本与按钮状态一致。
7. 切换中英文：确认不重读文件、不重新处理。
8. 选择输出目录并导出处理结果：确认生成 CSV/PNG/JSON；重复导出默认拒绝覆盖。
9. 检查源文件 SHA-256 前后不变。

---

## 5. M0.4 架构依赖发现

### 5.1 当前模块级依赖

```text
epr_workflow
├── epr_workflow.bes3t
│   └── epr_workflow.plot_asc
├── epr_workflow.plot_asc
└── epr_workflow.preprocessing

epr_workflow.gui
├── epr_workflow.gui.controller
│   ├── epr_workflow.gui.i18n
│   ├── epr_workflow.plot_asc
│   └── epr_workflow.preprocessing
└── epr_workflow.gui.i18n

epr_workflow.plot_settings
└── epr_workflow.preprocessing

epr_workflow.plot_export
├── epr_workflow.plot_asc
└── epr_workflow.plot_settings

epr_workflow.processed_export
├── epr_workflow.plot_asc
└── epr_workflow.preprocessing

epr_workflow.gui.main_window
├── gui.controller, gui.i18n, gui.mpl_canvas
├── gui.plot_editor_panel, gui.plot_export_dialog,
│   gui.preprocessing_panel
├── epr_workflow.plot_asc, epr_workflow.plot_export,
│   epr_workflow.plot_settings, epr_workflow.preprocessing,
│   epr_workflow.processed_export
```

`plot_asc` 内部的 `from epr_workflow.bes3t import read_bes3t` 位于
`read_dataset()` 函数体内，不是模块级导入；因此当前没有模块级循环。

### 5.2 Qt 依赖

当前直接导入 PySide6 的模块全部在 `src/epr_workflow/gui/`：

- `gui/app.py`
- `gui/main_window.py`
- `gui/plot_editor_panel.py`
- `gui/plot_export_dialog.py`
- `gui/preprocessing_panel.py`

`gui/mpl_canvas.py` 通过 Matplotlib Qt 后端间接使用 Qt，但不在核心模块。
核心模块与 `gui/controller.py`、`gui/i18n.py` 不直接导入 PySide6。

### 5.3 循环依赖

模块级 import 图检查结果：**无循环**。

- `bes3t` → `plot_asc` 是单向的；
- `plot_asc` 不在模块级导入 `bes3t`；
- GUI 模块单向依赖控制器/核心；
- `gui` 包不反向被核心导入。

### 5.4 多职责模块

| 模块 | 当前混合职责 | 迁移风险 |
| --- | --- | --- |
| `plot_asc.py` | ASC 导入、校验、绘图、CLI、批处理、元数据、路径保护 | 最高；M1/M2/M3/M6 逐步拆分 |
| `bes3t.py` | 技术专用解析 + 依赖 `plot_asc.ImportResult` | 中高；应包装为新 importer |
| `preprocessing.py` | EPR 轴语义 + 算法 + 会话 + 记录 | 高；需通用轴适配 |
| `plot_settings.py` | 样式 + EPR 曲线键 + 渲染 + 缓存 | 中高；需 Series 抽象 |
| `processed_export.py` | 导出 + EPR 列/标题/假设 | 中；需 ExportProfile |
| `gui/main_window.py` | UI + 工作流状态 + 元数据 + EPR 面板 | 最高；M8 拆分 GUI 壳 |
| `gui/i18n.py` | 翻译机制 + 扁平 EPR 键空间 | 中；需命名空间 |

### 5.5 当前违反目标架构的地方

这些是**现有债务**，M0 只记录，不强制修复：

1. `bes3t.py` 是技术专用模块，却位于包根并依赖 `plot_asc.ImportResult`；
2. `plot_asc.py` 同时承担 importer、plotting、CLI、batch 和 export guard；
3. `plot_settings.py`、`processed_export.py` 内含 EPR 专用曲线键、列名、标题和假设；
4. `gui/main_window.py` 直接依赖 EPR 语义和所有面板，没有技术模块注册；
5. `preprocessing.py` 使用 `field_G`、G 窗口和 EPR 词汇；
6. 当前没有 `app/`、`core/`、`techniques/` 包；
7. `PROJECT_ROOT`、`results`、`config/gui_settings.ini` 仍是 EPR 项目路径。

本次**没有引入新的架构违规**；只新增测试和文档。

### 5.6 架构测试

`tests/test_m0_architecture.py`：

- `test_modules_outside_gui_do_not_import_qt`
- `test_modules_outside_gui_do_not_import_gui`
- `test_importing_core_and_controller_does_not_load_qt`
- `test_current_module_level_import_graph_has_no_cycles`

这些测试只保护当前已成立的边界，不迫使现有多职责模块提前符合未来架构。

---

## 6. 科学完整性不变量

| 不变量 | 现有/新增证据 | 状态 |
| --- | --- | --- |
| 原始输入文件不变 | ASC/BES3T 哈希测试；`test_original_file_is_not_modified`、`test_batch_preserves_source_files_and_values`、`test_real_xepr_dataset_is_immutable...`、M0 数值/GUI/导出测试 | 已验证 |
| 轴不被静默排序或修复 | 非单调拒绝、递减轴保留、重复值诊断；M0 基线逐值检查轴首末/方向 | 已验证 |
| 不自动基线校正 | GUI 默认状态测试；新增加载不自动处理测试；raw JSON `applied_in_this_run.baseline_correction=false` | 已验证 |
| 不自动平滑/归一化 | 平滑默认关闭测试；新增 `steps == ()`；当前没有归一化代码路径 | 已验证（对现有功能） |
| 不静默插值/外推 | v0.2.0 生产代码没有插值/外推路径；M0 报告明确记录，未来新增时必须显式并记录 | 已记录；未来操作需新增测试 |
| 未知元数据保持未知 | ASC 元数据不虚构单位测试；BES3T 必需参数严格拒绝；M0 文档记录当前 schema 的不对称 | 已验证/已记录 |
| 非法/不支持数据显式拒绝 | ASC 非单调/NaN/不足点；BES3T 缺失/重复/截断/尾随/复数/多维/单位 | 已验证 |

注意：M0 不会为尚未实现的归一化、插值或 FTIR 预处理伪造测试；这些将在对应
里程碑中增加显式选择、预览、记录和拒绝测试。

---

## 7. 新增测试与结果

### 7.1 新增文件

- `tests/fixtures/m0_baseline.json`
- `tests/test_m0_baseline.py`
- `tests/test_m0_architecture.py`
- `tests/test_m0_gui_baseline.py`
- `docs/m0_baseline_report.md`

### 7.2 新增测试

- 数值基线：2 个参数化测试（ASC/BES3T）
- 原始导出 schema/来源：2 个参数化测试（ASC/BES3T）
- 架构边界：4 个测试
- GUI 加载不自动处理：2 个参数化测试（ASC/BES3T）

合计 **10 个通过测试**。

### 7.3 实际结果

原测试集（排除 M0 新测试）：

```text
298 passed, 1 skipped
```

完整测试集：

```text
308 passed, 1 skipped
```

`-W error::UserWarning`：

```text
308 passed, 1 skipped
```

差异说明：新增 10 个 M0 测试全部通过；原有 298 passed / 1 skipped 不变。
跳过项仍是 Windows 无法构造的大小写歧义 `.DTA` 伴随文件。真实 ASC/BES3T
基线测试在本机执行并通过，没有跳过。

---

## 8. 已知缺口与风险

1. M0 只建立基线，不实现 Spectrum1D、importer 注册表、FTIR/ATR。
2. 真实 ASC/BES3T 原始文件不随仓库分发；在缺少文件的环境中，相关测试会跳过。
   基线 JSON 仍记录期望值，但不能替代真实数据验证。
3. BES3T 仍缺少对应的 Xepr ASCII 导出，跨格式逐点比较仍未完成。
4. 当前 GUI 测试依赖精确文本和部分私有状态；未来 GUI 拆分前需要继续扩大
   接口级测试，M0 只增加了加载不自动处理测试。
5. 当前没有插值、归一化、峰检测或差谱；M0 只能记录“当前不存在静默路径”，
   不能为未来操作提供行为保证。
6. M0 的架构测试只保护 Qt/反向 GUI/循环依赖边界；`bes3t → plot_asc` 等现有
   耦合已记录但未强制修复。
7. 基线 JSON 是当前实现的快照；任何数值或 schema 变化都必须显式审查，
   不能直接更新。
8. CSV/JSON 的 ASC/BES3T schema 不对称（ASC 无 `source_format`，BES3T 有）
   是当前行为，M0 不改变。

---

## 9. M0 完成清单

- [x] 阅读 `CLAUDE.md` 和 `docs/architecture_proposal.md`
- [x] 记录 ASC 数值基线
- [x] 记录 BES3T 数值基线
- [x] 记录源文件大小与 SHA-256
- [x] 记录 CSV 列名、顺序、类型、单位
- [x] 记录 JSON 顶层字段、来源、哈希、raw/processed 表示
- [x] 记录覆盖保护
- [x] 记录 GUI 工作流与现有自动测试
- [x] 新增 GUI 加载不自动处理测试
- [x] 分析模块依赖、Qt 依赖、循环依赖、多职责模块
- [x] 新增架构边界测试
- [x] 记录科学完整性不变量与证据
- [x] 创建机器可读基线记录
- [x] 运行原测试集：298 passed, 1 skipped
- [x] 运行完整测试集：308 passed, 1 skipped
- [x] 运行 `-W error::UserWarning`：308 passed, 1 skipped
- [x] 确认无生产代码、现有测试、配置、项目身份修改
- [x] 确认无 raw data 修改
- [x] 确认无 commit、无 push

**M0 状态：完成。** M1 完成情况见 [m1_spectrum1d_report.md](m1_spectrum1d_report.md)，
M2 见 [m2_importer_registry_report.md](m2_importer_registry_report.md)，
M3 见 [m3_export_report.md](m3_export_report.md)，
M4 见 [m4_processing_report.md](m4_processing_report.md)，
M5 见 [m5_generic_plotting_report.md](m5_generic_plotting_report.md)，
M6 见 [m6_cli_batch_report.md](m6_cli_batch_report.md)，
M7 见 [m7_epr_backend_closure_report.md](m7_epr_backend_closure_report.md)，
M8 见 [m8_gui_architecture_report.md](m8_gui_architecture_report.md)。
