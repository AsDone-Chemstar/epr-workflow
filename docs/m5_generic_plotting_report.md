# M5 报告：通用绘图基础与原始/处理谱支持

- 状态：**M5 完成**
- 基线版本：EPR Workflow **v0.2.0**
- Git 基线：`327d5f6`
- 前序测试基线：M4 **423 passed, 1 skipped**
- M5 基线：**447 passed, 1 skipped**
- 日期：2026-11-02
- 范围：只新增技术无关的绘图数据、配置和 Matplotlib axes 渲染基础
- 现有 EPR plotting、GUI、CLI、PNG 导出：**未修改**
- Git：**未 commit、未 push**

---

## 1. 实现前的现有绘图检查

检查了：

- `src/epr_workflow/plot_asc.py`
- `src/epr_workflow/plot_settings.py`
- `src/epr_workflow/plot_export.py`
- `src/epr_workflow/gui/mpl_canvas.py`
- `src/epr_workflow/gui/main_window.py`
- `src/epr_workflow/gui/plot_editor_panel.py`
- `tests/test_plot_settings.py`
- `tests/test_plot_export.py`
- `tests/test_gui_plot_editor.py`
- M0–M4 报告及现有 `Spectrum1D`/`ProcessedSpectrum` API

### 现有绘图职责

- `plot_asc.plot_spectrum()`：从 DataFrame 直接绘制原始 EPR 谱并保存 PNG，固定使用
  `field_G`、`intensity`、磁场/强度标签。
- `plot_settings`：曲线样式、轴设置、图例、标签 key、`build_curves()`、
  `draw_spectrum()`、按源文件的样式缓存。
- `plot_export`：使用旧 `CurveData`/`PlotSettings`/`draw_spectrum` 导出 PNG。
- `gui/mpl_canvas`：Qt 内嵌 Matplotlib 画布。
- `gui/main_window`、`plot_editor_panel`：EPR 专用加载、预处理、曲线、标签和导出交互。

### 现有 EPR 绘图假设

- 固定列名 `field_G` / `intensity`
- 固定标签 `Magnetic field (G)` / `Intensity`
- 固定曲线键 `raw` / `processed` / `difference` / `fitted_baseline`
- 固定 EPR 曲线默认颜色、虚线、图例文本
- 旧 `PlotSettings`/`CurveStyle`/`PreprocessingResult` 类型
- GUI 直接依赖 Qt 和 EPR 语义

这些保持原样，没有迁移到 generic core。

### 可共享的绘图职责

- X/Y 数据提取
- 轴/信号名称与单位显示
- 标题和显式标签覆盖
- 线型、线宽、颜色
- 显式轴范围
- 网格和图例开关
- Matplotlib `Axes` 绘制
- 原始/处理系列的明确区分

---

## 2. 新增与修改文件

### 新增通用绘图模块

- [src/spectralab/core/plotting/__init__.py](../src/spectralab/core/plotting/__init__.py)
- [src/spectralab/core/plotting/series.py](../src/spectralab/core/plotting/series.py)
- [src/spectralab/core/plotting/settings.py](../src/spectralab/core/plotting/settings.py)
- [src/spectralab/core/plotting/renderer.py](../src/spectralab/core/plotting/renderer.py)

### 修改中立核心

- [src/spectralab/core/errors.py](../src/spectralab/core/errors.py)：新增 `PlottingError`
- [src/spectralab/core/__init__.py](../src/spectralab/core/__init__.py)：导出 plotting API

### 新增测试

- [tests/test_plotting.py](../tests/test_plotting.py)：20 个测试
- [tests/test_m5_architecture.py](../tests/test_m5_architecture.py)：4 个测试

合计 **24 个新测试**。

### 新增/更新文档

- 本报告
- [docs/architecture_proposal.md](architecture_proposal.md)：更新 M5 状态、实际范围和测试基线
- M4 报告页脚更新为已进入 M5

### 未修改

- `src/epr_workflow/plot_asc.py`
- `src/epr_workflow/plot_settings.py`
- `src/epr_workflow/plot_export.py`
- 现有 GUI、CLI、批处理
- 现有 CSV/JSON/PNG schema
- 现有测试、原始数据、配置
- `requirements.txt`

---

## 3. 通用绘图 API

### 3.1 `Series1D`

模块：`spectralab.core.plotting.series`

```python
@dataclass(frozen=True)
class Series1D:
    kind: Literal["raw", "processed"]
    axis: Axis1D
    signal: Signal1D
    label: str
    dataset_id: str
```

属性：

- `x_values` / `x`
- `y_values` / `y`
- `point_count`
- `is_raw`

特点：

- 只引用已有的只读 `Axis1D`/`Signal1D`；
- 不复制、不排序、不反转、不裁剪、不插值；
- 不执行科学处理；
- 检查 axis/signal 长度一致；
- 检查非有限值并显式拒绝。

### 3.2 数据提取

