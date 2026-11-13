"""User-initiated FTIR v1.0 CSV/JSON/PNG export.

The module is application-layer code because PNG rendering uses Matplotlib,
while the FTIR technique package is intentionally Qt/Matplotlib-free. CSV and
JSON rendering is still pure data code and uses the generic core export and
path-safety helpers.

Export never processes, sorts, reverses, interpolates or otherwise modifies a
source spectrum. Processed output is taken from an existing
:class:`ProcessedSpectrum`; difference output is taken from an existing
:class:`DifferenceResult`.
"""

from __future__ import annotations

import csv as _csv
import io
import math
import os
import platform
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
import scipy
from matplotlib import font_manager
from matplotlib.figure import Figure

from spectralab.core.errors import ExportSerializationError
from spectralab.core.export import (
    atomic_write_bytes,
    atomic_write_text,
    build_provenance_document,
    check_output_path,
    json_compatible,
    render_document_json,
)
from spectralab.core.model import Axis1D, Signal1D, Spectrum1D
from spectralab.core.plotting import (
    PlotConfig,
    format_axis_label,
    format_signal_label,
    plot_spectrum,
)
from spectralab.core.processing import ProcessedSpectrum, ProcessingOperation
from spectralab.techniques.ftir import DifferenceResult, PeakDetectionResult

FTIR_EXPORT_SCHEMA_ID = "spectralab.ftir.export"
FTIR_EXPORT_SCHEMA_VERSION = 1
FTIR_DIFFERENCE_EXPORT_SCHEMA_ID = "spectralab.ftir.difference_export"
FTIR_DIFFERENCE_EXPORT_SCHEMA_VERSION = 1
EXPORT_STATUS = "initial"
NUMERIC_SERIALIZATION = "python-repr-shortest-roundtrip-float64"
CSV_COLUMNS = ("x", "y")
DIFFERENCE_CSV_COLUMNS = ("x", "a", "b", "difference")


@dataclass(frozen=True)
class _ResolvedSpectrum:
    dataset: Spectrum1D
    axis: Axis1D
    signal: Signal1D
    selection: str
    history: tuple[ProcessingOperation, ...]


def _now_utc() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _timestamp(value: str | None) -> str:
    if value is None:
        return _now_utc()
    if not isinstance(value, str) or not value.strip():
        raise ExportSerializationError(
            "exported_at must be non-empty ISO-8601 text or None.",
            code="invalid_export_timestamp",
            context={"value": repr(value)},
        )
    return value


@lru_cache(maxsize=1)
def _font_family() -> tuple[str, ...]:
    """Prefer an installed CJK-capable font without requiring a new package."""
    available = {item.name for item in font_manager.fontManager.ttflist}
    for candidate in (
        "Microsoft YaHei",
        "SimHei",
        "DengXian",
        "SimSun",
        "Noto Sans CJK SC",
    ):
        if candidate in available:
            return (candidate, "DejaVu Sans")
    return ("DejaVu Sans",)


def software_versions() -> dict[str, str]:
    """Return actual runtime versions; never invent a package version."""
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "matplotlib": matplotlib.__version__,
        "spectralab": "unversioned",
    }


def _resolve_spectrum(source: Spectrum1D | ProcessedSpectrum) -> _ResolvedSpectrum:
    if isinstance(source, Spectrum1D):
        return _ResolvedSpectrum(
            dataset=source,
            axis=source.axis,
            signal=source.raw_signal,
            selection="raw",
            history=(),
        )
    if isinstance(source, ProcessedSpectrum):
        return _ResolvedSpectrum(
            dataset=source.source,
            axis=source.axis,
            signal=source.signal,
            selection="processed",
            history=tuple(source.history),
        )
    raise ExportSerializationError(
        "FTIR export requires a Spectrum1D or ProcessedSpectrum.",
        code="invalid_export_source",
        context={"type": type(source).__name__},
    )


def _protected_paths(
    spectra: Sequence[Spectrum1D],
) -> list[Path]:
    paths: list[Path] = []
    for spectrum in spectra:
        if not isinstance(spectrum, Spectrum1D):
            raise ExportSerializationError(
                "Protected export sources must be Spectrum1D objects.",
                code="invalid_export_source",
                context={"type": type(spectrum).__name__},
            )
        paths.extend(source.path for source in spectrum.provenance.source_files)
    return paths


