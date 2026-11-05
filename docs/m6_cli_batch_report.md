# M6 报告：通用 CLI 与 Batch Adapter

- 状态：**M6 完成**
- 基线版本：EPR Workflow **v0.2.0**
- Git 基线：`327d5f6`
- 前序测试基线：M5 **447 passed, 1 skipped**
- M6 基线：**468 passed, 1 skipped**
- 日期：2026-11-02
- 范围：只新增技术无关的 CLI、batch 编排和 raw Spectrum1D CSV/JSON 导出接线
- 现有 EPR CLI、batch、GUI、解析器、schema：**未修改**
- Git：**未 commit、未 push**

---

## 1. 实现前的现有 CLI / batch 检查

检查了：

- `src/epr_workflow/plot_asc.py` 的 `main()`、`run_single()`、`batch_process_directory()`、
  `run_batch()`、`discover_dataset_files()`
- `tests/test_plot_asc.py`、`tests/test_batch.py`
- M2 importer registry
- M3 通用 CSV/JSON export renderers
- M4 `ProcessingSession`
- M5 generic plotting foundation
- M0–M5 报告和 architecture proposal

### 现有 EPR CLI 行为

现有 `epr_workflow.plot_asc.main()`：

- 单文件 positional input，默认 `data/raw/BSA3T275.ASC`；
- `--input-dir` + `--recursive` 批量；
- `--output-dir` 默认 `<project>/results`；
- `--overwrite`；
- `--figure` / `--csv` / `--json` 只允许单文件；
- `--show` 只允许单文件；
- `--allow-non-monotonic`；
- 输出 `tables/<stem>_raw.csv`、`figures/<stem>_raw.png`、
  `logs/<stem>_metadata.json`、`logs/batch_summary.json`；
- 发现 `.ASC` / `.DSC`，排除 `.DTA`；
- 批处理捕获单文件失败并继续，部分失败退出 1；
- 旧的 `success_with_warnings` 状态和 JSON schema 保持不变。

### 兼容约束

M6 不修改上述任何代码、输出、字串、退出码或 schema。新 CLI 使用独立模块、
独立输出命名和独立 summary，避免与旧 EPR 输出混淆：

- 新 summary：`logs/spectralab_batch_summary.json`
- 旧 summary：`logs/batch_summary.json`（未改动）

---

## 2. 新 CLI 入口与用法

### 入口

```text
python -m spectralab.app
```

实现入口：

- [src/spectralab/app/__main__.py](../src/spectralab/app/__main__.py)
- [src/spectralab/app/cli.py](../src/spectralab/app/cli.py)

Python API：

```python
from spectralab.app.cli import main, build_parser
from spectralab.app.batch import run_batch, BatchResult
```

### 用法示例

```powershell
.\.venv\Scripts\python.exe -m spectralab.app .\data\raw\BSA3T275.ASC --output-dir .\results\generic
.\.venv\Scripts\python.exe -m spectralab.app .\data\raw\a.ASC .\data\raw\b.DSC --output-dir .\results\generic
.\.venv\Scripts\python.exe -m spectralab.app .\data\raw --output-dir .\results\generic --recursive
.\.venv\Scripts\python.exe -m spectralab.app .\data\raw --output-dir .\results\generic --format-id ASC
```

参数：

| 参数 | 行为 |
| --- | --- |
| `inputs` | 一个或多个文件或目录；保留显式顺序 |
| `--output-dir` | 必填输出目录 |
| `--format-id` / `--format` | 显式格式选择，例如 `ASC`、`BES3T` |
| `--technique` | 显式技术选择，例如 `epr` |
| `--recursive` | 目录递归发现 |
| `--overwrite` | 明确允许替换输出 |

没有默认输入、没有默认输出目录；不会隐式选择默认样本。

### 输入发现

- 显式文件无论后缀都进入处理；不支持/畸形文件显式失败，不会静默消失。
- 目录只发现 registry importer 声明的后缀；因此 `.DTA` 不会被当作独立数据集。
- 目录文件按相对路径 casefold 稳定排序。
- 显式输入顺序保留，目录展开内容按排序插入该位置。

---

## 3. Batch 行为

统一由：

