"""Unit tests for the pure linear-baseline preprocessing module."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from epr_workflow.preprocessing import (
    MIN_POINTS_PER_WINDOW,
    BaselineWindow,
    BaselineWindowError,
    DegenerateFitError,
    LinearBaselineSpec,
    NonFiniteDataError,
    NonMonotonicFieldError,
    PreprocessingError,
    PreprocessingSession,
    apply_linear_baseline,
    build_preprocessing_record,
    fit_linear_baseline,
    validate_baseline_data,
    validate_baseline_spec,
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def make_field(n: int = 101, *, start: float = 3280.0, step: float = 1.0) -> np.ndarray:
    return start + step * np.arange(n, dtype=float)


def make_spectrum(
    n: int = 101,
    *,
    slope: float = 2.0,
    intercept: float = 5.0,
    peak_height: float = 500.0,
    peak_center: float = 3330.0,
    peak_width: float = 5.0,
) -> tuple[np.ndarray, np.ndarray]:
    field = make_field(n)
    baseline = slope * field + intercept
    peak = peak_height * np.exp(-((field - peak_center) / peak_width) ** 2)
    return field, baseline + peak


def default_spec() -> LinearBaselineSpec:
    return LinearBaselineSpec(
        window_left=BaselineWindow(3280.0, 3284.0),
        window_right=BaselineWindow(3376.0, 3380.0),
    )


def window_mask(field: np.ndarray, window: BaselineWindow) -> np.ndarray:
    return (field >= window.start) & (field <= window.end)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def test_validate_returns_copies_and_direction() -> None:
    field, intensity = make_spectrum()
    field_copy = field.copy()
    intensity_copy = intensity.copy()

    out_field, out_intensity, direction = validate_baseline_data(field, intensity)

    assert direction == "strictly increasing"
    np.testing.assert_array_equal(out_field, field_copy)
    np.testing.assert_array_equal(out_intensity, intensity_copy)
    out_field[0] = -1.0  # the returned array is a copy
    assert field[0] == field_copy[0]


def test_decreasing_field_is_strictly_monotonic() -> None:
    field, intensity = make_spectrum()
    reversed_field = field[::-1].copy()
    reversed_intensity = intensity[::-1].copy()

    _, _, direction = validate_baseline_data(reversed_field, reversed_intensity)

    assert direction == "strictly decreasing"


def test_duplicate_field_values_are_refused() -> None:
    field = make_field(10)
    field[5] = field[4]
    with pytest.raises(NonMonotonicFieldError) as excinfo:
        validate_baseline_data(field, np.zeros_like(field))

    assert excinfo.value.code == "field_duplicate"
    assert excinfo.value.context["duplicates"] == 1


def test_non_monotonic_field_is_refused() -> None:
    field = make_field(10)
    field[[3, 4]] = field[[4, 3]]
    with pytest.raises(NonMonotonicFieldError) as excinfo:
        validate_baseline_data(field, np.zeros_like(field))

    assert excinfo.value.code == "field_not_monotonic"


def test_non_finite_values_are_refused() -> None:
    field, intensity = make_spectrum(10)
    intensity[2] = np.nan
    with pytest.raises(NonFiniteDataError) as excinfo:
        validate_baseline_data(field, intensity)
    assert excinfo.value.code == "nonfinite"

    intensity[2] = np.inf
    with pytest.raises(NonFiniteDataError):
        validate_baseline_data(field, intensity)


@pytest.mark.parametrize(
    "field,intensity",
    [
        ([], []),
        ([1.0, 2.0, 3.0], [1.0, 2.0]),
        ([[1.0, 2.0]], [1.0, 2.0]),
        ([1.0], [1.0]),
        (["a", "b", "c"], [1.0, 2.0, 3.0]),
    ],
)
def test_invalid_arrays_raise_array_code(field, intensity) -> None:
    with pytest.raises(PreprocessingError) as excinfo:
        validate_baseline_data(field, intensity)
    assert excinfo.value.code == "array"


def test_baseline_window_requires_start_before_end() -> None:
    with pytest.raises(BaselineWindowError) as excinfo:
        BaselineWindow(3284.0, 3280.0)
    assert excinfo.value.code == "window_bounds"


def test_baseline_window_requires_finite_bounds() -> None:
    with pytest.raises(BaselineWindowError):
        BaselineWindow(float("nan"), 3284.0)


def test_window_outside_field_range_is_refused() -> None:
    field, _ = make_spectrum()
    spec = LinearBaselineSpec(BaselineWindow(3000.0, 3004.0), BaselineWindow(3376.0, 3380.0))
    with pytest.raises(BaselineWindowError) as excinfo:
        validate_baseline_spec(field, spec)
    assert excinfo.value.code == "window_outside"


def test_window_order_is_refused() -> None:
    field, _ = make_spectrum()
    spec = LinearBaselineSpec(BaselineWindow(3376.0, 3380.0), BaselineWindow(3280.0, 3284.0))
    with pytest.raises(BaselineWindowError) as excinfo:
        validate_baseline_spec(field, spec)
    assert excinfo.value.code == "window_order"


def test_overlapping_windows_are_refused() -> None:
    field, _ = make_spectrum()
    spec = LinearBaselineSpec(BaselineWindow(3280.0, 3300.0), BaselineWindow(3290.0, 3380.0))
    with pytest.raises(BaselineWindowError) as excinfo:
        validate_baseline_spec(field, spec)
    assert excinfo.value.code == "window_overlap"


def test_windows_must_not_share_an_endpoint() -> None:
    field, _ = make_spectrum()
    spec = LinearBaselineSpec(BaselineWindow(3280.0, 3300.0), BaselineWindow(3300.0, 3380.0))
    with pytest.raises(BaselineWindowError) as excinfo:
        validate_baseline_spec(field, spec)
    assert excinfo.value.code == "window_overlap"


def test_at_least_one_unselected_point_between_windows() -> None:
    field = 3280.0 + 0.5 * np.arange(21)
    intensity = field * 2.0
    spec = LinearBaselineSpec(BaselineWindow(3280.0, 3282.0), BaselineWindow(3282.5, 3284.0))
    with pytest.raises(BaselineWindowError) as excinfo:
        validate_baseline_spec(field, spec)
    assert excinfo.value.code == "window_gap"
    assert excinfo.value.context["count"] == 0


def test_window_with_fewer_than_minimum_points_is_refused() -> None:
    field, _ = make_spectrum()
    spec = LinearBaselineSpec(BaselineWindow(3280.0, 3281.0), BaselineWindow(3378.0, 3380.0))
    with pytest.raises(BaselineWindowError) as excinfo:
        validate_baseline_spec(field, spec)
    assert excinfo.value.code == "window_points"
    assert excinfo.value.context["count"] == 2
    assert excinfo.value.context["required"] == MIN_POINTS_PER_WINDOW


# --------------------------------------------------------------------------
# Fit and correction
# --------------------------------------------------------------------------
def test_fit_recovers_a_known_line_exactly() -> None:
    field, intensity = make_spectrum(slope=2.0, intercept=5.0)

    fit, warnings = fit_linear_baseline(field, intensity, default_spec())

    assert fit.slope == pytest.approx(2.0, rel=1e-12, abs=1e-12)
    assert fit.intercept == pytest.approx(5.0, rel=1e-12, abs=1e-9)
    assert fit.r_squared == pytest.approx(1.0, abs=1e-12)
    assert fit.n_points_left == 5
    assert fit.n_points_right == 5
    assert warnings == ()


def test_corrected_baseline_windows_are_near_zero() -> None:
    field, intensity = make_spectrum()
    result = apply_linear_baseline(
        source=Path("synthetic.ASC"),
        field_G=field,
        intensity=intensity,
        spec=default_spec(),
        source_sha256="deadbeef",
    )
    mask = window_mask(field, default_spec().window_left) | window_mask(
        field, default_spec().window_right
    )

    assert abs(float(np.mean(result.intensity_processed[mask]))) < 1e-9
    np.testing.assert_allclose(
        result.removed_baseline, 2.0 * field + 5.0, rtol=0, atol=1e-9
    )
    np.testing.assert_array_equal(
        result.intensity_processed, result.intensity_raw - result.removed_baseline
    )
    assert result.intensity_processed.dtype == np.float64
    assert result.source_sha256 == "deadbeef"


def test_peak_is_preserved_while_baseline_is_removed() -> None:
    field, intensity = make_spectrum(peak_height=500.0)
    result = apply_linear_baseline(
        source=Path("synthetic.ASC"), field_G=field, intensity=intensity, spec=default_spec()
    )
    center = np.argmin(np.abs(field - 3330.0))

    assert result.intensity_processed[center] == pytest.approx(500.0, abs=1e-6)
    assert result.intensity_processed[center] != pytest.approx(0.0, abs=1.0)


def test_inputs_are_not_modified_and_results_are_read_only() -> None:
    field, intensity = make_spectrum()
    field_before = field.copy()
    intensity_before = intensity.copy()
    session = PreprocessingSession(
        source=Path("synthetic.ASC"), field_G=field, intensity=intensity
    )

    preview = session.preview(default_spec())
    applied = session.apply()
    undone = session.undo()
    reset = session.reset()

    np.testing.assert_array_equal(field, field_before)
    np.testing.assert_array_equal(intensity, intensity_before)
    for result in (preview, applied, undone, reset):
        assert not result.intensity_raw.flags.writeable
        assert not result.intensity_processed.flags.writeable
        assert not result.field_G.flags.writeable
        with pytest.raises(ValueError):
            result.intensity_processed[0] = 0.0


def test_decreasing_field_gives_the_same_correction() -> None:
    field, intensity = make_spectrum()
    reversed_result = apply_linear_baseline(
        source=Path("synthetic.ASC"),
        field_G=field[::-1],
        intensity=intensity[::-1],
        spec=default_spec(),
    )
    forward_result = apply_linear_baseline(
        source=Path("synthetic.ASC"),
        field_G=field,
        intensity=intensity,
        spec=default_spec(),
    )

    np.testing.assert_allclose(
        reversed_result.intensity_processed[::-1],
        forward_result.intensity_processed,
        rtol=0,
        atol=1e-12,
    )
    assert reversed_result.field_direction == "strictly decreasing"


def test_repeated_calls_are_deterministic() -> None:
    field, intensity = make_spectrum()
    first = apply_linear_baseline(
        source=Path("synthetic.ASC"), field_G=field, intensity=intensity, spec=default_spec()
    )
    second = apply_linear_baseline(
        source=Path("synthetic.ASC"), field_G=field, intensity=intensity, spec=default_spec()
    )

    np.testing.assert_array_equal(first.intensity_processed, second.intensity_processed)
    assert first.last_fit == second.last_fit


def test_large_offset_keeps_precision() -> None:
    field = make_field(101)
    intensity = 1.0e7 + 1.0e-3 * (field - 3280.0)

    result = apply_linear_baseline(
        source=Path("synthetic.ASC"), field_G=field, intensity=intensity, spec=default_spec()
    )
    mask = window_mask(field, default_spec().window_left) | window_mask(
        field, default_spec().window_right
    )

    assert np.all(np.isfinite(result.intensity_processed))
    assert abs(float(np.mean(result.intensity_processed[mask]))) < 1e-6
    assert result.last_fit is not None
    # The 1e7 offset limits the representable resolution of the input itself
    # to ~2e-9; the recovered slope must still be accurate to that scale.
    assert result.last_fit.slope == pytest.approx(1.0e-3, rel=1e-8)


def test_constant_intensity_has_undefined_r_squared() -> None:
    field = make_field(101)
    intensity = np.full_like(field, 7.0)

    fit, warnings = fit_linear_baseline(field, intensity, default_spec())

    assert fit.slope == 0.0
    assert fit.r_squared is None
    assert any(w.code == "prep_warning_r2_undefined" for w in warnings)


def test_few_points_warning() -> None:
    field = make_field(101)
    intensity = 2.0 * field + 5.0
    spec = LinearBaselineSpec(
        window_left=BaselineWindow(3280.0, 3282.0),
        window_right=BaselineWindow(3378.0, 3380.0),
    )

    _, warnings = fit_linear_baseline(field, intensity, spec)

    few = [w for w in warnings if w.code == "prep_warning_few_points"]
    assert len(few) == 2
    assert all(w.context["count"] == 3 for w in few)


def test_extrapolation_warning() -> None:
    field = make_field(101, start=0.0)
    intensity = 0.5 * field
    spec = LinearBaselineSpec(
        window_left=BaselineWindow(0.0, 2.0),
        window_right=BaselineWindow(10.0, 12.0),
    )

    _, warnings = fit_linear_baseline(field, intensity, spec)

    extrapolation = [w for w in warnings if w.code == "prep_warning_extrapolation"]
    assert len(extrapolation) == 1
    assert extrapolation[0].context["right"] == pytest.approx(88.0)


def test_high_coverage_warning() -> None:
    field = make_field(101, start=0.0)
    intensity = np.zeros_like(field)
    intensity[50] = 1.0
    spec = LinearBaselineSpec(
        window_left=BaselineWindow(0.0, 30.0),
        window_right=BaselineWindow(32.0, 62.0),
    )

    _, warnings = fit_linear_baseline(field, intensity, spec)

    assert any(w.code == "prep_warning_coverage_high" for w in warnings)


def test_low_coverage_warning() -> None:
    field = make_field(1024, start=3280.0, step=0.1)
    intensity = np.zeros_like(field)
    spec = LinearBaselineSpec(
        window_left=BaselineWindow(3280.0, 3280.2),
        window_right=BaselineWindow(3382.0, 3382.2),
    )

    _, warnings = fit_linear_baseline(field, intensity, spec)

    assert any(w.code == "prep_warning_coverage_low" for w in warnings)


def test_noisy_window_warning_when_region_contains_signal() -> None:
    field = make_field(201, start=0.0)
    rng = np.random.default_rng(1234)
    intensity = rng.normal(0.0, 0.01, field.size)
    intensity += 50.0 * np.exp(-((field - 20.0) / 2.0) ** 2)
    spec = LinearBaselineSpec(
        window_left=BaselineWindow(0.0, 2.0),
        window_right=BaselineWindow(18.0, 22.0),
    )

    _, warnings = fit_linear_baseline(field, intensity, spec)

    assert any(w.code == "prep_warning_noisy_window" for w in warnings)


# --------------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------------
def test_preview_does_not_commit_steps() -> None:
    field, intensity = make_spectrum()
    session = PreprocessingSession(
        source=Path("synthetic.ASC"), field_G=field, intensity=intensity
    )

    result = session.preview(default_spec())

    assert result.is_preview is True
    assert len(result.steps) == 1
    assert session.has_steps is False
    assert session.steps == ()


def test_apply_commits_and_undo_reset_recompute_from_raw() -> None:
    field, intensity = make_spectrum()
    session = PreprocessingSession(
        source=Path("synthetic.ASC"), field_G=field, intensity=intensity
    )

    first = session.apply(default_spec())
    assert len(session.steps) == 1
    assert first.is_preview is False
    assert len(first.steps) == 1

    second = session.apply(
        LinearBaselineSpec(
            window_left=BaselineWindow(3280.0, 3284.0),
            window_right=BaselineWindow(3376.0, 3380.0),
        )
    )
    assert len(session.steps) == 2
    assert len(second.steps) == 2

    undone = session.undo()
    assert len(session.steps) == 1
    np.testing.assert_array_equal(
        undone.intensity_processed, first.intensity_processed
    )

    reset = session.reset()
    assert session.steps == ()
    np.testing.assert_array_equal(reset.intensity_processed, reset.intensity_raw)


def test_apply_without_preview_or_spec_is_refused() -> None:
    field, intensity = make_spectrum()
    session = PreprocessingSession(
        source=Path("synthetic.ASC"), field_G=field, intensity=intensity
    )

    with pytest.raises(PreprocessingError) as excinfo:
        session.apply()

    assert excinfo.value.code == "no_pending"


def test_apply_after_preview_uses_preview_parameters() -> None:
    field, intensity = make_spectrum()
    session = PreprocessingSession(
        source=Path("synthetic.ASC"), field_G=field, intensity=intensity
    )

    session.preview(default_spec())
    result = session.apply()

    step = result.steps[0]
    assert step.spec == default_spec()
    assert len(session.steps) == 1


def test_discard_preview_prevents_accidental_apply() -> None:
    field, intensity = make_spectrum()
    session = PreprocessingSession(
        source=Path("synthetic.ASC"), field_G=field, intensity=intensity
    )
    session.preview(default_spec())
    session.discard_preview()

    with pytest.raises(PreprocessingError):
        session.apply()


def test_session_refuses_non_monotonic_field() -> None:
    field = make_field(20)
    field[5] = field[4]
    with pytest.raises(NonMonotonicFieldError):
        PreprocessingSession(
            source=Path("synthetic.ASC"), field_G=field, intensity=np.zeros_like(field)
        )


# --------------------------------------------------------------------------
# Processing record
# --------------------------------------------------------------------------
def test_processing_record_contains_everything_required() -> None:
    field, intensity = make_spectrum()
    session = PreprocessingSession(
        source=Path("synthetic.ASC"),
        field_G=field,
        intensity=intensity,
        source_sha256="abc123",
    )
    result = session.apply(default_spec())

    record = build_preprocessing_record(result)

    assert record["schema_version"] == "1.0"
    assert record["data_kind"] == "baseline_corrected"
    assert record["algorithm"] == {
        "name": "ordinary_least_squares_union_of_windows",
        "version": "1.0",
    }
    assert record["applied"] is True
    assert record["is_preview"] is False
    assert record["source_sha256"] == "abc123"
    assert record["step_order"] == ["linear_baseline"]
    assert record["raw_data_modified"] is False
    assert "smoothing" in record["not_applied"]

    step = record["steps"][0]
    assert step["source_sha256"] == "abc123"
    assert step["operation"] == "linear_baseline"
    assert step["method"] == "ordinary_least_squares_union_of_windows"
    assert step["algorithm"] == {
        "name": "ordinary_least_squares_union_of_windows",
        "version": "1.0",
    }
    windows = step["parameters"]["windows_G"]
    assert windows[0]["start"] == 3280.0
    assert windows[0]["end"] == 3284.0
    assert windows[1]["start"] == 3376.0
    assert windows[1]["end"] == 3380.0
    assert windows[0]["points"] == 5
    assert step["parameters"]["points_used"] == 10
    assert step["fit"]["slope"] == pytest.approx(2.0)
    assert step["fit"]["r_squared"] == pytest.approx(1.0)
    assert step["applied_at_utc"].endswith("+00:00")
    datetime.fromisoformat(step["applied_at_utc"])

    # Must be strict JSON: no NaN/Infinity tokens.
    json.dumps(record, allow_nan=False)


def test_preview_record_is_marked_as_preview() -> None:
    field, intensity = make_spectrum()
    session = PreprocessingSession(
        source=Path("synthetic.ASC"), field_G=field, intensity=intensity
    )

    record = build_preprocessing_record(session.preview(default_spec()))

    assert record["applied"] is False
    assert record["is_preview"] is True
    assert record["step_order"] == ["linear_baseline"]


# --------------------------------------------------------------------------
# Degenerate fit guard
# --------------------------------------------------------------------------
def test_ols_line_rejects_zero_variance() -> None:
    from epr_workflow.preprocessing import _ols_line

    with pytest.raises(DegenerateFitError) as excinfo:
        _ols_line(np.full(5, 3280.0), np.arange(5, dtype=float))

    assert excinfo.value.code == "degenerate"
