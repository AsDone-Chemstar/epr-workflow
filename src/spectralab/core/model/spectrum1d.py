"""Technique-independent one-dimensional spectrum container."""

from __future__ import annotations

from dataclasses import dataclass, field

from spectralab.core.errors import SpectrumValidationError
from spectralab.core.model.axis import Axis1D
from spectralab.core.model.metadata import SpectrumMetadata
from spectralab.core.model.provenance import Provenance
from spectralab.core.model.signal import Signal1D
from spectralab.core.model.values import required_text


@dataclass(frozen=True)
class Spectrum1D:
    """An imported one-dimensional spectrum.

    This object represents the raw imported state only. Processing results are
    deliberately not stored here; a later milestone will introduce a separate
    processed-result object. The raw arrays are read-only float64 arrays
    created by :class:`Axis1D` and :class:`Signal1D`.

    The model does not assume magnetic field, ascending order, a particular
    signal meaning or a particular unit. Missing metadata stays ``None``/empty
    and is listed in ``metadata.unknown_fields``.
    """

    dataset_id: str
    axis: Axis1D
    raw_signal: Signal1D
    metadata: SpectrumMetadata
    provenance: Provenance = field(default_factory=Provenance)

    def __post_init__(self) -> None:
        dataset_id = required_text(
            self.dataset_id,
            field="spectrum.dataset_id",
            error_cls=SpectrumValidationError,
        )
        object.__setattr__(self, "dataset_id", dataset_id)

        if not isinstance(self.axis, Axis1D):
            raise SpectrumValidationError(
                "spectrum.axis must be an Axis1D.",
                code="axis_type",
            )
        if not isinstance(self.raw_signal, Signal1D):
            raise SpectrumValidationError(
                "spectrum.raw_signal must be a Signal1D.",
                code="signal_type",
            )
        if not isinstance(self.metadata, SpectrumMetadata):
            raise SpectrumValidationError(
                "spectrum.metadata must be SpectrumMetadata.",
                code="metadata_type",
            )
        if not isinstance(self.provenance, Provenance):
            raise SpectrumValidationError(
                "spectrum.provenance must be Provenance.",
                code="provenance_type",
            )

        axis_count = self.axis.point_count
        signal_count = self.raw_signal.point_count
        if axis_count != signal_count:
            raise SpectrumValidationError(
                "Axis and signal lengths differ "
                f"({axis_count} != {signal_count}).",
                code="length",
                context={"axis": axis_count, "signal": signal_count},
            )

    @property
    def point_count(self) -> int:
        return self.axis.point_count

    @property
    def x_values(self):
        return self.axis.values

    @property
    def y_values(self):
        return self.raw_signal.values

    @property
    def technique(self) -> str:
        return self.metadata.technique

    @property
    def source_format(self) -> str | None:
        """Format identifier recorded in provenance, if any."""
        value = self.provenance.format_metadata.get("source_format")
        return value if isinstance(value, str) and value else None

    def __len__(self) -> int:
        return self.point_count


__all__ = ["Spectrum1D"]
