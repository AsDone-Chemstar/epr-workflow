# M12.2 报告：Baseline Audit Remediation

- 状态：**M12.2 完成**
- 基线：M12 / M12.1
- Git HEAD：`327d5f6`
- 前序测试基线：M12 **661 passed, 1 skipped**
- M12.2 结果：**667 passed, 1 skipped**
- 日期：2026-11-04
- Git：**未 commit、未 push、未创建 tag**
- M13 已另行完成；M14：**未开始**

---

## 1. 已修复内容

### A. Fitting region validation

文件：[src/spectralab/techniques/ftir/baseline.py](../src/spectralab/techniques/ftir/baseline.py)

修复：

1. **零贡献 region 拒绝**
   - 每个 region 独立计算 mask 和点数；
   - 任一 region 的点数为 0，抛出 `ftir_baseline_empty_region`；
   - 错误 context 包含：
     - `region_index`
     - `region`
     - `point_count = 0`
     - 所有 region 的 point counts。
2. **区域贡献记录**
   - `BaselineFit` 新增：
     - `region_point_counts`
     - `region_unique_point_counts`
   - diagnostics 同步记录，总和与 `fitting_point_count` 一致；
   - 相邻区域共享端点时使用唯一 mask 计数，端点不重复。
3. **重叠策略**
   - 重叠区域仍在拟合前拒绝；
   - 错误 context 增加两个 region 的索引和明确的 overlap policy；
   - 不做静默合并或自动修剪。
4. 保留总拟合点数 > degree 的验证。

### B. GUI preview invalidation

文件：[src/spectralab/app/gui/ftir_panel.py](../src/spectralab/app/gui/ftir_panel.py)

修复：

1. `region_start.textChanged` 和 `region_end.textChanged` 立即调用
   `_on_region_fields_changed()`：
   - 清除 preview；
   - 更新 fit info；
   - 禁用 Apply。
2. `_add_region()` 清空输入框时阻断信号，避免成功 Add 后重复触发取消。
3. 添加零贡献 region 时，GUI 立即报 `ftir.invalid_region`，不加入列表。
4. Import failure：
   - 如果存在 preview，失败时先 `_invalidate_preview()`；
   - 保留之前已导入的 spectrum、session、history、regions；
   - Apply 保持禁用；
   - 最后显示 import error status。
5. 区域列表显示每个区域的实际唯一点数。
6. Apply 后 fit info 使用 history diagnostics 显示：
   - 已应用的 degree；
   - 已应用的 fitting point count。

### C. ProcessingOperation dataset identity

Files:

- [src/spectralab/core/processing/records.py](../src/spectralab/core/processing/records.py)
- [src/spectralab/core/processing/session.py](../src/spectralab/core/processing/session.py)

修复：

- `ProcessingOperation` 新增可选字段：

```python
input_dataset_id: str | None = None
```

- `ProcessingSession.apply()` 使用：
  `input_dataset_id=self._source.dataset_id`
- 字段适用于所有 operation，包括 FTIR normalization 和 baseline；
- undo/redo 使用已存储的 record，因此 dataset id 随 history 保留；
- 手工构造 `ProcessingOperation` 时该字段可省略，保持兼容；
- 空白/非法 dataset id 会被 `optional_text` 拒绝；
- 没有修改 M3 export schema，也没有新增第二套 history。

---

## 2. 修改文件

修改：

- [src/spectralab/techniques/ftir/baseline.py](../src/spectralab/techniques/ftir/baseline.py)
- [src/spectralab/app/gui/ftir_panel.py](../src/spectralab/app/gui/ftir_panel.py)
- [src/spectralab/app/gui/ftir_translations.py](../src/spectralab/app/gui/ftir_translations.py)
- [src/spectralab/core/processing/records.py](../src/spectralab/core/processing/records.py)
- [src/spectralab/core/processing/session.py](../src/spectralab/core/processing/session.py)
- [tests/test_ftir_baseline.py](../tests/test_ftir_baseline.py)
- [tests/test_ftir_gui.py](../tests/test_ftir_gui.py)
- [tests/test_ftir_normalization.py](../tests/test_ftir_normalization.py)
- [tests/test_processing_session.py](../tests/test_processing_session.py)
- [docs/architecture_proposal.md](architecture_proposal.md)
- [docs/m12_ftir_baseline_report.md](m12_ftir_baseline_report.md)
- [docs/m12_1_baseline_audit_report.md](m12_1_baseline_audit_report.md)
- 本报告

