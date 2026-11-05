# M8 报告：SpectraLab GUI Shell 与技术注册表

- 状态：**M8 完成**
- 基线版本：EPR Workflow **v0.2.0**
- Git 基线：`327d5f6`
- 前序测试基线：M7 **494 passed, 1 skipped**
- M8 基线：**523 passed, 1 skipped**
- 日期：2026-11-02
- 范围：新增技术无关的 GUI 壳、技术注册表、设置/语言/元数据/状态服务，以及 EPR 面板
- 旧 EPR GUI：**未修改，仍独立可用**
- Git：**未 commit、未 push**

---

## 1. 实现前检查

检查了：

- `epr_workflow.gui` 的 `main_window.py`、`controller.py`、`i18n.py`、
  `mpl_canvas.py`、`preprocessing_panel.py`、`plot_editor_panel.py`
- 现有 GUI 测试与离屏测试方式
- M1–M7 的 `Spectrum1D`、`ProcessedSpectrum`、importer registry、
  CSV/JSON export、ProcessingSession 和 generic plotting API
- M2/M4 架构测试对 `techniques` 包的 Qt 边界要求

### 现有 EPR GUI 行为

- 旧 GUI 是单个 EPR 专用 `MainWindow`；
- 直接依赖 EPR parser、preprocessing、Plot Editor、plot export、processed export；
- 默认语言为简体中文；
- 支持 ASC/BES3T 加载、批处理、preview/apply、undo/reset、Plot Editor 和导出；
- 旧 GUI 测试依赖精确文本、私有状态和旧行为。

M8 没有修改旧 GUI。

---

## 2. 最终 GUI 架构

```text
src/spectralab/app/gui/
├── app.py              # composition root + desktop entry
├── __main__.py         # python -m spectralab.app.gui
├── main_window.py      # generic shell
├── controller.py       # Qt-free app controller
├── technique.py        # descriptor/protocol/registry (Qt-free)
├── settings.py         # JSON settings service (Qt-free)
├── i18n.py             # translator/catalogs (Qt-free)
├── metadata.py         # generic metadata formatter (Qt-free)
├── status.py           # status event model (Qt-free)
├── metadata_view.py    # Qt metadata pane
├── status_view.py      # Qt status label
├── epr_panel.py        # concrete EPR GUI adapter
└── epr_translations.py # EPR GUI translations
```

### 依赖关系

```text
app/gui/app.py (composition root)
  ├── app/gui/main_window.py  (no concrete EPR import)
  ├── app/gui/controller.py   (Qt-free)
  └── app/gui/epr_panel.py    (concrete EPR GUI adapter)

epr_panel.py
  ├── PySide6 / Matplotlib Qt canvas
  ├── spectralab.core (Spectrum1D, ProcessedSpectrum, ProcessingSession, plotting)
  └── spectralab.techniques.epr (independent EPR backend)

techniques/epr/*
  └── no Qt, no app import
core/*
  └── no Qt, no GUI, no app, no techniques
```

### 设计调整：EPR panel 位置

原架构提案将 EPR GUI adapter 放在 `techniques/epr/gui/`。M2/M4 架构测试明确要求
`techniques/epr` backend 不导入 Qt，因此 M8 将具体 EPR 面板放在应用层
`app/gui/epr_panel.py`：

- backend 继续保持 Qt-free；
- generic shell 不导入 EPR panel；
- 只有 composition root `app/gui/app.py` 导入 EPR panel；
- 依赖方向仍是 `app → techniques → core`；
- 未来 FTIR 面板同样可以在 app 层注册，不需要修改 generic MainWindow/Controller。

这是有意的架构 refinement，不是削弱 backend 边界。

---

## 3. 新增与修改文件

### 新增 GUI shell

