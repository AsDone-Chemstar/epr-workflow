"""Generic provenance and metadata documents for Spectrum1D export.

These builders never invent units, timestamps, sample information or hashes.
Unknown values are serialized as ``null``/empty collections and source hashes
remain distinct from the importer-defined canonical dataset hash.
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from spectralab.core.errors import ExportSerializationError
from spectralab.core.model import Spectrum1D

SCHEMA_STATUS = "initial"

HASH_DEFINITIONS = {
    "source_file_sha256": (
        "SHA-256 over the exact bytes of the corresponding source file. "
        "An empty string means the hash was not recorded."
    ),
    "canonical_sha256": (
        "Importer-defined canonical dataset hash. provenance.sha256_definition "
        "records the exact construction; null means no canonical hash was "
        "available."
    ),
}


def _json_compatible(value: Any, *, path: str) -> Any:
    """Convert values to JSON types without silently discarding information."""
    if isinstance(value, np.generic):
        return _json_compatible(value.item(), path=path)
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ExportSerializationError(
                f"Non-finite float at {path}; JSON/CSV export refuses to emit "
                "NaN or Infinity.",
                code="nonfinite_value",
                context={"path": path, "value": repr(value)},
            )
        return value
    if isinstance(value, np.ndarray):
        return _json_compatible(value.tolist(), path=path)
    if isinstance(value, Path) or isinstance(value, os.PathLike):
        return str(Path(value))
    if isinstance(value, (bytes, bytearray)):
        raise ExportSerializationError(
            f"Binary value at {path} cannot be represented as JSON without "
            "an explicit encoding.",
            code="unsupported_metadata_value",
            context={"path": path, "type": type(value).__name__},
        )
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ExportSerializationError(
                    f"Mapping key at {path} is not text; it cannot be "
                    "represented without renaming or dropping it.",
                    code="unsupported_metadata_key",
                    context={"path": path, "key_type": type(key).__name__},
                )
            result[key] = _json_compatible(
                item,
                path=f"{path}.{key}",
            )
        return result
    if isinstance(value, Sequence):
        return [
            _json_compatible(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    raise ExportSerializationError(
        f"Unsupported metadata value at {path}: {type(value).__name__}.",
        code="unsupported_metadata_value",
        context={"path": path, "type": type(value).__name__},
    )


def json_compatible(value: Any, *, path: str = "document") -> Any:
    """Convert values to strict JSON types without silent coercion.

    This is the public wrapper around the same conversion used by the generic
    export documents. It rejects non-finite floats, binary values and
    non-string mapping keys.
    """
    return _json_compatible(value, path=path)


def build_provenance_document(spectrum: Spectrum1D) -> dict[str, Any]:
    """Build the technique-independent provenance object for one spectrum."""
    provenance = spectrum.provenance
    return {
        "source_format": spectrum.source_format,
        "importer": {
            "id": provenance.importer_id,
            "version": provenance.importer_version,
        },
        "imported_at_utc": provenance.imported_at_utc,
        "source_files": [
            {
                "role": source.role,
                "path": str(source.path),
                "format_id": source.format_id,
                "size_bytes": source.size_bytes,
                "sha256": source.sha256 or None,
            }
            for source in provenance.source_files
        ],
        "canonical_sha256": provenance.canonical_sha256,
        "sha256_definition": provenance.sha256_definition,
        "file_size_bytes": provenance.file_size_bytes,
        "hash_definitions": dict(HASH_DEFINITIONS),
        "warnings": list(provenance.warnings),
        "assumptions": list(provenance.assumptions),
        "diagnostics": _json_compatible(
            dict(provenance.diagnostics),
            path="provenance.diagnostics",
        ),
        "format_metadata": _json_compatible(
            dict(provenance.format_metadata),
            path="provenance.format_metadata",
        ),
        "software_versions": _json_compatible(
            dict(provenance.software_versions),
            path="provenance.software_versions",
        ),
        "metadata_origin": _json_compatible(
            dict(spectrum.metadata.metadata_origin),
            path="metadata.metadata_origin",
        ),
    }


def build_metadata_document(
    spectrum: Spectrum1D,
    *,
    schema_id: str,
    schema_version: int,
    export_format: str,
    include_values: bool,
    numeric_serialization: str,
) -> dict[str, Any]:
    """Build the shared document used by JSON and CSV metadata output."""
    if not isinstance(spectrum, Spectrum1D):
        raise ExportSerializationError(
            "Generic export requires a Spectrum1D.",
            code="invalid_spectrum",
            context={"type": type(spectrum).__name__},
        )
    if not isinstance(schema_id, str) or not schema_id.strip():
        raise ExportSerializationError(
            "schema_id must be non-empty text.",
            code="invalid_schema",
        )
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version < 1
    ):
        raise ExportSerializationError(
            "schema_version must be a positive integer.",
            code="invalid_schema",
        )
    if not isinstance(include_values, bool):
        raise ExportSerializationError(
            "include_values must be a boolean.",
            code="invalid_schema",
        )

    axis = spectrum.axis
    signal = spectrum.raw_signal
    metadata = spectrum.metadata

    axis_document: dict[str, Any] = {
        "quantity": axis.quantity,
        "unit": axis.unit,
        "name": axis.name,
        "direction": axis.direction,
        "point_count": axis.point_count,
        "metadata_source": axis.metadata_source,
        "missing_reason": axis.missing_reason,
    }
    signal_document: dict[str, Any] = {
        "semantics": signal.semantics,
        "unit": signal.unit,
        "name": signal.name,
        "point_count": signal.point_count,
        "metadata_source": signal.metadata_source,
        "missing_reason": signal.missing_reason,
    }
    if include_values:
        axis_document["values"] = _json_compatible(
            axis.values,
            path="axis.values",
        )
        signal_document["values"] = _json_compatible(
            signal.values,
            path="signal.values",
        )

    document = {
        "schema_id": schema_id,
        "schema_version": schema_version,
        "schema_status": SCHEMA_STATUS,
        "export": {
            "format": export_format,
            "values_included": include_values,
            "point_order": "preserved",
            "processing_applied": [],
            "numeric_serialization": numeric_serialization,
        },
        "dataset": {
            "dataset_id": spectrum.dataset_id,
            "technique": spectrum.technique,
            "source_format": spectrum.source_format,
            "point_count": spectrum.point_count,
        },
        "axis": axis_document,
        "signal": signal_document,
        "metadata": {
            "technique": metadata.technique,
            "title": metadata.title,
            "instrument": _json_compatible(
                dict(metadata.instrument),
                path="metadata.instrument",
            ),
            "acquisition": _json_compatible(
                dict(metadata.acquisition),
                path="metadata.acquisition",
            ),
            "sample": _json_compatible(
                dict(metadata.sample),
                path="metadata.sample",
            ),
            "technique_metadata": _json_compatible(
                dict(metadata.technique_metadata),
                path="metadata.technique_metadata",
            ),
            "extra": _json_compatible(
                dict(metadata.extra),
                path="metadata.extra",
            ),
            "unknown_fields": list(metadata.unknown_fields),
            "metadata_origin": _json_compatible(
                dict(metadata.metadata_origin),
                path="metadata.metadata_origin",
            ),
        },
        "provenance": build_provenance_document(spectrum),
    }
    return _json_compatible(document, path="document")


__all__ = [
    "HASH_DEFINITIONS",
    "SCHEMA_STATUS",
    "build_metadata_document",
    "build_provenance_document",
    "json_compatible",
]
