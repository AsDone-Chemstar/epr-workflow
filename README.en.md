# EPR Workflow

[简体中文](README.md) | **English**

A Python analysis workflow for CW-EPR data exported from **Bruker ELEXSYS E580 / Xepr**.

Current version: **0.2.0**. See [CHANGELOG.md](CHANGELOG.md) for release notes and
version history.

Current scope: **import → validation → raw-spectrum plotting → export**, with
support for Xepr three-column ASCII `.ASC` files and native BES3T `.DSC`/`.DTA`
pairs, plus user-triggered **linear baseline correction**, **Savitzky–Golay
smoothing**, and an independent **Plot Editor**. Preprocessing operates only on
in-memory copies, is never applied automatically, and never modifies raw data.
The Plot Editor changes visualization settings only; it does not modify raw
data, processed data, or preprocessing history. Normalization, interpolation,
spike removal, automatic baseline detection, and global curve fitting are not
implemented.

## 1. Requirements

- Windows 10/11
- Python **3.11.9** (64-bit)
- Project virtual environment: `.venv`
- Dependencies: NumPy, SciPy, Pandas, Matplotlib, Pytest, and PySide6
  (versions are listed in `requirements.txt`)

## 2. Setup

```powershell
# Change to the project directory
cd "D:\EPR workflow"

# Create a virtual environment if .venv does not exist
python -m venv .venv

# Install dependencies
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. Running the scripts

### 3.0 Desktop GUI

The project includes a local desktop interface (PySide6 + Matplotlib) for visual
import, batch processing, status inspection, and zoom/pan. Start it after
installing the dependencies:

```powershell
cd "D:\EPR workflow"
.\.venv\Scripts\python.exe run_gui.py
```

Alternatively:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m epr_workflow.gui
```

GUI features:

- Open a single `.ASC` file or a BES3T `.DSC` descriptor and display its raw
  spectrum read-only (no output files are written). The DTA is paired
  automatically from the DSC and cannot be opened as an independent dataset.
- Select a folder for batch processing; CSV / PNG / JSON files and a batch
  summary are generated. Batch discovery includes `.ASC` and `.DSC` entry
  points and never treats `.DTA` as a separate dataset.
- The sample list uses colors for success / success with warnings / failure;
  click a sample to view its spectrum.
- The toolbar provides zoom, pan, and reset; hovering shows the magnetic field
  and intensity at the cursor.
- Display the field range, point count, signal statistics, and validation
  warnings.
- Open generated CSV / PNG / JSON outputs.
- Existing outputs are **not overwritten by default**; replacement is allowed
  only after checking "Allow overwrite".
- The "Preprocessing" panel in the left column lets the user explicitly choose
  linear baseline correction or Savitzky–Golay smoothing (see 3.4); no
  processing is performed by default.
- The "Plot" tab in the left column provides an independent Plot Editor: set
  visibility, name, color, line width, and line style for the curves that are
  actually available; edit the title, axis labels, ranges, legend, and font
  sizes; and preview changes live (see 3.5). Plot settings do not modify data or
  preprocessing records.
- Plot settings can be exported as a PNG. The exported file is the Matplotlib
  figure itself, not a window screenshot; existing files are not overwritten by
  default.
- The interface supports **live switching between Simplified Chinese and
  English** through the "Language" selector in the upper right. Switching
  language does not re-read the source data file, rerun batch processing, or
  clear the loaded spectra, sample list, batch results, selected sample, or
  cursor readout.
- The language choice is stored in `config\gui_settings.ini` (only the language
  code is saved; nothing is written to the registry). It is restored on restart;
  Simplified Chinese is the default when no setting exists.

GUI logic (`epr_workflow/gui/controller.py`) is separated from the Qt window.
Core data processing still uses `epr_workflow/plot_asc.py`; the GUI itself does
not perform any signal processing.

### 3.1 Processing a single file

```powershell
cd "D:\EPR workflow"

# Process data\raw\BSA3T275.ASC by default
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py

# Process a specified file
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py "data\raw\BSA5P5T10.ASC"

# Process a specified file and show it immediately
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py "data\raw\BSA5P5T10.ASC" --show

# Process a native BES3T dataset: the entry point is the .DSC, not the .DTA
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py "path\to\sample.DSC"
```

For BES3T, the `.DSC` and `.DTA` must share the same filename stem in the same
directory; extension matching is case-insensitive. A `.DTA` is only a companion
and cannot be opened as independent data.

The module form is also available (set `PYTHONPATH` first):

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m epr_workflow.plot_asc
```

### 3.2 Batch processing a directory

```powershell
cd "D:\EPR workflow"

