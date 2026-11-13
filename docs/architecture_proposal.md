# SpectraLab 架构提案

- 状态：**架构方向已批准；M0–M15 已完成；M16 尚未开始**
- 基线：EPR Workflow **v0.2.0**，提交 `327d5f6`
- 日期：2026-11-02
- 范围：评估现有 EPR Workflow，提出可复用的科学光谱平台架构，并规划 FTIR 作为第二个技术模块
- M0 结果：见 [M0 基线报告](m0_baseline_report.md)
- M1 结果：见 [M1 Spectrum1D 报告](m1_spectrum1d_report.md)
- M2 结果：见 [M2 Importer 注册表报告](m2_importer_registry_report.md)
- M3 结果：见 [M3 通用导出报告](m3_export_report.md)
- M4 结果：见 [M4 通用处理报告](m4_processing_report.md)
- M5 结果：见 [M5 通用绘图报告](m5_generic_plotting_report.md)
- M6 结果：见 [M6 通用 CLI/Batch 报告](m6_cli_batch_report.md)
- M7 结果：见 [M7 EPR Backend Closure 报告](m7_epr_backend_closure_report.md)
- M8 结果：见 [M8 GUI Architecture 报告](m8_gui_architecture_report.md)
- M9 结果：见 [M9 FTIR Importer 报告](m9_ftir_importer_report.md)
- M10 结果：见 [M10 FTIR GUI 报告](m10_ftir_gui_report.md)
- M11 结果：见 [M11 Maintenance & Normalization 报告](m11_maintenance_and_normalization_report.md)
- M12 结果：见 [M12 FTIR Baseline 报告](m12_ftir_baseline_report.md)
- M12.1 审计：[M12.1 Baseline Audit](m12_1_baseline_audit_report.md)
- M12.2 修复：[M12.2 Baseline Remediation](m12_2_baseline_remediation_report.md)
- M13 结果：见 [M13 FTIR Peak Picking 报告](m13_ftir_peak_picking_report.md)
- M0–M13 只新增中立核心、EPR backend、通用导出/处理/绘图/CLI、GUI shell、
  FTIR 文本导入、GUI 原始谱显示、显式归一化/基线校正与峰值检测，不修改
  现有 `epr_workflow` 应用代码、现有测试、配置或项目身份；不安装依赖，
  不 commit、不 push

现有 v0.2.0 功能必须继续工作：ASC 导入、BES3T 导入、GUI/CLI、批处理、
Plot Editor、线性基线校正、Savitzky–Golay 平滑、CSV/PNG/JSON 导出、
中英文界面、数据校验与 SHA-256 来源记录。

---

## 1. 当前架构评估

### 1.1 模块清单与职责

| 模块 | 当前职责 | 直接依赖 | Qt 依赖 | 复用判断 |
| --- | --- | --- | --- | --- |
| `plot_asc.py` | ASC 读取、校验、绘图、CLI、批处理、基础元数据、路径保护 | NumPy、Pandas、Matplotlib | 否 | 部分可复用；同时承担了过多职责 |
| `bes3t.py` | BES3T DSC/DTA 严格读取、配对、轴构造、来源信息 | `plot_asc.ImportResult`、NumPy、Pandas | 否 | 读取逻辑强 EPR 专用；错误码与严格校验模式可复用 |
| `preprocessing.py` | 基线校正、Savitzky–Golay、预处理会话、记录 | NumPy、SciPy、`epr_workflow.__version__` | 否 | 会话/预览/撤销模式可复用；科学语义强绑定 `field_G` 与 EPR 词汇 |
| `plot_settings.py` | 曲线样式、轴设置、绘图函数、每样品样式缓存 | `preprocessing`、NumPy | 否 | 渲染机制可复用；曲线键与默认标签 EPR 专用 |
| `plot_export.py` | 独立 Agg PNG 导出、原子写入、路径保护 | `plot_asc`、`plot_settings`、Matplotlib | 否 | 导出机制可复用；来源路径参数仍偏 EPR |
| `processed_export.py` | 处理结果 CSV/PNG/JSON 导出 | `plot_asc`、`preprocessing`、Matplotlib | 否 | 模式可复用；列名、标题、假设 EPR 专用 |
| `gui/controller.py` | GUI 无关加载/batch/会话存储 | `plot_asc`、`preprocessing`、`i18n` | 否 | 分层思路可复用；`SpectrumView` 与 `PreprocessingStore` 强 EPR 化 |
| `gui/main_window.py` | 单窗口 UI、批处理、预处理、绘图、导出 | 控制器、i18n、所有面板、导出器 | 是 | 整体 EPR 专用；窗口壳、语言切换、布局可复用 |
| `gui/i18n.py` | 中英文扁平字典、状态翻译 | 无 | 否 | 机制可复用；键空间未按技术/模块隔离 |
| `gui/preprocessing_panel.py` | EPR 基线窗口/Savitzky 控件 | Qt、`preprocessing` | 是 | EPR 专用 |
| `gui/plot_editor_panel.py` | 曲线/轴样式面板 | Qt、`plot_settings` | 是 | 控件模式可复用；曲线键 EPR 专用 |
| `gui/plot_export_dialog.py` | PNG 尺寸/DPI/标题/图例设置 | Qt、`plot_export` | 是 | 基本通用 |
| `gui/mpl_canvas.py` | Qt 内嵌 Matplotlib 画布与 CJK 字体 | Qt、Matplotlib | 是 | 通用 |
| `gui/app.py`、`run_gui.py`、`gui/__main__.py` | GUI 启动入口 | Qt、主窗口 | 是 | 入口可复用；名称和默认设置需迁移 |
| `__init__.py` | 包级导出与版本号 | 上述核心模块 | 否 | 需增加兼容层 |

### 1.2 当前依赖关系

```text
epr_workflow.__init__
├── bes3t ───────────────► plot_asc (ImportResult, combine_source_hashes)
├── plot_asc
└── preprocessing (lazy package version)

plot_settings ─────────────► preprocessing
plot_export ───────────────► plot_asc, plot_settings
processed_export ──────────► plot_asc, preprocessing

gui.controller ────────────► plot_asc, preprocessing, i18n
gui.main_window ───────────► controller, i18n, panels,
                             plot_export, plot_settings,
                             processed_export, preprocessing
```

`plot_asc.read_dataset()` 通过函数内延迟导入 `bes3t`，避免 `bes3t` 与
`plot_asc` 的模块级循环依赖。核心导入链不依赖 Qt；GUI 依赖通过
`controller` 和面板隔离，但 `main_window.py` 仍直接依赖大量 EPR 语义。

### 1.3 当前数据模型

当前主数据流：

```text
ASC/BES3T
  -> ImportResult
       source, data(DataFrame: index, field_G, intensity),
       sha256, source_files, source_hashes,
       field_order, format_metadata, warnings
  -> SpectrumView (GUI)
       source, data, n_points, field_min, field_max,
       signal statistics, sha256, source_format
  -> PreprocessingSession
       field_G, intensity, source_sha256
  -> PreprocessingResult
       field_G, intensity_raw, intensity_processed,
       removed_baseline, steps, last_fit, field_direction
  -> PlotSettings / build_curves / draw_spectrum
  -> processed_export / plot_export
```

`ImportResult` 已有可选的 `source_format`、`source_files`、`source_hashes`、
`sha256_definition`、`format_metadata`、`format_assumptions`，说明现有实现
已经在向通用来源模型靠拢，但它仍然是 ASC 列结构 + EPR 字段的组合：

- 固定列名 `index`、`field_G`、`intensity`；
- 轴单位没有独立对象，Gauss 语义散落在字段名、标签和元数据文本中；
- `field_order` 是字符串，不是明确的轴方向/坐标语义；
- ASC 专用计数字段（缺失列、重复磁场、索引连续性）与通用导入结果混在一起；
- 原始/处理后数据分离只存在于 `PreprocessingResult`；
- 仪器元数据、未知元数据、缺失原因没有统一表示；
- 来源信息、格式信息、假设和诊断分散在 `ImportResult`、`build_metadata`、
  `preprocessing` 记录和 GUI 渲染代码中；
- `SpectrumView` 是 GUI 展示模型，不应成为跨技术核心模型。

### 1.4 当前导入器架构

- `read_asc()`、`read_bes3t()` 是两个独立函数；
- `read_dataset()` 按扩展名分派 `.ASC` 与 `.DSC`，并显式拒绝 `.DTA`；
- 批处理通过 `discover_dataset_files()` 扫描 `.ASC`/`.DSC`；
- GUI 文件过滤器硬编码支持扩展名；
- 错误模型不统一：ASC 使用 `AscFormatError`/`AscDataError`，BES3T 使用带
  `code`/`context` 的 `Bes3tError`；
- 多文件数据集只在 BES3T 内部处理（DSC + DTA），没有通用
  `SourceBundle`/`DatasetDescriptor`；
- 没有 importer 注册表、probe、选项对象或格式版本协商；
- 仪器元数据以自由字典 `format_metadata` 存放；
- `build_metadata()` 仍以 ASC 假设为默认分支。

### 1.5 当前绘图、处理与导出架构

**绘图**

- `plot_settings.draw_spectrum()` 是 GUI 预览和 PNG 导出的共同渲染器，这是
  现有架构最好的复用点之一；
- `build_curves()`/`CurveData` 把原始、处理、差异、拟合基线组织成曲线；
- 但曲线键是固定的 `raw`/`processed`/`difference`/`fitted_baseline`；
- `PlotSettingsStore` 以源路径 + SHA 为键，适合单样品、单数据集；
- 不支持多谱叠加、差谱集合、二维谱图或复杂信号；
- 轴标签默认为磁场/强度，`draw_spectrum()` 的语义通过调用方文本注入，
  但曲线键和默认标签仍是 EPR 专用。

**处理**

- `PreprocessingSession` 的设计质量较高：构造时复制数组、设为只读、
  预览不提交、按步骤重算、缓存结果、SHA 不匹配时失效；
- Savitzky–Golay 是通用数值算法；
- 线性基线在数学上可用于一般 x-y 光谱，但当前变量名、窗口单位、
  警告文本、R²/外推诊断和导出记录都绑定 `field_G`；
- 每个处理步骤记录算法、版本、参数、输入来源、时间、诊断，具备可追溯性；
- 没有归一化、峰检测、差谱、谱图集合、多项式/橡胶带基线等；
- 操作集合由 `BASELINE_OPERATION`、`SAVGOL_OPERATION` 硬编码，
  没有通用操作注册表。

**导出与来源**

- 路径保护、`data/raw` 禁止写入、源文件覆盖保护、原子 PNG 写入已经成熟；
- `build_metadata()`、`processed_export`、`plot_export` 都记录来源和假设；
- 但 CSV 列、JSON 字段、标题、假设文本强 EPR 化；
- 来源记录不是单一对象，跨模块重复拼接；
- 一个数据集的多文件来源只在 BES3T 分支完整；
- 没有 schema 版本、技术模块级导出扩展点或多技术谱图集合导出。

### 1.6 当前 GUI 与 CLI

- GUI 由单个 `MainWindow` 持有加载、批处理、预处理、绘图、导出和状态；
- 文件过滤器、面板、元数据文本、曲线语义和错误翻译均 EPR 专用；
- `i18n.py` 是扁平键空间，无技术命名空间；所有键在两个语言中必须一致；
- `controller.py` 提供了 Qt 无关层，但 `SpectrumView` 仍假设 `field_G`；
- CLI 入口是 `plot_asc.main()`，批处理和单文件共享 EPR 输出命名；
- `run_gui.py` 和 `gui.__main__` 是 GUI 入口；
- `PROJECT_ROOT`、默认 `data/raw`、`results`、`config/gui_settings.ini` 等路径
  仍由 EPR 项目和 GUI 直接假设，未抽象为应用上下文；
- 没有通用 `spectralab` CLI、技术子命令或 importer 选择机制；
- 没有插件加载、技术模块注册或独立技术配置。

### 1.7 现有测试与回归风险

当前基线（v0.2.0）为 **298 passed, 1 skipped**。测试覆盖：

- ASC 读取、校验、CSV/JSON/PNG、批处理、来源哈希；
- BES3T 合成与真实样本、截断/尾随字节、复数/多维拒绝；
- 预处理、Savitzky–Golay、导出、Plot Editor；
- GUI 离屏测试、双语切换、错误翻译、文件对话框；
- 源文件不可变性和输出覆盖保护。

主要回归风险：

1. **精确字符串耦合**：GUI 测试断言窗口标题、按钮文本、标签、错误消息；
2. **JSON/CSV 结构耦合**：字段名、列顺序、假设文本、批量记录键集合；
3. **GUI 内部耦合**：测试直接访问 `_current_view`、`_session`、`_plot_settings`
   等私有状态；
4. **输出命名与路径耦合**：`_raw`、`_baseline`、`_plot`、figures/tables/logs；
5. **科学假设耦合**：Gauss、磁场方向、基线窗口、强度单位；
6. **没有架构契约测试**：目前没有测试保证“核心不导入 Qt”“技术模块不反向
   依赖 GUI”“新旧模型数值等价”。

因此迁移必须先用测试固定现有行为和数值，再移动代码。

---

## 2. 目标架构

### 2.1 设计原则

1. **核心与 GUI 分离**：核心不得导入 Qt；GUI 只消费模型、操作和渲染接口。
2. **核心与具体技术分离**：核心不导入 `epr` 或 `ftir`；技术模块向核心注册。
3. **科学数据不可变**：原始数组复制后只读；处理生成新结果，不原地修改。
4. **显式元数据**：未知就是未知；不填充默认单位、默认轴类型或默认信号语义。
5. **显式转换**：任何单位换算、轴反转、排序、插值、归一化都必须是用户可见、
   参数化、记录在案的操作；默认不执行。
