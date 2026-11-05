"""Explicit FTIR linear and polynomial baseline correction.

The fit uses float64 least squares on a centered and scaled copy of the
user-selected fitting X values. A Vandermonde matrix is built in degrees
0..degree and solved with ``numpy.linalg.lstsq``. The condition number is
checked against a documented threshold; no automatic degree reduction or
region selection is performed.

This module is Qt-free. Generic session state, preview, undo/redo and
provenance remain in :mod:`spectralab.core.processing`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from spectralab.core.errors import ProcessingError
from spectralab.core.model import Axis1D, Signal1D
from spectralab.core.processing import OperationOutput

BASELINE_DEGREES: tuple[int, ...] = (1, 2, 3, 4, 5)
MAX_CONDITION_NUMBER = 1.0e12
NUMERICAL_METHOD = (
    "numpy.polynomial least-squares Vandermonde fit with centered/scaled X"
)


class FTIRBaselineError(ProcessingError):
    """A baseline region, fit, or output is scientifically invalid."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "ftir_baseline",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, context=dict(context or {}))


def _finite_number(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FTIRBaselineError(
            f"{field} must be a finite number.",
            code="ftir_baseline_region_invalid",
            context={"field": field, "value": repr(value)},
        )
    number = float(value)
    if not np.isfinite(number):
        raise FTIRBaselineError(
            f"{field} must be finite.",
            code="ftir_baseline_region_invalid",
            context={"field": field, "value": repr(value)},
        )
    return number


@dataclass(frozen=True)
class BaselineRegion:
    """One inclusive X-coordinate fitting region."""

    start: float
    end: float

    def __post_init__(self) -> None:
        start = _finite_number(self.start, field="region.start")
        end = _finite_number(self.end, field="region.end")
        if start == end:
            raise FTIRBaselineError(
                "A baseline region must have distinct start and end values.",
                code="ftir_baseline_region_invalid",
                context={"start": start, "end": end},
            )
        lower, upper = sorted((start, end))
        object.__setattr__(self, "start", lower)
        object.__setattr__(self, "end", upper)

    @property
    def lower(self) -> float:
        return self.start

    @property
    def upper(self) -> float:
        return self.end

    def as_dict(self) -> dict[str, float]:
        return {"start": self.start, "end": self.end}

    def mask(self, values: np.ndarray) -> np.ndarray:
        return (values >= self.lower) & (values <= self.upper)


def _coerce_region(value: Any) -> BaselineRegion:
    if isinstance(value, BaselineRegion):
        return value
    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and len(value) == 2
    ):
        return BaselineRegion(value[0], value[1])
    raise FTIRBaselineError(
        "Each fitting region must be a BaselineRegion or a two-number pair.",
        code="ftir_baseline_region_invalid",
        context={"value": repr(value)},
    )


def normalize_regions(
    regions: BaselineRegion | Sequence[BaselineRegion | Sequence[float]],
) -> tuple[BaselineRegion, ...]:
    """Validate, canonicalize and sort non-overlapping fitting regions.

    A single ``BaselineRegion`` or one ``(start, end)`` pair is accepted as
    shorthand for a one-region list.
    """
    if isinstance(regions, BaselineRegion):
        normalized = (regions,)
    elif isinstance(regions, (str, bytes, bytearray)) or not isinstance(
        regions, Sequence
    ):
        raise FTIRBaselineError(
            "At least one fitting region is required.",
            code="ftir_baseline_regions",
        )
    elif (
        len(regions) == 2
        and all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in regions
        )
    ):
        normalized = (BaselineRegion(regions[0], regions[1]),)
    else:
        normalized = tuple(_coerce_region(value) for value in regions)
    if not normalized:
        raise FTIRBaselineError(
            "At least one fitting region is required.",
            code="ftir_baseline_regions",
        )
    ordered = tuple(sorted(normalized, key=lambda region: (region.start, region.end)))
    for index, (previous, current) in enumerate(zip(ordered, ordered[1:])):
        if current.start < previous.end:
            raise FTIRBaselineError(
                "Fitting regions must not overlap; no fitting points were "
                "combined.",
                code="ftir_baseline_region_overlap",
                context={
                    "first_index": index,
                    "second_index": index + 1,
                    "first": previous.as_dict(),
                    "second": current.as_dict(),
                    "overlap_policy": (
                        "Overlapping regions are rejected before fitting; "
                        "their point contributions are not combined."
                    ),
                },
            )
    return ordered