- [src/spectralab/app/gui/__init__.py](../src/spectralab/app/gui/__init__.py)
- [src/spectralab/app/gui/app.py](../src/spectralab/app/gui/app.py)
- [src/spectralab/app/gui/__main__.py](../src/spectralab/app/gui/__main__.py)
- [src/spectralab/app/gui/main_window.py](../src/spectralab/app/gui/main_window.py)
- [src/spectralab/app/gui/controller.py](../src/spectralab/app/gui/controller.py)
- [src/spectralab/app/gui/technique.py](../src/spectralab/app/gui/technique.py)
- [src/spectralab/app/gui/settings.py](../src/spectralab/app/gui/settings.py)
- [src/spectralab/app/gui/i18n.py](../src/spectralab/app/gui/i18n.py)
- [src/spectralab/app/gui/metadata.py](../src/spectralab/app/gui/metadata.py)
- [src/spectralab/app/gui/metadata_view.py](../src/spectralab/app/gui/metadata_view.py)
- [src/spectralab/app/gui/status.py](../src/spectralab/app/gui/status.py)
- [src/spectralab/app/gui/status_view.py](../src/spectralab/app/gui/status_view.py)

### 新增 EPR GUI adapter

- [src/spectralab/app/gui/epr_panel.py](../src/spectralab/app/gui/epr_panel.py)
- [src/spectralab/app/gui/epr_translations.py](../src/spectralab/app/gui/epr_translations.py)

### 新增测试

- [tests/test_gui_services.py](../tests/test_gui_services.py)：11
- [tests/test_gui_shell.py](../tests/test_gui_shell.py)：12
- [tests/test_m8_architecture.py](../tests/test_m8_architecture.py)：6

合计 **29 个新测试**。

### 新增/更新文档

- 本报告
- [docs/architecture_proposal.md](architecture_proposal.md)：M8 状态、结果和测试基线
- M7 报告页脚更新

### 未修改

- `src/epr_workflow/` 全部生产代码
- 旧 EPR GUI、Plot Editor、preprocessing、CLI、batch、export
- M3 schemas
- M4 `ProcessingSession`
- M5 plotting API
- M6 CLI/batch
- 现有测试、原始数据和配置
- `requirements.txt`

---

## 4. Technique Registry

模块：`spectralab.app.gui.technique`

### `TechniqueDescriptor`

```python
@dataclass(frozen=True)
class TechniqueDescriptor:
    id: str
    display_name_key: str
    panel_factory: Callable
    file_patterns: tuple[str, ...]
    translations: Mapping[str, Mapping[str, str]]
```

### `TechniqueRegistry`

- 显式 `register()`
- 保留注册顺序
- 重复 id 拒绝
- `get()` / `select()`
- 未知 id 抛出 `TechniqueRegistryError`
- 稳定的 `TechniquePanelProtocol`：
  - `spectrum_changed`
  - `status_event`
  - `open_file()`
  - `retranslate()`
  - `current_display()`

没有自动插件发现，没有隐式扫描。

### Dummy technique

测试中注册了 `dummy.one` 和 `dummy.two` 两个测试技术，证明：

- 新 panel 可以在不修改 generic MainWindow/Controller 的情况下注册；
- 技术切换可用；
- 每个技术有自己的翻译 catalog；
- 面板协议由 Qt widget 结构化实现。

---

## 5. Application Controller

模块：`spectralab.app.gui.controller`

- Qt-free
- 持有 `TechniqueRegistry`
- 持有 M2 importer registry
- 提供：
  - `active_technique`
  - `select_technique()`
  - `load_spectrum()`

`load_spectrum()`：

- 使用 M2 importer registry；
- 只接受恰好一个 `Spectrum1D`；
- 多谱输入明确失败；
- 不处理、不排序、不改源文件。

---

## 6. Generic Main Window

模块：`spectralab.app.gui.main_window`

功能：

- 技术选择器
- 打开文件
- 语言选择
- 左侧 generic metadata view
- 右侧技术面板 stack
- 底部 status view
- 设置加载/保存
- 运行时语言切换
- 面板状态/错误转发

