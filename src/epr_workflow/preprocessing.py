"""User-selected linear baseline correction for CW-EPR spectra.

This module is pure (NumPy only, no pandas, no Qt) and never touches the
source file. It provides:

* immutable descriptors for baseline windows and linear-baseline steps;
* validation of arrays, field axis and windows;
* ordinary-least-squares fitting over the union of two field windows;
* a :class:`PreprocessingSession` that keeps the raw arrays read-only and
  recomputes every result from them, step by step;
* an English processing record for JSON metadata.

Only the explicitly requested operation exists here. Smoothing, normalisation,
interpolation, clipping, outlier removal and signal fitting are deliberately
not implemented.

Scientific convention
---------------------
The corrected signal is ``intensity_raw - (slope * field_G + intercept)``.
A linear baseline is meaningful only if the baseline is additive in the
(undocumented) intensity units and if both selected windows are baseline-only;
these assumptions are recorded, never enforced silently.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

#: Minimum number of data points in each baseline window. This is only the
#: minimum required to make a straight-line fit computable; it is not evidence
#: that the region is a valid baseline.
MIN_POINTS_PER_WINDOW = 3

#: Minimum number of unselected data points that must remain between the two
#: windows, so the two regions are genuinely separate.
MIN_UNSELECTED_POINTS_BETWEEN_WINDOWS = 1

#: Small window sizes (in points) that trigger an informational warning.
FEW_POINTS_THRESHOLD = 5

#: Operation name stored in processing records.
BASELINE_OPERATION = "linear_baseline"
BASELINE_METHOD = "ordinary_least_squares_union_of_windows"
BASELINE_ALGORITHM_VERSION = "1.0"
SCHEMA_VERSION = "1.0"

#: Fractions used for diagnostic warnings (never for automatic decisions).
EXTRAPOLATION_WARNING_FRACTION = 0.25
LOW_COVERAGE_WARNING_FRACTION = 0.02
HIGH_COVERAGE_WARNING_FRACTION = 0.50
NOISY_WINDOW_SIGMA_FACTOR = 3.0

SAVGOL_OPERATION = "savitzky_golay"
SAVGOL_METHOD = "scipy.signal.savgol_filter"
SAVGOL_ALGORITHM_VERSION = "1.0"

#: Where a smoothing step takes its input from.
INPUT_RAW = "raw_data"
INPUT_CURRENT = "current_processed_result"


class PreprocessingError(ValueError):
    """Base class for preprocessing failures.

    ``code`` is a stable identifier used by the GUI to show a translated
    message; ``context`` holds the values needed to format it. ``str(exc)``
    remains the canonical English text used in logs and records.
    """

    default_code = "generic"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self.default_code
        self.context: dict[str, Any] = dict(context or {})


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


def _operation_method(operation: str) -> tuple[str, str]:
    if operation == BASELINE_OPERATION:
        return BASELINE_METHOD, BASELINE_ALGORITHM_VERSION
    if operation == SAVGOL_OPERATION:
        return SAVGOL_METHOD, SAVGOL_ALGORITHM_VERSION
    raise PreprocessingError(
        f"Unsupported preprocessing operation: {operation}",
        code="unsupported_operation",
        context={"operation": operation},
    )


@dataclass(frozen=True)
class PreprocessingStep:
    """One applied (or pending) operation, with its fitted parameters."""

    operation: str
    spec: LinearBaselineSpec | SavgolSpec
    fit: BaselineFit | None
    warnings: tuple[PreprocessingWarning, ...]
    applied_at_utc: str
    smoothing: SavgolDiagnostics | None = None
    #: ``raw_data`` or ``current_processed_result`` at the time of the step.
    input_source: str = INPUT_RAW
    #: Number of processing steps that preceded the input of this step.
    input_step_count: int = 0

    def as_record(self, index: int, source_sha256: str) -> dict[str, Any]:
        method, algorithm_version = _operation_method(self.operation)
        # The effective input of a step is determined by its position in the
        # final order. Existing steps that were moved behind a newly prepended
        # smoothing step keep their original fitted parameters, so that origin
        # is recorded separately as ``fit_input_source``.
        effective_source = INPUT_RAW if index == 1 else INPUT_CURRENT
        effective_count = 0 if index == 1 else index - 1

        if self.operation == BASELINE_OPERATION:
            if not isinstance(self.spec, LinearBaselineSpec) or self.fit is None:
                raise PreprocessingError(
                    "Baseline step is missing its specification or fit.",
                    code="unsupported_operation",
                )
            parameters = {
                "windows_G": [
                    {
                        "start": self.spec.window_left.start,
                        "end": self.spec.window_left.end,
                        "points": self.fit.n_points_left,
                    },
                    {
                        "start": self.spec.window_right.start,
                        "end": self.spec.window_right.end,
                        "points": self.fit.n_points_right,
                    },
                ],
                "inclusive_bounds": True,
                "weighting": "none",
                "points_used": self.fit.n_points,
                "input_source": effective_source,
                "input_step_count": effective_count,
                "fit_input_source": self.input_source,
            }
            fit_record: dict[str, Any] | None = self.fit.as_dict()
            smoothing_record = None
            output_definition = (
                "intensity_corrected = intensity_input - "
                "(slope * field_G + intercept)"
            )
        elif self.operation == SAVGOL_OPERATION:
            if not isinstance(self.spec, SavgolSpec) or self.smoothing is None:
                raise PreprocessingError(
                    "Smoothing step is missing its specification or diagnostics.",
                    code="unsupported_operation",
                )
            parameters = {
                "window_length": int(self.spec.window_length),
                "polyorder": int(self.spec.polyorder),
                "deriv": int(self.spec.deriv),
                "mode": self.spec.mode,
                "input_source": effective_source,
                "input_step_count": effective_count,
                "fit_input_source": self.input_source,
                "input_points": self.smoothing.n_points,
            }
            fit_record = None
            smoothing_record = self.smoothing.as_dict()
            output_definition = (
                "intensity_smoothed = scipy.signal.savgol_filter("
                "intensity_input, window_length, polyorder, deriv=0, "
                "mode='interp')"
            )
        else:
            raise PreprocessingError(
                f"Unsupported preprocessing operation: {self.operation}",
                code="unsupported_operation",
                context={"operation": self.operation},
            )

        record: dict[str, Any] = {
            "index": index,
            "operation": self.operation,
            "method": method,
            "algorithm": {
                "name": method,
                "version": algorithm_version,
            },
            "parameters": parameters,
            "warnings": [warning.as_dict() for warning in self.warnings],
            "applied_at_utc": self.applied_at_utc,
            "source_sha256": source_sha256,
            "output_definition": output_definition,
            "software": _software_versions(),
        }
        if fit_record is not None:
            record["fit"] = fit_record
        if smoothing_record is not None:
            record["diagnostics"] = smoothing_record
        return record


@dataclass(frozen=True)
class PreprocessingResult:
    """One consistent view of raw and processed arrays.

    All arrays are float64, one-dimensional and read-only. ``steps`` includes
    a pending preview step when ``is_preview`` is true; previews must never be
    written to disk.
    """

    source: Path
    source_sha256: str
    field_G: np.ndarray
    intensity_raw: np.ndarray
    intensity_processed: np.ndarray
    removed_baseline: np.ndarray
    steps: tuple[PreprocessingStep, ...]
    warnings: tuple[PreprocessingWarning, ...]
    last_fit: BaselineFit | None
    is_preview: bool
    field_direction: str

    @property
    def has_steps(self) -> bool:
        return bool(self.steps)

    @property
    def difference(self) -> np.ndarray:
        """Total change from raw to processed (raw - processed)."""
        return self.removed_baseline

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(step.operation for step in self.steps)

    @property
    def has_smoothing(self) -> bool:
        return any(
            step.operation == SAVGOL_OPERATION for step in self.steps
        )


def _software_versions() -> dict[str, str]:
    # Imported lazily so that this module can be imported by the package's
    # own __init__ without a circular import.
    from epr_workflow import __version__ as workflow_version

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": _scipy_version(),
        "epr_workflow": workflow_version,
    }


def _scipy_version() -> str:
    try:
        import scipy
    except Exception:
        return "not installed"
    return scipy.__version__


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


def _timestamp_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class _PendingStep:
    """Parameters of a preview that has not been committed."""

    operation: str
    baseline_spec: LinearBaselineSpec | None = None
    savgol_spec: SavgolSpec | None = None
    input_source: str = INPUT_CURRENT
    input_step_count: int = 0


class PreprocessingSession:
    """Per-file, in-memory preprocessing state.

    The constructor copies the raw arrays and marks them read-only. Every
    applied result is recomputed from those raw arrays using the recorded step
    parameters, so undo and reset can never modify the raw data. Results are
    cached until the step list changes, so switching the GUI language cannot
    re-run a smoothing or fitting algorithm.
    """

    def __init__(
        self,
        *,
        source: str | Path,
        field_G: Any,
        intensity: Any,
        source_sha256: str = "",
    ) -> None:
        field_values, intensity_values, direction = validate_baseline_data(
            field_G, intensity
        )
        field_values.setflags(write=False)
        intensity_values.setflags(write=False)
        self._source = Path(source)
        self._source_sha256 = str(source_sha256)
        self._field = field_values
        self._intensity = intensity_values
        self._field_direction = direction
        self._steps: list[PreprocessingStep] = []
        self._pending: _PendingStep | None = None
        self._cached_result: PreprocessingResult | None = None

    # ------------------------------------------------------------ properties
    @property
    def source(self) -> Path:
        return self._source

    @property
    def source_sha256(self) -> str:
        return self._source_sha256

    @property
    def steps(self) -> tuple[PreprocessingStep, ...]:
        return tuple(self._steps)

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(step.operation for step in self._steps)

    @property
    def has_steps(self) -> bool:
        return bool(self._steps)

    @property
    def field_direction(self) -> str:
        return self._field_direction

    # ------------------------------------------------------------ operations
    def preview(self, spec: LinearBaselineSpec) -> PreprocessingResult:
        """Preview a baseline step. Kept as the phase-1 public entry point."""
        return self.preview_baseline(spec)

    def preview_baseline(self, spec: LinearBaselineSpec) -> PreprocessingResult:
        """Compute a result including a pending baseline step; no commit."""
        input_source = INPUT_RAW if not self._steps else INPUT_CURRENT
        input_count = len(self._steps)
        step = self._make_baseline_step(
            spec, self._intensity_current(), input_source, input_count
        )
        self._pending = _PendingStep(
            operation=BASELINE_OPERATION,
            baseline_spec=spec,
            input_source=input_source,
            input_step_count=input_count,
        )
        return self._build_result((*self._steps, step), is_preview=True)

    def preview_savgol(
        self,
        spec: SavgolSpec,
        *,
        input_source: str = INPUT_CURRENT,
    ) -> PreprocessingResult:
        """Preview a Savitzky-Golay step on raw data or the current result."""
        source, input_count = self._resolve_smoothing_input(input_source)
        input_values = (
            self._intensity.copy()
            if source == INPUT_RAW
            else self._intensity_current()
        )
        step = self._make_savgol_step(spec, input_values, source, input_count)
        self._pending = _PendingStep(
            operation=SAVGOL_OPERATION,
            savgol_spec=spec,
            input_source=source,
            input_step_count=input_count,
        )
        if source == INPUT_RAW and self._steps:
            order = (step, *self._steps)
        else:
            order = (*self._steps, step)
        return self._build_result(order, is_preview=True)

    def discard_preview(self) -> None:
        self._pending = None

    def apply(self, spec: LinearBaselineSpec | None = None) -> PreprocessingResult:
        """Commit a pending step, or a baseline step supplied as ``spec``."""
        if spec is None:
            if self._pending is None:
                raise PreprocessingError(
                    "There are no pending preview parameters to apply.",
                    code="no_pending",
                )
            return self.apply_pending()
        input_source = INPUT_RAW if not self._steps else INPUT_CURRENT
        self._pending = _PendingStep(
            operation=BASELINE_OPERATION,
            baseline_spec=spec,
            input_source=input_source,
            input_step_count=len(self._steps),
        )
        return self.apply_pending()

    def apply_savgol(
        self,
        spec: SavgolSpec | None = None,
        *,
        input_source: str = INPUT_CURRENT,
    ) -> PreprocessingResult:
        """Commit a pending smoothing step, or a smoothing step given directly."""
        if spec is None:
            if self._pending is None or self._pending.operation != SAVGOL_OPERATION:
                raise PreprocessingError(
                    "There are no pending smoothing parameters to apply.",
                    code="no_pending",
                )
            return self.apply_pending()
        source, input_count = self._resolve_smoothing_input(input_source)
        self._pending = _PendingStep(
            operation=SAVGOL_OPERATION,
            savgol_spec=spec,
            input_source=source,
            input_step_count=input_count,
        )
        return self.apply_pending()

    def apply_pending(self) -> PreprocessingResult:
        """Commit the current preview (any supported operation)."""
        if self._pending is None:
            raise PreprocessingError(
                "There are no pending preview parameters to apply.",
                code="no_pending",
            )
        pending = self._pending
        current_values = self._intensity_current()

        if pending.operation == BASELINE_OPERATION:
            if pending.baseline_spec is None:
                raise PreprocessingError(
                    "The pending baseline step is incomplete.",
                    code="no_pending",
                )
            step = self._make_baseline_step(
                pending.baseline_spec,
                current_values,
                pending.input_source,
                pending.input_step_count,
            )
            self._steps.append(step)
        elif pending.operation == SAVGOL_OPERATION:
            if pending.savgol_spec is None:
                raise PreprocessingError(
                    "The pending smoothing step is incomplete.",
                    code="no_pending",
                )
            input_values = (
                self._intensity.copy()
                if pending.input_source == INPUT_RAW
                else current_values
            )
            step = self._make_savgol_step(
                pending.savgol_spec,
                input_values,
                pending.input_source,
                pending.input_step_count,
            )
            if pending.input_source == INPUT_RAW and self._steps:
                self._steps.insert(0, step)
            else:
                self._steps.append(step)
        else:
            raise PreprocessingError(
                f"Unsupported pending operation: {pending.operation}",
                code="unsupported_operation",
                context={"operation": pending.operation},
            )

        self._pending = None
        self._invalidate_cache()
        return self.current_result()

    def undo(self) -> PreprocessingResult:
        """Remove the most recent step and recompute from the raw data."""
        if self._steps:
            self._steps.pop()
        self._pending = None
        self._invalidate_cache()
        return self.current_result()

    def reset(self) -> PreprocessingResult:
        """Discard every step and return the raw spectrum."""
        self._steps.clear()
        self._pending = None
        self._invalidate_cache()
        return self.current_result()

    def current_result(self) -> PreprocessingResult:
        if self._cached_result is None:
            self._cached_result = self._build_result(
                tuple(self._steps), is_preview=False
            )
        return self._cached_result

    # ------------------------------------------------------------- internals
    def _invalidate_cache(self) -> None:
        self._cached_result = None

    def _resolve_smoothing_input(self, input_source: str) -> tuple[str, int]:
        if input_source not in (INPUT_RAW, INPUT_CURRENT):
            raise PreprocessingError(
                f"Unsupported smoothing input source: {input_source}",
                code="savgol_input_source",
                context={"source": input_source},
            )
        if not self._steps:
            return INPUT_RAW, 0
        if input_source == INPUT_RAW:
            return INPUT_RAW, 0
        return INPUT_CURRENT, len(self._steps)

    def _intensity_current(self) -> np.ndarray:
        return self.current_result().intensity_processed.copy()

    def _make_baseline_step(
        self,
        spec: LinearBaselineSpec,
        input_values: np.ndarray,
        input_source: str,
        input_count: int,
    ) -> PreprocessingStep:
        fit, warnings = fit_linear_baseline(self._field, input_values, spec)
        return PreprocessingStep(
            operation=BASELINE_OPERATION,
            spec=spec,
            fit=fit,
            warnings=warnings,
            applied_at_utc=_timestamp_utc(),
            input_source=input_source,
            input_step_count=input_count,
        )

    def _make_savgol_step(
        self,
        spec: SavgolSpec,
        input_values: np.ndarray,
        input_source: str,
        input_count: int,
    ) -> PreprocessingStep:
        _, diagnostics = smooth_savgol(input_values, spec)
        warnings: list[PreprocessingWarning] = []
        if input_source == INPUT_RAW and self._steps:
            warnings.append(
                PreprocessingWarning(
                    code="prep_warning_smoothing_reorders",
                    message=(
                        "Smoothing was applied to the raw data before the "
                        f"{len(self._steps)} existing step(s); the processing "
                        "order is now smoothing, then the existing steps. The "
                        "existing steps keep their fitted parameters and are "
                        "applied to the smoothed data."
                    ),
                    context={"step_count": len(self._steps)},
                )
            )
        return PreprocessingStep(
            operation=SAVGOL_OPERATION,
            spec=spec,
            fit=None,
            warnings=tuple(warnings),
            applied_at_utc=_timestamp_utc(),
            smoothing=diagnostics,
            input_source=input_source,
            input_step_count=input_count,
        )

    def _apply_step(
        self, values: np.ndarray, step: PreprocessingStep
    ) -> np.ndarray:
        if step.operation == BASELINE_OPERATION:
            if step.fit is None:
                raise PreprocessingError(
                    "Baseline step is missing its fit.", code="unsupported_operation"
                )
            return values - (
                step.fit.slope * self._field + step.fit.intercept
            )
        if step.operation == SAVGOL_OPERATION:
            if not isinstance(step.spec, SavgolSpec):
                raise PreprocessingError(
                    "Smoothing step has an invalid specification.",
                    code="unsupported_operation",
                )
            output, _ = smooth_savgol(values, step.spec)
            return output
        raise PreprocessingError(
            f"Unsupported preprocessing operation: {step.operation}",
            code="unsupported_operation",
            context={"operation": step.operation},
        )

    def _build_result(
        self,
        steps: tuple[PreprocessingStep, ...],
        *,
        is_preview: bool,
    ) -> PreprocessingResult:
        processed = self._intensity.copy()
        for step in steps:
            processed = self._apply_step(processed, step)
        removed = self._intensity - processed
        for array in (processed, removed):
            array.setflags(write=False)

        warnings: list[PreprocessingWarning] = []
        for step in steps:
            warnings.extend(step.warnings)

        last_fit = next(
            (step.fit for step in reversed(steps) if step.fit is not None),
            None,
        )
        return PreprocessingResult(
            source=self._source,
            source_sha256=self._source_sha256,
            field_G=self._field,
            intensity_raw=self._intensity,
            intensity_processed=processed,
            removed_baseline=removed,
            steps=steps,
            warnings=tuple(warnings),
            last_fit=last_fit,
            is_preview=is_preview,
            field_direction=self._field_direction,
        )


def apply_linear_baseline(
    *,
    source: str | Path,
    field_G: Any,
    intensity: Any,
    spec: LinearBaselineSpec,
    source_sha256: str = "",
) -> PreprocessingResult:
    """One-shot convenience wrapper around :class:`PreprocessingSession`."""
    session = PreprocessingSession(
        source=source,
        field_G=field_G,
        intensity=intensity,
        source_sha256=source_sha256,
    )
    return session.apply(spec)


def processing_data_kind(steps: tuple[PreprocessingStep, ...] | list[PreprocessingStep]) -> str:
    """Return the exported data kind for the applied step sequence."""
    operations = {step.operation for step in steps}
    has_baseline = BASELINE_OPERATION in operations
    has_smoothing = SAVGOL_OPERATION in operations
    if has_baseline and has_smoothing:
        return "baseline_corrected_and_smoothed"
    if has_baseline:
        return "baseline_corrected"
    if has_smoothing:
        return "smoothed"
    return "none"


def build_preprocessing_record(result: PreprocessingResult) -> dict[str, Any]:
    """Build the English ``preprocessing`` block for the exported metadata."""
    steps = [
        step.as_record(index, result.source_sha256)
        for index, step in enumerate(result.steps, start=1)
    ]
    operations = [step.operation for step in result.steps]
    algorithm_list = [
        {
            "operation": step.operation,
            "name": _operation_method(step.operation)[0],
            "version": _operation_method(step.operation)[1],
        }
        for step in result.steps
    ]

    assumptions: list[str] = []
    if BASELINE_OPERATION in operations:
        assumptions.extend(
            [
                "The intensity baseline is additive in the undocumented "
                "intensity units.",
                "One straight line represents the baseline across the "
                "displayed field range.",
                "The selected windows contain baseline only; this is the "
                "user's scientific judgement and is not verified by the "
                "software.",
            ]
        )
    if SAVGOL_OPERATION in operations:
        assumptions.extend(
            [
                "Savitzky-Golay smoothing fits a local polynomial over a "
                "fixed-width window and replaces each point by that local fit.",
                "Smoothing can change peak height, peak width and line shape; "
                "it does not by itself establish improved data quality.",
                "No scaling or normalisation is applied to exported values.",
            ]
        )

    not_applied = [
        "normalisation",
        "interpolation",
        "clipping",
        "outlier_removal",
        "signal_curve_fitting",
        "field_axis_reversal",
    ]
    if BASELINE_OPERATION not in operations:
        not_applied.insert(0, "baseline_correction")
    if SAVGOL_OPERATION not in operations:
        not_applied.insert(0, "smoothing")

    return {
        "schema_version": SCHEMA_VERSION,
        "data_kind": processing_data_kind(result.steps),
        "algorithm": (
            {
                "name": algorithm_list[-1]["name"],
                "version": algorithm_list[-1]["version"],
            }
            if algorithm_list
            else None
        ),
        "algorithms": algorithm_list,
        "applied": bool(result.steps) and not result.is_preview,
        "is_preview": result.is_preview,
        "source_file": result.source.name,
        "source_path": str(result.source),
        "source_sha256": result.source_sha256,
        "field_direction": result.field_direction,
        "step_order": operations,
        "steps": steps,
        "assumptions": assumptions,
        "not_applied": not_applied,
        "warnings": [warning.as_dict() for warning in result.warnings],
        "raw_data_modified": False,
    }
