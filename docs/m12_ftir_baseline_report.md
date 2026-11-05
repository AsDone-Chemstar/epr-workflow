# M12 报告：FTIR Linear / Polynomial Baseline Correction

- 状态：**M12 完成**
- 基线版本：EPR Workflow **v0.2.0**
- Git 基线：`327d5f6`
- 前序测试基线：M11 **631 passed, 1 skipped**
- M12 结果：**661 passed, 1 skipped**
- 日期：2026-11-04
- 旧 EPR 应用：**未修改，仍独立可用**
- Git：**未 commit、未 push、未创建 tag**
- M13–M17：**未实现**

---

## 1. 实现摘要

M12 新增：

1. FTIR 线性基线；
2. FTIR 2–5 阶多项式基线；
3. 用户定义的多个不重叠拟合区域；
4. Preview / Apply / Cancel；
5. Undo / Redo / Reset；
6. 完整处理 provenance；
7. FTIR GUI 算法/阶数/区域选择；
8. Baseline 曲线和区域可视化；
9. 中英文运行时切换。

没有实现自动区域选择、自动阶数、rubberband baseline 或自动基线执行。

---

## 2. 新增与修改文件

### 新增

- [src/spectralab/techniques/ftir/baseline.py](../src/spectralab/techniques/ftir/baseline.py)
- [tests/test_ftir_baseline.py](../tests/test_ftir_baseline.py)：22 个测试
- 本报告

### 修改

- [src/spectralab/techniques/ftir/__init__.py](../src/spectralab/techniques/ftir/__init__.py)
- [src/spectralab/app/gui/ftir_panel.py](../src/spectralab/app/gui/ftir_panel.py)
- [src/spectralab/app/gui/ftir_translations.py](../src/spectralab/app/gui/ftir_translations.py)
- [tests/test_ftir_gui.py](../tests/test_ftir_gui.py)：新增 8 个 baseline GUI 测试
- [docs/architecture_proposal.md](architecture_proposal.md)
- [docs/m11_maintenance_and_normalization_report.md](m11_maintenance_and_normalization_report.md)

### 删除

无。

### 未修改

- `src/epr_workflow/`
- 旧 EPR GUI/CLI/preprocessing/export
- `ProcessingSession` 的 M11 preview/undo/redo 行为
- M11 normalization 算法和 GUI 行为
- M3 export schema
- `requirements.txt`
- `S-BSAPEG-10.0.dpt`

---

## 3. 数学实现与数值方法

文件：

`src/spectralab/techniques/ftir/baseline.py`

### 模型

线性：

```text
baseline(x) = a*x + b
```

多项式：

```text
baseline(x) = c0 + c1*x + ... + cn*x^n
```

修正：

```text
y_corrected = y - baseline(x)
```

### 数值方法

- NumPy float64；
- 使用用户选择的拟合区域中的原始 X/Y 点；
- 对拟合 X 做内部中心化和缩放：

```text
z = (x_fit - mean(x_fit)) / max(abs(x_fit - mean(x_fit)))
```

- 构造 increasing-power Vandermonde 矩阵；
- 使用 `numpy.linalg.lstsq` 做最小二乘；
- 检查：
  - rank == degree + 1；
  - condition number <= `1e12`；
  - coefficients finite；
  - baseline finite；
  - corrected finite。
- 用同一 center/scale 在原 X 轴全部点上计算 baseline；
- 不做 degree fallback、自动区域变化或自动重拟合。

### 数值限制

- Condition threshold `1e12` 是明确的数值保护，不是科学结论；
- 拟合系数存储在 centered/scaled X 域，诊断同时记录 center/scale；
- 不实现加权最小二乘、robust fitting 或 rubberband baseline；
- 不对阶数或区域自动做推荐。

---

## 4. Fitting region 行为

`BaselineRegion(start, end)`：

- 使用 X 轴坐标；
- `start`/`end` 必须有限且不相等；
- 内部规范化为 `lower <= upper`；
- 保留数据原始顺序，不排序/反转/裁剪数据数组；
- 多个区域按坐标排序后记录；
- 重叠区域明确拒绝；
- 边界相接允许；
- 拟合点使用原始 X 值 masks，不反转折线数据。

错误：

