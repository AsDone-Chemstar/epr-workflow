"""Export processed spectra without touching the raw data.

Processed results are written to **new** files whose suffix reflects the
applied steps (``_baseline``, ``_smoothed`` or ``_baseline_smoothed``). The
original raw source files (ASC, or BES3T DSC+DTA) and the original raw
CSV/PNG/JSON exports are never modified, and output paths inside ``data/raw``
are refused.

Plotting deliberately does not call :func:`epr_workflow.plot_asc.plot_spectrum`:
that function forces the global matplotlib backend to Agg when ``show=False``,
which could interfere with the Qt canvas. A standalone ``Figure`` with an Agg
canvas is used instead, so exporting from the GUI cannot change its backend.
"""

from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from epr_workflow.plot_asc import (
    DEFAULT_DPI,
    DEFAULT_FIGSIZE,
    DEFAULT_LINEWIDTH,
    ImportResult,
    build_metadata,
    combine_source_hashes,
    guard_import_output_paths,
    verify_source_integrity,
)
from epr_workflow.preprocessing import (
    BASELINE_OPERATION,
    SAVGOL_OPERATION,
    PreprocessingError,
    PreprocessingResult,
    build_preprocessing_record,
    processing_data_kind,
)

#: Baseline-only CSV columns (kept unchanged from phase 1).
PROCESSED_COLUMNS = [
    "index",
    "field_G",
    "intensity_raw",
    "intensity_corrected",
    "baseline_removed",
]

#: Columns used when smoothing is part of the history. ``difference_from_raw``
#: is the total change from raw to processed, not a fitted baseline.
SMOOTHED_COLUMNS = [
    "index",
    "field_G",
    "intensity_raw",
    "intensity_corrected",
    "difference_from_raw",
]

_DATA_KIND_SUFFIX = {
    "baseline_corrected": "baseline",
    "smoothed": "smoothed",
    "baseline_corrected_and_smoothed": "baseline_smoothed",
    "none": "processed",
}


def _timestamp_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_processed_paths(
    stem: str,
    output_base: str | Path,
    *,
    data_kind: str = "baseline_corrected",
) -> dict[str, Path]:
    """Return the CSV/PNG/JSON targets for one processed export."""
    output_base = Path(output_base)
    suffix = _DATA_KIND_SUFFIX.get(data_kind, "processed")
    return {
        "csv": output_base / "tables" / f"{stem}_{suffix}.csv",
        "figure": output_base / "figures" / f"{stem}_{suffix}.png",
        "metadata_json": output_base / "logs" / f"{stem}_{suffix}_metadata.json",
    }


def _plot_processed(
    output_path: Path,
    *,
    title: str,
    field: np.ndarray,
    raw: np.ndarray,
    corrected: np.ndarray,
    difference: np.ndarray,
    data_kind: str,
) -> None:
    has_smoothing = data_kind in ("smoothed", "baseline_corrected_and_smoothed")
    figure = Figure(figsize=DEFAULT_FIGSIZE)
    FigureCanvasAgg(figure)  # attach a non-interactive canvas, no pyplot state
    axes = figure.add_subplot(111)
    axes.plot(
        field, raw, color="#8c8c8c", linewidth=0.8, linestyle="--", label="Raw"
    )
    axes.plot(
        field,
        difference,
        color="#c55a11",
        linewidth=0.8,
        linestyle=":",
        label=(
            "Difference (raw - processed)"
            if has_smoothing
            else "Removed baseline"
        ),
    )
    axes.plot(
        field,
        corrected,
        color="#1f4e79",
        linewidth=DEFAULT_LINEWIDTH,
        label=(
            "Processed"
            if data_kind == "baseline_corrected_and_smoothed"
            else ("Smoothed" if has_smoothing else "Corrected")
        ),
    )
    axes.set_xlabel("Magnetic field (G)")
    if data_kind == "baseline_corrected":
        ylabel = "Intensity (original units, baseline corrected)"
    elif data_kind == "smoothed":
        ylabel = "Intensity (original units, smoothed)"
    else:
        ylabel = "Intensity (original units, baseline corrected and smoothed)"
    axes.set_ylabel(ylabel)
    axes.set_title(title)
    axes.grid(True, which="major", color="#b0b0b0", alpha=0.35, linewidth=0.6)
    axes.tick_params(direction="out")
    axes.legend(loc="best", fontsize=8, frameon=False)
    figure.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=DEFAULT_DPI)