def _same_output_path(first: Path, second: Path) -> bool:
    try:
        return os.path.normcase(str(first.resolve(strict=False))) == (
            os.path.normcase(str(second.resolve(strict=False)))
        )
    except OSError:
        return False


def _axis_document(axis: Axis1D, *, include_values: bool) -> dict[str, Any]:
    document: dict[str, Any] = {
        "quantity": axis.quantity,
        "unit": axis.unit,
        "name": axis.name,
        "direction": axis.direction,
        "point_count": axis.point_count,
        "metadata_source": axis.metadata_source,
        "missing_reason": axis.missing_reason,
    }
    if include_values:
        document["values"] = json_compatible(axis.values, path="axis.values")
    return document


def _signal_document(signal: Signal1D, *, include_values: bool) -> dict[str, Any]:
    document: dict[str, Any] = {
        "semantics": signal.semantics,
        "unit": signal.unit,
        "name": signal.name,
        "point_count": signal.point_count,
        "metadata_source": signal.metadata_source,
        "missing_reason": signal.missing_reason,
    }
    if include_values:
        document["values"] = json_compatible(
            signal.values,
            path="signal.values",
        )
    return document


def _metadata_document(spectrum: Spectrum1D) -> dict[str, Any]:
    metadata = spectrum.metadata
    return json_compatible(
        {
            "technique": metadata.technique,
            "title": metadata.title,
            "instrument": dict(metadata.instrument),
            "acquisition": dict(metadata.acquisition),
            "sample": dict(metadata.sample),
            "technique_metadata": dict(metadata.technique_metadata),
            "extra": dict(metadata.extra),
            "unknown_fields": list(metadata.unknown_fields),
            "metadata_origin": dict(metadata.metadata_origin),
        },
        path="metadata",
    )


def _operation_record(record: ProcessingOperation) -> dict[str, Any]:
    return json_compatible(
        {
            "order": record.order,
            "operation_id": record.operation_id,
            "name": record.name,
            "technique": record.technique,
            "version": record.version,
            "parameters": dict(record.parameters),
            "input_state_id": record.input_state_id,
            "output_state_id": record.output_state_id,
            "input_dataset_id": record.input_dataset_id,
            "changes_axis": record.changes_axis,
            "axis_change_description": record.axis_change_description,
            "changes_signal_semantics": record.changes_signal_semantics,
            "changes_signal_unit": record.changes_signal_unit,
            "signal_change_description": record.signal_change_description,
            "warnings": list(record.warnings),
            "assumptions": list(record.assumptions),
            "diagnostics": dict(record.diagnostics),
        },
        path="processing.history",
    )


def _processing_history(
    history: Sequence[ProcessingOperation],
) -> list[dict[str, Any]]:
    return [_operation_record(record) for record in history]


def _peak_document(
    result: PeakDetectionResult | None,
    *,
    dataset_id: str,
    source: str,
) -> dict[str, Any] | None:
    if result is None:
        return None
    if not isinstance(result, PeakDetectionResult):
        raise ExportSerializationError(
            "peak_result must be a PeakDetectionResult or None.",
            code="invalid_peak_result",
            context={"type": type(result).__name__},
        )
    if result.dataset_id != dataset_id:
        raise ExportSerializationError(
            "The peak result belongs to a different dataset.",
            code="peak_result_dataset_mismatch",
            context={
                "expected": dataset_id,
                "actual": result.dataset_id,
            },
        )
    if result.source != source:
        raise ExportSerializationError(
            "The peak result belongs to a different source selection.",
            code="peak_result_source_mismatch",
            context={
                "expected": source,
                "actual": result.source,
            },
        )
    return result.as_dict()