def validate_degree(degree: Any) -> int:
    if isinstance(degree, bool) or not isinstance(degree, int):
        raise FTIRBaselineError(
            "Baseline polynomial degree must be an integer from 1 to 5.",
            code="ftir_baseline_degree",
            context={"value": repr(degree)},
        )
    if degree not in BASELINE_DEGREES:
        raise FTIRBaselineError(
            "Baseline polynomial degree must be 1, 2, 3, 4 or 5.",
            code="ftir_baseline_degree",
            context={"value": degree, "allowed": list(BASELINE_DEGREES)},
        )
    return degree


def _float_array(values: Any, *, field: str) -> np.ndarray:
    try:
        raw = np.asarray(values)
        if np.iscomplexobj(raw):
            raise FTIRBaselineError(
                f"{field} must be real-valued.",
                code="ftir_baseline_input",
                context={"field": field, "dtype": str(raw.dtype)},
            )
        array = np.asarray(values, dtype=np.float64)
    except FTIRBaselineError:
        raise
    except (TypeError, ValueError) as exc:
        raise FTIRBaselineError(
            f"{field} must be a real numeric array.",
            code="ftir_baseline_input",
            context={"field": field, "error": str(exc)},
        ) from exc
    if array.ndim != 1:
        raise FTIRBaselineError(
            f"{field} must be one-dimensional.",
            code="ftir_baseline_input",
            context={"field": field, "ndim": int(array.ndim)},
        )
    if array.size == 0:
        raise FTIRBaselineError(
            f"{field} must not be empty.",
            code="ftir_baseline_input",
            context={"field": field},
        )
    if not np.all(np.isfinite(array)):
        index = int(np.flatnonzero(~np.isfinite(array))[0])
        raise FTIRBaselineError(
            f"{field} contains a non-finite value.",
            code="ftir_baseline_nonfinite_input",
            context={"field": field, "index": index},
        )
    return array


@dataclass(frozen=True)
class BaselineFit:
    """A reproducible scaled-polynomial fit and its numerical diagnostics."""

    coefficients: tuple[float, ...]
    degree: int
    regions: tuple[BaselineRegion, ...]
    fitting_point_count: int
    x_center: float
    x_scale: float
    condition_number: float
    rank: int
    region_point_counts: tuple[int, ...] = ()
    region_unique_point_counts: tuple[int, ...] = ()
    numerical_method: str = NUMERICAL_METHOD

    @property
    def algorithm(self) -> str:
        return "linear" if self.degree == 1 else "polynomial"

    def evaluate(self, x_values: Any) -> np.ndarray:
        values = np.asarray(x_values, dtype=np.float64)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            scaled = (values - self.x_center) / self.x_scale
            baseline = np.polynomial.polynomial.polyval(
                scaled,
                np.asarray(self.coefficients, dtype=np.float64),
            )
        if not np.all(np.isfinite(baseline)):
            raise FTIRBaselineError(
                "The fitted baseline contains a non-finite value.",
                code="ftir_baseline_nonfinite_baseline",
            )
        return np.asarray(baseline, dtype=np.float64, copy=True)

    def as_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "degree": self.degree,
            "regions": [region.as_dict() for region in self.regions],
            "fitting_point_count": self.fitting_point_count,
            "region_point_counts": list(self.region_point_counts),
            "region_unique_point_counts": list(
                self.region_unique_point_counts
            ),
            "coefficients": [float(value) for value in self.coefficients],
            "coefficient_domain": "centered_scaled_x",
            "x_center": self.x_center,
            "x_scale": self.x_scale,
            "condition_number": self.condition_number,
            "rank": self.rank,
            "numerical_method": self.numerical_method,
            "condition_limit": MAX_CONDITION_NUMBER,
        }