6. **格式显式分派**：扩展名只是候选，必须 probe；多个候选要求显式选择。
7. **可追溯**：来源文件、哈希、解析参数、假设、诊断、处理历史和软件版本统一记录。
8. **不引入新依赖**：优先使用现有 NumPy/SciPy/Pandas/Matplotlib/PySide6 与
   Python 标准库；新依赖需单独论证和批准。
9. **渐进兼容**：旧包名、旧导入路径、旧 CLI 和旧 GUI 在迁移期保留。
10. **只实现需要的抽象**：近期的核心模型只实现 `Spectrum1D`；复数/二维先用
    接口与数据契约占位，不提前实现。

### 2.2 分层

```text
┌─────────────────────────────────────────────────────────────┐
│ app/                                                        │
│ CLI、批处理编排、GUI 主窗口、设置持久化、语言选择          │
└──────────────────────────────┬──────────────────────────────┘
                               │ 依赖接口，不依赖具体技术实现
┌──────────────────────────────▼──────────────────────────────┐
│ techniques/                                                 │
│ epr/：ASC/BES3T 导入、EPR 语义、默认绘图/导出/预置处理      │
│ ftir/：CSV/TXT 导入、波数/吸光度/透过率语义、FTIR 预置       │
└──────────────────────────────┬──────────────────────────────┘
                               │ 只依赖 core
┌──────────────────────────────▼──────────────────────────────┐
│ core/                                                       │
│ model（Axis1D/Signal1D/Spectrum1D/Provenance）              │
│ importers（协议/注册表/来源包）                             │
│ processing（会话/操作协议/通用算法）                        │
│ plotting（Series/Renderer/设置）                            │
│ export（CSV/JSON/PNG/路径保护/来源记录）                    │
│ i18n（错误码/翻译机制）                                     │
└─────────────────────────────────────────────────────────────┘
```

依赖方向必须是单向的：

```text
app -> techniques -> core
app -> core
core 不得导入 techniques、app、Qt
techniques 不得导入 app 或彼此
```

### 2.3 技术模块接口

每个技术模块实现一个明确的技术描述对象，而不是把所有逻辑塞入核心：

```python
class TechniqueModule(Protocol):
    id: str                       # "epr" / "ftir"
    display_name_key: str
    importers: tuple[Importer, ...]
    supported_models: tuple[type, ...]       # 近期只有 Spectrum1D
    default_plot_profile: str
    metadata_renderers: tuple[MetadataRenderer, ...]
    gui_panel_factories: tuple[PanelFactory, ...]
    export_profile: ExportProfile
```

技术模块可以注册：

- importer（ASC、BES3T、CSV、TXT）；
- 通用处理操作的默认参数与标签；
- 技术特有的信号语义/轴语义校验；
- 默认绘图配置（轴方向、坐标标签、颜色、图例）；
- 技术特有的元数据显示；
- 技术特有的 CSV/JSON 导出扩展字段；
- GUI 面板工厂。

核心只认识 `Spectrum1D`、`Importer`、`ProcessingOperation`、`Series1D`、
`ExportProfile` 等接口，不认识 EPR 的 `field_G` 或 FTIR 的 `cm^-1`。

### 2.4 错误与国际化边界

- 核心错误使用稳定 `code` + `context`，科学记录中保留英文原文；
- GUI/CLI 展示层按 code 翻译，不在核心硬编码中文；
- i18n 键按命名空间组织，例如 `core.error.unsupported_format`、
  `epr.error.companion_missing`、`ftir.error.column_mapping`；
- 技术模块提供自己的翻译条目，不修改全局 EPR 字典；
- 未翻译的错误显示 code/英文原文，不静默隐藏。

---

## 3. 建议目录结构

### 3.1 目标结构

```text
spectralab/
├── pyproject.toml                  # 以后引入；先不创建
├── src/
│   └── spectralab/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── errors.py
│       │   ├── model/
│       │   │   ├── __init__.py
│       │   │   ├── axis.py
│       │   │   ├── signal.py
│       │   │   ├── spectrum1d.py
│       │   │   ├── spectrum2d.py        # 占位/协议，近期不实现
│       │   │   ├── time_domain.py       # 占位/协议，近期不实现
│       │   │   ├── metadata.py
│       │   │   ├── provenance.py
│       │   │   └── collection.py        # 多谱集合，FTIR 比较需要
│       │   ├── importers/
│       │   │   ├── base.py
│       │   │   ├── registry.py
│       │   │   ├── sources.py
│       │   │   └── validation.py
│       │   ├── processing/
│       │   │   ├── base.py
│       │   │   ├── session.py
│       │   │   ├── records.py
│       │   │   └── operations/
│       │   │       ├── savgol.py
│       │   │       ├── baseline_linear.py
│       │   │       ├── normalize.py
│       │   │       ├── difference.py
│       │   │       └── peaks.py
│       │   ├── plotting/
│       │   │   ├── series.py
│       │   │   ├── settings.py
│       │   │   ├── renderer.py
│       │   │   ├── canvas.py
│       │   │   └── export.py
│       │   ├── export/
│       │   │   ├── csv.py
│       │   │   ├── json.py
│       │   │   ├── paths.py
│       │   │   └── provenance.py
│       │   └── i18n/
│       │       ├── base.py
│       │       └── catalog.py
│       ├── techniques/
│       │   ├── epr/
│       │   │   ├── __init__.py
│       │   │   ├── technique.py
│       │   │   ├── importers/
│       │   │   │   ├── xepr_asc.py
│       │   │   │   └── bes3t.py
│       │   │   ├── semantics.py
│       │   │   ├── processing_defaults.py
│       │   │   ├── plotting_defaults.py
│       │   │   ├── export_profile.py
│       │   │   ├── i18n_zh.py / i18n_en.py
│       │   │   └── gui/
│       │   │       ├── preprocessing_panel.py
│       │   │       └── plot_editor_panel.py
│       │   └── ftir/
│       │       ├── __init__.py
│       │       ├── technique.py
│       │       ├── importers/
│       │       │   ├── generic_csv.py
│       │       │   └── generic_txt.py
│       │       ├── mapping.py
│       │       ├── semantics.py
│       │       ├── processing_defaults.py
│       │       ├── plotting_defaults.py
│       │       ├── export_profile.py
│       │       ├── i18n_zh.py / i18n_en.py
│       │       └── gui/
│       │           ├── import_panel.py
│       │           ├── processing_panel.py
│       │           └── plot_panel.py
│       └── app/
│           ├── cli.py
│           ├── batch.py
│           ├── registry.py             # 加载技术模块
│           └── gui/
│               ├── main_window.py
│               ├── controller.py
│               ├── metadata_view.py
│               └── settings.py
├── tests/
│   ├── core/
│   ├── techniques/epr/
│   ├── techniques/ftir/
│   └── app/
└── docs/
    └── architecture_proposal.md
```

### 3.2 过渡结构（推荐实际采用）

迁移期间保留旧包与旧入口：

```text
src/
├── epr_workflow/                  # 旧包，保持可导入、可运行
│   ├── plot_asc.py                # 旧 API 适配器/兼容层
│   ├── bes3t.py                   # 旧 API 适配器/兼容层
│   ├── preprocessing.py           # 旧 API 适配器/兼容层
│   ├── plot_settings.py
│   ├── plot_export.py
│   ├── processed_export.py
│   └── gui/                       # 旧 GUI，保持工作
└── spectralab/                    # 新核心与新技术模块
    ├── core/
    ├── techniques/epr/            # 包装旧实现，逐步迁移
    ├── techniques/ftir/           # 新实现
    └── app/
```

兼容规则：

- `epr_workflow` 在至少一个次版本周期内仍是有效导入路径；
- 旧函数签名和返回对象暂不改变；
- 新架构通过适配器读取旧 `ImportResult` 和旧 `PreprocessingResult`；
- 只有在数值等价测试通过后才迁移内部实现；
- 项目根目录、包名、GUI 标题、GitHub 仓库名在当前阶段全部保持原样。

---

## 4. Spectrum1D 数据模型规范

### 4.1 设计目标

`Spectrum1D` 必须表达“一条一维光谱 + 一个自变量轴 + 一个因变量信号”，
而不是把 EPR 的字段名硬编码进核心。

它需要同时支持：

- 磁场 (G)、波数 (cm⁻¹)、波长 (nm)、频率 (Hz)、时间、索引等轴；
- 强度、吸光度、透过率、一阶导数、任意单位等信号；
- 递增与递减轴；
- 原始点序；
- 原始数据与处理结果的严格分离；
- 仪器/采集/样品元数据；
- 未知/缺失元数据的显式表示；
- 来源、假设、诊断、处理历史。

### 4.2 建议类型

以下为**接口草案**，不是本次实现：

```python
AxisDirection = Literal["increasing", "decreasing", "unknown"]
AxisQuantity = Literal[
    "magnetic_field", "wavenumber", "wavelength", "frequency",
    "time", "index", "unknown"
]
SignalSemantics = Literal[
    "intensity", "absorbance", "transmittance",
    "first_derivative", "unknown"
]

@dataclass(frozen=True)
class Axis1D:
    values: np.ndarray                 # 只读 float64，保持原始顺序
    name: str | None                   # 例如 "Magnetic field" / "Wavenumber"
    unit: str | None                   # 例如 "G" / "cm^-1" / None
    quantity: AxisQuantity             # 明确物理量；unknown 不冒充已知量
    direction: AxisDirection           # 从原值检查得到，不排序
    metadata_source: str               # "descriptor" / "user" / "inferred" / "unknown"
    missing_reason: str | None = None

@dataclass(frozen=True)
class Signal1D:
    values: np.ndarray                 # 只读 float64；原始或处理后的一个通道
    name: str | None                   # 例如 "Intensity" / "Absorbance"
    unit: str | None                   # 例如 "AU" / None；不虚构
    semantics: SignalSemantics         # 明确信号语义；unknown 时不标签化
    metadata_source: str
    missing_reason: str | None = None

@dataclass(frozen=True)
class SourceFile:
    role: str                          # "descriptor" / "data" / "spectrum"
    path: Path
    sha256: str
    size_bytes: int
    format_id: str

@dataclass(frozen=True)
class Provenance:
    importer_id: str
    importer_version: str
    imported_at_utc: str
    source_files: tuple[SourceFile, ...]
    software_versions: Mapping[str, str]
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]
    diagnostics: Mapping[str, Any]
    format_metadata: Mapping[str, Any]
    sha256_definition: str

@dataclass(frozen=True)
class SpectrumMetadata:
    technique: str
    title: str | None
    instrument: Mapping[str, Any]       # 未知字段不填充
    acquisition: Mapping[str, Any]
    sample: Mapping[str, Any]
    technique_metadata: Mapping[str, Any]  # 技术专用元数据，如 FTIR acquisition_mode
    extra: Mapping[str, Any]
    unknown_fields: tuple[str, ...]     # 明确列出缺失项
    metadata_origin: Mapping[str, str]  # 每个字段的来源

@dataclass(frozen=True)
class Spectrum1D:
    dataset_id: str
    axis: Axis1D
    raw_signal: Signal1D
    metadata: SpectrumMetadata
    provenance: Provenance
    # 不在此处放 processed；处理结果是独立派生对象
```

`technique_metadata` 用于放置技术专用、且核心不应理解的元数据。例如 FTIR 的
`acquisition_mode`（ATR/Transmission/Unknown）与 `atr_correction_status`
（applied/not_applied/not_applicable/unknown）由 FTIR 技术模块定义和校验，
核心只负责原样保存与导出，不推断、不补默认值。

处理结果建议使用独立对象，避免“原始/处理”混淆：

```python
@dataclass(frozen=True)
class ProcessedSpectrum:
    raw: Spectrum1D
    signal: Signal1D                   # 当前处理结果
    history: tuple[ProcessingRecord, ...]
    warnings: tuple[str, ...]
    is_preview: bool = False
```

### 4.3 不变量

1. `axis.values` 与 `raw_signal.values` 长度相等，且一维。
2. `axis.values` 与 `raw_signal.values` 复制后设为只读；构造后不可原地修改。
3. 原始点顺序不排序、不去重、不插值；`direction` 只描述，不改变数据。
4. 原始信号在 `Spectrum1D.raw_signal`；处理结果在 `ProcessedSpectrum.signal`，
   永远不回写 `raw_signal`。
5. 未知元数据使用 `None`/`unknown` + `missing_reason` + `unknown_fields`，
   不使用猜测值；JSON 中不得把 `None` 变成“0”或默认单位。
6. 轴方向与绘图方向分离：数据方向来自来源；显示方向是绘图设置，必须显式记录。
7. 同一次导入中所有数组使用统一 dtype（建议 float64）；原始整数/float32 的
   来源类型记录在 `format_metadata` 中，不丢失。
8. 任何转换（单位、方向、排序、插值、归一化）都必须是显式操作并写入历史。
9. 采集模式、信号语义、ATR 校正状态只作为显式元数据保存；不从文件扩展名、
   数值范围或 Absorbance/Transmittance 语义推断。

### 4.4 EPR 适配方式

ASC 适配：

- `Axis1D.quantity="magnetic_field"`，`name` 来自表头/`"Magnetic field"`，
  `unit="G"`，方向由现有单调性检查得到；
- `Signal1D.name="Intensity"`，`unit=None`（original/arbitrary），
  `semantics="unknown"`，因为当前程序不区分吸收谱/一阶导数谱；