# Process all .ASC and .DSC entry points under data\raw
# (subdirectories are not searched; .DTA is never treated as a dataset)
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py --input-dir data\raw --output-dir results

# Write to a new directory to avoid touching existing results
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py --input-dir data\raw --output-dir results\batch_20261026

# Include subdirectories
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py --input-dir data\raw --output-dir results\all --recursive

# Allow existing outputs to be overwritten
.\.venv\Scripts\python.exe src\epr_workflow\plot_asc.py --input-dir data\raw --output-dir results --overwrite
```

Batch-mode rules:

- Only `.asc` and `.dsc` entry files are processed; matching is
  **case-insensitive**. A `.dta` is a BES3T companion and is never treated as
  an independent dataset.
- Subdirectories are not searched by default; add `--recursive` when needed.
- Processing order is deterministic (relative paths sorted case-insensitively),
  so repeated runs are consistent.
- A failure in one file does not stop the other files; failure information is
  written to the batch summary.
- Existing outputs are **rejected by default**; add `--overwrite` to replace
  them.
- Single-file mode has the same overwrite protection; repeated runs require
  `--overwrite`.

### 3.3 Common options

| Option | Description |
| --- | --- |
| `input` | Single-file mode: `.ASC` path or BES3T `.DSC` descriptor; defaults to `data\raw\BSA3T275.ASC` |
| `--input-dir PATH` | Batch mode: process `.ASC` and `.DSC` entry points in this directory (`.DTA` is excluded) |
| `--output-dir PATH` | Output root, defaults to `results` (batch outputs go into its figures/tables/logs subdirectories) |
| `--recursive` | Search subdirectories in batch mode (disabled by default) |
| `--overwrite` | Allow existing output files to be replaced (rejected by default) |
| `--figure PATH` | Single-file only: custom PNG path |
| `--csv PATH` | Single-file only: custom CSV path |
| `--json PATH` | Single-file only: custom JSON report path |
| `--show` | Single-file only: display the figure interactively |
| `--allow-non-monotonic` | Allow plotting data with a non-monotonic field axis (rejected by default to avoid misleading plots) |
| `--log-level` | Logging level, default `INFO` |

`input` and `--input-dir` cannot be used together. `--figure/--csv/--json/--show`
are available only in single-file mode.

### 3.4 Preprocessing (linear baseline correction / Savitzky–Golay smoothing, GUI only)

Processing is performed only on in-memory copies. The original source files
(ASC or BES3T DSC/DTA) and any already-exported raw results are never modified.
No baseline window is selected by default, and smoothing is not enabled
automatically.

1. Open a single supported data file (ASC or BES3T DSC), or run batch processing
   and select a sample.
2. In the "Preprocessing" panel under "Method", choose:
   - **Linear baseline correction**: enter two closed windows (in G). The four
     input fields start empty; without them, preview and apply are unavailable.
   - **Savitzky–Golay smoothing**: set the window length and polynomial order,
     and choose the smoothing input: "current processed result" (append after
     existing steps) or "raw data" (place before existing steps).
3. Click "Preview": the plot shows the raw data (gray dashed), the difference
   (orange dotted), and the processed result (blue solid). Preview writes no
   files.
4. Click "Cancel preview": discard the temporary preview without changing the
   raw data or the applied processing history.
5. Click "Apply": record the step in the in-memory session for the current file
   (multiple steps may be applied, in order).
6. "Undo" removes the last step, and "Reset" returns to the raw data. Both
   recompute from the original arrays according to the recorded steps.
7. Click "Export processed results…" to write files. Existing files are not
   overwritten by default; check "Allow overwrite" first.

Baseline rules and limitations:

- Each window must contain at least 3 data points. **Three points are only the
  computational minimum for fitting and do not imply that the baseline region
  is reliable.**
- The current version uses **two** non-overlapping closed windows, as approved
  in the design; single-window fitting is not implemented.
- The two windows must not overlap or share endpoints, and at least one
  unselected data point must remain between them.
- Only a **strictly monotonic** field axis is accepted. Duplicate or
  non-monotonic axes are rejected; the program does not sort or repair them.
- Fitting method: all points in both windows are combined into one ordinary
  least-squares straight-line fit, which is then subtracted point by point over
  the full field:
  `intensity_corrected = intensity_raw - (slope × field_G + intercept)`.
- The interface reports residual RMS, window point counts, extrapolation
  distance, and diagnostic warnings. **R² describes only the goodness of the
  straight-line fit inside the chosen windows; it does not prove that the
  selected region is a baseline.** Use the preview, residuals, point counts, and
  extrapolation distance together.

Smoothing rules and limitations:

- Uses `scipy.signal.savgol_filter(window_length, polyorder, deriv=0, mode="interp")`
  and preserves the point count, field order, and float64 type.
- The window length must be **odd**, at least 3, and no larger than the number of
  data points. The polynomial order must satisfy
  `0 ≤ polyorder < window_length`.
- Smoothing changes peak height, peak width, and line shape. **A smoother curve
  does not mean better data quality.**
- When "raw data" is chosen as the input and processing steps already exist, the
  new smoothing step is inserted before the existing steps; both the interface
  and the JSON record the new order and issue a warning.
- Invalid smoothing parameters do not modify any data or applied history.

General rules:

- Processing state for each file exists only in memory for the current session.
  Switching samples does not lose it; closing the program does. If the source
  file's SHA-256 changes, the corresponding session is invalidated.
- Switching language only redraws the interface; it does not refit or resmooth.
- Batch preprocessing and CLI preprocessing options are not currently supported.

### 3.5 Plot Editor (plot settings, GUI only)

The Plot Editor is an independent "Plot" tab in the left column. It **changes
visualization settings only**; it does not read files, rerun baseline correction
or smoothing, or modify raw data, processed data, or preprocessing history.

The curve list is generated dynamically from the data actually available. It
never creates a curve that does not exist:

- **Raw data**: always available.
- **Processed result**: available only after at least one preprocessing step has
  been applied in the current session.
- **Difference / removed baseline**: available only when processing steps exist.
  After baseline correction it is raw minus the processed result; after
  smoothing it is raw minus the smoothed result (the total change, not a
  refitted baseline).
- **Fitted baseline**: available only when baseline correction recorded fit
  parameters. It is **hidden by default** and explicitly labeled as a fitted
  baseline so it cannot be mistaken for an experimental signal.

Each available curve can be configured independently:

- Visibility (hiding a curve does not delete data or change processing steps).
- Display name; when blank, a language-dependent default name is used.
- Color (color picker or `#RRGGBB`) and line width (0.1–10.0 pt).
- Line style: solid, dashed, dotted, or dash-dot.

