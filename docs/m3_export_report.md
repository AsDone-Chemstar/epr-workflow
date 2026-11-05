# M3 报告：通用 Provenance 与 Spectrum1D 导出

- 状态：**M3 完成**
- 基线版本：EPR Workflow **v0.2.0**
- Git 基线：`327d5f6`
- 前序测试基线：M2 **364 passed, 1 skipped**
- M3 基线：**384 passed, 1 skipped**
- 日期：2026-11-02
- 范围：只实现技术无关的 `Spectrum1D` CSV/JSON 导出、provenance 文档和输出保护
- 现有生产行为：**未改变**
- 现有 EPR 代码、CLI、GUI、CSV/JSON schema：**未修改**
- Git：**未 commit、未 push**

---

## 1. 新增与修改文件

### 新增核心导出模块

- [src/spectralab/core/export/__init__.py](../src/spectralab/core/export/__init__.py)
- [src/spectralab/core/export/csv.py](../src/spectralab/core/export/csv.py)
- [src/spectralab/core/export/json.py](../src/spectralab/core/export/json.py)
- [src/spectralab/core/export/paths.py](../src/spectralab/core/export/paths.py)
- [src/spectralab/core/export/provenance.py](../src/spectralab/core/export/provenance.py)

### 修改现有中立代码

- [src/spectralab/core/errors.py](../src/spectralab/core/errors.py)：新增 `ExportError`、
  `ExportPathError`、`ExportSerializationError`、`OutputExistsError`
- [src/spectralab/core/__init__.py](../src/spectralab/core/__init__.py)：导出新 API

### 新增测试

- [tests/test_m3_export.py](../tests/test_m3_export.py)：16 个导出/来源/安全测试
- [tests/test_m3_architecture.py](../tests/test_m3_architecture.py)：4 个边界测试

合计 **20 个新测试**。

### 新增/更新文档

- [docs/spectrum1d_export_schema_v1.md](spectrum1d_export_schema_v1.md)：CSV/JSON v1 契约
- [docs/spectrum1d_export_v1.schema.json](spectrum1d_export_v1.schema.json)：
  机器可读 JSON Schema（draft 2020-12）
- 本报告
- [docs/architecture_proposal.md](architecture_proposal.md)：更新 M3 状态、实际范围和测试基线
- M2 报告页脚更新为已进入 M3

### 未修改

- `src/epr_workflow/` 下所有生产代码
- ASC/BES3T 解析器
- 现有 GUI、CLI、批处理
- 现有 EPR CSV/JSON 导出 schema
- 现有测试
- `requirements.txt`
- 原始数据和配置

---

## 2. Generic CSV API

模块：`spectralab.core.export.csv`

```python
CSV_COLUMNS = ("x", "y")
CSV_SCHEMA_ID = "spectralab.spectrum1d.csv_metadata"
CSV_SCHEMA_VERSION = 1
CSV_NUMERIC_SERIALIZATION = "python-repr-shortest-roundtrip-float64"

def render_spectrum_csv(spectrum: Spectrum1D) -> str: ...
def build_csv_metadata_document(spectrum: Spectrum1D) -> dict: ...
def render_csv_metadata_json(spectrum: Spectrum1D) -> str: ...
def export_spectrum_csv(
    spectrum: Spectrum1D,
    output_path: str | Path,
    *,
    overwrite: bool = False,
    metadata_path: str | Path | None = None,
) -> dict[str, Path]: ...
```

CSV 文件：

```csv
x,y
3280.0,400.088
3280.1,272.312
...
```

规则：

- 固定表头 `x,y`，不含 `field_G`、`intensity` 等技术列名；
- 行数等于 `point_count`；
- 严格保持原始点序；
- 递减轴不反转；
- 不排序、不插值、不平滑、不基线、不归一化；
- UTF-8 无 BOM，逗号分隔，LF 换行。

附属 metadata：

- 默认路径：与 CSV 同目录、同 stem 的 `_metadata.json`；
- 例如 `sample.csv` → `sample_metadata.json`；
- 记录轴 quantity/unit/name/direction、信号 semantics/unit/name、
  dataset/technique/source_format/point_count、metadata 和 provenance；
