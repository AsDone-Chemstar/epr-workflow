# SpectraLab / EPR Workflow 项目现状、功能与路线图

> 阅读对象：外部 AI 助手（GPT）或新加入项目的开发者。  
> 文档目的：用一份自包含的材料说明这个项目是什么、现在能做什么、已经做到哪一步、还缺什么、下一步准备做什么。  
> 生成日期：2026-11-05  
> 代码快照：Git HEAD `fae60edc970c67014f921dfddd58dce0ff62d603`（M0–M13 本地 checkpoint；M14、M15 尚未提交）

---

## 0. 先给阅读者的三句话

1. 这是一个 **Python 科研光谱工作流**，最初只处理 Bruker CW-EPR，现在正在增量演进为支持多种技术的 **SpectraLab** 平台；第二个技术是 **FTIR / ATR-FTIR**。
2. 目前存在 **两套 GUI 并存**：旧的 EPR GUI 功能完整；新的 SpectraLab GUI 已有 FTIR 完整分析链和部分 EPR 功能，但还没有完全替代旧 GUI。
3. 项目当前完成到 **M15（FTIR v1.0 导出与加固）**；完整测试 **750 passed, 1 skipped**；原始 EPR 回归 **298 passed, 1 skipped**。M16 及以后尚未开始。

---

## 1. 项目一句话

> 一个面向实验光谱数据的本地 Python 工作流：严格导入原始谱、保留来源和处理历史、只执行用户显式请求的处理/分析，并输出可追溯的结果。

当前主要用户场景：

- Bruker ELEXSYS E580 / Xepr 导出的 CW-EPR 数据；
- 通用两列 FTIR / ATR-FTIR 文本数据（CSV / TXT / DPT）；
- 科研数据处理中的原始数据保护、参数记录、可重复性和来源追踪。

---

## 2. 当前状态快照

| 项目 | 状态 |
| --- | --- |
| Git 仓库 | `D:\EPR workflow` |
| 当前分支 | `main` |
| Git HEAD | `fae60edc970c67014f921dfddd58dce0ff62d603` |
| 最近提交 | `checkpoint: M0-M13 SpectraLab foundation` |
| M14 | 已实现，**未提交** |
| M15 | 已实现，**未提交** |
| 已发布版本 | `v0.2.0`（2026-10-28，原生 BES3T 支持） |
| 新平台名称 | SpectraLab（内部/开发中，尚未发布独立版本号） |
| Python | 3.11.9，64 位，Windows |
| 虚拟环境 | `.venv` |
| 直接依赖 | NumPy 2.4.6、SciPy 1.17.1、Pandas 3.1.0、Matplotlib 3.11.2、Pytest 9.1.1、PySide6 6.12.0 |
| 完整测试 | **750 passed, 1 skipped** |
| 原始 EPR 回归 | **298 passed, 1 skipped** |
| 架构测试 | **20 passed** |
| 唯一 skip | 既有 Windows `.DTA` 大小写歧义测试 |
| 真实 FTIR 样本 | `S-BSAPEG-10.0.dpt`，4350 点，未修改 |
| 真实样本 SHA-256 | `501fe570b175d8f2a089c21c17f469b1a087d654040f72986c5ba9fe9bffe761` |

---

## 3. 产品构成：两个 GUI 和两套入口

### 3.1 Legacy EPR GUI（旧 GUI，功能完整）

启动：

```powershell
cd "D:\EPR workflow"
.\.venv\Scripts\python.exe run_gui.py
```

或双击 `启动 EPR Workflow.bat`。

这是当前 **EPR 完整工作流** 的入口，功能包括：

- 单文件导入 `.ASC` / BES3T `.DSC`（自动配对 `.DTA`）；
- 目录批量处理，样品列表，成功/警告/失败状态；
- 原始谱显示、缩放/平移、鼠标光标读数；
- 线性基线校正；
- Savitzky–Golay 平滑，可选 raw/current 输入；
- 处理预览、取消、应用、撤销、重置；
- Plot Editor：曲线可见性、名称、颜色、线宽、线型、标题、轴标签、自动/手动范围、图例、字号、重置、恢复默认可见性；
- 处理结果导出 CSV / PNG / JSON；
- 打开已生成的 CSV / PNG / JSON；
- 默认禁止覆盖已有输出；
- 简体中文 / English 实时切换；
- 配置保存在 `config/gui_settings.ini`。