Generic shell 不导入任何具体 technique panel。具体 panel 由 registry/factory 提供。

---

## 7. EPR Integration

模块：`app.gui.epr_panel`

EPR 是第一个注册技术。

### 支持

- 通过 M2 registry + M7 independent EPR backend 导入 ASC/BES3T；
- 显示 `Spectrum1D`；
- 通过 M5 `plot_spectrum()` 绘制原始谱；
- 显示 generic metadata；
- 显式控制：
  - 线性基线（四个窗口边界必须由用户填写）
  - Savitzky–Golay 平滑
  - undo
  - redo
  - reset
- `ProcessingSession` 在 panel 内创建；
- processed 显示为 `ProcessedSpectrum`，raw/processed 在图上区分；
- 处理历史进入 metadata view；
- 失败操作保持原 session 状态，并显示 error status。

### 不支持 / 未迁移

- 旧 Plot Editor
- preview / pending apply
- raw-input smoothing reorder
- processed CSV/JSON/PNG 导出
- batch GUI
- 旧 EPR 图形全部细节

M8 的目标是一个可工作的新 shell，不是重现旧 GUI 全部功能。

---

## 8. Settings

模块：`spectralab.app.gui.settings`

- JSON 文件：`config/spectralab_gui_settings.json`
- 与旧 EPR `config/gui_settings.ini` 分开
- 保存：
  - language
  - active technique
  - window width/height
- 默认值：
  - 简体中文
  - 1100 × 760
- malformed JSON / invalid values → safe defaults
- 写入使用临时文件 + `os.replace`
- 写失败以状态 warning 显示，不崩溃
- 测试环境可使用内存-only 或临时路径

---

## 9. Language

模块：`spectralab.app.gui.i18n`

- 简体中文 / English
- 通用 shell catalog
- EPR panel catalog
- 技术 catalog 显式注册
- 缺失 key fallback：
  1. 当前语言
  2. 默认语言（`zh`）
  3. key 本身
- 冲突 key 拒绝
- 不支持的语言 catalog 拒绝
- 运行时切换更新：
  - window title
  - controls
  - technique names
  - panel labels
  - plot raw/processed legend labels
  - metadata view
  - status message

旧 EPR GUI 文本未修改。

---

## 10. Metadata / Status

### Metadata

`format_metadata()` 支持：

- `Spectrum1D`
- `ProcessedSpectrum`
- 显示类型
- technique
- dataset id
- 点数
- axis quantity/unit/name/direction/source
- signal semantics/unit/name/source
- source format
- title/instrument/acquisition/sample
- technique_metadata / extra
- unknown_fields
- metadata_origin
- source files + hashes/sizes
- processed history、parameters、warnings、assumptions、diagnostics

未知值统一显示为 `unknown` / `未知`，不推断单位或语义。

### Status

`StatusEvent` levels：

- success
- info
- warning
- error

颜色区分，语言切换后状态文本重新翻译。Panel 错误通过 status event 显示，不静默吞掉。

---

## 11. Architecture Validation

- `src/spectralab/core` 仍不导入 Qt、GUI、app 或 techniques；
- generic GUI modules 不导入 concrete techniques；
- `app/gui/epr_panel.py` 不导入 `epr_workflow` 或 FTIR；
- `techniques/epr` backend 仍不导入 Qt；
- 导入 core/EPR backend/Qt-free GUI services 不加载 Qt；
- 旧 `epr_workflow.gui` 仍可导入；
- M6 CLI 仍可导入且不加载 Qt；
- GUI 导入图无循环；
- `app/gui/app.py` 是唯一 concrete EPR composition root。

---

## 12. 测试结果

新增 **29 个 M8 测试**：

- `tests/test_gui_services.py`：11
- `tests/test_gui_shell.py`：12
- `tests/test_m8_architecture.py`：6