- 不包含 X/Y values；值只在 CSV 文件中；
- schema ID 为 `spectralab.spectrum1d.csv_metadata`，version `1`。

`export_spectrum_csv()` 返回：

```python
{
    "csv": Path(...),
    "metadata": Path(...),
}
```

---

## 3. Generic JSON API 与 Schema

模块：`spectralab.core.export.json`

```python
JSON_SCHEMA_ID = "spectralab.spectrum1d.export"
JSON_SCHEMA_VERSION = 1
JSON_NUMERIC_SERIALIZATION = "python-json-shortest-roundtrip-float64"

def build_export_document(spectrum: Spectrum1D) -> dict: ...
def render_document_json(document: dict) -> str: ...
def render_spectrum_json(spectrum: Spectrum1D) -> str: ...
def export_spectrum_json(
    spectrum: Spectrum1D,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path: ...
```

JSON 顶层：

```text
schema_id
schema_version
schema_status = "initial"
export
  format = "json"
  values_included = true
  point_order = "preserved"
  processing_applied = []
  numeric_serialization = "python-json-shortest-roundtrip-float64"
dataset
  dataset_id, technique, source_format, point_count
axis
  quantity, unit, name, direction, point_count,
  metadata_source, missing_reason, values
signal
  semantics, unit, name, point_count,
  metadata_source, missing_reason, values
metadata
  technique, title, instrument, acquisition, sample,
  technique_metadata, extra, unknown_fields, metadata_origin
provenance
  source_format, importer, imported_at_utc, source_files,
  canonical_sha256, sha256_definition, file_size_bytes,
  hash_definitions, warnings, assumptions, diagnostics,
  format_metadata, software_versions, metadata_origin
```

详细字段和类型见
[spectrum1d_export_schema_v1.md](spectrum1d_export_schema_v1.md)，
机器可读版本见
[spectrum1d_export_v1.schema.json](spectrum1d_export_v1.schema.json)。

序列化：

- `ensure_ascii=False`
- `allow_nan=False`
- `sort_keys=True`
- `indent=2`
- 末尾一个 LF
- 不写入当前导出时间戳

Schema 状态明确为 `initial`，不是永久稳定契约；未来不兼容变化必须提高
`schema_version`。

---

## 4. Provenance 字段与哈希定义

模块：`spectralab.core.export.provenance`

### 4.1 来源字段

- `source_format`
- `importer.id`、`importer.version`
- `imported_at_utc`：只有模型有时才输出；M1/M2 当前 EPR 导入为 `null`
- `source_files[].role`
- `source_files[].path`
- `source_files[].format_id`
- `source_files[].size_bytes`
- `source_files[].sha256`
- `canonical_sha256`
- `sha256_definition`
- `file_size_bytes`
- `hash_definitions`
- `warnings`
- `assumptions`
- `diagnostics`
- `format_metadata`
- `software_versions`
- `metadata_origin`

### 4.2 哈希定义

源文件哈希：

```text
source_files[].sha256 =
    SHA-256(exact source file bytes)
```

空字符串在模型中表示未记录；导出为 `null`。不是空文件的哈希。

规范数据集哈希：

```text
canonical_sha256 =
    importer-defined canonical dataset hash
```

准确构造必须读取 `sha256_definition`。对 BES3T，现有定义是：

```text
SHA-256(b"BES3T:" + descriptor_sha256 + b":" + data_sha256)
```

对单文件 ASC，规范哈希可能与源文件 SHA-256 相同；字段语义仍保持区分：
一个是源文件哈希，一个是 importer 定义的规范数据集哈希。

缺失的 `canonical_sha256` 或 `sha256_definition` 保持 `null`，不推测。

---

## 5. 数值序列化策略

### CSV

```text
float64 -> Python float -> repr(float)
```

`repr(float)` 是能精确往返同一 binary64 值的最短十进制表示。没有主动四舍五入、
截断或固定小数位。

### JSON

使用 Python 标准库 `json.dumps`，浮点数采用其最短可往返表示；
`allow_nan=False` 禁止输出 `NaN` / `Infinity`。