```python
run_batch(inputs, output_dir, *, format_id=None, technique=None,
          recursive=False, overwrite=False, registry=None) -> BatchResult
```

实现：

- 每个文件独立 `registry.read()`；
- 单个失败不阻止其他文件；
- 每个文件记录成功或失败、错误码、输出路径；
- 结果输入顺序稳定；
- 每个文件都通过 M2 registry 选择 importer；
- 使用 M3 `render_spectrum_csv()`、`render_csv_metadata_json()`、
  `render_spectrum_json()` 生成内容；
- 没有运行 M4 processing；
- 没有运行 M5 plotting；
- 没有自动平滑、基线、归一化、滤波、插值、排序、反转或峰检测。

### 每文件输出

```text
<output-dir>/tables/<stem>.csv
<output-dir>/tables/<stem>_metadata.json
<output-dir>/json/<stem>.json
```

### Batch summary

```text
<output-dir>/logs/spectralab_batch_summary.json
```

Schema：

- `schema_id = "spectralab.batch_summary"`
- `schema_version = 1`

内容包含：

- 请求的 inputs；
- output directory；
- format/technique/recursive/overwrite；
- files discovered/succeeded/failed；
- overall status：`success` / `partial_failure` / `failed`；
- batch-level structured errors；
- 每个文件的 input、status、format、technique、importer、point count、
  source hash、source files、warnings、outputs、error code/context；
- `processing_applied: []`；
- scientific note。

---

## 4. 错误与退出码设计

| Exit code | 场景 |
| --- | --- |
| `0` | 全部文件成功，且没有 discovery/summary 错误 |
| `1` | 任一文件失败、输入缺失、无输入、输出冲突、summary/overwrite 失败 |
| `2` | argparse 参数使用错误 |

错误码来自 registry/exporter，并补充 batch 错误：

- `unsupported_format`
- `ambiguous_format`
- `entry_not_found`
- `importer_read_failed`
- `output_exists`
- `output_is_source_file`
- `output_collision`
- `multiple_spectra_unsupported`
- `input_not_found`
- `no_inputs`
- `invalid_output_dir`
- `summary_parent_not_directory`
- `summary_path`
- `summary_write_failed`

所有文件失败都进入 summary；不会静默跳过。歧义 importer 要求显式
`--format-id`/`--format` 或 `--technique`，不会自动按 confidence 选择。

---

## 5. 输出命名与碰撞保护

### 命名

每个输入 stem 生成：

- `tables/<stem>.csv`
- `tables/<stem>_metadata.json`
- `json/<stem>.json`

summary：

- `logs/spectralab_batch_summary.json`

### 碰撞

写入前计算全部输出路径的规范化绝对路径：

- 两个不同输入产生同一输出路径 → 两个文件都标为 `output_collision`，
  不写任何冲突输出；
- 不自动改名、不自动加序号、不静默覆盖；
- 其他不冲突文件仍可继续处理。

### 覆盖

- 默认 `overwrite=False`。
- 任一输出已存在，该文件失败为 `output_exists`，不写该文件的三个输出。
- summary 已存在且未授权 → 整个 batch 在写入任何 per-file 输出前失败。
- `--overwrite` 才允许替换。
- 源文件路径通过 M3 source protection 和输入路径检查保护，即使
  `overwrite=True` 也拒绝。

### 部分输出

每个文件先完成 registry 读取、source protection 和全部序列化，再逐个原子写
三个文件。序列化失败不会留下该文件的任何输出。三个文件不是跨文件事务；
极端文件系统错误下可能出现部分已写文件，summary 会标记
`partial_outputs=true` 并记录已写路径。

---

## 6. 架构边界结果

- generic CLI 位于 `spectralab.app`；
- `spectralab.core` 不导入 CLI、batch、GUI、Qt、EPR 或 FTIR；
- `spectralab.app.cli` / `batch` 不直接导入 `epr_workflow`；
- 技术选择通过 `spectralab.app.registry` 的显式注册完成；
- 依赖方向保持 `app → techniques → core`；
- 新 CLI 未修改旧 EPR 入口；
- 新 CLI 未接入 GUI；
- 未新增依赖；
- 未修改 M3 schema、M4 processing 或 M5 plotting。

