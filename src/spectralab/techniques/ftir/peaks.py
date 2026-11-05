"""Explicit FTIR peak picking with a separate analysis-result model.

Detection uses ``scipy.signal.find_peaks``. It never modifies the source
Spectrum1D, processed signal or ProcessingSession. Peak results are analysis
data, not processing history.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from scipy.signal import find_peaks

from spectralab.core.errors import ProcessingError
from spectralab.core.model import Axis1D, Signal1D

PeakPolarity = Literal["positive", "negative", "both"]
PeakSource = Literal["raw", "processed"]
PEAK_POLARITIES: tuple[str, ...] = ("positive", "negative", "both")
PEAK_SOURCES: tuple[str, ...] = ("raw", "processed")
ALGORITHM = "scipy.signal.find_peaks"
ALGORITHM_VERSION = "1.0.0"
LIMITATIONS: tuple[str, ...] = (
    "Local extrema at the first or last sample are not reported as local peaks.",
    "Width is measured at half prominence in sample positions and converted to "
    "the X-axis unit by linear interpolation.",
)


class PeakDetectionError(ProcessingError):
    """A peak-picking parameter or input is invalid."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "ftir_peak_detection",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, context=context)


def _nonnegative_number(value: Any, *, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PeakDetectionError(
            f"{field} must be a non-negative finite number or None.",
            code="ftir_peak_invalid_parameter",
            context={"field": field, "value": repr(value)},
        )
    number = float(value)
    if not np.isfinite(number) or number < 0.0:
        raise PeakDetectionError(
            f"{field} must be a non-negative finite number or None.",
            code="ftir_peak_invalid_parameter",
            context={"field": field, "value": repr(value)},
        )
    return number


def _polarity(value: Any) -> PeakPolarity:
    if not isinstance(value, str):
        raise PeakDetectionError(
            "Peak polarity must be 'positive', 'negative' or 'both'.",
            code="ftir_peak_invalid_polarity",
            context={"value": repr(value)},
        )
    key = value.strip().casefold()
    if key not in PEAK_POLARITIES:
        raise PeakDetectionError(
            "Peak polarity must be 'positive', 'negative' or 'both'.",
            code="ftir_peak_invalid_polarity",
            context={"value": value, "allowed": list(PEAK_POLARITIES)},
        )
    return key  # type: ignore[return-value]


def _source(value: Any) -> PeakSource:
    if not isinstance(value, str):
        raise PeakDetectionError(
            "Peak source must be 'raw' or 'processed'.",
            code="ftir_peak_invalid_source",
            context={"value": repr(value)},
        )
    key = value.strip().casefold()
    if key not in PEAK_SOURCES:
        raise PeakDetectionError(
            "Peak source must be 'raw' or 'processed'.",
            code="ftir_peak_invalid_source",
            context={"value": value, "allowed": list(PEAK_SOURCES)},
        )
    return key  # type: ignore[return-value]


@dataclass(frozen=True)
class PeakDetectionParameters:
    """Explicit peak-picking settings.

    ``height`` and ``prominence`` are in the selected signal's units. They are
    applied to the oriented signal: ``y`` for positive peaks and ``-y`` for
    negative peaks. ``distance_points`` and ``min_width_points`` are measured
    in sample points, never in physical X-axis units.
    """

    polarity: PeakPolarity = "positive"
    source: PeakSource = "raw"
    height: float | None = None
    prominence: float | None = None
    distance_points: int = 1
    min_width_points: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "polarity", _polarity(self.polarity))
        object.__setattr__(self, "source", _source(self.source))
        object.__setattr__(
            self,
            "height",
            _nonnegative_number(self.height, field="height"),
        )
        object.__setattr__(
            self,
            "prominence",
            _nonnegative_number(self.prominence, field="prominence"),
        )
        if isinstance(self.distance_points, bool) or not isinstance(
            self.distance_points, int
        ):
            raise PeakDetectionError(
                "distance_points must be a positive integer.",
                code="ftir_peak_invalid_parameter",
                context={"field": "distance_points"},
            )
        if self.distance_points < 1:
            raise PeakDetectionError(
                "distance_points must be at least 1 sample.",
                code="ftir_peak_invalid_parameter",
                context={"field": "distance_points", "value": self.distance_points},
            )
        object.__setattr__(
            self,
            "min_width_points",
            _nonnegative_number(
                self.min_width_points,
                field="min_width_points",
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "polarity": self.polarity,
            "source": self.source,
            "height": self.height,
            "prominence": self.prominence,
            "distance_points": self.distance_points,
            "min_width_points": self.min_width_points,
        }


@dataclass(frozen=True)
class Peak1D:
    """One detected peak independent of the source arrays."""

    index: int
    polarity: Literal["positive", "negative"]
    x: float
    y: float
    prominence: float
    width_samples: float
    width_x: float

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int):
            raise PeakDetectionError(
                "Peak index must be an integer.",
                code="ftir_peak_invalid_result",
            )
        if self.index < 0:
            raise PeakDetectionError(
                "Peak index must not be negative.",
                code="ftir_peak_invalid_result",
            )
        if self.polarity not in ("positive", "negative"):
            raise PeakDetectionError(
                "Peak polarity must be positive or negative.",
                code="ftir_peak_invalid_result",
            )
        for field_name in ("x", "y", "prominence", "width_samples", "width_x"):
            value = getattr(self, field_name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise PeakDetectionError(
                    f"Peak {field_name} must be numeric.",
                    code="ftir_peak_invalid_result",
                    context={"field": field_name},
                )
            if not np.isfinite(float(value)):
                raise PeakDetectionError(
                    f"Peak {field_name} must be finite.",
                    code="ftir_peak_invalid_result",
                    context={"field": field_name},
                )
        if self.prominence < 0.0:
            raise PeakDetectionError(
                "Peak prominence must not be negative.",
                code="ftir_peak_invalid_result",
            )
        if self.width_samples < 0.0 or self.width_x < 0.0:
            raise PeakDetectionError(
                "Peak widths must not be negative.",
                code="ftir_peak_invalid_result",
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "polarity": self.polarity,
            "x": self.x,
            "y": self.y,
            "prominence": self.prominence,
            "width_samples": self.width_samples,
            "width_x": self.width_x,
        }


@dataclass(frozen=True)
class PeakDetectionResult:
    """Completed peak-picking result and its provenance."""

    peaks: tuple[Peak1D, ...]
    parameters: PeakDetectionParameters
    dataset_id: str
    axis_quantity: str
    axis_unit: str | None
    axis_direction: str
    signal_semantics: str
    signal_unit: str | None
    source_operation_history: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    algorithm: str = ALGORITHM
    algorithm_version: str = ALGORITHM_VERSION
    limitations: tuple[str, ...] = LIMITATIONS

    def __post_init__(self) -> None:
        peaks = tuple(self.peaks)
        if any(not isinstance(peak, Peak1D) for peak in peaks):
            raise PeakDetectionError(
                "PeakDetectionResult.peaks must contain Peak1D objects.",
                code="ftir_peak_invalid_result",
            )
        object.__setattr__(self, "peaks", peaks)
        if not isinstance(self.parameters, PeakDetectionParameters):
            raise PeakDetectionError(
                "PeakDetectionResult.parameters must be PeakDetectionParameters.",
                code="ftir_peak_invalid_result",
            )
        if not isinstance(self.dataset_id, str) or not self.dataset_id.strip():
            raise PeakDetectionError(
                "PeakDetectionResult.dataset_id must be non-empty text.",
                code="ftir_peak_invalid_result",
            )
        for field_name in ("axis_quantity", "axis_direction", "signal_semantics"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise PeakDetectionError(
                    f"PeakDetectionResult.{field_name} must be non-empty text.",
                    code="ftir_peak_invalid_result",
                    context={"field": field_name},
                )
        for field_name in ("axis_unit", "signal_unit"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value):
                raise PeakDetectionError(
                    f"PeakDetectionResult.{field_name} must be text or None.",
                    code="ftir_peak_invalid_result",
                    context={"field": field_name},
                )
        object.__setattr__(
            self,
            "source_operation_history",
            tuple(self.source_operation_history),
        )
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "limitations", tuple(self.limitations))

    @property
    def source(self) -> str:
        return self.parameters.source

    @property
    def polarity(self) -> str:
        return self.parameters.polarity

    @property
    def positive_count(self) -> int:
        return sum(1 for peak in self.peaks if peak.polarity == "positive")

    @property
    def negative_count(self) -> int:
        return sum(1 for peak in self.peaks if peak.polarity == "negative")

    @property
    def peak_count(self) -> int:
        return len(self.peaks)

    def as_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "algorithm_version": self.algorithm_version,
            "source": self.source,
            "polarity": self.polarity,
            "parameters": self.parameters.as_dict(),
            "dataset_id": self.dataset_id,
            "axis_quantity": self.axis_quantity,
            "axis_unit": self.axis_unit,
            "axis_direction": self.axis_direction,
            "signal_semantics": self.signal_semantics,
            "signal_unit": self.signal_unit,
            "source_operation_history": list(self.source_operation_history),
            "positive_count": self.positive_count,
            "negative_count": self.negative_count,
            "peak_count": self.peak_count,
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "peaks": [peak.as_dict() for peak in self.peaks],
        }