### 非有限值

- 模型本身拒绝非有限数组；
- 若模型数组被外部强行改写为非有限值，CSV/JSON 导出会在写文件前抛出
  `ExportSerializationError(code="nonfinite_value")`；
- metadata 中的非有限 float 同样拒绝；
- 不产生无效 JSON，也不产生部分输出文件。

### 精度验证

测试用 `struct.pack(">d", value)` 比较原值与导出后读回值，而不是只比较显示文本。
覆盖了 `1e-300`、`1e-200`、`0.1 + 0.2`、`-0.0`、最小次正规数、
最大有限 float64 等值。

---

## 6. 未知元数据处理

- 未知轴单位 → `null`
- 未知信号单位 → `null`
- 未知语义 → `"unknown"`
- 未知轴量 → `"unknown"`
- 未知名称/标题/导入时间 → `null`
- 未知 instrument/acquisition/sample → `{}`
- 未知源文件哈希/大小 → `null`
- 未记录的 canonical hash/definition → `null`
- `unknown_fields` 原样记录
- `missing_reason` 原样记录
- 不根据技术、文件名、数值或扩展名推断单位/语义

不支持的 metadata 值类型不会被 `str()` 隐式替代：导出会抛出
`ExportSerializationError(code="unsupported_metadata_value")`。

---

## 7. 输出覆盖与安全

模块：`spectralab.core.export.paths`

- 默认 `overwrite=False`；
- 已存在输出 → `OutputExistsError`，同时也是 `FileExistsError`；
- 覆盖必须显式传 `overwrite=True`；
- 导出目标不能等于任何 `provenance.source_files` 的路径，即使
  `overwrite=True`；
- 路径比较使用规范化后的绝对路径，覆盖符号链接解析结果；
- 目标为目录、空路径、非法类型 → `ExportPathError`；
- CSV 和 metadata 的路径在写入前都检查；
- CSV 和 metadata 都先完成序列化，再写文件；
- 单文件使用同目录临时文件 + `os.replace`，避免半写入内容；
- 序列化失败不会留下 CSV 或 sidecar。

限制：CSV 数据文件和 metadata sidecar 是两个独立文件。每个文件是原子写入，
但两者的写入不是跨文件事务；极端文件系统错误下，一个文件可能已经写入而另一个
失败。这一风险已记录，不影响“序列化失败时不产生输出”的保证。

---

## 8. 数值往返结果

真实 M0 数据：

- ASC：`BSA3T275.ASC` 1024 点；
- BES3T：`BSA3mal1h.DSC`/`.DTA` 1024 点；
- CSV 行数与点数一致；
- CSV `x`/`y` 读回后与 `Spectrum1D` 原值 bit-exact；
- JSON `axis.values`/`signal.values` 读回后 bit-exact；
- 首末值、M0 baseline 首末 X 与信号最值一致；
- 递减合成轴保持原顺序；
- 导出前后源文件 SHA-256 不变；
- 导出前后 `Spectrum1D` 数组不变且保持只读。

BES3T provenance 验证：

- `source_files` 的 `descriptor` 和 `data` 哈希保留；
- `canonical_sha256` 与两个源文件哈希不同；
- `sha256_definition` 保留 `BES3T:` 组合定义；
- M0 baseline 的规范哈希一致。

---

## 9. 架构边界结果

- `spectralab.core.export` 不导入 Qt、GUI、`epr_workflow`、`spectralab.app`
  或 `spectralab.techniques`；
- 导入 core export 不加载 EPR、Qt 或技术包；
- core export 模块不包含 `field_G`、`intensity` 或 `CW-EPR` 等 EPR 专用文本；
- core 导出图无循环导入；
- 未新增依赖；
- 未连接旧 GUI/CLI；
- 旧 `epr_workflow` 仍可独立导入和运行。

---

## 10. 测试结果

新增 **20 个 M3 测试**：

- `tests/test_m3_export.py`：16
- `tests/test_m3_architecture.py`：4

实际运行：

