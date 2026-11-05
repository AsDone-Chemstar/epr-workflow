# M4 报告：通用 ProcessingSession / ProcessedSpectrum 与 EPR 处理适配

- 状态：**M4 完成**
- 基线版本：EPR Workflow **v0.2.0**
- Git 基线：`327d5f6`
- 前序测试基线：M3 **384 passed, 1 skipped**
- M4 基线：**423 passed, 1 skipped**
- 日期：2026-11-02
- 范围：只实现通用一维处理会话、操作记录、ProcessedSpectrum 和 EPR 线性基线/Savitzky-Golay 适配
- 现有生产行为：**未改变**
- 现有 EPR 代码、preprocessing、GUI、CLI、CSV/JSON schema：**未修改**
- Git：**未 commit、未 push**

---

## 1. 已检查的现有 EPR preprocessing 行为

在实现前检查了 `src/epr_workflow/preprocessing.py`、`tests/test_preprocessing.py`、
`tests/test_savgol.py` 和现有 GUI 预处理调用链。

### 实际支持的操作

现有实现只实际支持两类操作：

1. **线性基线校正**
   - `BaselineWindow(start_G, end_G)`，闭区间；
   - `LinearBaselineSpec(window_left, window_right)`；
   - 两个窗口不得重叠，必须至少保留一个未选点；
   - 每个窗口至少 3 点；
   - 磁场轴必须严格单调；
   - 使用两个窗口的并集做普通最小二乘直线拟合；
   - 输出：
     `intensity_corrected = intensity_input - (slope * field_G + intercept)`；
   - 无加权、无自动窗口、无橡胶带、无多项式基线；
   - 产生空窗口、覆盖率、外推、噪声等警告。

2. **Savitzky–Golay 平滑**
   - `SavgolSpec(window_length, polyorder, deriv=0, mode="interp")`；
   - 调用 `scipy.signal.savgol_filter`；
   - `window_length` 必须为奇数且至少 3；
   - `polyorder` 必须满足 `0 <= polyorder < window_length`；
   - 只支持 `deriv=0`、`mode="interp"`；
   - 不做归一化、裁剪或离群点处理。

### 现有会话行为

`epr_workflow.preprocessing.PreprocessingSession` 已经提供：

- 原始数组复制并设为只读；
- preview / discard preview / apply；
- baseline 与 Savgol；
- smoothing 可以选择 raw 或 current 输入，并把 raw 输入的 smoothing
  插入到已有步骤之前；
- undo 和 reset；
- 每次从原始数组重新计算；
- 记录操作、拟合结果、警告和时间戳；
- 生成现有 EPR JSON preprocessing record。

现有实现**没有 redo**。现有 preview、raw-input 重排和旧 JSON record
是 EPR 应用层行为，没有直接复制到 generic core。

### 未支持的操作

现有实现没有：

- 归一化；
- 多项式或橡胶带基线；
- 手动/自动峰检测；
- 差谱；
- 插值、排序、轴反转；
- 复杂信号、时域、二维谱；
- 自动处理。

M4 没有新增这些算法。

---

## 2. 新增与修改文件

### 新增通用处理模块

- [src/spectralab/core/processing/__init__.py](../src/spectralab/core/processing/__init__.py)
- [src/spectralab/core/processing/base.py](../src/spectralab/core/processing/base.py)
- [src/spectralab/core/processing/records.py](../src/spectralab/core/processing/records.py)
- [src/spectralab/core/processing/session.py](../src/spectralab/core/processing/session.py)

### 修改中立核心

- [src/spectralab/core/errors.py](../src/spectralab/core/errors.py)：新增
  `ProcessingError`、`InvalidProcessingOperationError`、
  `InvalidProcessingOutputError`、`ProcessingExecutionError`
- [src/spectralab/core/__init__.py](../src/spectralab/core/__init__.py)：导出 processing API

### 新增 EPR 适配器

- [src/spectralab/techniques/epr/processing_adapter.py](../src/spectralab/techniques/epr/processing_adapter.py)
- [src/spectralab/techniques/epr/__init__.py](../src/spectralab/techniques/epr/__init__.py)：导出 EPR 处理操作

### 新增测试

- [tests/test_processing_session.py](../tests/test_processing_session.py)：23 个测试
- [tests/test_epr_processing_adapter.py](../tests/test_epr_processing_adapter.py)：11 个测试
- [tests/test_m4_architecture.py](../tests/test_m4_architecture.py)：5 个测试

合计 **39 个新测试**。

### 新增/更新文档

- 本报告
- [docs/architecture_proposal.md](architecture_proposal.md)：更新 M4 状态、实际范围和测试基线
- M3 报告页脚更新为已进入 M4