重要：**旧 GUI 没有被新 GUI 替换，仍然独立可用。**

### 3.2 SpectraLab GUI（新 GUI，迁移中）

启动（当前需要手动设置 `PYTHONPATH`）：

```powershell
cd "D:\EPR workflow"
$env:PYTHONPATH = "D:\EPR workflow\src"
.\.venv\Scripts\python.exe -m spectralab.app.gui
```

新 GUI 的结构：

```text
顶部：技术选择（EPR / FTIR）、打开文件、语言
左侧：元数据 / 处理历史
右侧：当前技术面板
底部：状态栏
```

目前包含两个技术面板：

#### SpectraLab EPR 面板

已实现：

- ASC / BES3T 导入；
- 原始/处理后谱图；
- 线性基线校正；
- Savitzky–Golay 平滑；
- 应用、撤销、重做、重置；
- 处理历史与来源显示；
- 中英文切换。

尚未迁移到新面板：

- 处理预览 / 取消；
- Savgol 的 raw/current 输入选择；
- 批处理 UI 和样品列表；
- Plot Editor；
- 处理结果 CSV/JSON/PNG 导出；
- 鼠标光标读数；
- 打开输出文件。

#### SpectraLab FTIR 面板

已实现：

- CSV / TXT / DPT 导入；
- 显式列映射、表头、分隔符、小数点、编码、跳过行；
- X 轴物理量/单位、Y 信号语义/单位、ATR/Transmission 采集模式、ATR 校正状态、仪器厂商/型号；
- 原始谱显示，高波数在左的视觉反转（不改变数据）；
- 归一化：Min-Max、max-abs、L2；
- 基线校正：线性、2–5 阶多项式，显式拟合区域，预览/应用/撤销/重做/重置；
- 峰检测：positive / negative / both，raw / processed 来源，height、prominence、minimum distance、minimum width，预览/应用/清除，结果表与图上标记；
- 差谱：A − B，精确轴匹配或显式线性插值，A/B 各自 raw/processed 来源，预览/应用/清除；
- 三个底部标签页：Import options、Peak picking、Difference；
- 多光谱工作区：每个导入光谱有独立 `ProcessingSession`；
- 中英文切换；
- 处理历史、峰检测 provenance、差谱 provenance。

尚未实现：

- FTIR 平滑；
- FTIR 批处理 GUI；
- FTIR/差谱文件导出；
- 多光谱叠加比较（M16）；
- 自动对齐、自动插值、自动归一化、自动基线、自动极性推断。

### 3.3 CLI / 批处理