def build_ftir_spectrum_document(
    source: Spectrum1D | ProcessedSpectrum,
    *,
    include_values: bool = True,
    peak_result: PeakDetectionResult | None = None,
    exported_at: str | None = None,
    export_format: str = "json",
) -> dict[str, Any]:
    """Build the single-spectrum FTIR export document without writing files."""
    resolved = _resolve_spectrum(source)
    if not isinstance(include_values, bool):
        raise ExportSerializationError(
            "include_values must be a boolean.",
            code="invalid_export_option",
        )
    if export_format not in ("json", "csv_metadata"):
        raise ExportSerializationError(
            "export_format must be 'json' or 'csv_metadata'.",
            code="invalid_export_option",
        )
    document = {
        "schema_id": FTIR_EXPORT_SCHEMA_ID,
        "schema_version": FTIR_EXPORT_SCHEMA_VERSION,
        "schema_status": EXPORT_STATUS,
        "export": {
            "format": export_format,
            "values_included": include_values,
            "point_order": "preserved",
            "source_selection": resolved.selection,
            "source_dataset_id": resolved.dataset.dataset_id,
            "processing_applied": [
                record.operation_id for record in resolved.history
            ],
            "exported_at_utc": _timestamp(exported_at),
            "numeric_serialization": NUMERIC_SERIALIZATION,
            "software_versions": software_versions(),
        },
        "dataset": {
            "dataset_id": resolved.dataset.dataset_id,
            "technique": resolved.dataset.technique,
            "source_format": resolved.dataset.source_format,
            "point_count": resolved.axis.point_count,
        },
        "axis": _axis_document(resolved.axis, include_values=include_values),
        "signal": _signal_document(resolved.signal, include_values=include_values),
        "metadata": _metadata_document(resolved.dataset),
        "provenance": build_provenance_document(resolved.dataset),
        "processing": {
            "selection": resolved.selection,
            "history": _processing_history(resolved.history),
            "operation_ids": [
                record.operation_id for record in resolved.history
            ],
        },
        "peak_detection": _peak_document(
            peak_result,
            dataset_id=resolved.dataset.dataset_id,
            source=resolved.selection,
        ),
    }
    return json_compatible(document, path="document")


def render_ftir_spectrum_json(
    source: Spectrum1D | ProcessedSpectrum,
    *,
    peak_result: PeakDetectionResult | None = None,
    exported_at: str | None = None,
) -> str:
    return render_document_json(
        build_ftir_spectrum_document(
            source,
            peak_result=peak_result,
            exported_at=exported_at,
        )
    )


def _format_float(value: Any, *, path: str) -> str:
    number = float(value)
    if not math.isfinite(number):
        raise ExportSerializationError(
            f"Non-finite value at {path}; export refuses to emit NaN or "
            "Infinity.",
            code="nonfinite_value",
            context={"path": path, "value": repr(number)},
        )
    return repr(number)


def render_xy_csv(
    x_values: Sequence[float],
    columns: Sequence[Sequence[float]],
    *,
    header: Sequence[str],
) -> str:
    """Render numeric CSV with exact point order and shortest round-trip text."""
    if len(header) != 1 + len(columns):
        raise ExportSerializationError(
            "CSV header length does not match the data columns.",
            code="invalid_csv_columns",
        )
    lengths = {len(x_values)}
    lengths.update(len(column) for column in columns)
    if len(lengths) != 1:
        raise ExportSerializationError(
            "CSV columns have different lengths.",
            code="invalid_csv_columns",
            context={"lengths": sorted(lengths)},
        )
    output = io.StringIO(newline="")
    writer = _csv.writer(output, lineterminator="\n")
    writer.writerow(header)
    for index in range(len(x_values)):
        row = [_format_float(x_values[index], path=f"axis.values[{index}]")]
        for column_index, column in enumerate(columns):
            row.append(
                _format_float(
                    column[index],
                    path=f"columns[{column_index}][{index}]",
                )
            )
        writer.writerow(row)
    return output.getvalue()


def render_ftir_spectrum_csv(
    source: Spectrum1D | ProcessedSpectrum,
) -> str:
    resolved = _resolve_spectrum(source)
    return render_xy_csv(
        resolved.axis.values,
        (resolved.signal.values,),
        header=CSV_COLUMNS,
    )


def build_ftir_spectrum_csv_metadata(
    source: Spectrum1D | ProcessedSpectrum,
    *,
    peak_result: PeakDetectionResult | None = None,
    exported_at: str | None = None,
) -> dict[str, Any]:
    document = build_ftir_spectrum_document(
        source,
        include_values=False,
        peak_result=peak_result,
        exported_at=exported_at,
        export_format="csv_metadata",
    )
    document["csv"] = {
        "columns": list(CSV_COLUMNS),
        "delimiter": ",",
        "encoding": "utf-8",
        "line_ending": "LF",
        "data_values": "stored in the sibling CSV data file",
        "numeric_format": NUMERIC_SERIALIZATION,
        "source_selection": document["export"]["source_selection"],
    }
    return json_compatible(document, path="document")