```text
完整测试集 pytest -v：
384 passed, 1 skipped
exit code 0

pytest -q -W error::UserWarning：
384 passed, 1 skipped
exit code 0

原 EPR 测试集（排除 M0/M1/M2/M3 测试）：
298 passed, 1 skipped
```

日志：

- `results/logs/pytest_m3_20261102_verbose.txt`
- `results/logs/pytest_m3_20261102_userwarning.txt`
- `results/logs/pytest_m3_20261102_original.txt`

---

## 11. 向后兼容

- 现有 `epr_workflow` 生产代码未修改；
- 现有 ASC/BES3T 解析器未修改；
- 现有 GUI、CLI、批处理和导出路径未修改；
- 现有 EPR CSV/JSON schema 未修改；
- 现有测试未修改；
- 原 EPR 测试 298 passed / 1 skipped 不变；
- 新导出器没有接入旧 GUI/CLI，删除新模块即可回滚；
- 无新增依赖，`requirements.txt` 未修改。

---

## 12. 剩余限制与风险

1. M3 只实现通用 CSV/JSON 和 provenance；没有实现 PNG 导出。
2. 没有创建 `techniques/epr/export_profile.py`，也没有适配旧 `processed_export.py`
   或 `plot_export.py`。这是按本次 M3 任务范围执行；架构提案中更广的 EPR 导出
   等价工作未进行。
3. 没有接入 CLI、GUI 或批处理，导出只能由代码显式调用。
4. 提供机器可读 JSON Schema（draft 2020-12），但未新增 `jsonschema`
   依赖；测试验证 schema 文件与输出顶层结构、版本常量和 required 字段一致，
   没有调用第三方完整 validator。
5. CSV 和 metadata 是双文件输出；每个文件原子写入，但不构成跨文件事务。
6. 输出保护只覆盖 `provenance.source_files` 中明确记录的源文件；核心不知道
   其他项目路径（例如 `data/raw`），这属于应用层策略。
7. 目前只支持原始 `Spectrum1D`，不包含处理结果、差谱、复杂信号、时域或二维谱。
8. `imported_at_utc` 在现有 EPR 导入链中不可得，因此保持 `null`。
9. metadata 中不支持的 Python 类型会显式失败，而不是转成字符串；
   调用方必须先把它转换为有明确定义的 JSON 类型。
10. JSON 文档包含完整 X/Y 数组，大谱会占用较多内存和磁盘。
11. `schema_version=1` 是初始契约，不承诺永久稳定；未来不兼容变化必须显式升版。

---

## 13. M3 完成清单

- [x] 通用 `x,y` CSV，不含 EPR 列名
- [x] CSV 原始点序、数值和递减轴保持
- [x] CSV 附属 metadata
- [x] 通用 JSON schema v1
- [x] JSON 严格拒绝 NaN/Infinity
- [x] 确定性序列化
- [x] 通用 provenance
- [x] 源文件角色/大小/SHA-256
- [x] 规范哈希与源文件哈希分离
- [x] importer ID/version
- [x] 缺失时间保持 `null`
- [x] metadata origin 保留
- [x] 未知单位/语义显式保留
- [x] 默认覆盖保护
- [x] 显式 `overwrite=True`
- [x] 源文件路径保护
- [x] 序列化失败无部分输出
- [x] 真实 ASC/BES3T 数值往返
- [x] 源文件和 `Spectrum1D` 不变
- [x] core 不导入 Qt/EPR/app/techniques
- [x] 无循环导入
- [x] 原 EPR 测试 298 passed / 1 skipped
- [x] 完整测试 384 passed / 1 skipped
- [x] `-W error::UserWarning` 通过
- [x] 未 commit、未 push

**M3 状态：完成。** M4 见 [M4 通用处理报告](m4_processing_report.md)，
M5 见 [M5 通用绘图报告](m5_generic_plotting_report.md)，M6 见
[M6 通用 CLI/Batch 报告](m6_cli_batch_report.md)，M7 见
[M7 EPR Backend Closure 报告](m7_epr_backend_closure_report.md)，M8 见
[M8 GUI Architecture 报告](m8_gui_architecture_report.md)；M9 尚未开始。