- 第 1 列 `index` 只保留为来源行号/诊断，不作为物理轴；
- `ImportResult` 的 `source_hashes`、`format_metadata`、`warnings` 映射到
  `Provenance`；现有 CSV/JSON 输出由适配器继续生成，数值不变。

BES3T 适配：

- `Axis1D.quantity="magnetic_field"`，`unit="G"`，轴值仍使用
  `linspace(XMIN, XMIN+XWID, XPTS)`，端点包含，不重新采样；
- `Signal1D` 使用解码后的 float64 值；原始 `IRFMT`/`BSEQ`/`IKKF` 放在
  `Provenance.format_metadata`；
- DSC/DTA 两个 `SourceFile` 进入 `Provenance.source_files`；
- `format_id="bes3t"`，importer 版本记录在 `Provenance`。

兼容策略：

- 新 importer 在内部调用旧 `read_asc()`/`read_bes3t()` 或共享解析函数；
- 适配器把旧 `ImportResult` 转为 `Spectrum1D`，逐数组比较；
- 旧 API 继续返回旧 `ImportResult`，直到所有调用方迁移；
- 不得为了模型统一改变任何数值、轴端点、dtype 语义或 CSV/JSON 科学字段。

### 4.5 未来模型

不要求现在实现，但接口上不能堵死：

- `ComplexSignal`/`TimeDomainSignal`：复数数组、实部/虚部、时间轴、回波/相位、
  采集窗；不得强行塞入 `Spectrum1D` 的实数 `Signal1D`。
- `Spectrum2D`：两个独立轴 + 二维信号矩阵 + 切片/等高线元数据；不得把二维
  数据拉平成一维“光谱”。
- `SpectrumCollection`：多个 `Spectrum1D`/`ProcessedSpectrum` 的集合，用于
  FTIR 多谱比较、差谱和批量绘图；集合成员保留各自来源和历史。

---

## 5. 导入器接口规范

### 5.1 协议

```python
class Importer(Protocol):
    id: str
    version: str
    technique: str
    entry_suffixes: tuple[str, ...]

    def probe(self, entry: Path) -> ProbeResult: ...
    def collect_sources(self, entry: Path) -> tuple[SourceFile, ...]: ...
    def read(self, request: ImportRequest) -> ImportedDataset: ...
```

`ProbeResult`：

```python
@dataclass(frozen=True)
class ProbeResult:
    supported: bool
    confidence: float          # 0..1，仅用于排序；不替代显式选择
    format_id: str
    technique: str | None
    reason: str | None
```

`ImportRequest`：

```python
@dataclass(frozen=True)
class ImportRequest:
    entry: Path
    companions: Mapping[str, Path] = ...
    technique_hint: str | None = None
    options: Mapping[str, Any] = ...
    allow_ambiguous: bool = False
```

FTIR 的 `options` 将包含 `FTIRImportOptions`：列映射、采集模式、ATR 校正状态、
信号语义、分隔符/小数点/表头等。importer 不得从扩展名推断采集模式或校正状态；
无法确定时保留 `unknown` 或要求显式输入。

`ImportedDataset`：

```python
@dataclass(frozen=True)
class ImportedDataset:
    spectra: tuple[Spectrum1D, ...]
    primary_index: int
    format_id: str
    technique: str
    warnings: tuple[str, ...]
    diagnostics: Mapping[str, Any]
```

### 5.2 注册与选择

```python
class ImporterRegistry:
    def register(self, importer: Importer) -> None: ...
    def candidates(self, entry: Path) -> tuple[ProbeResult, ...]: ...
    def select(self, entry, *, technique=None, format_id=None) -> Importer: ...
```

规则：

- 扩展名只用于缩小候选范围，不单独决定格式；
- 多个 importer 同时 probe 成功时，要求 `technique_hint` 或 `format_id`，
  否则抛出 `AmbiguousFormatError`；
- 没有候选时抛出 `UnsupportedFormatError`，列出支持的格式和入口要求；
- 不允许“尝试读取直到成功”的静默回退；
- 注册表在应用启动时由 `app.registry` 加载技术模块；
- 核心不硬编码 `.ASC`/`.DSC`/`.CSV` 列表。

### 5.3 多文件与伴随文件

- `collect_sources()` 负责识别 DSC+DTA、可能的轴文件、未来多文件数据集；
- 返回的 `SourceFile` 必须包含角色（descriptor/data/axis/...）；
- 缺失或歧义伴随文件由 importer 抛出带 code 的错误；
- 文件配对规则写进 importer 文档和测试，不靠文件名猜测；
- 批处理只把每个数据集的入口文件传给注册表，绝不会把 `.DTA` 当成独立数据集。

### 5.4 错误模型

```python
class ImportFailure(ValueError):
    code: str
    context: Mapping[str, Any]
    severity: Literal["error", "warning"]
```

- 格式缺失、元数据矛盾、截断、尾随字节、不支持复杂度/维度：error；
- 非致命诊断（例如整数强度转为 float64、DSRC 非 EXP）：warning；
- importer 不输出中文/英文用户文案，只输出稳定 code 与英文消息；
- 展示层使用 `core.i18n` + 技术模块翻译表；
- 科学记录保留英文原文、code、context。

### 5.5 现有导入器如何适配

| 新接口 | 现有实现 | 适配方式 |
| --- | --- | --- |
| `XeprASCImporter` | `read_asc()`、`plot_asc._process_one` 的 ASC 分支 | probe 检查三列表头；read 调用旧解析；适配到 `Spectrum1D`；保留旧 `ImportResult` |
| `BES3TImporter` | `read_bes3t()`、`find_companion_dta()` | probe 检查 `#DESC`；collect_sources 返回 DSC/DTA；read 适配轴与来源 |
| `GenericCSVImporter` | 无 | 新实现；必须提供列映射、分隔符、单位；不自动判断吸光度/透过率 |
| `GenericTXTImporter` | 无 | 新实现；空白/Tab/自定义分隔符，注释行与列映射显式化 |

`read_asc()`、`read_bes3t()`、`read_dataset()` 在过渡期保留为兼容入口，
内部可以委托新 importer；不得改变其现有返回值和数值行为。

---

## 6. 共享与技术专用功能矩阵

| 功能 | 当前状态 | 可复用性 | 需要的变化 | 风险 |
| --- | --- | --- | --- | --- |
| 源文件哈希/路径保护/原子写入 | EPR 导出中成熟 | **高** | 抽到 `core.export`/`core.sources` | 中：路径语义、DSC/DTA 多源 |
| 只读数组/复制/预览/撤销 | `PreprocessingSession` 成熟 | **高** | 用 `Axis1D` 替代 `field_G`，保留事务语义 | 高：处理记录和 GUI 依赖旧名 |
| Savitzky–Golay | 已实现 | **高** | 参数与轴解耦，保留同一 SciPy 调用 | 低 |
| 线性基线 | 已实现但 EPR 化 | **中高** | 通用 x 轴/窗口；算法本身不变 | 高：窗口单位、诊断、记录 |
| 归一化 | 未实现 | **新核心通用** | 设计显式方法（min-max/area/vector 等） | 高：方法选择、可逆性、记录 |
| 峰检测 | 未实现 | **新核心通用** | `scipy.signal.find_peaks` 参数化，极性显式 | 中高：峰极性/阈值/误标 |
| 差谱 | 未实现 | **新核心通用** | 轴对齐策略显式；默认拒绝不匹配轴 | 高：插值/对齐会改变科学数据 |
| 多谱比较 | 未实现 | **新核心通用** | `SpectrumCollection` + overlay 渲染 | 中：颜色/图例/性能 |
| 绘图渲染/PNG 导出 | 已实现 | **高** | `Series1D` 取代固定曲线键；保留 Matplotlib | 中：曲线键和默认标签 |
| 轴设置/颜色/字体 | 已实现 | **高** | 通用轴标签/单位；技术默认值 | 低 |
| CSV/JSON 导出框架 | 已实现 | **中高** | 技术 `ExportProfile` 决定列/schema | 高：旧 schema 兼容 |
| i18n 机制 | 已实现 | **高** | 命名空间 + 模块翻译表 | 中：扁平键迁移 |
| GUI 壳/画布/工具栏 | 已实现 | **高** | 保留，增加技术面板注册 | 中：MainWindow 拆分 |
| EPR ASC/BES3T 解析 | 已实现 | **技术专用** | 包装为新 importer，不改数值 | 高：回归基线 |
| EPR 曲线键/默认标签 | 已实现 | **技术专用** | 放进 `techniques/epr` | 中：Plot Editor 测试 |
| EPR 基线窗口/G 语义 | 已实现 | **技术专用** | 保留在 EPR 模块；核心用通用轴 | 高：科学假设 |
| FTIR 波数/吸光度/透过率 | 未实现 | **技术专用** | `techniques/ftir` 语义与映射 | 高：单位/语义错误 |
| FTIR 默认绘图方向 | 未实现 | **技术专用** | 技术默认配置，用户可改 | 中：不反转数据 |

“多个文件都 import 它”不等于通用。例如 `i18n` 被很多模块使用，但其键空间目前
完全是 EPR 语义；`plot_asc` 被 GUI 和 CLI 共用，但它同时包含 EPR 导入、绘图、
批处理和路径策略。迁移时应按职责拆分，而不是按使用次数判断。

---

## 7. EPR 迁移计划

迁移原则：每个阶段都保持 Windows + Python 3.11.9 + 当前 `.venv` 可运行；
不新增依赖；每一步都保留旧入口和旧测试；只有在前一阶段门禁通过后才进入下一阶段。
不得采用一次性重写。

### 阶段 0：冻结基线与回归测试

- 固定 v0.2.0 提交 `327d5f6`；
- 为 ASC/BES3T 合成样本和真实样本保存数值基线；
- 为 CSV/JSON 输出保存规范化快照（去掉时间戳/绝对路径）；
- 为批处理记录键集合、GUI 文本、错误码建立契约测试；
- 记录当前测试基线：298 passed, 1 skipped；
- 添加“核心不导入 Qt”“技术模块不导入 app”的导入图测试。

**门禁：** 新测试在旧代码上全部通过，且不依赖人工视觉。

### 阶段 1：并行引入核心模型与适配器

- 新增 `core.model`（`Axis1D`、`Signal1D`、`Spectrum1D`、`Provenance`）；
- 新增 `legacy_adapter`，把现有 `ImportResult` 转成 `Spectrum1D`；
- 不改变任何现有调用方；
- 对 ASC/BES3T 每个样本做数组逐值比较和元数据映射测试。

**门禁：** 新模型转换不改变任何数值、轴端点、来源哈希和现有 JSON/CSV。

### 阶段 2：导入器协议与注册表

- 新增 `Importer`、`ProbeResult`、`ImportRequest`、`ImportedDataset`；
- 新建 `XeprASCImporter`、`BES3TImporter`，内部委托现有解析；
- 新注册表只供新 CLI/GUI 使用；旧 `read_dataset()` 保持；
- 探测失败/多候选/不支持格式的错误有明确 code。

**门禁：** 旧导入入口结果不变；新入口与旧入口逐值等价。

### 阶段 3：通用处理会话

- 新增 `core.processing.ProcessingSession` 外观，接受 `Axis1D` + `Signal1D`；
- 内部复用现有 `PreprocessingSession` 的复制/只读/预览/撤销/缓存模式；
- 线性基线与 Savitzky–Golay 保留算法和记录字段；
- EPR 适配器提供 `field_G` 兼容属性/记录映射；
- 不增加归一化/峰检测到 EPR 默认 UI。

**门禁：** EPR 预处理测试全部通过；处理记录与旧 JSON 的科学字段一致。

### 阶段 4：通用绘图与导出

- 引入 `Series1D`/`RenderProfile`，把 `build_curves` 的固定键移到 EPR 技术模块；
- `draw_spectrum` 保留为兼容包装；
- PNG 导出使用通用 `Series1D`，继续使用相同 Matplotlib 渲染器；
- CSV/JSON 由技术 `ExportProfile` 决定列与字段；
- 旧 Plot Editor 仍工作，曲线键保持兼容。

**门禁：** 同一样本的旧/新 PNG 像素级或结构级一致（允许字体/元数据差异时
必须解释）；CSV/JSON 科学字段等价。

### 阶段 5：CLI 与批处理适配

- 新增 `spectralab.app.cli`，支持技术/格式/列映射参数；
- 保留 `plot_asc.py` 作为旧 CLI 入口；
- 批处理通过 importer 注册表发现入口，继续排除 DTA 等伴随文件；
- 输出命名先保持旧规则，再在独立版本中引入新规则。

**门禁：** 旧 CLI 命令与退出码不变；新 CLI 对同一输入产生等价 CSV/JSON/PNG。

### 阶段 6：GUI 模块化

- 拆出 GUI 壳（窗口、语言、设置、状态）；
- `MainWindow` 只负责组装技术面板和通用组件；
- EPR 面板包装现有 `preprocessing_panel`、`plot_editor_panel`；
- 文件过滤器、元数据渲染、错误翻译由技术模块提供；
- 保留旧 `MainWindow` 公共行为，测试逐步迁移到面板/控制器接口。

**门禁：** 现有 GUI 测试通过；关键流程（打开、批处理、预处理、Plot Editor、
语言切换、导出）在新旧实现上行为一致。

### 阶段 7：EPR 技术模块收口

- 把 ASC/BES3T importer、EPR 语义、默认绘图/导出、EPR i18n 全部移入
  `techniques/epr`；
- 旧 `epr_workflow` 保留适配器；
- 删除仅在新路径使用的重复代码前，先确认旧路径仍有测试。

**门禁：** 新 `spectralab` 与旧 `epr_workflow` 对同一 EPR 输入结果一致；
旧入口仍可用。

### 阶段 8：FTIR 模块

