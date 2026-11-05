"""Technique-independent one-dimensional signal model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from spectralab.core.errors import SignalValidationError
from spectralab.core.model.values import optional_text, readonly_float_array

SignalSemantics = Literal[
    "intensity",
    "absorbance",
    "transmittance",
    "first_derivative",
    "unknown",
]

SIGNAL_SEMANTICS: frozenset[str] = frozenset(
    {
        "intensity",
        "absorbance",
        "transmittance",
        "first_derivative",
        "unknown",
    }
)


@dataclass(frozen=True)
class Signal1D:
    """One real-valued dependent-variable channel.

    The model stores only the declared semantics; it never infers absorbance,
    transmittance, intensity or derivative meaning from values or metadata.
    ``unit=None`` explicitly means that the unit is unknown or undocumented.
    """

    values: np.ndarray
    semantics: SignalSemantics
    unit: str | None = None
    name: str | None = None
    metadata_source: str = "unknown"
    missing_reason: str | None = None

    def __post_init__(self) -> None:
        values = readonly_float_array(
            self.values,
            field="signal.values",
            error_cls=SignalValidationError,
        )
        object.__setattr__(self, "values", values)

        if self.semantics not in SIGNAL_SEMANTICS:
            raise SignalValidationError(
                f"Unsupported signal semantics: {self.semantics!r}",
                code="signal_semantics",
                context={"semantics": self.semantics},
            )
        unit = optional_text(
            self.unit, field="signal.unit", error_cls=SignalValidationError
        )
        name = optional_text(
            self.name, field="signal.name", error_cls=SignalValidationError
        )
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "name", name)

        if not isinstance(self.metadata_source, str) or not self.metadata_source:
            raise SignalValidationError(
                "signal.metadata_source must be a non-empty string.",
                code="metadata_source",
            )
        if self.missing_reason is not None and not isinstance(
            self.missing_reason, str
        ):
            raise SignalValidationError(
                "signal.missing_reason must be text or None.",
                code="missing_reason",
            )

    @property
    def point_count(self) -> int:
        return int(self.values.size)

    @property
    def unit_is_known(self) -> bool:
        return self.unit is not None

    @property
    def semantics_is_known(self) -> bool:
        return self.semantics != "unknown"


__all__ = ["SIGNAL_SEMANTICS", "Signal1D", "SignalSemantics"]
