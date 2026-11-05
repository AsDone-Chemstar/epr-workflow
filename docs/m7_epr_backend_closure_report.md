# M7 报告：EPR Backend Closure

- 状态：**M7 完成**
- 基线版本：EPR Workflow **v0.2.0**
- Git 基线：`327d5f6`
- 前序测试基线：M6 **468 passed, 1 skipped**
- M7 基线：**494 passed, 1 skipped**
- 日期：2026-11-02
- 范围：将 SpectraLab EPR backend 从旧 `epr_workflow` 运行时依赖中迁移出来
- 旧应用：**未修改，仍独立可用**
- Git：**未 commit、未 push**

---

## 1. Legacy dependency inventory

在编码前建立了完整清单：

[文档：M7 EPR Legacy Dependency Inventory](m7_dependency_inventory.md)

### 发现并迁移的运行时依赖

| 旧模块 | 旧 API | 新位置 |
| --- | --- | --- |
| `epr_workflow.plot_asc` | `read_asc()` | `techniques/epr/importers/_asc_reader.py` |
| `epr_workflow.plot_asc` | `AscFormatError` | `_asc_reader.py` |
| `epr_workflow.plot_asc` | `AscDataError` | `_asc_reader.py` |
| `epr_workflow.bes3t` | `read_bes3t()` | `techniques/epr/importers/_bes3t_reader.py` |
| `epr_workflow.bes3t` | `find_companion_dta()` | `_bes3t_reader.py` |
| `epr_workflow.preprocessing` | `BaselineWindow` / `LinearBaselineSpec` | `techniques/epr/processing_impl.py` |
| `epr_workflow.preprocessing` | `SavgolSpec` | `processing_impl.py` |
| `epr_workflow.preprocessing` | `fit_linear_baseline()` | `processing_impl.py` |
| `epr_workflow.preprocessing` | `smooth_savgol()` | `processing_impl.py` |
| `epr_workflow.preprocessing` | baseline/Savgol constants | `processing_impl.py` |

迁移后，`src/spectralab/` 中不再有 `epr_workflow` import。

---

## 2. 新增与修改文件

### 新增 EPR backend 实现

- [src/spectralab/techniques/epr/importers/_import_result.py](../src/spectralab/techniques/epr/importers/_import_result.py)
- [src/spectralab/techniques/epr/importers/_asc_reader.py](../src/spectralab/techniques/epr/importers/_asc_reader.py)
- [src/spectralab/techniques/epr/importers/_bes3t_reader.py](../src/spectralab/techniques/epr/importers/_bes3t_reader.py)
- [src/spectralab/techniques/epr/processing_impl.py](../src/spectralab/techniques/epr/processing_impl.py)

### 修改现有 SpectraLab EPR backend

- `techniques/epr/importers/xepr_asc.py`：改用内部 ASC reader
- `techniques/epr/importers/bes3t.py`：改用内部 BES3T reader
- `techniques/epr/importers/_common.py`：改用内部 ASC 错误类型
- `techniques/epr/processing_adapter.py`：改用内部 processing 实现；继续接受旧 spec
- `techniques/epr/__init__.py`：导出内部 EPR specs

### 新增测试

- [tests/test_epr_backend.py](../tests/test_epr_backend.py)：22 个迁移/等价测试
- [tests/test_m7_architecture.py](../tests/test_m7_architecture.py)：4 个边界测试

合计 **26 个新测试**。

### 新增/更新文档

- [docs/m7_dependency_inventory.md](m7_dependency_inventory.md)
- 本报告
- [docs/architecture_proposal.md](architecture_proposal.md)：更新 M7 状态与测试基线
- M6 报告页脚更新为已进入 M7

### 未修改

- `src/epr_workflow/` 全部生产代码
- 旧 EPR GUI、CLI、batch、export
- M3 schema
- M4 generic `ProcessingSession`
- M5 plotting API
- M6 CLI/batch 代码
- 原始测试和 raw data
- `requirements.txt`

---

## 3. ASC migration results

### 新实现

`techniques/epr/importers/_asc_reader.py` 独立实现：

- 三列 Xepr ASC 表头识别
- 列顺序检查
- 逐行解析、非数值/非有限行拒绝
- 原始点序保持
- index continuity 诊断
- 重复/非单调轴拒绝
- 源文件 SHA-256/大小
- warnings/rejected rows/诊断计数