按第 8 节实现；在 EPR 回归门禁持续通过的前提下推进。

### 阶段 9：项目重命名

只有在以下条件全部满足后才建议改名：

1. EPR 功能在新核心上达到行为等价；
2. FTIR beta 至少覆盖导入、显示、基线/平滑、归一化、峰检测、差谱和导出；
3. `epr_workflow` 兼容导入路径、CLI 别名和 GUI 旧入口有明确保留周期；
4. 旧配置 `config/gui_settings.ini` 有迁移/回退方案；
5. 文档、README、GitHub 仓库说明和发布流程准备好。

建议顺序：

1. 先引入内部包名 `spectralab`，继续发布 `epr_workflow` 兼容包；
2. 增加 `spectralab` CLI/入口，保留旧 `plot_asc.py`、`run_gui.py`；
3. 发布一个同时记录新旧名称的过渡版本；
4. 最后再重命名 GitHub 仓库和产品名（GitHub 会保留旧 URL 重定向）；
5. 旧包名至少保留一个次版本，之后才考虑移除。

**当前不执行任何重命名。**

---

## 8. FTIR 开发计划

### 8.1 初始范围

只支持一维 FTIR/ATR-FTIR 光谱：

- 两列 CSV/TXT 导入；ATR-FTIR 导出默认按同一通用两列流程处理，前提是实际
  导出文件确认该结构；
- 用户显式指定 X/Y 列；
- X 轴为波数，单位 `cm^-1`；
- Y 轴为吸光度 (Absorbance) 或透过率 (Transmittance)；未确定时为 `unknown`；
- 采集模式：`ATR`、`Transmission` 或 `Unknown`；不得从扩展名推断；
- ATR 校正状态：`applied`、`not_applied`、`not_applicable` 或 `unknown`；
  未知时保持 `unknown`；
- 递增/递减波数轴均保留；
- 基线校正、Savitzky–Golay、归一化、峰检测、差谱、多谱比较。

第一版**不支持**：

- 二维 FTIR 成像/显微图谱；
- 独立的 ATR 文件解析器；
- ATR 校正、ATR 物理计算（折射率、穿透深度、有效光程等）；
- 自动判断吸光度/透过率或采集模式；
- 自动单位换算（如 µm ↔ cm⁻¹）；
- 自动大气补偿、Kramers–Kronig、导数谱、去卷积；
- 自动化学基团归属；
- 不匹配轴之间的静默插值/对齐；
- 任何未记录参数的自动处理。

### 8.2 导入与列映射

`GenericCSVImporter` / `GenericTXTImporter` 的显式选项：

```python
@dataclass(frozen=True)
class ColumnMapping:
    x: int | str
    y: int | str
    x_name: str | None
    x_unit: str | None
    y_name: str | None
    y_unit: str | None
    y_semantics: SignalSemantics
    header: bool
    delimiter: str | None
    comment: str | None

@dataclass(frozen=True)
class FTIRImportOptions:
    mapping: ColumnMapping
    acquisition_mode: AcquisitionMode       # atr / transmission / unknown
    atr_correction_status: ATRCorrectionStatus
                                            # applied / not_applied /
                                            # not_applicable / unknown
```

`AcquisitionMode` 与 `ATRCorrectionStatus` 属于 FTIR 技术元数据，存放在
`SpectrumMetadata.technique_metadata` 中，由 `techniques/ftir/semantics.py`
定义并校验；核心模型不导入 FTIR 模块。

规则：

- `x_unit` 第一版只接受 `cm^-1`；其他单位不静默换算，明确拒绝或要求用户先转换；
- `y_semantics` 必须由用户选择 `absorbance`、`transmittance` 或 `unknown`；
  不根据列名/数值范围猜测；
- `acquisition_mode` 必须由用户显式选择或保留 `unknown`；不得从文件扩展名
  或 Y 轴语义推断；
- `atr_correction_status` 必须由用户显式提供或保留 `unknown`；不得假设所有
  ATR 光谱已经校正；
- `x`/`y` 可用列索引或列名；缺失/重复/非数值列明确报错；
- 保留原始行顺序；递减轴不排序、不反转数据；
- 舍入/精度不在导入时改变；
- 多谱文件（宽表）第一版不自动拆分；如支持，必须显式声明每列为一个谱。

### 8.2a ATR-FTIR 元数据与处理边界

建议的 FTIR 技术元数据：

```python
AcquisitionMode = Literal["atr", "transmission", "unknown"]
ATRCorrectionStatus = Literal[
    "applied", "not_applied", "not_applicable", "unknown"
]

@dataclass(frozen=True)
class FTIRMetadata:
    acquisition_mode: AcquisitionMode
    atr_correction_status: ATRCorrectionStatus
    signal_semantics: SignalSemantics       # absorbance / transmittance / unknown
    axis_unit: str | None                   # 第一版仅 "cm^-1" 或 unknown
    source_metadata: Mapping[str, Any]
```

规则：

- 初版不实现独立 ATR 解析器；ATR 文件如果符合两列 CSV/TXT 结构，走同一
  importer；
- 采集模式与信号语义独立：`ATR` 不等于 `Absorbance`，`Transmission` 不等于
  `Transmittance`；
- 无法从文件确定时，`acquisition_mode`、`atr_correction_status`、
  `signal_semantics` 保留 `unknown`，或由用户显式输入；
- 不假设 ATR 校正已经发生；不自动做 ATR 校正；
- 未来 ATR 校正和物理计算（折射率、穿透深度、有效光程、偏振等）放在
  `techniques/ftir/processing/atr.py` 或独立 FTIR 处理模块中，必须有理论依据
  和真实样本验证，不能进入通用核心；
- ATR 校正状态、采集模式和所有相关假设写入 JSON 来源记录和导出假设。

### 8.3 轴与绘图方向

- `Axis1D.quantity="wavenumber"`，`unit="cm^-1"`；
- `direction` 从原始值检查，保留 `increasing`/`decreasing`；
- 绘图显示方向是独立设置，例如 `display_direction="high_to_low"`；
- 显示反转只改变绘制坐标/坐标轴方向，**不修改数组、行序、CSV 或来源哈希**；
- 导出记录必须写明显示方向与数据方向；
- 默认 FTIR 绘图方向建议高波数在左（与常见红外谱一致），但这是显示默认值，
  不是数据转换。

### 8.4 共享操作与 FTIR 专用操作

| 功能 | 归属 | 说明 |
| --- | --- | --- |
| CSV/TXT 解析、列映射 | 核心通用 | 所有技术可复用；FTIR 只提供默认预设/语义 |
| 线性基线 | 核心通用 | 通用 x/y；FTIR 默认区域/预设属于 FTIR |
| 多项式基线（阶数 2–5） | 核心通用 | 用户显式选择区域和阶数；FTIR 提供默认/标签 |
| 橡胶带基线 | FTIR 专用（未来） | v1.0 不实现；需单独科学审查 |
| Savitzky–Golay | 核心通用 | 同一 SciPy 算法；FTIR 默认窗口属于 FTIR |
| 归一化（Min-Max/最大绝对值/L2） | 核心通用 | 三种已批准方法；必须显式记录 |
| 峰检测 | 核心通用 | `find_peaks` 参数化；FTIR 提供参数/标签，不推断极性 |
| 差谱 | 核心通用 | 轴对齐校验；默认拒绝不匹配轴 |
| 多谱叠加 | 核心通用 | `SpectrumCollection`；不自动平均 |
| 波数单位/吸光度语义 | FTIR 专用 | 技术语义校验、标签、默认绘图 |
| 采集模式（ATR/Transmission/Unknown） | FTIR 专用 | 用户显式选择或 unknown，不从扩展名推断 |
| ATR 校正状态 | FTIR 专用元数据 | unknown 保留；v1.0 不执行校正 |
| ATR 校正/物理计算（折射率、穿透深度等） | FTIR 专用（未来） | 独立处理模块；需理论依据和真实样本验证 |
| 基团归属/谱库匹配 | FTIR 专用（未来） | 不属于第一版 |

### 8.5 处理阶段建议

1. 导入 + 显示 + 来源记录（不处理）；
2. 线性基线 + 多项式基线（阶数 2–5）+ Savitzky–Golay（复用核心）；
3. 归一化（显式方法、记录）；
4. 峰检测（显式极性、阈值、prominence；不自动归属）；
5. 差谱（同一轴/显式对齐策略）；
6. 多谱比较（overlay、图例、颜色）；
7. 更专业的 FTIR 基线/大气补偿需单独设计；
8. ATR 校正与物理计算不进入 v1.0；未来作为独立 FTIR 处理模块设计和验证。

### 8.6 多谱比较与差谱

- `SpectrumCollection` 保存多个独立 `Spectrum1D`/`ProcessedSpectrum`；
- 不把多个谱拼成一个数据矩阵而不记录成员来源；
- 差谱 `A - B` 必须验证两条谱的轴一致；不一致时默认拒绝，
  只有用户显式选择插值/裁剪并记录参数时才执行；
- 归一化/基线等处理对集合成员逐条记录；
- 导出必须保留每个成员的来源哈希和处理历史。

---

## 9. 回归测试策略

### 9.1 当前基线

- 现有 v0.2.0 生产测试：**298 passed, 1 skipped**；
- M0 基线/架构测试后：**308 passed, 1 skipped**；
- M1 模型/适配器测试后：**332 passed, 1 skipped**；
- M2 importer 协议/注册表测试后：**364 passed, 1 skipped**；
- M3 通用导出测试后：**384 passed, 1 skipped**；
- M4 通用处理测试后：**423 passed, 1 skipped**；
- M5 通用绘图测试后：**447 passed, 1 skipped**；
- M6 通用 CLI/Batch 测试后：**468 passed, 1 skipped**；
- M7 EPR backend 独立化测试后：**494 passed, 1 skipped**；
- M8 GUI shell/registry 测试后：**523 passed, 1 skipped**；
- M9 FTIR importer/batch 测试后：**592 passed, 1 skipped**；
- M10 FTIR GUI 测试后：**622 passed, 1 skipped**；
- M11 maintenance + normalization 测试后：**631 passed, 1 skipped**；
- M12 FTIR baseline 测试后：**661 passed, 1 skipped**；
- M12.2 audit remediation 测试后：**667 passed, 1 skipped**；
- M13 peak picking 测试后：**689 passed, 1 skipped**；
- M11 架构测试从 54 个/约 58.5 秒合并为 20 个/约 5.4 秒，仍保留五个
  独立子进程域；
- 跳过项是 Windows 无法构造的大小写歧义 `.DTA` 伴随文件；
- 真实 `BSA3mal1h` BES3T 样本在本机已执行并通过；
- 真实 `S-BSAPEG-10.0.dpt` ATR-FTIR 样本已导入并通过专项及端到端 CLI 验证；
- 任何迁移步骤都不得降低该基线。

### 9.2 迁移前必须增加的测试

1. **数值特征化测试**
   - ASC/BES3T 合成与真实样本的 `x`/`y` 数组逐值比较；
   - 轴端点、步长、方向、点数、dtype、原始点序；
   - 源文件 SHA-256 前后不变。
2. **输出快照测试**
   - CSV 列名/列顺序/数值；
   - JSON 规范化快照（移除时间戳、绝对路径、版本号后比较结构）；
   - 批处理记录键集合和状态；
   - PNG 尺寸/DPI/元数据；不把截图作为唯一判据。
3. **旧 API 契约测试**
   - `read_asc`、`read_bes3t`、`read_dataset` 的返回类型/字段/错误码；
   - `PreprocessingSession` 的 preview/apply/undo/reset；
   - `draw_spectrum`、`build_curves`、`export_processed`、`export_plot_png`；
   - CLI 退出码与批处理汇总。
4. **架构边界测试**
   - `core` 不导入 Qt；
   - `core` 不导入 `techniques`/`app`；
   - `techniques.epr` 与 `techniques.ftir` 不互相导入；
   - `epr_workflow` 兼容层保持可导入。
5. **新模型不变量测试**
   - 只读数组、长度一致、未知元数据不填充、轴方向不排序、
     原始/处理分离、历史可重复。
6. **Importer 测试**
   - probe 成功/失败/歧义；
   - 多文件来源角色与 SHA；
   - 不支持格式明确报错；
   - 不允许扩展名单独决定格式。
7. **FTIR 测试**
   - CSV/TXT 列映射、分隔符、注释、编码；
   - `cm^-1`、吸光度/透过率/unknown、递增/递减轴；
   - 采集模式 `ATR`/`Transmission`/`unknown` 与 ATR 校正状态
     `applied`/`not_applied`/`not_applicable`/`unknown`；
   - 不从扩展名推断采集模式，不假设 ATR 已校正，不执行 ATR 校正；
   - 线性/多项式基线、归一化、峰检测极性、差谱轴校验、多谱叠加；
   - 所有用户选择与参数写入 JSON。

### 9.3 等价性判定

- 数值：`np.array_equal`（整数/来源值）或 `np.testing.assert_allclose`
  （必须说明容差来源）；
- 元数据：规范化 JSON 后比较，忽略时间戳/绝对路径/版本号；
- 图：优先比较数据系列和轴设置；像素比较仅作为附加证据；
- 错误：比较 code/context 和用户可见翻译，不只比较异常类型；
- 批处理：比较记录键集合、状态、输出路径和源哈希。

### 9.4 执行门禁

