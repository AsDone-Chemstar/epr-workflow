# M1 报告：Spectrum1D 数据模型与旧 EPR 适配器

- 状态：**M1 完成**
- 基线版本：EPR Workflow **v0.2.0**
- Git 基线：`327d5f6`
- M0 基线：**308 passed, 1 skipped**
- 日期：2026-11-02
- 范围：只实现中立 `Spectrum1D` 模型、显式轴/信号语义、旧 EPR 适配器和测试
- 生产行为：**未改变**
- 现有 EPR 代码、CLI、GUI、CSV/JSON schema：**未修改**

---

## 1. 包与目录

现有应用包保持 `epr_workflow`，未重命名、未移动。M1 新增一个独立的中立核心包：

```text
src/
├── epr_workflow/                 # 现有 EPR 应用，保持原样
└── spectralab/
    └── core/
        ├── __init__.py
        ├── errors.py
        ├── legacy_adapter.py     # 过渡性 EPR 兼容桥（无 EPR import）
        └── model/
            ├── __init__.py
            ├── axis.py
            ├── metadata.py
            ├── provenance.py
            ├── signal.py
            ├── spectrum1d.py
            └── values.py
```

`epr_workflow` 仍是当前正式应用包。`spectralab.core` 是新增的中立核心命名空间，
不是对现有包的改名；后续里程碑再逐步接入技术模块。

---

## 2. Spectrum1D API 与字段定义

### 2.1 Axis1D

`spectralab.core.model.axis.Axis1D`：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `values` | `numpy.ndarray` | 原始 X 值；复制为 float64 后只读 |
| `quantity` | `AxisQuantity` | 物理量：`magnetic_field`、`wavenumber`、`wavelength`、`frequency`、`time`、`index`、`unknown` |
| `unit` | `str \| None` | 单位；`None` 明确表示未知/未记录 |
| `name` | `str \| None` | 轴名称；`None` 表示未记录 |
| `direction` | `increasing` / `decreasing` / `unknown` | 描述性方向；不排序、不反转 |
| `metadata_source` | `str` | 轴值/方向的来源说明 |
| `missing_reason` | `str \| None` | 缺失原因的可选说明 |

属性：`point_count`、`is_known_direction`。

方向策略：

- 严格递增 → `increasing`；
- 严格递减 → `decreasing`；
- 重复值或非单调 → `unknown`；
- 无法推断为严格单调时，默认构造失败；必须显式传
  `direction="unknown"`，模型才会保留原始顺序；
- 显式 `unknown` 不会被自动覆盖为 increasing/decreasing；
- 不排序、不去重、不插值、不反转。

### 2.2 Signal1D

`spectralab.core.model.signal.Signal1D`：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `values` | `numpy.ndarray` | 原始 Y 值；复制为 float64 后只读 |
| `semantics` | `SignalSemantics` | `intensity`、`absorbance`、`transmittance`、`first_derivative`、`unknown` |
| `unit` | `str \| None` | Y 单位；`None` 明确表示未知/未记录 |
| `name` | `str \| None` | 信号名称 |
| `metadata_source` | `str` | 信号来源说明 |
| `missing_reason` | `str \| None` | 缺失原因 |

属性：`point_count`、`unit_is_known`、`semantics_is_known`。

模型不根据数值、轴单位或技术名称推断信号语义。EPR 适配器保留现有应用的
不确定性，使用 `semantics="unknown"`，因为 v0.2.0 不区分吸收谱/一阶导数谱。

### 2.3 SpectrumMetadata

`spectralab.core.model.metadata.SpectrumMetadata`：

- `technique`：技术标识，例如 `"epr"`；
- `title`：`str | None`；
- `instrument`、`acquisition`、`sample`：元数据映射；
- `technique_metadata`：技术专用元数据扩展点（FTIR 的采集模式/ATR 状态等未来放在这里）；
- `extra`：其他未分类元数据；
- `unknown_fields`：显式列出未知字段；
- `metadata_origin`：字段来源说明。

映射使用浅层 `MappingProxyType`，防止意外顶层写入；嵌套值不深度冻结。

### 2.4 SourceFile / Provenance

`SourceFile`：

- `role`：`source`、`descriptor`、`data` 等；
- `path`：`pathlib.Path`；
- `sha256`：源文件哈希；空字符串表示未记录；
- `size_bytes`：`int | None`；
- `format_id`：格式标识，例如 `ASC`、`BES3T`。

`Provenance`：

- `source_files`：`SourceFile` 元组；
- `canonical_sha256` 与 `sha256_definition`；
- `file_size_bytes`；
- `warnings`、`assumptions`；
- `format_metadata`、`diagnostics`、`software_versions`；
- `importer_id`、`importer_version`、`imported_at_utc`。

缺失值使用 `None`/空集合，不填充默认单位、默认哈希或伪造时间。

