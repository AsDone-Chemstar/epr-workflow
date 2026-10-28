# EPR Workflow

**简体中文** | [English](README.en.md)

用于 **Bruker ELEXSYS E580 / Xepr** 导出的 CW-EPR 数据的 Python 分析工作流。

当前版本：**0.2.0**。版本更新与历史版本说明见 [CHANGELOG.md](CHANGELOG.md)。

当前版本完成：**导入 → 校验 → 绘制原始谱图 → 导出**，支持 Xepr 三列
ASCII `.ASC` 与原生 BES3T `.DSC`/`.DTA` 配对数据；以及用户主动触发的
**线性基线校正**、**Savitzky–Golay 平滑**和独立的 **Plot Editor（绘图设置）**。
预处理只在内存副本上进行，不自动应用，不修改原始数据；Plot Editor 只改变
可视化设置，不修改原始数据、已处理数据或预处理历史。未实现归一化、插值、去尖峰、
自动基线识别或全局曲线拟合。

## 1. 环境要求

- Windows 10/11
- Python **3.11.9**（64 位）
- 项目虚拟环境：`.venv`
- 依赖：NumPy、SciPy、Pandas、Matplotlib、Pytest、PySide6（版本见 `requirements.txt`）

## 2. 环境搭建

```powershell
# 进入项目目录
cd "D:\EPR workflow"

# 若 .venv 不存在，创建虚拟环境
python -m venv .venv

# 安装依赖
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. 运行脚本

### 3.0 桌面 GUI

本项目附带一个本地桌面界面（PySide6 + Matplotlib），提供可视化导入、批量处理、
状态查看与缩放/平移。启动方式（需先安装依赖）：

```powershell
cd "D:\EPR workflow"
.\.venv\Scripts\python.exe run_gui.py
```

也可以：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m epr_workflow.gui
```

GUI 功能：

- 打开单个 `.ASC` 文件或 BES3T `.DSC` 描述文件，只读显示原始谱图
  （不写任何输出）；DTA 由 DSC 自动配对，不能单独作为数据入口。
- 选择文件夹批量处理，生成 CSV / PNG / JSON 与批次汇总；批量模式发现
  `.ASC` 和 `.DSC`，不会把 `.DTA` 当作独立数据集。
- 样品列表用颜色标注成功 / 成功但有警告 / 失败；点击样品查看其谱图。
- 工具栏提供缩放、平移、复位；鼠标悬停显示光标处的磁场与强度。
- 显示磁场范围、数据点数、信号统计与校验警告。
- 打开已生成的 CSV / PNG / JSON 输出。
- 默认**禁止覆盖**已有输出；勾选“允许覆盖”后才允许替换。
- 左栏“预处理”面板支持用户显式选择线性基线校正或 Savitzky–Golay 平滑（见 3.4）；
  默认不执行任何处理。
- 左栏“绘图”标签页提供独立的 Plot Editor：按实际可用曲线设置可见性、名称、颜色、
  线宽和线型，编辑标题、坐标轴标签、范围、图例与字号，并实时预览（见 3.5）。
  绘图设置不会修改数据或预处理记录。
- 绘图设置可导出为 PNG，导出的是 Matplotlib 图像本身而不是窗口截图；默认不覆盖。
- 界面支持**简体中文 / English 实时切换**：右上角「语言 / Language」下拉框。
  切换语言不会重新读取原始数据文件、不会重新批量处理，也不会清空已加载的谱图、
  样品列表、批次结果、当前选中样品或光标读数。
- 语言选择保存在 `config\gui_settings.ini`（只保存语言代码，不写注册表）；
  重启后自动恢复，没有记录时默认简体中文。

GUI 逻辑（`epr_workflow/gui/controller.py`）与界面（Qt 窗口）分离，核心数据处理
仍复用 `epr_workflow/plot_asc.py`，GUI 本身不做任何信号处理。

### 3.1 处理单个文件

```powershell
cd "D:\EPR workflow"

# 默认处理 data\raw\BSA3T275.ASC
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py

# 处理指定文件
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py "data\raw\BSA5P5T10.ASC"

# 指定文件并立即弹窗查看
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py "data\raw\BSA5P5T10.ASC" --show

# 处理原生 BES3T 数据集：入口是 .DSC，而不是 .DTA
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py "path\to\sample.DSC"
```

BES3T 的 `.DSC` 与 `.DTA` 必须位于同一目录、文件名主干相同；扩展名大小写
不敏感。`.DTA` 只是伴随文件，不能单独作为输入。

也可以用模块方式运行（需先设置 `PYTHONPATH`）：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m epr_workflow.plot_asc
```

### 3.2 批量处理一个目录

```powershell
cd "D:\EPR workflow"

