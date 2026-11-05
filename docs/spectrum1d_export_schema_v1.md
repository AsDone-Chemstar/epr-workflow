# Spectrum1D 通用导出 Schema v1

- Schema ID（JSON）：`spectralab.spectrum1d.export`
- Schema version：`1`
- Schema status：`initial`
- CSV 附属元数据 Schema ID：`spectralab.spectrum1d.csv_metadata`
- CSV 附属元数据 Schema version：`1`
- 适用范围：仅一维实值 `Spectrum1D` 原始导入状态
- 状态：**初始版本，可能通过显式 schema 版本变化演进，不承诺永久稳定**
- 机器可读 JSON Schema：
  [spectrum1d_export_v1.schema.json](spectrum1d_export_v1.schema.json)

本 schema 不由任何技术模块定义。EPR、FTIR 等只能提供 `Spectrum1D`，
不能在通用字段中引入 `field_G`、`intensity` 等技术专用列名。

---

## 1. Generic CSV v1

### 1.1 数据文件

- 编码：UTF-8，无 BOM
- 分隔符：逗号
- 行结束：LF（`\n`）
- 表头：`x,y`
- 行数：表头 + `point_count`
- 行序：严格保持 `Spectrum1D.axis.values` / `raw_signal.values` 的原始顺序
- 不做排序、反转、插值、归一化、平滑或基线处理
- 递减轴保持递减顺序

数值策略：

```text
每个 float64 值先转换到 Python float，
再使用 repr(float) 输出最短的、可精确往返的十进制表示。
```

这不会主动四舍五入或截断；CSV 读回后应与原 float64 位模式一致。

### 1.2 附属元数据 JSON

默认文件名：与 CSV 同目录、同 stem，后缀 `_metadata.json`。
例如 `sample.csv` → `sample_metadata.json`。

顶层字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_id` | string | 固定为 `spectralab.spectrum1d.csv_metadata` |
| `schema_version` | integer | 当前为 `1` |
| `schema_status` | string | `initial` |
| `export` | object | 导出格式和序列化策略 |
| `dataset` | object | 数据集 ID、技术、来源格式、点数 |
| `axis` | object | 轴语义和元数据；**不含 values** |
| `signal` | object | 信号语义和元数据；**不含 values** |
| `metadata` | object | title、instrument、acquisition、sample、技术元数据、extra、未知字段、来源 |
| `provenance` | object | 来源文件、哈希、导入器、警告、假设、诊断 |
| `csv` | object | CSV 列、分隔符、编码、行结束和数值策略 |

`export.values_included` 为 `false`；数据值只存在于 CSV 文件。

---

## 2. Generic JSON v1

JSON 文档包含 CSV 元数据的全部字段，并额外包含：

- `axis.values`
- `signal.values`

顶层字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_id` | string | `spectralab.spectrum1d.export` |
| `schema_version` | integer | `1` |
| `schema_status` | string | `initial` |
| `export` | object | `format="json"`、values 是否包含、点序、处理列表、数值策略 |
| `dataset` | object | `dataset_id`、`technique`、`source_format`、`point_count` |
| `axis` | object | 轴语义、元数据、`values` |
| `signal` | object | 信号语义、元数据、`values` |
| `metadata` | object | 描述性元数据和未知字段 |
| `provenance` | object | 来源、哈希、导入器、警告、诊断 |

`export.processing_applied` 在 M3 中始终是空数组。它明确表示没有应用处理。

---

## 3. `axis` 字段

| 字段 | 类型 | 未知值 |
| --- | --- | --- |
| `quantity` | string | `unknown` |
| `unit` | string 或 null | `null` 表示未记录，不推断 |
| `name` | string 或 null | `null` |
| `direction` | `increasing` / `decreasing` / `unknown` | `unknown` |
| `point_count` | integer | 不适用 |
| `metadata_source` | string | 原样保留 |
| `missing_reason` | string 或 null | `null` |
| `values` | number array | JSON 输出包含；CSV sidecar 不包含 |

方向是描述性字段，不会触发排序或反转。

## 4. `signal` 字段

| 字段 | 类型 | 未知值 |
| --- | --- | --- |
| `semantics` | string | `unknown` |
| `unit` | string 或 null | `null` 表示未记录，不推断 |
| `name` | string 或 null | `null` |
| `point_count` | integer | 不适用 |
| `metadata_source` | string | 原样保留 |
| `missing_reason` | string 或 null | `null` |
| `values` | number array | JSON 输出包含；CSV sidecar 不包含 |