def _finite_vector(values: Any, *, field: str) -> np.ndarray:
    try:
        raw = np.asarray(values)
        if np.iscomplexobj(raw):
            raise PeakDetectionError(
                f"{field} must be real-valued.",
                code="ftir_peak_invalid_input",
                context={"field": field},
            )
        array = np.asarray(values, dtype=np.float64)
    except PeakDetectionError:
        raise
    except (TypeError, ValueError) as exc:
        raise PeakDetectionError(
            f"{field} must be a real numeric array.",
            code="ftir_peak_invalid_input",
            context={"field": field, "error": str(exc)},
        ) from exc
    if array.ndim != 1:
        raise PeakDetectionError(
            f"{field} must be one-dimensional.",
            code="ftir_peak_invalid_input",
            context={"field": field, "ndim": int(array.ndim)},
        )
    if array.size == 0:
        raise PeakDetectionError(
            f"{field} must not be empty.",
            code="ftir_peak_invalid_input",
            context={"field": field},
        )
    if not np.all(np.isfinite(array)):
        index = int(np.flatnonzero(~np.isfinite(array))[0])
        raise PeakDetectionError(
            f"{field} contains a non-finite value.",
            code="ftir_peak_nonfinite_input",
            context={"field": field, "index": index},
        )
    return array