def export_ftir_spectrum_csv(
    source: Spectrum1D | ProcessedSpectrum,
    output_path: str | Path,
    *,
    overwrite: bool = False,
    metadata_path: str | Path | None = None,
    peak_result: PeakDetectionResult | None = None,
    exported_at: str | None = None,
) -> dict[str, Path]:
    resolved = _resolve_spectrum(source)
    csv_target = Path(output_path)
    metadata_target = (
        csv_target.with_name(f"{csv_target.stem}_metadata.json")
        if metadata_path is None
        else Path(metadata_path)
    )
    if _same_output_path(csv_target, metadata_target):
        raise ExportSerializationError(
            "CSV and metadata paths must be different.",
            code="duplicate_output_path",
            context={"path": str(csv_target)},
        )
    protected = _protected_paths((resolved.dataset,))
    check_output_path(
        csv_target,
        overwrite=overwrite,
        protected_paths=protected,
    )
    check_output_path(
        metadata_target,
        overwrite=overwrite,
        protected_paths=protected,
    )
    csv_text = render_ftir_spectrum_csv(source)
    metadata_text = render_document_json(
        build_ftir_spectrum_csv_metadata(
            source,
            peak_result=peak_result,
            exported_at=exported_at,
        )
    )
    written_metadata = atomic_write_text(
        metadata_target,
        metadata_text,
        overwrite=overwrite,
        protected_paths=protected,
    )
    written_csv = atomic_write_text(
        csv_target,
        csv_text,
        overwrite=overwrite,
        protected_paths=protected,
    )
    return {"csv": written_csv, "metadata": written_metadata}


def export_ftir_spectrum_json(
    source: Spectrum1D | ProcessedSpectrum,
    output_path: str | Path,
    *,
    overwrite: bool = False,
    peak_result: PeakDetectionResult | None = None,
    exported_at: str | None = None,
) -> Path:
    resolved = _resolve_spectrum(source)
    protected = _protected_paths((resolved.dataset,))
    target = check_output_path(
        output_path,
        overwrite=overwrite,
        protected_paths=protected,
    )
    text = render_ftir_spectrum_json(
        source,
        peak_result=peak_result,
        exported_at=exported_at,
    )
    return atomic_write_text(
        target,
        text,
        overwrite=overwrite,
        protected_paths=protected,
    )


def _save_figure_png(
    figure: Figure,
    output_path: str | Path,
    *,
    overwrite: bool,
    protected: Sequence[Path],
    dpi: int,
) -> Path:
    if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi < 50:
        raise ExportSerializationError(
            "dpi must be an integer of at least 50.",
            code="invalid_dpi",
            context={"dpi": repr(dpi)},
        )
    buffer = io.BytesIO()
    with matplotlib.rc_context(
        {
            "font.sans-serif": list(_font_family()),
            "axes.unicode_minus": False,
        }
    ):
        figure.savefig(
            buffer,
            format="png",
            dpi=dpi,
            bbox_inches="tight",
            facecolor="white",
        )
    payload = buffer.getvalue()
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ExportSerializationError(
            "Matplotlib did not produce a valid PNG payload.",
            code="png_serialization",
        )
    target = check_output_path(
        output_path,
        overwrite=overwrite,
        protected_paths=protected,
    )
    return atomic_write_bytes(
        target,
        payload,
        overwrite=overwrite,
        protected_paths=protected,
    )


def export_ftir_spectrum_png(
    source: Spectrum1D | ProcessedSpectrum,
    output_path: str | Path,
    *,
    overwrite: bool = False,
    title: str | None = None,
    dpi: int = 300,
    width_in: float = 7.0,
    height_in: float = 4.5,
) -> Path:
    resolved = _resolve_spectrum(source)
    protected = _protected_paths((resolved.dataset,))
    figure = Figure(figsize=(width_in, height_in), dpi=100)
    axes = figure.add_subplot(111)
    config = PlotConfig(
        title=title
        or resolved.dataset.metadata.title
        or resolved.dataset.dataset_id,
        xlabel=format_axis_label(resolved.axis),
        ylabel=format_signal_label(resolved.signal),
        legend_visible=False,
    )
    if resolved.selection == "processed":
        plot_spectrum(axes, source, config, include_raw=False)  # type: ignore[arg-type]
    else:
        plot_spectrum(axes, resolved.dataset, config)
    return _save_figure_png(
        figure,
        output_path,
        overwrite=overwrite,
        protected=protected,
        dpi=dpi,
    )


