# M2 报告：Importer 协议、注册表与旧 EPR 导入适配

- 状态：**M2 完成**
- 基线版本：EPR Workflow **v0.2.0**
- Git 基线：`327d5f6`
- 前序基线：M0 **308 passed, 1 skipped**；M1 **332 passed, 1 skipped**
- M2 基线：**364 passed, 1 skipped**
- 日期：2026-11-02
- 范围：只新增中立 importer 协议/注册表、EPR ASC/BES3T 适配器和测试
- 现有生产行为：**未改变**
- 现有 EPR 代码、CLI、GUI、CSV/JSON schema：**未修改**
- Git：**未 commit、未 push**

---

## 1. 新增与修改文件

### 新增核心 importer 基础设施

- [src/spectralab/core/importers/__init__.py](../src/spectralab/core/importers/__init__.py)
- [src/spectralab/core/importers/base.py](../src/spectralab/core/importers/base.py)
- [src/spectralab/core/importers/registry.py](../src/spectralab/core/importers/registry.py)
- [src/spectralab/core/importers/sources.py](../src/spectralab/core/importers/sources.py)
- [src/spectralab/core/importers/validation.py](../src/spectralab/core/importers/validation.py)

### 新增 EPR 技术适配器

- [src/spectralab/techniques/__init__.py](../src/spectralab/techniques/__init__.py)
- [src/spectralab/techniques/epr/__init__.py](../src/spectralab/techniques/epr/__init__.py)
- [src/spectralab/techniques/epr/importers/__init__.py](../src/spectralab/techniques/epr/importers/__init__.py)
- [src/spectralab/techniques/epr/importers/_common.py](../src/spectralab/techniques/epr/importers/_common.py)
- [src/spectralab/techniques/epr/importers/xepr_asc.py](../src/spectralab/techniques/epr/importers/xepr_asc.py)
- [src/spectralab/techniques/epr/importers/bes3t.py](../src/spectralab/techniques/epr/importers/bes3t.py)

### 新增应用层显式注册

- [src/spectralab/app/__init__.py](../src/spectralab/app/__init__.py)
- [src/spectralab/app/registry.py](../src/spectralab/app/registry.py)

### 修改现有中立代码

- [src/spectralab/core/errors.py](../src/spectralab/core/errors.py)：新增 importer 错误类型
- [src/spectralab/core/__init__.py](../src/spectralab/core/__init__.py)：导出 importer API
- [src/spectralab/core/legacy_adapter.py](../src/spectralab/core/legacy_adapter.py)：新增可选
  `importer_id` / `importer_version`，默认行为不变

### 新增测试

- [tests/test_importer_registry.py](../tests/test_importer_registry.py)：12 个注册表/协议测试
- [tests/test_epr_importers.py](../tests/test_epr_importers.py)：14 个 EPR 适配器测试
- [tests/test_m2_architecture.py](../tests/test_m2_architecture.py)：6 个边界测试

合计 **32 个新测试**。

### 新增 / 更新文档

- 本报告
- [docs/architecture_proposal.md](architecture_proposal.md)：更新 M2 状态和测试基线
- [docs/m1_spectrum1d_report.md](m1_spectrum1d_report.md)：页脚更新为已进入 M2

### 未修改

- `src/epr_workflow/` 下所有生产代码
- 现有测试
- GUI、CLI、批处理、CSV/JSON 导出 schema
- `requirements.txt`
- 原始数据、项目名称、包名、仓库和配置

---

## 2. Importer 协议 API

模块：`spectralab.core.importers.base`

### 2.1 `Importer` Protocol

```python
@runtime_checkable
class Importer(Protocol):
    id: str
    version: str
    technique: str
    entry_suffixes: tuple[str, ...]

    def probe(self, entry: Path) -> ProbeResult: ...
    def collect_sources(self, entry: Path) -> tuple[SourceFile, ...]: ...
    def read(self, request: ImportRequest) -> ImportedDataset: ...
```

协议只定义接口，不包含具体技术解析。`runtime_checkable` 用于测试和注册前检查。

### 2.2 `ProbeResult`

| 字段 | 含义 |
| --- | --- |
| `supported` | 内容探测是否确认支持 |
| `confidence` | 0–1 的描述性置信度；**不用于打破歧义** |
| `format_id` | 格式标识 |
| `technique` | 技术标识或 `None` |
| `reason` | 不支持/支持原因 |

