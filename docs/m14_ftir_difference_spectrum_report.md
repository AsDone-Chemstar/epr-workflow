# M14 报告：FTIR Difference Spectrum

- 状态：**M14 完成**
- 基线：M13
- Git HEAD：`fae60ed`（M0–M13 checkpoint）
- 前序测试基线：M13 **689 passed, 1 skipped**
- M14 结果：**724 passed, 1 skipped**
- 日期：2026-11-05
- Git：**未 commit、未 push、未创建 tag**
- M15：**未开始**

---

## 1. 实现摘要

已实现：

1. 显式 `Difference = Spectrum A - Spectrum B`；
2. 精确 X 轴比较的直接相减；
3. 用户显式选择的线性插值；
4. A/B 各自 Raw / Current Processed 来源；
5. 轴物理量、单位、信号语义、信号单位、方向、点数和数据集身份验证；
6. Preview / Apply-Save / Clear；
7. FTIR 差谱标签页、A/B 选择器、来源选择器、匹配方式选择器；
8. A、B、插值后的 B、差谱四条曲线的预览；
9. 独立 `DifferenceResult`，不写入 `ProcessingSession`；
10. 完整来源、处理历史和插值 provenance；
11. 一个 FTIR 面板内的多光谱工作区（每个光谱有独立 `ProcessingSession`）；
12. 中英文运行时切换。

未实现：

- 自动轴对齐、自动插值或自动来源选择；
- 外推、排序、反转源数组；
- 峰拟合、去卷积、化学归属；
- 自动归一化、自动基线、自动平滑；
- 差谱文件导出；
- 多光谱叠加比较（M16）；
- M15。

---

## 2. 架构与修改文件

依赖方向保持：

```text
app → techniques → core
```

差谱依赖两个数据集，不能表示成单源 `ProcessingSession` 的一步操作，因此采用
与 M13 峰检测相同的模式：FTIR technique 层的独立分析结果 + app 层 GUI。

### 新增

- [src/spectralab/techniques/ftir/difference.py](../src/spectralab/techniques/ftir/difference.py)
- [tests/test_ftir_difference.py](../tests/test_ftir_difference.py)
- [tests/test_ftir_difference_gui.py](../tests/test_ftir_difference_gui.py)
- 本报告

### 修改

- [src/spectralab/techniques/ftir/__init__.py](../src/spectralab/techniques/ftir/__init__.py)
- [src/spectralab/app/gui/ftir_panel.py](../src/spectralab/app/gui/ftir_panel.py)
- [src/spectralab/app/gui/ftir_translations.py](../src/spectralab/app/gui/ftir_translations.py)
- [docs/architecture_proposal.md](architecture_proposal.md)

### 未修改

- `src/spectralab/core/`
- `src/epr_workflow/`
- M11 normalization 算法行为
- M12 baseline 算法行为
- M13 peak-picking 算法行为
- `requirements.txt`
- raw data / `S-BSAPEG-10.0.dpt`

无删除文件。无新增依赖。

### 与提案的偏差

提案原计划放在 `core/processing/operations/difference.py` 和
`techniques/ftir/difference_defaults.py`。实现改为单个
`techniques/ftir/difference.py`，原因：

- 差谱有两个源数据集，放入单源 `ProcessingSession` 会丢失源身份；
- core 不应包含 FTIR 或两谱操作语义；
- GUI 直接调用 technique API，避免复制数值逻辑。

该偏差已记录在架构提案的 M14 结果中。

---

## 3. 直接相减比较策略

精确模式要求：

- 两个 X 数组点数相同；
- 对应 float64 X 值完全相同；
- 点序完全相同；
- 不排序、不反转、不插值；
- 不读取或使用点序以外的容差。

实现使用：

```python
np.array_equal(x_a, x_b)
```

这是**逐元素精确相等**，没有 `np.allclose`、没有相对/绝对容差。即使差异为
`1e-12` 也会被拒绝。

计算：

```text
difference[i] = signal_A[i] - signal_B[i]
```

失败码：

- `ftir_difference_point_count`
- `ftir_difference_axis_values`