Axes and legend:

- The title, X-axis label, and Y-axis label are editable and may be left empty.
- X/Y ranges can be automatic or manual. Manual ranges require finite numbers
  with the minimum below the maximum; invalid input shows an error and keeps the
  last valid settings.
- The legend can be shown or hidden and its location selected. Title, axis, tick,
  and legend font sizes can be adjusted separately.

Operating rules:

- All changes are reflected in the GUI canvas immediately; scientific data are
  never saved automatically.
- "Reset" restores the default plot settings for the current data. "Restore
  default visibility" changes only curve visibility; custom names, colors, line
  widths, line styles, and axis settings are preserved.
- Plot settings are stored per sample in current-session memory and restored
  when switching samples. If the source file's SHA-256 changes, that sample's old
  settings are invalidated. Settings are not retained after the program closes.
- Switching language updates automatic titles/labels and default legend names,
  but does not re-read the source data file or rerun correction or smoothing. Custom text
  and styles are preserved.
- Export is disabled while preprocessing is in an **unapplied preview** state, so
  a temporary preview cannot be mistaken for a final result.

PNG export:

- Click "Export plot…" in the "Plot" tab. The output is the current Matplotlib
  figure itself (not a window screenshot), produced by the same drawing function
  and settings used for the live preview.
- Width, height (inches), and DPI are configurable; the common 150 / 300 / 600
  dpi values are supported. Title and legend can be included or omitted
  independently.
- The default path is `<output-dir>\figures\<sample>_plot.png`; another path may
  be chosen.
