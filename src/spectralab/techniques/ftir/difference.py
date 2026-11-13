"""Explicit FTIR difference spectra (``Spectrum A - Spectrum B``).

The operation is deliberately separate from :class:`ProcessingSession`: a
difference depends on two datasets, so it cannot be represented as one
single-source processing history entry without losing source identity.

Two X-axis matching modes are supported:

``exact``
    Both X arrays must have equal length and exactly equal float64 values in
    the same order. Comparison uses ``numpy.array_equal``; there is no
    numerical tolerance, sorting or reversal.

``interpolate``
    Spectrum A's X points inside the common overlap are used as the target
    axis. Spectrum B is linearly interpolated onto that target with
    ``numpy.interp``. The operation never extrapolates and never modifies a
    source array.

This module is Qt-free and does not import the GUI or legacy EPR code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from spectralab.core.errors import ProcessingError
from spectralab.core.model import Axis1D, Signal1D

DifferenceAxisMatch = Literal["exact", "interpolate"]
DifferenceSource = Literal["raw", "processed"]

DIFFERENCE_AXIS_MATCHES: tuple[str, ...] = ("exact", "interpolate")
DIFFERENCE_SOURCES: tuple[str, ...] = ("raw", "processed")
DIFFERENCE_ALGORITHM_VERSION = "1.0.0"
ALGORITHM_EXACT = "direct_subtraction"
ALGORITHM_INTERPOLATED = "linear_interpolation"
INTERPOLATION_METHOD = "linear"
EXACT_COMPARISON_POLICY = (
    "numpy.array_equal on float64 X arrays: equal length, identical values "
    "in identical order; no tolerance, sorting or reversal."
)
INTERPOLATION_POLICY = (
    "Spectrum A X points inside the closed common overlap are the target "
    "axis; Spectrum B is linearly interpolated onto those points with "
    "numpy.interp. No extrapolation, sorting or reversal is used."
)
ARITHMETIC_DEFINITION = "A - B"
LIMITATIONS: tuple[str, ...] = (
    "Interpolation mode uses only the closed common X-axis overlap; points "
    "outside it are excluded rather than extrapolated.",
    "Interpolation is linear only; no spline, smoothing or alignment is used.",
    "Difference results are not written to either source ProcessingSession.",
    "Dataset identity is compared by dataset_id; different IDs are treated "
    "as distinct even if their numeric arrays are identical.",
    "M14 does not implement a general difference-result export path.",
)


class FTIRDifferenceError(ProcessingError):
    """A difference-spectrum input, parameter or result is invalid."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "ftir_difference",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, context=dict(context or {}))


def _axis_match(value: Any) -> DifferenceAxisMatch:
    if not isinstance(value, str):
        raise FTIRDifferenceError(
            "axis_match must be 'exact' or 'interpolate'.",
            code="ftir_difference_invalid_parameter",
            context={"field": "axis_match", "value": repr(value)},
        )
    key = value.strip().casefold()
    if key not in DIFFERENCE_AXIS_MATCHES:
        raise FTIRDifferenceError(
            "axis_match must be 'exact' or 'interpolate'.",
            code="ftir_difference_invalid_parameter",
            context={
                "field": "axis_match",
                "value": value,
                "allowed": list(DIFFERENCE_AXIS_MATCHES),
            },
        )
    return key  # type: ignore[return-value]


def _source(value: Any, *, field: str) -> DifferenceSource:
    if not isinstance(value, str):
        raise FTIRDifferenceError(
            f"{field} must be 'raw' or 'processed'.",
            code="ftir_difference_invalid_parameter",
            context={"field": field, "value": repr(value)},
        )
    key = value.strip().casefold()
    if key not in DIFFERENCE_SOURCES:
        raise FTIRDifferenceError(
            f"{field} must be 'raw' or 'processed'.",
            code="ftir_difference_invalid_parameter",
            context={
                "field": field,
                "value": value,
                "allowed": list(DIFFERENCE_SOURCES),
            },
        )
    return key  # type: ignore[return-value]