# 处理 data\raw 下所有 .ASC 与 .DSC 入口（不搜索子目录，不单独处理 .DTA）
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py --input-dir data\raw --output-dir results

# 只输出到新的目录，避免碰到已有结果
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py --input-dir data\raw --output-dir results\batch_20261026

# 包含子目录
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py --input-dir data\raw --output-dir results\all --recursive

# 允许覆盖已有输出
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py --input-dir data\raw --output-dir results --overwrite
```

批量模式规则：

- 只处理扩展名为 `.asc` 或 `.dsc` 的入口文件，**大小写不敏感**；
  `.dta` 是 BES3T 伴随文件，绝不会被当作独立数据集。
- 默认不搜索子目录，需要时加 `--recursive`。
- 处理顺序固定（按相对路径不区分大小写排序），每次运行一致。
- 某个文件失败不会中断其他文件；失败信息写入批次汇总。
- 默认**拒绝覆盖**已有输出；确认后加 `--overwrite`。
- 单个文件模式同样受覆盖保护，重复运行需加 `--overwrite`。

### 3.3 常用参数

| 参数 | 说明 |
| --- | --- |
| `input` | 单文件模式：输入 `.ASC` 路径或 BES3T `.DSC` 描述文件，默认 `data\raw\BSA3T275.ASC` |
| `--input-dir PATH` | 批处理模式：处理该目录下的 `.ASC` 和 `.DSC` 入口（忽略 `.DTA`） |
| `--output-dir PATH` | 输出根目录，默认 `results`（批次时结果放在其下的 figures/tables/logs） |
| `--recursive` | 批处理时搜索子目录（默认关闭） |
| `--overwrite` | 允许替换已存在的输出文件（默认拒绝） |
| `--figure PATH` | 仅单文件：自定义 PNG 路径 |
| `--csv PATH` | 仅单文件：自定义 CSV 路径 |
| `--json PATH` | 仅单文件：自定义 JSON 报告路径 |
| `--show` | 仅单文件：交互式显示图像 |
| `--allow-non-monotonic` | 允许绘制磁场非单调的数据（默认拒绝，避免误导） |
| `--log-level` | 日志级别，默认 `INFO` |

`input` 与 `--input-dir` 不能同时使用；`--figure/--csv/--json/--show` 只用于单文件模式。

### 3.4 预处理（线性基线校正 / Savitzky–Golay 平滑，仅 GUI）

处理只在内存副本上进行；原始数据文件（ASC 或 BES3T DSC/DTA）与已有的原始导出
结果都不会被修改。默认没有选择任何基线区间，平滑也不会自动启用。

1. 打开单个受支持的数据文件（ASC 或 BES3T DSC），或批量处理后选中一个样品。
2. 在左栏“预处理”的“方法”中选择：
   - **线性基线校正**：填写左、右两个闭区间（单位 G）。
     四个输入框初始为空，不填写就无法预览或应用。
   - **Savitzky–Golay 平滑**：设置窗口长度与多项式阶数，并选择平滑输入：
     “当前处理结果”（追加到已有步骤之后）或“原始数据”（置于已有步骤之前）。
3. 点“预览”：图中显示原始（灰虚线）、差异（橙点线）与处理结果（蓝实线）；
   预览不会写入任何文件。
4. 点“取消预览”：丢弃临时预览结果，不改变原始数据，也不改变已应用的处理历史。
5. 点“应用”：把该步骤记入当前文件的内存会话（可多次应用，按顺序记录）。
6. “撤销”移除最后一步，“重置”回到原始数据；两者都从原始数据重算。
7. 点“导出处理结果…”写出文件；默认不覆盖已有文件，需要先勾选“允许覆盖”。

基线规则与限制：

- 每个窗口至少包含 3 个数据点；**3 点只是拟合可计算的最低要求，不代表基线区域可靠**。
- 当前版本按已批准设计使用**两个**互不重叠的闭区间窗口；单区间拟合未实现。
- 两个窗口不得重叠或共享端点，且两窗口之间至少保留 1 个未选数据点。
- 只允许**严格单调**的磁场轴；重复值或非单调轴会被拒绝，程序不排序、不修复。
- 拟合方法：两个窗口内的全部点联合做一次普通最小二乘直线拟合，再对全场逐点相减
  （`intensity_corrected = intensity_raw - (slope × field_G + intercept)`）。
- 界面显示残差 RMS、窗口点数、外推距离与诊断警告。**R² 只描述窗口内直线拟合的
  贴合程度，不能证明所选区域就是基线**，必须结合预览、残差、点数和外推距离判断。

平滑规则与限制：

- 使用 `scipy.signal.savgol_filter(window_length, polyorder, deriv=0, mode="interp")`，
  保持点数、磁场顺序和 float64 类型不变。
- 窗口长度必须为**奇数**、至少 3、且不超过数据点数；多项式阶数必须满足
  `0 ≤ polyorder < window_length`。
- 平滑会改变峰高、峰宽和线形；**曲线更光滑不代表数据质量提高**。
- 选择“原始数据”作为输入且已有处理步骤时，新的平滑步骤会排到已有步骤之前，
  界面和 JSON 都会记录新顺序并给出警告。
- 平滑参数不合法时不会修改任何数据或已应用历史。

通用规则：

- 每个文件的处理状态只保存在当前会话内存中，切换样品不会丢失；关闭程序后消失。
  源文件 SHA-256 变化时，对应会话自动作废。
- 语言切换只重绘界面，不会重新拟合或重新平滑。
- 当前不支持批量预处理，也没有 CLI 预处理参数。

### 3.5 Plot Editor（绘图设置，仅 GUI）

Plot Editor 是左栏独立的“绘图”标签页，**只改变可视化设置**；它不读取文件、
不重新运行基线校正或平滑、不修改原始数据、已处理数据或预处理历史。

曲线列表按当前实际可用的数据动态生成，不会凭空创建曲线：

- **原始数据**：始终可用。
- **处理结果**：只有在当前会话已应用至少一个预处理步骤时可用。
- **差异曲线 / 已移除基线**：只有存在处理步骤时可用；基线校正后表示原始减去处理
  结果，平滑后表示原始减去平滑结果（总变化，不是重新拟合的基线）。
- **拟合基线**：只有基线校正确实记录了拟合参数时可用；默认**隐藏**，并明确标记为
  拟合基线，避免被误认为实验信号。

每一可用曲线可单独设置：

- 是否可见（隐藏不会删除数据，也不会改变处理步骤）。
- 显示名称；留空时使用随语言变化的默认名称。
- 颜色（颜色选择器或 `#RRGGBB`）与线宽（0.1–10.0 pt）。
- 线型：实线、虚线、点线、点划线。