不得根据技术名称或数值推断吸光度、透过率或一阶导数。

---

## 5. `metadata` 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `technique` | string | 技术 ID |
| `title` | string 或 null | 未知为 null |
| `instrument` | object | 未记录时为空对象 |
| `acquisition` | object | 未记录时为空对象 |
| `sample` | object | 未记录时为空对象 |
| `technique_metadata` | object | 技术专用扩展点；核心不解释 |
| `extra` | object | 其他元数据 |
| `unknown_fields` | string array | 显式未知字段列表 |
| `metadata_origin` | object | 字段来源 |

映射的值会递归转换为 JSON 类型。不支持的值类型不会被 `str()` 静默替代，
而是抛出 `ExportSerializationError`。

---

## 6. `provenance` 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `source_format` | string 或 null | 导入格式 ID |
| `importer.id` | string | 导入器 ID |
| `importer.version` | string | 导入器版本 |
| `imported_at_utc` | string 或 null | 只有原模型有时才输出 |
| `source_files` | array | 源文件记录 |
| `source_files[].role` | string | `source` / `descriptor` / `data` / ... |
| `source_files[].path` | string | 源文件路径 |
| `source_files[].format_id` | string | 源文件格式 |
| `source_files[].size_bytes` | integer 或 null | 未知为 null |
| `source_files[].sha256` | string 或 null | 未知为 null |
| `canonical_sha256` | string 或 null | importer 定义的规范数据集哈希 |
| `sha256_definition` | string 或 null | 规范哈希的准确构造定义 |
| `file_size_bytes` | integer 或 null | 旧导入结果记录的总体大小 |
| `hash_definitions` | object | 导出中哈希字段的说明 |
| `warnings` | string array | 导入警告 |
| `assumptions` | string array | 显式假设 |
| `diagnostics` | object | 导入诊断 |
| `format_metadata` | object | 格式元数据 |
| `software_versions` | object | 已知软件版本 |
| `metadata_origin` | object | 元数据来源 |

### 哈希定义

- `source_files[].sha256`
  - 定义：对应源文件精确字节的 SHA-256。
  - 空字符串/`null` 表示未记录，不表示空文件。
- `canonical_sha256`
  - 定义：importer 定义的规范数据集哈希。
  - 单文件 ASC 可能与源文件 SHA-256 相同；这仍是规范数据集哈希，不是新的源文件哈希。
  - BES3T 的现有定义是：
    `SHA-256(b"BES3T:" + descriptor_sha256 + b":" + data_sha256)`。
  - 准确构造必须从 `sha256_definition` 读取；缺失时保持 `null`，不推测。

---

## 7. 数值和 JSON 常量策略

- JSON 使用 Python 标准库 `json.dumps`：
  - `ensure_ascii=False`
  - `allow_nan=False`
  - `sort_keys=True`
  - `indent=2`
- 不允许输出 `NaN`、`Infinity` 或 `-Infinity`。
- 非有限模型值会在写出前抛出 `ExportSerializationError`。
- 元数据中的非有限 float 同样拒绝。
- JSON 浮点数使用 Python 的最短可往返十进制表示。
- CSV 浮点数使用 `repr(float)` 的最短可往返十进制表示。
- 输出末尾统一带一个 LF。

确定性：同一 `Spectrum1D` 在相同字段下重复渲染应产生相同字节内容；导出过程
不写入当前时间戳。

---

## 8. 未知信息

- 缺失单位：`null`
- 缺失名称/标题/时间：`null`
- 缺失采集/仪器/样品：空对象
- 未知语义/轴量：字符串 `"unknown"`
- 未知字段：显式 `unknown_fields`
- 缺失哈希/大小：`null`
- 不虚构仪器、样品、采集参数、单位、时间或哈希

---

## 9. 版本演进

`1` 是初始导出 schema。未来若发生不兼容变化，必须增加 `schema_version`
并在文档中记录迁移；不要静默改变字段含义或删除科学字段。

`initial` 状态表示该 schema 尚未承诺永久稳定。

---

## 10. 输出安全

- 默认拒绝覆盖已存在文件。
- 覆盖必须显式传入 `overwrite=True`。
- 导出目标不能是任何 `provenance.source_files` 中的源文件，即使
  `overwrite=True`。
- 两种输出都先完成全部序列化，再写文件；序列化失败不会留下部分文件。
- 单个文件使用同目录临时文件 + `os.replace`，避免出现半写入内容。
- 不修改 `Spectrum1D`，不修改源文件。