错误 context 记录第一个不匹配的索引、两个 X 值和比较策略。

---

## 4. 插值算法与目标轴

插值必须由用户显式选择 `interpolate`。

目标轴定义：

1. 计算共同重叠区间：
   `[max(min(A), min(B)), min(max(A), max(B))]`；
2. 取 Spectrum A 中位于闭区间内的 X 点，保持 A 的原始顺序；
3. 用这些点作为目标轴；
4. 将 Spectrum B 线性插值到目标轴；
5. 计算 `A_target - B_interpolated`。

实现使用 `numpy.interp`，仅线性插值。

### 端点

闭区间端点包含在目标轴中；结果轴只包含 A 原有点，不新增 A 之外的端点。

### 不外推

目标点全部位于 B 的 `[min, max]` 内；任何目标点越界都会拒绝，错误码
`ftir_difference_extrapolation`。

### 单调性与重复值

- A、B 必须具有已知的严格单调方向；
- 重复或非单调轴在 `Axis1D` 层被标记为 `direction='unknown'`；
- 差谱层再次拒绝 `direction='unknown'`，错误码
  `ftir_difference_axis_not_monotonic`。

### B 为递减轴

`numpy.interp` 需要递增样本点。实现只在局部工作副本中反转 B 的 X/Y 副本，
用于插值；**源对象、源数组顺序和输出目标轴顺序都不改变**。输出结果仍按 A
的原始顺序排列。

### 失败条件

- 无共同重叠：`ftir_difference_no_overlap`；
- 目标点少于 2：`ftir_difference_insufficient_points`；
- B 有重复或非单调：`ftir_difference_axis_not_monotonic`；
- 需要外推：`ftir_difference_extrapolation`。

---

## 5. 兼容性验证

`compute_difference()` 在计算前验证：

| 项目 | 规则 |
| --- | --- |
| X 轴物理量 | 必须相同且不能是 `unknown` |
| X 轴单位 | 必须相同；两者都为 `None` 时保留未知单位 |
| X 轴方向 | 必须严格递增或严格递减 |
| 信号语义 | 必须相同且不能是 `unknown` |
| 信号单位 | 必须相同；两者都为 `None` 时保留未知单位 |
| 点数 | 精确模式必须相同 |
| 数据集身份 | `dataset_id` 必须不同 |

不推断缺失单位或语义，不做单位换算。

错误码：

- `ftir_difference_axis_quantity`
- `ftir_difference_axis_quantity_unknown`
- `ftir_difference_axis_unit`
- `ftir_difference_signal_semantics`
- `ftir_difference_signal_semantics_unknown`
- `ftir_difference_signal_unit`
- `ftir_difference_same_dataset`

数据集身份按 `dataset_id` 比较；不同 ID 即使数组完全相同也视为不同数据集。
该限制记录在结果 `limitations` 中。

---

## 6. 结果模型

`DifferenceResult` 是冻结 dataclass，包含：

- 差谱 `Axis1D`；
- 差谱 `Signal1D`；
- `dataset_a_id` / `dataset_b_id`；
- `source_a` / `source_b`（`raw` / `processed`）；
- `DifferenceParameters`；
- `axis_match`（`exact` / `interpolate`）；
- `DifferenceInterpolation`（插值模式）：
  - 方法 `linear`；
  - 目标数据集；
  - 被插值数据集；
  - 目标点数；
  - 重叠上下界；
  - 外推状态 `none`；
  - 端点策略；
  - 对齐后的 B `Signal1D`；
- A/B 源处理历史；
- warnings / assumptions / limitations；
- 算法名和版本；
- 点数。

`as_dict()` 输出 provenance-ready 元数据，**不包含数组**。数组由只读
`Axis1D`/`Signal1D` 持有，不引用可变源数组。

算法值：

```text
direct_subtraction
linear_interpolation
```

算术定义固定为：

```text
A - B
```

没有创建第二套 ProcessingSession history。

---

## 7. GUI 行为

FTIR 底部现在有三个标签页：

```text
Import options
Peak picking
Difference
```

### 多光谱工作区