- Existing files are **rejected by default**; replacement requires confirmation.
- It never writes to `data\raw\`, never overwrites the raw `_raw` outputs or
  processed CSV/JSON files, and plot-parameter changes do not alter any
  scientific data output.

## 4. Output files

### 4.1 Single file

For `BSA3T275.ASC` (file stem `BSA3T275`, output root `results`):

| File | Content |
| --- | --- |
| `results\figures\BSA3T275_raw.png` | Raw CW-EPR spectrum, 300 dpi |
| `results\tables\BSA3T275_raw.csv` | Imported three-column data (`index, field_G, intensity`) |
| `results\logs\BSA3T275_metadata.json` | Validation and statistics report |

### 4.2 Batch processing

```text
<output-dir>\
├── figures\<sample>_raw.png
├── tables\<sample>_raw.csv
├── logs\<sample>_metadata.json
└── logs\batch_summary.json
```

`<sample>` is generated from the input filename. With `--recursive`, relative
subdirectories are included, for example
`data\raw\sub\X.ASC` → `sub_X_raw.csv`, so same-named files in different
subdirectories do not overwrite each other. If two files would still produce the
same output name, those files are marked as failed and no output is written.

The JSON report contains: source filename, file size, SHA-256, import time (UTC),
valid point count, rejected-row count, missing-column row count
(`missing_value_count`, counted by **row**, not by missing cell), non-finite /
duplicate-field counts, field minimum and maximum, signal min/max/mean/standard
deviation, field monotonicity, index continuity, software version, all validation
warnings, and whether the source file remained unchanged.

In addition:

- `outputs`: the CSV, PNG, and JSON paths actually generated in this run.
- `processing`: plotting parameters for this run (figsize, dpi, line width), with
  `smoothing` / `baseline_correction` / `normalisation` / `field_axis_reversal`
  all set to `false`. This field **describes only the current run**; it is not a
  guarantee about future runs.

CSV `index`: written as integers (`1` rather than `1.0`) only when every value is
a valid integer. Non-integer or invalid values are preserved as-is and are never
forced to integers.

### 4.3 Batch summary `batch_summary.json`

```json
{
  "batch": {
    "processed_at_utc": "2026-10-26T11:08:10+00:00",
    "timezone": "All timestamps are UTC (datetime.now(timezone.utc)).",
    "input_dir": "D:\\EPR workflow\\data\\raw",
    "output_dir": "D:\\EPR workflow\\results\\batch_integration_20261026",
    "recursive": false,
    "files_discovered": 2,
    "files_succeeded": 2,
    "files_succeeded_with_warnings": 0,
    "files_failed": 0,
    "overall_status": "success",
    "errors": []
  },
  "files": [ ... ]
}
```

- Each file records its own `status`: `success` (no warnings),
  `success_with_warnings` (processed but with validation warnings), or `failed`
  (not processed or no result produced).
- `overall_status`: `success`, `success_with_warnings`, `partial_failure`, or
  `failed`.
- Each file entry also contains the source SHA-256 (before and after processing),
  field range, output paths, warnings, and error information.
- Exit codes: `0` when every file succeeds (including files with warnings only),
  and `1` when any file fails.
- The summary explicitly states that **a completed script run does not mean the
  data have been scientifically validated**.

Batch failures and warnings are printed to the console (for example,
`[1/2] FAILED: xxx.ASC`) and written to the summary; they are never silently
skipped.

### 4.4 Processed results (baseline correction / Savitzky–Golay smoothing)

The filename suffix depends on the processing actually applied:

| Processing history | Files |
| --- | --- |
| Linear baseline correction only | `<sample>_baseline.csv/.png/_metadata.json` |
| Savitzky–Golay smoothing only | `<sample>_smoothed.csv/.png/_metadata.json` |
| Baseline correction + smoothing | `<sample>_baseline_smoothed.csv/.png/_metadata.json` |

- For baseline correction only, the CSV columns follow the first stage:
  `index, field_G, intensity_raw, intensity_corrected, baseline_removed`.
- For output containing smoothing, the CSV columns are
  `index, field_G, intensity_raw, intensity_corrected, difference_from_raw`.
  The last column is the **total change from raw to processed**, not the fitted
  baseline.
- The PNG and JSON use **English** (consistent with the existing raw export); the
  GUI interface remains bilingual.
- The `preprocessing` block in the JSON records: `schema_version`, `data_kind`,
  algorithm names and versions, step order, each step's parameters and input
  source, baseline window coordinates/point counts/fit parameters, smoothing
  window length/order/change statistics, application time (UTC), source SHA-256,
  software version (including SciPy), warnings, assumptions, the `not_applied`
  list, and output-column descriptions.
- The top level also records `data_kind` (`baseline_corrected`, `smoothed`, or
  `baseline_corrected_and_smoothed`), clearly distinguishing processed output
  from raw-data export.
- The `processing.applied_in_this_run` flag and `preprocessing_step_order` are
  updated at the same time. The JSON structure for raw-data export is unchanged.
- Before writing, the export verifies the source file's SHA-256; if the source
  changed after import, the export is rejected.

### 4.5 Plot Editor image `<sample>_plot.png`

- Default location: `<output-dir>\figures\<sample>_plot.png` (editable in the
  export dialog).
- The content is the current Plot Editor Matplotlib figure, including the curves
  visible at that time, title/labels, ranges, legend, fonts, and line styles. It
  does not include GUI controls or window borders.
- Automatic titles, axis labels, and default curve names use the **interface
  language at export time**; user-entered text is preserved verbatim. This
  differs from the fixed-English rule for processed PNG/JSON files in 4.4.
- Figure size, DPI, and whether to include the title/legend are chosen in the
  export dialog; defaults are `8 × 5 in` and `300 dpi`.
- This file is a **display output**, not a new scientific data record. It does not
  create or modify CSV/JSON files.
- Export does not change the original source files, already-exported `_raw`
  results, or the current session's preprocessing history.

### 4.6 BES3T import output

- Raw-output naming is the same as for ASC: `<sample>_raw.csv`,
  `<sample>_raw.png`, and `<sample>_metadata.json`, where `<sample>` is the
  `.DSC` filename stem.
- BES3T raw CSV appends a constant `source_format` column (`BES3T`) after the
  historical three columns. ASC CSV remains
  `index, field_G, intensity` without that column.
- BES3T processed CSV also appends `source_format=BES3T`; raw intensity
  remains `intensity_raw`, and processed intensity is `intensity_corrected`.
- JSON adds:
  - `source_format`: `BES3T`;
  - `source_files`: role, absolute path, filename, before/after SHA-256, size,
    and unchanged flag for the DSC and DTA;
  - `sha256_definition`: definition of the combined hash;
  - `file_size_bytes_definition`: total size of both source files;
  - `format_metadata`: raw descriptor text, `#DESC`/`#SPL`/`#DSL` records,
    parsed and inferred parameters, axis definition, binary type/byte order,
    and diagnostics;
  - `assumptions`: BES3T-specific assumptions.