坐标轴与图例：

- 标题、X 轴标签、Y 轴标签均可编辑，也可留空。
- X/Y 范围可选自动或手动；手动范围要求有限数字且最小值小于最大值，非法输入会
  显示错误并保留上一次有效设置。
- 图例可显示/隐藏并选择位置；标题、坐标轴、刻度和图例字号可单独调整。

操作规则：

- 所有修改实时反映在 GUI 画布中；不会自动保存科学数据。
- “重置”恢复当前数据的默认绘图设置；“恢复默认可见性”只恢复曲线的显示/隐藏
  状态，保留用户自定义的名称、颜色、线宽、线型与坐标轴设置。
- 绘图设置按样品保存在当前会话内存中；切换样品后可恢复。源文件 SHA-256 变化时，
  该样品的旧设置作废。关闭程序后设置不保留。
- 语言切换会更新自动标题/标签与图例默认名称，但不会重新读取原始数据文件，也不会
  重新校正或平滑；用户自定义的文字与样式保持不变。
- 预处理处于**未应用的预览**状态时禁止导出绘图，避免把临时预览误当作正式结果。

导出 PNG：

- 从“绘图”标签页点击“导出绘图…”，输出的是当前 Matplotlib 图形本身（不是窗口
  截图），使用与实时预览相同的绘图函数和设置。
- 可设置宽、高（英寸）和 DPI；支持常用 150 / 300 / 600 dpi。可分别选择是否包含
  标题和图例。
