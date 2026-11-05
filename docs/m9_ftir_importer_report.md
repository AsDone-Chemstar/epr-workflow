# M9 报告：FTIR CSV/TXT Importer 与 Batch Core

- 状态：**M9 完成（含真实样本验收）**
- 基线版本：EPR Workflow **v0.2.0**
- Git 基线：`327d5f6`
- 前序测试基线：M8 **523 passed, 1 skipped**
- M9 基线：**592 passed, 1 skipped**
- 日期：2026-11-03
- 范围：generic FTIR CSV/TXT/DPT 单谱导入、显式映射与语义元数据、batch/CLI 接入
- 旧 EPR 应用：**未修改，仍独立可用**
- Git：**未 commit、未 push、未创建 tag**
- M9 范围外：M10 及以后；M10 与 M11 已另行完成，M12–M17 仍未实现

---

## 1. 实现前检查

检查了：

- [architecture_proposal.md](architecture_proposal.md) 的 M9 设计和 FTIR 约束；
- M1 `Spectrum1D`/`Axis1D`/`Signal1D`/`SpectrumMetadata`/`Provenance`；
- M2 `ImportRequest`、`Importer` 协议和 `ImporterRegistry`；
- M3 raw CSV/JSON 导出与 provenance；
- M6 generic CLI/batch 的发现、碰撞、覆盖和源文件保护规则；
- M7/M8 架构边界和测试组织方式；
- `Test data/`、`data/raw/`、`tests/fixtures/` 及仓库历史。

### 真实样本检查

任务指定的真实 ATR-FTIR 样本：

```text
S-BSAPEG-10.0.dpt
```

首次实现时该文件不在检出中，M9 报告将其记录为阻塞项。用户随后上传到项目
根目录：

```text
D:\EPR workflow\S-BSAPEG-10.0.dpt
```

只读检查结果：

- 89617 bytes；
- 4350 行；
- UTF-8，无 BOM；
- CRLF；
- 每行两列，Tab 分隔；
- 无表头；
- 第一行 `3998.83701\t-0.00065`；
- 最后一行 `899.39981\t-0.00507`；
- SHA-256
  `501fe570b175d8f2a089c21c17f469b1a087d654040f72986c5ba9fe9bffe761`。

测试和端到端导入均未修改该文件；导入前后 SHA-256 相同。

---

## 2. 最终 importer 架构

```text
src/spectralab/techniques/ftir/
├── __init__.py
├── technique.py                 # 显式注册
└── importers/
    ├── __init__.py
    ├── _generic.py              # 严格共享文本解析器
    ├── generic_csv.py           # GenericCSVImporter
    ├── generic_txt.py           # GenericTXTImporter (.txt/.dpt)
    ├── mapping.py               # ColumnMapping / FTIRImportOptions
    └── semantics.py             # FTIR 元数据词汇与 FTIRMetadata
```

依赖方向：

```text
app ──► techniques/ftir ──► core
```

- `core` 不导入 FTIR、EPR、Qt 或 app；
- FTIR backend 不导入 Qt、app、EPR 或 `epr_workflow`；
- M9 FTIR backend 不包含 GUI；M10 在应用层加入 FTIR 面板；
- 没有 FTIR processing 模块（M10+）；
- 没有自动插件发现或隐式注册。

新增 importer ID：

| ID | 类 | 后缀 | format_id |
| --- | --- | --- | --- |
| `ftir.csv` | `GenericCSVImporter` | `.csv` | `FTIR_CSV` |
| `ftir.txt` | `GenericTXTImporter` | `.txt`, `.dpt` | `FTIR_TXT` |

`build_importer_registry()` 现在按显式顺序注册：

```text
epr.xepr_asc, epr.bes3t, ftir.csv, ftir.txt
```

这是 M9 为 batch/CLI 可用性所做的有意集成；generic GUI 仍只有 EPR 面板。

---

## 3. 支持的格式与解析选项

### 3.1 文件类型

