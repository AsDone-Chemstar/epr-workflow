"""Generic, technique-independent metadata text formatter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from spectralab.app.gui.i18n import Translator
from spectralab.core.model import Spectrum1D
from spectralab.core.processing import ProcessedSpectrum


class MetadataError(ValueError):
    """The metadata formatter received an unsupported display object."""


def _format_value(value: Any, translator: Translator) -> str:
    if value is None:
        return translator.tr("app.unknown")
    if isinstance(value, str):
        return value if value.strip() else translator.tr("app.unknown")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        if not value:
            return translator.tr("app.unknown")
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    if isinstance(value, (list, tuple)):
        if not value:
            return translator.tr("app.none")
        return json.dumps(list(value), ensure_ascii=False, default=str)
    if isinstance(value, (bool, int, float)):
        return str(value)
    return str(value)


def _source_file_lines(spectrum: Spectrum1D, translator: Translator) -> list[str]:
    source_files = spectrum.provenance.source_files
    if not source_files:
        return [translator.tr("meta.source_none")]
    lines: list[str] = []
    for source in source_files:
        lines.append(
            translator.tr(
                "meta.source_file",
                role=source.role,
                path=str(source.path),
            )
        )
        lines.append(
            translator.tr(
                "meta.source_details",
                format_id=source.format_id,
                size=(
                    source.size_bytes
                    if source.size_bytes is not None
                    else translator.tr("app.unknown")
                ),
                sha=source.sha256 or translator.tr("app.unknown"),
            )
        )
    return lines


def format_metadata(
    display: Spectrum1D | ProcessedSpectrum,
    translator: Translator,
) -> str:
    """Format available metadata and processing history without inference."""
    if isinstance(display, ProcessedSpectrum):
        source = display.source
        axis = display.axis
        signal = display.signal
        history = display.history
        kind = translator.tr("meta.kind_processed")
    elif isinstance(display, Spectrum1D):
        source = display
        axis = display.axis
        signal = display.raw_signal
        history = ()
        kind = translator.tr("meta.kind_raw")
    else:
        raise MetadataError(
            "Metadata formatting supports Spectrum1D and ProcessedSpectrum."
        )

    metadata = source.metadata
    lines = [
        translator.tr("meta.kind", kind=kind),
        translator.tr("meta.technique", value=metadata.technique),
        translator.tr("meta.dataset_id", value=source.dataset_id),
        translator.tr("meta.points", value=source.point_count),
        translator.tr("meta.axis"),
        translator.tr("meta.axis_quantity", value=axis.quantity),
        translator.tr(
            "meta.axis_unit",
            value=axis.unit or translator.tr("app.unknown"),
        ),
        translator.tr(
            "meta.axis_name",
            value=axis.name or translator.tr("app.unknown"),
        ),
        translator.tr("meta.axis_direction", value=axis.direction),
        translator.tr("meta.axis_source", value=axis.metadata_source),
        translator.tr("meta.signal"),
        translator.tr("meta.signal_semantics", value=signal.semantics),
        translator.tr(
            "meta.signal_unit",
            value=signal.unit or translator.tr("app.unknown"),
        ),
        translator.tr(
            "meta.signal_name",
            value=signal.name or translator.tr("app.unknown"),
        ),
        translator.tr("meta.signal_source", value=signal.metadata_source),
        translator.tr(
            "meta.source_format",
            value=source.source_format or translator.tr("app.unknown"),
        ),
        translator.tr(
            "meta.title_field",
            value=_format_value(metadata.title, translator),
        ),
        translator.tr(
            "meta.instrument",
            value=_format_value(metadata.instrument, translator),
        ),
        translator.tr(
            "meta.acquisition",
            value=_format_value(metadata.acquisition, translator),
        ),
        translator.tr(
            "meta.sample",
            value=_format_value(metadata.sample, translator),
        ),
        translator.tr(
            "meta.technique_metadata",
            value=_format_value(metadata.technique_metadata, translator),
        ),
        translator.tr(
            "meta.extra",
            value=_format_value(metadata.extra, translator),
        ),
        translator.tr(
            "meta.unknown_fields",
            value=(
                ", ".join(metadata.unknown_fields)
                if metadata.unknown_fields
                else translator.tr("app.none")
            ),
        ),
        translator.tr(
            "meta.metadata_origin",
            value=_format_value(metadata.metadata_origin, translator),
        ),
        translator.tr("meta.source_files"),
        *_source_file_lines(source, translator),
    ]
    provenance = source.provenance
    import_options = provenance.format_metadata.get("import_options")
    if import_options is not None:
        lines.append(
            translator.tr(
                "meta.import_options",
                value=_format_value(import_options, translator),
            )
        )
    if provenance.warnings:
        lines.append(
            translator.tr(
                "meta.warnings",
                value="; ".join(provenance.warnings),
            )
        )
    if provenance.assumptions:
        lines.append(
            translator.tr(
                "meta.assumptions",
                value="; ".join(provenance.assumptions),
            )
        )

    if history:
        lines.append(
            translator.tr("meta.processing_history", count=len(history))
        )
        for record in history:
            lines.append(
                translator.tr(
                    "meta.operation",
                    order=record.order,
                    operation_id=record.operation_id,
                    technique=record.technique,
                    version=record.version,
                )
            )
            lines.append(
                translator.tr(
                    "meta.operation_parameters",
                    value=_format_value(record.parameters, translator),
                )
            )
            if record.warnings:
                lines.append(
                    translator.tr(
                        "meta.operation_warnings",
                        value="; ".join(record.warnings),
                    )
                )
            if record.assumptions:
                lines.append(
                    translator.tr(
                        "meta.operation_assumptions",
                        value="; ".join(record.assumptions),
                    )
                )
            if record.diagnostics:
                lines.append(
                    translator.tr(
                        "meta.operation_diagnostics",
                        value=_format_value(record.diagnostics, translator),
                    )
                )
    else:
        lines.append(translator.tr("meta.processing_none"))

    return "\n".join(lines)


__all__ = ["MetadataError", "format_metadata"]
