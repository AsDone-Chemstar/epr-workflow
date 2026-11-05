"""Independent EPR baseline and Savitzky-Golay implementation.

The numerical formulas, validation rules, warning order and diagnostic fields
mirror the legacy ``epr_workflow.preprocessing`` implementation without
importing it. The old application remains the reference implementation for
regression tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from spectralab.core.errors import ProcessingError

#: Minimum number of data points in each baseline window.
MIN_POINTS_PER_WINDOW = 3
MIN_UNSELECTED_POINTS_BETWEEN_WINDOWS = 1
FEW_POINTS_THRESHOLD = 5

BASELINE_OPERATION = "linear_baseline"
BASELINE_METHOD = "ordinary_least_squares_union_of_windows"
BASELINE_ALGORITHM_VERSION = "1.0"
SAVGOL_OPERATION = "savitzky_golay"
SAVGOL_METHOD = "scipy.signal.savgol_filter"
SAVGOL_ALGORITHM_VERSION = "1.0"
SCHEMA_VERSION = "1.0"

EXTRAPOLATION_WARNING_FRACTION = 0.25
LOW_COVERAGE_WARNING_FRACTION = 0.02
HIGH_COVERAGE_WARNING_FRACTION = 0.50
NOISY_WINDOW_SIGMA_FACTOR = 3.0


class EprProcessingError(ProcessingError):
    """Base error for the independent EPR processing backend."""

    default_code = "epr_processing"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code=code or self.default_code,
            context=context,
        )


class PreprocessingError(EprProcessingError):
    """Base class for EPR preprocessing failures (legacy-compatible code)."""

    default_code = "generic"


class BaselineWindowError(PreprocessingError):
    default_code = "window"


class NonFiniteDataError(PreprocessingError):
    default_code = "nonfinite"


class NonMonotonicFieldError(PreprocessingError):
    default_code = "field_not_monotonic"


class DegenerateFitError(PreprocessingError):
    default_code = "degenerate"


@dataclass(frozen=True)
class BaselineWindow:
    """One closed magnetic-field interval ``[start_G, end_G]``."""

    start_G: float
    end_G: float

    def __post_init__(self) -> None:
        start = float(self.start_G)
        end = float(self.end_G)
        if not (np.isfinite(start) and np.isfinite(end)):
            raise BaselineWindowError(
                "Baseline window bounds must be finite numbers.",
                code="window_bounds",
                context={"start": start, "end": end},
            )
        if not start < end:
            raise BaselineWindowError(
                f"Invalid baseline window: start {start:.4f} G must be less "
                f"than end {end:.4f} G.",
                code="window_bounds",
                context={"start": start, "end": end},
            )

    @property
    def start(self) -> float:
        return float(self.start_G)

    @property
    def end(self) -> float:
        return float(self.end_G)


@dataclass(frozen=True)
class LinearBaselineSpec:
    """The two disjoint windows used for one linear baseline fit.

    ``window_left`` must be the lower-field window; the validator enforces
    ``window_left.end < window_right.start`` plus at least one unselected point
    between them.
    """

    window_left: BaselineWindow
    window_right: BaselineWindow


@dataclass(frozen=True)
class SavgolSpec:
    """Parameters for one Savitzky-Golay smoothing step.

    ``deriv`` and ``mode`` are fixed in this version; they are stored in the
    record so the exact SciPy call is reproducible.
    """

    window_length: int
    polyorder: int
    deriv: int = 0
    mode: str = "interp"


@dataclass(frozen=True)
class SavgolDiagnostics:
    """How much one smoothing step changed the input signal."""

    n_points: int
    rms_change: float
    max_abs_change: float
    input_mean: float
    input_std: float
    output_mean: float
    output_std: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_points": self.n_points,
            "rms_change": self.rms_change,
            "max_abs_change": self.max_abs_change,
            "input_mean": self.input_mean,
            "input_std": self.input_std,
            "output_mean": self.output_mean,
            "output_std": self.output_std,
        }


@dataclass(frozen=True)
class PreprocessingWarning:
    """A non-blocking diagnostic, translatable via its stable ``code``."""

    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "context": dict(self.context)}


@dataclass(frozen=True)
class BaselineFit:
    """Result of one ordinary-least-squares line fit on the selected windows."""

    slope: float
    intercept: float
    r_squared: float | None
    rms_residual: float
    field_centroid_G: float
    intensity_centroid: float
    n_points: int
    n_points_left: int
    n_points_right: int
    residual_rms_left: float
    residual_rms_right: float
    extrapolation_left_G: float
    extrapolation_right_G: float
    selected_fraction: float
    window_span_fraction: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": "intensity = slope * field_G + intercept",
            "slope": self.slope,
            "intercept": self.intercept,
            "slope_units": "intensity_units_per_G",
            "r_squared": self.r_squared,
            "rms_residual": self.rms_residual,
            "field_centroid_G": self.field_centroid_G,
            "intensity_centroid": self.intensity_centroid,
            "residual_rms_left": self.residual_rms_left,
            "residual_rms_right": self.residual_rms_right,
        }



def _as_float_1d(values: Any, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1:
        raise PreprocessingError(
            f"{name} must be a one-dimensional array; got {array.ndim} dimensions.",
            code="array",
        )
    try:
        converted = array.astype(np.float64, copy=True)
    except (TypeError, ValueError) as exc:
        raise PreprocessingError(
            f"{name} contains values that cannot be converted to float: {exc}",
            code="array",
        ) from exc
    return converted


def validate_baseline_data(
    field_G: Any, intensity: Any
) -> tuple[np.ndarray, np.ndarray, str]:
    """Validate and copy ``field_G``/``intensity``; return the field direction.

    Raises :class:`PreprocessingError` (code ``array`` or ``nonfinite``) and
    :class:`NonMonotonicFieldError` (code ``field_duplicate`` or
    ``field_not_monotonic``). Nothing is sorted, merged or repaired.
    """
    field_values = _as_float_1d(field_G, "field_G")
    intensity_values = _as_float_1d(intensity, "intensity")

    if field_values.size == 0:
        raise PreprocessingError(
            "The data arrays are empty.", code="array"
        )
    if field_values.size != intensity_values.size:
        raise PreprocessingError(
            "field_G and intensity must have the same length "
            f"({field_values.size} != {intensity_values.size}).",
            code="array",
        )
    if not np.all(np.isfinite(field_values)) or not np.all(
        np.isfinite(intensity_values)
    ):
        raise NonFiniteDataError(
            "The data contain NaN or infinite values; baseline correction is "
            "not possible without changing the data.",
            code="nonfinite",
            context={
                "nonfinite_field": int(np.sum(~np.isfinite(field_values))),
                "nonfinite_intensity": int(np.sum(~np.isfinite(intensity_values))),
            },
        )
    if field_values.size < 2:
        raise PreprocessingError(
            "At least two data points are required to define a field axis.",
            code="array",
        )

    direction = _field_direction(field_values)
    return field_values, intensity_values, direction


def _field_direction(field_values: np.ndarray) -> str:
    diffs = np.diff(field_values)
    duplicate_steps = int(np.sum(diffs == 0))
    if duplicate_steps:
        raise NonMonotonicFieldError(
            "The magnetic-field axis contains repeated adjacent values and is "
            "not strictly monotonic. Baseline correction was refused; no rows "
            "were removed or merged.",
            code="field_duplicate",
            context={"duplicates": duplicate_steps},
        )
    if np.all(diffs > 0):
        return "strictly increasing"
    if np.all(diffs < 0):
        return "strictly decreasing"
    raise NonMonotonicFieldError(
        "The magnetic-field axis is not strictly monotonic. Baseline "
        "correction was refused; the rows were not sorted or repaired.",
        code="field_not_monotonic",
        context={"decreasing_steps": int(np.sum(diffs < 0))},
    )


def _window_mask(field_values: np.ndarray, window: BaselineWindow) -> np.ndarray:
    return (field_values >= window.start) & (field_values <= window.end)


def validate_baseline_spec(
    field_values: np.ndarray, spec: LinearBaselineSpec
) -> tuple[int, int]:
    """Validate the two windows against the field axis.

    Returns ``(points_left, points_right)``. Raises :class:`BaselineWindowError`
    with a specific ``code`` when a window is reversed, outside the field
    range, too sparse, overlapping, or not separated by an unselected point.
    """
    left = spec.window_left
    right = spec.window_right
    field_values = np.asarray(field_values, dtype=np.float64)

    field_min = float(field_values.min())
    field_max = float(field_values.max())
    tolerance = 1e-9 * max(1.0, field_max - field_min)

    for window in (left, right):
        if window.start < field_min - tolerance or window.end > field_max + tolerance:
            raise BaselineWindowError(
                f"Baseline window {window.start:.4f}-{window.end:.4f} G lies "
                f"outside the field range {field_min:.4f}-{field_max:.4f} G.",
                code="window_outside",
                context={
                    "start": window.start,
                    "end": window.end,
                    "field_min": field_min,
                    "field_max": field_max,
                },
            )

    if left.start >= right.start:
        raise BaselineWindowError(
            "The left baseline window must start below the right window "
            f"(left start {left.start:.4f} G, right start "
            f"{right.start:.4f} G).",
            code="window_order",
            context={"left_start": left.start, "right_start": right.start},
        )

    if left.end >= right.start:
        raise BaselineWindowError(
            "The baseline windows overlap or share an endpoint "
            f"(left end {left.end:.4f} G >= right start {right.start:.4f} G).",
            code="window_overlap",
            context={"left_end": left.end, "right_start": right.start},
        )

    gap_count = int(
        np.sum((field_values > left.end) & (field_values < right.start))
    )
    if gap_count < MIN_UNSELECTED_POINTS_BETWEEN_WINDOWS:
        raise BaselineWindowError(
            "At least "
            f"{MIN_UNSELECTED_POINTS_BETWEEN_WINDOWS} unselected data point(s) "
            f"must remain between the windows; found {gap_count}.",
            code="window_gap",
            context={
                "count": gap_count,
                "required": MIN_UNSELECTED_POINTS_BETWEEN_WINDOWS,
            },
        )

    points_left = int(np.sum(_window_mask(field_values, left)))
    points_right = int(np.sum(_window_mask(field_values, right)))
    for window, count in ((left, points_left), (right, points_right)):
        if count < MIN_POINTS_PER_WINDOW:
            raise BaselineWindowError(
                f"Baseline window {window.start:.4f}-{window.end:.4f} G "
                f"contains only {count} data point(s); at least "
                f"{MIN_POINTS_PER_WINDOW} are required.",
                code="window_points",
                context={
                    "start": window.start,
                    "end": window.end,
                    "count": count,
                    "required": MIN_POINTS_PER_WINDOW,
                },
            )

    return points_left, points_right


def _noise_sigma(values: np.ndarray) -> float:
    """Robust noise estimate from first differences (median absolute deviation)."""
    if values.size < 3:
        return 0.0
    diffs = np.diff(values)
    median = float(np.median(diffs))
    mad = float(np.median(np.abs(diffs - median)))
    return 1.4826 * mad / np.sqrt(2.0)


def _ols_line(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Ordinary least squares for ``y = slope*x + intercept`` (centered)."""
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    x_centered = x - x_mean
    denominator = float(np.dot(x_centered, x_centered))
    if denominator <= 0.0:
        raise DegenerateFitError(
            "The field values in the baseline windows have zero variance, so "
            "a straight line is undefined.",
            code="degenerate",
        )
    slope = float(np.dot(x_centered, y - y_mean) / denominator)
    intercept = y_mean - slope * x_mean
    if not (np.isfinite(slope) and np.isfinite(intercept)):
        raise PreprocessingError(
            "The linear baseline fit produced non-finite coefficients.",
            code="fit_nonfinite",
        )
    return slope, intercept