# ---------------------------------------------------------------------------
# Difference export
# ---------------------------------------------------------------------------
def _validate_difference_sources(
    result: DifferenceResult,
    source_a: Spectrum1D,
    source_b: Spectrum1D,
) -> None:
    if not isinstance(result, DifferenceResult):
        raise ExportSerializationError(
            "Difference export requires a DifferenceResult.",
            code="invalid_difference_result",
            context={"type": type(result).__name__},
        )
    for label, source, expected in (
        ("A", source_a, result.dataset_a_id),
        ("B", source_b, result.dataset_b_id),
    ):
        if not isinstance(source, Spectrum1D):
            raise ExportSerializationError(
                f"Difference source {label} must be a Spectrum1D.",
                code="invalid_export_source",
            )
        if source.dataset_id != expected:
            raise ExportSerializationError(
                f"Difference source {label} does not match the result.",
                code="difference_source_mismatch",
                context={
                    "expected": expected,
                    "actual": source.dataset_id,
                },
            )


def _source_export_document(
    source: Spectrum1D,
    *,
    selection: str,
    operation_ids: Sequence[str],
    processed: ProcessedSpectrum | None,
    peak_result: PeakDetectionResult | None,
) -> dict[str, Any]:
    if selection not in ("raw", "processed"):
        raise ExportSerializationError(
            "Difference source selection must be 'raw' or 'processed'.",
            code="invalid_export_source_selection",
            context={"selection": selection},
        )
    if selection == "raw" and processed is not None:
        raise ExportSerializationError(
            "A raw source selection must not include a ProcessedSpectrum.",
            code="difference_source_mismatch",
        )
    if selection == "processed" and processed is None:
        processing_history: list[dict[str, Any]] = []
        processed_axis = None
        processed_signal = None
    elif processed is not None:
        if processed.source.dataset_id != source.dataset_id:
            raise ExportSerializationError(
                "Processed source does not belong to the raw dataset.",
                code="difference_source_mismatch",
                context={
                    "expected": source.dataset_id,
                    "actual": processed.source.dataset_id,
                },
            )
        actual_operations = tuple(
            record.operation_id for record in processed.history
        )
        if actual_operations != tuple(operation_ids):
            raise ExportSerializationError(
                "Processed source history does not match the recorded "
                "difference provenance.",
                code="difference_history_mismatch",
                context={
                    "expected": list(operation_ids),
                    "actual": list(actual_operations),
                },
            )
        processing_history = _processing_history(processed.history)
        processed_axis = _axis_document(processed.axis, include_values=False)
        processed_signal = _signal_document(
            processed.signal,
            include_values=False,
        )
    else:
        processing_history = []
        processed_axis = None
        processed_signal = None
    return {
        "dataset_id": source.dataset_id,
        "selection": selection,
        "operation_ids": list(operation_ids),
        "processing_history": processing_history,
        "processed_axis": processed_axis,
        "processed_signal": processed_signal,
        "metadata": _metadata_document(source),
        "provenance": build_provenance_document(source),
        "peak_detection": _peak_document(
            peak_result,
            dataset_id=source.dataset_id,
            source=selection,
        ),
    }