- CSV
- TXT
- DPT 风格文本
- 两列或多列单谱文本（多列必须显式映射 X/Y）
- Tab、逗号、分号、空白或单字符自定义分隔符

一个文件在 M9 中只产生一个 `Spectrum1D`。`ImportedDataset` 本身仍支持未来
多谱结果，但 M9 不拆分宽表。

### 3.2 显式选项

`ColumnMapping`：

```python
ColumnMapping(
    x=0, y=1,
    x_name=None, x_unit=None, x_quantity=None,
    y_name=None, y_unit=None, y_semantics="unknown",
    header=False,
    delimiter=None,
    comment=None,
    decimal=".",
    encoding="utf-8-sig",
    skip_rows=0,
)
```

支持：

- X/Y 零基列索引或表头列名；
- `header=True/False`；
- 分隔符：`comma`、`tab`、`semicolon`、`whitespace`、`auto` 或单字符；
- 小数点：`.` 或 `,`；
- 注释标记（可多个）；
- 文本编码；
- 显式跳过文件开头物理行；
- 可选 X/Y 名称与单位；
- 信号语义；
- 采集模式；
- ATR 校正状态；
- 可选仪器厂商/型号。

`FTIRImportOptions`：

```python
FTIRImportOptions(
    mapping=ColumnMapping(...),
    acquisition_mode="Unknown",
    atr_correction_status="unknown",
    instrument_vendor=None,
    instrument_model=None,
)
```

选项可通过以下形式传入：

```python
registry.read(path, options={"ftir": FTIRImportOptions(...)})
registry.read(path, options={"ftir": {"x": 1, "y": 2, "header": True}})
registry.read(path, options={"x": 1, "y": 2, "header": True})
registry.read(path, options={"mapping": ColumnMapping(...)})
```

未知选项会以 `ftir_unsupported_option` 明确失败，不会被静默忽略。

### 3.3 默认值

| 项目 | 默认 | 说明 |
| --- | --- | --- |
| CSV 分隔符 | `,` | 由后缀决定 |
| TXT/DPT 分隔符 | 空白 | 同时覆盖 Tab |
| 小数点 | `.` | 逗号需显式 |
| header | `False` | 不自动检测 |
| comment | 无 | 需显式 |
| encoding | `utf-8-sig` | 需其他编码时显式 |
| skip_rows | `0` | 需显式 |
| X/Y 列 | 仅两列时 0/1 | 多于两列必须显式 |
| X quantity | `unknown` | 除非显式 quantity 或 `cm^-1` unit |
| X unit | `None` | 仅接受显式 `cm^-1` |
| Y semantics | `unknown` | 绝不推断 |
| Y unit | `None` | 绝不推断 |
| acquisition mode | `Unknown` | 绝不从文件名/后缀/数值推断 |
| ATR status | `unknown` | 不假设已校正 |

两列默认映射会写入 `assumptions`，并在 `format_metadata` 标记
`defaulted_two_column_mapping=true`。

---

## 4. 元数据映射

### Axis

- `Axis1D.values`：原始行序、原始 X 列；
- `quantity`：显式 `wavenumber`，或由显式 `x_unit="cm^-1"` 确认；否则
  `unknown`；
- `unit`：仅显式 `cm^-1` 或 `None`；
- `name`：仅显式提供；
- `direction`：从导入值推断的 `increasing`/`decreasing`；
- 不允许重复或非单调 X；不会排序、反转、插值或删除点。

### Signal

- `Signal1D.semantics`：`absorbance`、`transmittance` 或 `unknown`；
- `unit`：仅显式提供；
- `name`：仅显式提供；
- 不从数值范围、列名、文件名或采集模式推断语义。

### Acquisition / ATR

写入 `SpectrumMetadata.acquisition` 和 `technique_metadata`：

```json
{
  "mode": "ATR",
  "atr_correction_status": "not_applied"
}
```

