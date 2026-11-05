"""Versioned JSON export for one generic Spectrum1D."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from spectralab.core.errors import ExportSerializationError
from spectralab.core.export.paths import atomic_write_text, check_output_path
from spectralab.core.export.provenance import build_metadata_document
from spectralab.core.model import Spectrum1D

JSON_SCHEMA_ID = "spectralab.spectrum1d.export"
JSON_SCHEMA_VERSION = 1
JSON_NUMERIC_SERIALIZATION = "python-json-shortest-roundtrip-float64"


def render_document_json(document: dict[str, Any]) -> str:
    """Serialize a document deterministically with strict JSON constants."""
    try:
        text = json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ExportSerializationError(
            "The export document could not be serialized as strict JSON.",
            code="json_serialization",
            context={"error": str(exc)},
        ) from exc
    return text + "\n"


def build_export_document(spectrum: Spectrum1D) -> dict[str, Any]:
    """Build the generic Spectrum1D JSON document (schema version 1)."""
    return build_metadata_document(
        spectrum,
        schema_id=JSON_SCHEMA_ID,
        schema_version=JSON_SCHEMA_VERSION,
        export_format="json",
        include_values=True,
        numeric_serialization=JSON_NUMERIC_SERIALIZATION,
    )


def render_spectrum_json(spectrum: Spectrum1D) -> str:
    """Render one spectrum as deterministic, strict UTF-8 JSON text."""
    return render_document_json(build_export_document(spectrum))


def export_spectrum_json(
    spectrum: Spectrum1D,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write the generic JSON export without modifying the spectrum or sources."""
    if not isinstance(spectrum, Spectrum1D):
        raise ExportSerializationError(
            "Generic JSON export requires a Spectrum1D.",
            code="invalid_spectrum",
            context={"type": type(spectrum).__name__},
        )
    protected = [source.path for source in spectrum.provenance.source_files]
    target = check_output_path(
        output_path,
        overwrite=overwrite,
        protected_paths=protected,
    )
    text = render_spectrum_json(spectrum)
    return atomic_write_text(
        target,
        text,
        overwrite=overwrite,
        protected_paths=protected,
    )


__all__ = [
    "JSON_NUMERIC_SERIALIZATION",
    "JSON_SCHEMA_ID",
    "JSON_SCHEMA_VERSION",
    "build_export_document",
    "export_spectrum_json",
    "render_document_json",
    "render_spectrum_json",
]