- `ftir_baseline_regions`
- `ftir_baseline_region_invalid`
- `ftir_baseline_region_overlap`
- `ftir_baseline_insufficient_points`
- `ftir_baseline_rank_deficient`
- `ftir_baseline_ill_conditioned`
- `ftir_baseline_nonfinite_coefficients`
- `ftir_baseline_nonfinite_baseline`
- `ftir_baseline_nonfinite_output`

拟合点数必须严格大于 degree。Rank 或 condition 不合格时不会降低阶数。

---

## 5. ProcessingSession 集成

使用 M11 的现有机制：

```python
session.preview(operation)
session.apply(operation)
session.undo() / redo() / reset()
```

没有新增 processing framework，也没有复制 session 逻辑。

- Preview 只返回 `OperationOutput`；
- 不修改 `_applied`、`_redo`、history 或 raw spectrum；
- Apply 才写入 `ProcessingOperation`；
- Baseline 使用**当前 processed signal**，不是 raw；
- Raw → Normalization → Baseline 支持；
- Undo baseline 恢复 normalized state；
- Failed operation 不改变 session；
- Preview 不进入 history。

---

## 6. Provenance 字段

### `ProcessingOperation.parameters`

- `algorithm`: `linear` / `polynomial`
- `degree`: 1–5
- `regions`: `[{"start": ..., "end": ...}, ...]`
- `region_count`

### `ProcessingOperation.diagnostics`

- `algorithm`
- `degree`
- `regions`
- `fitting_point_count`
- `coefficients`（centered/scaled X 域）
- `coefficient_domain = "centered_scaled_x"`
- `x_center`
- `x_scale`
- `condition_number`
- `condition_limit`
- `rank`
- `numerical_method`
- `point_count`

### 通用记录

- operation id：`ftir.baseline.linear` / `ftir.baseline.polynomial`
- technique：`ftir`
- version：`1.0.0`
- order
- input_state_id / output_state_id
- operation history 由 `ProcessedSpectrum.history` 保存
- source dataset identity 由 `ProcessedSpectrum.source.dataset_id` 保留

没有 preview record；只有 Apply 后生成 history。

---

## 7. GUI workflow

FTIR processing 区域现在支持两类操作：

```text
Normalization
Baseline correction
```

Baseline 控件：

- Algorithm：Linear / Polynomial
- Polynomial degree：2–5
- Fitting regions：Add / Remove
- Region X start/end 输入
- 区域列表
- 拟合点数/阶数显示
- Preview / Apply / Cancel preview
- Undo / Redo / Reset to raw

### Preview

Baseline preview 显示：

- Original raw：灰色虚线
- Current processed：绿色（有处理历史时）
- Estimated baseline：橙色虚线
- Preview-corrected：蓝色

Fitting regions 以半透明黄色区域显示在图上。

预览不写入 history；切换 algorithm/degree/region 会取消旧 preview。

### Apply / Cancel / Undo / Redo / Reset

- Apply 使用当前 preview operation 显式提交；
- Cancel 清除 preview，恢复到已提交状态；
- Undo/Redo 直接恢复 session 存储的状态；
- Reset 回 raw；
- 新文件导入清除 preview 和旧区域；
- 不自动基线。

### Language

中英文覆盖：

- 操作/算法/阶数/区域控件；
- 拟合信息；
- 状态；
- 图例；
- baseline/current/preview 标签。

没有可提供的 GUI 截图；离屏 GUI 测试覆盖上述交互。

---

## 8. 测试结果

新增 **30 个 M12 测试**：

- `tests/test_ftir_baseline.py`：22
- `tests/test_ftir_gui.py` 新增 baseline 测试：8

覆盖：

- 线性 baseline 恢复；
- degree 2–5 恢复；
- increasing/decreasing X；
- 多区域；
- 点数不足；
- 空数组/长度不一致；
- NaN/Inf；
- rank-deficient；
- ill-conditioned；
- 非法/重叠区域；
- 非有限 coefficients/baseline/output；
- raw/X/点序不变；
- preview 不修改 history/redo/raw；
- apply/undo/redo/reset；
- normalization → baseline → undo normalized；
- failed operation 不改变 session；
- GUI 算法/degree/region 选择；
- GUI preview/apply/cancel/undo/redo/reset；
- 参数变化使 preview 失效；
- 中英文切换；
- descending X；
- 新文件导入清除 preview；
- 真实 4350 点样本；
- EPR 回归。