def build_ftir_difference_document(
    result: DifferenceResult,
    *,
    source_a: Spectrum1D,
    source_b: Spectrum1D,
    processed_a: ProcessedSpectrum | None = None,
    processed_b: ProcessedSpectrum | None = None,
    peak_result_a: PeakDetectionResult | None = None,
    peak_result_b: PeakDetectionResult | None = None,
    include_values: bool = True,
    exported_at: str | None = None,
    result_role: str | None = None,
    export_format: str = "json",
) -> dict[str, Any]:
    """Build a dedicated difference export document with both sources."""
    _validate_difference_sources(result, source_a, source_b)
    if result.source_a == "processed" and processed_a is None:
        raise ExportSerializationError(
            "Processed source A was selected but no ProcessedSpectrum was "
            "supplied.",
            code="missing_processed_source",
        )
    if result.source_b == "processed" and processed_b is None:
        raise ExportSerializationError(
            "Processed source B was selected but no ProcessedSpectrum was "
            "supplied.",
            code="missing_processed_source",
        )
    if not isinstance(include_values, bool):
        raise ExportSerializationError(
            "include_values must be a boolean.",
            code="invalid_export_option",
        )
    if export_format not in ("json", "csv_metadata"):
        raise ExportSerializationError(
            "export_format must be 'json' or 'csv_metadata'.",
            code="invalid_export_option",
        )
    if result_role not in (None, "preview", "applied"):
        raise ExportSerializationError(
            "result_role must be 'preview', 'applied' or None.",
            code="invalid_export_option",
        )

    analysis = result.as_dict()
    difference_values: dict[str, Any] = {}
    if include_values:
        difference_values = {
            "x_values": json_compatible(
                result.axis.values,
                path="difference.x_values",
            ),
            "a_values": json_compatible(
                result.aligned_a_signal.values,
                path="difference.a_values",
            ),
            "b_values": json_compatible(
                result.aligned_b_signal.values,
                path="difference.b_values",
            ),
            "difference_values": json_compatible(
                result.signal.values,
                path="difference.difference_values",
            ),
        }
    document = {
        "schema_id": FTIR_DIFFERENCE_EXPORT_SCHEMA_ID,
        "schema_version": FTIR_DIFFERENCE_EXPORT_SCHEMA_VERSION,
        "schema_status": EXPORT_STATUS,
        "export": {
            "format": export_format,
            "values_included": include_values,
            "point_order": "preserved",
            "operation": "A - B",
            "axis_match": result.axis_match,
            "result_role": result_role,
            "exported_at_utc": _timestamp(exported_at),
            "numeric_serialization": NUMERIC_SERIALIZATION,
            "software_versions": software_versions(),
        },
        "difference": {
            "analysis": analysis,
            "point_count": result.point_count,
            **difference_values,
        },
        "sources": {
            "a": _source_export_document(
                source_a,
                selection=result.source_a,
                operation_ids=result.source_operation_history_a,
                processed=processed_a,
                peak_result=peak_result_a,
            ),
            "b": _source_export_document(
                source_b,
                selection=result.source_b,
                operation_ids=result.source_operation_history_b,
                processed=processed_b,
                peak_result=peak_result_b,
            ),
        },
        "interpolation": (
            None
            if result.interpolation is None
            else {
                **result.interpolation.as_dict(),
                "b_original_point_count": source_b.point_count,
            }
        ),
    }
    return json_compatible(document, path="document")


def render_ftir_difference_json(
    result: DifferenceResult,
    *,
    source_a: Spectrum1D,
    source_b: Spectrum1D,
    processed_a: ProcessedSpectrum | None = None,
    processed_b: ProcessedSpectrum | None = None,
    peak_result_a: PeakDetectionResult | None = None,
    peak_result_b: PeakDetectionResult | None = None,
    exported_at: str | None = None,
    result_role: str | None = None,
) -> str:
    return render_document_json(
        build_ftir_difference_document(
            result,
            source_a=source_a,
            source_b=source_b,
            processed_a=processed_a,
            processed_b=processed_b,
            peak_result_a=peak_result_a,
            peak_result_b=peak_result_b,
            exported_at=exported_at,
            result_role=result_role,
        )
    )


def render_ftir_difference_csv(result: DifferenceResult) -> str:
    if not isinstance(result, DifferenceResult):
        raise ExportSerializationError(
            "Difference CSV export requires a DifferenceResult.",
            code="invalid_difference_result",
        )
    return render_xy_csv(
        result.axis.values,
        (
            result.aligned_a_signal.values,
            result.aligned_b_signal.values,
            result.signal.values,
        ),
        header=DIFFERENCE_CSV_COLUMNS,
    )


def build_ftir_difference_csv_metadata(
    result: DifferenceResult,
    *,
    source_a: Spectrum1D,
    source_b: Spectrum1D,
    processed_a: ProcessedSpectrum | None = None,
    processed_b: ProcessedSpectrum | None = None,
    peak_result_a: PeakDetectionResult | None = None,
    peak_result_b: PeakDetectionResult | None = None,
    exported_at: str | None = None,
    result_role: str | None = None,
) -> dict[str, Any]:
    document = build_ftir_difference_document(
        result,
        source_a=source_a,
        source_b=source_b,
        processed_a=processed_a,
        processed_b=processed_b,
        peak_result_a=peak_result_a,
        peak_result_b=peak_result_b,
        include_values=False,
        exported_at=exported_at,
        result_role=result_role,
        export_format="csv_metadata",
    )
    document["csv"] = {
        "columns": list(DIFFERENCE_CSV_COLUMNS),
        "delimiter": ",",
        "encoding": "utf-8",
        "line_ending": "LF",
        "numeric_format": NUMERIC_SERIALIZATION,
        "b_column": (
            "linear interpolation of B onto the A target axis"
            if result.interpolation is not None
            else "B on the exact common X axis"
        ),
        "b_original_point_count": source_b.point_count,
        "data_values": "stored in the sibling CSV data file",
    }
    return json_compatible(document, path="document")


