# M12.1 审计报告：FTIR Baseline Correction

- 审计状态：**发现问题，建议修正后再最终接受**
- 审计范围：M12 FTIR linear/polynomial baseline
- Git HEAD：`327d5f6`
- 生产代码修改：**无**
- 测试修改：**无**
- Git：**未 commit、未 push、未创建 tag**
- M13：**未开始**

---

## 1. 审计范围与文件

已检查：

- [src/spectralab/techniques/ftir/baseline.py](../src/spectralab/techniques/ftir/baseline.py)
- [src/spectralab/app/gui/ftir_panel.py](../src/spectralab/app/gui/ftir_panel.py)
- [src/spectralab/core/processing/session.py](../src/spectralab/core/processing/session.py)
- [src/spectralab/core/processing/records.py](../src/spectralab/core/processing/records.py)
- [tests/test_ftir_baseline.py](../tests/test_ftir_baseline.py)
- [tests/test_ftir_gui.py](../tests/test_ftir_gui.py)
- [docs/m12_ftir_baseline_report.md](m12_ftir_baseline_report.md)
- [docs/architecture_proposal.md](architecture_proposal.md)
- 相关 M11 normalization tests 与 architecture tests

审计只读；除本报告外没有修改任何文件。

---

## 2. 执行的只读检查

```text
.\.venv\Scripts\python.exe -m pytest -q tests/test_ftir_baseline.py tests/test_ftir_gui.py tests/test_architecture.py
结果：79 passed in 14.79s
```

另执行了只读 Python 审计脚本，检查：

- 相邻区域是否重复计算端点；
- increasing/decreasing X 轴拟合是否等价；
- provenance 字段；
- apply → undo → redo → new apply；
- failed apply 是否改变 session；
- 空/越界 region 的行为；
- GUI preview 在 region 输入框变化后是否失效。

`git status` 与源文件 SHA-256 检查也执行；`S-BSAPEG-10.0.dpt` 未改变。

---

## 3. Audit A — Numerical stability

### 已验证

- 拟合 X 使用：

```text
z = (x_fit - mean(x_fit)) / max(abs(x_fit - mean(x_fit)))
```

- Vandermonde 矩阵使用 `np.vander(..., increasing=True)`；
- 使用 `numpy.linalg.lstsq(..., rcond=None)`；
- rank < degree + 1 时拒绝；
- condition number 使用 Vandermonde 的 largest/smallest singular value；
- condition > `1e12` 时拒绝；
- coefficients、baseline、corrected 都检查 finite；
- baseline 使用同一 center/scale 在原始 X 轴上求值；
- 不会自动降低 degree 或改变区域。

相关位置：