新增：

- `docs/m12_2_baseline_remediation_report.md`

删除：无。

未修改：

- `src/epr_workflow/`
- M11 normalization 算法
- `requirements.txt`
- `S-BSAPEG-10.0.dpt`
- raw data
- M3 export schema

---

## 3. Dataset ID 兼容性

- `ProcessingOperation` 是冻结 dataclass；
- 新字段默认 `None`，旧构造调用仍可运行；
- `ProcessingSession.apply()` 为每次 operation 自动填入 source dataset id；
- `ProcessingOperation` 的 `__post_init__` 使用 `optional_text` 校验；
- 现有 M4 generic processing 测试已更新/扩展并通过；
- FTIR normalization record 现在包含 `input_dataset_id`；
- baseline record 现在包含 `input_dataset_id`；
- Undo/Redo 复用 record，dataset id 不丢失；
- M3 CSV/JSON export schema 未改变；
- 没有第二个 processing-history 系统。

---

## 4. 测试

新增/更新的 focused tests：

- 零贡献/越界 region 被拒绝，错误包含 region index；
- 相邻区域端点去重并记录 unique contributions；
- 重叠区域错误 context 包含 indices 和 policy；
- region 文本编辑立即取消 preview；
- 文本编辑后 Apply 禁用，重新 preview 后恢复；
- GUI 拒绝零贡献 region；
- import failure 清除旧 preview，同时保留旧 spectrum/session/history；
- processing record 的 `input_dataset_id`；
- 手工 record 默认 `None`；
- 非法 dataset id 拒绝；
- normalization record dataset id；
- normalization → baseline record dataset id 在 undo/redo 后保留；
- 既有 normalization 和 baseline 测试全部通过。

实际运行：

```text
完整 verbose：
667 passed, 1 skipped in 56.94s

warnings-as-errors：
667 passed, 1 skipped in 54.40s

原始 EPR 回归：
298 passed, 1 skipped in 38.91s
```

架构：

```text
.\scripts\check.ps1 -Mode arch
20 passed in 6.32s
```

唯一 skip 是既有 Windows `.DTA` 大小写歧义测试。

日志：

- `results/logs/pytest_m12_2_20261104_verbose.txt`
- `results/logs/pytest_m12_2_20261104_userwarning.txt`
- `results/logs/pytest_m12_2_20261104_original.txt`

---

## 5. 剩余限制

1. 重叠区域仍然直接拒绝，不合并点；错误中报告 indices/policy，但不执行拟合。
2. 每个 region 的点数在 UI 和 diagnostics 中以 accepted/adjacent 区域贡献显示；
   重叠区域的联合贡献不会计算，因为拟合在之前终止。
3. 没有自动区域、自动 degree、robust/weighted fitting 或 rubberband baseline。
4. 没有 baseline processing export 或参数持久化。
5. `ProcessingOperation` 仍没有 timestamp 字段。
6. 无历史时 current processed 与 raw 等价，图上仍只显示一条 raw 曲线。
7. Preview 时 GUI 仍执行一次额外 fit 用于 baseline 曲线绘制，然后
   `session.preview()` 再执行拟合；结果确定一致，但没有消除重复计算。
8. 图例在完整处理链中仍主要按最后一个 operation 命名当前 processed 曲线。
9. M12.2 没有 M13 峰检测；M13 已另行完成，仍没有 M14 差谱或 M15 导出加固。

---

## 6. Git 状态

```text
HEAD = 327d5f633c701cb07c3279754d35427dfc6b8bb0
```

- 未 commit
- 未 push
- 未创建 tag
- 未 amend/rebase
- 未修改 raw data
- 未修改 `requirements.txt`
- 未修改 `S-BSAPEG-10.0.dpt`
- 工作树仍保留 M0–M12.2 未提交文件
- **M13 已另行完成；M14 未开始**

---

## 7. DPT 样本

`S-BSAPEG-10.0.dpt` 未被修改。

SHA-256：

```text
501fe570b175d8f2a089c21c17f469b1a087d654040f72986c5ba9fe9bffe761
```

**M12.2 完成。** M13 已完成，见
[M13 FTIR Peak Picking 报告](m13_ftir_peak_picking_report.md)；M14 尚未开始。