- `sha256` is the SHA-256 of `BES3T:<dsc-sha256>:<dta-sha256>`, not the hash of
  either file alone. A change to either source file fails provenance
  verification.
- `data/raw` write protection, source-overwrite protection, processed-output
  protection, and Plot Editor export protection apply to both DSC and DTA.

## 5. Supported data formats and assumptions

### 5.1 Xepr ASCII `.ASC`

1. Plain text, whitespace-separated (spaces/tabs), **three columns**.
2. The header row contains the keywords `index`, `Field [G]`, and `Intensity []`
   in that order. If other columns are present or the order differs, the program
   **raises an error instead of guessing** the meaning of the columns.
3. Column 1 is used only as a row index, not as a physical quantity.
4. Column 2 is the magnetic field in **Gauss (G)**.
5. Column 3 has no documented intensity unit and is reported in **original
   units**; no unit is invented.
6. Blank lines are ignored. Unparsable lines are **recorded and excluded**, with a
   warning and line number.
7. Data-row order is preserved exactly; nothing is sorted.
8. Linear baseline correction assumes that the intensity baseline can be
   represented by a straight line over the displayed field range and that the
   baseline is additive on the undocumented intensity scale. The user is
   responsible for this assumption; the program does not validate it.
9. Savitzky–Golay smoothing assumes that the signal in a local window can be
   approximated by a low-order polynomial. Smoothing changes peak height, peak
   width, and line shape; it does not necessarily improve data quality.

### 5.2 Bruker BES3T `.DSC` + `.DTA`

This release supports **one-dimensional, real-valued** BES3T datasets only.

1. Use the `.DSC` descriptor as the entry point. A same-stem `.DTA`
   (case-insensitive) must exist in the same directory; a `.DTA` cannot be
   opened independently.
2. The `#DESC` layer must contain verifiable values for:
   - `BSEQ`: `BIG` or `LIT`; no unverified default byte order is used.
   - `IKKF`: one `REAL` only; `CPLX` and multiple values are rejected.
   - `IRFMT`: one of `C`/`S`/`I`/`F`/`D`
     (int8/int16/int32/float32/float64).
   - `XTYP`: `IDX` only; `IGD` external axes and `NTUP` are unsupported.
   - `XPTS`: positive integer and at least 3.
   - `XMIN`, `XWID`: finite, with `XWID` nonzero.
   - `XUNI`: `G` (Gauss) only; no mT or other unit conversion is applied.
3. If `YPTS`/`ZPTS` are absent, BES3T's documented dimension default of 1 is
   used and recorded in `inferred_parameters`. A value greater than 1, or a
   `YTYP`/`ZTYP` other than `NODATA`, is rejected as multidimensional.
4. The linear axis is `linspace(XMIN, XMIN + XWID, XPTS)`, with **both
   endpoints included**. The step is therefore `XWID / (XPTS - 1)`, not
   `XWID / XPTS`.
5. The DTA payload is decoded from `IRFMT` and `BSEQ` and its size is checked
   exactly. Fewer bytes are reported as truncation; extra bytes are reported
   as trailing data. Nothing is silently padded or truncated.
