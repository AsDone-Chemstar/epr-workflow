# M7 EPR Legacy Dependency Inventory

- 基线：`327d5f6`
- 前序状态：M0–M6 完成，468 passed / 1 skipped
- 本文件在 M7 编码前建立，用于记录 `spectralab.techniques.epr` 对
  `epr_workflow` 的全部运行时依赖。

## 1. 运行时依赖矩阵

| # | 导入模块 | 旧函数/类 | 当前调用方 | 建议替代 | 兼容风险 | 必要等价测试 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `epr_workflow.plot_asc` | `read_asc()` | `techniques/epr/importers/xepr_asc.py::XeprAscImporter.read` | SpectraLab EPR 内部 ASC reader；直接返回本地导入结果并转 `Spectrum1D` | ASC 表头、列顺序、拒绝行、非有限/重复轴、warning、index continuity、hash/provenance 必须完全一致 | 真 ASC M0 数值；合成有效/畸形 ASC；warning 与错误码 |
| 2 | `epr_workflow.plot_asc` | `AscFormatError` | `techniques/epr/importers/_common.py` 错误映射 | EPR 技术层自己的 ASC 错误类型 | 旧 CLI 的 `AscFormatError` 不受影响；新 backend 只映射内部异常 | malformed header、column order |
| 3 | `epr_workflow.plot_asc` | `AscDataError` | `_common.py` 错误映射 | EPR 技术层自己的 ASC 错误类型 | 错误码/消息与旧 parser 一致 | too few rows、non-monotonic、nonfinite |
| 4 | `epr_workflow.bes3t` | `read_bes3t()` | `techniques/epr/importers/bes3t.py::Bes3tImporter.read` | SpectraLab EPR 内部 BES3T reader | DSC/DTA 配对、参数校验、dtype/字节序、截断/尾随字节、unsupported 情况、hash 必须一致 | 真 BES3T M0 数值；合成有效/畸形 BES3T；错误码 |
| 5 | `epr_workflow.bes3t` | `find_companion_dta()` | `bes3t.py::collect_sources`、`read` | 内部 companion 查找函数 | 大小写不敏感 stem、歧义/缺失 companion、错误码 | companion missing/ambiguous |
| 6 | `epr_workflow.preprocessing` | `BaselineWindow` | `processing_adapter` | EPR 内部 frozen `EprBaselineWindow` | 旧测试会继续传旧 `BaselineWindow`；适配器需结构化接受并转换 | baseline window constructor validation |
| 7 | `epr_workflow.preprocessing` | `LinearBaselineSpec` | `processing_adapter` | EPR 内部 `EprLinearBaselineSpec` | 旧测试/用户可能传旧 spec；保持 duck-type 兼容 | baseline specs |
| 8 | `epr_workflow.preprocessing` | `SavgolSpec` | `processing_adapter` | EPR 内部 `EprSavgolSpec` | 同上；参数校验/默认值一致 | Savgol specs |
| 9 | `epr_workflow.preprocessing` | `fit_linear_baseline()` | baseline operation | 复制并独立实现同一 OLS/warnings/diagnostics | 细微浮点顺序/警告文字/诊断字段可能变化 | baseline numerical exactness + warnings |
| 10 | `epr_workflow.preprocessing` | `smooth_savgol()` | Savgol operation | 独立调用 SciPy `savgol_filter`，复制同参数/诊断 | SciPy 调用顺序必须一致 | Savgol exactness + diagnostics |
| 11 | `epr_workflow.preprocessing` | `BASELINE_OPERATION`, `BASELINE_METHOD`, `BASELINE_ALGORITHM_VERSION` | operation metadata | EPR 内部常量 | 旧 operation ID 和版本应保留 | record metadata |
| 12 | `epr_workflow.preprocessing` | `SAVGOL_OPERATION`, `SAVGOL_METHOD`, `SAVGOL_ALGORITHM_VERSION` | operation metadata | EPR 内部常量 | 旧 operation ID 和版本应保留 | record metadata |

## 2. 非运行时依赖

- `spectralab.core.legacy_adapter` 不在运行时导入 `epr_workflow`；它是 M1
  兼容桥，继续保留。
- `tests/` 中现有 M4 测试使用旧 `LinearBaselineSpec`/`SavgolSpec` 作为输入；
  迁移后适配器应继续接受这两个对象，避免修改现有测试。
- `spectralab.app.registry` 通过显式注册导入 EPR importers；迁移完成后应
  不再间接加载 `epr_workflow`。

## 3. 迁移边界

- 不修改 `epr_workflow` 任何生产模块。
- 新 EPR backend 不运行时导入 `epr_workflow`。
- 解析器结果必须保留 M0 exact numerical/provenance baseline。
- 处理实现必须保留旧 operation ID、版本、参数验证、warning 顺序和诊断。
- 旧 EPR CLI/GUI/导出继续使用旧 `epr_workflow`，不受新 backend 影响。

## 4. 计划验证

- M0 `asc_real` / `bes3t_real` exact X/Y/点序/hash。
- 有效/畸形 ASC 和 BES3T 合成样本。
- `source`/`descriptor`/`data` roles and hashes。
- baseline/Savgol 与旧 `PreprocessingSession` 逐值对比。
- 新 backend import graph 中无 `epr_workflow`。
- 原 EPR 298 passed / 1 skipped 保持不变。

## 5. 迁移完成状态

M7 完成后，`src/spectralab/` 中不存在任何 `epr_workflow` import；表中
依赖均已由 SpectraLab EPR backend 的内部实现替代。仅测试代码仍导入旧实现作为
独立数值比较基线，不构成运行时依赖。