```python
series_from_spectrum(spectrum, *, label="Raw") -> tuple[Series1D, ...]
series_from_processed(processed, *, include_raw=True,
                      raw_label="Raw", processed_label="Processed")
build_series(source, *, config=None, include_raw=True)
```

- `Spectrum1D` → 一个 `kind="raw"` 系列；
- `ProcessedSpectrum` → 默认 raw + processed 两个系列；
- `include_raw=False` 可只绘制 processed；
- 原始系列使用 `processed.source`，不重放处理。

### 3.3 标签格式化

```python
format_axis_label(axis) -> str
format_signal_label(signal) -> str
```

规则：

- name + unit → `"Name (unit)"`
- 只有 name → `"Name"`
- 只有 unit → `"unit"`
- 两者都未知 → `""`

不使用数值范围猜测单位，不把 `quantity="unknown"` 自动映射成物理标签。

### 3.4 `LineStyle`

```python
@dataclass(frozen=True)
class LineStyle:
    color: str = "#1f4e79"
    linewidth: float = 1.0
    linestyle: str = "-"
```

- 颜色限定 `#RRGGBB`；
- 线宽必须是有限正数；
- 线型限定 `-`、`--`、`:`、`-.`。

### 3.5 `PlotConfig`

```python
@dataclass(frozen=True)
class PlotConfig:
    title: str | None = None
    xlabel: str | None = None
    ylabel: str | None = None
    xlim: tuple[float, float] | None = None
    ylim: tuple[float, float] | None = None
    grid_visible: bool = True
    legend_visible: bool = True
    legend_location: str = "best"
    raw_label: str = "Raw"
    processed_label: str = "Processed"
    raw_style: LineStyle = LineStyle("#7f7f7f", 0.8, "--")
    processed_style: LineStyle = LineStyle("#1f4e79", 1.0, "-")
```

行为：

- `title`/`xlabel`/`ylabel` 为 `None` 时从已记录元数据推导；
- 显式字符串覆盖元数据；
- `""` 是显式空标签，不会回退到元数据；
- x/y limits 只在显式提供时设置；
- grid/legend 都是显式配置；
- raw 和 processed 默认使用不同标签、颜色和线型。

### 3.6 渲染

```python
render_series(axes, series, config=None, *, title=None) -> list[Line2D]
plot_spectrum(axes, source, config=None, *, include_raw=True) -> list[Line2D]
```

- 接受 Matplotlib `Axes`；
- `plot_spectrum` 接受 `Spectrum1D` 或 `ProcessedSpectrum`；
- 先清除 axes，再按 series 顺序绘制；
- 保留传入 X/Y 的点序；
- 设置标题、轴标签、limits、grid、legend；
- 返回实际创建的 Matplotlib line 对象。

### 3.7 错误

`PlottingError` 具有稳定 `code`/`context`：

- `plot_unsupported_input`
- `plot_series_data`
- `plot_series_kind`
- `plot_nonfinite_data`
- `plot_no_series`
- `plot_config`
- `plot_line_style`
- `plot_limits`
- `plot_legend`
- `plot_ambiguous_xlabel`
- `plot_ambiguous_ylabel`

---

## 4. 原始/处理谱区分

- `Series1D.kind` 明确为 `"raw"` 或 `"processed"`；
- raw 使用 `PlotConfig.raw_label`，processed 使用 `processed_label`；
- 默认 raw 为灰色虚线、processed 为蓝色实线；
- `ProcessedSpectrum` 默认同时绘制 raw 与 processed；
- `include_raw=False` 可只绘制 processed；
- raw 数据来自 `ProcessedSpectrum.source`，processed 数据来自当前 `axis/signal`；
- 不把 processed 数据重新包装成 `Spectrum1D`；
- 不重放处理历史，不修改处理状态。

---

## 5. 未知元数据与安全行为

- 轴 name/unit 两者未知时，标签为空字符串；
- 信号 name/unit 两者未知时，标签为空字符串；
- 只有单位时只显示单位；
- 不从数值范围、技术名称或文件扩展名推断单位；
- 多个 series 的轴标签不同且没有显式 `xlabel` 时，抛出
  `plot_ambiguous_xlabel`；
- 多个 series 的信号标签不同且没有显式 `ylabel` 时，抛出
  `plot_ambiguous_ylabel`；
- 显式标签可以安全覆盖这种歧义；
- 非有限数据直接拒绝；
- 类型、长度、颜色、线宽、limits、legend location 都显式验证。

---

## 6. 输入不可变性

- `Series1D` 引用已有只读 `Axis1D`/`Signal1D`，不写回；
- 渲染只调用 `axes.plot(x, y, ...)`；
- 不排序、不反转、不裁剪、不插值、不重采样；
- 不调用任何 M4 processing 操作；
- 不修改 `Spectrum1D` 或 `ProcessedSpectrum`；
- 不修改源数据文件；
- 测试比较输入/输出数组和只读标志，并直接检查传给 Matplotlib 的
  `Line2D` X/Y 数据。