### 等价证据

与旧 `read_asc()` 比较：

- DataFrame 列、dtype、逐值内容完全相等
- rejected rows 与 warnings 顺序/内容相等
- `field_order`、index continuity 相等
- SHA-256、文件大小相等
- format metadata/provenance 字段相等
- 真 M0 ASC 1024 点 baseline 相等
- malformed header、过少点、非单调轴的错误类型和消息相等
- 源文件在读取前后 hash 不变

### 旧依赖状态

`XeprAscImporter` 不再导入或调用 `epr_workflow.plot_asc`。

---

## 4. BES3T migration results

### 新实现

`techniques/epr/importers/_bes3t_reader.py` 独立实现：

- `.DSC` / `.DTA` 大小写不敏感配对
- 缺失/歧义 companion 拒绝
- `#DESC` section 解析
- XTYP IDX / XMIN / XWID / XPTS 轴
- IRFMT/BSEQ/IKKF 校验
- real-only、1D-only、Gauss-only
- truncated/trailing payload 拒绝
- descriptor/data 双源哈希和规范组合哈希
- 原始 int/float 数值到 float64 的精确转换

### 等价证据

与旧 `read_bes3t()` 比较：

- data frame/点序/X/Y 完全相等
- `source_files`、`source_hashes`、规范 SHA-256 相等
- `format_metadata["axis"]`、`format_metadata["binary"]` 相等
- real M0 BES3T 1024 点 baseline 相等
- big-endian float64 与 little-endian float32 解释相等
- missing companion、unsupported units、truncated payload 的旧错误码相同
- 源文件不修改

### 旧依赖状态

`Bes3tImporter` 不再导入或调用 `epr_workflow.bes3t`。

---

## 5. Processing migration results

### 新实现

`techniques/epr/processing_impl.py` 包含独立实现：

- `EprProcessingError` 及参数/窗口错误类型
- `BaselineWindow`、`LinearBaselineSpec`、`SavgolSpec`
- `BaselineFit`、`SavgolDiagnostics`、`PreprocessingWarning`
- field validation、window validation
- OLS line fit
- warning order and diagnostics
- SciPy Savitzky-Golay call

没有新增算法，也没有改变参数、warning code、operation ID 或算法版本。

### Adapter compatibility

`processing_adapter.py`：

- 使用内部实现；
- 继续结构化接受旧 `LinearBaselineSpec`/`SavgolSpec`，将其转换为内部 frozen spec；
- 因此已有 M4 调用和测试无需修改；
- operation ID 仍为 `linear_baseline` / `savitzky_golay`；
- `technique="epr"`；
- version 仍为 `1.0`；
- 继续保留 `epr_axis_unsupported` 对非 `magnetic_field`/`G` 轴的拒绝。

### 等价证据

- 线性基线 `fit.as_dict()` 完全相等
- 警告消息/context/顺序完全相等
- 递减轴 fit 完全相等
- Savitzky-Golay 输出数组逐值相等
- smoothing diagnostics 完全相等
- 无效 Savgol 参数 code 相等
- M4 EPR processing adapter 测试继续通过
- generic `ProcessingSession` 未修改

---

## 6. 精确数值与 provenance 证据

使用 M0 `tests/fixtures/m0_baseline.json` 及真实数据：

- ASC：
  - 1024 点
  - X/Y 与旧 parser 逐值相等
  - SHA-256 与 M0 baseline 相等
- BES3T：
  - 1024 点
  - X/Y 与旧 parser 逐值相等
  - descriptor/data 哈希和规范组合哈希与 M0 baseline 相等
  - binary dtype/byte order 相等
- baseline/Savgol：
  - 新/旧算法确定性 float64 结果完全相等
  - diagnostics 完全相等
- 所有比较均使用精确相等（DataFrame equals、array_equal、dict equality），没有用宽容差掩盖差异。

---

## 7. 架构依赖结果

验证结果：

- `src/spectralab/` AST 中不存在 `epr_workflow` / `epr_workflow.*` import
- 独立 subprocess 导入 `spectralab.techniques.epr`、importers、processing
  adapter、app registry/CLI/batch 后，`epr_workflow` 未加载