@dataclass(frozen=True)
class DifferenceParameters:
    """Explicit difference-spectrum settings.

    ``source_a`` and ``source_b`` are independent; the caller must choose
    both explicitly. ``axis_match='interpolate'`` always uses Spectrum A as
    the target axis. No default interpolation is performed.
    """

    axis_match: DifferenceAxisMatch = "exact"
    source_a: DifferenceSource = "raw"
    source_b: DifferenceSource = "raw"

    def __post_init__(self) -> None:
        object.__setattr__(self, "axis_match", _axis_match(self.axis_match))
        object.__setattr__(
            self,
            "source_a",
            _source(self.source_a, field="source_a"),
        )
        object.__setattr__(
            self,
            "source_b",
            _source(self.source_b, field="source_b"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "axis_match": self.axis_match,
            "source_a": self.source_a,
            "source_b": self.source_b,
            "interpolation_target": (
                "a" if self.axis_match == "interpolate" else None
            ),
        }


@dataclass(frozen=True)
class DifferenceInterpolation:
    """Description and aligned values for explicit linear interpolation."""

    method: str
    target_dataset_id: str
    interpolated_dataset_id: str
    target_point_count: int
    overlap_low: float
    overlap_high: float
    extrapolation: str
    endpoint_policy: str
    aligned_b_signal: Signal1D = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.method != INTERPOLATION_METHOD:
            raise FTIRDifferenceError(
                "Only linear interpolation is supported.",
                code="ftir_difference_invalid_result",
                context={"method": self.method},
            )
        for field_name in ("target_dataset_id", "interpolated_dataset_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise FTIRDifferenceError(
                    f"DifferenceInterpolation.{field_name} must be non-empty "
                    "text.",
                    code="ftir_difference_invalid_result",
                )
        if (
            isinstance(self.target_point_count, bool)
            or not isinstance(self.target_point_count, int)
            or self.target_point_count < 2
        ):
            raise FTIRDifferenceError(
                "DifferenceInterpolation.target_point_count must be at least 2.",
                code="ftir_difference_invalid_result",
            )
        for field_name in ("overlap_low", "overlap_high"):
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise FTIRDifferenceError(
                    f"DifferenceInterpolation.{field_name} must be numeric.",
                    code="ftir_difference_invalid_result",
                )
            if not np.isfinite(float(value)):
                raise FTIRDifferenceError(
                    f"DifferenceInterpolation.{field_name} must be finite.",
                    code="ftir_difference_invalid_result",
                )
        if self.extrapolation != "none":
            raise FTIRDifferenceError(
                "Difference interpolation must not extrapolate.",
                code="ftir_difference_invalid_result",
            )
        if not isinstance(self.endpoint_policy, str) or not self.endpoint_policy:
            raise FTIRDifferenceError(
                "DifferenceInterpolation.endpoint_policy must be non-empty "
                "text.",
                code="ftir_difference_invalid_result",
            )
        if not isinstance(self.aligned_b_signal, Signal1D):
            raise FTIRDifferenceError(
                "DifferenceInterpolation.aligned_b_signal must be a Signal1D.",
                code="ftir_difference_invalid_result",
            )
        if self.aligned_b_signal.point_count != self.target_point_count:
            raise FTIRDifferenceError(
                "Interpolated Signal B length does not match the target axis.",
                code="ftir_difference_invalid_result",
                context={
                    "target": self.target_point_count,
                    "signal": self.aligned_b_signal.point_count,
                },
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "target_dataset_id": self.target_dataset_id,
            "interpolated_dataset_id": self.interpolated_dataset_id,
            "target_point_count": self.target_point_count,
            "overlap_low": self.overlap_low,
            "overlap_high": self.overlap_high,
            "extrapolation": self.extrapolation,
            "endpoint_policy": self.endpoint_policy,
            "aligned_b_point_count": self.aligned_b_signal.point_count,
        }


@dataclass(frozen=True)
class DifferenceResult:
    """An immutable difference result with complete source provenance."""

    axis: Axis1D
    signal: Signal1D
    aligned_a_signal: Signal1D
    aligned_b_signal: Signal1D
    dataset_a_id: str
    dataset_b_id: str
    source_a: DifferenceSource
    source_b: DifferenceSource
    parameters: DifferenceParameters
    axis_match: DifferenceAxisMatch
    interpolation: DifferenceInterpolation | None = None
    source_operation_history_a: tuple[str, ...] = ()
    source_operation_history_b: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = LIMITATIONS
    algorithm: str = ALGORITHM_EXACT
    algorithm_version: str = DIFFERENCE_ALGORITHM_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.axis, Axis1D):
            raise FTIRDifferenceError(
                "DifferenceResult.axis must be an Axis1D.",
                code="ftir_difference_invalid_result",
            )
        if not isinstance(self.signal, Signal1D):
            raise FTIRDifferenceError(
                "DifferenceResult.signal must be a Signal1D.",
                code="ftir_difference_invalid_result",
            )
        if self.axis.point_count != self.signal.point_count:
            raise FTIRDifferenceError(
                "DifferenceResult axis and signal lengths differ.",
                code="ftir_difference_invalid_result",
                context={
                    "axis": self.axis.point_count,
                    "signal": self.signal.point_count,
                },
            )
        for field_name in ("aligned_a_signal", "aligned_b_signal"):
            signal = getattr(self, field_name)
            if not isinstance(signal, Signal1D):
                raise FTIRDifferenceError(
                    f"DifferenceResult.{field_name} must be a Signal1D.",
                    code="ftir_difference_invalid_result",
                )
            if signal.point_count != self.axis.point_count:
                raise FTIRDifferenceError(
                    f"DifferenceResult.{field_name} does not match the "
                    "result axis.",
                    code="ftir_difference_invalid_result",
                    context={
                        "axis": self.axis.point_count,
                        "signal": signal.point_count,
                    },
                )
        for field_name in ("dataset_a_id", "dataset_b_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise FTIRDifferenceError(
                    f"DifferenceResult.{field_name} must be non-empty text.",
                    code="ftir_difference_invalid_result",
                )
        if self.dataset_a_id == self.dataset_b_id:
            raise FTIRDifferenceError(
                "Difference result source A and B must be different datasets.",
                code="ftir_difference_same_dataset",
            )
        if not isinstance(self.parameters, DifferenceParameters):
            raise FTIRDifferenceError(
                "DifferenceResult.parameters must be DifferenceParameters.",
                code="ftir_difference_invalid_result",
            )
        if self.source_a != self.parameters.source_a:
            raise FTIRDifferenceError(
                "DifferenceResult.source_a does not match its parameters.",
                code="ftir_difference_invalid_result",
            )
        if self.source_b != self.parameters.source_b:
            raise FTIRDifferenceError(
                "DifferenceResult.source_b does not match its parameters.",
                code="ftir_difference_invalid_result",
            )
        if self.axis_match not in DIFFERENCE_AXIS_MATCHES:
            raise FTIRDifferenceError(
                "DifferenceResult.axis_match is invalid.",
                code="ftir_difference_invalid_result",
            )
        if self.axis_match == "interpolate":
            if self.interpolation is None:
                raise FTIRDifferenceError(
                    "An interpolated difference needs interpolation metadata.",
                    code="ftir_difference_invalid_result",
                )
            if (
                self.interpolation.aligned_b_signal.point_count
                != self.axis.point_count
            ):
                raise FTIRDifferenceError(
                    "Interpolated Signal B does not match the result axis.",
                    code="ftir_difference_invalid_result",
                )
            if self.interpolation.target_dataset_id != self.dataset_a_id:
                raise FTIRDifferenceError(
                    "Interpolation target dataset is not Spectrum A.",
                    code="ftir_difference_invalid_result",
                )
            if (
                self.interpolation.interpolated_dataset_id
                != self.dataset_b_id
            ):
                raise FTIRDifferenceError(
                    "Interpolated dataset is not Spectrum B.",
                    code="ftir_difference_invalid_result",
                )
            expected_algorithm = ALGORITHM_INTERPOLATED
        else:
            if self.interpolation is not None:
                raise FTIRDifferenceError(
                    "An exact difference must not contain interpolation "
                    "metadata.",
                    code="ftir_difference_invalid_result",
                )
            expected_algorithm = ALGORITHM_EXACT
        if self.algorithm != expected_algorithm:
            raise FTIRDifferenceError(
                "DifferenceResult.algorithm does not match its axis mode.",
                code="ftir_difference_invalid_result",
                context={
                    "algorithm": self.algorithm,
                    "expected": expected_algorithm,
                },
            )
        if (
            not isinstance(self.algorithm_version, str)
            or not self.algorithm_version.strip()
        ):
            raise FTIRDifferenceError(
                "DifferenceResult.algorithm_version must be non-empty text.",
                code="ftir_difference_invalid_result",
            )
        for field_name in (
            "source_operation_history_a",
            "source_operation_history_b",
            "warnings",
            "assumptions",
            "limitations",
        ):
            values = tuple(getattr(self, field_name))
            if any(not isinstance(item, str) for item in values):
                raise FTIRDifferenceError(
                    f"DifferenceResult.{field_name} must contain text.",
                    code="ftir_difference_invalid_result",
                )
            object.__setattr__(self, field_name, values)

    @property
    def point_count(self) -> int:
        return self.axis.point_count

    @property
    def operation(self) -> str:
        return ARITHMETIC_DEFINITION

    def as_dict(self) -> dict[str, Any]:
        """Return provenance-ready metadata without signal arrays."""
        return {
            "algorithm": self.algorithm,
            "algorithm_version": self.algorithm_version,
            "operation": ARITHMETIC_DEFINITION,
            "axis_match": self.axis_match,
            "parameters": self.parameters.as_dict(),
            "dataset_a_id": self.dataset_a_id,
            "dataset_b_id": self.dataset_b_id,
            "source_a": self.source_a,
            "source_b": self.source_b,
            "source_operation_history_a": list(
                self.source_operation_history_a
            ),
            "source_operation_history_b": list(
                self.source_operation_history_b
            ),
            "axis": {
                "quantity": self.axis.quantity,
                "unit": self.axis.unit,
                "name": self.axis.name,
                "direction": self.axis.direction,
                "point_count": self.axis.point_count,
            },
            "signal": {
                "semantics": self.signal.semantics,
                "unit": self.signal.unit,
                "point_count": self.signal.point_count,
            },
            "aligned": {
                "a_point_count": self.aligned_a_signal.point_count,
                "b_point_count": self.aligned_b_signal.point_count,
            },
            "interpolation": (
                None
                if self.interpolation is None
                else self.interpolation.as_dict()
            ),
            "warnings": list(self.warnings),
            "assumptions": list(self.assumptions),
            "limitations": list(self.limitations),
        }