采集模式规范值为 `ATR`、`Transmission`、`Unknown`；ATR 状态为
`applied`、`not_applied`、`not_applicable`、`unknown`。小写输入会被规范化，
未知值不会被补全。采集模式与信号语义相互独立。

### Instrument / sample

- `instrument.vendor`、`instrument.model`：可选，仅来自显式用户输入；
- `sample`：M9 不解析，保持为空并列入 `unknown_fields`；
- `title`：M9 不推断，保持 `None`。

### 未知字段

`unknown_fields` 会显式记录，例如：

- `axis.quantity`
- `axis.unit`
- `axis.name`
- `signal.semantics`
- `signal.unit`
- `signal.name`
- `acquisition_mode`
- `atr_correction_status`
- `instrument.vendor`
- `instrument.model`
- `title`
- `sample`

### Provenance

每个成功谱记录：

- 完整源文件 SHA-256；
- 文件大小；
- importer ID/version；
- 分隔符、小数点、编码、header、comment、skip rows；
- 解析后的 X/Y 列索引；
- 表头字段；
- 数据行数、空行/注释行计数；
- 完整 resolved import options；
- 默认两列映射假设；
- 未处理声明。

源文件在读取前后哈希不变；读取期间若文件变化，会以
`source_changed_during_import` 失败。

---

## 5. Axis 与错误处理

### 轴

- 原始点序原样保留；
- 递增和递减轴都接受；
- 重复 X → `axis_not_monotonic`；
- 非单调 X → `axis_not_monotonic`；
- 不排序、不反转、不删除重复点、不插值、不外推。

### 解析错误

稳定的 `ImportFailure.code` 包括：

- `ftir_empty_file`
- `ftir_no_data`
- `ftir_invalid_number`
- `ftir_nonfinite`
- `ftir_missing_value`
- `ftir_missing_column`
- `ftir_inconsistent_columns`
- `ftir_insufficient_columns`
- `ftir_insufficient_points`
- `ftir_column_mapping_required`
- `ftir_same_column`
- `ftir_unknown_column_name`
- `ftir_duplicate_column_name`
- `ftir_header_required`
- `ftir_invalid_encoding`
- `ftir_decode_error`
- `ftir_invalid_delimiter`
- `ftir_delimiter_decimal_conflict`
- `ftir_unsupported_axis_unit`
- `ftir_unsupported_signal_semantics`
- `ftir_unsupported_acquisition_mode`
- `ftir_unsupported_atr_status`
- `ftir_unsupported_option`
- `axis_not_monotonic`

错误包含行号、列号、轴或选项 context；没有静默修复或部分输出。

---

## 6. Batch 与 CLI

### Batch

`run_batch()` 新增可选 `options` 参数：

```python
run_batch(inputs, output_dir, options={"ftir": FTIRImportOptions(...)})
```

行为：

- 多个独立文件按显式输入顺序处理；
- 目录发现使用注册 importer 声明的后缀：
  - `.csv`, `.txt`, `.dpt`, `.asc`, `.dsc`
- 单文件失败不阻止其他文件；
- 保留已有输出碰撞检测、覆盖保护和源文件保护；
- 每个成功记录包含 source path、size、SHA-256、importer、warnings、
  metadata、resolved import options；
- batch summary 新增 `import_options` 和每文件 metadata；
- 不重命名、不静默覆盖。

选项应用到此 batch 中每个被选 importer。EPR importer 仍拒绝非空 options，
因此对 EPR 文件传入 FTIR 选项会明确失败，而不是忽略。

### CLI

新增显式 FTIR 参数：

```text
--x-column / --x-col
--y-column / --y-col
--header
--delimiter / --separator
--decimal / --decimal-separator
--comment / --comments
--encoding
--skip-rows
--x-quantity / --axis-quantity
--x-unit / --axis-unit
--x-name / --axis-name
--y-semantics / --signal-semantics
--y-unit / --signal-unit
--y-name / --signal-name
--acquisition-mode
--atr-correction / --atr-correction-status
--instrument-vendor
--instrument-model
```

