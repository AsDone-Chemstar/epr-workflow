"""One-way adapter from the legacy EPR import result to Spectrum1D.

This module is intentionally a compatibility bridge for M1. It accepts the
existing ``epr_workflow.plot_asc.ImportResult`` by duck typing and does not
import the EPR package at runtime, so the neutral core package remains free of
EPR-specific imports. The adapter will move to ``techniques/epr`` when the
technique module is introduced (M7).

The adapter never re-reads files, sorts points, converts units, smooths,
baselines, normalizes or interpolates. It copies numeric values through the
read-only Spectrum1D constructors.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spectralab.core.model import (
    Axis1D,
    Provenance,
    Signal1D,
    SourceFile,
    Spectrum1D,
    SpectrumMetadata,
)


class LegacyAdapterError(ValueError):
    """The legacy import object lacks required structure."""

    def __init__(self, message: str, *, code: str, context: dict | None = None):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


_DIRECTION = {
    "strictly increasing": "increasing",
    "strictly decreasing": "decreasing",
}


def _required_attr(obj: Any, name: str) -> Any:
    if not hasattr(obj, name):
        raise LegacyAdapterError(
            f"Legacy import result is missing required attribute {name!r}.",
            code="legacy_attribute",
            context={"attribute": name},
        )
    return getattr(obj, name)


def _source_files(result: Any, source_format: str) -> tuple[SourceFile, ...]:
    files = dict(getattr(result, "source_files", {}) or {})
    hashes = dict(getattr(result, "source_hashes", {}) or {})
    if not files:
        files = {"source": str(_required_attr(result, "source"))}
    if not hashes:
        hashes = {"source": str(_required_attr(result, "sha256"))}

    records: list[SourceFile] = []
    for role, path_value in files.items():
        path = Path(path_value)
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        records.append(
            SourceFile(
                role=str(role),
                path=path,
                sha256=str(hashes.get(role, "")),
                size_bytes=size,
                format_id=source_format,
            )
        )
    return tuple(records)


def spectrum1d_from_import_result(
    result: Any,
    *,
    dataset_id: str | None = None,
    importer_id: str = "epr_workflow.legacy_adapter",
    importer_version: str = "unknown",
) -> Spectrum1D:
    """Convert a legacy EPR ``ImportResult`` into a :class:`Spectrum1D`.

    Parameters
    ----------
    result
        Existing ``ImportResult`` from ``read_asc``/``read_bes3t`` or
        ``read_dataset``. It is only read; no attribute or array is modified.
    dataset_id
        Optional stable identifier. When omitted, the source filename stem is
        used. This is an identifier, not acquired scientific metadata.
    importer_id, importer_version
        Provenance identifiers supplied by a concrete importer adapter. The
        defaults preserve the M1 direct-call behaviour.
    """
    data = _required_attr(result, "data")
    if "field_G" not in data.columns or "intensity" not in data.columns:
        raise LegacyAdapterError(
            "Legacy import data must contain 'field_G' and 'intensity' "
            "columns.",
            code="legacy_columns",
            context={"columns": list(data.columns)},
        )

    source = Path(_required_attr(result, "source"))
    source_format = str(getattr(result, "source_format", "unknown"))
    field_order = str(getattr(result, "field_order", "unknown"))
    format_metadata = dict(getattr(result, "format_metadata", {}) or {})
    format_metadata.setdefault("source_format", source_format)

    axis_meta = format_metadata.get("axis")
    axis_meta = axis_meta if isinstance(axis_meta, dict) else {}
    parsed = format_metadata.get("parsed_parameters")
    parsed = parsed if isinstance(parsed, dict) else {}

    axis_unit = axis_meta.get("unit", "G")
    if not isinstance(axis_unit, str) or not axis_unit:
        axis_unit = "G"
    source_axis_name = axis_meta.get("name")
    source_signal_name = parsed.get("IRNAM") or "Intensity"
    source_signal_unit = parsed.get("IRUNI") or None
    if isinstance(source_signal_unit, str):
        source_signal_unit = source_signal_unit.strip() or None
    else:
        source_signal_unit = None

    axis_direction = _DIRECTION.get(field_order, "unknown")
    field = data["field_G"].to_numpy()
    intensity = data["intensity"].to_numpy()

    axis = Axis1D(
        values=field,
        quantity="magnetic_field",
        unit=axis_unit,
        name="Magnetic field",
        direction=axis_direction,
        metadata_source="ImportResult.data['field_G']",
    )
    signal = Signal1D(
        values=intensity,
        semantics="unknown",
        unit=source_signal_unit,
        name=str(source_signal_name),
        metadata_source="ImportResult.data['intensity']",
        missing_reason=(
            None
            if source_signal_unit is not None
            else "The legacy EPR import does not document an intensity unit."
        ),
    )

    source_files = _source_files(result, source_format)
    warnings = tuple(str(item) for item in (getattr(result, "warnings", ()) or ()))
    assumptions = tuple(
        str(item)
        for item in (getattr(result, "format_assumptions", ()) or ())
    )
    diagnostics = {
        "legacy_source_format": source_format,
        "field_order": field_order,
        "rejected_rows": len(getattr(result, "rejected_rows", ()) or ()),
        "missing_value_count": int(
            getattr(result, "missing_value_count", 0) or 0
        ),
        "nonfinite_value_count": int(
            getattr(result, "nonfinite_value_count", 0) or 0
        ),
        "duplicate_field_count": int(
            getattr(result, "duplicate_field_count", 0) or 0
        ),
        "index_continuity": str(
            getattr(result, "index_continuity", "not checked")
        ),
    }

    provenance = Provenance(
        source_files=source_files,
        canonical_sha256=getattr(result, "sha256", None) or None,
        sha256_definition=getattr(result, "sha256_definition", None),
        file_size_bytes=getattr(result, "file_size_bytes", None),
        warnings=warnings,
        assumptions=assumptions,
        format_metadata=format_metadata,
        diagnostics=diagnostics,
        software_versions={},
        importer_id=importer_id,
        importer_version=importer_version,
        imported_at_utc=None,
    )

    unknown_fields = [
        "title",
        "instrument",
        "acquisition",
        "sample",
        "signal_semantics",
    ]
    if source_signal_unit is None:
        unknown_fields.append("signal_unit")

    metadata = SpectrumMetadata(
        technique="epr",
        title=None,
        instrument={},
        acquisition={},
        sample={},
        technique_metadata={
            "source_format": source_format,
            "source_field_order": field_order,
            "source_axis_name": source_axis_name,
            "source_signal_name": source_signal_name,
            "source_signal_unit": source_signal_unit,
        },
        extra={},
        unknown_fields=tuple(unknown_fields),
        metadata_origin={
            "axis.values": "ImportResult.data['field_G']",
            "axis.unit": "legacy EPR format (G)",
            "axis.direction": "ImportResult.field_order",
            "signal.values": "ImportResult.data['intensity']",
            "signal.unit": "unknown unless IRUNI is present",
            "signal.semantics": "unknown",
            "source_format": "ImportResult.source_format",
            "source_files": "ImportResult.source_files/sha256",
        },
    )

    return Spectrum1D(
        dataset_id=dataset_id or source.stem or source.name or "epr_dataset",
        axis=axis,
        raw_signal=signal,
        metadata=metadata,
        provenance=provenance,
    )


class LegacyEprAdapter:
    """Small object-style wrapper around the one-way adapter function."""

    @staticmethod
    def to_spectrum1d(
        result: Any, *, dataset_id: str | None = None
    ) -> Spectrum1D:
        return spectrum1d_from_import_result(result, dataset_id=dataset_id)


# Intuitive aliases for callers and future migration code.
to_spectrum1d = spectrum1d_from_import_result
adapt_import_result = spectrum1d_from_import_result


__all__ = [
    "LegacyAdapterError",
    "LegacyEprAdapter",
    "adapt_import_result",
    "spectrum1d_from_import_result",
    "to_spectrum1d",
]