覆盖：

- settings 默认/持久化/malformed
- translator fallback/runtime switch
- technique registry registration/duplicate/unknown/switch
- dummy technique integration
- controller import
- metadata formatter raw/processed/unknown
- status events
- generic shell / dummy panels
- EPR ASC import
- EPR BES3T import（本地文件存在时）
- raw plotting
- explicit baseline/Savgol
- undo/redo/reset
- invalid parameter status
- import failure status
- language switching labels/legend/status
- settings persistence
- architecture boundaries
- legacy GUI/M6 CLI importability

实际运行：

```text
完整测试集 pytest -v：
523 passed, 1 skipped
exit code 0

pytest -q -W error::UserWarning：
523 passed, 1 skipped
exit code 0

原 EPR 测试集（排除 M0–M8 测试）：
298 passed, 1 skipped
exit code 0
```

日志：

- `results/logs/pytest_m8_20261102_verbose.txt`
- `results/logs/pytest_m8_20261102_userwarning.txt`
- `results/logs/pytest_m8_20261102_original.txt`

---

## 13. 向后兼容

- 旧 `epr_workflow` 全部代码未修改；
- 旧 GUI、Plot Editor、preprocessing、CLI、batch、export 未修改；
- 旧测试未修改；
- 原 EPR 测试 298 passed / 1 skipped；
- M6 generic CLI 行为未改变；
- M1–M7 公共 API 未修改；
- 新 GUI 入口独立：
  - `python -m spectralab.app.gui`
- 删除新增 GUI 模块即可回滚。

---

## 14. 剩余技术债与风险

1. 新 GUI 不是旧 GUI 的功能等价重写；没有 Plot Editor、批处理 UI、processed export 或 preview。
2. EPR panel 目前只提供简化 baseline/Savgol 操作；没有 raw-input reorder。
3. EPR panel 放在 app 层，而不是 `techniques/epr/gui`，是为了让 EPR backend
   保持 Qt-free；未来技术面板需要由 composition root 注册。
4. GUI 设置只覆盖语言、活动技术、窗口大小；没有迁移旧 `gui_settings.ini`。
5. 没有 GUI 文件菜单、最近文件、导出对话框或多窗口。
6. 新 GUI canvas 没有旧 GUI 的 Matplotlib toolbar、CJK 字体策略或光标读数。
7. Metadata formatter 是技术无关文本表示，不是完整 provenance 序列化。
8. 没有 FTIR、FTIR GUI、多谱比较、DEER、脉冲 EPR 或二维模型。
9. GUI 错误显示英文异常原文；通用 shell 的标签/状态翻译已本地化，科学错误原文
   保留英文用于记录。
10. 旧应用和新应用并存，尚未统一设置、i18n 或窗口行为。

---

## 15. M8 完成清单

- [x] Generic Main Window
- [x] Qt-free Application Controller
- [x] Technique Panel Registry
- [x] stable panel protocol
- [x] explicit registration
- [x] duplicate/unknown technique errors
- [x] technique switching
- [x] dummy technique test
- [x] EPR technique registration
- [x] EPR ASC import
- [x] EPR BES3T import
- [x] Spectrum1D display
- [x] M5 raw plotting
- [x] M4 ProcessingSession access
- [x] explicit baseline/Savgol/undo/redo/reset UI
- [x] generic metadata view
- [x] status/error view
- [x] JSON settings service
- [x] Chinese/English + fallback
- [x] runtime language switching
- [x] no legacy GUI modification
- [x] no `epr_workflow` runtime import in SpectraLab
- [x] core remains Qt-free
- [x] no new dependencies
- [x] original EPR 298 passed / 1 skipped
- [x] full suite 523 passed / 1 skipped
- [x] `-W error::UserWarning` 通过
- [x] 未 commit、未 push、未开始 M9

**M8 状态：完成。** M9 尚未开始。
