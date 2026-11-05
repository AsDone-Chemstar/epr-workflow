# M10 报告：FTIR Import GUI 与 Raw Spectrum Display

- 状态：**M10 完成**
- 基线版本：EPR Workflow **v0.2.0**
- Git 基线：`327d5f6`
- 前序测试基线：M9 **592 passed, 1 skipped**
- M10 基线：**622 passed, 1 skipped**
- 日期：2026-11-03
- 范围：FTIR 技术注册、导入选项 GUI、原始 Spectrum1D 显示、元数据/状态/语言集成
- 旧 EPR 应用：**未修改，仍独立可用**
- Git：**未 commit、未 push、未创建 tag**
- M11 已另行完成；M12–M17：**未实现**

---

## 1. 实现前检查

检查了：

- [architecture_proposal.md](architecture_proposal.md) 的 M8–M10 设计；
- [M8 GUI 报告](m8_gui_architecture_report.md)；
- [M9 FTIR Importer 报告](m9_ftir_importer_report.md)；
- generic `MainWindow`、`ApplicationController`、`TechniqueRegistry`；
- EPR panel 的协议实现和离屏测试方式；
- M9 `ColumnMapping` / `FTIRImportOptions` / FTIR metadata；
- M1 `Spectrum1D` 和 M5 plotting API；
- 现有 GUI、架构和 EPR 回归测试。

M10 没有修改 M9 importer 的解析或元数据行为。

---

## 2. 最终 GUI 架构

```text
src/spectralab/app/gui/
├── app.py                    composition root + desktop entry
├── main_window.py            generic shell（未为 FTIR 修改）
├── controller.py             generic controller + options passthrough
├── metadata.py               generic metadata formatter（增加 provenance 信息）
├── ftir_panel.py             FTIR panel
├── ftir_options_widget.py    reusable explicit options editor
├── ftir_import_dialog.py     file selection + options confirmation
└── ftir_translations.py      FTIR zh/en catalog + registration helper
```

依赖关系：

```text
app/gui/app.py (composition root)
  ├── EPR panel
  └── FTIR panel

ftir_panel.py
  ├── PySide6 + Matplotlib Qt canvas
  ├── app/gui controller / options widget / dialog
  ├── spectralab.core.model + plotting
  └── M9 FTIR options objects

techniques/ftir/*
  └── 仍然 Qt-free、app-free
core/*
  └── 仍然 Qt-free、app-free、technique-free
```

FTIR GUI 放在应用层，而不是 `techniques/ftir/gui/`，以保持 FTIR backend 的
Qt-free 边界；只有 composition root 导入具体 FTIR panel。

---

## 3. FTIR 注册

`build_technique_registry()` 现在显式注册：

```text
1. epr
2. ftir
```

FTIR descriptor：

- `id = "ftir"`
- display key：`technique.ftir.name`
- panel factory：`spectralab.app.gui.ftir_panel.create_panel`
- file patterns：
  - `*.csv`, `*.CSV`
  - `*.txt`, `*.TXT`
  - `*.dpt`, `*.DPT`

没有自动发现或隐式注册。generic `MainWindow` 和 `ApplicationController`
没有 FTIR 专用分支。

---

## 4. ApplicationController options 透传

`ApplicationController.load_spectrum()` 新增向后兼容参数：

```python
load_spectrum(
    path,
    *,
    format_id=None,
    technique_hint=None,
    options=None,
)
```

`options` 原样传给 `ImporterRegistry.read()`，controller 不解释 FTIR 选项。
FTIR panel 调用：

```python
controller.load_spectrum(
    path,
    technique_hint="ftir",
    options={"ftir": ftir_options},
)
```

因此所有解析和科学语义仍由 M9 backend 执行。

---

## 5. FTIR Panel 行为

`FtirPanel` 实现 `TechniquePanelProtocol`：

- `spectrum_changed`
- `status_event`
- `open_file(path)`
- `retranslate()`
- `current_display()`

面板提供：

- 当前文件标签；
- “使用选项导入 FTIR 文件…”按钮；
- 原始谱图；
- 高波数左侧显示复选框；
- 原始数据说明；
- 内联 FTIR 导入选项编辑器；
- 元数据通过 generic shell 的 metadata view 显示；
- 状态通过 generic status view 显示。

### 文件导入流程

1. 通用 “打开光谱…” 按钮选择 CSV/TXT/DPT 文件；
2. FTIR panel 使用当前内联选项调用 controller；
3. controller 通过 M9 registry 选择 `ftir.csv` 或 `ftir.txt`；
4. M9 返回 `ImportedDataset` + `Spectrum1D`；
5. panel 更新当前显示、绘图、metadata、status。