def _validate_axis_signal_pair(
    axis: Any,
    signal: Any,
    *,
    side: str,
) -> None:
    if not isinstance(axis, Axis1D):
        raise FTIRDifferenceError(
            f"Spectrum {side} requires an Axis1D.",
            code="ftir_difference_invalid_input",
            context={"side": side},
        )
    if not isinstance(signal, Signal1D):
        raise FTIRDifferenceError(
            f"Spectrum {side} requires a Signal1D.",
            code="ftir_difference_invalid_input",
            context={"side": side},
        )
    if axis.point_count != signal.point_count:
        raise FTIRDifferenceError(
            f"Spectrum {side} axis and signal lengths differ.",
            code="ftir_difference_invalid_input",
            context={
                "side": side,
                "axis": axis.point_count,
                "signal": signal.point_count,
            },
        )


def _require_known_direction(axis: Axis1D, *, side: str) -> None:
    if not axis.is_known_direction:
        raise FTIRDifferenceError(
            f"Spectrum {side} X axis is not strictly monotonic; difference "
            "calculation is rejected.",
            code="ftir_difference_axis_not_monotonic",
            context={
                "side": side,
                "direction": str(axis.direction),
            },
        )


def _validate_compatibility(
    axis_a: Axis1D,
    signal_a: Signal1D,
    axis_b: Axis1D,
    signal_b: Signal1D,
) -> None:
    """Reject incompatible axes/signals without inferring missing metadata."""
    _require_known_direction(axis_a, side="A")
    _require_known_direction(axis_b, side="B")

    if axis_a.quantity != axis_b.quantity:
        raise FTIRDifferenceError(
            "Spectra A and B have different X-axis quantities.",
            code="ftir_difference_axis_quantity",
            context={
                "quantity_a": axis_a.quantity,
                "quantity_b": axis_b.quantity,
            },
        )
    if axis_a.quantity == "unknown":
        raise FTIRDifferenceError(
            "The X-axis quantity is unknown for both spectra; compatibility "
            "cannot be established.",
            code="ftir_difference_axis_quantity_unknown",
        )
    if axis_a.unit != axis_b.unit:
        raise FTIRDifferenceError(
            "Spectra A and B have different X-axis units.",
            code="ftir_difference_axis_unit",
            context={"unit_a": axis_a.unit, "unit_b": axis_b.unit},
        )

    if signal_a.semantics != signal_b.semantics:
        raise FTIRDifferenceError(
            "Spectra A and B have different signal semantics.",
            code="ftir_difference_signal_semantics",
            context={
                "semantics_a": signal_a.semantics,
                "semantics_b": signal_b.semantics,
            },
        )
    if signal_a.semantics == "unknown":
        raise FTIRDifferenceError(
            "Signal semantics are unknown for both spectra; compatibility "
            "cannot be established.",
            code="ftir_difference_signal_semantics_unknown",
        )
    if signal_a.unit != signal_b.unit:
        raise FTIRDifferenceError(
            "Spectra A and B have different signal units.",
            code="ftir_difference_signal_unit",
            context={"unit_a": signal_a.unit, "unit_b": signal_b.unit},
        )