- [baseline.py:283](../src/spectralab/techniques/ftir/baseline.py#L283)：mask
- [baseline.py:300](../src/spectralab/techniques/ftir/baseline.py#L300)：center/scale
- [baseline.py:309](../src/spectralab/techniques/ftir/baseline.py#L309)：Vandermonde
- [baseline.py:334](../src/spectralab/techniques/ftir/baseline.py#L334)：condition
- [baseline.py:248](../src/spectralab/techniques/ftir/baseline.py#L248)：diagnostics

### 判断

数值核心没有发现 Critical/High 问题。
`1e12` 是数值稳定性保护阈值，不是科学有效性证明，也不是严格误差上界；实现和报告都将其记录为 condition limit。

系数明确记录在：

```text
coefficient_domain = "centered_scaled_x"
```

并同时记录 `x_center`、`x_scale`，所以可复现。若外部消费者期望原始 X 域系数，需要自行变换。

**严重度：Informational。**

---

## 4. Audit B — Fitting-region boundaries

### 已验证

- 区域是闭区间 `[start, end]`；
- 区域自动 canonicalize，支持递增/递减 X；
- 相邻区域 `[0,3]`、`[3,6]` 共享端点时，mask OR 只计算端点一次：

```text
x = 0..6，adjacent_count = 7
```

- 重叠区域被拒绝；
- `x_fit` 由原始 X 顺序 mask 取得，不排序、不反转数据；
- increasing/decreasing 的同一数据在只读检查中得到相同 coefficients、center、scale，baseline 最大绝对差为 `0.0`；
- GUI 与 provenance 的总 fitting point count 都来自同一个 `fit.fitting_point_count`。

### 确认问题 B1（Medium）

**空/越界 region 可以被静默接受。**

实测：

```text
x = 1000..1010
regions = (0,5), (1000,1005)
degree = 1
```

第二个区域完全不在数据范围内，但拟合成功：

```text
regions = [{'start': 0.0, 'end': 5.0}, {'start': 1000.0, 'end': 1005.0}]
fitting_point_count = 6
fit_succeeded = True
```

代码只构造一个总 mask：

[baseline.py:283](../src/spectralab/techniques/ftir/baseline.py#L283)

没有逐区域检查拟合点数。结果：

- 数值拟合只使用了有效区域的点；
- 空区域仍出现在 `parameters`、`diagnostics` 和 GUI region list 中；
- GUI 只显示总点数，不显示“该区域贡献 0 点”；
- 用户可能误以为两个区域都约束了基线；
- 这违反了“不要静默修复/忽略无效输入”的科学透明性原则。

**建议：** 要求每个 region 至少包含一个数据点，或至少记录并显示 per-region point count / warning；最好在 region 层面明确拒绝零贡献区域。

### 严重度

**Medium**。数值结果没有被污染，但 provenance 和用户理解可能误导。

---

## 5. Audit C — Preview 与 Session 一致性

### 已验证的转换

| 转换 | 行为 |
| --- | --- |
| Preview → 改 algorithm | `baseline_algorithm.currentIndexChanged` → `_on_baseline_parameters_changed` → 清除 preview |
| Preview → 改 degree | 同一 handler → 清除 preview |
| Preview → Add/Remove region | 成功操作后 `_invalidate_preview()` |
| Preview → Cancel | `_cancel_preview()` 清除，不写 history |
| Preview → import new spectrum | 成功 import 清除 preview 和 regions |
| Apply → Undo → Redo | session 恢复存储状态；GUI 清除 preview |
| Apply → Undo → new Apply | `session.apply()` 清空 redo；只读脚本确认 |
| Failed Apply | `_execute` 先验证/执行，session 不变；只读脚本确认 history/redo 保持 |

Session 侧：

- `preview()` 使用 `_execute()`，不写 `_applied`/`_redo`；
- `apply()` 只在完整验证后 append；
- failed operation 不会部分修改。

### 确认问题 C1（Medium）

**编辑 region 文本但未点 Add，不会使 preview 失效，Apply 仍然启用。**

GUI 只连接了：

- algorithm；
- degree；
- Add/Remove region。

[ftir_panel.py:195](../src/spectralab/app/gui/ftir_panel.py#L195) 的 `region_start` / `region_end`
没有 `textChanged` 连接。

只读 GUI 检查确认：

```text
preview_before_edit = True, apply_enabled = True
随后把 start/end 改为 1010/1015（未 Add）
preview_after_text_edit_without_add = True, apply_enabled = True
regions 仍是旧的两个区域
```

用户可能输入新区域后直接点击 Apply，而实际应用的是旧 preview/旧区域。
这是 GUI 层面的科学操作风险，不是数值算法错误。

**建议：** 在 `region_start.textChanged` / `region_end.textChanged` 时清除 preview 并禁用 Apply，或要求用户必须 Add 后才能再次 preview；同时给出明确提示。

### 潜在风险 C2（Low）

新文件导入失败时，旧文件的 preview/regions 会保留，同时显示 error status。
这通常与旧 spectrum 一致，但用户可能误以为新文件已加载。当前不是状态损坏；属于 UX 风险。

### 潜在风险 C3（Low）

Preview 期间直接编辑文本但不 Add，仍显示旧区域阴影和旧 preview；与 C1 同一根因。

---

## 6. Audit D — Plot semantics

### 已验证

- preview 时 raw 使用灰色虚线；
- current processed 使用绿色实线（仅在有处理历史时）；
- estimated baseline 使用橙色虚线；
- preview-corrected 使用蓝色；
- legend 有独立标签；
- fitting regions 使用半透明阴影；
- descending X 只通过 `axes.set_xlim` 影响显示，不修改数组；
- raw/source X/Y 在预览和应用后保持不变。

### 确认问题 D1（Low）

**没有处理历史时，不单独绘制 current processed 曲线。**

代码条件：

[ftir_panel.py:506](../src/spectralab/app/gui/ftir_panel.py#L506)

```python
if self._session is not None and self._session.history:
    ... plot current ...
```

没有历史时 current 与 raw 数值等价，因此只显示 raw 曲线。
这在数学上等价，但严格按“Preview 必须显示 current processed”的要求，当前标签中没有显式 current 曲线。

**建议：** 可在无历史时给 raw 曲线增加说明，或显式绘制重叠的 current 曲线并标注等价关系。

### 潜在风险 D2（Low）

`_processed_label()` 按最后一个 operation 选择 “归一化” 或 “基线校正”，多步处理链的当前曲线只反映最后一步名称。
metadata history 仍完整；图例名称可能被用户理解为“只有最后一步”。
建议使用通用 “处理后 / Processed” 标签，或在图例中显示操作链摘要。

---

## 7. Additional checks

### Provenance

已记录：

- operation id
- algorithm / degree
- regions
- fitting_point_count
- scaled coefficients + center/scale
- condition number/limit
- rank
- numerical method
- point count
- input/output state ids

### 确认问题 P1（Medium/Low）

**`ProcessingOperation` 本身没有 input dataset identifier。**

- `ProcessedSpectrum.source.dataset_id` 保留 dataset identity；
- `ProcessingOperation` 只有 `input_state_id`，没有 `input_dataset_id`；
- 只读检查确认：

```text
record_has_dataset_id = False
source_dataset_id = audit-dataset
input_state_id = original
```

当前 GUI 中可以通过 `ProcessedSpectrum.source.dataset_id` 追溯；但如果单独序列化/导出 history record，dataset identity 会丢失。
M12 任务明确要求记录 input dataset identifier。

**建议：** 为 history record 增加 `input_dataset_id`（或在 apply 时把 dataset id 写入 diagnostics），并在未来 export 前固定该结构。

### 其他

- Baseline 作用于 current processed signal：代码 `_preview` 使用 `session.current`，
  `session.preview` 也使用 current state。
- Normalization → Baseline → Undo → normalized：测试通过。
- Raw `Spectrum1D` 未修改：测试通过。
- 架构：baseline Qt-free，GUI 在 app 层；架构测试 20 passed。
- 无新依赖。

---

## 8. 问题分级汇总

| 等级 | 数量 | 结论 |
| --- | --- | --- |
| Critical | 0 | 无数值/数据破坏 |
| High | 0 | 无 session/架构破坏 |
| Medium | 3 | 空区域静默忽略；region 文本编辑不失效 preview；record 级 dataset id 缺失 |
| Low | 4 | post-apply fit info pending；无历史 current 曲线省略；last-op 图例标签；导入失败旧 preview |
| Informational | 3 | 重复 fit、condition heuristic、scaled coefficients |

---

## 9. Confirmed vs potential

### Confirmed

1. 空/越界 region 被静默接受，贡献 0 点。
2. 编辑 region 输入框但不 Add 时，旧 preview 仍有效，Apply 仍可用。
3. ProcessingOperation record 本身没有 input dataset id。
4. Apply 后 fit info 显示“尚未拟合”（因为 preview fit 被清除）。
5. 无历史时 baseline preview 只有 raw，没有独立 current processed 曲线。

### Potential risks

- 导入失败后旧 preview 保留可能造成用户误解。
- `_processed_label` 只反映最后一个 operation。
- Preview 中 fit 被计算两次（GUI 显示 + session preview），虽然确定性一致，但属于不必要计算。
- Condition threshold 是工程性保护，并非科学验证。

### No issue found

- 相邻端点不会重复计数（实测 7 个唯一点）。
- 重叠区域会拒绝。
- Increasing/decreasing 轴拟合结果等价。
- Fitting-point count 与 mask 实际点数一致（总点数）。
- Preview 不写 history/redo。
- Apply/undo/redo/new apply/failed apply session 状态一致。
- Raw/Spectrum1D/source 未修改。
- 架构和依赖边界正常。

---

## 10. 建议修复

### 必须修复（建议 M12 最终接受前）

1. **Reject or explicitly record zero-point regions.**
   - 在 `fit_baseline` 中逐 region 计算 mask count；
   - `count == 0` 直接报 `ftir_baseline_empty_region`；
   - 或在 GUI 和 diagnostics 中记录每区域点数并警告。
2. **Invalidate preview on region text edits.**
   - 连接 `region_start.textChanged` / `region_end.textChanged` 到
     `_invalidate_preview()`，并更新 Apply 状态。

### 建议修复

3. 在 `ProcessingOperation` 或 diagnostics 中加入 `input_dataset_id`。
4. Apply 后保留最后一个已应用 fit 的 degree/fitting-point 摘要，避免“尚未拟合”
   与已应用状态冲突。
5. 无历史时显式说明 raw 与 current 等价，或显示当前处理曲线。
6. 图例使用通用 “处理后” 标签或显示完整操作链。

### 不需要修改

- 中心化/缩放方法；
- Vandermonde/lstsq；
- rank/condition/finite 校验；
- 区域闭区间和重叠规则；
- Session preview/apply/undo/redo；
- baseline 数值算法。

---

## 11. 验收结论

**不建议将 M12 无条件接受为最终状态。**

数值核心、Session 状态管理和架构边界是可靠的；没有 Critical/High 问题。
但至少应先处理两个 Medium 问题：

1. 空/越界 region 静默贡献 0 点；
2. region 文本编辑后旧 preview 仍可 Apply。

第三个 Medium 问题（record 级 input dataset id）在当前 UI 中可通过
`ProcessedSpectrum.source.dataset_id` 追溯，但在 history 单独导出前应补齐。

M12 的数值算法本身可以保留，不需要重写。

---

## 12. Git 与数据状态

- HEAD：`327d5f633c701cb07c3279754d35427dfc6b8bb0`
- 未 commit
- 未 push
- 未创建 tag
- 未修改生产代码
- 未修改测试
- 未修改 `requirements.txt`
- 未修改 `S-BSAPEG-10.0.dpt`
- `S-BSAPEG-10.0.dpt` SHA-256：

```text
501fe570b175d8f2a089c21c17f469b1a087d654040f72986c5ba9fe9bffe761
```

本报告是本次审计唯一新增文件。

审计发现已由 [M12.2 Baseline Remediation](m12_2_baseline_remediation_report.md)
处理；本报告保留为审计时点的原始记录。