面板自己的 “使用选项导入…” 按钮打开模态
`FtirImportDialog`，允许在导入前显式确认文件、列映射、解析选项和 FTIR 元数据。

导入失败或选项无效时：

- 不替换上一条光谱；
- 不修改已有图；
- 发出 error status；
- 显示源错误和稳定错误代码。

成功但有 importer warnings 时使用 warning status，并显示 warning 内容。

---

## 6. 导入对话框与选项

`FtirImportDialog` 包含：

- 文件路径输入；
- 浏览按钮和 FTIR 文件过滤器；
- 完整选项编辑器；
- Import / Cancel；
- 行内错误标签；
- 接受前验证文件存在与选项合法。

### 列与解析选项

| 选项 | GUI 控件 | 默认 |
| --- | --- | --- |
| X 列 | 文本（索引或表头名） | 空（两列文件使用 M9 默认） |
| Y 列 | 文本（索引或表头名） | 空 |
| Header | 复选框 | False |
| Delimiter | 下拉：auto/comma/tab/semicolon/whitespace/custom | auto |
| 自定义分隔符 | 单字符输入 | 关闭 |
| Decimal | dot / comma | dot |
| Comment markers | 文本，空格分隔多个 | 空 |
| Encoding | 可编辑下拉 | `utf-8-sig` |
| Skip rows | 非负整数 | 0 |

多列文件未指定 X/Y 时，M9 仍会明确失败，不会猜列。

### FTIR 元数据选项

| 选项 | 控件 |
| --- | --- |
| X quantity | unknown / wavenumber |
| X unit | unknown / `cm^-1` |
| X name | 可选文本 |
| Y semantics | unknown / absorbance / transmittance |
| Y unit | 可选文本 |
| Y name | 可选文本 |
| Acquisition mode | Unknown / ATR / Transmission |
| ATR correction | unknown / applied / not_applied / not_applicable |
| Instrument vendor | 可选文本 |
| Instrument model | 可选文本 |

所有值都显式传递到 M9，GUI 不从文件名、后缀、数值范围或厂商名推断科学语义。
Acquisition mode 和 signal semantics 保持独立。

内联编辑器与对话框使用同一个 `FtirOptionsWidget`，避免两套选项实现。

---

## 7. 元数据处理

generic M8 metadata view 现在额外显示：

- `provenance.format_metadata["import_options"]`；
- provenance warnings；
- provenance assumptions。

FTIR 导入后 metadata view 显示：

- technique = ftir；
- dataset ID；
- point count；
- axis quantity / unit / name / direction；
- signal semantics / unit / name；
- source filename、format、size、SHA-256；
- acquisition mode；
- ATR correction status；
- instrument vendor/model；
- resolved import options；
- unknown fields；
- import assumptions。

未知字段不会补默认值，继续在 `unknown_fields` 中显式列出，并显示为
`unknown` / `未知`。

---

## 8. Raw Spectrum Display

使用 M5：

```python
plot_spectrum(axes, spectrum, PlotConfig(...))
```

显示规则：

- 只显示 raw `Spectrum1D`；
- 不创建 `ProcessingSession`；
- 不进行平滑、基线、归一化、ATR 校正、排序、反转或插值；
- 图例标签为“原始”/“Raw”；
- 图上明确标注“只显示原始数据…”；
- title 使用显式 metadata title，否则 dataset ID；
- X label 使用已知 axis name/quantity/unit；
- Y label 使用已知 signal name/semantics/unit；
- 未知 X/Y 标签显示为显式的未知文本；
- `axes.lines[0]` 的 X/Y 数据与 `Spectrum1D` 原始数组逐值一致。

### 显示方向

当 X quantity 为 `wavenumber`：

- 默认勾选“高波数显示在左侧”；
- 只调用 `axes.set_xlim(high, low)`；
- 不修改数据数组、点序或源文件；
- 未勾选时恢复正常从左到右的数值方向。

未知 quantity 时该复选框禁用，不进行方向反转。

---

## 9. 语言实现

新增 `ftir_translations.py`：

- 技术名称；
- panel 标签；
- 所有选项标签/枚举显示；
- 导入对话框；
- 状态消息；
- 原始谱/显示方向说明；
- 错误提示。

运行时切换语言会更新：