def _validate_dataset_identity(dataset_a_id: Any, dataset_b_id: Any) -> None:
    for field_name, value in (
        ("dataset_a_id", dataset_a_id),
        ("dataset_b_id", dataset_b_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise FTIRDifferenceError(
                f"{field_name} must be non-empty text.",
                code="ftir_difference_invalid_input",
                context={"field": field_name},
            )
    if dataset_a_id == dataset_b_id:
        raise FTIRDifferenceError(
            "Spectrum A and Spectrum B must be different datasets.",
            code="ftir_difference_same_dataset",
            context={"dataset_id": dataset_a_id},
        )


def _exact_difference(
    axis_a: Axis1D,
    signal_a: Signal1D,
    axis_b: Axis1D,
    signal_b: Signal1D,
    parameters: DifferenceParameters,
    *,
    dataset_a_id: str,
    dataset_b_id: str,
    history_a: Sequence[str],
    history_b: Sequence[str],
) -> DifferenceResult:
    if axis_a.point_count != axis_b.point_count:
        raise FTIRDifferenceError(
            "Exact subtraction requires equal point counts.",
            code="ftir_difference_point_count",
            context={
                "points_a": axis_a.point_count,
                "points_b": axis_b.point_count,
                "policy": EXACT_COMPARISON_POLICY,
            },
        )
    if not np.array_equal(axis_a.values, axis_b.values):
        mismatch = int(np.flatnonzero(axis_a.values != axis_b.values)[0])
        raise FTIRDifferenceError(
            "Exact subtraction requires identical X values in the same order.",
            code="ftir_difference_axis_values",
            context={
                "first_mismatch_index": mismatch,
                "x_a": float(axis_a.values[mismatch]),
                "x_b": float(axis_b.values[mismatch]),
                "policy": EXACT_COMPARISON_POLICY,
            },
        )

    values = np.asarray(signal_a.values, dtype=np.float64) - np.asarray(
        signal_b.values, dtype=np.float64
    )
    if not np.all(np.isfinite(values)):
        index = int(np.flatnonzero(~np.isfinite(values))[0])
        raise FTIRDifferenceError(
            "The difference contains a non-finite value.",
            code="ftir_difference_nonfinite_output",
            context={"index": index},
        )
    signal = Signal1D(
        values=values,
        semantics=signal_a.semantics,
        unit=signal_a.unit,
        name=None,
        metadata_source="ftir.difference",
        missing_reason="Difference spectrum; no source signal name was retained.",
    )
    aligned_a = Signal1D(
        values=signal_a.values,
        semantics=signal_a.semantics,
        unit=signal_a.unit,
        name=signal_a.name,
        metadata_source="ftir.difference.aligned_a",
        missing_reason=signal_a.missing_reason,
    )
    aligned_b = Signal1D(
        values=signal_b.values,
        semantics=signal_b.semantics,
        unit=signal_b.unit,
        name=signal_b.name,
        metadata_source="ftir.difference.aligned_b",
        missing_reason=signal_b.missing_reason,
    )
    return DifferenceResult(
        axis=axis_a,
        signal=signal,
        aligned_a_signal=aligned_a,
        aligned_b_signal=aligned_b,
        dataset_a_id=dataset_a_id,
        dataset_b_id=dataset_b_id,
        source_a=parameters.source_a,
        source_b=parameters.source_b,
        parameters=parameters,
        axis_match="exact",
        interpolation=None,
        source_operation_history_a=tuple(history_a),
        source_operation_history_b=tuple(history_b),
        assumptions=(
            "Subtraction is defined exactly as A - B.",
            EXACT_COMPARISON_POLICY,
        ),
    )


def _overlap_bounds(axis_a: Axis1D, axis_b: Axis1D) -> tuple[float, float]:
    low = max(float(axis_a.values.min()), float(axis_b.values.min()))
    high = min(float(axis_a.values.max()), float(axis_b.values.max()))
    if low >= high:
        raise FTIRDifferenceError(
            "The two X axes have no common overlap with at least two target "
            "points.",
            code="ftir_difference_no_overlap",
            context={
                "a_min": float(axis_a.values.min()),
                "a_max": float(axis_a.values.max()),
                "b_min": float(axis_b.values.min()),
                "b_max": float(axis_b.values.max()),
                "overlap_low": low,
                "overlap_high": high,
            },
        )
    return low, high


def _interpolated_difference(
    axis_a: Axis1D,
    signal_a: Signal1D,
    axis_b: Axis1D,
    signal_b: Signal1D,
    parameters: DifferenceParameters,
    *,
    dataset_a_id: str,
    dataset_b_id: str,
    history_a: Sequence[str],
    history_b: Sequence[str],
) -> DifferenceResult:
    low, high = _overlap_bounds(axis_a, axis_b)

    target_mask = (axis_a.values >= low) & (axis_a.values <= high)
    target_x = np.asarray(axis_a.values[target_mask], dtype=np.float64)
    target_y_a = np.asarray(signal_a.values[target_mask], dtype=np.float64)
    if target_x.size < 2:
        raise FTIRDifferenceError(
            "Interpolation requires at least two Spectrum A target points "
            "inside the common overlap.",
            code="ftir_difference_insufficient_points",
            context={"target_point_count": int(target_x.size)},
        )

    b_min = float(axis_b.values.min())
    b_max = float(axis_b.values.max())
    if np.any(target_x < b_min) or np.any(target_x > b_max):
        raise FTIRDifferenceError(
            "Interpolation would require extrapolation; the operation is "
            "rejected.",
            code="ftir_difference_extrapolation",
            context={
                "target_min": float(target_x.min()),
                "target_max": float(target_x.max()),
                "b_min": b_min,
                "b_max": b_max,
            },
        )

    # np.interp requires increasing sample points. A decreasing Spectrum B is
    # reversed only in this local working copy; the source object and the
    # output target order are never changed.
    if axis_b.direction == "decreasing":
        work_x = np.asarray(axis_b.values[::-1], dtype=np.float64)
        work_y = np.asarray(signal_b.values[::-1], dtype=np.float64)
    else:
        work_x = np.asarray(axis_b.values, dtype=np.float64)
        work_y = np.asarray(signal_b.values, dtype=np.float64)
    if work_x.size < 2 or np.any(np.diff(work_x) <= 0.0):
        raise FTIRDifferenceError(
            "Spectrum B X axis must be strictly monotonic for interpolation.",
            code="ftir_difference_axis_not_monotonic",
            context={"direction": str(axis_b.direction)},
        )

    aligned_b = np.interp(target_x, work_x, work_y)
    values = target_y_a - aligned_b
    if not np.all(np.isfinite(values)):
        index = int(np.flatnonzero(~np.isfinite(values))[0])
        raise FTIRDifferenceError(
            "The interpolated difference contains a non-finite value.",
            code="ftir_difference_nonfinite_output",
            context={"index": index},
        )

    target_axis = Axis1D(
        values=target_x,
        quantity=axis_a.quantity,
        unit=axis_a.unit,
        name=axis_a.name,
        direction=axis_a.direction,
        metadata_source="ftir.difference.target_a",
    )
    interpolated_signal = Signal1D(
        values=aligned_b,
        semantics=signal_b.semantics,
        unit=signal_b.unit,
        name=signal_b.name,
        metadata_source="ftir.difference.interpolated_b",
        missing_reason=signal_b.missing_reason,
    )
    difference_signal = Signal1D(
        values=values,
        semantics=signal_a.semantics,
        unit=signal_a.unit,
        name=None,
        metadata_source="ftir.difference",
        missing_reason="Difference spectrum; no source signal name was retained.",
    )
    aligned_a_signal = Signal1D(
        values=target_y_a,
        semantics=signal_a.semantics,
        unit=signal_a.unit,
        name=signal_a.name,
        metadata_source="ftir.difference.aligned_a",
        missing_reason=signal_a.missing_reason,
    )
    interpolation = DifferenceInterpolation(
        method=INTERPOLATION_METHOD,
        target_dataset_id=dataset_a_id,
        interpolated_dataset_id=dataset_b_id,
        target_point_count=int(target_axis.point_count),
        overlap_low=low,
        overlap_high=high,
        extrapolation="none",
        endpoint_policy=(
            "Closed overlap endpoints are included when they exist in "
            "Spectrum A's target axis."
        ),
        aligned_b_signal=interpolated_signal,
    )
    return DifferenceResult(
        axis=target_axis,
        signal=difference_signal,
        aligned_a_signal=aligned_a_signal,
        aligned_b_signal=interpolated_signal,
        dataset_a_id=dataset_a_id,
        dataset_b_id=dataset_b_id,
        source_a=parameters.source_a,
        source_b=parameters.source_b,
        parameters=parameters,
        axis_match="interpolate",
        interpolation=interpolation,
        algorithm=ALGORITHM_INTERPOLATED,
        source_operation_history_a=tuple(history_a),
        source_operation_history_b=tuple(history_b),
        assumptions=(
            "Subtraction is defined exactly as A - B.",
            INTERPOLATION_POLICY,
        ),
    )


def compute_difference(
    axis_a: Axis1D,
    signal_a: Signal1D,
    axis_b: Axis1D,
    signal_b: Signal1D,
    parameters: DifferenceParameters,
    *,
    dataset_a_id: str,
    dataset_b_id: str,
    source_operation_history_a: Sequence[str] = (),
    source_operation_history_b: Sequence[str] = (),
) -> DifferenceResult:
    """Compute ``A - B`` without modifying either source object."""
    if not isinstance(parameters, DifferenceParameters):
        raise FTIRDifferenceError(
            "compute_difference requires DifferenceParameters.",
            code="ftir_difference_invalid_parameter",
        )
    _validate_dataset_identity(dataset_a_id, dataset_b_id)
    _validate_axis_signal_pair(axis_a, signal_a, side="A")
    _validate_axis_signal_pair(axis_b, signal_b, side="B")
    _validate_compatibility(axis_a, signal_a, axis_b, signal_b)

    history_a = tuple(source_operation_history_a)
    history_b = tuple(source_operation_history_b)
    if any(not isinstance(item, str) for item in history_a + history_b):
        raise FTIRDifferenceError(
            "Source operation histories must contain operation ID text.",
            code="ftir_difference_invalid_input",
        )

    if parameters.axis_match == "exact":
        return _exact_difference(
            axis_a,
            signal_a,
            axis_b,
            signal_b,
            parameters,
            dataset_a_id=dataset_a_id,
            dataset_b_id=dataset_b_id,
            history_a=history_a,
            history_b=history_b,
        )
    return _interpolated_difference(
        axis_a,
        signal_a,
        axis_b,
        signal_b,
        parameters,
        dataset_a_id=dataset_a_id,
        dataset_b_id=dataset_b_id,
        history_a=history_a,
        history_b=history_b,
    )


__all__ = [
    "ALGORITHM_EXACT",
    "ALGORITHM_INTERPOLATED",
    "DIFFERENCE_ALGORITHM_VERSION",
    "ARITHMETIC_DEFINITION",
    "DIFFERENCE_AXIS_MATCHES",
    "DIFFERENCE_SOURCES",
    "DifferenceAxisMatch",
    "DifferenceInterpolation",
    "DifferenceParameters",
    "DifferenceResult",
    "DifferenceSource",
    "EXACT_COMPARISON_POLICY",
    "FTIRDifferenceError",
    "INTERPOLATION_METHOD",
    "INTERPOLATION_POLICY",
    "LIMITATIONS",
    "compute_difference",
]
