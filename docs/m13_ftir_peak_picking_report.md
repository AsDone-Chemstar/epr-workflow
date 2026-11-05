# M13 报告：FTIR Peak Picking

- 状态：**M13 完成**
- 基线：M12.2
- Git HEAD：`327d5f6`
- 前序测试基线：M12.2 **667 passed, 1 skipped**
- M13 结果：**689 passed, 1 skipped**
- 日期：2026-11-04
- Git：**未 commit、未 push、未创建 tag**
- M14：**未开始**

---

## 1. 实现摘要

新增：

1. 显式 FTIR peak picking；
2. positive / negative / both polarity；
3. raw 或 current processed 检出源；
4. height、prominence、minimum distance、minimum width；
5. Preview / Apply-Save / Clear；
6. Peak Results 表；
7. 正/负峰图上标记；
8. 完整检测 provenance；
9. 中英文运行时切换；
10. 真实 4350 点样本验证。

未实现：

- peak fitting；
- peak deconvolution；
- 化学归属或 functional-group assignment；
- 自动 polarity 推断；
- 自动 smoothing/baseline/normalization；
- Peak Results 文件导出；
- 将峰值检测写入 ProcessingSession history。

---

## 2. 架构与文件

```text
app → techniques → core
```

- Peak detection 算法在 FTIR technique 层；
- Peak result 是独立分析模型；
- GUI 在 app 层；
- 没有修改 core、M11 normalization、M12 baseline 或 legacy EPR。

### 新增

- [src/spectralab/techniques/ftir/peaks.py](../src/spectralab/techniques/ftir/peaks.py)
- [tests/test_ftir_peaks.py](../tests/test_ftir_peaks.py)

### 修改

- [src/spectralab/techniques/ftir/__init__.py](../src/spectralab/techniques/ftir/__init__.py)
- [src/spectralab/app/gui/ftir_panel.py](../src/spectralab/app/gui/ftir_panel.py)
- [src/spectralab/app/gui/ftir_translations.py](../src/spectralab/app/gui/ftir_translations.py)
- [tests/test_ftir_gui.py](../tests/test_ftir_gui.py)
- [docs/architecture_proposal.md](architecture_proposal.md)
- [docs/m12_2_baseline_remediation_report.md](m12_2_baseline_remediation_report.md)
- 本报告

### 未修改

- `src/epr_workflow/`
- `src/spectralab/core/`
- M11 normalization 行为
- M12 baseline 行为
- `requirements.txt`
- raw data / `S-BSAPEG-10.0.dpt`

无删除文件。

---

## 3. 检测算法与参数语义

实现使用现有依赖：

```text
scipy.signal.find_peaks
```

没有新增第三方依赖。

### Polarity

- `positive`：局部极大值；
- `negative`：对 `-y` 做局部极大值检测，即原信号的局部极小值；
- `both`：分别检测并合并，按原始 sample index 排序。

polarity 必须由用户选择，不从数据、文件名或 metadata 推断。

### 参数

| 参数 | 语义 |
| --- | --- |
| height | 取向信号单位；positive 使用 `y`，negative 使用 `-y`；负峰阈值是幅值 |
| prominence | 取向信号的 prominence，信号单位；负峰记录为正幅值 |
| distance_points | 最小峰间距，单位为 sample points，不是物理 X 距离 |
| min_width_points | 最小峰宽，单位为 sample points |

所有参数都显式显示在 GUI 中；blank 表示无阈值。默认：
- source = raw；
- polarity = positive；
- height/prominence/min width = blank；
- distance = 1 sample。

这些默认值可见，不作为极性或数据推断。

### 峰结果

`Peak1D` 记录：

- sample index；
- polarity；
- X position；
- Y value；
- prominence；
- width in samples；
- width in X-axis units。

Width 使用 `find_peaks` 的 half-prominence width，并用 sample-position 到 X 值的线性插值转换成 X 轴单位；不改变原始点序。Descending X 轴使用绝对值，不反转数据。

Limitations 明确记录：

- 首/末样本点不会被报告为局部峰；
- width 是 half-prominence width，并经过线性插值转换为 X 单位。

---

## 4. GUI 行为

FTIR 面板底部增加 tab：

```text
Import options
Peak picking
```

Peak Picking tab 提供：

- Detection source：Raw / Current processed；
- Polarity：Positive / Negative / Both；
- Height threshold；
- Prominence threshold；
- Minimum distance（samples）；
- Minimum width（samples）；
- Preview peaks；
- Apply/Save results；
- Clear results；
- Peak Results table；
- 正/负峰 markers；
- source/polarity/counts/parameters/warnings 状态。

### Preview

- 只读取选中 source；
- 绘制选中 spectrum 和峰标记：
  - positive：绿色 `^`；
  - negative：红色 `v`；
- 不修改 raw/current processed/session/history/metadata/provenance；
- Preview 结果进入表，Apply 前不写任何持久状态；
- 参数或 source/polarity 改变会使 preview 失效；
- Apply 在有效 preview 前保持禁用。

### Apply / Clear