- FTIR panel 标签；
- 选项编辑器标签和下拉项；
- 导入对话框（存在时）；
- metadata labels；
- status message；
- 图例与 X/Y 轴标签。

EPR translation catalog 与旧 EPR GUI 文本未修改。

---

## 10. 真实样本验证

真实文件：

```text
S-BSAPEG-10.0.dpt
```

位置：项目根目录。GUI 测试使用显式选项：

- X 0 / Y 1
- `wavenumber` / `cm^-1`
- Absorbance
- ATR
- ATR correction unknown

结果：

- 原 GUI 导入成功；
- 4350 点；
- 图中 line 包含 4350 个 X 点；
- X 首末点约 `3998.83701` / `899.39981`；
- X 轴显示为高波数在左；
- metadata 显示 4350 点、wavenumber、cm^-1、absorbance、ATR、unknown；
- status 为 success；
- 没有 processing session；
- 源文件 SHA-256 前后一致；
- `processing_applied=[]`（M9 原始导出路径同样保持）。

真实文件是用户上传的未跟踪文件；测试未修改它。

---

## 11. 新增与修改文件

### 新增 FTIR GUI

- [src/spectralab/app/gui/ftir_panel.py](../src/spectralab/app/gui/ftir_panel.py)
- [src/spectralab/app/gui/ftir_import_dialog.py](../src/spectralab/app/gui/ftir_import_dialog.py)
- [src/spectralab/app/gui/ftir_options_widget.py](../src/spectralab/app/gui/ftir_options_widget.py)
- [src/spectralab/app/gui/ftir_translations.py](../src/spectralab/app/gui/ftir_translations.py)

### 新增测试

- [tests/test_ftir_gui.py](../tests/test_ftir_gui.py)：23 个测试
- [tests/test_m10_architecture.py](../tests/test_m10_architecture.py)：7 个测试

合计 **30 个新测试**。

### 修改

- [src/spectralab/app/gui/app.py](../src/spectralab/app/gui/app.py)：显式注册 FTIR
- [src/spectralab/app/gui/controller.py](../src/spectralab/app/gui/controller.py)：
  generic `options` passthrough
- [src/spectralab/app/gui/metadata.py](../src/spectralab/app/gui/metadata.py)：
  显示 import options / warnings / assumptions
- [src/spectralab/app/gui/i18n.py](../src/spectralab/app/gui/i18n.py)：3 个通用
  provenance 标签
- [tests/test_gui_shell.py](../tests/test_gui_shell.py)：技术数量从 1 更新为 2
- [docs/architecture_proposal.md](architecture_proposal.md)：M10 状态和结果
- [docs/m9_ftir_importer_report.md](m9_ftir_importer_report.md)：M9 后续状态
- 本报告

### 未修改

- `src/epr_workflow/` 全部生产代码
- 旧 EPR GUI/Plot Editor/preprocessing/CLI/batch/export
- `app/gui/epr_panel.py`、`epr_translations.py`
- M9 FTIR importer/parser 行为
- M1–M8 核心模型、导出、处理、绘图 API 行为
- 原始实验数据
- `requirements.txt`

---

## 12. 架构验证

- `core` 仍不导入 Qt、GUI、app 或 techniques；
- `techniques/ftir` 仍不导入 Qt、app、EPR 或 `epr_workflow`；
- generic GUI 文件不导入 FTIR GUI 或 FTIR backend；
- FTIR GUI 文件不导入 EPR GUI/backend 或 legacy；
- `app/gui/app.py` 是唯一注册具体 FTIR panel 的 composition root；
- 导入图无循环；
- FTIR backend 不包含 GUI 目录；
- 无运行时 `epr_workflow` 导入；
- EPR panel 和旧 GUI 回归正常。

---

## 13. 测试结果

新增 **30 个 M10 测试**：

- `tests/test_ftir_gui.py`：23
- `tests/test_m10_architecture.py`：7

覆盖：

1. FTIR 注册；
2. panel protocol；
3. CSV/TXT/DPT 导入；
4. options 透传到 M9；
5. 列映射；
6. 元数据保留；
7. unknown 显示；
8. 递增/递减轴；
9. 原始数据完整性；
10. 导入错误；
11. warning/success/error status；
12. 中英文；
13. 运行时语言切换；
14. 真实样本 GUI；
15. EPR GUI 回归；
16. 架构约束。

实际运行：

```text
完整测试集 pytest -v：
622 passed, 1 skipped
exit code 0

pytest -q -W error::UserWarning：
622 passed, 1 skipped
exit code 0

原 EPR 测试集（HEAD 中已跟踪的 14 个测试文件）：
298 passed, 1 skipped
exit code 0
```