### 2.3 `ImportRequest`

| 字段 | 含义 |
| --- | --- |
| `entry` | 数据集入口文件 |
| `companions` | 预声明伴随文件；M2 EPR 适配器不接受覆盖 |
| `technique_hint` | 技术要求；与 importer 不一致时拒绝 |
| `options` | 格式选项；M2 EPR 适配器不接受未知选项 |
| `allow_ambiguous` | 预留；注册表仍不会按置信度自动消歧 |

`companions` 和 `options` 在构造时浅拷贝为只读映射。

### 2.4 `ImportedDataset`

| 字段 | 含义 |
| --- | --- |
| `spectra` | 至少一个 `Spectrum1D` |
| `primary_index` | 主谱索引 |
| `format_id` | 成功导入的格式 |
| `technique` | 技术标识 |
| `warnings` | 导入阶段警告 |
| `diagnostics` | 导入诊断 |

`primary` 属性返回 `spectra[primary_index]`。M2 的 EPR 导入始终返回一个谱。

---

## 3. 注册表 API 与分派规则

模块：`spectralab.core.importers.registry`

```python
class ImporterRegistry:
    @property
    def importers(self) -> tuple[Importer, ...]: ...
    def register(self, importer: Importer, *, replace: bool = False) -> None: ...
    def candidates(self, entry: Path) -> tuple[ProbeResult, ...]: ...
    def select(self, entry: Path, *, technique=None, format_id=None) -> Importer: ...
    def read(self, entry: Path, *, technique=None, format_id=None,
             companions=None, options=None, allow_ambiguous=False) -> ImportedDataset: ...
```

分派规则：

1. 只对 `entry_suffixes` 匹配的 importer 调用 `probe()`；扩展名只用于缩小候选集。
2. 扩展名匹配不等于支持；必须 `probe().supported` 为真。
3. 没有候选 → `UnsupportedFormatError`（`code="unsupported_format"`），上下文列出
   探测结果和可用格式。
4. 多个候选且没有 `technique`/`format_id` 明确选择 →
   `AmbiguousFormatError`（`code="ambiguous_format"`）。
5. `confidence` 只记录，不自动选最高分。
6. `read()` 先 `select()`，再调用唯一 importer；读取失败不会尝试其他 importer。
7. 注册表不导入具体技术包，不自动发现插件；默认新建的 `ImporterRegistry()` 为空。
8. 重复 `id` 默认拒绝；只有显式 `replace=True` 才替换。
9. `probe()` 抛异常、返回非 `ProbeResult`、`read()` 返回非 `ImportedDataset`
   都会变成明确错误，不会静默跳过或回退。

应用层显式注册：

```python
from spectralab.app.registry import build_importer_registry

registry = build_importer_registry()
```

当前只注册 `epr.xepr_asc` 和 `epr.bes3t`。核心层不认识这两个 ID。

---

## 4. ASC 与 BES3T 适配器行为

### 4.1 `XeprAscImporter`

- `id="epr.xepr_asc"`
- `version="0.1.0"`
- `technique="epr"`
- `entry_suffixes=(".asc",)`
- `format_id="ASC"`
- 类名别名：`XeprASCImporter`

`probe()`：

- 后缀必须为 `.asc`；
- 扫描文本，要求同时出现 `index`、`Field`、`Intensity` 表头标记；
- 不猜测列，不读取数据行做格式判断。

`read()`：

- 调用现有 `epr_workflow.plot_asc.read_asc()`；
- 通过 M1 `spectrum1d_from_import_result()` 转成 `Spectrum1D`；
- 保留点序、数值、`G` 单位、方向、来源哈希/大小/警告；
- `semantics="unknown"`，不推断吸收/导数谱。

`collect_sources()`：

- 返回一个 `role="source"` 的 `SourceFile`，包含 SHA-256 和大小。

### 4.2 `Bes3tImporter`

- `id="epr.bes3t"`
- `version="0.1.0"`
- `technique="epr"`
- `entry_suffixes=(".dsc",)`
- `format_id="BES3T"`
- 类名别名：`BES3TImporter`

`probe()`：