def export_ftir_difference_csv(
    result: DifferenceResult,
    output_path: str | Path,
    *,
    source_a: Spectrum1D,
    source_b: Spectrum1D,
    processed_a: ProcessedSpectrum | None = None,
    processed_b: ProcessedSpectrum | None = None,
    peak_result_a: PeakDetectionResult | None = None,
    peak_result_b: PeakDetectionResult | None = None,
    overwrite: bool = False,
    metadata_path: str | Path | None = None,
    exported_at: str | None = None,
    result_role: str | None = None,
) -> dict[str, Path]:
    _validate_difference_sources(result, source_a, source_b)
    csv_target = Path(output_path)
    metadata_target = (
        csv_target.with_name(f"{csv_target.stem}_metadata.json")
        if metadata_path is None
        else Path(metadata_path)
    )
    if _same_output_path(csv_target, metadata_target):
        raise ExportSerializationError(
            "CSV and metadata paths must be different.",
            code="duplicate_output_path",
            context={"path": str(csv_target)},
        )
    protected = _protected_paths((source_a, source_b))
    check_output_path(
        csv_target,
        overwrite=overwrite,
        protected_paths=protected,
    )
    check_output_path(
        metadata_target,
        overwrite=overwrite,
        protected_paths=protected,
    )
    csv_text = render_ftir_difference_csv(result)
    metadata_text = render_document_json(
        build_ftir_difference_csv_metadata(
            result,
            source_a=source_a,
            source_b=source_b,
            processed_a=processed_a,
            processed_b=processed_b,
            peak_result_a=peak_result_a,
            peak_result_b=peak_result_b,
            exported_at=exported_at,
            result_role=result_role,
        )
    )
    written_metadata = atomic_write_text(
        metadata_target,
        metadata_text,
        overwrite=overwrite,
        protected_paths=protected,
    )
    written_csv = atomic_write_text(
        csv_target,
        csv_text,
        overwrite=overwrite,
        protected_paths=protected,
    )
    return {"csv": written_csv, "metadata": written_metadata}


def export_ftir_difference_json(
    result: DifferenceResult,
    output_path: str | Path,
    *,
    source_a: Spectrum1D,
    source_b: Spectrum1D,
    processed_a: ProcessedSpectrum | None = None,
    processed_b: ProcessedSpectrum | None = None,
    peak_result_a: PeakDetectionResult | None = None,
    peak_result_b: PeakDetectionResult | None = None,
    overwrite: bool = False,
    exported_at: str | None = None,
    result_role: str | None = None,
) -> Path:
    _validate_difference_sources(result, source_a, source_b)
    protected = _protected_paths((source_a, source_b))
    target = check_output_path(
        output_path,
        overwrite=overwrite,
        protected_paths=protected,
    )
    text = render_ftir_difference_json(
        result,
        source_a=source_a,
        source_b=source_b,
        processed_a=processed_a,
        processed_b=processed_b,
        peak_result_a=peak_result_a,
        peak_result_b=peak_result_b,
        exported_at=exported_at,
        result_role=result_role,
    )
    return atomic_write_text(
        target,
        text,
        overwrite=overwrite,
        protected_paths=protected,
    )


