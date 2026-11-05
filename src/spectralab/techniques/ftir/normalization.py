"""Explicit FTIR normalization operations.

The algorithms are technique-specific and Qt-free. Generic session state,
undo/redo and provenance remain in :mod:`spectralab.core.processing`.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

import numpy as np

from spectralab.core.errors import ProcessingError
from spectralab.core.model import Axis1D, Signal1D
from spectralab.core.processing import OperationOutput

NormalizationMethod = Literal["min_max", "max_abs", "l2"]
NORMALIZATION_METHODS: tuple[str, ...] = ("min_max", "max_abs", "l2")
_METHOD_ALIASES = {
    "min_max": "min_max",
    "min-max": "min_max",
    "minmax": "min_max",
    "max_abs": "max_abs",
    "max-abs": "max_abs",
    "maxabs": "max_abs",
    "l2": "l2",
    "l2_norm": "l2",
}
_METHOD_NAMES = {
    "min_max": "Min-Max normalization",
    "max_abs": "Maximum absolute value normalization",
    "l2": "L2 norm normalization",
}


class FTIRNormalizationError(ProcessingError):
    """A normalization method or denominator is scientifically invalid."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "ftir_normalization",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, context=dict(context or {}))


def normalize_method(value: str) -> NormalizationMethod:
    """Return a canonical normalization method or raise explicitly."""
    if not isinstance(value, str) or not value.strip():
        raise FTIRNormalizationError(
            "Normalization method must be non-empty text.",
            code="ftir_normalization_method",
            context={"value": repr(value)},
        )
    key = value.strip().casefold()
    canonical = _METHOD_ALIASES.get(key)
    if canonical is None:
        raise FTIRNormalizationError(
            f"Unsupported normalization method: {value!r}",
            code="ftir_normalization_method",
            context={"value": value, "allowed": list(NORMALIZATION_METHODS)},
        )
    return canonical  # type: ignore[return-value]


def normalize_values(values: Any, method: str) -> np.ndarray:
    """Return a fresh float64 normalized copy of one finite signal."""
    canonical = normalize_method(method)
    try:
        raw = np.asarray(values)
        if np.iscomplexobj(raw):
            raise FTIRNormalizationError(
                "Normalization input must be real-valued.",
                code="ftir_normalization_input",
                context={"dtype": str(raw.dtype)},
            )
        array = np.asarray(values, dtype=np.float64)
    except FTIRNormalizationError:
        raise
    except (TypeError, ValueError) as exc:
        raise FTIRNormalizationError(
            "Normalization input must be a real numeric array.",
            code="ftir_normalization_input",
            context={"error": str(exc)},
        ) from exc
    if array.ndim != 1:
        raise FTIRNormalizationError(
            "Normalization input must be one-dimensional.",
            code="ftir_normalization_input",
            context={"ndim": int(array.ndim)},
        )
    if array.size == 0:
        raise FTIRNormalizationError(
            "Normalization input must contain at least one value.",
            code="ftir_normalization_input",
            context={"size": 0},
        )
    if not np.all(np.isfinite(array)):
        index = int(np.flatnonzero(~np.isfinite(array))[0])
        raise FTIRNormalizationError(
            "Normalization input contains a non-finite value.",
            code="ftir_normalization_nonfinite_input",
            context={"index": index},
        )

    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        if canonical == "min_max":
            minimum = float(np.min(array))
            maximum = float(np.max(array))
            denominator = maximum - minimum
            if denominator == 0.0:
                raise FTIRNormalizationError(
                    "Min-Max normalization is undefined for a constant "
                    "signal: max(y) - min(y) is zero.",
                    code="ftir_normalization_zero_denominator",
                    context={
                        "method": canonical,
                        "minimum": minimum,
                        "maximum": maximum,
                    },
                )
            result = (array - minimum) / denominator
        elif canonical == "max_abs":
            denominator = float(np.max(np.abs(array)))
            if denominator == 0.0:
                raise FTIRNormalizationError(
                    "Maximum-absolute normalization is undefined for an "
                    "all-zero signal.",
                    code="ftir_normalization_zero_denominator",
                    context={"method": canonical},
                )
            result = array / denominator
        else:
            squared_sum = float(np.sum(array * array, dtype=np.float64))
            denominator = float(np.sqrt(squared_sum))
            if denominator == 0.0:
                raise FTIRNormalizationError(
                    "L2 normalization is undefined for an all-zero signal.",
                    code="ftir_normalization_zero_denominator",
                    context={"method": canonical},
                )
            result = array / denominator

    if not np.isfinite(denominator):
        raise FTIRNormalizationError(
            "Normalization denominator is not finite.",
            code="ftir_normalization_nonfinite_denominator",
            context={"method": canonical, "denominator": denominator},
        )
    if not np.all(np.isfinite(result)):
        raise FTIRNormalizationError(
            "Normalization produced a non-finite value.",
            code="ftir_normalization_nonfinite_output",
            context={"method": canonical},
        )

    return np.asarray(result, dtype=np.float64, copy=True)


class FTIRNormalizationOperation:
    """One explicit normalization operation for a ProcessingSession."""

    technique = "ftir"
    version = "1.0.0"
    changes_axis = False
    axis_change_description = None
    changes_signal_semantics = False
    changes_signal_unit = False
    signal_change_description = None

    def __init__(self, method: str) -> None:
        self.method = normalize_method(method)
        self.operation_id = f"ftir.normalize.{self.method}"
        self.name = _METHOD_NAMES[self.method]
        self.parameters: dict[str, Any] = {"method": self.method}

    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput:
        values = normalize_values(signal.values, self.method)
        normalized = Signal1D(
            values=values,
            semantics=signal.semantics,
            unit=signal.unit,
            name=signal.name,
            metadata_source=signal.metadata_source,
            missing_reason=signal.missing_reason,
        )
        return OperationOutput(
            axis=axis,
            signal=normalized,
            assumptions=(
                "Normalization is an explicit mathematical scaling; signal "
                "semantics and unit were preserved, and no baseline, ATR or "
                "other correction was applied.",
            ),
            diagnostics={
                "method": self.method,
                "point_count": normalized.point_count,
            },
        )


def create_normalization_operation(method: str) -> FTIRNormalizationOperation:
    """Create one operation for an explicit user-selected method."""
    return FTIRNormalizationOperation(method)


__all__ = [
    "FTIRNormalizationError",
    "FTIRNormalizationOperation",
    "NORMALIZATION_METHODS",
    "NormalizationMethod",
    "create_normalization_operation",
    "normalize_method",
    "normalize_values",
]
