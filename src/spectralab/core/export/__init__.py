"""Technique-independent export for Spectrum1D.

The package emits generic ``x,y`` CSV plus a JSON metadata sidecar, and a
versioned JSON document containing the full imported spectrum and provenance.
It contains no EPR/FTIR column names, Qt imports or GUI assumptions.
"""

from spectralab.core.errors import (
    ExportError,
    ExportPathError,
    ExportSerializationError,
    OutputExistsError,
)
from spectralab.core.export.csv import (
    CSV_COLUMNS,
    CSV_NUMERIC_SERIALIZATION,
    CSV_SCHEMA_ID,
    CSV_SCHEMA_VERSION,
    build_csv_metadata_document,
    export_spectrum_csv,
    render_csv_metadata_json,
    render_spectrum_csv,
)
from spectralab.core.export.json import (
    JSON_NUMERIC_SERIALIZATION,
    JSON_SCHEMA_ID,
    JSON_SCHEMA_VERSION,
    build_export_document,
    export_spectrum_json,
    render_document_json,
    render_spectrum_json,
)
from spectralab.core.export.paths import (
    atomic_write_bytes,
    atomic_write_text,
    check_output_path,
)
from spectralab.core.export.provenance import (
    HASH_DEFINITIONS,
    SCHEMA_STATUS,
    build_metadata_document,
    build_provenance_document,
    json_compatible,
)

__all__ = [
    "CSV_COLUMNS",
    "CSV_NUMERIC_SERIALIZATION",
    "CSV_SCHEMA_ID",
    "CSV_SCHEMA_VERSION",
    "ExportError",
    "ExportPathError",
    "ExportSerializationError",
    "HASH_DEFINITIONS",
    "JSON_NUMERIC_SERIALIZATION",
    "JSON_SCHEMA_ID",
    "JSON_SCHEMA_VERSION",
    "OutputExistsError",
    "SCHEMA_STATUS",
    "atomic_write_bytes",
    "atomic_write_text",
    "build_csv_metadata_document",
    "build_export_document",
    "build_metadata_document",
    "build_provenance_document",
    "check_output_path",
    "json_compatible",
    "export_spectrum_csv",
    "export_spectrum_json",
    "render_csv_metadata_json",
    "render_document_json",
    "render_spectrum_csv",
    "render_spectrum_json",
]