为了支持 A/B，两个光谱必须能同时存在：

- 每次导入创建一个独立工作区；
- 每个工作区有自己的 `ProcessingSession`；
- 顶部 `Current spectrum` 选择器决定处理、撤销、峰检测作用于哪个光谱；
- 同一路径再次导入会替换该工作区；
- 不同路径但相同 `dataset_id` 的工作区仍保留，但不会被同时选为 A/B。

### Difference 标签页

提供：

- Spectrum A 选择器；
- Spectrum B 选择器（自动排除与 A 相同的工作区和相同 `dataset_id`）；
- A/B 来源：Raw / Current Processed；
- X 轴匹配：Exact / Linear interpolation；
- Preview；
- Apply/Save；
- Clear；
- 状态、参数摘要、警告和 limitations。

### Preview

绘制：

1. Spectrum A（所选来源）；
2. Spectrum B（所选来源）；
3. 插值模式下的 B（线性插值到 A 轴），用虚线区分；
4. 差谱 A − B。

预览不修改：

- 任一 Raw Spectrum；
- 任一 Current Processed；
- 任一 ProcessingSession；
- Undo/Redo；
- 元数据或 provenance。

### 状态失效

- 更改 A、B、来源或匹配方式：清除 preview，Apply 禁用；
- 切换标签页：有差谱结果时重新显示差谱，有峰结果时重新显示峰结果；
- 新导入：清除 preview 和 applied difference；
- 任一处理 apply/undo/redo/reset：清除 difference preview 和 applied result；
- 失败的计算保留两个源光谱和它们已有的处理状态，不产生部分结果。

实现选择“处理变化时清除全部差谱结果”，即使用户的差谱只用了 raw 来源。这是
保守的失效策略，避免任何 stale result。

---

## 8. Provenance

`DifferenceResult` 记录：

- 两个 `dataset_id`；
- 两个来源（raw/processed）；
- 两个来源的处理历史 operation IDs；
- 算术定义 `A - B`；
- 轴匹配方式和插值参数；
- 轴/信号元数据；
- 点数；
- warnings / assumptions / limitations；
- 算法名和版本。

`as_dict()` 可用于未来 JSON provenance 导出，但 M14 没有文件导出。

---

## 9. Export 决策

现有通用导出：

- [src/spectralab/core/export/csv.py](../src/spectralab/core/export/csv.py)
- [src/spectralab/core/export/json.py](../src/spectralab/core/export/json.py)

只接受 `Spectrum1D`，使用 schema v1 的单谱字段。`DifferenceResult`：

- 有两个源数据集；
- 有插值目标/方法；
- 有独立算术定义；
- 不是 `Spectrum1D`。

直接塞入现有 schema 会丢失源身份或破坏 schema。按照 M14 的范围，**没有实现
差谱文件导出**。

M15 后续需要：

- 专用 difference export profile；
- CSV 列定义和 JSON schema；
- 两个源数据集和插值 provenance；
- 输出路径保护；
- 双语标签；
- 测试。

---

## 10. 测试结果

新增 **35 个 M14 测试**：

- [tests/test_ftir_difference.py](../tests/test_ftir_difference.py)：22
- [tests/test_ftir_difference_gui.py](../tests/test_ftir_difference_gui.py)：13

覆盖：

### 直接相减

- 相同递增轴；
- 相同递减轴；
- 相同轴、不同信号；
- 不同点数；
- 略有不同的 X 值（1e-12 也拒绝）；
- 不同点序；
- 模型层拒绝非有限值。

### 插值

- 不同采样间隔；
- 递增目标轴；
- 递减目标轴；
- 递减 B；
- 部分重叠；
- 无重叠；
- 端点包含；
- 不外推；
- 重复 B 轴；
- 非单调 B 轴；
- 目标点不足。

### 兼容性

- 相同物理量/单位；
- 不同物理量；
- 不同单位；
- 相同信号语义；
- 不兼容语义；
- 未知语义；
- 缺失单位（双方 `None`）；
- 不兼容信号单位；
- 相同数据集 ID。

### 状态与完整性

