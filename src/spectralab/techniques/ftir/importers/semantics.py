"""FTIR-specific metadata vocabulary and validation.

The neutral core stores FTIR acquisition mode and ATR correction status in
``SpectrumMetadata.technique_metadata`` without interpreting them. This module
owns the FTIR vocabulary and only accepts explicit values; it never infers a
mode or correction status from a filename, extension, signal shape or numeric
range.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from spectralab.core.errors import ImportFailure

AcquisitionMode = Literal["ATR", "Transmission", "Unknown"]
ATRCorrectionStatus = Literal[
    "applied", "not_applied", "not_applicable", "unknown"
]

ACQUISITION_MODES: tuple[str, ...] = ("ATR", "Transmission", "Unknown")
ATR_CORRECTION_STATUSES: tuple[str, ...] = (
    "applied",
    "not_applied",
    "not_applicable",
    "unknown",
)
FTIR_SIGNAL_SEMANTICS: tuple[str, ...] = (
    "absorbance",
    "transmittance",
    "unknown",
)
FTIR_AXIS_QUANTITIES: tuple[str, ...] = ("wavenumber", "unknown")
FTIR_AXIS_UNITS: tuple[str, ...] = ("cm^-1",)

_ACQUISITION_ALIASES = {
    "atr": "ATR",
    "transmission": "Transmission",
    "transmittance": "Transmission",
    "unknown": "Unknown",
}
_ATR_STATUS_ALIASES = {
    "applied": "applied",
    "not_applied": "not_applied",
    "not applicable": "not_applicable",
    "not-applicable": "not_applicable",
    "not_applicable": "not_applicable",
    "unknown": "unknown",
}
_UNIT_ALIASES = {
    "cm^-1": "cm^-1",
    "cm-1": "cm^-1",
    "cm⁻¹": "cm^-1",
    "1/cm": "cm^-1",
}


def _invalid(message: str, *, code: str, **context: Any) -> ImportFailure:
    return ImportFailure(message, code=code, context=context)


def normalize_acquisition_mode(value: Any) -> str:
    """Return the canonical acquisition mode or raise a coded error."""
    if not isinstance(value, str) or not value.strip():
        raise _invalid(
            "FTIR acquisition_mode must be 'ATR', 'Transmission' or 'Unknown'.",
            code="ftir_invalid_acquisition_mode",
            value=repr(value),
        )
    key = " ".join(value.strip().split()).casefold()
    canonical = _ACQUISITION_ALIASES.get(key)
    if canonical is None:
        raise _invalid(
            "Unsupported FTIR acquisition mode. Use 'ATR', 'Transmission' "
            "or 'Unknown'.",
            code="ftir_unsupported_acquisition_mode",
            value=value,
            allowed=list(ACQUISITION_MODES),
        )
    return canonical


def normalize_atr_correction_status(value: Any) -> str:
    """Return the canonical ATR correction status or raise a coded error."""
    if not isinstance(value, str) or not value.strip():
        raise _invalid(
            "FTIR atr_correction_status must be 'applied', 'not_applied', "
            "'not_applicable' or 'unknown'.",
            code="ftir_invalid_atr_status",
            value=repr(value),
        )
    key = value.strip().casefold().replace("-", "_").replace(" ", "_")
    canonical = _ATR_STATUS_ALIASES.get(key)
    if canonical is None:
        raise _invalid(
            "Unsupported FTIR ATR correction status.",
            code="ftir_unsupported_atr_status",
            value=value,
            allowed=list(ATR_CORRECTION_STATUSES),
        )
    return canonical


def normalize_signal_semantics(value: Any) -> str:
    """Accept only the FTIR signal semantics supported by M9."""
    if not isinstance(value, str) or not value.strip():
        raise _invalid(
            "FTIR signal semantics must be 'absorbance', 'transmittance' or "
            "'unknown'.",
            code="ftir_invalid_signal_semantics",
            value=repr(value),
        )
    key = value.strip().casefold()
    if key not in FTIR_SIGNAL_SEMANTICS:
        raise _invalid(
            "Unsupported FTIR signal semantics. The importer never infers "
            "them from numeric values.",
            code="ftir_unsupported_signal_semantics",
            value=value,
            allowed=list(FTIR_SIGNAL_SEMANTICS),
        )
    return key


def normalize_axis_quantity(value: Any) -> str:
    """Accept only ``wavenumber`` or ``unknown`` for the FTIR X axis."""
    if not isinstance(value, str) or not value.strip():
        raise _invalid(
            "FTIR axis quantity must be 'wavenumber' or 'unknown'.",
            code="ftir_invalid_axis_quantity",
            value=repr(value),
        )
    key = value.strip().casefold()
    if key not in FTIR_AXIS_QUANTITIES:
        raise _invalid(
            "Unsupported FTIR axis quantity.",
            code="ftir_unsupported_axis_quantity",
            value=value,
            allowed=list(FTIR_AXIS_QUANTITIES),
        )
    return key


def normalize_axis_unit(value: Any) -> str | None:
    """Return ``cm^-1`` for explicit aliases, or ``None`` when unknown."""
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _invalid(
            "FTIR axis unit must be text or None.",
            code="ftir_invalid_axis_unit",
            value=repr(value),
        )
    key = value.strip().replace(" ", "")
    canonical = _UNIT_ALIASES.get(key)
    if canonical is None:
        raise _invalid(
            "The FTIR importer only accepts the explicitly supplied unit "
            "'cm^-1'; no unit conversion is performed.",
            code="ftir_unsupported_axis_unit",
            value=value,
            allowed=list(FTIR_AXIS_UNITS),
        )
    return canonical


@dataclass(frozen=True)
class FTIRMetadata:
    """Validated FTIR technical metadata stored with a Spectrum1D."""

    acquisition_mode: str = "Unknown"
    atr_correction_status: str = "unknown"
    signal_semantics: str = "unknown"
    axis_unit: str | None = None
    source_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "acquisition_mode",
            normalize_acquisition_mode(self.acquisition_mode),
        )
        object.__setattr__(
            self,
            "atr_correction_status",
            normalize_atr_correction_status(self.atr_correction_status),
        )
        object.__setattr__(
            self,
            "signal_semantics",
            normalize_signal_semantics(self.signal_semantics),
        )
        object.__setattr__(self, "axis_unit", normalize_axis_unit(self.axis_unit))
        if not isinstance(self.source_metadata, Mapping):
            raise _invalid(
                "FTIR source_metadata must be a mapping.",
                code="ftir_invalid_metadata",
                field="source_metadata",
            )
        object.__setattr__(
            self,
            "source_metadata",
            MappingProxyType(dict(self.source_metadata)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "acquisition_mode": self.acquisition_mode,
            "atr_correction_status": self.atr_correction_status,
            "signal_semantics": self.signal_semantics,
            "axis_unit": self.axis_unit,
            "source_metadata": dict(self.source_metadata),
        }


__all__ = [
    "ACQUISITION_MODES",
    "ATR_CORRECTION_STATUSES",
    "ATRCorrectionStatus",
    "AcquisitionMode",
    "FTIR_AXIS_QUANTITIES",
    "FTIR_AXIS_UNITS",
    "FTIR_SIGNAL_SEMANTICS",
    "FTIRMetadata",
    "normalize_acquisition_mode",
    "normalize_atr_correction_status",
    "normalize_axis_quantity",
    "normalize_axis_unit",
    "normalize_signal_semantics",
]