### 未修改

- `src/epr_workflow/` 下所有生产代码
- 现有 `epr_workflow.preprocessing`
- ASC/BES3T 解析器
- 现有 GUI、CLI、批处理、CSV/JSON schema
- 现有测试、原始数据、配置
- `requirements.txt`

---

## 3. ProcessedSpectrum API

模块：`spectralab.core.processing`

```python
@dataclass(frozen=True)
class ProcessedSpectrum:
    source: Spectrum1D
    axis: Axis1D
    signal: Signal1D
    history: tuple[ProcessingOperation, ...] = ()
    session_id: str | None = None
```

字段和属性：

- `source` / `source_spectrum`：原始 `Spectrum1D` 引用；
- `axis`：处理后的 X 轴；
- `signal`：处理后的 Y 信号；
- `history` / `processing_history`：成功应用的操作记录；
- `session_id`：可选的会话标识；
- `source_spectrum` / `raw_spectrum`：原 `Spectrum1D` 引用别名；
- `metadata`：原 `Spectrum1D.metadata`；
- `provenance`：原 `Spectrum1D.provenance`；
- `technique`、`source_format`；
- `point_count`、`x_values`、`y_values`；
- `operations`：当前历史的 operation ID 序列；
- `warnings`、`assumptions`：按历史顺序聚合；
- `is_original`：历史为空；
- `metadata`/`provenance` 不复制、不丢弃。

原始 `Spectrum1D` 和 `ProcessedSpectrum` 是不同类型；M3 raw exporter
不会把 `ProcessedSpectrum` 当作原始谱接受。

---

## 4. ProcessingSession API

模块：`spectralab.core.processing.session`

```python
class ProcessingSession:
    def __init__(self, spectrum: Spectrum1D, *, session_id=None): ...
    @property
    def source(self) -> Spectrum1D: ...
    @property
    def history(self) -> tuple[ProcessingOperation, ...]: ...
    @property
    def operations(self) -> tuple[str, ...]: ...
    @property
    def current(self) -> ProcessedSpectrum: ...
    def current_spectrum(self) -> ProcessedSpectrum: ...
    @property
    def can_undo(self) -> bool: ...
    @property
    def can_redo(self) -> bool: ...
    def apply(self, operation: OperationImplementation) -> ProcessedSpectrum: ...
    def undo(self) -> ProcessedSpectrum: ...
    def redo(self) -> ProcessedSpectrum: ...
    def reset(self) -> ProcessedSpectrum: ...
```

行为：

- 构造时不复制、不改写原始谱；
- `apply()` 接收显式 `OperationImplementation`；
- 成功后才写入历史；
- 失败不会改变当前状态、历史或 redo 栈；
- `undo()` 返回上一状态；
- `redo()` 返回被撤销的状态；
- `reset()` 清空历史、redo 栈并回到原始谱；
- 没有自动应用、预览或隐式处理。

---

## 5. ProcessingOperation 表示

### 5.1 可执行操作协议

模块：`spectralab.core.processing.base`

```python
@runtime_checkable
class OperationImplementation(Protocol):
    operation_id: str
    name: str
    technique: str
    version: str
    parameters: Mapping[str, Any]
    changes_axis: bool
    axis_change_description: str | None
    changes_signal_semantics: bool
    changes_signal_unit: bool
    signal_change_description: str | None
    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput: ...
```

`OperationImplementation` 是技术模块提供的执行实现。

### 5.2 已应用操作记录

模块：`spectralab.core.processing.records`

```python
@dataclass(frozen=True)
class ProcessingOperation:
    order: int
    operation_id: str
    name: str
    technique: str
    version: str
    parameters: Mapping[str, Any]
    input_state_id: str
    output_state_id: str
    changes_axis: bool
    axis_change_description: str | None
    changes_signal_semantics: bool
    changes_signal_unit: bool
    signal_change_description: str | None
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]
    diagnostics: Mapping[str, Any]
```

这是**成功应用后**的历史记录，不是可执行对象。

包含：

- 稳定 operation ID；
- 名称；
- 技术标识；
- 参数快照；
- 执行顺序；
- 输入/输出状态 ID（`original` / `step-N`）；
- 轴/信号变化声明；
- 警告、假设、诊断。

失败操作不会产生 `ProcessingOperation` 记录。

---

## 6. Undo / Redo 恢复策略

采用**保存不可变状态**而不是算法重放：