def _require_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise PreprocessingError(
            f"{name} must be an integer.",
            code="savgol_parameter",
            context={"name": name},
        )
    return int(value)


def validate_savgol_spec(spec: SavgolSpec, n_points: int) -> None:
    """Validate Savitzky-Golay parameters against the available points."""
    window_length = _require_integer(spec.window_length, "window_length")
    polyorder = _require_integer(spec.polyorder, "polyorder")

    if spec.deriv != 0 or spec.mode != "interp":
        raise PreprocessingError(
            "Only deriv=0 and mode='interp' are supported by this workflow.",
            code="savgol_parameter",
            context={"name": "deriv/mode"},
        )
    if window_length < 3:
        raise PreprocessingError(
            f"window_length must be at least 3; got {window_length}.",
            code="savgol_window_too_small",
            context={"window_length": window_length},
        )
    if window_length % 2 == 0:
        raise PreprocessingError(
            f"window_length must be odd; got {window_length}.",
            code="savgol_window_even",
            context={"window_length": window_length},
        )
    if n_points < window_length:
        raise PreprocessingError(
            f"window_length ({window_length}) exceeds the number of data "
            f"points ({n_points}).",
            code="savgol_window_too_large",
            context={"window_length": window_length, "n_points": int(n_points)},
        )
    if polyorder < 0 or polyorder >= window_length:
        raise PreprocessingError(
            "polyorder must satisfy 0 <= polyorder < window_length "
            f"(polyorder={polyorder}, window_length={window_length}).",
            code="savgol_polyorder",
            context={
                "polyorder": polyorder,
                "window_length": window_length,
            },
        )