6. Original point order is preserved. No sorting, interpolation, scaling,
   smoothing, or baseline correction is performed.
7. The raw descriptor text, all `#DESC`/`#SPL`/`#DSL` records, parsed values,
   inferred values, source SHA-256 hashes, and file sizes are recorded in JSON.
8. Real integer formats are represented as float64 in the common data model;
   their numerical values are unchanged, and this is recorded in assumptions.

Unsupported: complex data, multidimensional data, `IGD` axes, `NTUP` axes,
non-Gauss axis units, multiple values per point, missing required metadata,
truncated payloads, and trailing bytes. These cases raise explicit errors
rather than being guessed into a spectrum.

`Test data\BSA3mal1h.DSC`/`.DTA` is a local validation sample and is not
uploaded with the repository.

Validation of that real sample in this release:

- `XPTS=1024`; the DTA is 8192 bytes, consistent with 1024 × 8 bytes.
- `IRFMT=D` and `BSEQ=BIG`, decoded as big-endian float64.
- `XMIN=3310` and `XWID=100` produce a 3310–3410 G axis with 1024 points.
- The first three intensities are `-76, -69, -67`; the last is `-84`, matching
  the raw binary payload.
- DSC and DTA SHA-256 hashes are unchanged before and after import.

No matching Xepr ASCII export was available, so **point-by-point cross-format
comparison is still pending**. A successful plot alone is not sufficient
evidence that decoding is correct.

## 6. Validation rules

- Plotting is refused when fewer than 3 valid points remain.
- The field column must be strictly increasing or strictly decreasing;
  non-monotonic data are **rejected by default** and no plot is generated.
- Diagnostics distinguish "duplicate field values" from "decreasing steps";
  duplicate points are never deleted or merged.
- NaN / Inf rows are identified and excluded, and the count is written to the
  report.
- Duplicate field values make the field axis non-monotonic: this is an error by
  default. With `--allow-non-monotonic`, a warning is issued and no data are
  deleted or merged.
- Index continuity is a **warning**, not an error: continuity is checked only
  when indices are integers and strictly increasing. The program does not assume
  that every file starts at 1, and it does not sort or renumber.
- The field axis is **not reversed** (acquisition metadata authorization has not
  been granted).
- After a run, the source file's SHA-256 is recomputed to confirm that the data
  file was not modified.
- GUI baseline correction accepts only a strictly monotonic field axis; duplicate
  or non-monotonic axes are rejected without sorting or repair.
- Baseline results never replace the raw data; undo and reset both recompute from
  the original array according to the recorded steps.
- The Savitzky–Golay window length must be odd, at least 3, and no larger than
  the number of data points. The polynomial order must satisfy
  `0 ≤ polyorder < window_length`, and all input values must be finite.
- Smoothing does not change the number of points, the field axis, or the row
  order. It does not rescale, normalize, or remove points.
- BES3T DSC/DTA pairing requires a case-insensitive filename-stem match; a
  same-named but mismatched DTA is never paired automatically.
- Missing, duplicate, or malformed required BES3T metadata is rejected; no
  silent defaults are substituted.
- The BES3T DTA size must equal `XPTS × bytes-per-point`; truncation and
  trailing bytes are rejected.
- The BES3T axis must be strictly monotonic after construction from
  `XMIN`/`XWID`/`XPTS`; it is never sorted, reversed, or replaced.
- A non-finite BES3T intensity rejects the whole dataset; individual points are
  not deleted.
- DSC and DTA SHA-256 hashes are recomputed after import; a change to either
  source invalidates provenance.

## 7. Current limitations

- Only the three-column Xepr ASCII `.ASC` format and the explicitly limited
  one-dimensional real BES3T `.DSC`/`.DTA` layout are supported. PAR/SPC,
  two-/three-dimensional BES3T, complex data, `IGD` external axis files, and
  `NTUP` axes are not parsed.
- BES3T axis units currently accept only `G`; no automatic mT-to-G or other
  unit conversion is applied.
- A BES3T `DSRC` other than `EXP` produces a warning, but the program does not
  treat that field alone as proof of scientific validity.
- Xepr acquisition parameters (microwave frequency, power, modulation amplitude,
  time constant, etc.) are not read, so no unverified experimental conditions are
  annotated on the plots.
- Absorption and first-derivative spectra are not distinguished, and the signal
  type is not inferred.
- Batch processing scans only the selected directory; `--recursive` is an
  explicit option and subdirectories are not entered by default.
- Output-name collisions (for example, `a_b\C.ASC` and `a\b_C.ASC` under
  `--recursive`) cause the affected files to fail instead of being renamed
  automatically.