def fit_baseline(
    axis_values: Any,
    signal_values: Any,
    regions: BaselineRegion | Sequence[BaselineRegion | Sequence[float]],
    degree: int,
) -> BaselineFit:
    """Fit a baseline from explicit regions without modifying input arrays."""
    degree = validate_degree(degree)
    x_values = _float_array(axis_values, field="axis.values")
    y_values = _float_array(signal_values, field="signal.values")
    if x_values.size != y_values.size:
        raise FTIRBaselineError(
            "Axis and signal lengths differ.",
            code="ftir_baseline_input",
            context={"axis": x_values.size, "signal": y_values.size},
        )
    regions_tuple = normalize_regions(regions)

    region_masks = tuple(region.mask(x_values) for region in regions_tuple)
    region_point_counts = tuple(
        int(np.count_nonzero(region_mask)) for region_mask in region_masks
    )
    for index, count in enumerate(region_point_counts):
        if count == 0:
            raise FTIRBaselineError(
                "A fitting region contains no data points from this spectrum.",
                code="ftir_baseline_empty_region",
                context={
                    "region_index": index,
                    "region": regions_tuple[index].as_dict(),
                    "point_count": 0,
                    "region_point_counts": list(region_point_counts),
                },
            )

    mask = np.zeros(x_values.size, dtype=bool)
    region_unique_point_counts: list[int] = []
    for region_mask in region_masks:
        unique_mask = region_mask & ~mask
        region_unique_point_counts.append(int(np.count_nonzero(unique_mask)))
        mask |= region_mask
    fitting_point_count = int(np.count_nonzero(mask))
    if fitting_point_count <= degree:
        raise FTIRBaselineError(
            "The number of fitting points must be greater than the "
            "polynomial degree.",
            code="ftir_baseline_insufficient_points",
            context={
                "degree": degree,
                "fitting_point_count": fitting_point_count,
            },
        )

    x_fit = x_values[mask]
    y_fit = y_values[mask]
    x_center = float(np.mean(x_fit))
    x_scale = float(np.max(np.abs(x_fit - x_center)))
    if not np.isfinite(x_scale) or x_scale == 0.0:
        raise FTIRBaselineError(
            "Fitting X values have no usable spread; the fit is rank-deficient.",
            code="ftir_baseline_rank_deficient",
            context={"x_center": x_center, "x_scale": x_scale},
        )

    z_fit = (x_fit - x_center) / x_scale
    vandermonde = np.vander(z_fit, N=degree + 1, increasing=True)
    try:
        coefficients, _residuals, rank, singular_values = np.linalg.lstsq(
            vandermonde,
            y_fit,
            rcond=None,
        )
    except np.linalg.LinAlgError as exc:
        raise FTIRBaselineError(
            "Polynomial baseline fitting failed numerically.",
            code="ftir_baseline_fit_failed",
            context={"error": str(exc)},
        ) from exc

    if int(rank) < degree + 1:
        raise FTIRBaselineError(
            "The selected fitting regions do not constrain all polynomial "
            "coefficients; the fit is rank-deficient.",
            code="ftir_baseline_rank_deficient",
            context={"rank": int(rank), "coefficient_count": degree + 1},
        )
    singular_values = np.asarray(singular_values, dtype=np.float64)
    smallest = float(singular_values[-1]) if singular_values.size else 0.0
    largest = float(singular_values[0]) if singular_values.size else 0.0
    condition_number = (
        float(largest / smallest) if smallest > 0.0 else float("inf")
    )
    if not np.isfinite(condition_number) or condition_number > MAX_CONDITION_NUMBER:
        raise FTIRBaselineError(
            "Polynomial fitting is numerically ill-conditioned.",
            code="ftir_baseline_ill_conditioned",
            context={
                "condition_number": condition_number,
                "condition_limit": MAX_CONDITION_NUMBER,
            },
        )
    coefficients = np.asarray(coefficients, dtype=np.float64)
    if not np.all(np.isfinite(coefficients)):
        raise FTIRBaselineError(
            "Polynomial fitting produced non-finite coefficients.",
            code="ftir_baseline_nonfinite_coefficients",
        )

    fit = BaselineFit(
        coefficients=tuple(float(value) for value in coefficients),
        degree=degree,
        regions=regions_tuple,
        fitting_point_count=fitting_point_count,
        x_center=x_center,
        x_scale=x_scale,
        condition_number=condition_number,
        rank=int(rank),
        region_point_counts=region_point_counts,
        region_unique_point_counts=tuple(region_unique_point_counts),
    )
    baseline = fit.evaluate(x_values)
    with np.errstate(over="ignore", invalid="ignore"):
        corrected = y_values - baseline
    if not np.all(np.isfinite(corrected)):
        raise FTIRBaselineError(
            "Baseline correction produced a non-finite value.",
            code="ftir_baseline_nonfinite_output",
        )
    return fit