#### 新 CLI（SpectraLab）

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m spectralab.app data\raw --output-dir results\generic --recursive
```

能力：

- 通过显式 importer registry 批量导入；
- 输出原始 X/Y CSV；
- 输出 JSON 元数据；
- 输出批处理汇总 JSON；
- 支持递归目录、显式格式 ID、覆盖开关；
- FTIR 文本解析选项；
- **不做处理、不做峰检测、不做差谱、不出 PNG**。

#### 旧 CLI（EPR）

```powershell
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py "data\raw\BSA3T275.ASC"
```

能力：

- 单文件 ASC/BES3T 读取、校验、绘图、CSV/JSON/PNG 输出；
- 目录批处理；
- EPR 专用输出命名与来源记录；
- 预处理不在 CLI 中执行，预处理在旧 GUI 中完成。

---

## 4. 架构

### 4.1 依赖方向

```text
app → techniques → core
```

约束：

- `core` 不导入 Qt、Matplotlib、具体技术或 legacy `epr_workflow`；
- `techniques` 不导入 GUI/Qt/legacy；
- GUI 只在 `app` 层；
- 运行时禁止新代码导入 legacy `epr_workflow`；
- legacy 包保持独立、仍可启动；
- 无循环导入。

### 4.2 通用核心

- `Axis1D`：只读 float64 X 轴，记录 quantity、unit、name、direction、metadata_source；
- `Signal1D`：只读 float64 Y 信号，记录 semantics、unit、name；
- `Spectrum1D`：导入谱，包含 axis、raw_signal、metadata、provenance；
- `ProcessedSpectrum`：一个未修改源谱 + 当前 axis/signal + 处理历史；
- `ProcessingSession`：单谱、显式、事务式处理会话，支持 preview/apply/undo/redo/reset；
- `ProcessingOperation`：一次成功操作的历史记录，包含参数、诊断、警告、假设、输入 dataset id；
- `ImporterRegistry`：显式 importer ID，不做隐式格式猜测；
- 通用绘图：`Series1D`、`PlotConfig`、`render_series`、`plot_spectrum`；
- 通用导出：原始 `Spectrum1D` 的 CSV/JSON，schema v1，路径保护和原子写入。

### 4.3 技术模块

- `techniques/epr/`：ASC/BES3T 独立读取器、EPR 线性基线、Savgol 独立实现，数值上与 legacy 有对照测试；
- `techniques/ftir/`：严格文本导入、归一化、基线、峰检测、差谱。

### 4.4 GUI 壳

- 技术注册表；
- 通用 MainWindow；
- 元数据视图；
- 状态事件；
- 设置服务（JSON）；
- 翻译服务（zh/en）；
- 技术面板协议：`open_file`、`retranslate`、`current_display`、`spectrum_changed`、`status_event`。

---

## 5. 目录结构（核心部分）

```text
D:\EPR workflow\
├── src\
│   ├── epr_workflow\                 # legacy EPR 包，仍完整可用
│   │   ├── plot_asc.py               # ASC/BES3T 读取、CLI、批处理
│   │   ├── bes3t.py
│   │   ├── preprocessing.py          # legacy 线性基线 / Savgol
│   │   ├── processed_export.py       # legacy 处理结果导出
│   │   ├── plot_settings.py
│   │   ├── plot_export.py
│   │   └── gui\                      # legacy EPR GUI
│   └── spectralab\                   # 新平台
│       ├── core\
│       │   ├── model\                # Axis1D / Signal1D / Spectrum1D / Provenance
│       │   ├── importers\            # registry
│       │   ├── processing\           # session / records / base
│       │   ├── plotting\             # Series1D / renderer
│       │   └── export\               # CSV / JSON / path safety
│       ├── techniques\
│       │   ├── epr\                  # 独立 EPR 读取和处理
│       │   └── ftir\                 # 导入 / 归一化 / 基线 / 峰 / 差谱
│       └── app\
│           ├── cli.py                # 新 CLI
│           ├── batch.py              # 批处理
│           └── gui\                  # 新 GUI 壳 + EPR/FTIR 面板
├── tests\                            # 750 passed, 1 skipped
├── docs\                             # 里程碑报告和架构提案
├── scripts\check.ps1                 # fast/gui/arch/regression/full/release
├── data\raw\                         # 原始 EPR 数据（不提交）
├── Test data\                        # 真实 BES3T 样本（不提交）
├── results\                          # 输出与日志（不提交）
├── S-BSAPEG-10.0.dpt                 # 真实 FTIR 样本（未跟踪、不提交）
├── requirements.txt
├── run_gui.py                        # 旧 EPR GUI 启动器
└── 启动 EPR Workflow.bat
```

---

## 6. 功能清单

### 6.1 EPR

已实现（旧 GUI 完整，新 GUI 部分）：

- Bruker Xepr 三列 ASC 导入；
- 原生 BES3T `.DSC`/`.DTA` 配对导入；
- ASC/BES3T 严格校验、哈希、来源记录；
- 原始谱图；
- 线性基线校正；
- Savitzky–Golay 平滑；
- 预览/应用/撤销/重置（旧 GUI）；
- 应用/撤销/重做/重置（新 EPR 面板）；
- 批量导入（旧 GUI / 新 CLI）；
- Plot Editor（旧 GUI）；
- 处理结果 CSV/JSON/PNG 导出（旧 GUI）；
- 光标读数（旧 GUI）；
- 中英文；
- 完整回归测试。

重要限制：

- 新 SpectraLab EPR 面板 **尚未** 具备旧 GUI 的批处理 UI、Plot Editor、处理导出、预览和光标读数；
- 两套 EPR 实现目前并存，legacy 仍是对外 EPR 入口。

### 6.2 FTIR / ATR-FTIR

已实现：

- CSV / TXT / DPT 通用两列文本导入；
- 显式列映射、表头、分隔符、小数点、编码、跳过行；
- X/Y 单位和语义显式输入，不推断；
- ATR / Transmission / Unknown 采集模式；
- ATR 校正状态；
- 原始谱显示；
- 波数轴视觉反转；
- Min-Max / max-abs / L2 归一化；
- 线性 / 2–5 阶多项式基线，显式拟合区域；
- 正/负/双向峰检测，height / prominence / distance / width；
- 峰结果表与图上标记；
- A − B 差谱，精确轴匹配或显式线性插值；
- 多光谱工作区；
- 处理历史、峰 provenance、差谱 provenance；
- 单谱 raw/processed CSV/JSON/PNG 导出；
- 差谱专用 CSV/JSON/PNG 导出；
- 默认覆盖保护、源文件保护、完整 provenance；
- 导出控件和消息中英文；
- 中英文。

未实现：

- FTIR 平滑；
- FTIR 批处理 GUI；
- 多光谱叠加比较；
- 自动对齐、自动插值、自动归一化、自动基线、自动极性；
- 化学归属、峰拟合、去卷积。

### 6.3 通用能力

- `Spectrum1D` 中立模型；
- 显式 importer registry；
- 通用 `ProcessingSession`；
- 通用 `Series1D` 绘图；
- 通用原始谱 CSV/JSON 导出；
- 通用 CLI 批量导入；
- 技术注册表 GUI 壳；
- 元数据/处理历史视图；
- JSON 设置；
- zh/en 翻译；
- 架构边界测试；
- release gate。

---

## 7. 里程碑进度

| 里程碑 | 内容 | 状态 | 测试结果 |
| --- | --- | --- | --- |
| M0 | 基线特征化与架构边界 | 完成 | 308 passed, 1 skipped |
| M1 | Spectrum1D + legacy adapter | 完成 | 332 passed, 1 skipped |
| M2 | Importer registry + EPR adapters | 完成 | 364 passed, 1 skipped |
| M3 | 通用导出 | 完成 | 384 passed, 1 skipped |
| M4 | 通用 ProcessingSession + EPR adapter | 完成 | 423 passed, 1 skipped |
| M5 | 通用绘图 | 完成 | 447 passed, 1 skipped |
| M6 | 通用 CLI / 批处理 | 完成 | 468 passed, 1 skipped |
| M7 | EPR backend 独立 | 完成 | 494 passed, 1 skipped |
| M8 | SpectraLab GUI 壳 + EPR 面板 | 完成 | 523 passed, 1 skipped |
| M9 | FTIR CSV/TXT/DPT importer + 批处理核心 | 完成 | 592 passed, 1 skipped |
| M10 | FTIR 导入 GUI + 原始谱显示 | 完成 | 622 passed, 1 skipped |
| M11 | 维护优化 + FTIR 归一化 | 完成 | 631 passed, 1 skipped |
| M12 | FTIR 线性/多项式基线 | 完成 | 661 passed, 1 skipped |
| M12.1 | 基线 audit（只审计，不改代码） | 完成 | 79 focused |
| M12.2 | 基线 audit 修复 | 完成 | 667 passed, 1 skipped |
| M13 | FTIR 峰检测 | 完成 | 689 passed, 1 skipped |
| M14 | FTIR 差谱 | 完成 | 724 passed, 1 skipped |
| M15 | FTIR v1.0 导出、来源、双语与端到端加固 | 完成 | 750 passed, 1 skipped |

原始 EPR 回归在每个里程碑都保持 **298 passed, 1 skipped**。

---

## 8. M14/M15 的关键设计（最新完成的功能）

M14 新增 **35 个测试**（22 个 backend + 13 个 GUI），完整测试从 M13 的
689 提升到 724。M15 新增 **26 个测试**，完整测试提升到 750。

### 8.1 精确相减

```text
difference[i] = A[i] - B[i]
```

要求：

- 点数相同；
- X 值逐元素完全相等（`numpy.array_equal`）；
- 顺序相同；
- 不排序、不反转、不插值；
- 没有数值容差。

### 8.2 线性插值

用户显式选择 `interpolate` 时：

1. 计算共同重叠区间；
2. 使用 A 在闭区间内的 X 点作为目标轴；
3. 将 B 线性插值到目标轴（`numpy.interp`）；
4. 计算 A − B_interpolated；
5. 不外推、不排序、不修改源数组。

B 为递减轴时，只反转局部工作副本给 `numpy.interp` 使用；源对象和输出顺序不变。

### 8.3 兼容性

- X 轴物理量必须相同且已知；
- X 轴单位必须相同（双方 `None` 时保留未知）；
- 信号语义必须相同且已知；
- 信号单位必须相同（双方 `None` 时保留未知）；
- 数据集 ID 必须不同；
- 重复/非单调轴拒绝；
- 未知语义/物理量拒绝；
- 非有限值在模型层拒绝。

### 8.4 结果与导出

`DifferenceResult` 是独立分析结果，不进入 `ProcessingSession`。它记录两个数据集、两个来源、处理历史、插值参数、算法版本和限制。

M15 已实现差谱专用导出：

- CSV：`x, a, b, difference`；
- JSON：两个源、SHA-256、处理历史、插值设置和 provenance；
- PNG：A、B、插值 B、A−B。

`DifferenceResult` 在 M15 增加只读 `aligned_a_signal` / `aligned_b_signal`，用于 CSV 列；M14 的算术定义不变。

### 8.5 M15 导出

- 单谱：raw/processed CSV、JSON、PNG；
- 差谱：专用 CSV/JSON/PNG；
- CSV 带 JSON metadata sidecar；
- JSON 记录源文件 SHA-256、导入参数、仪器、采集模式、ATR 状态、处理历史、峰参数、导出时间、软件版本；
- 默认禁止覆盖；拒绝覆盖源文件；
- PNG 在 app 层用 Matplotlib 渲染，不污染 technique 后端；
- GUI 增加 Export 标签页和差谱导出控件；
- 中文/英文切换；
- 批量导入的每个文件记录 resolved mapping 和 parsing 参数。

---

## 9. 科学完整性与数据安全规则

项目对所有新功能坚持：

1. 原始数据只读；
2. 不自动平滑、归一化、基线校正、滤波、去尖峰；
3. 不自动对齐、不自动插值、不外推；
4. 不排序、不反转源数组；
5. 不推断缺失单位、语义、采集模式或轴方向；
6. 不做单位换算；
7. 不把不兼容的信号相减；
8. 不伪造元数据、哈希、时间戳或测量值；
9. 所有处理/分析必须由用户显式触发；
10. 处理历史与原始数据分离；
11. 分析结果（峰、差谱）与处理历史分离；
12. 预览不修改任何持久状态；
13. 输出路径默认拒绝覆盖，且不能覆盖源数据；
14. 真实实验数据不修改、不重命名、不删除。

---

## 10. 已知限制与技术债

### 10.1 产品/入口

- 新 SpectraLab GUI 需要手动设置 `PYTHONPATH`；没有 `pyproject.toml`、console script 或安装包；
- 默认启动器 `run_gui.py` 仍指向旧 EPR GUI；
- 两个 GUI 功能不一致，用户容易误以为新 GUI 功能缺失；
- README 主要描述旧 EPR 产品，尚未完整描述 SpectraLab。

### 10.2 EPR 迁移

- 新 EPR 面板缺：预览/取消、Savgol raw/current 输入、批处理 UI、Plot Editor、处理导出、光标读数、打开输出；
- 新 EPR 后端与 legacy 数值等价，但 GUI 行为尚未对齐；
- 官方路线图 M15–M17 是 FTIR 导向，**没有正式安排 EPR GUI 全面对齐**；
- 若要“所有 EPR 功能进入 SpectraLab”，需要新增一个明确的 EPR parity 里程碑。

### 10.3 FTIR

- `ftir_panel.py` 已约 2300 行，包含多光谱工作区、处理、峰、差谱、导出，后续应拆分；
- 没有 FTIR 平滑；
- 没有 FTIR 批处理 GUI；
- 差谱 CSV 只含对齐后的 B；原始 B 数组不放入同一 CSV（长度可能不同）；
- 差谱导出 API 需要结果加两个源 `Spectrum1D`；
- `spectralab` 尚无发布版本号，导出 JSON 记录 `"unversioned"`；
- PNG 中文字体依赖系统已安装 CJK 字体；
- 没有多光谱比较（M16）；
- 峰结果是全局状态，切换当前光谱会清除；
- 差谱在任一处理变化时全部清除（保守失效）；
- 数据集身份按 `dataset_id`，不按哈希；同名文件视为同一数据集；
- 插值目标固定为 A；
- 未知信号语义/物理量直接拒绝，因此某些未标注单位的文件需要用户先显式设置。

### 10.4 工程/流程

- M14、M15 代码尚未提交；HEAD 仍停在 M0–M13 checkpoint；
- 没有 CI（GitHub Actions）；release gate 目前是本地 `scripts/check.ps1`；
- 旧/新 EPR 实现并存，bug 可能需要修两处，直到 legacy 冻结；
- 没有统一的 Plot Editor/导出/批处理通用 GUI 组件；
- 测试依赖部分未跟踪真实文件；缺失时相关测试会 skip。

---

## 11. 未来计划

### 11.1 M15 — FTIR v1.0 导出、来源、双语与端到端加固（已完成）

已完成：

- 单谱和差谱 CSV/JSON/PNG；
- provenance、双语、覆盖保护；
- 批量 mapping 记录；
- 端到端测试。

原始目标：

- FTIR CSV / JSON / PNG 导出；
- 导出中包含处理历史、源哈希、轴方向、采集模式、ATR 校正状态、归一化/基线/峰/差谱参数；
- 双语界面；
- 批处理映射；
- 端到端测试；
- 不新增依赖、不重命名项目。

M15 已使 FTIR 功能链达到 v1.0 完整度：

```text
导入 → 显示 → 归一化 → 基线 → 峰检测 → 差谱 → 导出
```

### 11.2 M16 — FTIR 多谱比较（可选，v1.0 之后）

- 在 `SpectrumCollection` 上做多谱叠加/比较；
- 不自动平均、不自动对齐；
- 每个成员保留自己的来源和历史；
- 轴不一致显式处理；
- 不属于 v1.0 必要门禁，需要单独批准。

### 11.3 M17 — 重命名准备评审（只评审，不执行）

- 评估 `spectralab` 包名、兼容层、配置迁移、CLI/GUI 入口、GitHub 仓库重命名；
- 只产出文档/清单；
- 不改代码、不改包名、不改仓库。

### 11.4 建议但尚未批准的里程碑：EPR GUI 功能对齐

如果目标是“所有 EPR 功能都在 SpectraLab 中，不再单独走旧通道”，建议在 M15 之后增加：

1. 通用 GUI 组件：处理预览、批处理/样品列表、导出对话框、Plot Editor、光标读数；
2. EPR 面板逐项对齐：预览、Savgol raw/current、批处理、导出、Plot Editor、设置迁移；
3. 把 SpectraLab 设为默认入口，旧入口保留一个过渡版本并提示迁移；
4. 冻结 legacy 后端，只保留兼容导入路径；
5. 最后才做 M17 重命名评审。

这项工作目前 **不在官方已批准路线图中**，需要单独批准。

### 11.5 更长期

- 更多技术模块（其他光谱技术）；
- 多谱比较、批量绘图；
- 统一导出/来源 schema；
- CI、打包、安装器；
- 旧 EPR 功能退役与包名迁移。

---

## 12. 如何运行和验证

### 12.1 运行新 GUI

```powershell
cd "D:\EPR workflow"
$env:PYTHONPATH = "D:\EPR workflow\src"
.\.venv\Scripts\python.exe -m spectralab.app.gui
```

### 12.2 运行旧 EPR GUI

```powershell
cd "D:\EPR workflow"
.\.venv\Scripts\python.exe run_gui.py
```

### 12.3 运行新 CLI

```powershell
cd "D:\EPR workflow"
$env:PYTHONPATH = "D:\EPR workflow\src"
.\.venv\Scripts\python.exe -m spectralab.app "data\raw" --output-dir "results\generic" --recursive
```

### 12.4 运行测试

```powershell
cd "D:\EPR workflow"
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"