- 后缀必须为 `.dsc`；
- 扫描文本中是否存在 `#DESC` 段；
- `.DTA` 不在入口后缀中，不能作为独立数据集。

`read()`：

- 调用现有 `epr_workflow.bes3t.read_bes3t()`；
- 仍由旧解析器执行 `.DSC`/`.DTA` 配对、截断/尾随字节校验、二进制解码和轴构造；
- 通过 M1 适配器保留 `linspace(XMIN, XMIN+XWID, XPTS)` 轴和所有来源信息。

`collect_sources()`：

- 调用 `find_companion_dta()`；
- 返回 `descriptor` 和 `data` 两个源文件角色及哈希。

### 4.3 明确的 M2 限制

M2 EPR 适配器拒绝非空 `ImportRequest.companions` 和 `options`，避免“传入了参数但
被静默忽略”。如果需要允许非单调 ASC 轴或覆盖伴随文件，应在后续里程碑中显式
设计并记录，而不是在 M2 隐式开放。

---

## 5. 错误处理

核心错误（`spectralab.core.errors`）：

| 错误 | code | 场景 |
| --- | --- | --- |
| `ImportFailure` | 自定义 | 导入失败基类，含上下文与 severity |
| `UnsupportedFormatError` | `unsupported_format` | 无候选/后缀不支持/显式过滤无匹配 |
| `AmbiguousFormatError` | `ambiguous_format` | 多个 importer 同时支持 |
| `ImporterRegistrationError` | `invalid_importer` / `duplicate_importer_id` | 注册定义错误/重复注册 |

注册表/请求错误：

- `entry_not_found`：入口不存在或不是文件；
- `importer_probe_failed`：probe 抛异常；
- `invalid_probe_result`：probe 返回错误类型；
- `invalid_import_result`：read 返回错误类型或空 `ImportedDataset`；
- `importer_read_failed`：读取中的非 `ImportFailure` 异常。

EPR 适配器错误：

- ASC：`asc_format_error`、`asc_data_error`；
- BES3T：保留旧解析器 code，例如 `bes3t_companion_missing`、
  `bes3t_missing_parameter`、`bes3t_truncated`、`bes3t_trailing_bytes`；
- 源文件读取：`source_read_failed`；
- M2 请求限制：`unsupported_companion_override`、`unsupported_import_option`、
  `technique_mismatch`。

所有错误都保留英文消息、稳定 code 和上下文；失败读取不会返回部分 `Spectrum1D`。

---

## 6. 数值等价

### 6.1 合成样本

ASC：

- 逐值比较 `registry.read()` 与 `read_asc()` 的 X/Y；
- 保留递增和递减点序，不排序、不反转。

BES3T：

- 逐值比较 `registry.read()` 与 `read_bes3t()`；
- 保留 DSC/DTA 来源哈希；
- 递减轴保留原始顺序。

### 6.2 真实 M0 基线

使用 `tests/fixtures/m0_baseline.json` 的 `asc_real` 和 `bes3t_real`：

- 点数；
- X/Y 数组逐值相等；
- 首末 X、首末 Y、最小/最大 Y、首末 5 点；
- 轴方向、单位、信号语义；
- `source_format`；
- 规范 SHA-256；
- `source_files` 角色和哈希；
- 导入前后源文件哈希不变。

本机真实 ASC/BES3T 文件存在，测试实际执行并通过，未跳过。

---

## 7. 科学完整性检查

- 无平滑、基线、归一化、滤波、插值、排序、轴反转；
- 不自动推断单位或信号语义；
- 不填充仪器/采集/样品元数据；
- 未知元数据保持未知；
- 文件扩展名只缩小候选，必须通过内容 probe；
- 不支持格式、歧义格式、缺失伴随文件、截断/尾随数据都显式失败；
- 读取失败不返回部分结果，不回退到其他 importer；
- 源文件只读，测试比较导入前后 SHA-256；
- 旧 `ImportResult` 对象和数值不被修改。

---

## 8. 架构边界检查

- `spectralab.core` 不导入 Qt、GUI、`epr_workflow`、`spectralab.app` 或
  `spectralab.techniques`；