- `requirements.txt` lists only direct dependencies; transitive dependencies are
  not pinned (SciPy is listed as a direct dependency).
- Core validation warnings and exception text generated by `plot_asc.py` remain
  in **English** in the GUI: these strings are also written to JSON metadata and
  batch summaries as scientific records, so the GUI translates only their titles
  and descriptions.
- Chinese axis titles and plot titles in the GUI use a system CJK font
  (Microsoft YaHei preferred). If no CJK font is available, Chinese labels may
  appear as boxes; the data themselves are unaffected.
- If the language preference file `config\gui_settings.ini` cannot be created,
  the GUI still runs; only the language choice is not saved, and it returns to
  Simplified Chinese on each start.
- Smoothing changes peak height, peak width, and line shape. A smoother curve
  **does not** mean higher data quality and cannot replace scientific judgment of
  the original spectrum.
- Choosing "raw data" as the smoothing input when steps already exist changes the
  processing order (smoothing first, then the existing steps); the interface and
  JSON record the new order and issue a warning.
- Baseline windows are chosen by the user; the program does not decide whether
  they are truly baseline regions. Preview and diagnostics are only aids.
- Window input precision is 0.0001 G; the coordinates actually used are recorded
  verbatim in the processing record.
- Undo/reset does not delete already-exported processed-result files and does not
  change the original `_raw` outputs.
- The Plot Editor curve list contains only the curves actually provided by the
  current preprocessing result. Intermediate arrays such as
  "baseline-corrected but not yet smoothed" are not cached, and intermediate
  results are not recomputed just for plotting.
- The fitted baseline appears only when a baseline-correction step recorded fit
  parameters and is hidden by default. It is a fitted guide, **not an
  experimental signal**.
- Plot settings are kept only for the current program session and are lost when
  the program closes. They are not written to `config` or scientific data files.
- Plot Editor PNG files are display output. They do not replace CSV/JSON
  processing records and do not constitute new scientific analysis.
- Font sizes are set as integer points (6–40); figure dimensions are set in
  inches; the DPI limit is 1200.
- Only PNG export is available. Vector output (SVG/PDF) and batch export of plot
  settings are not provided.
- Core validation warnings, console output, and JSON logs remain in English.
  Processing-step errors and warnings are bilingual in the GUI; exported records
  remain English by design.

## 8. Running the tests

```powershell
cd "D:\EPR workflow"
.\.venv\Scripts\python.exe -m pytest -v
```

Test coverage includes normal reading, blank lines/headers, column mapping,
malformed rows, non-finite values, non-monotonic fields, missing files, no plot
for invalid data, and that source files are not modified, plus end-to-end import
of the real experimental file. Regression tests also check that CSV values match
the source point by point, integer indices are not written as floats,
non-integer indices are not rounded, metadata statistics agree with independent
recalculation, `BSA3T275.ASC` has 1024 points / 3280–3380 G / first point
400.088, and index gaps and duplicate fields are diagnosed correctly.

Batch tests cover multi-file processing, deterministic order, case-insensitive
extensions, continuing after a single-file failure, empty/missing directories,
overwrite protection, output-name collisions, summary counts and status,
unchanged source hashes, no sorting or processing, and single-file compatibility.

GUI tests cover controller logic (import, warnings, error handling, batch status,
overwrite protection, unchanged source, non-monotonic data, output-name
collisions, status mapping) and offscreen smoke tests of the PySide6 window.

Interface-language tests cover identical English/Chinese key sets, fallback for
missing keys and unknown languages, status/overall-status/field-direction
translations, synchronized updates after live switching for widgets, metadata,
plots, cursor, batch summary, and toolbar hints, no file re-read or reprocessing
during a switch, preservation of the selected sample and batch results, language
preference persistence and invalid-value fallback, Chinese/English label layout
sizes, and structural checks of control rows.

Preprocessing tests cover window validation (order, bounds, insufficient points,
overlap, shared endpoints, insufficient gap, duplicate/non-monotonic fields),
fit and correction values (known straight lines, preserved peaks, decreasing
fields, deterministic repeated calls, precision with a 1e7 offset), read-only
inputs and results, preview not committed, apply/undo/reset, processing-record
fields, and strict JSON.

Savitzky–Golay tests cover constant input remaining constant, invalid/even
windows, invalid polynomial orders, insufficient points, non-finite values,
missing SciPy, output length and field order, peak position/height/FWHM/spacing
changes for a known double peak, noise smoothing, raw/current-result inputs,
order adjustment and warning for raw input, preview/apply/undo/reset, result
caching, processing records, and data kinds.