- 默认路径为 `<output-dir>\figures\<sample>_plot.png`，也可另选路径。
- 默认**拒绝覆盖**已有文件；确认后才允许替换。
- 不写入 `data\raw\`，不覆盖原始 `_raw` 或处理结果 CSV/JSON；绘图参数变化不会改变
  任何科学数据输出。

## 4. 输出文件

### 4.1 单文件

以 `BSA3T275.ASC` 为例（文件名主干 `BSA3T275`，输出根目录为 `results`）：

| 文件 | 内容 |
| --- | --- |
| `results\figures\BSA3T275_raw.png` | 原始 CW-EPR 谱图，300 dpi |
| `results\tables\BSA3T275_raw.csv` | 导入后的三列数据（`index, field_G, intensity`） |
| `results\logs\BSA3T275_metadata.json` | 校验与统计报告 |

### 4.2 批处理

```text
<output-dir>\
├── figures\<sample>_raw.png
├── tables\<sample>_raw.csv
├── logs\<sample>_metadata.json
└── logs\batch_summary.json
```

`<sample>` 由输入文件名生成；使用 `--recursive` 时包含相对子目录，例如
`data\raw\sub\X.ASC` → `sub_X_raw.csv`，避免不同子目录同名文件互相覆盖。
若两个文件仍会生成相同的输出名，这些文件会被标记为失败且不写任何输出。

JSON 报告包含：源文件名、文件大小、SHA-256、导入时间（UTC）、有效点数、被拒绝行数、
缺失列行数（`missing_value_count`，按**行**统计，不是缺失单元格数）、
非有限值 / 重复磁场值数量、磁场最小最大值、信号最小最大/均值/标准差、
磁场单调性、索引连续性、软件版本、全部校验警告，以及原始文件是否未被改动。

此外：

- `outputs`：本次运行实际生成的 CSV、PNG、JSON 路径。
- `processing`：本次运行的绘图参数（figsize、dpi、线宽），以及
  `smoothing` / `baseline_correction` / `normalisation` / `field_axis_reversal`
  均为 `false`。该字段**只描述本次运行**，不是对未来运行的保证。

CSV 中的 `index`：仅当所有值都是有效整数时以整数写出（`1` 而不是 `1.0`）；
非整数或无效值原样保留，绝不强制取整。

### 4.3 批次汇总 `batch_summary.json`

```json
{
  "batch": {
    "processed_at_utc": "2026-10-26T11:08:10+00:00",
    "timezone": "All timestamps are UTC (datetime.now(timezone.utc)).",
    "input_dir": "D:\\EPR workflow\\data\\raw",
    "output_dir": "D:\\EPR workflow\\results\\batch_integration_20261026",
    "recursive": false,
    "files_discovered": 2,
    "files_succeeded": 2,
    "files_succeeded_with_warnings": 0,
    "files_failed": 0,
    "overall_status": "success",
    "errors": []
  },
  "files": [ ... ]
}
```

- 每个文件单独记录 `status`：`success`（无警告）、`success_with_warnings`（已处理但有校验警告）、
  `failed`（未处理或无法产出结果）。
- `overall_status`：`success`、`success_with_warnings`、`partial_failure` 或 `failed`。
- 每个文件还包含源文件 SHA-256（处理前后）、字段范围、输出路径、警告与错误信息。
- 退出码：所有文件成功（含仅有警告）为 `0`，任一文件失败为 `1`。
- 汇总中明确说明：**脚本跑完不代表数据在科学上已被验证**。

批次失败与警告同时打印到控制台（`[1/2] FAILED: xxx.ASC` 等），并写入汇总，
不会静默跳过。

### 4.4 处理结果（基线校正 / Savitzky–Golay 平滑）

文件后缀取决于实际应用的处理：

| 处理历史 | 文件 |
| --- | --- |
| 仅线性基线校正 | `<sample>_baseline.csv/.png/_metadata.json` |
| 仅 Savitzky–Golay 平滑 | `<sample>_smoothed.csv/.png/_metadata.json` |
| 基线校正 + 平滑 | `<sample>_baseline_smoothed.csv/.png/_metadata.json` |

- 仅基线校正的 CSV 列沿用第一阶段：
  `index, field_G, intensity_raw, intensity_corrected, baseline_removed`。
- 含平滑的 CSV 列：`index, field_G, intensity_raw, intensity_corrected,
  difference_from_raw`；最后一列是**原始减去处理后**的总变化，不是拟合基线。
- PNG 与 JSON 使用**英文**（与现有原始导出保持一致）；GUI 界面文字仍可中英文切换。
- JSON 中的 `preprocessing` 块记录：`schema_version`、`data_kind`、
  算法名称与版本、步骤顺序、每一步的参数与输入来源、基线窗口坐标/点数/拟合参数、
  平滑窗口长度/阶数/变化统计、应用时间（UTC）、源文件 SHA-256、软件版本
  （含 SciPy）、警告、假设、`not_applied` 列表，以及输出列说明。
- 顶层同时写入 `data_kind`（`baseline_corrected`、`smoothed` 或
  `baseline_corrected_and_smoothed`），与原始数据导出明确区分。
- 同时更新 `processing.applied_in_this_run` 标志与
  `preprocessing_step_order`。原始数据导出的 JSON 结构不变。
- 导出会在写盘前校验源文件 SHA-256；若源文件在导入后发生变化，导出被拒绝。

### 4.5 Plot Editor 图片 `<sample>_plot.png`

- 默认位置：`<output-dir>\figures\<sample>_plot.png`（可在导出对话框中修改）。
- 内容为 Plot Editor 当前预览的 Matplotlib 图像，包含当时可见的曲线、标题/标签、
  范围、图例、字体和线型；不包含 GUI 控件或窗口边框。
- 自动标题、坐标轴标签与曲线默认名称使用**导出时界面语言**；用户自定义的文字原样
  保留。这与 4.4 中处理结果 PNG/JSON 固定使用英文的规则不同。
- 尺寸、DPI、是否包含标题/图例由导出对话框决定；默认 `8 × 5 in`、`300 dpi`。
- 该文件是**显示输出**，不是新的科学数据记录；不会生成或修改 CSV/JSON。
- 导出不会改变原始数据文件、已导出的 `_raw` 结果或当前会话的预处理历史。

### 4.6 BES3T 导入输出

- 原始导出命名与 ASC 相同：`<sample>_raw.csv`、`<sample>_raw.png`、
  `<sample>_metadata.json`，其中 `<sample>` 是 `.DSC` 文件名主干。
- BES3T 原始 CSV 在历史三列之后增加常量列
  `source_format`（值为 `BES3T`），用于在文件层面区分来源格式；
  ASC CSV 仍保持 `index, field_G, intensity` 三列不变。
- BES3T 处理结果 CSV 同样在末尾增加 `source_format=BES3T`；
  原始强度列仍为 `intensity_raw`，处理后为 `intensity_corrected`。
- JSON 顶层增加：
  - `source_format`：`BES3T`；
  - `source_files`：DSC 与 DTA 的角色、绝对路径、文件名、前后 SHA-256、
    文件大小及未变标志；
  - `sha256_definition`：组合 SHA-256 的定义；
  - `file_size_bytes_definition`：文件大小为两者之和；
  - `format_metadata`：原始描述文本、`#DESC`/`#SPL`/`#DSL` 记录、
    解析参数、推断参数、轴定义、二进制类型/字节序、诊断；
  - `assumptions`：BES3T 专用假设。