这些参数只在至少一个被提供时构造 FTIR options。无效 option 返回 CLI exit code
`2`，不创建 output 目录。

现有 M6 CLI 参数、输出结构、碰撞和覆盖行为保持不变；新增 summary 字段为
向后兼容的增量。

---

## 7. 真实样本与测试结果

### 真实样本

真实样本已上传到项目根目录，并通过专项测试：

```text
tests/test_ftir_importer.py::test_real_atr_ftir_sample_if_present PASSED
```

验证结果：

- 4350 点；
- `format_id=FTIR_TXT`，`technique=ftir`；
- X 严格递减：`3998.83701 → 899.39981`；
- Y：`-0.00065 → -0.00507`；
- 全部 X/Y 有限；
- 显式 `wavenumber`/`cm^-1`；
- 显式 Absorbance；
- 显式 ATR；
- ATR 校正状态保持 `unknown`；
- 源 SHA-256 与 provenance 一致；
- importer `ftir.txt` version `1.0.0`；
- 无 warnings；
- 两列默认映射被记录为 assumption；
- 未执行任何处理、ATR 校正、排序、反转或插值。

端到端 CLI 验证输出到：

```text
results/m9_ftir_real_sample_20261103/
```

结果：

- `1 succeeded, 0 failed, status=success`；
- CSV 4350 行，首行 `3998.83701,-0.00065`，末行 `899.39981,-0.00507`；
- JSON/summary 的源 SHA-256 与源文件一致；
- `processing_applied=[]`；
- 导入前后源文件哈希相同。

### DPT 风格覆盖

除真实样本外，另使用合成 DPT 风格数据验证：

- 4350 行；
- Tab 分隔；
- 无 header；
- 两列；
- 递减 X；
- 数值逐值精确读回；
- 不排序、不反转。

合成数据在测试中生成，不写入 `data/raw/`，也不冒充真实测量。

### 新增测试

- [tests/test_ftir_importer.py](../tests/test_ftir_importer.py)：50 passed
- [tests/test_ftir_batch.py](../tests/test_ftir_batch.py)：12 passed
- [tests/test_m9_architecture.py](../tests/test_m9_architecture.py)：7 passed

合计 **69 个新测试，全部通过**。

覆盖：

1. 逗号 CSV
2. Tab TXT/DPT
3. 小数逗号
4. 有/无表头
5. 显式 X/Y 索引与列名
6. 递增与递减轴
7. 重复/非单调轴
8. 非法数值
9. NaN/Infinity
10. 缺列/行长度不一致
11. unknown 元数据保留
12. Absorbance/Transmittance
13. ATR/Transmission/Unknown
14. ATR 校正状态
15. DPT 风格 4350 点
16. 多文件 batch
17. 部分失败隔离
18. 输出碰撞/覆盖保护
19. 源文件不可变
20. 架构与依赖约束

### 实际运行

```text
真实样本专项测试：
1 passed
exit code 0

完整测试集 pytest -v：
592 passed, 1 skipped
exit code 0

pytest -q -W error::UserWarning：
592 passed, 1 skipped
exit code 0

原 EPR 测试集（HEAD 中已跟踪的 14 个测试文件）：
298 passed, 1 skipped
exit code 0
```

日志：

- `results/logs/pytest_m9_20261103_real_sample.txt`
- `results/logs/pytest_m9_20261103_verbose_real_sample.txt`
- `results/logs/pytest_m9_20261103_userwarning_real_sample.txt`
- `results/logs/pytest_m9_20261103_original_real_sample.txt`

基线比较：

- M8：523 passed, 1 skipped
- M9（真实样本前）：591 passed, 2 skipped
- M9（真实样本后）：**592 passed, 1 skipped**
- 新增 69 passed
- 原 EPR 子集保持 298 passed, 1 skipped

剩余 skip 是原 EPR 的 Windows `.DTA` 大小写歧义测试，与 M9 无关。

---

## 8. 新增与修改文件

### 新增 FTIR backend