日志：

- `results/logs/pytest_m10_20261103_verbose.txt`
- `results/logs/pytest_m10_20261103_userwarning.txt`
- `results/logs/pytest_m10_20261103_original.txt`

基线比较：

- M9：592 passed, 1 skipped
- M10：622 passed, 1 skipped
- 新增 30 passed
- 原 EPR 子集保持 298 passed, 1 skipped

剩余 skip 是原 EPR 的 Windows `.DTA` 大小写歧义测试，与 M10 无关。

---

## 14. 兼容性与科学完整性

- 旧 EPR GUI、CLI、Plot Editor、preprocessing、export 未修改；
- 原 EPR 测试保持 298 passed, 1 skipped；
- M9 FTIR importer 未修改；
- M10 不执行任何 FTIR 处理；
- 源文件只读；
- 原始点序、数值、轴方向不被绘图反转改变；
- GUI 不推断 acquisition mode、signal semantics、axis unit 或 ATR 状态；
- 未知 metadata 保持 unknown；
- 所有 import options 都进入 M9 provenance；
- 无新增依赖。

---

## 15. 剩余技术债与限制

1. 没有导入前数据预览；对话框在 accept 时验证并直接导入。
2. 导入选项不持久化；每次启动使用安全默认值。
3. 通用 “打开文件” 使用内联选项；完整配置需使用 panel 的导入对话框。
4. 全数字表头列名会被当作列索引；没有单独的“索引/名称”模式切换。
5. 没有 FTIR processing、归一化、基线、峰检测、差谱或多谱比较。
6. 没有 Plot Editor、processed export 或 FTIR 图像导出。
7. 宽表不拆分；多列必须显式映射一个 X/Y。
8. Metadata view 对 technique_metadata/import options 使用较长 JSON 文本。
9. 后端科学错误保留英文原文；通用界面标签/状态已本地化。
10. 显示方向只对 `wavenumber` 启用；未知 X 轴不能启用高波数左侧显示。
11. 每次成功导入会把显示方向复选框重置为高波数在左；未保存用户偏好。
12. 一个文件仍只能产生一个 Spectrum1D。
13. 没有 vendor-specific FTIR 格式或自动厂商识别。
14. 没有 recent files、文件菜单或多窗口。

---

## 16. Git 状态

实现前后 HEAD 均为：

```text
327d5f633c701cb07c3279754d35427dfc6b8bb0
```

- 未 commit；
- 未 push；
- 未创建 tag；
- 未重写 Git 历史；
- 未修改原始实验数据；
- 未修改 `requirements.txt`；
- `src/epr_workflow/` 未修改；
- 用户上传的 `S-BSAPEG-10.0.dpt` 仍为未跟踪文件，内容未修改；
- M0–M10 文件仍未跟踪。

---

## 17. 完成清单

- [x] FTIR technique 显式注册
- [x] FTIR panel 实现 panel protocol
- [x] generic MainWindow/Controller 无 FTIR 专用分支
- [x] FTIR backend 保持 Qt-free
- [x] CSV/TXT/DPT 文件过滤
- [x] 文件选择对话框
- [x] X/Y 索引或表头名
- [x] 分隔符/小数点/header/comment/encoding/skip rows
- [x] acquisition mode / ATR status
- [x] axis quantity/unit
- [x] signal semantics/unit
- [x] vendor/model
- [x] M9 options 透传
- [x] 原始谱 M5 显示
- [x] 递增/递减轴
- [x] 仅视觉的高波数左侧显示
- [x] raw 数据不被绘图修改
- [x] unknown 元数据显式显示
- [x] metadata import options/warnings/assumptions
- [x] success/warning/error status
- [x] 中英文和运行时切换
- [x] 真实样本 GUI 验证
- [x] EPR GUI 回归
- [x] 原 EPR 298 passed / 1 skipped
- [x] 完整 622 passed / 1 skipped
- [x] `-W error::UserWarning` 通过
- [x] M10 范围停在 M11 之前（M11 已另行完成）
- [x] 未 commit、未 push

**M10 完成。** FTIR 可经新 GUI 导入并显示原始谱；真实样本通过；元数据、
状态和语言服务工作；M10 未进行任何 FTIR 处理。M11 已完成，见
[M11 Maintenance & Normalization 报告](m11_maintenance_and_normalization_report.md)；
M12 尚未开始。