- 每次成功 apply 都保存该步的 `Axis1D` 和 `Signal1D`；
- undo 把最后一条 `_Applied` 记录移到 redo 栈；
- redo 把保存的不可变状态移回 applied 栈；
- redo 不重新调用算法，因此不会受随机性、外部状态或操作对象后续修改影响；
- 原始 axis 在操作不改变 X 时可以被复用；
- 输出 signal 是新的只读数组，原始数组不被复用为可写数组；
- reset 清空 applied 和 redo 栈。

测试 `test_redo_restores_saved_output_without_replaying_operation` 使用带调用计数的操作验证：
redo 后计数不增加，输出与 undo 前逐值相同。

因此 M4 的 redo 是**确定性状态恢复**，不是重新执行。

---

## 7. EPR 适配器行为

模块：`spectralab.techniques.epr.processing_adapter`

### `EprLinearBaselineOperation`

- `operation_id="linear_baseline"`（旧 EPR operation ID）
- `name="EPR linear baseline correction"`
- `technique="epr"`
- `version="1.0"`（来自旧算法版本）
- 构造参数：旧 `LinearBaselineSpec`
- `changes_axis=False`
- `changes_signal_semantics=False`
- `changes_signal_unit=False`

`apply()`：

1. 要求轴 `quantity="magnetic_field"`、`unit="G"`；
2. 调用旧 `fit_linear_baseline`；
3. 使用旧公式计算 processed Y；
4. 复用 X 轴；
5. 保留信号 name/semantics/unit/missing_reason；
6. 将旧警告、拟合诊断、points_used 写入历史记录。

### `EprSavitzkyGolayOperation`

- `operation_id="savitzky_golay"`（旧 EPR operation ID）
- `name="EPR Savitzky-Golay smoothing"`
- `technique="epr"`
- `version="1.0"`
- 构造参数：旧 `SavgolSpec`
- `changes_axis=False`
- 调用旧 `smooth_savgol`
- 复用 X 轴并保留信号元数据。

### 未适配的旧功能

以下旧 EPR 行为没有强行塞入 generic session：

- preview / discard preview / pending apply；
- smoothing 以 raw 输入插入到已有步骤之前的重排；
- 旧 `PreprocessingResult.is_preview`；
- 旧 `build_preprocessing_record` 的 EPR JSON schema；
- 旧 GUI 预览/撤销/重置交互；
- 旧处理时间戳/软件版本记录。

这些仍保留在旧 `epr_workflow` 应用中。generic session 只执行显式、顺序 apply，
需要 raw-first 顺序时由调用方先 apply smoothing 再 apply baseline。

---

## 8. 数值等价结果

使用 M0 真实 ASC 与 BES3T 数据，以及合成递增/递减数据：

- EPR linear baseline：
  - X、processed Y、removed baseline 与旧 `PreprocessingSession` 逐值相等；
  - `fit` 诊断与旧 `last_fit.as_dict()` 相等；
  - 警告消息序列相等；
  - 源文件哈希和输入数组不变。
- EPR Savitzky-Golay：
  - X、processed Y 与旧 session 逐值相等；
  - smoothing diagnostics 相等。
- 组合 baseline → Savgol：
  - 与旧 `apply(baseline)` 后 `apply_savgol` 逐值相等；
  - generic history 顺序为 baseline、savgol。
- 递减轴：
  - 合成递减磁场数据与旧 session 结果逐值相等；
  - X 顺序保持递减。
- 非 EPR 轴：
  - `wavenumber`/`cm^-1` 轴被明确拒绝，错误码 `epr_axis_unsupported`。
- 旧错误码：
  - 窗口点数不足等旧错误码被保留，例如 `window_points`。

---

## 9. 不可变性与科学完整性

- 原始 `Spectrum1D` 对象不变；
- 原始 X/Y 数组保持只读；
- processed axis/signal 由 `Axis1D`/`Signal1D` 创建，数组只读；
- 不排序、不反转、不插值、不归一化；
- 不自动执行任何处理；
- 每个操作必须显式 apply；
- 操作失败不写历史、不改变当前状态、不清空 redo；
- undo/redo 恢复保存的不可变状态；
- 操作参数在 apply 前快照到历史；
- 操作记录包含警告、假设和诊断；
- 原始 metadata/provenance 通过 `source` 保留；
- X 变化必须声明 `changes_axis=True` 且提供描述；
- 信号 semantics/unit 变化必须声明并提供描述；
- 非空参数映射和结果类型都在执行前后验证；
- 旧 EPR 源文件和旧 preprocessing 实现未被修改。

---

## 10. 架构边界结果

- `spectralab.core.processing` 不导入 Qt、GUI、`epr_workflow`、`spectralab.app`
  或 `spectralab.techniques`；
- 导入 core processing 不加载 EPR、Qt 或技术包；
- core processing 代码中不包含 `field_G`、`magnetic_field`、`Field [G]`、
  `CW-EPR`；