def _detect_oriented(
    y_values: np.ndarray,
    x_values: np.ndarray,
    parameters: PeakDetectionParameters,
    *,
    polarity: Literal["positive", "negative"],
) -> tuple[list[Peak1D], float]:
    oriented = y_values if polarity == "positive" else -y_values
    width_arg = (
        0.0
        if parameters.min_width_points is None
        else float(parameters.min_width_points)
    )
    indices, properties = find_peaks(
        oriented,
        height=parameters.height,
        prominence=parameters.prominence,
        distance=parameters.distance_points,
        width=width_arg,
    )
    if indices.size == 0:
        return [], width_arg

    prominences = properties.get("prominences")
    widths = properties.get("widths")
    left_ips = properties.get("left_ips")
    right_ips = properties.get("right_ips")
    if (
        prominences is None
        or widths is None
        or left_ips is None
        or right_ips is None
    ):
        raise PeakDetectionError(
            "scipy.signal.find_peaks did not return the required properties.",
            code="ftir_peak_detection_failed",
        )

    positions = np.arange(x_values.size, dtype=np.float64)
    peaks: list[Peak1D] = []
    for position in range(len(indices)):
        index = int(indices[position])
        left_x = float(np.interp(left_ips[position], positions, x_values))
        right_x = float(np.interp(right_ips[position], positions, x_values))
        peaks.append(
            Peak1D(
                index=index,
                polarity=polarity,
                x=float(x_values[index]),
                y=float(y_values[index]),
                prominence=float(prominences[position]),
                width_samples=float(widths[position]),
                width_x=abs(right_x - left_x),
            )
        )
    return peaks, width_arg


def _validated_parameters(parameters: Any) -> PeakDetectionParameters:
    if not isinstance(parameters, PeakDetectionParameters):
        raise PeakDetectionError(
            "Peak detection requires PeakDetectionParameters.",
            code="ftir_peak_invalid_parameter",
        )
    return parameters