- Preview 不修改两个源；
- Apply 不修改两个源；
- 两个 ProcessingSession history 不变；
- 参数/来源/数据集选择使 preview 失效；
- 新导入清除结果；
- 处理变化清除结果；
- 失败操作保留源数据；
- provenance 标识两个数据集；
- 结果不持有可变源数组；
- 标签页切换恢复差谱图；
- 中英文切换。

### 回归

- M11 normalization；
- M12 baseline；
- M13 peak picking；
- 原始 EPR。

实际运行：

```text
完整 verbose：
724 passed, 1 skipped in 64.80s

warnings-as-errors：
724 passed, 1 skipped in 64.76s

原始 EPR 回归：
298 passed, 1 skipped in 39.26s

架构：
20 passed in 11.68s

聚焦 M11–M14 FTIR：
85 passed in 2.41s
```

唯一 skip 是既有 Windows `.DTA` 大小写歧义测试。

日志：

- `results/logs/pytest_m14_final_20261105_verbose.txt`
- `results/logs/pytest_m14_final_20261105_userwarning.txt`
- `results/logs/pytest_m14_final_20261105_original.txt`

M13 → M14：689 → **724 passed**。

---

## 11. 科学限制

1. 精确模式没有数值容差；浮点表示差异会被拒绝。
2. 插值目标固定为 A，不提供用户选择 B 作为目标轴。
3. 插值只用共同重叠区；区间外的 A 点被排除，不外推。
4. 插值在 B 递减时只反转局部工作副本，源数组和输出顺序不变。
5. 数据集身份按 `dataset_id`，不按文件哈希；相同数组但不同 ID 可相减。
6. 未知物理量、未知信号语义被拒绝；双方都为 `None` 的单位被保留为未知单位。
7. 差值信号不保留原信号名称，`name=None` 并使用显式 `missing_reason`。
8. 差谱结果不写入 ProcessingSession，不会被保存到磁盘。
9. 任一处理变化清除差谱结果，包括只用 raw 的差谱；这是保守失效。
10. 没有差谱导出、峰拟合、去卷积或化学解释。
11. 没有多光谱叠加比较（M16）。
12. 没有自动对齐、自动插值、自动来源选择或自动单位转换。

---

## 12. 剩余技术债务

1. `ftir_panel.py` 已约 2300 行，多光谱工作区是增量实现；建议后续拆分为
   通用工作区控制器、处理控件、峰控件和差谱控件。
2. 差谱绘图直接在 app 层使用 Matplotlib 多条曲线；通用 renderer 目前只有
   raw/processed 两种样式，未扩展为 A/B/difference 系列。
3. 没有工作区删除 UI；长期运行会累积已导入光谱。
4. `DifferenceResult.as_dict()` 已准备 metadata，但未接入导出。
5. 处理变化时清除全部差谱结果，而不是只清除依赖该处理源的结果。
6. 峰结果仍是全局状态，切换当前光谱会清除；未来可做每工作区结果。
7. 数据集 ID 由文件名 stem 生成，同名文件会被视为同一数据集。
8. 测试使用小型合成 CSV 和既有真实 DPT；没有针对复杂 FTIR 差谱样本集。
9. M15 的导出、批处理映射和端到端加固尚未开始。

---

## 13. 真实样本

`S-BSAPEG-10.0.dpt` 未被修改：

- 4350 点；
- X 轴：`wavenumber`、`cm^-1`、`decreasing`；
- 信号语义：`absorbance`；
- 信号单位：`None`（显式未知）；
- SHA-256：

```text
501fe570b175d8f2a089c21c17f469b1a087d654040f72986c5ba9fe9bffe761
```

---

## 14. Git 状态

```text
HEAD = fae60edc970c67014f921dfddd58dce0ff62d603
```

- 未 commit；
- 未 push；
- 未创建 tag；
- 未 amend/rebase/reset/clean；
- 未修改 raw data；
- 未修改 `requirements.txt`；
- 未修改 `S-BSAPEG-10.0.dpt`；
- 未修改 legacy `epr_workflow`；
- **M15 未开始**。

**M14 完成。**
