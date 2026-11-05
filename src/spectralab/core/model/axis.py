"""Technique-independent one-dimensional X-axis model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from spectralab.core.errors import AxisValidationError
from spectralab.core.model.values import optional_text, readonly_float_array

AxisDirection = Literal["increasing", "decreasing", "unknown"]
AxisQuantity = Literal[
    "magnetic_field",
    "wavenumber",
    "wavelength",
    "frequency",
    "time",
    "index",
    "unknown",
]

AXIS_DIRECTIONS: frozenset[str] = frozenset(
    {"increasing", "decreasing", "unknown"}
)
AXIS_QUANTITIES: frozenset[str] = frozenset(
    {
        "magnetic_field",
        "wavenumber",
        "wavelength",
        "frequency",
        "time",
        "index",
        "unknown",
    }
)


def infer_axis_direction(values: np.ndarray) -> AxisDirection:
    """Describe strict monotonic direction without sorting or modifying values."""
    differences = np.diff(values)
    if np.all(differences > 0):
        return "increasing"
    if np.all(differences < 0):
        return "decreasing"
    return "unknown"


@dataclass(frozen=True)
class Axis1D:
    """One independent-variable axis.

    ``values`` are preserved in the original point order as a read-only
    float64 array. ``direction`` is descriptive; it never causes sorting,
    reversal or resampling.

    Duplicate or non-monotonic values have ``direction='unknown'``. They are
    accepted only when the caller explicitly passes ``direction='unknown'``;
    otherwise construction fails. This prevents accidental use of such an axis
    in operations that assume strict monotonicity, while still allowing
    faithful representation when the caller deliberately marks direction as
    unknown.
    """

    values: np.ndarray
    quantity: AxisQuantity
    unit: str | None = None
    name: str | None = None
    direction: AxisDirection | None = None
    metadata_source: str = "unknown"
    missing_reason: str | None = None

    def __post_init__(self) -> None:
        values = readonly_float_array(
            self.values,
            field="axis.values",
            error_cls=AxisValidationError,
        )
        object.__setattr__(self, "values", values)

        if self.quantity not in AXIS_QUANTITIES:
            raise AxisValidationError(
                f"Unsupported axis quantity: {self.quantity!r}",
                code="axis_quantity",
                context={"quantity": self.quantity},
            )
        unit = optional_text(
            self.unit, field="axis.unit", error_cls=AxisValidationError
        )
        name = optional_text(
            self.name, field="axis.name", error_cls=AxisValidationError
        )
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "name", name)

        inferred = infer_axis_direction(values)
        direction = self.direction
        if direction is None:
            if inferred == "unknown":
                raise AxisValidationError(
                    "Axis values are not strictly monotonic. Pass "
                    "direction='unknown' explicitly if this is intentional; "
                    "the model will preserve the original order and will not "
                    "sort or repair it.",
                    code="axis_not_monotonic",
                    context={"inferred": inferred},
                )
            object.__setattr__(self, "direction", inferred)
        else:
            if direction not in AXIS_DIRECTIONS:
                raise AxisValidationError(
                    f"Unsupported axis direction: {direction!r}",
                    code="axis_direction",
                    context={"direction": direction},
                )
            if inferred == "unknown" and direction != "unknown":
                raise AxisValidationError(
                    f"Axis values are not {direction}; direction cannot be "
                    "inferred from the values.",
                    code="axis_direction",
                    context={"direction": direction, "inferred": inferred},
                )
            if inferred != "unknown" and direction not in (inferred, "unknown"):
                raise AxisValidationError(
                    f"Axis direction {direction!r} contradicts the values "
                    f"({inferred!r}).",
                    code="axis_direction",
                    context={"direction": direction, "inferred": inferred},
                )
            object.__setattr__(self, "direction", direction)

        if not isinstance(self.metadata_source, str) or not self.metadata_source:
            raise AxisValidationError(
                "axis.metadata_source must be a non-empty string.",
                code="metadata_source",
            )
        if self.missing_reason is not None and not isinstance(
            self.missing_reason, str
        ):
            raise AxisValidationError(
                "axis.missing_reason must be text or None.",
                code="missing_reason",
            )

    @property
    def point_count(self) -> int:
        return int(self.values.size)

    @property
    def is_known_direction(self) -> bool:
        return self.direction in ("increasing", "decreasing")


__all__ = [
    "AXIS_DIRECTIONS",
    "AXIS_QUANTITIES",
    "Axis1D",
    "AxisDirection",
    "AxisQuantity",
    "infer_axis_direction",
]