### 2.5 Spectrum1D

`spectralab.core.model.spectrum1d.Spectrum1D`：

| 字段 | 含义 |
| --- | --- |
| `dataset_id` | 数据集标识符，不是科学测量值 |
| `axis` | `Axis1D` |
| `raw_signal` | `Signal1D` |
| `metadata` | `SpectrumMetadata` |
| `provenance` | `Provenance`（可选，默认空） |

属性：`point_count`、`x_values`、`y_values`、`technique`、`source_format`。

`Spectrum1D` 只表示**导入原始状态**；M1 不引入 processing 对象，也不在模型内
执行基线、平滑、归一化或插值。

---

## 3. 不可变性实现

- `Axis1D.values` 和 `Signal1D.values` 在构造时复制为 `float64`；
- 调用 `setflags(write=False)`；
- 输入数组后来被修改不会影响模型；
- dataclass 为 frozen，字段不能重新绑定；
- 元数据/来源映射使用浅层 `MappingProxyType`，顶层键值不可写；
- 嵌套映射不深度冻结；来源元数据可能包含嵌套字典，M1 不做深度复制。

**限制：** read-only 是防误写，不是安全边界。拥有数组引用的调用者若主动调用
`setflags(write=True)`，仍可绕过；M1 不提供密码学或进程级不可变性。

---

## 4. 验证策略

### Axis1D

- 必须是一维、实数值、至少 2 点；
- 拒绝非有限值；
- 拒绝复数；
- `quantity` 必须是允许值之一；
- `unit` 为 `None` 或非空、无首尾空白字符串；
- `name` 为 `None` 或非空、无首尾空白字符串；
- `direction` 必须是允许值，并与实际值一致或显式 `unknown`；
- 重复/非单调轴默认拒绝；显式 `direction="unknown"` 才接受，且不排序、不改值。

### Signal1D

- 必须是一维、实数值、至少 2 点；
- 拒绝非有限值、复数；
- `semantics` 必须是允许值之一；
- `unit` 规则同 Axis；
- 不推断语义。

### Spectrum1D

- `dataset_id` 非空；
- `axis`/`raw_signal` 类型正确；
- 轴与信号点数必须一致；
- `metadata`/`provenance` 类型正确。

---

## 5. 旧 EPR 适配器映射

模块：`spectralab.core.legacy_adapter`

入口：

- `spectrum1d_from_import_result(result)`
- `to_spectrum1d(result)`（别名）
- `adapt_import_result(result)`（别名）
- `LegacyEprAdapter().to_spectrum1d(result)`

适配器接受现有 `epr_workflow.plot_asc.ImportResult`，使用鸭子类型，
**不导入 EPR 模块**。它是过渡性桥接；M7 可以把它移动到 `techniques/epr`。

| 旧字段/来源 | Spectrum1D 字段 |
| --- | --- |
| `ImportResult.data["field_G"]` | `axis.values` |
| `ImportResult.data["intensity"]` | `raw_signal.values` |
| `ImportResult.field_order` | `axis.direction`（映射 increasing/decreasing；其他 → unknown） |
| 旧 EPR 语义 | `axis.quantity="magnetic_field"` |
| 旧 EPR 场单位 | `axis.unit="G"` |
| 旧 EPR 信号名 | `signal.name="Intensity"`（BES3T 的 `IRNAM` 会保留在技术元数据） |
| 旧 EPR 强度单位 | `signal.unit=None`（除非 BES3T `IRUNI` 非空） |
| 旧 EPR 语义 | `signal.semantics="unknown"` |
| `ImportResult.source_format` | `provenance.format_metadata["source_format"]`、`Spectrum1D.source_format` |
| `ImportResult.source_files/source_hashes` | `provenance.source_files` |
| `ImportResult.sha256` | `provenance.canonical_sha256` |
| `ImportResult.file_size_bytes` | `provenance.file_size_bytes` |
| `ImportResult.warnings/format_assumptions` | `provenance.warnings/assumptions` |
| `ImportResult` 计数/诊断 | `provenance.diagnostics` |
| 无法获得的仪器/采集/样品/标题 | 空映射/`None` + `metadata.unknown_fields` |

方向映射：

```text
"strictly increasing" -> "increasing"
"strictly decreasing" -> "decreasing"
其他（unknown/non-monotonic） -> "unknown"
```

适配器是单向的；M1 不实现 Spectrum1D → ImportResult 反向转换。

---

## 6. 数值等价验证

新增测试使用 `tests/fixtures/m0_baseline.json` 对真实 ASC/BES3T 样本逐项比较：