---

## 7. 测试结果

新增 **21 个 M6 测试**：

- `tests/test_cli.py`：17
- `tests/test_m6_architecture.py`：4

覆盖：

- 单文件成功与 CSV/JSON 输出
- 多文件与输入顺序
- 目录排序与递归
- 显式 format/technique
- 错误 format
- 歧义 importer
- 不支持文件
- 缺失输入/空目录
- 输出碰撞
- 覆盖保护
- summary 覆盖保护
- source-file protection
- 部分失败隔离
- warnings/hash 记录
- exit code
- argparse exit code
- raw preservation
- no processing
- architecture boundaries
- old CLI importability

实际运行：

```text
完整测试集 pytest -v：
468 passed, 1 skipped
exit code 0

pytest -q -W error::UserWarning：
468 passed, 1 skipped
exit code 0

原 EPR 测试集（排除 M0–M6 测试）：
298 passed, 1 skipped
exit code 0
```

日志：

- `results/logs/pytest_m6_20261102_verbose.txt`
- `results/logs/pytest_m6_20261102_userwarning.txt`
- `results/logs/pytest_m6_20261102_original.txt`

---

## 8. 向后兼容

- 旧 `epr_workflow.plot_asc.main()` 未修改；
- 旧 batch、ASC/BES3T parser、GUI、CLI、CSV/JSON/PNG 输出未修改；
- 旧 summary `logs/batch_summary.json` 未修改；
- 现有测试未修改；
- 原 EPR 测试 298 passed / 1 skipped 不变；
- 新 CLI 独立入口和独立 summary；
- 删除新增 app 模块即可回滚；
- 无新增依赖，`requirements.txt` 未修改。

---

## 9. 剩余限制与风险

1. 新 CLI 只做 raw import + generic CSV/JSON；没有 processing 或 plotting 选项。
2. M4 `ProcessingSession` 和 M5 plotting foundation 没有接入 CLI；本里程碑没有安全的
   用户处理参数设计，因此显式保持 raw-only。
3. 没有 PNG/plot 输出。
4. 输出目录是显式单一目录；没有 per-file 自定义输出路径。
5. 目录发现使用 registry 声明的后缀；显式文件仍会进入处理并由 probe/read 明确失败。
6. `--format-id`/`--technique` 不会改变目录发现的后缀集合；被过滤掉的文件会作为
   该目录中的输入被发现并显式失败，而不是静默删除。
7. 一个输入产生多个 `Spectrum1D` 时会显式失败（`multiple_spectra_unsupported`）；
   M2 当前 EPR importer 只产生一个谱。
8. CSV、metadata sidecar、JSON 三个文件不是跨文件事务；已写路径会在失败记录中
   标记为 partial outputs。
9. 没有 batch summary 的时间戳；summary 是确定性结构化状态。
10. 新输出布局与旧 EPR 输出不同；旧的 `tables/*_raw.csv`、`figures/*.png`、
    `logs/batch_summary.json` 保持不变。
11. 没有 GUI integration、FTIR、peak detection、difference spectra、multi-spectrum
    comparison、M7 或 M8。

---

## 10. M6 完成清单

- [x] 独立 `spectralab.app` CLI
- [x] `python -m spectralab.app`
- [x] 显式 input files/directories
- [x] registry-based importer selection
- [x] explicit format/technique
- [x] explicit output directory
- [x] generic CSV/JSON export
- [x] batch multiple inputs
- [x] input order preservation
- [x] per-file successes/failures
- [x] non-zero exit on failures
- [x] structured `spectralab_batch_summary.json`
- [x] output collision detection
- [x] overwrite protection
- [x] source-file protection
- [x] partial batch isolation
- [x] no automatic processing
- [x] no old EPR code changes
- [x] no Qt/EPR imports from core
- [x] no new dependencies
- [x] 完整测试 468 passed / 1 skipped
- [x] 原 EPR 子集 298 passed / 1 skipped
- [x] 未 commit、未 push

**M6 状态：完成。** M7 见 [M7 EPR Backend Closure 报告](m7_epr_backend_closure_report.md)，
M8 见 [M8 GUI Architecture 报告](m8_gui_architecture_report.md)；M9 尚未开始。