class FTIRBaselineOperation:
    """One explicit linear or polynomial baseline operation."""

    technique = "ftir"
    version = "1.0.0"
    changes_axis = False
    axis_change_description = None
    changes_signal_semantics = False
    changes_signal_unit = False
    signal_change_description = None

    def __init__(
        self,
        regions: BaselineRegion | Sequence[BaselineRegion | Sequence[float]],
        degree: int,
    ) -> None:
        self.degree = validate_degree(degree)
        self.regions = normalize_regions(regions)
        self.algorithm = "linear" if self.degree == 1 else "polynomial"
        self.operation_id = (
            "ftir.baseline.linear"
            if self.degree == 1
            else "ftir.baseline.polynomial"
        )
        self.name = (
            "Linear baseline correction"
            if self.degree == 1
            else f"Polynomial baseline correction (degree {self.degree})"
        )
        self.parameters: dict[str, Any] = {
            "algorithm": self.algorithm,
            "degree": self.degree,
            "regions": [region.as_dict() for region in self.regions],
            "region_count": len(self.regions),
        }

    def fit(self, axis: Axis1D, signal: Signal1D) -> BaselineFit:
        return fit_baseline(
            axis.values,
            signal.values,
            self.regions,
            self.degree,
        )

    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput:
        fit = self.fit(axis, signal)
        baseline = fit.evaluate(axis.values)
        with np.errstate(over="ignore", invalid="ignore"):
            corrected = np.asarray(signal.values, dtype=np.float64) - baseline
        if not np.all(np.isfinite(corrected)):
            raise FTIRBaselineError(
                "Baseline correction produced a non-finite value.",
                code="ftir_baseline_nonfinite_output",
            )
        corrected_signal = Signal1D(
            values=corrected,
            semantics=signal.semantics,
            unit=signal.unit,
            name=signal.name,
            metadata_source=signal.metadata_source,
            missing_reason=signal.missing_reason,
        )
        diagnostics = fit.as_dict()
        diagnostics["point_count"] = corrected_signal.point_count
        return OperationOutput(
            axis=axis,
            signal=corrected_signal,
            assumptions=(
                "The baseline was estimated only from the user-selected "
                "fitting regions; no automatic peak detection, region "
                "selection or degree reduction was used.",
            ),
            diagnostics=diagnostics,
        )


def create_baseline_operation(
    regions: BaselineRegion | Sequence[BaselineRegion | Sequence[float]],
    degree: int,
) -> FTIRBaselineOperation:
    return FTIRBaselineOperation(regions, degree)


__all__ = [
    "BASELINE_DEGREES",
    "BaselineFit",
    "BaselineRegion",
    "FTIRBaselineError",
    "FTIRBaselineOperation",
    "MAX_CONDITION_NUMBER",
    "NUMERICAL_METHOD",
    "create_baseline_operation",
    "fit_baseline",
    "normalize_regions",
    "validate_degree",
]