- `Spectrum1D.point_count`；
- `x_values`/`y_values` 与 `ImportResult.data` 逐值相等；
- 轴首末值、强度首末值、最小/最大、首末 5 点；
- `axis.direction`；
- `axis.unit="G"`、`axis.quantity="magnetic_field"`；
- `signal.semantics="unknown"`、`signal.unit=None`；
- `source_format`、`canonical_sha256`、`file_size_bytes`；
- `source_files` 角色与哈希；
- BES3T `format_metadata["axis"]`、`binary`；
- 转换前后 `ImportResult` 数组和源文件 SHA-256 不变。

真实 ASC/BES3T 文件缺失时测试跳过；本机实际执行并通过。

---

## 7. 架构边界

- `spectralab.core` 不导入 Qt/PySide6/PyQt；
- `spectralab.core` 不导入 `epr_workflow`、`spectralab.techniques` 或 GUI；
- 旧 `epr_workflow` 包保持可导入，仍不导入 Qt；
- 适配器没有运行时 EPR import；
- 适配器在 M1 暂放在 `core/legacy_adapter.py`，这是过渡性兼容桥，未来移到
  `techniques/epr`；它不违反当前“core 不 import 技术模块”的导入边界。
- 现有 M0 架构测试继续通过。

新增架构测试：`tests/test_m1_architecture.py`。

---

## 8. 测试结果

### 新增测试

- `tests/test_spectrum1d.py`：13 个模型测试
- `tests/test_legacy_epr_adapter.py`：8 个适配器测试
- `tests/test_m1_architecture.py`：3 个边界测试

合计 **24 个新测试**。

### 实际运行

M0 基线（排除 M1 新测试）：

```text
308 passed, 1 skipped
```

完整测试集：

```text
332 passed, 1 skipped
```

`-W error::UserWarning`：

```text
332 passed, 1 skipped
```

原 EPR 测试集（排除 M0/M1 测试）：

```text
298 passed, 1 skipped
```

结论：新增 24 个测试全部通过；原有 298 passed / 1 skipped 不变；M0 基线
308 passed / 1 skipped 不变。没有生产行为变化。

---

## 9. 已知限制与风险

1. `Spectrum1D` 目前只覆盖一维实值谱；不包含 `ProcessedSpectrum`、
   `ComplexSignal`、`TimeDomainSignal` 或 `Spectrum2D`。
2. 适配器中的场单位固定为 `G`，符合当前 v0.2.0 的 ASC/BES3T 导入；不代表
   未来所有技术都使用 G。
3. 适配器把 EPR 信号语义保留为 `unknown`，不声称吸收谱/一阶导数谱。
4. 仪器、采集、样品和标题在旧 ImportResult 中不可得，因此保持未知；没有虚构。
5. `Provenance.software_versions` 在适配器中为空，`imported_at_utc` 为 `None`；
   旧 ImportResult 没有这些字段。
6. 映射不可变性是浅层的；嵌套来源元数据仍应视为只读。
7. 重复/非单调轴默认拒绝，只有显式 `direction="unknown"` 才接受；这是文档化
   的 M1 策略，未来处理操作必须自行检查可处理性。
8. 适配器在 `core` 中是过渡性 EPR 兼容桥；它没有运行时 EPR import，但概念上
   仍是 EPR 专用映射，计划在 M7 移入 `techniques/epr`。
9. 没有实现反向转换，也没有把 Spectrum1D 接入 GUI/CLI/导出；M1 是兼容层，
   不是应用切换。

---

## 10. M1 完成清单

- [x] 独立 `Spectrum1D` 模型
- [x] `Axis1D` / `Signal1D` 显式语义和单位
- [x] `SpectrumMetadata` / `SourceFile` / `Provenance`
- [x] 只读数组与冻结映射
- [x] 方向推断与重复/非单调轴策略
- [x] 非有限值、复数、长度、单位、语义验证
- [x] 旧 EPR 单向适配器
- [x] ASC/BES3T 数值等价
- [x] 源文件/哈希/格式差异保留
- [x] 未知元数据显式保留
- [x] 核心不导入 Qt/EPR/techniques
- [x] 现有 EPR 测试保持 298 passed / 1 skipped
- [x] 完整测试 332 passed / 1 skipped
- [x] `-W error::UserWarning` 通过
- [x] 无生产代码、现有测试、CSV/JSON schema、GUI、CLI 修改
- [x] 无 commit、无 push

**M1 状态：完成。** M2 见
[M2 Importer 注册表报告](m2_importer_registry_report.md)，M3 见
[M3 通用导出报告](m3_export_report.md)，M4 见
[M4 通用处理报告](m4_processing_report.md)，M5 见
[M5 通用绘图报告](m5_generic_plotting_report.md)，M6 见
[M6 通用 CLI/Batch 报告](m6_cli_batch_report.md)，M7 见
[M7 EPR Backend Closure 报告](m7_epr_backend_closure_report.md)，M8 见
[M8 GUI Architecture 报告](m8_gui_architecture_report.md)；M9 尚未开始。