每一步迁移都运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m pytest -q -W error::UserWarning
```

Windows 上额外运行 GUI 离屏测试；核心测试不依赖显示器。
任何一步出现 EPR 数值差异、源文件哈希变化、CSV/JSON 科学字段变化或
GUI 关键流程失败，都停止迁移并修复，不继续下一阶段。

---

## 10. 风险与未决设计决策

### 10.1 主要风险

1. **名称/包/仓库重命名风险**：导入路径、配置目录、CLI、GUI 入口、GitHub URL、
   文档链接都会受影响；必须最后执行并保留兼容层。
2. **模型抽象过度**：试图同时支持 1D/2D/复数/时域会让核心复杂化；
   近期只实现 `Spectrum1D`，其余用协议占位。
3. **单位模型风险**：字符串单位简单但容易误用；引入单位库会增加依赖。
   建议先做显式字符串 + 白名单 + 禁止自动换算，后续再评估。
4. **轴方向语义风险**：数据方向、绘图方向、排序/反转如果混在一起，容易
   在 CSV/JSON 中造成不可追溯的变换。必须分离并用测试锁定。
5. **FTIR 科学算法风险**：基线类型、归一化方法、峰检测极性、
   吸光度/透过率转换都可能改变结论；第一版只实现明确、可复现的算法。
6. **多谱/差谱风险**：轴不匹配时插值会改变数据；默认拒绝，显式选择才执行。
7. **ATR-FTIR 语义风险**：ATR 采集模式、Absorbance/Transmittance、ATR 校正
   状态是独立维度；扩展名和数值范围不能推断，未知必须保留，v1.0 不校正。
8. **GUI 测试脆弱性**：现有测试依赖文本和私有状态；模块化时要先建立
   接口级测试，再迁移断言。
9. **JSON/CSV schema 兼容**：新模型不能破坏旧字段；需要 schema 版本和
   适配器，而不是一次性替换。
10. **批处理中的用户映射**：FTIR CSV 的列映射无法在批处理中逐文件交互；
    需要预设/清单文件或显式 CLI 参数，不能猜列。
11. **插件发现与依赖**：首选静态注册（无新依赖）；entry points 需要打包
    基础设施，暂不引入。
12. **性能/内存**：复制只读数组会占用内存；大光谱需要流式/共享策略，
    但第一版保持简单并测试内存行为。
13. **科学记录与翻译分离**：中文 GUI 文案不能进入 JSON 科学记录；
    错误 code/英文原文与翻译映射必须保持稳定。

### 10.2 需要用户确认的决策

在开始实现前，建议确认：

1. **FTIR 输入**：第一版只支持单谱 CSV/TXT，还是也要支持宽表/多谱文件？
2. **归一化方法**：第一版需要哪些（min-max、面积、向量范数、SNV）？
3. **基线方法**：第一版只复用线性基线，还是需要多项式/橡胶带基线？
4. **峰检测**：是否需要波数窗口、峰宽、prominence、极性规则？
5. **差谱/多谱**：轴不一致时是否允许显式插值？默认是否拒绝？
6. **重命名门槛**：是否接受“先内部 `spectralab`、后 GitHub 仓库重命名”的
   分阶段方案？
7. **兼容周期**：`epr_workflow` 旧包名/旧 CLI/GUI 入口需要保留多久？
8. **项目身份**：产品名是否确定为 SpectraLab，还是保留备选名？
9. **仪器元数据**：FTIR 首版需要解析哪些仪器字段（厂商、分辨率、扫描次数、
   检测器、光束分裂器等）？未知字段如何展示？
10. **多技术配置**：是否需要项目文件（`.spectralab`）保存谱图集合、
    处理历史和绘图设置？第一版可以先不实现。

### 10.3 建议的下一步

1. 确认第 10.2 节的关键决策；
2. 在**不改变现有代码**的前提下，先补充第 9.2 节的数值/契约回归测试；
3. 实现 `Spectrum1D` + 适配器，先只读、不替换旧路径；
4. 用真实 EPR ASC/BES3T 样本做逐值等价验证；
5. 再推进 importer 注册表和 FTIR 导入；
6. 每次迁移后运行完整测试，保持 EPR v0.2.0 行为不变。

## 11. Architecture Decisions（已批准）

状态：用户于 2026-11-02 批准以下架构方向。实现顺序与门禁按第 12 节执行。

### AD-01 项目方向

- 长期目标是多技术科学光谱平台。
- 初始技术模块：EPR（现有成熟模块）、FTIR（下一开发优先项）。
- 未来可能技术：NMR、Raman、UV-Vis、荧光。
- 保留现有 EPR 实现，逐步迁移，不重写。
- 依赖方向固定为 `app → techniques → core`。
- `core` 不得导入 Qt，也不得依赖具体技术模块。

### AD-02 核心边界

- 核心负责：数据模型、importer 协议/注册表、通用处理协议、通用绘图/导出基础设施、
  来源与错误机制。
- 技术模块负责：格式解析、技术语义、默认处理/绘图/导出配置、技术面板与技术文案。
- 应用层负责：CLI、批处理编排、GUI 壳、设置持久化、注册表加载。
- 跨层通信使用协议/数据对象，不使用 GUI 私有状态或技术模块全局变量。

### AD-03 FTIR v1.0 文件导入范围

支持：

- 两列 CSV；
- 两列 TXT；
- 带表头的 CSV/TXT，并允许用户配置表头处理；
- 用户显式指定 X/Y 列映射；
- 可配置分隔符和小数点符号；
- 批量导入多个“单谱文件”。

v1.0 不支持：

- 宽表/多谱单文件导入；
- 未确认的厂商原生格式；
- 自动猜测列、单位、吸光度/透过率。

架构要求：

- `ImportedDataset.spectra` 必须是序列，允许未来 importer 从一个源文件返回
  多个 `Spectrum1D`；v1.0 的 CSV/TXT importer 只返回一个。
- 宽表支持作为未来 importer 能力，不在 v1.0 实现。
- 厂商原生格式必须等实验室仪器型号和真实样本文件确认后再设计。

### AD-04 归一化

支持三种显式选择的方法：

1. Min-Max 归一化；
2. 最大绝对值归一化；
3. 向量归一化（L2 范数）。

所有归一化操作必须：

- 保留原始数据，不覆盖；
- 分母为零、非有限或无效时明确拒绝；
- 在结果和处理记录中写明方法、参数、输入来源；
- 支持预览后再应用；
- 不自动执行。

### AD-05 基线校正

支持：

- 线性基线校正；
- 多项式基线校正，用户选择阶数 2–5。

规则：

- 用户必须显式选择拟合区域；
- 不实现自动基线识别；
- 不实现橡胶带（rubberband）基线；
- 现有 EPR 线性基线实现和数值结果保持不变。

### AD-06 峰检测

支持：

- 正峰；
- 负峰；
- 双极性。

用户可配置：

- prominence；
- 最小峰间距；
- 最小峰宽；
- 高度阈值。

规则：

- 不得仅根据 Absorbance/Transmittance 元数据推断峰极性；
- 用户必须在接受或导出前检查检测结果；
- 峰检测结果、参数和输入数据来源必须记录。

### AD-07 差谱

规则：

- X 轴在明确记录的匹配规则下完全一致时，才允许直接相减；
- X 轴不一致时默认拒绝；
- 只有用户显式请求时才允许线性插值；
- 插值只能限制在共同重叠的 X 范围内；
- 绝不外推；
- 必须记录两条源谱、目标轴、插值方法和全部参数；
- 绝不修改源谱。

### AD-08 项目身份

- 暂时保留 `epr_workflow` 包名。
- 暂不重命名 GitHub 仓库、可执行文件、GUI、CLI 或配置目录。
- 设计未来迁移到 `spectralab` 命名空间，并保留兼容层。
- 只有 EPR 迁移等价且 FTIR 达到 beta 稳定后，才考虑正式重命名。

### AD-09 数据完整性与科学要求

以下要求继续强制适用：

- 原始数据不可变；
- 处理结果是独立对象；
- 不做静默转换；
- 不做静默单位换算；
- 不静默排序或反转轴；
- 轴方向与绘图显示方向分离；
- 未知元数据保持显式未知；
- 所有处理操作可追溯、可复现；
- 现有 EPR 数值输出保持不变。

### AD-10 近期模型范围

- 立即只实现 `Spectrum1D` 及其迁移。
- 不实现 `ComplexSignal`、`TimeDomainSignal` 或 `Spectrum2D`。
- 允许在未来用协议/类型占位，但不得提前实现或强行把复数/二维数据塞入
  `Spectrum1D`。

### AD-11 ATR-FTIR

实验室使用 ATR-FTIR。初版 FTIR 模块假设 ATR-FTIR 导出文件与其他 FTIR 光谱
一样，可以通过同一套通用 CSV/TXT 两列导入流程处理；这一假设必须在实际导出
文件确认后保持可验证。

已批准规则：

1. 初版不创建单独的 ATR 文件解析器。
2. 使用共享的 FTIR `Spectrum1D` 数据模型。
3. 增加采集模式元数据：`ATR`、`Transmission`、`Unknown`。
4. 保留信号语义：`Absorbance`、`Transmittance`、`Unknown`。
5. 原样保留原始轴值、信号值、点序、单位和来源元数据。
6. 不假设所有 ATR 光谱已经完成 ATR 校正。
7. ATR 校正状态未知时，必须保留为 `unknown`。
8. 不自动应用 ATR 校正。
9. FTIR v1.0 不实现 ATR 校正。
10. 未来的 ATR 专用校正和物理计算必须放在独立的 FTIR 处理模块中。

附加验证要求：

- FTIR importer 不得仅根据文件扩展名推断采集模式。
- 如果采集模式、信号类型、轴单位或校正状态无法从文件确定，必须保留为
  `unknown` 或要求用户显式输入。
- `ATR`、`Transmission`、`Unknown` 与 `Absorbance`、`Transmittance`、
  `Unknown` 是两个独立维度：ATR 不等于 Absorbance，Transmission 也不等于
  Transmittance；不得互相推断。
- 采集模式和校正状态必须进入来源记录、导出 JSON 和界面显示。

---

## 12. 详细实施路线图

### 12.1 路线图原则

- 每个里程碑都是可独立评审、独立测试、可回滚的变更。
- 默认保留旧入口；新路径在等价性门禁通过前不替换旧路径。
- 每个里程碑都运行完整测试，而不只运行新增测试。
- 任何 EPR 数值、CSV/JSON 科学字段、源文件哈希或 GUI 关键流程的变化，
  都视为回归失败。
- 不新增依赖；Windows + Python 3.11.9 + 现有 `.venv` 必须可运行。
- FTIR 的每个科学操作都必须有预览、显式应用和记录，不自动执行。
- 路线图中的路径是建议目标路径；当前任务不创建这些文件。

### 12.2 里程碑总览

| 里程碑 | 目标 | 复杂度 | 依赖 |
| --- | --- | --- | --- |
| M0 | 基线特征化与架构边界测试 | S | 无 |
| M1 | Spectrum1D 模型与旧结果适配器 | M | M0 |
| M2 | Importer 协议、注册表与 EPR 导入适配 | M | M1 |
| M3 | 通用来源/导出基础设施与 EPR 导出适配 | M | M1, M2 |
| M4 | 通用处理会话与 EPR 处理适配 | L | M1, M3 |
| M5 | 通用绘图 Series/Renderer 与 EPR 绘图适配 | L | M1, M4 |
| M6 | 新 CLI/批处理适配器，旧 CLI 保留 | M | M2, M3 |
| M7 | EPR 技术模块后端收口 | L | M2–M6 |
| M8 | GUI 壳与面板注册表，EPR 兼容 | XL | M5, M7 |
| M9 | FTIR CSV/TXT importer、列映射与批处理核心 | L | M1, M2, M3 |
| M10 | FTIR 导入 GUI 与原始谱显示 | M | M8, M9 |
| M11 | FTIR 归一化 | M | M4, M10 |
| M12 | FTIR 线性/多项式基线 | L | M4, M10 |
| M13 | FTIR 峰检测 | M | M5, M10 |
| M14 | FTIR 差谱与轴匹配策略 | L | M4, M10 |
| M15 | FTIR v1.0 导出、来源、双语与端到端加固 | M | M9–M14 |
| M16 | FTIR 多谱比较（v1.0 之后，可选） | M | M15 |
| M17 | 重命名准备评审（不执行重命名） | S | M8, M15 |

复杂度含义：S = 小，M = 中，L = 大，XL = 很大；这是相对复杂度，不是时间承诺。

### M0 — 基线特征化与架构边界测试

**目标**

在不改变任何应用行为的前提下，把 v0.2.0 的科学数值、输出结构和架构边界固定为
回归基线。

**预计文件/模块**

- 新增 `tests/test_m0_baseline.py`（数值、CSV/JSON 导出基线）；
- 新增 `tests/test_m0_architecture.py`（Qt/反向 GUI/模块级循环边界）；
- 新增 `tests/test_m0_gui_baseline.py`（加载不自动处理）；
- 新增 `tests/fixtures/m0_baseline.json`（机器可读数值摘要）；
- 新增 `docs/m0_baseline_report.md`；
- 不修改现有测试。

**依赖**

无。

**测试要求**

- ASC/BES3T 合成样本与真实样本的 x/y 数组逐值、点数、轴端点、方向、dtype；
- 源文件 SHA-256 前后不变；
- CSV 列名/顺序/数值；
- JSON 规范化后比较（忽略时间戳、绝对路径、版本号）；
- 批处理记录键集合、状态、输出路径；
- 现有 GUI 离屏关键流程；
- 导入图边界测试。

**验收标准**

- 所有新增测试在当前代码上通过；
- 基线可重复生成；
- 不修改任何应用代码、现有测试、配置或项目身份。

**回滚策略**

仅删除新增测试/基线文件；应用代码未动。

**M0 结果**

已完成。基线记录、导出/GUI/架构测试和完成清单见
[m0_baseline_report.md](m0_baseline_report.md)。生产代码与现有测试未修改。

### M1 — Spectrum1D 模型与旧结果适配器

**目标**

建立 `Axis1D`、`Signal1D`、`Spectrum1D`、`SourceFile`、`Provenance`、
`SpectrumMetadata` 和旧 `ImportResult` 的单向适配器；不改变现有调用方。

**预计文件/模块**

- 新增 `src/spectralab/core/model/axis.py`、`signal.py`、`spectrum1d.py`、
  `metadata.py`、`provenance.py`、`values.py`；
- 新增 `src/spectralab/core/legacy_adapter.py`；
- 新增 `tests/test_spectrum1d.py`、`tests/test_legacy_epr_adapter.py`、
  `tests/test_m1_architecture.py`。

**依赖**

M0。

**测试要求**

- 数组只读、长度一致、一维；
- 原始点序保持；递增/递减轴不排序；
- ASC/BES3T 到新模型的数值逐值相等；
- 未知元数据不填充默认值；
- `source_files`/`source_hashes`/`format_metadata` 映射完整；
- 旧 `ImportResult` 仍可原样使用。

**验收标准**

- 适配器转换前后 x/y 数组、点数和轴端点完全一致；
- 新模型不导入 Qt；
- 不改变任何现有模块的导入路径或行为。

**回滚策略**

新模块不被任何生产代码引用；删除即可恢复。

**M1 结果**

已完成 `spectralab.core` 模型与单向旧 EPR 适配器；24 个新增测试通过，
完整测试 332 passed / 1 skipped。设计、映射和限制见
[m1_spectrum1d_report.md](m1_spectrum1d_report.md)。现有 `epr_workflow`
应用代码、GUI、CLI、CSV/JSON schema 未修改。

### M2 — Importer 协议、注册表与 EPR 导入适配

**目标**

建立 `Importer`、`ProbeResult`、`ImportRequest`、`ImportedDataset`、
`ImporterRegistry`；用适配器实现 `XeprASCImporter` 与 `BES3TImporter`。

**预计文件/模块**

- 新增 `src/spectralab/core/importers/base.py`、`registry.py`、`sources.py`、
  `validation.py`；
- 新增 `src/spectralab/techniques/epr/importers/xepr_asc.py`、
  `bes3t.py`；
- 新增 `src/spectralab/app/registry.py`（初始只注册 EPR）；
- 保留 `epr_workflow.plot_asc.read_dataset` 作为旧入口；
- 新增 `tests/core/importers/`、`tests/techniques/epr/importers/`。

**依赖**

M1。

**测试要求**

- probe 正确识别 ASC/BES3T；
- `.DTA` 不能作为独立入口；
- 多候选/不支持格式/缺失伴随文件产生明确错误码；
- 新 importer 与旧 `read_asc`/`read_bes3t` 逐值等价；
- 旧 `read_dataset` 结果不变。

**验收标准**

- 新注册表能选择 ASC/BES3T；
- 旧入口仍可用且完全等价；
- 不改变 GUI/CLI 默认路径。

**回滚策略**

不接线到旧调用方；删除注册表/新 importer；旧路径继续工作。

**M2 结果**

已完成 `spectralab.core.importers` 协议/注册表/来源辅助、
`spectralab.techniques.epr.importers` 的 ASC/BES3T 适配器，以及
`spectralab.app.registry` 的显式注册；新增 32 个测试，完整测试
364 passed / 1 skipped。设计、错误码和限制见
[m2_importer_registry_report.md](m2_importer_registry_report.md)。

实现偏差：测试沿用现有仓库的扁平 `tests/` 目录，而不是计划中的
`tests/core/importers/`、`tests/techniques/epr/importers/`；M2 未新增
`SourceBundle`，伴随文件通过 `ImportRequest.companions` 预留并由 BES3T
适配器按现有规则发现。现有 `epr_workflow` 应用代码、GUI、CLI、
CSV/JSON schema 未修改。

### M3 — 通用来源/导出基础设施与 EPR 导出适配

**目标**

把来源记录、路径保护、CSV/JSON/PNG 导出基础设施与 EPR 专用列/假设分离；
保留现有 ASC/BES3T 输出。

**预计文件/模块**

- 新增 `src/spectralab/core/export/provenance.py`、`paths.py`、`csv.py`、
  `json.py`；
- 新增 `src/spectralab/techniques/epr/export_profile.py`；
- 适配 `processed_export.py`、`plot_export.py` 的新旧接口；
- 新增 `tests/core/export/`、`tests/techniques/epr/export/`。

**依赖**

M1、M2。

**测试要求**

- 旧 CSV 列/顺序/数值不变；
- 旧 JSON 科学字段不变（忽略时间戳/路径/版本）；
- DSC/DTA 与 ASC 源哈希、来源角色完整；
- 路径保护、覆盖保护、原子 PNG 写入；
- 新导出器与旧导出器等价。

**验收标准**

- EPR 原始/处理导出均等价；
- 旧 JSON schema 不被破坏；
- 新导出器默认不接入 GUI/CLI，直到 M6/M8 验证。

**回滚策略**

保留旧导出器为默认；新模块可删除或禁用。

**M3 结果**

已完成 `spectralab.core.export` 的通用 `x,y` CSV、CSV metadata sidecar、
版本化 JSON 文档、provenance 文档、输出路径保护与原子文本写入；新增
20 个测试，完整测试 384 passed / 1 skipped。schema 见
[spectrum1d_export_schema_v1.md](spectrum1d_export_schema_v1.md) 和
[spectrum1d_export_v1.schema.json](spectrum1d_export_v1.schema.json)，
实现与限制见 [m3_export_report.md](m3_export_report.md)。

实现偏差：本次 M3 任务明确只要求通用原始 `Spectrum1D` 导出，因此未实现 PNG、
未新增 `techniques/epr/export_profile.py`，也未适配旧 `processed_export.py`、
`plot_export.py`。旧导出器与旧 CSV/JSON schema 完全未修改。测试继续沿用扁平
`tests/` 目录。现有 `epr_workflow` 应用代码、GUI、CLI、批处理未修改。

### M4 — 通用处理会话与 EPR 处理适配

**目标**

建立 `core.processing` 的会话/操作/记录协议，适配现有线性基线和
Savitzky–Golay；不改变 EPR 数值与记录。

**预计文件/模块**

- 新增 `src/spectralab/core/processing/base.py`、`session.py`、`records.py`；
- 新增 `src/spectralab/core/processing/operations/savgol.py`、
  `baseline_linear.py`；
- 新增 `src/spectralab/techniques/epr/processing_defaults.py`、
  `processing_adapter.py`；
- 新增 `tests/core/processing/`、`tests/techniques/epr/processing/`。

**依赖**

M1、M3。

**测试要求**

- 只读数组、预览不提交、应用/撤销/重置；
- 处理步骤顺序、输入来源、缓存、SHA 失效；
- EPR 线性基线与 Savitzky 结果逐值等价；
- EPR JSON 处理记录字段不变；
- 新会话不实现归一化/峰检测/差谱。

**验收标准**

- EPR 处理数值、JSON 科学字段、GUI 现有行为全部保持；
- 新会话可处理通用 `Axis1D`，但 EPR 默认路径仍走适配器。

**回滚策略**

旧 `PreprocessingSession` 保持默认；新会话不接入 GUI。

**M4 结果**

已完成 `spectralab.core.processing` 的 `ProcessedSpectrum`、
`OperationOutput`、`OperationImplementation`、`ProcessingOperation` 记录和
`ProcessingSession`（apply/undo/redo/reset），以及
`spectralab.techniques.epr.processing_adapter` 的线性基线和
Savitzky-Golay 适配；新增 39 个测试，完整测试 423 passed / 1 skipped。
实现和限制见 [m4_processing_report.md](m4_processing_report.md)。

实现偏差：没有创建 `techniques/epr/processing_defaults.py`；generic session
不复制旧 EPR 的 preview/pending、raw-input 重排和 JSON preprocessing record，
这些继续保留在旧应用。M4 没有 processed-spectrum 导出，M3 raw export 不变。
测试继续沿用扁平 `tests/` 目录。现有 `epr_workflow` 生产代码、GUI、CLI、
preprocessing、CSV/JSON schema 未修改。

### M5 — 通用绘图 Series/Renderer 与 EPR 绘图适配

**目标**

把固定曲线键和 EPR 默认标签移入 EPR 技术模块；建立通用 `Series1D`/
`RenderProfile`，保留现有 Plot Editor 行为。

**预计文件/模块**

- 新增 `src/spectralab/core/plotting/series.py`、`settings.py`、`renderer.py`、
  `export.py`；
- 新增 `src/spectralab/techniques/epr/plotting_defaults.py`；
- 保留 `draw_spectrum`/`build_curves` 兼容包装；
- 新增 `tests/core/plotting/`、`tests/techniques/epr/plotting/`。

**依赖**

M1、M4。

**测试要求**

- 原始/处理/差异/拟合基线系列顺序与样式；
- 轴方向、显示方向、空标签、图例、字体；
- 旧/新渲染的数据系列一致；
- PNG 尺寸/DPI/原子写入；
- Plot Editor 旧测试继续通过。

**验收标准**

- EPR 预览与导出视觉/数据一致；
- 旧 Plot Editor 仍工作；
- 不改变 GUI 默认路径。

**回滚策略**

旧 renderer 保持默认；新 renderer 可禁用。

**M5 结果**

已完成 `spectralab.core.plotting` 的 `Series1D`、`LineStyle`、
`PlotConfig`、原始/处理系列提取和 Matplotlib `Axes` 渲染器；新增
24 个测试，完整测试 447 passed / 1 skipped。API、未知元数据处理和限制见
[m5_generic_plotting_report.md](m5_generic_plotting_report.md)。

实现偏差：本次 M5 任务明确要求独立 generic foundation，因此没有新增
`techniques/epr/plotting_defaults.py`，没有把旧 `draw_spectrum`/`build_curves`
改为兼容包装，也没有 PNG exporter 或 GUI 集成。现有 EPR plotting、Plot Editor、
plot export、GUI、CLI、CSV/JSON schema 均未修改。测试继续沿用扁平 `tests/` 目录。

### M6 — 新 CLI/批处理适配器

**目标**

建立 `app/cli.py`、`app/batch.py` 通过 importer 注册表工作；保留旧
`plot_asc.py` 入口和退出码。

**预计文件/模块**

- 新增 `src/spectralab/app/cli.py`、`batch.py`；
- 新增旧 CLI 兼容适配器；
- 新增 `tests/app/cli/`、`tests/app/batch/`。

**依赖**

M2、M3。

**测试要求**

- 旧命令的参数、输出、退出码不变；
- 新命令对同一 ASC/BES3T 产生等价输出；
- 批处理只发现入口文件，排除 DTA；
- 失败隔离、覆盖保护、汇总。

**验收标准**

- 旧 CLI 完全兼容；
- 新 CLI 可用于 EPR；
- 不改变 FTIR/EPR 默认入口。

**回滚策略**

旧 `plot_asc.py` 继续作为默认；新应用层不接线。

**M6 结果**

已完成 `spectralab.app` 的 generic CLI、batch 编排和 `python -m
spectralab.app` 入口；使用 M2 registry 与 M3 raw renderers，新增 21 个测试，
完整测试 468 passed / 1 skipped。用法、输出布局、错误码和限制见
[m6_cli_batch_report.md](m6_cli_batch_report.md)。

实现偏差：没有新增旧 CLI 兼容适配器层；旧 CLI 完全独立保留。新 CLI 不提供
processing/plotting 参数，因此没有接入 M4/M5。输出使用新的
`tables/<stem>.csv`、`tables/<stem>_metadata.json`、`json/<stem>.json` 和
`logs/spectralab_batch_summary.json`，与旧 EPR 输出分离。测试继续沿用扁平
`tests/` 目录。现有 `epr_workflow` CLI、batch、parser、GUI、schema 未修改。

### M7 — EPR 技术模块后端收口

**目标**

把 EPR importer、语义、处理默认值、绘图默认值、导出 profile 和 EPR i18n
收口到 `techniques/epr`；旧包保留适配器。

**预计文件/模块**

- `src/spectralab/techniques/epr/technique.py`、`semantics.py`、
  `export_profile.py`、`i18n_*.py`；
- 迁移 `xepr_asc.py`/`bes3t.py` 的注册；
- 保留 `epr_workflow` 兼容模块；
- 新增 `tests/techniques/epr/` 集成测试。

**依赖**

M2–M6。

**测试要求**

- 新旧 EPR 后端逐值等价；
- 来源/错误/导出/绘图默认值一致；
- 旧 API 入口仍可导入；
- 技术模块不导入 app/core 以外的技术模块。

**验收标准**

- EPR 可在新后端独立运行；
- 旧 EPR 入口仍工作；
- 尚无 FTIR 依赖。

**回滚策略**

旧 `epr_workflow` 路径保持默认；新模块可删除。

**M7 结果**

已完成 EPR importers 和 baseline/Savgol processing 的独立实现；
`src/spectralab/` 不再运行时导入 `epr_workflow`。依赖清单见
[m7_dependency_inventory.md](m7_dependency_inventory.md)，实现、等价证据和
限制见 [m7_epr_backend_closure_report.md](m7_epr_backend_closure_report.md)。

新增 26 个测试，完整测试 494 passed / 1 skipped；原 EPR 子集
298 passed / 1 skipped 不变。旧 `epr_workflow` 全部生产代码、GUI、CLI、
batch、处理和导出未修改。

实现偏差：本次 M7 任务聚焦 importer/processing runtime closure，没有新增
`technique.py`、`semantics.py`、`export_profile.py`、`plotting_defaults.py`
或 EPR i18n；这些属于后续技术模块/应用层工作。测试继续沿用扁平 `tests/` 目录。

### M8 — GUI 壳与面板注册表，EPR 兼容

**目标**

拆分 GUI 壳（窗口、语言、设置、状态）与技术面板；EPR 现有面板通过适配器
接入；保持 EPR GUI 行为。

**预计文件/模块**

- 新增 `src/spectralab/app/gui/main_window.py`、`controller.py`、
  `metadata_view.py`、`settings.py`；
- 新增 `src/spectralab/techniques/epr/gui/` 适配器；
- 保留旧 `epr_workflow.gui` 入口；
- 新增 `tests/app/gui/`、`tests/techniques/epr/gui/`。

**依赖**

M5、M7。

**测试要求**

- 打开、批处理、预处理、Plot Editor、语言切换、导出；
- 旧 GUI 文本/行为；
- 源文件哈希不变；
- 面板注册/卸载不遗留状态；
- 旧 `MainWindow` 仍可启动。

**验收标准**

- EPR GUI 行为等价；
- 旧入口仍工作；
- 新壳可加载 EPR 技术模块，但尚未加载 FTIR。

**回滚策略**

旧 GUI 保持默认；新壳可禁用。

**M8 结果**

已完成 generic GUI shell、Qt-free controller、technique registry、metadata/status
视图、JSON settings、zh/en 翻译和 EPR 技术面板；新增 29 个测试，完整测试
523 passed / 1 skipped，原 EPR 子集 298 passed / 1 skipped 不变。架构和限制见
[m8_gui_architecture_report.md](m8_gui_architecture_report.md)。

实现偏差：M8 没有重写旧 GUI，也没有实现批处理 UI、Plot Editor、processed export
或 preview。具体 EPR 面板放在 `app/gui/epr_panel.py`，而不是
`techniques/epr/gui/`，以保持 EPR backend 的 Qt-free 约束并继续通过 M2/M4
架构测试；只有 composition root 导入它。测试继续沿用扁平 `tests/` 目录。

### M9 — FTIR CSV/TXT importer、列映射与批处理核心

**目标**

实现 FTIR/ATR-FTIR 单谱 CSV/TXT 导入、显式列映射、分隔符/小数点/表头选项、
`cm^-1` 轴、吸光度/透过率/unknown 语义、采集模式与 ATR 校正状态元数据；
批量导入多个单谱文件。

**预计文件/模块**

- 新增 `src/spectralab/techniques/ftir/importers/generic_csv.py`、
  `generic_txt.py`；
- 新增 `mapping.py`、`semantics.py`、`technique.py`（初始注册）；
- `ImportRequest` 支持 `ColumnMapping`；`ImportedDataset.spectra` 为单元素；
- 新增 `tests/techniques/ftir/importers/`。

**依赖**

M1、M2、M3。

**测试要求**

- 两列 CSV/TXT、有无表头、空白/Tab/自定义分隔符、逗号/点小数；
- 用户指定 X/Y 列；
- `cm^-1`、吸光度/透过率/unknown 必须显式；
- 采集模式 `ATR`/`Transmission`/`unknown` 由用户显式选择或保留 `unknown`；
- ATR 校正状态 `applied`/`not_applied`/`not_applicable`/`unknown` 显式记录，
  不从扩展名推断，不自动校正；
- 递减轴保留；
- 宽表/未确认厂商格式明确拒绝；
- 批量单谱文件，源哈希不变。

**验收标准**

- 合法数据导入为 `Spectrum1D`，数值/轴/语义/来源可验证；
- 缺失/歧义映射、非法单位、非法数值明确报错；
- ATR/Transmission/Unknown 与 ATR 校正状态保留在技术元数据中；
- 不实现任何 FTIR 处理或 ATR 校正。

**回滚策略**

从 `build_importer_registry()` 移除 FTIR 注册、删除 FTIR 模块即可回滚；generic
GUI 尚未注册 FTIR 面板，EPR 不受影响。

**M9 结果**

已完成 generic CSV/TXT/DPT importer、显式列映射/分隔符/小数点/表头/注释/
编码/跳过行选项、FTIR 语义与 ATR 元数据，以及批量导入选项和 CLI 参数；新增
69 个测试，全部通过；完整测试 592 passed / 1 skipped，原 EPR 子集 298 passed
/ 1 skipped 不变。真实 `S-BSAPEG-10.0.dpt` 样本（4350 点、递减轴、ATR/
Absorbance、ATR 校正状态 unknown）已成功导入并完成端到端原始导出验证。
实现与限制见 [m9_ftir_importer_report.md](m9_ftir_importer_report.md)。

实现偏差：
- 默认应用注册表和 M6 CLI 已显式注册 FTIR importer，以便 M9 批处理可用；
  M9 时 GUI 只有 EPR 面板，M10 已另行加入 FTIR 面板；
- 宽表不会自动拆分；多于两列时必须显式映射 X/Y，未映射列会记录 warning。

### M10 — FTIR 导入 GUI 与原始谱显示

**目标**

在技术面板注册表中加入 FTIR 导入面板、列映射对话框和原始谱显示；
不加入任何科学处理。

**预计文件/模块**

- 新增 `src/spectralab/techniques/ftir/gui/import_panel.py`、
  `mapping_dialog.py`；
- 接入 `app/gui` 的技术面板注册；
- 新增 `tests/techniques/ftir/gui/`。

**实际实现（M10）**

FTIR 面板和对话框放在应用层 `src/spectralab/app/gui/ftir_panel.py`、
`ftir_import_dialog.py`、`ftir_options_widget.py`、`ftir_translations.py`，
而不是 `techniques/ftir/gui/`。这与 M8 EPR 面板的处理一致：FTIR backend
保持 Qt-free，只有 composition root 导入具体 GUI。测试继续使用扁平
`tests/` 目录。

**依赖**

M8、M9。

**测试要求**

- 文件选择/表头/分隔符/小数点/列映射；
- 采集模式、信号语义、ATR 校正状态的选择/显示；未知值显示为 unknown；
- 预览列映射；错误提示中英文；
- 原始谱显示、轴标签、单位、方向；
- 不自动处理、不写文件；
- EPR 面板仍正常。

**验收标准**

- FTIR 原始谱可读、可显示；所有映射和语义由用户显式选择；
- ATR 校正状态与采集模式可见且不被推断；
- EPR 回归不降低。

**回滚策略**

从注册表移除 FTIR 面板；EPR 不受影响。

**M10 结果**

已完成 FTIR 技术注册、面板协议实现、内联/对话框导入选项、M9 options 透传、
原始谱 M5 绘图、显式元数据/状态展示、中英文运行时切换和真实
`S-BSAPEG-10.0.dpt` GUI 验证；新增 30 个测试，完整测试 622 passed / 1
skipped，原 EPR 子集 298 passed / 1 skipped 不变。实现与限制见
[m10_ftir_gui_report.md](m10_ftir_gui_report.md)。

实现偏差：
- 导入界面为内联选项面板 + 可选模态导入对话框；generic “打开文件”使用当前
  内联选项，不修改通用 MainWindow 的 FTIR 专用逻辑；
- 没有导入前预览；选项在对话框接受时校验，随后直接导入；
- 显示方向反转仅作用于 Matplotlib 坐标轴，不修改数据；未知 X 轴不做反转；
- M10 不执行任何 FTIR 处理。

### M11 — FTIR 归一化

**目标**

实现三种归一化：Min-Max、最大绝对值、L2；预览后应用，记录参数。

**预计文件/模块**

- 新增 `src/spectralab/core/processing/operations/normalize.py`；
- 新增 `src/spectralab/techniques/ftir/normalization_defaults.py`；
- 扩展 FTIR 处理面板；
- 新增 `tests/core/processing/normalize/`、`tests/techniques/ftir/processing/`。

**实际实现（M11）**

归一化算法放在 `src/spectralab/techniques/ftir/normalization.py`，而不是
core；generic session 只增加无副作用的 `preview()`。测试继续使用扁平
`tests/` 目录（`test_ftir_normalization.py`、`test_architecture.py`）。

**依赖**

M4、M10。

**测试要求**

- 三种公式逐值正确；
- 零分母/非有限/空数组拒绝；
- 原始数据不变；
- 预览/应用/撤销；
- 处理记录包含方法/参数/输入来源；
- 不自动执行。

**验收标准**

- 归一化结果可复现；
- EPR 处理不受影响；
- 不引入隐式单位或语义转换。

**回滚策略**

从 FTIR 面板禁用归一化操作；核心代码可保留但未注册。

**M11 结果**

Part A 已完成：

- M0–M10 的 54 个架构测试合并为 20 个，运行时间从约 58.5 秒降至约
  5.4 秒；子进程域从 27 个启动点合并为 5 个独立域；
- FTIR 导入使用单次稳定字节快照，probe 最多读取 64 KiB；
- FTIR scientific metadata canonical 化：axis/signal 使用核心字段，
  acquisition 使用 `metadata.acquisition`，`technique_metadata` 只保留
  format/column/header，provenance 保留 requested options 与 resolved mapping；
- `parse_column_reference()`、FTIR suffix 常量和 `build_file_filter()` 已共享；
- FTIR translation catalog 只由 composition root/MainWindow 注册；
- 新增 `scripts/check.ps1` 和 `docs/development_workflow.md`。

Part B 已完成：

- 新增 `techniques/ftir/normalization.py`，实现 Min-Max、最大绝对值和 L2
  三种显式归一化；
- 使用现有 `ProcessingSession`、`OperationOutput`、undo/redo/reset 和
  `ProcessedSpectrum`；
- `ProcessingSession` 增加无副作用的 `preview()`，预览不修改历史或 redo；
- FTIR 面板提供方法选择、预览、应用、取消、撤销、重做、重置到原始；
- 原始数组、X 轴、点序、信号 semantics/unit 保持不变；
- 零/非有限分母、空/复数/非有限输入和超范围输出明确失败；
- 真实 `S-BSAPEG-10.0.dpt` 通过 GUI 归一化验证。

偏差：

- 归一化算法放在 `techniques/ftir/normalization.py`，而不是 core
  `operations/normalize.py`；这符合“技术特定算法留在 FTIR 层”的约束；
- 归一化不改变 signal unit/semantics；记录假设说明这是显式数学缩放；
- M9 的“FTIR 无 processing 模块”边界是 M9 范围限制，已由 M11 Part B
  取代；新增算法模块仍保持 Qt-free，并由架构测试覆盖。

完整结果见 [M11 报告](m11_maintenance_and_normalization_report.md)。

### M12 — FTIR 线性/多项式基线

**目标**

复用通用线性基线；新增用户指定阶数 2–5 的多项式基线；用户显式选择区域。

**预计文件/模块**

- 新增 `src/spectralab/core/processing/operations/baseline_polynomial.py`；
- 通用化 `baseline_linear.py` 的轴/区域接口；
- 新增 `src/spectralab/techniques/ftir/baseline_defaults.py`；
- 扩展 FTIR 处理面板；
- 新增 `tests/core/processing/baseline/`、`tests/techniques/ftir/baseline/`。

**依赖**

M4、M10。

**测试要求**

- 线性基线 EPR 数值不变；
- 多项式阶数 2–5 的已知数据拟合/残差；
- 区域选择、越界、重叠、点数不足、非有限值；
- 预览/应用/撤销/记录；
- 不自动基线、不实现橡胶带。

**验收标准**

- 用户选择的区域和阶数可复现；
- EPR 线性基线仍完全等价；
- 多项式结果和诊断明确。

**回滚策略**

FTIR 面板只暴露已稳定的操作；移除多项式注册；线性/EPR 不变。

**实际实现（M12）**

- 新增 `src/spectralab/techniques/ftir/baseline.py`，包含线性与 2–5 阶
  多项式基线；
- 使用中心化/缩放 X 的 float64 Vandermonde 最小二乘，记录条件数并拒绝
  病态/秩亏拟合；
- 区域为闭区间 X 坐标，支持多个不重叠区域、递增/递减轴；
- operation 参数记录算法、阶数、区域；diagnostics 记录拟合点数、缩放域
  系数、中心/尺度、条件数、rank 和数值方法；
- 复用 `ProcessingSession.preview/apply/undo/redo/reset`；
- FTIR 面板增加 normalization/baseline 操作选择、区域列表、度数、预览
  基线曲线和区域阴影；
- 真实 `S-BSAPEG-10.0.dpt` 通过 GUI 基线预览/应用验证。

偏差：
- 没有复用 EPR 线性基线实现，而是在 FTIR 技术层使用独立的基线 API；
  这避免把 EPR 的 field/unit 假设带入 FTIR，同时不改动 EPR；
- 没有自动区域、自动阶数或 rubberband baseline；
- 基线预览在无历史时 raw 与 current 等价，只显示一条 raw/current 曲线；
  有归一化历史时显示 raw、current、baseline、preview 四条曲线；
- 拟合系数记录在 centered/scaled X 域，并同时记录 center/scale 以便复现。

完整结果见 [M12 报告](m12_ftir_baseline_report.md)。

### M13 — FTIR 峰检测

**目标**

支持正峰、负峰、双极性；用户设置 prominence、最小距离、最小宽度、高度阈值；
检测结果可检查后再接受/导出。

**预计文件/模块**

- 新增 `src/spectralab/core/processing/operations/peaks.py`；
- 新增 `src/spectralab/techniques/ftir/peak_defaults.py`；
- 新增 FTIR 峰表/检查 UI；
- 新增 `tests/core/processing/peaks/`、`tests/techniques/ftir/peaks/`。

**依赖**

M5、M10。

**测试要求**

- 已知合成峰的正/负/双极性检测；
- 四个参数逐项生效；
- 不根据吸光度/透过率推断极性；
- 标记/取消标记/接受/导出前检查；
- 处理记录保存参数和结果。

**验收标准**

- 检测可复现且可人工检查；
- 不对峰做化学归属；
- EPR 不受影响。

**回滚策略**

关闭 FTIR 峰检测面板/操作；不影响其他处理。

**实际实现（M13）**

- 新增 `src/spectralab/techniques/ftir/peaks.py`，使用现有
  `scipy.signal.find_peaks`；
- 峰值结果是独立分析模型 `PeakDetectionResult`/`Peak1D`，不进入
  `ProcessingSession` history；
- 支持 raw/current processed source、positive/negative/both polarity；
- height/prominence 使用取向信号单位，distance/min width 使用 sample points；
- width 同时记录 sample points 和 X 轴单位（half-prominence 插值）；
- FTIR 面板新增 Peak picking tab、参数输入、Preview/Apply/Clear、
  Peak Results 表、正/负峰标记和区域状态；
- 参数/来源变化使 preview 失效；processing 状态变化或新导入清除峰值结果；
- 中英文覆盖 GUI、表头、状态和标记；
- 结果记录 dataset ID、axis/signal units、source operation history、
  algorithm/version、参数、计数、warnings/limitations。

偏差：

- 没有把峰检测放进 ProcessingSession，因为它是分析结果而非信号处理历史；
- 没有新增 core processing peak operation；
- 没有峰拟合、deconvolution、化学归属或自动极性推断；
- 边界首末采样点不作为局部峰；result limitations 明确记录；
- 未导出 Peak Results 到文件。

完整结果见 [M13 报告](m13_ftir_peak_picking_report.md)。

### M14 — FTIR 差谱与轴匹配策略

**目标**

实现严格轴匹配的直接差谱；轴不一致默认拒绝；用户显式请求才做共同重叠区间的
线性插值；绝不外推。

**预计文件/模块**

- 新增 `src/spectralab/core/processing/operations/difference.py`；
- 新增 `src/spectralab/techniques/ftir/difference_defaults.py`；
- 新增 FTIR 差谱 UI；
- 新增 `tests/core/processing/difference/`、`tests/techniques/ftir/difference/`。

**依赖**

M4、M10。

**测试要求**

- 相同轴直接相减；
- 轴不匹配默认拒绝；
- 显式插值只在共同重叠区间；
- 不外推、不改源谱；
- 记录源谱、目标轴、插值方法/参数；
- 结果长度/轴与目标一致。

**验收标准**

- 差谱结果可追溯；
- 插值必须用户显式选择；
- EPR/其他 FTIR 操作不受影响。

**回滚策略**

禁用 FTIR 差谱注册；源谱和处理路径不变。

**M14 结果**

已完成显式 ``A - B`` 差谱、精确轴比较、显式线性插值、兼容性验证、独立结果
模型、FTIR 差谱 GUI、预览/应用/清除、来源与处理历史记录，以及 35 个新增测试。
完整测试 724 passed / 1 skipped，原始 EPR 回归 298 passed / 1 skipped，架构
20 passed。实现偏差：差谱依赖两个数据集，未放入单源 ``ProcessingSession`` 或
``core/processing/operations``，而是作为 FTIR technique 层的独立分析结果
（与 M13 峰检测同一模式）。详见
[m14_ftir_difference_spectrum_report.md](m14_ftir_difference_spectrum_report.md)。

### M15 — FTIR v1.0 导出、来源、双语与端到端加固

**目标**

完成 FTIR CSV/JSON/PNG 导出、来源记录、双语界面、批处理映射和端到端测试。

**预计文件/模块**

- 新增 `src/spectralab/techniques/ftir/export_profile.py`；
- 扩展 `core/export` 与技术面板；
- `docs/` 更新 FTIR 使用说明；
- 新增 `tests/techniques/ftir/export/`、`tests/app/ftir_e2e.py`。

**依赖**

M9–M14。

**测试要求**

- CSV 列/单位/语义/来源；
- JSON 处理历史、源哈希、轴方向、采集模式、ATR 校正状态、
  插值/归一化/峰参数；
- PNG 轴方向/标签/图例；
- 双语切换不重读/不重算；
- 批量导入映射；
- 原始文件不变。

**验收标准**

- FTIR v1.0 全部批准功能可用；
- EPR 全部回归测试通过；
- 不新增依赖，不重命名项目。

**回滚策略**

FTIR 技术模块从应用注册表移除；EPR 和旧入口保持原状。

**M15 结果**

已完成单谱 CSV/JSON/PNG 导出、差谱专用 CSV/JSON/PNG 导出、完整 provenance、
FTIR GUI Export 标签页、差谱导出控件、zh/en 文案、默认覆盖保护和批量每文件
mapping/parsing 记录；新增 26 个测试。完整测试 750 passed / 1 skipped，原始
EPR 回归 298 passed / 1 skipped，架构 20 passed。实现偏差：PNG 渲染放在
``spectralab.app.ftir_export``（app 层），因为架构约束禁止 ``techniques/``
导入 Matplotlib；M14 的 ``DifferenceResult`` 增加只读 aligned A/B 信号以支持
CSV 的 ``x, a, b, difference`` 列。详见
[m15_ftir_v1_report.md](m15_ftir_v1_report.md)。

### M16 — FTIR 多谱比较（v1.0 之后，可选）

**目标**

在 `SpectrumCollection` 上实现多谱叠加/比较；不自动平均、不自动对齐。

**预计文件/模块**

- 扩展 `core/model/collection.py`、`core/plotting/series.py`；
- 新增 `techniques/ftir/gui/compare_panel.py`；
- 新增 `tests/techniques/ftir/compare/`。

**依赖**

M15。

**测试要求**

- 每个成员来源/历史保留；
- 覆盖顺序/图例/颜色；
- 差谱/归一化对成员独立；
- 轴不一致显式处理；
- 不自动平均。

**验收标准**

- 多谱比较不改变任何源对象；
- 导出保留成员来源。

**回滚策略**

不注册比较面板；单谱功能不变。

**状态**：不属于 v1.0 的必要门禁，需单独批准。

### M17 — 重命名准备评审（不执行重命名）

**目标**

评估 `spectralab` 命名、兼容层、配置迁移、CLI/GUI 入口和 GitHub 重命名的
前置条件；本里程碑只产出文档/清单，不改名。

**预计文件/模块**

- `docs/` 中的迁移清单、兼容矩阵、发布检查表；
- 不修改应用代码、包名、仓库或配置。

**依赖**

M8、M15。

**测试要求**

- 旧导入路径/CLI/GUI/配置迁移演练；
- 兼容层测试计划；
- 回滚/双名称发布计划。

**验收标准**

- 重命名条件、顺序、兼容周期明确；
- 明确“暂不重命名”。

**回滚策略**

无代码变更；删除/搁置文档即可。

### 12.3 建议的实施顺序

1. **M0 已完成**：数值、导出、GUI 和架构边界基线已建立；下一步 M1。
2. M1 → M2 → M3：建立模型、导入、来源/导出的最小闭环。
3. M4 → M5：处理与绘图；仍不改变旧 GUI。
4. M6 → M7：新 CLI/后端收口，旧入口继续可用。
5. M8：GUI 壳迁移，最高风险，必须最后替换旧 GUI 默认路径。
6. M9 → M10：FTIR 只读导入与显示。
7. M11 → M14：逐个科学操作，每个独立评审。
8. M15：v1.0 加固。
9. M16/M17：仅在前述稳定后考虑。

---

## 13. 与当前代码库的冲突与未决问题

### 13.1 明确冲突

| 决策 | 当前代码冲突 | 处理策略 |
| --- | --- | --- |
| AD-01/AD-02 目标依赖 | 当前 `bes3t.py` 依赖 `plot_asc.ImportResult`；`plot_asc` 同时承担导入/绘图/CLI/批处理；`main_window` 直接依赖 EPR 语义 | 用 M1/M2 适配器拆出模型与 importer；M7/M8 再收口技术模块；不重写 |
| AD-03 CSV/TXT + 映射 | 当前只有 `.ASC`/`.DSC` 分派；GUI 过滤器/批处理发现 EPR 专用；无列映射 | M2 注册表 + M9 FTIR importer；旧 EPR 发现逻辑保留 |
| AD-03 宽表不支持但未来多 `Spectrum1D` | 当前 `ImportResult` 只返回一个 DataFrame；`ImportedDataset` 尚未存在 | M1/M2 将 `spectra` 设计为序列；v1.0 CSV/TXT 只产生一个 |
| AD-04 归一化 | 当前无归一化；`PreprocessingSession` 硬编码两个操作；无预览操作注册表 | M4 通用操作协议 + M11 归一化；EPR 操作不变 |
| AD-05 多项式基线 2–5 | 当前 `BaselineWindow` 使用 `start_G`/`end_G`、两窗口线性拟合；没有多项式/多区域 API | M4/M12 通用轴与区域；EPR 线性基线走兼容路径，数值不变 |
| AD-06 峰检测 | 当前无峰检测；曲线模型固定为四类；无检查/接受 UI | M5 Series + M13 新操作/面板；不自动推断极性 |
| AD-07 差谱/插值 | 当前无差谱；`Axis1D` 不存在；无轴匹配/插值策略 | M1 轴模型 + M14 操作；默认拒绝不匹配轴 |
| AD-08 身份/重命名 | 当前包名 `epr_workflow`；`PROJECT_ROOT`、默认路径、GUI 标题、配置目录均 EPR 专用 | 保留现状；M17 只做评审；未来 `spectralab` + 兼容层 |
| AD-09 数据完整性 | `ImportResult` 仍有 EPR 固定列/计数字段；`SpectrumView` 是 GUI 模型；原始/处理分离只在 `PreprocessingResult` | M1 新模型 + 适配器；M0 回归锁定；不改变现有数值 |
| AD-10 只实现 Spectrum1D | 当前 `PreprocessingResult.field_G`、固定曲线键、无通用轴 | M1/M4/M5 逐步抽象；复数/二维只留占位 |
| AD-11 ATR-FTIR | 当前没有 FTIR importer、采集模式/ATR 校正状态元数据，也没有 ATR 处理模块 | M9 使用同一 CSV/TXT importer；采集模式/校正状态显式或 unknown；不做 ATR 解析/校正 |
| 现有测试稳定性 | GUI 测试依赖精确文本/私有状态；JSON/CSV schema 精确；批处理记录键集合 | M0 先补接口/不变量测试；迁移时保留兼容层，逐步替换断言 |

### 13.2 未决/需要确认的问题

1. **FTIR 表头处理**：`header` 是布尔值、行号，还是“跳过 N 行 + 表头行”？
   需要明确 API 和 UI。
2. **CSV/TXT 解析细节**：引号、转义、千位分隔符、编码（UTF-8/UTF-8-SIG、
   Latin-1）如何支持？第一版建议 UTF-8/UTF-8-SIG + 明确错误，不猜编码。
3. **列映射在批处理中的传递**：CLI 参数、映射预设文件还是每文件 manifest？
   不能逐文件交互猜测。
4. **“X 轴完全一致”的判定**：严格数组相等，还是允许文档化的浮点容差？
   必须在 M14 前定义；建议先严格相等，后再讨论容差。
5. **差谱目标轴**：使用第一条谱、第二条谱、交集网格还是用户指定？
   建议默认使用共同重叠区间上的源谱 A 轴，必须记录。
6. **多项式基线区域**：多个区域如何选择？是否像 EPR 一样用闭区间？
   阶数 2–5 的多项式是否需要权重/诊断？需在 M12 前定义。
7. **峰参数单位**：最小距离/最小宽度用点数还是 x 轴单位？高度阈值是绝对值、
   相对最大值还是相对噪声？需明确。
8. **FTIR 默认显示方向**：默认高波数在左还是低波数在左？用户可改；
   不得改变数据。
9. **归一化/基线/峰检测的顺序语义**：是否允许任意顺序？每一步都记录；
   需定义默认推荐顺序，但不自动应用。
10. **多谱比较是否属于 v1.0**：当前决策只明确批量导入多个单谱文件；
   叠加比较可放 M16/后续版本，需确认。
11. **兼容周期**：`epr_workflow` 旧包/CLI/GUI/配置保留多久？
   需在 M17 前给出明确策略。
12. **仪器元数据**：FTIR 首版需要哪些字段、未知字段如何展示/导出？
13. **项目文件**：是否需要 `.spectralab` 保存集合/历史/绘图设置？
    第一版可以不做，但需明确。
14. **ATR 校正状态的来源**：CSV/TXT 通常没有标准字段，v1.0 应默认 `unknown`
    并允许用户在导入界面显式选择；是否需要预设/批量映射文件？
15. **ATR 文件结构确认**：当前假设 ATR-FTIR 导出符合两列 CSV/TXT；必须在
    真实导出文件到位后确认，否则只保留 unknown/显式映射，不增加 ATR 解析器。

### 13.3 本阶段结论

- 决策与当前代码没有不可调和的冲突，但存在大量**接口/命名/schema 兼容工作**；
- 最高风险不是 FTIR 算法，而是 EPR 回归与 GUI/JSON/CSV 兼容；
- 应先做 M0/M1/M2，建立模型和回归门禁，再进入处理/绘图和 GUI；
- 在 M0–M3 完成前，不应开始 FTIR 实现；
- 重命名必须等到 EPR 等价、FTIR beta、兼容层和配置迁移完成之后。

**本提案到此结束。当前未修改任何应用程序代码、现有测试、配置或项目身份，未安装依赖，未 commit、未 push。等待下一步批准。**