- 导入 importer 核心不加载 Qt、EPR 或技术包；
- 默认 `ImporterRegistry()` 为空，核心不自动注册/发现；
- `spectralab.techniques.epr` 只依赖 core 和现有 `epr_workflow`；
- 技术包不导入 app、GUI 或 FTIR；
- `spectralab.app.registry` 是显式集成点，当前只注册 EPR；
- core → techniques → app 的导入图无循环；
- 旧 `epr_workflow` 仍可独立导入，版本仍为 `0.2.0`。

---

## 9. 测试结果

新增 32 个测试：

- `tests/test_importer_registry.py`：12
- `tests/test_epr_importers.py`：14
- `tests/test_m2_architecture.py`：6

实际运行：

```text
M2 新增测试：32 passed, 0 skipped
完整测试集：364 passed, 1 skipped
pytest -v：364 passed, 1 skipped，exit 0
pytest -q -W error::UserWarning：364 passed, 1 skipped，exit 0
原 EPR 测试集（排除 M0/M1/M2 测试）：298 passed, 1 skipped
```

日志：

- `results/logs/pytest_m2_20261102_verbose.txt`
- `results/logs/pytest_m2_20261102_userwarning.txt`

---

## 10. 向后兼容

- `epr_workflow` 生产代码未修改；
- `read_asc()`、`read_bes3t()`、`read_dataset()` 返回值不变；
- 旧 CLI、GUI、批处理、导出路径未接线到新注册表；
- CSV/JSON schema 未修改；
- M1 `legacy_adapter` 默认 `importer_id` 和 `importer_version` 保持不变；
- 原 EPR 测试 298 passed / 1 skipped 不变；
- 新 importer 未替换任何旧入口，删除新模块即可回滚。

---

## 11. 剩余限制与风险

1. M2 只适配 ASC/BES3T；FTIR 未实现任何 importer。
2. 具体 EPR importer 仍调用 `epr_workflow` 旧解析器；这是过渡设计，
   M7 才计划将后端收口到 `techniques/epr`。
3. `legacy_adapter` 仍位于 core，概念上仍是 EPR 兼容桥；这是 M1 的既定安排，
   M2 没有迁移它。
4. 没有 `SourceBundle` 完整对象；`ImportRequest.companions` 已占位但 EPR 适配器
   暂不接受覆盖。
5. `allow_ambiguous=True` 不会让注册表自动选最高置信度；M2 选择显式优先。
6. 探测逻辑是轻量内容检查，不是完整解析：探测确认表头/#DESC 后，真正格式
   错误仍由旧解析器在 `read()` 中报告。
7. `format_id` 使用现有 `ASC`/`BES3T` 大写标识；尚无跨技术统一格式 ID 注册表。
8. `Provenance.imported_at_utc` 仍为 `None`，旧 `ImportResult` 没有该字段；
   导入器版本固定为 `0.1.0`。
9. 新注册表尚未接入 GUI/CLI/批处理；不改变现有用户路径。
10. 没有自动回退、单位转换或处理操作。

---

## 12. M2 完成清单

- [x] `Importer` 协议
- [x] `ProbeResult` / `ImportRequest` / `ImportedDataset`
- [x] `ImporterRegistry` 显式注册
- [x] 重复注册拒绝/显式替换
- [x] 内容 probe，扩展名不单独决定
- [x] 不支持格式错误
- [x] 歧义格式错误
- [x] ASC 适配器
- [x] BES3T 适配器
- [x] `.DTA` 不作为独立入口
- [x] 失败读取不返回部分结果
- [x] 无自动处理
- [x] 真实 M0 数值等价
- [x] 源文件不变
- [x] core 不导入 Qt/EPR/app/techniques
- [x] 无循环导入
- [x] 旧 EPR 入口保持 298 passed / 1 skipped
- [x] 完整测试 364 passed / 1 skipped
- [x] `-W error::UserWarning` 通过
- [x] 无 commit、无 push

**M2 状态：完成。** M3 见 [M3 通用导出报告](m3_export_report.md)，
M4 见 [M4 通用处理报告](m4_processing_report.md)，M5 见
[M5 通用绘图报告](m5_generic_plotting_report.md)，M6 见
[M6 通用 CLI/Batch 报告](m6_cli_batch_report.md)，M7 见
[M7 EPR Backend Closure 报告](m7_epr_backend_closure_report.md)，M8 见
[M8 GUI Architecture 报告](m8_gui_architecture_report.md)；M9 尚未开始。