- 同一 subprocess 中 Qt 未加载
- 旧 `epr_workflow` 仍可独立导入
- 旧 `main/read_dataset/PreprocessingSession` 仍可用
- 新 EPR backend 无循环导入
- `spectralab.app` 仍通过显式 importer registry 工作
- M6 CLI 行为不变
- 无新增依赖

### 剩余旧依赖

运行时：**无**。

仅测试层仍导入旧实现作为数值比较参考，这是有意保留的回归基线，不属于 backend 运行时依赖。

---

## 8. 回归结果

新增 **26 个 M7 测试**：

- `tests/test_epr_backend.py`：22
- `tests/test_m7_architecture.py`：4

实际运行：

```text
完整测试集 pytest -v：
494 passed, 1 skipped
exit code 0

pytest -q -W error::UserWarning：
494 passed, 1 skipped
exit code 0

原 EPR 测试集（排除 M0–M7 测试）：
298 passed, 1 skipped
exit code 0
```

基线比较：

- M6：468 passed, 1 skipped
- M7：494 passed, 1 skipped
- 新增 26 个测试
- 原 EPR 子集保持 298 passed / 1 skipped

日志：

- `results/logs/pytest_m7_20261102_verbose.txt`
- `results/logs/pytest_m7_20261102_userwarning.txt`
- `results/logs/pytest_m7_20261102_original.txt`

---

## 9. 向后兼容

- 旧 `epr_workflow` 生产代码未修改；
- 旧 parser/preprocessing/GUI/CLI/batch/export 未修改；
- 旧应用仍可独立运行；
- M3 raw export schema 未修改；
- M4 `ProcessingSession` 未修改；
- M5 plotting API 未修改；
- M6 CLI 未修改；
- 现有测试未修改；
- 原 EPR 子集 298 passed / 1 skipped 不变；
- 无新增依赖。

---

## 10. 剩余技术债与风险

1. 新 EPR reader 和 processing 实现是旧实现的受控复制；这是为了避免修改旧应用并先完成独立
   backend，但也意味着两套代码未来可能漂移。
2. 旧 `epr_workflow` 仍保留自己的 parser、preprocessing、GUI、CLI 和导出路径，尚未删除或
   改为调用新 backend。
3. `spectralab.core.legacy_adapter` 仍用于把本地 EPR import result 转成 `Spectrum1D`；
   它不导入 `epr_workflow`，但名称和结构仍是过渡性的。
4. 新 ASC/BES3T reader 仍使用本地 `EprImportResult` 中间结构，再通过 core bridge
   转成 `Spectrum1D`；直接构建 `Spectrum1D` 的进一步简化可留待后续重构。
5. M4 未迁移的旧 EPR preview/pending/raw-input 重排仍只在旧应用中存在。
6. 旧 EPR JSON preprocessing record 仍由旧应用生成，未迁移。
7. 没有新增格式、GUI、FTIR 或新算法。
8. 测试仍导入旧实现做精确比较；旧测试和旧代码不能被删除，否则会失去独立回归基线。

---

## 11. M7 完成清单

- [x] 编码前依赖清单
- [x] 独立 ASC reader
- [x] 独立 BES3T reader 和 companion 查找
- [x] 独立 baseline 实现
- [x] 独立 Savitzky-Golay 实现
- [x] 旧 spec 结构化兼容
- [x] ASC 数值/provenance 等价
- [x] BES3T 数值/provenance 等价
- [x] baseline/Savgol 数值与诊断等价
- [x] 错误码/警告顺序验证
- [x] 递增/递减轴验证
- [x] `src/spectralab` 无 `epr_workflow` import
- [x] EPR backend 运行时无旧包加载
- [x] 旧应用独立可用
- [x] 无 Qt
- [x] 无循环导入
- [x] M6 CLI 行为不变
- [x] 原 EPR 测试 298 passed / 1 skipped
- [x] 完整测试 494 passed / 1 skipped
- [x] `-W error::UserWarning` 通过
- [x] 未 commit、未 push

**M7 状态：完成。** M8 已完成，见
[M8 GUI Architecture 报告](m8_gui_architecture_report.md)；M9 尚未开始。