def export_ftir_difference_png(
    result: DifferenceResult,
    output_path: str | Path,
    *,
    source_a: Spectrum1D,
    source_b: Spectrum1D,
    processed_b: ProcessedSpectrum | None = None,
    overwrite: bool = False,
    title: str | None = None,
    labels: Mapping[str, str] | None = None,
    dpi: int = 300,
    width_in: float = 7.0,
    height_in: float = 4.5,
) -> Path:
    _validate_difference_sources(result, source_a, source_b)
    if result.source_b == "processed":
        if processed_b is None:
            raise ExportSerializationError(
                "Processed source B was selected but no ProcessedSpectrum "
                "was supplied.",
                code="missing_processed_source",
            )
        if processed_b.source.dataset_id != source_b.dataset_id:
            raise ExportSerializationError(
                "Processed source B does not belong to the raw dataset.",
                code="difference_source_mismatch",
                context={
                    "expected": source_b.dataset_id,
                    "actual": processed_b.source.dataset_id,
                },
            )
        actual_operations = tuple(
            record.operation_id for record in processed_b.history
        )
        if actual_operations != tuple(result.source_operation_history_b):
            raise ExportSerializationError(
                "Processed source B history does not match the result.",
                code="difference_history_mismatch",
            )
        b_axis, b_signal = processed_b.axis, processed_b.signal
    else:
        if processed_b is not None:
            raise ExportSerializationError(
                "A raw source B selection must not include a "
                "ProcessedSpectrum.",
                code="difference_source_mismatch",
            )
        b_axis, b_signal = source_b.axis, source_b.raw_signal
    label_map = {
        "title": title or "Difference spectrum (A - B)",
        "a": f"A: {source_a.dataset_id}",
        "b": f"B: {source_b.dataset_id}",
        "b_interpolated": "B (linear interpolation to A)",
        "difference": "A - B",
    }
    if labels is not None:
        if not isinstance(labels, Mapping):
            raise ExportSerializationError(
                "labels must be a mapping or None.",
                code="invalid_export_option",
            )
        unknown = set(labels) - set(label_map)
        if unknown:
            raise ExportSerializationError(
                "Unsupported PNG label key(s): "
                + ", ".join(sorted(str(key) for key in unknown)),
                code="invalid_export_option",
            )
        for key, value in labels.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ExportSerializationError(
                    "labels must map text keys to text values.",
                    code="invalid_export_option",
                )
            label_map[key] = value
    figure = Figure(figsize=(width_in, height_in), dpi=100)
    axes = figure.add_subplot(111)
    axes.plot(
        result.axis.values,
        result.aligned_a_signal.values,
        color="#1f77b4",
        linewidth=1.1,
        label=label_map["a"],
    )
    axes.plot(
        b_axis.values,
        b_signal.values,
        color="#ff7f0e",
        linewidth=1.1,
        label=label_map["b"],
    )
    if result.interpolation is not None:
        axes.plot(
            result.axis.values,
            result.aligned_b_signal.values,
            color="#8c564b",
            linewidth=1.0,
            linestyle="--",
            label=label_map["b_interpolated"],
        )
    axes.plot(
        result.axis.values,
        result.signal.values,
        color="#2e7d32",
        linewidth=1.8,
        label=label_map["difference"],
    )
    axes.set_title(label_map["title"])
    axes.set_xlabel(format_axis_label(result.axis))
    axes.set_ylabel(format_signal_label(result.signal))
    axes.grid(
        True,
        which="major",
        color="#b0b0b0",
        alpha=0.35,
        linewidth=0.6,
    )
    axes.legend(loc="best", frameon=False)
    protected = _protected_paths((source_a, source_b))
    return _save_figure_png(
        figure,
        output_path,
        overwrite=overwrite,
        protected=protected,
        dpi=dpi,
    )


__all__ = [
    "CSV_COLUMNS",
    "DIFFERENCE_CSV_COLUMNS",
    "EXPORT_STATUS",
    "FTIR_DIFFERENCE_EXPORT_SCHEMA_ID",
    "FTIR_DIFFERENCE_EXPORT_SCHEMA_VERSION",
    "FTIR_EXPORT_SCHEMA_ID",
    "FTIR_EXPORT_SCHEMA_VERSION",
    "NUMERIC_SERIALIZATION",
    "build_ftir_difference_csv_metadata",
    "build_ftir_difference_document",
    "build_ftir_spectrum_csv_metadata",
    "build_ftir_spectrum_document",
    "export_ftir_difference_csv",
    "export_ftir_difference_json",
    "export_ftir_difference_png",
    "export_ftir_spectrum_csv",
    "export_ftir_spectrum_json",
    "export_ftir_spectrum_png",
    "render_ftir_difference_csv",
    "render_ftir_difference_json",
    "render_ftir_spectrum_csv",
    "render_ftir_spectrum_json",
    "render_xy_csv",
    "software_versions",
]