def _title_for(stem: str, data_kind: str) -> str:
    titles = {
        "baseline_corrected": "Linear Baseline Corrected CW-EPR Spectrum",
        "smoothed": "Savitzky-Golay Smoothed CW-EPR Spectrum",
        "baseline_corrected_and_smoothed": (
            "Baseline Corrected and Savitzky-Golay Smoothed CW-EPR Spectrum"
        ),
    }
    return f"{stem} - {titles.get(data_kind, 'Processed CW-EPR Spectrum')}"


def _processed_run_record(
    result: PreprocessingResult, import_result: ImportResult
) -> dict[str, Any]:
    operations = result.operations
    data_kind = processing_data_kind(result.steps)
    if import_result.source_format == "BES3T":
        description = (
            "Processed export: the listed preprocessing steps were applied to "
            "an in-memory copy and written to new files. The raw BES3T .DSC/"
            ".DTA pair and the original raw exports were not modified."
        )
    else:
        description = (
            "Processed export: the listed preprocessing steps were applied to "
            "an in-memory copy and written to new files. The raw ASC file and "
            "the original raw exports were not modified."
        )
    return {
        "applied_in_this_run": {
            "smoothing": SAVGOL_OPERATION in operations,
            "baseline_correction": BASELINE_OPERATION in operations,
            "normalisation": False,
            "field_axis_reversal": False,
        },
        "data_kind": data_kind,
        "preprocessing_step_order": list(operations),
        "plot": {
            "figsize_inch": list(DEFAULT_FIGSIZE),
            "dpi": DEFAULT_DPI,
            "line_width": DEFAULT_LINEWIDTH,
        },
        "description": description,
    }


def _processed_assumptions(
    import_result: ImportResult, result: PreprocessingResult
) -> list[str]:
    operations = result.operations
    if import_result.source_format == "BES3T":
        assumptions = list(import_result.format_assumptions)
    else:
        assumptions = [
            "The file is a whitespace-separated Xepr ASCII export with a header "
            "containing 'index', 'Field [G]' and 'Intensity []'.",
            "Column 1 is a row index and is not a physical quantity.",
            "Column 2 is magnetic field in Gauss (G).",
            "Column 3 intensity has no documented unit; values are reported in "
            "original (arbitrary) units.",
        ]
    if BASELINE_OPERATION in operations:
        assumptions.extend(
            [
                "The intensity baseline is additive in those units, and one "
                "straight line represents it across the displayed field range.",
                "The selected baseline windows contain baseline only; this is "
                "the user's scientific judgement and is not verified by the "
                "software.",
            ]
        )
    if SAVGOL_OPERATION in operations:
        assumptions.extend(
            [
                "Savitzky-Golay smoothing fits a local polynomial over a "
                "fixed-width window; it can change peak height, peak width and "
                "line shape.",
                "Smoothing is not evidence of improved data quality and does "
                "not remove a physically modelled noise component.",
            ]
        )
    assumptions.append(
        "No normalisation, interpolation, clipping, outlier removal or global "
        "signal curve fitting was applied."
    )
    return assumptions


def _output_statistics(values: np.ndarray) -> dict[str, float]:
    return {
        "min": float(values.min()),
        "max": float(values.max()),
        "mean": float(values.mean()),
        "std_ddof1": float(values.std(ddof=1)) if values.size > 1 else 0.0,
    }