- `spectralab.techniques.epr.processing_adapter` 只依赖 core 与旧 EPR preprocessing；
- 技术包不导入 app、GUI 或 FTIR；
- core → techniques → app 导入图无循环；
- M3 raw exporter 不接受 `ProcessedSpectrum`，不会把处理结果伪装成原始谱；
- 未修改 M3 原始导出 schema。

---

## 11. 测试结果

新增 **39 个 M4 测试**：

- `tests/test_processing_session.py`：23
- `tests/test_epr_processing_adapter.py`：11
- `tests/test_m4_architecture.py`：5

实际运行：

```text
完整测试集 pytest -v：
423 passed, 1 skipped
exit code 0

pytest -q -W error::UserWarning：
423 passed, 1 skipped
exit code 0

原 EPR 测试集（排除 M0/M1/M2/M3/M4 测试）：
298 passed, 1 skipped
exit code 0
```

日志：

- `results/logs/pytest_m4_20261102_verbose.txt`
- `results/logs/pytest_m4_20261102_userwarning.txt`
- `results/logs/pytest_m4_20261102_original.txt`

---

## 12. 向后兼容

- `epr_workflow` 生产代码未修改；
- 现有 `epr_workflow.preprocessing` 未修改；
- ASC/BES3T 解析器、GUI、CLI、批处理、CSV/JSON schema 未修改；
- 现有测试未修改；
- 原 EPR 测试 298 passed / 1 skipped 不变；
- 新 processing 没有接入旧 GUI/CLI；
- 删除新增模块即可回滚；
- 无新增依赖，`requirements.txt` 未修改。

---

## 13. 剩余限制与风险

1. `ProcessingSession` 只提供显式顺序 apply；不提供旧 EPR 的 preview、pending
   apply 或 raw-input 重排。
2. EPR 适配器只支持 `magnetic_field` + `G`，不做单位转换；其他轴会被拒绝。
3. 旧 EPR JSON preprocessing record 没有迁移到 generic core；旧 schema 保持不变。
4. processed-spectrum export 被推迟；M3 raw export 不变，`ProcessedSpectrum`
   不会被误当作原始 `Spectrum1D`。
5. 当前没有 FTIR 处理实现、峰检测、差谱、归一化、复杂/二维谱。
6. Undo/redo 保存每一步的 axis/signal 状态以换取精确恢复；大谱和多步处理会保留
   相应数组，内存随历史增长。复用不改变的 X axis，但不压缩 Y 状态。
7. `session_id` 默认是 `None`；调用方可显式提供。没有自动生成 ID，避免把
   非科学标识伪装成测量元数据。
8. 信号 name/metadata_source/missing_reason 的任意变化目前没有被声明标志强制
   检查；强制检查的是 X 轴变化、信号 semantics 和 unit。操作实现仍应保持
   这些字段语义一致。
9. 操作实现必须自行保证不产生随机或外部状态相关输出；本实现通过保存状态避免
   redo 重放，但首次 apply 仍由实现决定。
10. `ProcessedSpectrum` 没有独立导出 schema；M4 不把处理结果写入旧 CSV/JSON。

---

## 14. M4 完成清单

- [x] `ProcessedSpectrum`
- [x] `OperationOutput`
- [x] `OperationImplementation`
- [x] `ProcessingOperation` 历史记录
- [x] `ProcessingSession`
- [x] apply / undo / redo / reset
- [x] 原始 `Spectrum1D` 与数组不变
- [x] 处理数组只读
- [x] 参数、顺序、状态关联记录
- [x] 失败操作回滚
- [x] X 轴变化显式声明
- [x] 信号 semantics/unit 变化显式声明
- [x] 确定性状态恢复（不重放）
- [x] EPR 线性基线适配
- [x] EPR Savitzky-Golay 适配
- [x] 真实 ASC/BES3T 数值等价
- [x] 递减轴
- [x] core 不导入 Qt/EPR/app/techniques
- [x] 无循环导入
- [x] 原 EPR 测试 298 passed / 1 skipped
- [x] 完整测试 423 passed / 1 skipped
- [x] `-W error::UserWarning` 通过
- [x] 未 commit、未 push

**M4 状态：完成。** M5 见 [M5 通用绘图报告](m5_generic_plotting_report.md)，
M6 见 [M6 通用 CLI/Batch 报告](m6_cli_batch_report.md)，M7 见
[M7 EPR Backend Closure 报告](m7_epr_backend_closure_report.md)，M8 见
[M8 GUI Architecture 报告](m8_gui_architecture_report.md)；M9 尚未开始。