实际运行：

```text
M12 release 完整 verbose：
661 passed, 1 skipped in 51.04s
exit code 0

M12 release warnings-as-errors：
661 passed, 1 skipped in 54.06s
exit code 0

M12 release 原 EPR 14 文件回归：
298 passed, 1 skipped in 37.59s
exit code 0
```

日志：

- `results/logs/pytest_m12_20261104_verbose.txt`
- `results/logs/pytest_m12_20261104_userwarning.txt`
- `results/logs/pytest_m12_20261104_original.txt`

M11 → M12：

- 631 → **661 passed**
- skip 保持 1（Windows `.DTA` 大小写歧义）
- M11 normalization 和现有 EPR 数值行为未变。

---

## 9. 真实样本验证

`S-BSAPEG-10.0.dpt`：

- GUI 导入 4350 点；
- explicit wavenumber / `cm^-1` / absorbance / ATR；
- baseline regions（测试显式提供）：3800–3900、950–1000 `cm^-1`；
- preview 显示 baseline 曲线和区域阴影；
- linear baseline preview 成功；
- apply 后生成 `ftir.baseline.linear` history；
- raw X/Y 数组不变；
- source SHA-256 不变：

```text
501fe570b175d8f2a089c21c17f469b1a087d654040f72986c5ba9fe9bffe761
```

没有硬编码该文件名或数值到 GUI；测试显式提供路径和区域。

---

## 10. 架构检查

- `techniques/ftir/baseline.py` Qt-free；
- FTIR backend 不导入 app/GUI/EPR/legacy/Matplotlib；
- GUI 只在 app 层；
- 无循环导入；
- 无 `epr_workflow` runtime import；
- 未修改 EPR 线性基线实现；
- 架构测试：20 passed / 约 6.6 秒；
- 无新增依赖。

---

## 11. 已知限制

1. 只支持 polynomial least squares；没有 robust/weighted 拟合。
2. Condition threshold `1e12` 是数值保护，不是科学验证。
3. Fit coefficients 存储于 centered/scaled X 域。
4. 没有自动区域、自动阶数、rubberband baseline。
5. 没有拟合参数持久化/批量基线处理。
6. 没有 baseline processing export 或 Project 持久化。
7. `ProcessingOperation` 没有 timestamp 字段。
8. 无处理历史时 baseline preview 的 raw 与 current 等价，因此只显示一条 raw 曲线；有历史时显示四条曲线。
9. 区域在 UI 列表中排序显示，用户输入顺序不作为参数顺序保存。
10. 没有多光谱、M13 峰检测、M14 差谱或 M15 导出加固。
11. 真实样本测试依赖用户提供的未跟踪文件。

---

## 12. Git 状态

HEAD：

```text
327d5f633c701cb07c3279754d35427dfc6b8bb0
```

- 未 commit；
- 未 push；
- 未创建 tag；
- 未 amend/rebase；
- 未修改 raw data；
- 未修改 `requirements.txt`；
- 未删除 M12 无关文件；
- `S-BSAPEG-10.0.dpt` 未修改。

---

## 13. 完成清单

- [x] Linear baseline
- [x] Polynomial degree 2–5
- [x] Explicit fitting regions
- [x] Multiple regions
- [x] Increasing/decreasing X
- [x] Point count > degree
- [x] Rank/condition validation
- [x] Non-finite/empty/mismatch rejection
- [x] Single stable snapshot / source unchanged
- [x] ProcessingSession preview
- [x] Apply/undo/redo/reset
- [x] Normalization → baseline
- [x] Undo restores normalized state
- [x] Provenance coefficients/regions/degree
- [x] GUI baseline curves and region shading
- [x] GUI add/remove regions
- [x] GUI parameter invalidation
- [x] GUI language switching
- [x] GUI new import clears preview
- [x] Real 4350-point sample
- [x] EPR regression 298 passed / 1 skipped
- [x] Full 661 passed / 1 skipped
- [x] Warnings-as-errors passed
- [x] No new dependencies
- [x] No raw-data modification
- [x] M13 not started
- [x] No commit/push/tag

**M12 完成。** 基线校正后端、GUI preview/apply 流程、provenance 和真实样本验证均已完成。

M12.1 审计发现的问题已由
[M12.2 修复报告](m12_2_baseline_remediation_report.md) 处理；M13 尚未开始。