# 完整测试
.\.venv\Scripts\python.exe -m pytest -q

# warnings-as-errors
.\.venv\Scripts\python.exe -m pytest -q -W error::UserWarning

# 原始 EPR 回归
.\scripts\check.ps1 -Mode regression

# 架构
.\scripts\check.ps1 -Mode arch

# 完整 release gate
.\scripts\check.ps1 -Mode release -Milestone m14
```

当前结果：

```text
完整：750 passed, 1 skipped
warnings-as-errors：750 passed, 1 skipped
原始 EPR：298 passed, 1 skipped
架构：20 passed
```

---

## 13. 关键文件索引

### 通用核心

- `src/spectralab/core/model/axis.py`
- `src/spectralab/core/model/signal.py`
- `src/spectralab/core/model/spectrum1d.py`
- `src/spectralab/core/model/provenance.py`
- `src/spectralab/core/processing/session.py`
- `src/spectralab/core/processing/records.py`
- `src/spectralab/core/plotting/series.py`
- `src/spectralab/core/plotting/renderer.py`
- `src/spectralab/core/export/csv.py`
- `src/spectralab/core/export/json.py`

### EPR

- `src/spectralab/techniques/epr/importers/`
- `src/spectralab/techniques/epr/processing_impl.py`
- `src/spectralab/techniques/epr/processing_adapter.py`
- `src/spectralab/app/gui/epr_panel.py`
- legacy：`src/epr_workflow/gui/`、`src/epr_workflow/preprocessing.py`、`src/epr_workflow/processed_export.py`

### FTIR

- `src/spectralab/techniques/ftir/importers/`
- `src/spectralab/techniques/ftir/normalization.py`
- `src/spectralab/techniques/ftir/baseline.py`
- `src/spectralab/techniques/ftir/peaks.py`
- `src/spectralab/techniques/ftir/difference.py`
- `src/spectralab/app/gui/ftir_panel.py`
- `src/spectralab/app/gui/ftir_translations.py`

### GUI / CLI

- `src/spectralab/app/gui/app.py`
- `src/spectralab/app/gui/main_window.py`
- `src/spectralab/app/cli.py`
- `src/spectralab/app/batch.py`
- `run_gui.py`

### 测试与流程

- `tests/test_architecture.py`
- `tests/_arch_support.py`
- `tests/test_ftir_importer.py`
- `tests/test_ftir_normalization.py`
- `tests/test_ftir_baseline.py`
- `tests/test_ftir_peaks.py`
- `tests/test_ftir_difference.py`
- `tests/test_ftir_gui.py`
- `tests/test_ftir_difference_gui.py`
- `tests/test_epr_backend.py`
- `tests/test_processing_session.py`
- `scripts/check.ps1`
- `docs/architecture_proposal.md`
- `docs/m14_ftir_difference_spectrum_report.md`

---

## 14. 当前 Git 与数据状态

```text
HEAD = fae60edc970c67014f921dfddd58dce0ff62d603
```

- M0–M13 已进入本地 checkpoint 提交；
- M14、M15 代码、测试、文档尚未提交；
- 未 push；
- 未创建 tag；
- 未 amend/rebase/reset/clean；
- 未修改 `requirements.txt`；
- 未修改 legacy `epr_workflow`；
- 未修改 `S-BSAPEG-10.0.dpt`；
- `S-BSAPEG-10.0.dpt` 是未跟踪的原始实验样本，不应提交；
- `data/raw/`、`Test data/`、`results/`、`config/`、`.venv/` 均不提交。

真实 FTIR 样本：

```text
文件名：S-BSAPEG-10.0.dpt
点数：4350
X 轴：wavenumber，cm^-1，decreasing
信号：absorbance，unit=None（显式未知）
SHA-256：501fe570b175d8f2a089c21c17f469b1a087d654040f72986c5ba9fe9bffe761
```

---

## 15. 给 GPT 的建议提问方式

如果要让 GPT 基于本文档做后续工作，建议在提示中明确：

1. 当前目标是什么：EPR 功能对齐、FTIR v1.0、导出、重构、还是写用户文档；
2. 允许修改的范围：是否只读分析、是否写代码、是否写测试；
3. 必须保持的约束：原始数据只读、不自动处理、不推断单位/语义、不提交 Git；
4. 需要输出什么：计划、代码、测试、文档、审查意见；
5. 是否需要区分 legacy EPR GUI 与 SpectraLab GUI。

推荐提示示例：

```text
你是一个科学软件架构评审者。请阅读下面的项目文档，
只做分析，不写代码。重点评估：
1) 把 legacy EPR GUI 全部功能迁移到 SpectraLab 的最佳里程碑拆分；
2) 哪些通用 GUI 组件应先抽取；
3) 现有测试和架构约束是否足够防止回归；
4) 给出风险清单和验收标准。
```

---

## 16. 一句话总结

> 这个项目已经完成了“中立光谱模型 + 通用导入/处理/绘图/导出 + FTIR v1.0 分析链（导入、归一化、基线、峰、差谱、导出）”，但 **EPR 完整 GUI 仍在 legacy 中**；下一步是 M16（可选多谱比较），而“所有 EPR 功能进入 SpectraLab”需要单独批准的 EPR parity 里程碑。