- [src/spectralab/techniques/ftir/__init__.py](../src/spectralab/techniques/ftir/__init__.py)
- [src/spectralab/techniques/ftir/technique.py](../src/spectralab/techniques/ftir/technique.py)
- [src/spectralab/techniques/ftir/importers/__init__.py](../src/spectralab/techniques/ftir/importers/__init__.py)
- [src/spectralab/techniques/ftir/importers/_generic.py](../src/spectralab/techniques/ftir/importers/_generic.py)
- [src/spectralab/techniques/ftir/importers/generic_csv.py](../src/spectralab/techniques/ftir/importers/generic_csv.py)
- [src/spectralab/techniques/ftir/importers/generic_txt.py](../src/spectralab/techniques/ftir/importers/generic_txt.py)
- [src/spectralab/techniques/ftir/importers/mapping.py](../src/spectralab/techniques/ftir/importers/mapping.py)
- [src/spectralab/techniques/ftir/importers/semantics.py](../src/spectralab/techniques/ftir/importers/semantics.py)

### 新增测试

- [tests/test_ftir_importer.py](../tests/test_ftir_importer.py)
- [tests/test_ftir_batch.py](../tests/test_ftir_batch.py)
- [tests/test_m9_architecture.py](../tests/test_m9_architecture.py)

### 修改

- [src/spectralab/app/registry.py](../src/spectralab/app/registry.py)：显式注册 FTIR
- [src/spectralab/app/batch.py](../src/spectralab/app/batch.py)：传递 options，
  summary 记录 metadata/options
- [src/spectralab/app/cli.py](../src/spectralab/app/cli.py)：新增 FTIR 参数
- [tests/test_m2_architecture.py](../tests/test_m2_architecture.py)：注册表 ID
  期望更新；技术包规则改为允许自身导入、禁止 EPR↔FTIR 交叉导入
- [tests/test_epr_importers.py](../tests/test_epr_importers.py)：默认注册表 ID
  列表更新
- [docs/architecture_proposal.md](architecture_proposal.md)：M9 状态与结果
- 本报告

### 未修改

- `src/epr_workflow/` 全部生产代码
- 旧 EPR GUI、CLI、batch、preprocessing、Plot Editor、export
- M1–M8 公共模型/导出/处理/绘图 API 的实现
- M3 schema
- 原始实验数据、配置
- `requirements.txt`

---

## 9. 架构验证

- `src/spectralab/core` 不导入 FTIR、EPR、Qt、app 或 GUI；
- FTIR backend 不导入 Qt、app、GUI、EPR 或 `epr_workflow`；
- 导入整个 FTIR 包不会加载 Qt、EPR 或 `epr_workflow`；
- `src/spectralab` 中不存在任何 `epr_workflow` 运行时 import；
- `build_importer_registry()` 显式注册 EPR 与 FTIR，不加载 Qt；
- FTIR importer 图无循环；
- FTIR 包没有 GUI 或 processing 子模块；
- 旧 `epr_workflow` 与 M6 CLI 仍可导入；
- EPR parser/preprocessing 未修改。

---

## 10. 向后兼容

- 旧 EPR 测试 298 passed, 1 skipped；
- 旧 EPR GUI/CLI/Plot Editor/preprocessing/export 未修改；
- M6 CLI 原有参数与行为保持；新增参数和 summary 字段为增量；
- `run_batch()` 原有调用不需要修改；新参数有默认 `None`；
- `ImporterRegistry`、`ImportRequest`、`ImportedDataset` 协议未修改；
- 删除 `techniques/ftir` 并从 `build_importer_registry()` 移除注册即可回滚；
- 无新增依赖。

---

## 11. 剩余技术债与限制

1. 默认注册表和 CLI 现在包含 FTIR；如果调用方假定注册表只有 EPR，需要更新
   其期望。