- `sha256` 是 DSC SHA-256 与 DTA SHA-256 按 `BES3T:<dsc>:<dta>` 组合后的
  SHA-256，不是任一单文件哈希；两个源文件中任一改变都会使来源校验失败。
- `data/raw` 写入防护、源文件覆盖防护、处理结果覆盖保护同样适用于 DSC 与 DTA；
  Plot Editor 导出也会拒绝把 DSC 或 DTA 当作输出路径。

## 5. 支持的数据格式与假设

### 5.1 Xepr ASCII `.ASC`

1. 纯文本，空白（空格/Tab）分隔，**三列**。
2. 表头行包含 `index`、`Field [G]`、`Intensity []` 三个关键字，且按此顺序。
   表中若出现其他列或顺序不同，程序会**报错而不是猜测**列含义。
3. 第 1 列仅作行索引，不当作物理量。
4. 第 2 列磁场单位为 **Gauss (G)**。
5. 第 3 列强度无文档单位，报告为 **original units**（不虚构单位）。
6. 空行被忽略；无法解析的行被**记录并排除**，同时给出警告和行号。
7. 数据行顺序被原样保留，不排序。
8. 线性基线校正假设：强度基线在所显示的磁场范围内可由一条直线表示，
   且基线在未记录单位的强度上是可加的。该假设由用户判断，程序不验证。
9. Savitzky–Golay 平滑假设：局部窗口内的信号可由低阶多项式近似；
   平滑会改变峰高、峰宽和线形，不代表数据质量一定改善。

### 5.2 Bruker BES3T `.DSC` + `.DTA`

第一版只支持**一维、实数值**的 BES3T 数据集。读取流程：

1. 以 `.DSC` 描述文件为入口，在其所在目录查找同名 `.DTA`
   （文件名主干大小写不敏感）；`.DTA` 不能单独打开。
2. 解析 `#DESC` 层，要求以下参数存在且可验证：
   - `BSEQ`：`BIG` 或 `LIT`；不使用未经验证的默认字节序。
   - `IKKF`：仅接受单个 `REAL`；`CPLX` 或多重值被拒绝。
   - `IRFMT`：仅接受单个 `C`/`S`/`I`/`F`/`D`
     （int8/int16/int32/float32/float64）。
   - `XTYP`：仅接受 `IDX`；`IGD`（外部 `.XGF` 轴）与 `NTUP` 未实现。
   - `XPTS`：正整数且至少为 3。
   - `XMIN`、`XWID`：有限数值，`XWID` 不得为 0。
   - `XUNI`：仅接受 `G`（Gauss）；当前不做 mT 等单位换算。
3. `YPTS`/`ZPTS` 缺失时按 BES3T 规范推断为 1，并在来源记录中标记为
   `inferred_parameters`；若显式给出大于 1，或 `YTYP`/`ZTYP` 不是 `NODATA`，
   则作为多维数据拒绝。
4. 线性轴按 `linspace(XMIN, XMIN + XWID, XPTS)` 构造，**包含两个端点**。
   因此相邻点步长为 `XWID / (XPTS - 1)`，不是 `XWID / XPTS`。
5. 根据 `IRFMT` 与 `BSEQ` 解码 `DTA`，并严格检查期望字节数：
   少于期望值报“截断”，多于期望值报“尾随字节”，不会静默截断或补齐。
