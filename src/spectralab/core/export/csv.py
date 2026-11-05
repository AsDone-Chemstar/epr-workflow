"""Generic X/Y CSV export for one Spectrum1D, with a JSON metadata sidecar."""

from __future__ import annotations

import csv as _csv
import io
import math
import os
from pathlib import Path
from typing import Any

from spectralab.core.errors import (
    ExportPathError,
    ExportSerializationError,
)
from spectralab.core.export.json import render_document_json
from spectralab.core.export.paths import atomic_write_text, check_output_path
from spectralab.core.export.provenance import build_metadata_document
from spectralab.core.model import Spectrum1D

CSV_SCHEMA_ID = "spectralab.spectrum1d.csv_metadata"
CSV_SCHEMA_VERSION = 1
CSV_COLUMNS = ("x", "y")
CSV_NUMERIC_SERIALIZATION = "python-repr-shortest-roundtrip-float64"


def _format_float(value: Any, *, path: str) -> str:
    number = float(value)
    if not math.isfinite(number):
        raise ExportSerializationError(
            f"Non-finite value at {path}; CSV export refuses to emit NaN or "
            "Infinity.",
            code="nonfinite_value",
            context={"path": path, "value": repr(number)},
        )
    # repr(float) is the shortest decimal string that round-trips to the same
    # binary64 value. It neither rounds nor truncates the stored value.
    return repr(number)


def render_spectrum_csv(spectrum: Spectrum1D) -> str:
    """Render generic ``x,y`` CSV with original point order and float64 values."""
    if not isinstance(spectrum, Spectrum1D):
        raise ExportSerializationError(
            "Generic CSV export requires a Spectrum1D.",
            code="invalid_spectrum",
            context={"type": type(spectrum).__name__},
        )
    output = io.StringIO(newline="")
    writer = _csv.writer(output, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for index, (x_value, y_value) in enumerate(
        zip(spectrum.x_values, spectrum.y_values, strict=True)
    ):
        writer.writerow(
            [
                _format_float(x_value, path=f"axis.values[{index}]"),
                _format_float(y_value, path=f"signal.values[{index}]"),
            ]
        )
    return output.getvalue()


def build_csv_metadata_document(spectrum: Spectrum1D) -> dict[str, Any]:
    """Build the sidecar metadata document for a generic CSV export."""
    document = build_metadata_document(
        spectrum,
        schema_id=CSV_SCHEMA_ID,
        schema_version=CSV_SCHEMA_VERSION,
        export_format="csv_metadata",
        include_values=False,
        numeric_serialization=CSV_NUMERIC_SERIALIZATION,
    )
    document["csv"] = {
        "columns": list(CSV_COLUMNS),
        "delimiter": ",",
        "encoding": "utf-8",
        "line_ending": "LF",
        "data_values": "stored in the sibling CSV data file",
        "numeric_format": CSV_NUMERIC_SERIALIZATION,
    }
    return document


def render_csv_metadata_json(spectrum: Spectrum1D) -> str:
    """Render the deterministic JSON sidecar for a CSV export."""
    return render_document_json(build_csv_metadata_document(spectrum))


def _same_path(first: Path, second: Path) -> bool:
    try:
        return os.path.normcase(str(first.resolve(strict=False))) == (
            os.path.normcase(str(second.resolve(strict=False)))
        )
    except OSError:
        return False


def export_spectrum_csv(
    spectrum: Spectrum1D,
    output_path: str | Path,
    *,
    overwrite: bool = False,
    metadata_path: str | Path | None = None,
) -> dict[str, Path]:
    """Write a generic CSV and its JSON metadata sidecar.

    Both paths are checked before either file is written. Serialization also
    completes before writing, so an invalid value or unsupported metadata type
    produces no partial output. Existing files require ``overwrite=True``.
    """
    if not isinstance(spectrum, Spectrum1D):
        raise ExportSerializationError(
            "Generic CSV export requires a Spectrum1D.",
            code="invalid_spectrum",
            context={"type": type(spectrum).__name__},
        )

    try:
        csv_path = Path(output_path)
    except (TypeError, ValueError) as exc:
        raise ExportPathError(
            "The CSV output path must be text or a filesystem path.",
            code="invalid_output_path",
            context={"type": type(output_path).__name__},
        ) from exc
    if metadata_path is None:
        metadata_target = csv_path.with_name(
            f"{csv_path.stem}_metadata.json"
        )
    else:
        try:
            metadata_target = Path(metadata_path)
        except (TypeError, ValueError) as exc:
            raise ExportPathError(
                "The metadata output path must be text or a filesystem path.",
                code="invalid_output_path",
                context={"type": type(metadata_path).__name__},
            ) from exc

    if _same_path(csv_path, metadata_target):
        raise ExportPathError(
            "The CSV and metadata output paths must be different.",
            code="duplicate_output_path",
            context={"path": str(csv_path)},
        )

    protected = [source.path for source in spectrum.provenance.source_files]
    csv_target = check_output_path(
        csv_path,
        overwrite=overwrite,
        protected_paths=protected,
    )
    metadata_target = check_output_path(
        metadata_target,
        overwrite=overwrite,
        protected_paths=protected,
    )

    csv_text = render_spectrum_csv(spectrum)
    metadata_text = render_csv_metadata_json(spectrum)

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
    return {
        "csv": written_csv,
        "metadata": written_metadata,
    }


__all__ = [
    "CSV_COLUMNS",
    "CSV_NUMERIC_SERIALIZATION",
    "CSV_SCHEMA_ID",
    "CSV_SCHEMA_VERSION",
    "build_csv_metadata_document",
    "export_spectrum_csv",
    "render_csv_metadata_json",
    "render_spectrum_csv",
]