- Apply/Save 把 preview 结果转为 applied result；
- 不修改 spectrum 或 ProcessingSession；
- Clear 清除 preview/applied 结果、表和 markers；
- 新导入 spectrum 会清除峰值结果；
- 应用 normalization/baseline 或 undo/redo/reset 会清除峰值结果，避免 stale processed-source results。

### Results table

列：

- sample index；
- polarity；
- X；
- Y；
- prominence；
- width (samples)；
- width (X unit)。

表头显示实际 axis/signal unit；未知单位显示 unknown。

### Language

中英文覆盖：

- tab；
- 所有参数标签和 placeholder；
- 按钮；
- 状态和 warning；
- peak table headers；
- polarity；
- markers；
- source/parameter summary。

---

## 5. Provenance 设计

Peak detection 是分析结果，不是 ProcessingSession 操作。

`PeakDetectionResult` 记录：

- `algorithm = scipy.signal.find_peaks`
- `algorithm_version = 1.0.0`
- source (`raw` / `processed`)
- polarity
- height
- prominence
- distance_points
- min_width_points
- dataset_id
- axis quantity/unit/direction
- signal semantics/unit
- source operation history（processed source 时的 operation IDs）
- positive_count / negative_count / peak_count
- warnings
- limitations
- peaks（float 结果，不引用 raw/processed arrays）

没有创建第二套 processing history，也没有把峰值结果写入 `ProcessingOperation`。

---

## 6. 测试结果

新增 **22 个 M13 测试**：

- [tests/test_ftir_peaks.py](../tests/test_ftir_peaks.py)：14
- `tests/test_ftir_gui.py` 新增 peak GUI 测试：8

覆盖：

- positive/negative/both；
- height/prominence；
- minimum distance/width；
- increasing/decreasing X；
- boundary peaks 与限制；
- constant/no-peak；
- empty/mismatch/nonfinite arrays；
- invalid parameters；
- preview 不修改 session/raw；
- Preview/Apply/Clear；
- source processed 和 operation history provenance；
- parameter/source preview invalidation；
- 新导入/processing 变化清除峰值结果；
- 中英文；
- 真实 4350 点样本；
- M11 normalization/M12 baseline 回归。

实际运行：

```text
完整 verbose：
689 passed, 1 skipped in 60.13s

warnings-as-errors：
689 passed, 1 skipped in 59.91s

原始 EPR 回归：
298 passed, 1 skipped in 35.13s

架构：
20 passed in 11.31s
```

唯一 skip 是既有 Windows `.DTA` 大小写歧义测试。

日志：

- `results/logs/pytest_m13_20261104_verbose.txt`
- `results/logs/pytest_m13_20261104_userwarning.txt`
- `results/logs/pytest_m13_20261104_original.txt`

M12.2 → M13：667 → **689 passed**。

---

## 7. 科学完整性

- 不修改 raw Spectrum1D；
- 不修改 current processed signal；
- 不修改 ProcessingSession history/undo/redo；
- 不排序、反转、插值、平滑、归一化或 baseline-correct；
- 保留原始 X 轴和点序；
- 支持递增/递减轴；
- 非有限/空输入明确拒绝；
- 不从信号推断 polarity；
- 不做化学归属；
- 不自动执行 peak detection。

真实样本：

- `S-BSAPEG-10.0.dpt`；
- 4350 点；
- preview 不修改源；
- SHA-256 不变：

```text
501fe570b175d8f2a089c21c17f469b1a087d654040f72986c5ba9fe9bffe761
```

---

## 8. 架构检查

- `techniques/ftir/peaks.py` Qt-free；
- FTIR backend 不导入 app/GUI/EPR/legacy/Matplotlib；
- GUI 在 app 层；
- 没有循环导入；
- 没有 `epr_workflow` runtime import；
- 没有修改 core 或 ProcessingSession；
- 没有新依赖；
- 20 个架构测试通过。

---

## 9. 已知限制与风险

1. `find_peaks` 不把首/末 sample 作为局部峰；result limitations 明确记录。
2. Height 对 negative peak 作用于 `-y`，即幅值；GUI 标签和报告已说明。
3. Width 是 half-prominence width，不是 FWHM 或其他定义。
4. 没有峰拟合、deconvolution、峰面积或化学归属。
5. Peak Results 没有导出到文件。
6. 没有自动 polarity、自动参数或自动检测。
7. 峰值结果是内存中的 analysis result，不进入 ProcessingSession。
8. Processed source 在 processing 改变后会使结果清除；这是有意的 stale-result 防护。
9. 没有 M14 差谱/轴匹配或 M15 导出加固。
10. 真实样本测试依赖用户提供的未跟踪文件。

---

## 10. Git 状态

```text
HEAD = 327d5f633c701cb07c3279754d35427dfc6b8bb0
```

- 未 commit；
- 未 push；
- 未创建 tag；
- 未 amend/rebase；
- 未修改 raw data；
- 未修改 `requirements.txt`；
- 未修改 `S-BSAPEG-10.0.dpt`；
- 工作树保留 M0–M13 未提交改动；
- **M14 未开始**。

`S-BSAPEG-10.0.dpt` SHA-256：

```text
501fe570b175d8f2a089c21c17f469b1a087d654040f72986c5ba9fe9bffe761
```

**M13 完成。** 未开始 M14。