def smooth_savgol(
    intensity: Any, spec: SavgolSpec
) -> tuple[np.ndarray, SavgolDiagnostics]:
    """Apply SciPy's Savitzky-Golay filter to one ordered signal.

    The output has the same length, dtype (float64) and ordering as the input.
    No scaling, normalisation or outlier handling is performed.
    """
    values = _as_float_1d(intensity, "intensity")
    if values.size == 0:
        raise PreprocessingError("The data arrays are empty.", code="array")
    if not np.all(np.isfinite(values)):
        raise NonFiniteDataError(
            "The data contain NaN or infinite values; smoothing is not possible.",
            code="nonfinite",
        )
    validate_savgol_spec(spec, values.size)

    try:
        from scipy.signal import savgol_filter
    except ImportError as exc:
        raise PreprocessingError(
            "SciPy is not available, so Savitzky-Golay smoothing cannot run.",
            code="savgol_unavailable",
        ) from exc

    try:
        output = savgol_filter(
            values,
            window_length=int(spec.window_length),
            polyorder=int(spec.polyorder),
            deriv=0,
            mode="interp",
        )
    except Exception as exc:  # SciPy errors become a clear domain error
        raise PreprocessingError(
            f"Savitzky-Golay smoothing failed: {exc}",
            code="savgol_failed",
        ) from exc

    output = np.asarray(output, dtype=np.float64)
    if output.shape != values.shape or not np.all(np.isfinite(output)):
        raise PreprocessingError(
            "Savitzky-Golay smoothing returned an invalid array.",
            code="savgol_output_invalid",
        )

    difference = output - values
    diagnostics = SavgolDiagnostics(
        n_points=int(values.size),
        rms_change=float(np.sqrt(np.mean(difference**2))),
        max_abs_change=float(np.max(np.abs(difference))),
        input_mean=float(np.mean(values)),
        input_std=float(values.std(ddof=1)) if values.size > 1 else 0.0,
        output_mean=float(np.mean(output)),
        output_std=float(output.std(ddof=1)) if output.size > 1 else 0.0,
    )
    return output, diagnostics