2. 自定义分隔符仅支持单字符；不支持多字符串分隔符。
3. `header` 是布尔值；不支持“表头在第 N 行”或复杂多级表头。
4. 不解析仪器厂商/型号、分辨率、扫描次数等文件内元数据；只能由用户显式
   提供厂商/型号。
5. 宽表不会拆分；显式映射一个 X/Y 后，其他列只记录 warning，不解释。
6. 非单调/重复 X 仍被严格拒绝；这符合现有 `Spectrum1D` 模型，但不支持含
   重复点的原始仪器导出。
7. `cm^-1` 是唯一接受的 X 单位；不做波数/波长/微米换算。
8. FTIR 选项应用于整个 batch；混合 EPR/FTIR batch 带 FTIR 选项时，EPR 文件
   会明确失败。
9. M9 本身没有 FTIR GUI 或处理；M10 已另行加入导入面板/对话框和原始谱显示，
   仍没有 ATR 校正、归一化、基线、峰检测、差谱或多谱比较。
10. 没有 vendor-specific 格式或从 `.dpt` 文件名/结构自动识别厂商。
11. 没有自动表头/分隔符检测；`delimiter=None` 仅选择已声明的后缀默认值。
12. 注释只按行首标记识别，不支持行内注释。
13. 文本解析不保留原始数值字符串，只保留 float64 值；原始文件哈希和完整
    源文件仍保留。

---

## 12. Git 状态

实现前后 HEAD 均为：

```text
327d5f633c701cb07c3279754d35427dfc6b8bb0
```

- 未 commit；
- 未 push；
- 未创建 tag；
- 未重写 Git 历史；
- 未修改原始实验数据；
- 未修改 `requirements.txt`；
- `src/epr_workflow/` 未修改；
- 用户上传的 `S-BSAPEG-10.0.dpt` 位于项目根目录，当前为未跟踪文件；测试只读，
  SHA-256 前后不变；
- M9 时工作树为未跟踪的 M0–M9 SpectraLab 文件；M10 已另行完成。

---

## 13. 完成清单

- [x] Generic CSV importer
- [x] Generic TXT/DPT importer
- [x] 显式 X/Y 列索引
- [x] 表头列名映射
- [x] 逗号/Tab/分号/空白/自定义分隔符
- [x] 点/逗号小数
- [x] 有/无表头
- [x] 注释标记
- [x] 编码
- [x] 显式跳过行
- [x] 递增/递减轴保留
- [x] 重复/非单调轴拒绝
- [x] 非法/非有限数值拒绝
- [x] 缺列/行长度错误
- [x] 两列默认映射，宽表要求显式映射
- [x] wavenumber/cm^-1 显式确认
- [x] absorbance/transmittance/unknown
- [x] ATR/Transmission/Unknown
- [x] ATR 校正状态四值
- [x] 可选厂商/型号
- [x] provenance 与选项追踪
- [x] 源文件不可变
- [x] FTIR batch 导入
- [x] 部分失败隔离
- [x] 输出碰撞/覆盖保护
- [x] CLI 显式参数
- [x] 显式 importer 注册
- [x] 无 Qt/EPR/legacy 依赖
- [x] 无循环导入
- [x] 无新增依赖
- [x] 原 EPR 298 passed / 1 skipped
- [x] 完整 592 passed / 1 skipped
- [x] `-W error::UserWarning` 通过
- [x] 真实 `S-BSAPEG-10.0.dpt` 导入（4350 点、递减轴、显式 ATR/Absorbance）
- [x] 真实样本 CLI 端到端 raw CSV/JSON 导出
- [x] 源文件哈希在导入前后不变
- [x] M9 范围停在 M10 之前（M10 已另行完成）
- [x] 未 commit、未 push

**M9 完成。** 真实 ATR-FTIR 样本已成功导入并完成端到端原始导出验证；源文件
未被修改。M10 已完成，见
[M10 FTIR GUI 报告](m10_ftir_gui_report.md)；M11 已完成，见
[M11 Maintenance & Normalization 报告](m11_maintenance_and_normalization_report.md)；
M12 尚未开始。