---

## 7. 架构依赖结果

- `spectralab.core.plotting` 不导入 Qt、GUI、`epr_workflow`、
  `spectralab.app` 或 `spectralab.techniques`；
- core plotting 不包含 `field_G`、`intensity`、`magnetic_field`、`Field [G]`、
  `CW-EPR`；
- 导入 core plotting 不加载 Qt、EPR 或 Matplotlib；
- core plotting 导入图无循环；
- 没有将新 plotting 接入旧 GUI/CLI；
- 没有新增依赖；
- 没有修改 M3 raw export；
- 没有修改 M4 processing。

---

## 8. 测试与回归结果

新增 **24 个 M5 测试**：

- `tests/test_plotting.py`：20
- `tests/test_m5_architecture.py`：4

测试覆盖：

- `Spectrum1D` 和 `ProcessedSpectrum`
- 精确 X/Y 提取
- 递增/递减轴保持
- 未知轴/信号元数据
- 显式标签和标题覆盖
- 显式 limits
- line style/width/color
- grid/legend
- 输入不可变
- 非有限值、类型、配置错误
- 歧义标签错误
- core import 边界和循环
- 无 Qt/EPR/Matplotlib 导入

实际运行：

```text
完整测试集 pytest -v：
447 passed, 1 skipped
exit code 0

pytest -q -W error::UserWarning：
447 passed, 1 skipped
exit code 0

原 EPR 测试集（排除 M0–M5 测试）：
298 passed, 1 skipped
exit code 0
```

日志：

- `results/logs/pytest_m5_20261102_verbose.txt`
- `results/logs/pytest_m5_20261102_userwarning.txt`
- `results/logs/pytest_m5_20261102_original.txt`

---

## 9. 向后兼容

- 现有 `epr_workflow` plotting/export/GUI 代码未修改；
- 现有 ASC/BES3T、preprocessing、CLI、批处理未修改；
- 现有 CSV/JSON schema 未修改；
- 现有测试未修改；
- 原 EPR 测试 298 passed / 1 skipped 不变；
- 新 plotting 没有接入旧 GUI 或 PNG 导出；
- 删除新增模块即可回滚；
- 无新增依赖，`requirements.txt` 未修改。

---

## 10. 剩余限制与风险

1. M5 只提供 generic series/config/axes renderer；没有 PNG 文件导出。
2. 没有新增 `techniques/epr/plotting_defaults.py`，没有把旧
   `draw_spectrum`/`build_curves` 改为兼容包装；旧 EPR renderer 完全保留。
3. 没有 GUI 集成、Plot Editor 迁移、CLI 或批处理集成。
4. 没有多谱叠加、差谱、峰检测、复杂信号或二维谱。
5. `PlotConfig` 没有字体大小、图尺寸、DPI 等输出设置；这些属于后续
   exporter/应用层。
6. generic renderer 需要调用方提供 Matplotlib `Axes`；不负责创建 figure。
7. `Series1D` 复用输入只读数组，不做防御性深复制；输入对象本身若被非正常
   改写，系列也会看到变化。正常 `Spectrum1D`/`ProcessedSpectrum` 保证只读。
8. 轴/信号标签只使用 name/unit；当两者均未知时保持空白，不根据 quantity 或数值
   范围发明标签。
9. `ProcessedSpectrum` 默认同时画 raw 和 processed；如需只画 processed，
   必须显式 `include_raw=False`。
10. 没有把 `ProcessedSpectrum` 导出为 M3 原始 schema；M5 不改变 M3。
11. 未新增 `tests/core/plotting/` 子目录，继续采用仓库扁平 `tests/` 结构。

---

## 11. M5 完成清单

- [x] `Series1D`
- [x] `Spectrum1D` series extraction
- [x] `ProcessedSpectrum` raw/processed series extraction
- [x] raw/processed 明确 kind 与标签
- [x] X/Y 数值和点序保持
- [x] 递增/递减轴
- [x] 未知元数据不发明标签
- [x] 显式标签/标题覆盖
- [x] line style/width/color
- [x] 显式 xlim/ylim
- [x] grid/legend 配置
- [x] Matplotlib axes renderer
- [x] 输入只读/不变
- [x] 非有限值和非法输入显式错误
- [x] core 不导入 Qt/EPR/app/techniques/Matplotlib
- [x] 无循环导入
- [x] 原 EPR 测试 298 passed / 1 skipped
- [x] 完整测试 447 passed / 1 skipped
- [x] `-W error::UserWarning` 通过
- [x] 未 commit、未 push

**M5 状态：完成。** M6 见 [M6 通用 CLI/Batch 报告](m6_cli_batch_report.md)，
M7 见 [M7 EPR Backend Closure 报告](m7_epr_backend_closure_report.md)，M8 见
[M8 GUI Architecture 报告](m8_gui_architecture_report.md)；M9 尚未开始。