def _validated_pair(
    x_values: Any,
    y_values: Any,
) -> tuple[np.ndarray, np.ndarray]:
    x = _finite_vector(x_values, field="axis.values")
    y = _finite_vector(y_values, field="signal.values")
    if x.size != y.size:
        raise PeakDetectionError(
            "Axis and signal lengths differ.",
            code="ftir_peak_invalid_input",
            context={"axis": x.size, "signal": y.size},
        )
    return x, y


def _run_detection(
    x_values: np.ndarray,
    y_values: np.ndarray,
    parameters: PeakDetectionParameters,
    *,
    dataset_id: str,
    axis_quantity: str,
    axis_unit: str | None,
    axis_direction: str,
    signal_semantics: str,
    signal_unit: str | None,
    source_operation_history: Sequence[str],
) -> PeakDetectionResult:
    warnings: list[str] = []
    if float(np.ptp(y_values)) == 0.0:
        warnings.append(
            "The selected signal is constant; no local peaks are expected."
        )

    peaks: list[Peak1D] = []
    polarities = (
        ("positive", "negative")
        if parameters.polarity == "both"
        else (parameters.polarity,)
    )
    for polarity in polarities:
        found, _width_arg = _detect_oriented(
            y_values,
            x_values,
            parameters,
            polarity=polarity,  # type: ignore[arg-type]
        )
        peaks.extend(found)
    peaks.sort(key=lambda peak: peak.index)
    if not peaks:
        warnings.append("No peaks were detected for the selected parameters.")

    return PeakDetectionResult(
        peaks=tuple(peaks),
        parameters=parameters,
        dataset_id=dataset_id,
        axis_quantity=axis_quantity,
        axis_unit=axis_unit,
        axis_direction=axis_direction,
        signal_semantics=signal_semantics,
        signal_unit=signal_unit,
        source_operation_history=tuple(source_operation_history),
        warnings=tuple(warnings),
    )


def detect_peak_values(
    x_values: Any,
    y_values: Any,
    parameters: PeakDetectionParameters,
    *,
    dataset_id: str,
    axis_quantity: str = "unknown",
    axis_unit: str | None = None,
    axis_direction: str = "unknown",
    signal_semantics: str = "unknown",
    signal_unit: str | None = None,
    source_operation_history: Sequence[str] = (),
) -> PeakDetectionResult:
    """Detect peaks from explicit arrays without constructing a Spectrum1D."""
    params = _validated_parameters(parameters)
    x, y = _validated_pair(x_values, y_values)
    return _run_detection(
        x,
        y,
        params,
        dataset_id=dataset_id,
        axis_quantity=axis_quantity,
        axis_unit=axis_unit,
        axis_direction=axis_direction,
        signal_semantics=signal_semantics,
        signal_unit=signal_unit,
        source_operation_history=source_operation_history,
    )


def detect_peaks(
    axis: Axis1D,
    signal: Signal1D,
    parameters: PeakDetectionParameters,
    *,
    dataset_id: str,
    source_operation_history: Sequence[str] = (),
) -> PeakDetectionResult:
    """Detect local peaks without modifying axis, signal or session state."""
    if not isinstance(axis, Axis1D):
        raise PeakDetectionError(
            "Peak detection requires an Axis1D.",
            code="ftir_peak_invalid_input",
        )
    if not isinstance(signal, Signal1D):
        raise PeakDetectionError(
            "Peak detection requires a Signal1D.",
            code="ftir_peak_invalid_input",
        )
    params = _validated_parameters(parameters)
    x, y = _validated_pair(axis.values, signal.values)
    return _run_detection(
        x,
        y,
        params,
        dataset_id=dataset_id,
        axis_quantity=axis.quantity,
        axis_unit=axis.unit,
        axis_direction=str(axis.direction),
        signal_semantics=signal.semantics,
        signal_unit=signal.unit,
        source_operation_history=source_operation_history,
    )


__all__ = [
    "ALGORITHM",
    "ALGORITHM_VERSION",
    "LIMITATIONS",
    "PEAK_POLARITIES",
    "PEAK_SOURCES",
    "Peak1D",
    "PeakDetectionError",
    "PeakDetectionParameters",
    "PeakDetectionResult",
    "PeakPolarity",
    "PeakSource",
    "detect_peak_values",
    "detect_peaks",
]
