"""Shared helpers for the independent EPR importer adapters."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn

from spectralab.core.errors import ImportFailure
from spectralab.core.importers import ImportedDataset, ImportRequest
from spectralab.core.model import Spectrum1D
from spectralab.techniques.epr.importers._asc_reader import (
    AscDataError,
    AscFormatError,
)


def request_entry(request: ImportRequest, *, technique: str) -> Path:
    """Validate a direct-call request without silently ignoring overrides."""
    if not isinstance(request, ImportRequest):
        raise ImportFailure(
            "Importer.read() requires an ImportRequest.",
            code="invalid_import_request",
            context={"type": type(request).__name__},
        )
    if request.companions:
        raise ImportFailure(
            "The M2 EPR importers resolve companion files from the entry; "
            "explicit companion overrides are not supported.",
            code="unsupported_companion_override",
            context={"companions": sorted(request.companions)},
        )
    if request.options:
        raise ImportFailure(
            "The M2 EPR importers accept no import options; values are not "
            "silently ignored.",
            code="unsupported_import_option",
            context={"options": sorted(request.options)},
        )
    if request.technique_hint is not None and request.technique_hint != technique:
        raise ImportFailure(
            f"Technique hint {request.technique_hint!r} does not match this "
            f"{technique!r} importer.",
            code="technique_mismatch",
            context={
                "technique_hint": request.technique_hint,
                "technique": technique,
            },
        )
    return request.entry


def raise_import_failure(
    exc: Exception,
    *,
    importer_id: str,
    entry: Path,
) -> NoReturn:
    """Translate a legacy parser error into a stable ImportFailure."""
    if isinstance(exc, ImportFailure):
        raise exc

    if isinstance(exc, FileNotFoundError):
        code = "entry_not_found"
    elif isinstance(exc, PermissionError):
        code = "entry_not_readable"
    elif isinstance(exc, AscFormatError):
        code = "asc_format_error"
    elif isinstance(exc, AscDataError):
        code = "asc_data_error"
    else:
        legacy_code = getattr(exc, "code", None)
        code = (
            legacy_code
            if isinstance(legacy_code, str) and legacy_code.strip()
            else "importer_read_failed"
        )

    context: dict[str, Any] = {
        "importer_id": importer_id,
        "entry": str(entry),
        "cause_type": type(exc).__name__,
    }
    legacy_context = getattr(exc, "context", None)
    if isinstance(legacy_context, Mapping):
        context.update(legacy_context)

    raise ImportFailure(
        f"Importer {importer_id!r} could not read {entry.name!r}: {exc}",
        code=code,
        context=context,
    ) from exc


def dataset_from_spectrum(spectrum: Spectrum1D) -> ImportedDataset:
    """Wrap one converted spectrum in the common import-result container."""
    return ImportedDataset(
        spectra=(spectrum,),
        primary_index=0,
        format_id=spectrum.source_format or "unknown",
        technique=spectrum.technique,
        warnings=spectrum.provenance.warnings,
        diagnostics=spectrum.provenance.diagnostics,
    )


__all__ = [
    "dataset_from_spectrum",
    "raise_import_failure",
    "request_entry",
]