Processed-export tests cover CSV columns and point-by-point equality, overwrite
protection, `data/raw` write protection, refusal to export previews/no-step
results/changed source files, metadata declarations (algorithm version, data
kind, output columns), English output, `_smoothed` / `_baseline_smoothed` naming,
the `difference_from_raw` column, and processing order and input source.

GUI preprocessing tests cover no windows selected by default, smoothing disabled
by default, panel enable states, three preview curves without writing files,
preview invalidation after parameter changes, cancelling a preview,
apply/undo/reset, bilingual switching preserving state without refitting or
resmoothing, translated error messages, per-file sessions, invalidation when the
source changes, export/open buttons, overwrite protection, and unchanged source
hashes through the full workflow.

Plot Editor tests cover dynamic curves based on the actual preprocessing result,
the fitted baseline hidden by default and evaluated from recorded parameters
(without refitting), visibility/name/color/line width/line style, titles and empty
labels, automatic/manual ranges and invalid-range errors, legend location, font
sizes, reset and restore-default-visibility, per-sample save/restore, language
switching without re-reading source data or reprocessing, export disabled during
an unapplied preview, error when no curve is visible, default path and overwrite
protection, exported image size/DPI, title/legend options, unchanged source hash,
and no modification of existing CSV/JSON.

BES3T tests cover valid one-dimensional real data, point counts and
point-by-point values, big-/little-endian float64/float32/integer formats, the
axis formula and endpoints, single-file/batch/CLI/GUI/processed-export
integration, DTA exclusion from dataset discovery, missing DSC/DTA, extension
case, missing/duplicate/invalid required metadata, complex and multidimensional
data, IGD/mT/A formats, zero width/too few points, truncation, trailing bytes,
non-finite values, unchanged DSC and DTA hashes, and the real `BSA3mal1h`
dataset (1024 points, 3310–3410 G, first/last values). The real-data test skips
automatically when the local sample is absent.

The Plot Editor pure logic and exporter also have separate tests. Invalid test
inputs are written to temporary directories and do not touch experimental data.
Current full-suite result: **298 passed, 1 skipped** (the skip is the
case-ambiguity companion test that cannot be constructed on Windows; the real
BES3T sample runs when present locally).

## 9. Directory structure

```text
EPR workflow\
├── .venv\
├── data\raw\            # raw experimental data (read-only)
├── Test data\           # local BES3T validation sample (not uploaded)
├── results\figures\     # output figures
├── results\tables\      # output tables
├── results\logs\        # reports and batch summaries
├── 启动 EPR Workflow.bat  # double-click to start the GUI
├── src\epr_workflow\
│   ├── __init__.py
│   ├── plot_asc.py       # ASC import / validation / plotting / export / batch
│   ├── bes3t.py          # strict BES3T .DSC/.DTA reader (no Qt)
│   ├── preprocessing.py  # baseline correction + Savitzky–Golay (NumPy/SciPy, no Qt)
│   ├── plot_settings.py  # Plot Editor settings model and shared renderer (no Qt)
│   ├── plot_export.py    # PNG plot export (standalone Agg figure, atomic write)
│   ├── processed_export.py # processed-result CSV/PNG/JSON export
│   └── gui\
│       ├── __init__.py
│       ├── i18n.py       # Chinese/English interface text (no Qt dependency)
│       ├── controller.py # GUI core logic (no Qt dependency, testable)
│       ├── preprocessing_panel.py # preprocessing panel (emits signals only)
│       ├── plot_editor_panel.py # plot-settings panel (emits signals only)
│       ├── plot_export_dialog.py # plot PNG export dialog
│       ├── mpl_canvas.py # matplotlib canvas + zoom/pan toolbar
│       ├── main_window.py# PySide6 interface
│       ├── app.py        # entry point
│       └── __main__.py   # python -m epr_workflow.gui
├── run_gui.py            # GUI launcher
├── config\gui_settings.ini  # GUI language preference (created after the first language change)
├── tests\
│   ├── test_plot_asc.py
│   ├── test_batch.py
│   ├── test_bes3t.py
│   ├── test_preprocessing.py
│   ├── test_savgol.py
│   ├── test_processed_export.py
│   ├── test_plot_settings.py
│   ├── test_plot_export.py
│   ├── test_gui_controller.py
│   ├── test_gui_i18n.py
│   ├── test_gui_preprocessing.py
│   ├── test_gui_plot_editor.py
│   ├── test_gui_bes3t.py
│   └── test_gui_widgets.py
├── conftest.py
├── requirements.txt
├── CHANGELOG.md           # release notes and version history
├── README.md              # Simplified Chinese documentation
└── README.en.md           # English documentation
```