def fit_linear_baseline(
    field_G: Any,
    intensity: Any,
    spec: LinearBaselineSpec,
) -> tuple[BaselineFit, tuple[PreprocessingWarning, ...]]:
    """Fit one straight baseline over the union of the two windows.

    Does not modify the inputs. Raises on invalid data, a non-strictly
    monotonic field axis, invalid windows, or a degenerate fit.
    """
    field_values, intensity_values, _ = validate_baseline_data(field_G, intensity)
    points_left, points_right = validate_baseline_spec(field_values, spec)

    left = spec.window_left
    right = spec.window_right
    mask = _window_mask(field_values, left) | _window_mask(field_values, right)
    x = field_values[mask]
    y = intensity_values[mask]

    slope, intercept = _ols_line(x, y)

    fitted = slope * x + intercept
    residuals = y - fitted
    ss_res = float(np.dot(residuals, residuals))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r_squared: float | None
    warnings: list[PreprocessingWarning] = []
    if ss_tot == 0.0:
        r_squared = None
        warnings.append(
            PreprocessingWarning(
                code="prep_warning_r2_undefined",
                message=(
                    "Intensity is constant within the selected windows, so "
                    "R-squared is undefined (the slope may be zero)."
                ),
            )
        )
    else:
        r_squared = float(1.0 - ss_res / ss_tot)

    left_residuals = intensity_values[_window_mask(field_values, left)] - (
        slope * field_values[_window_mask(field_values, left)] + intercept
    )
    right_residuals = intensity_values[_window_mask(field_values, right)] - (
        slope * field_values[_window_mask(field_values, right)] + intercept
    )
    rms_left = float(np.sqrt(np.mean(left_residuals**2)))
    rms_right = float(np.sqrt(np.mean(right_residuals**2)))
    rms_total = float(np.sqrt(np.mean(residuals**2)))

    field_min = float(field_values.min())
    field_max = float(field_values.max())
    span = field_max - field_min
    extrapolation_left = float(left.start - field_min)
    extrapolation_right = float(field_max - right.end)
    selected_fraction = float((points_left + points_right) / field_values.size)
    window_span_fraction = (
        float(((left.end - left.start) + (right.end - right.start)) / span)
        if span > 0
        else 1.0
    )

    for window, count in ((left, points_left), (right, points_right)):
        if count < FEW_POINTS_THRESHOLD:
            warnings.append(
                PreprocessingWarning(
                    code="prep_warning_few_points",
                    message=(
                        f"Baseline window {window.start:.4f}-{window.end:.4f} G "
                        f"contains only {count} data point(s) (minimum "
                        f"{MIN_POINTS_PER_WINDOW}). This is a computational "
                        "minimum, not evidence that the region is a valid "
                        "baseline."
                    ),
                    context={
                        "start": window.start,
                        "end": window.end,
                        "count": count,
                        "required": MIN_POINTS_PER_WINDOW,
                    },
                )
            )

    limit = EXTRAPOLATION_WARNING_FRACTION * span
    if extrapolation_left > limit or extrapolation_right > limit:
        warnings.append(
            PreprocessingWarning(
                code="prep_warning_extrapolation",
                message=(
                    "The baseline windows leave a large extrapolation region: "
                    f"left {extrapolation_left:.4f} G, right "
                    f"{extrapolation_right:.4f} G (threshold {limit:.4f} G)."
                ),
                context={
                    "left": extrapolation_left,
                    "right": extrapolation_right,
                    "threshold": float(limit),
                },
            )
        )

    if selected_fraction < LOW_COVERAGE_WARNING_FRACTION:
        warnings.append(
            PreprocessingWarning(
                code="prep_warning_coverage_low",
                message=(
                    "The baseline windows contain only "
                    f"{selected_fraction:.2%} of the data points, which is "
                    "very sparse."
                ),
                context={"fraction": selected_fraction},
            )
        )
    if window_span_fraction > HIGH_COVERAGE_WARNING_FRACTION:
        warnings.append(
            PreprocessingWarning(
                code="prep_warning_coverage_high",
                message=(
                    "The two windows together cover "
                    f"{window_span_fraction:.2%} of the field span and may "
                    "include real signal."
                ),
                context={"fraction": window_span_fraction},
            )
        )

    noise = _noise_sigma(intensity_values)
    if noise > 0.0:
        threshold = NOISY_WINDOW_SIGMA_FACTOR * noise
        if rms_left > threshold or rms_right > threshold:
            warnings.append(
                PreprocessingWarning(
                    code="prep_warning_noisy_window",
                    message=(
                        "A baseline window deviates strongly from the fitted "
                        f"line (residual RMS left {rms_left:.6g}, right "
                        f"{rms_right:.6g}; global noise estimate {noise:.6g}). "
                        "That region may contain real signal rather than a "
                        "pure baseline."
                    ),
                    context={
                        "left_rms": rms_left,
                        "right_rms": rms_right,
                        "noise": noise,
                    },
                )
            )

    fit = BaselineFit(
        slope=slope,
        intercept=intercept,
        r_squared=r_squared,
        rms_residual=rms_total,
        field_centroid_G=float(np.mean(x)),
        intensity_centroid=float(np.mean(y)),
        n_points=int(x.size),
        n_points_left=points_left,
        n_points_right=points_right,
        residual_rms_left=rms_left,
        residual_rms_right=rms_right,
        extrapolation_left_G=extrapolation_left,
        extrapolation_right_G=extrapolation_right,
        selected_fraction=selected_fraction,
        window_span_fraction=window_span_fraction,
    )
    return fit, tuple(warnings)



__all__ = [
    "BASELINE_ALGORITHM_VERSION",
    "BASELINE_METHOD",
    "BASELINE_OPERATION",
    "BaselineFit",
    "BaselineWindow",
    "BaselineWindowError",
    "DegenerateFitError",
    "EprProcessingError",
    "FEW_POINTS_THRESHOLD",
    "LinearBaselineSpec",
    "MIN_POINTS_PER_WINDOW",
    "MIN_UNSELECTED_POINTS_BETWEEN_WINDOWS",
    "NonFiniteDataError",
    "NonMonotonicFieldError",
    "PreprocessingError",
    "PreprocessingWarning",
    "SAVGOL_ALGORITHM_VERSION",
    "SAVGOL_METHOD",
    "SAVGOL_OPERATION",
    "SavgolDiagnostics",
    "SavgolSpec",
    "fit_linear_baseline",
    "smooth_savgol",
    "validate_baseline_data",
    "validate_baseline_spec",
    "validate_savgol_spec",
]
