"""EPR linear-baseline and Savitzky-Golay operations for SpectraLab.

The implementation lives in the independent EPR technique package. Legacy
``epr_workflow`` spec objects are accepted structurally for compatibility with
existing M4 tests and callers, but no ``epr_workflow`` module is imported.

Only one ordinary-least-squares linear baseline over two closed field windows
and Savitzky-Golay smoothing with ``deriv=0`` and ``mode="interp"`` are
provided. Generic legacy preview/pending state, raw-input reordering and EPR
JSON record generation are not adapted here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from spectralab.core.model import Axis1D, Signal1D
from spectralab.core.processing import OperationOutput
from spectralab.techniques.epr.processing_impl import (
    BASELINE_ALGORITHM_VERSION,
    BASELINE_METHOD,
    BASELINE_OPERATION,
    SAVGOL_ALGORITHM_VERSION,
    SAVGOL_METHOD,
    SAVGOL_OPERATION,
    BaselineWindow,
    EprProcessingError,
    LinearBaselineSpec,
    SavgolSpec,
    fit_linear_baseline,
    smooth_savgol,
)

_BASELINE_ASSUMPTIONS = (
    "The intensity baseline is additive in the undocumented intensity units.",
    "One straight line represents the baseline across the selected field range.",
    "The selected windows contain baseline only; this is the user's scientific "
    "judgement and is not verified by the software.",
)
_SAVGOL_ASSUMPTIONS = (
    "Savitzky-Golay smoothing fits a local polynomial over a fixed-width "
    "window and replaces each point by that local fit.",
    "Smoothing can change peak height, peak width and line shape; it does not "
    "by itself establish improved data quality.",
    "No scaling or normalisation is applied to exported values.",
)


def _coerce_baseline_spec(spec: Any) -> LinearBaselineSpec:
    if isinstance(spec, LinearBaselineSpec):
        return spec
    try:
        left = spec.window_left
        right = spec.window_right
        return LinearBaselineSpec(
            window_left=BaselineWindow(
                start_G=float(left.start),
                end_G=float(left.end),
            ),
            window_right=BaselineWindow(
                start_G=float(right.start),
                end_G=float(right.end),
            ),
        )
    except Exception as exc:
        raise EprProcessingError(
            "EprLinearBaselineOperation requires a linear baseline spec with "
            "two windows.",
            code="epr_baseline_spec",
            context={"type": type(spec).__name__},
        ) from exc


def _coerce_savgol_spec(spec: Any) -> SavgolSpec:
    if isinstance(spec, SavgolSpec):
        return spec
    try:
        return SavgolSpec(
            window_length=spec.window_length,
            polyorder=spec.polyorder,
            deriv=spec.deriv,
            mode=spec.mode,
        )
    except Exception as exc:
        raise EprProcessingError(
            "EprSavitzkyGolayOperation requires a Savitzky-Golay spec.",
            code="epr_savgol_spec",
            context={"type": type(spec).__name__},
        ) from exc


def _require_epr_axis(axis: Axis1D) -> None:
    if axis.quantity != "magnetic_field" or axis.unit != "G":
        raise EprProcessingError(
            "EPR processing requires a magnetic-field X axis in Gauss (G). "
            "No unit conversion is performed.",
            code="epr_axis_unsupported",
            context={
                "quantity": axis.quantity,
                "unit": axis.unit,
            },
        )


@dataclass(frozen=True)
class EprLinearBaselineOperation:
    """EPR linear baseline over two closed ``G`` windows."""

    spec: Any

    operation_id: ClassVar[str] = BASELINE_OPERATION
    name: ClassVar[str] = "EPR linear baseline correction"
    technique: ClassVar[str] = "epr"
    version: ClassVar[str] = BASELINE_ALGORITHM_VERSION
    changes_axis: ClassVar[bool] = False
    axis_change_description: ClassVar[str | None] = None
    changes_signal_semantics: ClassVar[bool] = False
    changes_signal_unit: ClassVar[bool] = False
    signal_change_description: ClassVar[str | None] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "spec", _coerce_baseline_spec(self.spec))

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "windows_G": [
                {
                    "start": self.spec.window_left.start,
                    "end": self.spec.window_left.end,
                },
                {
                    "start": self.spec.window_right.start,
                    "end": self.spec.window_right.end,
                },
            ],
            "inclusive_bounds": True,
            "weighting": "none",
            "method": BASELINE_METHOD,
        }

    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput:
        _require_epr_axis(axis)
        fit, warnings = fit_linear_baseline(
            axis.values,
            signal.values,
            self.spec,
        )
        processed = signal.values - (
            fit.slope * axis.values + fit.intercept
        )
        processed_signal = Signal1D(
            values=processed,
            semantics=signal.semantics,
            unit=signal.unit,
            name=signal.name,
            metadata_source=signal.metadata_source,
            missing_reason=signal.missing_reason,
        )
        return OperationOutput(
            axis=axis,
            signal=processed_signal,
            warnings=tuple(warning.message for warning in warnings),
            assumptions=_BASELINE_ASSUMPTIONS,
            diagnostics={
                "legacy_operation": BASELINE_OPERATION,
                "method": BASELINE_METHOD,
                "algorithm_version": BASELINE_ALGORITHM_VERSION,
                "fit": fit.as_dict(),
                "points_used": fit.n_points,
                "warning_records": [warning.as_dict() for warning in warnings],
            },
        )


@dataclass(frozen=True)
class EprSavitzkyGolayOperation:
    """EPR Savitzky-Golay smoothing on the current signal."""

    spec: Any

    operation_id: ClassVar[str] = SAVGOL_OPERATION
    name: ClassVar[str] = "EPR Savitzky-Golay smoothing"
    technique: ClassVar[str] = "epr"
    version: ClassVar[str] = SAVGOL_ALGORITHM_VERSION
    changes_axis: ClassVar[bool] = False
    axis_change_description: ClassVar[str | None] = None
    changes_signal_semantics: ClassVar[bool] = False
    changes_signal_unit: ClassVar[bool] = False
    signal_change_description: ClassVar[str | None] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "spec", _coerce_savgol_spec(self.spec))

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {
            "window_length": int(self.spec.window_length),
            "polyorder": int(self.spec.polyorder),
            "deriv": int(self.spec.deriv),
            "mode": self.spec.mode,
            "method": SAVGOL_METHOD,
        }

    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput:
        _require_epr_axis(axis)
        processed, diagnostics = smooth_savgol(signal.values, self.spec)
        processed_signal = Signal1D(
            values=processed,
            semantics=signal.semantics,
            unit=signal.unit,
            name=signal.name,
            metadata_source=signal.metadata_source,
            missing_reason=signal.missing_reason,
        )
        return OperationOutput(
            axis=axis,
            signal=processed_signal,
            assumptions=_SAVGOL_ASSUMPTIONS,
            diagnostics={
                "legacy_operation": SAVGOL_OPERATION,
                "method": SAVGOL_METHOD,
                "algorithm_version": SAVGOL_ALGORITHM_VERSION,
                "smoothing": diagnostics.as_dict(),
            },
        )


# Architecture-style aliases.
EPRLinearBaselineOperation = EprLinearBaselineOperation
EPRSavitzkyGolayOperation = EprSavitzkyGolayOperation

__all__ = [
    "EPRLinearBaselineOperation",
    "EPRSavitzkyGolayOperation",
    "EprLinearBaselineOperation",
    "EprProcessingError",
    "EprSavitzkyGolayOperation",
    "BaselineWindow",
    "LinearBaselineSpec",
    "SavgolSpec",
]