def export_processed(
    *,
    import_result: ImportResult,
    result: PreprocessingResult,
    output_base: str | Path,
    overwrite: bool = False,
) -> dict[str, Path]:
    """Write CSV, PNG and JSON for an applied preprocessing result.

    Supports baseline correction, Savitzky-Golay smoothing and their
    combination. Raises :class:`FileExistsError` when outputs exist and
    ``overwrite`` is false, :class:`ValueError` when a target is inside
    ``data/raw`` or over the source file, and :class:`PreprocessingError` for
    previews, missing steps, mismatched data, or a source file that changed
    after import.
    """
    if result.is_preview:
        raise PreprocessingError(
            "Preview results cannot be exported; apply the step first.",
            code="preview_export",
        )
    if not result.steps:
        raise PreprocessingError(
            "No preprocessing steps have been applied.", code="no_steps"
        )

    source = Path(import_result.source)
    if source.resolve() != Path(result.source).resolve():
        raise PreprocessingError(
            "The processed result does not belong to the imported file.",
            code="data_mismatch",
        )

    expected_sha = import_result.sha256
    source_unchanged, source_hashes_after = verify_source_integrity(
        import_result
    )
    if not source_unchanged:
        try:
            actual_sha = combine_source_hashes(
                import_result.source_format, source_hashes_after
            )
        except ValueError:
            actual_sha = str(source_hashes_after)
        raise PreprocessingError(
            "The source file(s) changed after import (SHA-256 mismatch); "
            "exporting processed results was refused.",
            code="source_changed",
            context={"expected": expected_sha, "actual": actual_sha},
        )
    if result.source_sha256 and result.source_sha256 != expected_sha:
        raise PreprocessingError(
            "The processed result does not match the imported data "
            "(SHA-256 mismatch).",
            code="data_mismatch",
        )

    field = import_result.data["field_G"].to_numpy()
    if field.shape != result.field_G.shape or not np.array_equal(
        field, result.field_G
    ):
        raise PreprocessingError(
            "The processed result does not match the imported field "
            "coordinates.",
            code="data_mismatch",
        )

    data_kind = processing_data_kind(result.steps)
    has_smoothing = data_kind in (
        "smoothed",
        "baseline_corrected_and_smoothed",
    )
    columns = list(SMOOTHED_COLUMNS if has_smoothing else PROCESSED_COLUMNS)
    if import_result.source_format != "ASC":
        columns.append("source_format")
    paths = resolve_processed_paths(
        import_result.source.stem, output_base, data_kind=data_kind
    )
    guard_import_output_paths(import_result, paths)

    existing = [str(path) for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Output file(s) already exist: "
            + ", ".join(existing)
            + ". Use --overwrite to replace them, or choose another --output-dir."
        )

    difference_column = (
        "difference_from_raw" if has_smoothing else "baseline_removed"
    )
    frame_data = {
        "index": import_result.data["index"].to_numpy(),
        "field_G": field,
        "intensity_raw": result.intensity_raw,
        "intensity_corrected": result.intensity_processed,
        difference_column: result.difference,
    }
    if import_result.source_format != "ASC":
        frame_data["source_format"] = import_result.source_format
    frame = pd.DataFrame(frame_data)[columns]

    paths["csv"].parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(paths["csv"], index=False)

    _plot_processed(
        paths["figure"],
        title=_title_for(import_result.source.stem, data_kind),
        field=field,
        raw=result.intensity_raw,
        corrected=result.intensity_processed,
        difference=result.difference,
        data_kind=data_kind,
    )

    source_unchanged, source_hashes_after = verify_source_integrity(
        import_result
    )
    outputs = {key: str(path.resolve()) for key, path in paths.items()}
    metadata = build_metadata(
        import_result,
        raw_file_unchanged=source_unchanged,
        outputs=outputs,
        processing=_processed_run_record(result, import_result),
        source_hashes_after=source_hashes_after,
    )
    metadata["assumptions"] = _processed_assumptions(import_result, result)
    metadata["data_kind"] = data_kind
    preprocessing_record = build_preprocessing_record(result)
    if not preprocessing_record["source_sha256"]:
        preprocessing_record["source_sha256"] = expected_sha
        for step_record in preprocessing_record["steps"]:
            step_record["source_sha256"] = expected_sha
    preprocessing_record["exported_at_utc"] = _timestamp_utc()
    preprocessing_record["output_columns"] = list(columns)
    preprocessing_record["raw_values_included_in_csv"] = True
    preprocessing_record["output_statistics"] = {
        "intensity_raw": _output_statistics(result.intensity_raw),
        "intensity_corrected": _output_statistics(result.intensity_processed),
        difference_column: _output_statistics(result.difference),
    }
    export_software = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }
    try:
        import scipy

        export_software["scipy"] = scipy.__version__
    except Exception:
        export_software["scipy"] = "not installed"
    preprocessing_record["export_software"] = export_software
    metadata["preprocessing"] = preprocessing_record

    paths["metadata_json"].parent.mkdir(parents=True, exist_ok=True)
    paths["metadata_json"].write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return paths