6. 保留原始点顺序；不排序、不插值、不缩放、不平滑、不做基线校正。
7. 原始描述文本、全部 `#DESC`/`#SPL`/`#DSL` 记录、解析值、推断值、
   两个源文件的 SHA-256 和文件大小写入 JSON 来源记录。
8. 实数整数类型在内存中转换为 float64，以复用现有数据处理模型；
   数值本身不改变，并在 assumptions 中记录。

不支持：复数、多维、`IGD` 轴、`NTUP` 轴、非 Gauss 轴单位、
多谐波/每点多值布局、缺失必需元数据、截断数据和尾随字节。
遇到这些情况会明确报错，不会猜测或强行读取。

`Test data\` 中的 `BSA3mal1h.DSC`/`.DTA` 是本地验证样本，不随仓库上传。

本版本对该真实样本的验证结果：

- `XPTS=1024`，`DTA` 为 8192 字节，符合 1024 × 8 字节。
- `IRFMT=D`、`BSEQ=BIG`，按大端 float64 解码。
- `XMIN=3310`、`XWID=100`，构造轴为 3310–3410 G，包含 1024 点。
- 首三个强度值为 `-76, -69, -67`，末点为 `-84`；数值与原始二进制一致。
- 测试前后 DSC 与 DTA 的 SHA-256 均未改变。

未提供该样本对应的 Xepr ASCII 导出，因此**尚未完成逐点跨格式比较**；
这一项仍待补充真实的 `.ASC` 导出后验证。仅成功绘图不构成解析正确的充分证据。

## 6. 校验规则

- 行数不足 3 个有效点时拒绝绘图。
- 磁场列必须严格递增或严格递减；非单调时默认**报错退出**，不生成图。
- 诊断信息区分“重复磁场值”与“递减步”，重复点不会被删除或合并。
- NaN / Inf 行被识别并排除，计数写入报告。
- 重复磁场值会使磁场轴判定为非单调：默认报错退出；使用
  `--allow-non-monotonic` 时给出警告，且数据不会被删除或合并。
- 索引连续性是**警告**而非错误：仅当 index 为整数且严格递增时检查是否存在跳号；
  不假设所有文件都从 1 开始，也不排序、不重新编号。
- 磁场轴**不反转**（未获得采集元数据授权）。
- 运行结束后重新计算原始文件 SHA-256，确认数据文件未被修改。
- GUI 基线校正只接受严格单调的磁场轴；重复值或非单调轴直接拒绝，不排序、不修复。
- 基线处理结果不会替换原始数据；撤销与重置都从原始数组按记录步骤重算。
- Savitzky–Golay 窗口长度必须为奇数、至少 3、且不超过数据点数；
  多项式阶数必须满足 `0 ≤ polyorder < window_length`；输入必须全部有限。
- 平滑不改变数据点数量、磁场轴或行序；不执行缩放、归一化或去点。
- BES3T `.DSC`/`.DTA` 配对按文件名主干大小写不敏感匹配；不把同名不匹配的
  `.DTA` 自动配对。
- BES3T 必需参数缺失、重复或类型错误时直接拒绝；不采用静默默认值。
- BES3T `DTA` 字节数必须严格等于 `XPTS × 每点字节数`；截断或尾随字节均拒绝。
- BES3T 轴必须由 `XMIN`/`XWID`/`XPTS` 构造成严格单调；不排序、不反转、
  不替换缺失轴。
- 非有限 BES3T 强度整份数据拒绝，不删除单点后继续。
- 导入后重新计算 DSC 与 DTA 的 SHA-256；任一文件改变即认为来源已变。

## 7. 当前限制

- 只支持上述三列 Xepr ASCII `.ASC`，以及本版本明确限定的一维实数
  BES3T `.DSC`/`.DTA`；不解析 PAR/SPC、二维/三维 BES3T、复数数据、
  `IGD` 外部轴文件或 `NTUP` 轴。
- BES3T 轴单位目前只接受 `G`；不会自动把 mT 等单位换算为 G。
- BES3T 的 `DSRC` 若不是 `EXP` 会给出警告，但程序不会仅凭该字段判断
  数据的科学有效性。
- 不读取 Xepr 的采集参数（微波频率、功率、调制幅度、时间常数等），
  因此图中不标注任何未经验证的实验条件。
- 不区分吸收谱 / 一阶导数谱，也不判断信号类型。
- 批处理只扫描指定目录；`--recursive` 为显式选项，默认不进入子目录。
- 输出命名冲突（例如 `--recursive` 下 `a_b\C.ASC` 与 `a\b_C.ASC`）
  会使相关文件直接失败，而不是自动改名。
- `requirements.txt` 只列直接依赖，未固定间接依赖（SciPy 已作为直接依赖列出）。
- GUI 中由 `plot_asc.py` 生成的核心校验警告与异常文本保持**英文原文**：
  这些文本同时写入 JSON 元数据与批次汇总，属于科学记录，GUI 只翻译其标题与说明。
- GUI 绘图中的中文坐标轴标题/图名使用系统 CJK 字体（优先 Microsoft YaHei）；
  若系统没有可用中文字体，中文标签可能显示为方框，数据本身不受影响。
- 语言偏好文件 `config\gui_settings.ini` 若无法创建，GUI 仍可正常运行，
  只是不保存语言选择（每次启动回到简体中文）。
- 平滑会改变峰高、峰宽与线形；曲线更光滑**不代表**数据质量提高，
  也不能替代对原始谱线的科学判断。
- 平滑输入选择“原始数据”且已有处理步骤时，会改变处理顺序（先平滑、后原有步骤），
  界面和 JSON 会记录新顺序并给出警告。
- 基线窗口由用户给定，程序不判断其是否真的是基线；预览与诊断只是辅助。
- 窗口输入精度为 0.0001 G；实际使用的坐标会原样写入处理记录。
- 撤销/重置不会删除已经导出的处理结果文件，也不会改变原始 `_raw` 输出。
- Plot Editor 的曲线列表只包含当前预处理结果实际提供的曲线；不缓存“校正后但尚未
  平滑”等中间数组，也不会为绘图临时重算中间结果。
- 拟合基线只在基线校正步骤记录了拟合参数时出现，默认隐藏；它是拟合辅助线，
  **不是实验信号**。
- 绘图设置只保存在当前程序会话内，关闭程序后丢失；不写入 `config` 或科学数据文件。
- Plot Editor 导出的 PNG 是显示输出，不替代 CSV/JSON 处理记录，也不构成新的科学分析。
- 字体大小以整数 pt 设置（6–40）；画布尺寸以英寸设置，DPI 上限为 1200。
- 只有 PNG 导出；不提供矢量图（SVG/PDF）或批量绘图设置导出。
- 核心校验警告、控制台输出与 JSON 日志仍为英文；处理步骤的错误与警告在 GUI 中
  提供中英文，导出记录按设计保持英文。

## 8. 运行测试

```powershell
cd "D:\EPR workflow"
.\.venv\Scripts\python.exe -m pytest -v
```

测试覆盖：正常读取、空行/表头、列映射、畸形行、非有限值、非单调磁场、
文件缺失、非法数据不生成图、原始文件不被修改，以及对真实实验文件的端到端导入。
回归测试还会检查：CSV 回读值与源数据逐值一致、整数索引不被写成浮点、
非整数索引不被取整、元数据统计量与独立重算一致、`BSA3T275.ASC` 的
1024 点 / 3280–3380 G / 首点 400.088，以及索引跳号与重复磁场的诊断行为。
批处理测试覆盖：多文件处理、顺序确定性、扩展名大小写、单文件失败后继续、
空目录 / 目录不存在、覆盖保护、输出名冲突、汇总计数与状态、
源文件哈希不变、不排序不处理，以及单文件模式兼容。
GUI 测试覆盖：controller 核心逻辑（读取、警告、错误处理、批处理状态、覆盖保护、
源文件不变、非单调、输出名冲突、状态映射）以及 PySide6 窗口的离屏冒烟测试。
界面语言测试覆盖：中英文词典键集合一致、缺失键与未知语言回退、状态/总体状态/
磁场方向翻译、实时切换后窗口控件/元数据/绘图/光标/批次汇总与工具栏提示同步更新、
切换不重读文件且不重新处理、选中样品与批次结果保持、语言偏好持久化与非法值回退、
中英文标签布局尺寸，以及控件行的结构检查。
预处理测试覆盖：窗口校验（顺序、越界、点数不足、重叠、共享端点、间隔不足、
重复/非单调磁场）、拟合与校正数值（已知直线、峰保留、递减磁场、重复调用确定性、
1e7 偏置下的精度）、输入只读与结果只读、预览不提交、应用/撤销/重置、
处理记录字段与严格 JSON。
Savitzky–Golay 测试覆盖：常数输入保持常数、无效/偶数窗口、阶数非法、点数不足、
非有限值、SciPy 缺失、输出长度与磁场顺序、已知双峰的峰位/峰高/半高宽/峰间距变化、
噪声平滑效果、原始/当前结果两种输入、原始输入时的顺序调整与警告、预览/应用/
撤销/重置、结果缓存、处理记录与数据类型。
处理导出测试覆盖：CSV 列与逐值一致、覆盖保护、`data/raw` 写入防护、
预览/无步骤/源文件变化拒绝导出、元数据声明（算法版本、数据类型、输出列）与英文输出；
平滑与混合导出的 `_smoothed` / `_baseline_smoothed` 命名、`difference_from_raw`
列、处理顺序与输入来源。
GUI 预处理测试覆盖：默认未选择任何区间、平滑默认关闭、面板启用状态、预览三曲线
且不写文件、参数变更使预览失效、取消预览、应用/撤销/重置、双语切换保持状态且
不重新拟合/平滑、错误提示翻译、按文件会话、源文件变化作废会话、导出与打开按钮、
覆盖保护，以及全流程源文件哈希不变。
Plot Editor 测试覆盖：曲线按实际预处理结果动态出现、拟合基线默认隐藏且由已记录
参数求值（不重新拟合）、可见性/名称/颜色/线宽/线型、标题与空标签、自动/手动范围
与非法范围报错、图例位置、字号、重置与恢复默认可见性、按样品保存与恢复、语言切换
不重读原始数据且不重新处理、未应用预览时禁止导出、无可见曲线报错、默认路径与覆盖保护、
导出图像尺寸/DPI、包含标题/图例选项、源文件哈希不变，以及不修改已有 CSV/JSON。
BES3T 测试覆盖：有效一维实数数据、点数与逐值一致、大端/小端、float64/float32/
整数格式、轴公式与端点、单文件/批量/CLI/GUI/处理导出集成、DTA 不被当作独立数据集、
缺失 DSC/DTA、大小写扩展名、必需参数缺失/重复/非法、复数、多维、IGD/mT/A 格式、
零宽度/点数不足、截断与尾随字节、非有限值、DSC 与 DTA 哈希不变，以及真实
`BSA3mal1h` 样本的 1024 点/3310–3410 G/首末值检查。真实样本不存在时该测试自动跳过。
Plot Editor 的纯逻辑与导出器也分别有独立测试，使用临时目录和合成数据；
测试中的错误输入不会写入实验数据目录。
当前完整测试结果：**298 passed, 1 skipped**（跳过项为 Windows 上无法构造的
大小写歧义伴随文件；真实 BES3T 样本在本机存在时会实际执行）。

## 9. 目录结构

```text
EPR workflow\
├── .venv\
├── data\raw\            # 原始实验数据（只读）
├── Test data\           # 本地 BES3T 验证样本（不随仓库上传）
├── results\figures\     # 输出图片
├── results\tables\      # 输出表格
├── results\logs\        # 输出报告与批处理汇总
├── 启动 EPR Workflow.bat  # 双击启动 GUI
├── src\epr_workflow\
│   ├── __init__.py
│   ├── plot_asc.py       # ASC 导入 / 校验 / 绘图 / 导出 / 批处理
│   ├── bes3t.py          # BES3T .DSC/.DTA 严格读取（无 Qt）
│   ├── preprocessing.py  # 基线校正 + Savitzky–Golay（纯 NumPy/SciPy，无 Qt）
│   ├── plot_settings.py  # Plot Editor 设置模型与统一绘图函数（无 Qt）
│   ├── plot_export.py    # PNG 绘图导出（独立 Agg 图形，原子写入）
│   ├── processed_export.py # 处理结果 CSV/PNG/JSON 导出
│   └── gui\
│       ├── __init__.py
│       ├── i18n.py       # 中英文界面文案（无 Qt 依赖）
│       ├── controller.py # GUI 核心逻辑（无 Qt 依赖，可测试）
│       ├── preprocessing_panel.py # 预处理面板（只发信号）
│       ├── plot_editor_panel.py # 绘图设置面板（只发信号）
│       ├── plot_export_dialog.py # 绘图 PNG 导出对话框
│       ├── mpl_canvas.py # matplotlib 画布 + 缩放/平移工具栏
│       ├── main_window.py# PySide6 界面
│       ├── app.py        # 启动入口
│       └── __main__.py   # python -m epr_workflow.gui
├── run_gui.py            # GUI 启动脚本
├── config\gui_settings.ini  # GUI 语言偏好（首次切换语言后生成）
├── tests\
│   ├── test_plot_asc.py
│   ├── test_batch.py
│   ├── test_bes3t.py
│   ├── test_preprocessing.py
│   ├── test_savgol.py
│   ├── test_processed_export.py
│   ├── test_plot_settings.py
│   ├── test_plot_export.py
│   ├── test_gui_controller.py
│   ├── test_gui_i18n.py
│   ├── test_gui_preprocessing.py
│   ├── test_gui_plot_editor.py
│   ├── test_gui_bes3t.py
│   └── test_gui_widgets.py
├── conftest.py
├── requirements.txt
├── CHANGELOG.md           # 版本更新公告
├── README.md              # 中文说明
└── README.en.md           # English documentation
```
