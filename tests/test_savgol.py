"""Tests for Savitzky-Golay smoothing and its integration with baseline steps."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from epr_workflow.preprocessing import (
    BASELINE_OPERATION,
    INPUT_CURRENT,
    INPUT_RAW,
    SAVGOL_OPERATION,
    BaselineWindow,
    LinearBaselineSpec,
    NonFiniteDataError,
    PreprocessingError,
    PreprocessingSession,
    SavgolSpec,
    build_preprocessing_record,
    processing_data_kind,
    smooth_savgol,
    validate_savgol_spec,
)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def baseline_spec() -> LinearBaselineSpec:
    return LinearBaselineSpec(
        window_left=BaselineWindow(0.0, 4.0),
        window_right=BaselineWindow(196.0, 200.0),
    )


def spectrum(
    *,
    n: int = 201,
    centers: tuple[float, ...] = (80.0, 120.0),
    widths: tuple[float, ...] = (4.0, 4.0),
    heights: tuple[float, ...] = (1.0, 1.0),
    baseline: float = 0.0,
    noise: float = 0.0,
    seed: int = 1234,
) -> tuple[np.ndarray, np.ndarray]:
    field = np.arange(n, dtype=float)
    values = np.full(n, float(baseline))
    for center, width, height in zip(centers, widths, heights):
        values = values + height * np.exp(-((field - center) / width) ** 2)
    if noise:
        values = values + np.random.default_rng(seed).normal(0.0, noise, n)
    return field, values


def session_for(field: np.ndarray, values: np.ndarray) -> PreprocessingSession:
    return PreprocessingSession(
        source=Path("synthetic.ASC"),
        field_G=field,
        intensity=values,
        source_sha256="abc123",
    )


def fwhm(field: np.ndarray, values: np.ndarray, center_index: int) -> float:
    half = values[center_index] / 2.0
    left = center_index
    while left > 0 and values[left] > half:
        left -= 1
    right = center_index
    while right < len(values) - 1 and values[right] > half:
        right += 1

    def crossing(i: int, j: int) -> float:
        y1, y2 = values[i], values[j]
        if y2 == y1:
            return float(field[i])
        return float(field[i] + (half - y1) * (field[j] - field[i]) / (y2 - y1))

    return crossing(right - 1, right) - crossing(left, left + 1)


def peak_index(values: np.ndarray, lo: int, hi: int) -> int:
    return lo + int(np.argmax(values[lo:hi]))


# --------------------------------------------------------------------------
# Basic algorithm behaviour
# --------------------------------------------------------------------------
def test_constant_input_remains_constant() -> None:
    values = np.full(101, 42.0)
    spec = SavgolSpec(window_length=7, polyorder=3)

    output, diagnostics = smooth_savgol(values, spec)

    np.testing.assert_allclose(output, values, rtol=0, atol=1e-12)
    assert output.shape == values.shape
    assert diagnostics.rms_change <= 1e-12
    assert diagnostics.max_abs_change <= 1e-12


def test_output_length_dtype_and_order_are_preserved() -> None:
    field, values = spectrum(noise=0.01)
    session = session_for(field, values)
    raw_before = values.copy()

    result = session.apply_savgol(SavgolSpec(9, 3))

    assert result.intensity_processed.shape == values.shape
    assert result.intensity_processed.dtype == np.float64
    np.testing.assert_array_equal(result.field_G, field)
    np.testing.assert_array_equal(result.intensity_raw, raw_before)
    np.testing.assert_array_equal(field, np.arange(len(field), dtype=float))
    assert len(result.intensity_processed) == len(values)


def test_smoothing_reduces_point_to_point_noise() -> None:
    field, values = spectrum(noise=0.05)
    output, _ = smooth_savgol(values, SavgolSpec(11, 2))

    assert np.std(np.diff(output)) < np.std(np.diff(values))


def test_known_peaks_keep_position_height_width_and_separation() -> None:
    field, values = spectrum()
    output, _ = smooth_savgol(values, SavgolSpec(window_length=9, polyorder=3))

    before_left = peak_index(values, 60, 100)
    before_right = peak_index(values, 100, 140)
    after_left = peak_index(output, 60, 100)
    after_right = peak_index(output, 100, 140)

    assert abs(after_left - before_left) <= 1
    assert abs(after_right - before_right) <= 1
    separation_before = field[before_right] - field[before_left]
    separation_after = field[after_right] - field[after_left]
    assert separation_after == pytest.approx(separation_before, abs=1.0)

    height_ratio = output[after_left] / values[before_left]
    assert 0.95 <= height_ratio <= 1.05
    width_ratio = fwhm(field, output, after_left) / fwhm(
        field, values, before_left
    )
    assert 0.90 <= width_ratio <= 1.10


# --------------------------------------------------------------------------
# Parameter validation
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "spec, n_points, code",
    [
        (SavgolSpec(2, 1), 101, "savgol_window_too_small"),
        (SavgolSpec(1, 0), 101, "savgol_window_too_small"),
        (SavgolSpec(4, 2), 101, "savgol_window_even"),
        (SavgolSpec(5, 5), 101, "savgol_polyorder"),
        (SavgolSpec(5, 6), 101, "savgol_polyorder"),
        (SavgolSpec(5, -1), 101, "savgol_polyorder"),
        (SavgolSpec(11, 2), 9, "savgol_window_too_large"),
        (SavgolSpec(5, 1, deriv=1), 101, "savgol_parameter"),
        (SavgolSpec(5, 1, mode="wrap"), 101, "savgol_parameter"),
        (SavgolSpec(3.0, 1), 101, "savgol_parameter"),  # type: ignore[arg-type]
        (SavgolSpec(5, 2.0), 101, "savgol_parameter"),  # type: ignore[arg-type]
        (SavgolSpec(True, 1), 101, "savgol_parameter"),  # type: ignore[arg-type]
    ],
)
def test_invalid_savgol_parameters_raise(spec, n_points, code) -> None:
    with pytest.raises(PreprocessingError) as excinfo:
        validate_savgol_spec(spec, n_points)
    assert excinfo.value.code == code


def test_non_finite_input_is_refused() -> None:
    values = np.zeros(51)
    values[10] = np.nan
    with pytest.raises(NonFiniteDataError):
        smooth_savgol(values, SavgolSpec(5, 2))

    values[10] = np.inf
    with pytest.raises(NonFiniteDataError):
        smooth_savgol(values, SavgolSpec(5, 2))


def test_scipy_missing_gives_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "scipy.signal", None)
    with pytest.raises(PreprocessingError) as excinfo:
        smooth_savgol(np.zeros(21), SavgolSpec(5, 2))
    assert excinfo.value.code == "savgol_unavailable"


def test_invalid_smoothing_input_source_is_refused() -> None:
    field, values = spectrum()
    session = session_for(field, values)
    with pytest.raises(PreprocessingError) as excinfo:
        session.preview_savgol(SavgolSpec(9, 3), input_source="somewhere")
    assert excinfo.value.code == "savgol_input_source"


# --------------------------------------------------------------------------
# Preview / apply / undo / reset and ordering
# --------------------------------------------------------------------------
def test_preview_does_not_commit_a_smoothing_step() -> None:
    field, values = spectrum(noise=0.02)
    session = session_for(field, values)

    preview = session.preview_savgol(SavgolSpec(9, 3))

    assert preview.is_preview is True
    assert preview.operations == (SAVGOL_OPERATION,)
    assert session.has_steps is False
    assert session.steps == ()

    applied = session.apply_pending()
    assert applied.is_preview is False
    assert applied.operations == (SAVGOL_OPERATION,)
    assert len(session.steps) == 1

    undone = session.undo()
    assert undone.operations == ()
    assert session.steps == ()

    session.apply_savgol(SavgolSpec(9, 3))
    reset = session.reset()
    assert reset.operations == ()
    np.testing.assert_array_equal(reset.intensity_processed, reset.intensity_raw)


def test_smoothing_current_result_appends_after_baseline() -> None:
    field, values = spectrum(baseline=3.0)
    session = session_for(field, values)
    baseline_result = session.apply(baseline_spec())

    preview = session.preview_savgol(
        SavgolSpec(9, 3), input_source=INPUT_CURRENT
    )
    assert preview.operations == (BASELINE_OPERATION, SAVGOL_OPERATION)
    assert preview.is_preview is True

    applied = session.apply_pending()
    assert applied.operations == (BASELINE_OPERATION, SAVGOL_OPERATION)
    assert session.steps[0].operation == BASELINE_OPERATION
    assert session.steps[1].operation == SAVGOL_OPERATION
    assert session.steps[1].input_source == INPUT_CURRENT
    assert session.steps[1].input_step_count == 1

    expected, _ = smooth_savgol(
        baseline_result.intensity_processed, SavgolSpec(9, 3)
    )
    np.testing.assert_allclose(
        applied.intensity_processed, expected, rtol=0, atol=1e-12
    )


def test_smoothing_raw_data_is_inserted_before_existing_steps() -> None:
    field, values = spectrum(baseline=3.0)
    session = session_for(field, values)
    session.apply(baseline_spec())
    spec = SavgolSpec(9, 3)

    preview = session.preview_savgol(spec, input_source=INPUT_RAW)

    assert preview.operations == (SAVGOL_OPERATION, BASELINE_OPERATION)
    assert preview.is_preview is True
    assert any(
        warning.code == "prep_warning_smoothing_reorders"
        for warning in preview.warnings
    )

    applied = session.apply_pending()

    assert applied.operations == (SAVGOL_OPERATION, BASELINE_OPERATION)
    assert session.steps[0].operation == SAVGOL_OPERATION
    assert session.steps[0].input_source == INPUT_RAW
    assert session.steps[0].input_step_count == 0
    assert session.steps[1].operation == BASELINE_OPERATION
    assert any(
        warning.code == "prep_warning_smoothing_reorders"
        for warning in applied.warnings
    )

    smoothed, _ = smooth_savgol(values, spec)
    baseline_fit = session.steps[1].fit
    assert baseline_fit is not None
    expected = smoothed - (baseline_fit.slope * field + baseline_fit.intercept)
    np.testing.assert_allclose(
        applied.intensity_processed, expected, rtol=0, atol=1e-12
    )

    record = build_preprocessing_record(applied)
    first, second = record["steps"]
    assert first["parameters"]["input_source"] == INPUT_RAW
    assert first["parameters"]["input_step_count"] == 0
    assert first["parameters"]["fit_input_source"] == INPUT_RAW
    assert second["parameters"]["input_source"] == INPUT_CURRENT
    assert second["parameters"]["input_step_count"] == 1
    # The baseline was fitted on the raw data before smoothing was prepended.
    assert second["parameters"]["fit_input_source"] == INPUT_RAW


def test_undo_after_mixed_steps_restores_baseline_result() -> None:
    field, values = spectrum(baseline=3.0)
    session = session_for(field, values)
    baseline_result = session.apply(baseline_spec())
    session.apply_savgol(SavgolSpec(9, 3))

    restored = session.undo()

    assert restored.operations == (BASELINE_OPERATION,)
    np.testing.assert_allclose(
        restored.intensity_processed,
        baseline_result.intensity_processed,
        rtol=0,
        atol=1e-12,
    )


def test_inputs_and_session_lengths_are_unchanged() -> None:
    field, values = spectrum(noise=0.01)
    field_before = field.copy()
    values_before = values.copy()
    session = session_for(field, values)

    session.preview_savgol(SavgolSpec(9, 3))
    session.apply_pending()
    session.undo()
    session.apply_savgol(SavgolSpec(11, 2))
    session.reset()

    np.testing.assert_array_equal(field, field_before)
    np.testing.assert_array_equal(values, values_before)
    assert session.current_result().intensity_raw.flags.writeable is False


def test_current_result_is_cached_and_not_recomputed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    field, values = spectrum(noise=0.01)
    session = session_for(field, values)
    result = session.apply_savgol(SavgolSpec(9, 3))

    def _fail(*args, **kwargs):
        raise AssertionError("cached result must not re-run smoothing")

    monkeypatch.setattr(
        "epr_workflow.preprocessing.smooth_savgol", _fail
    )
    assert session.current_result() is result


def test_processing_data_kind() -> None:
    field, values = spectrum(baseline=3.0)
    session = session_for(field, values)
    assert processing_data_kind(session.steps) == "none"

    session.apply(baseline_spec())
    assert processing_data_kind(session.steps) == "baseline_corrected"

    session.apply_savgol(SavgolSpec(9, 3))
    assert (
        processing_data_kind(session.steps)
        == "baseline_corrected_and_smoothed"
    )

    other = session_for(*spectrum())
    other.apply_savgol(SavgolSpec(9, 3))
    assert processing_data_kind(other.steps) == "smoothed"


# --------------------------------------------------------------------------
# Processing record
# --------------------------------------------------------------------------
def test_smoothing_record_contains_parameters_and_provenance() -> None:
    field, values = spectrum(noise=0.01)
    session = session_for(field, values)
    result = session.apply_savgol(SavgolSpec(9, 3))

    record = build_preprocessing_record(result)

    assert record["data_kind"] == "smoothed"
    assert record["applied"] is True
    assert record["step_order"] == ["savitzky_golay"]
    assert record["algorithm"] == {
        "name": "scipy.signal.savgol_filter",
        "version": "1.0",
    }
    assert record["algorithms"][0]["operation"] == "savitzky_golay"
    assert "smoothing" not in record["not_applied"]
    assert "baseline_correction" in record["not_applied"]
    assert any("Savitzky-Golay" in item for item in record["assumptions"])
    assert record["source_sha256"] == "abc123"

    step = record["steps"][0]
    assert step["operation"] == "savitzky_golay"
    assert step["parameters"]["window_length"] == 9
    assert step["parameters"]["polyorder"] == 3
    assert step["parameters"]["deriv"] == 0
    assert step["parameters"]["mode"] == "interp"
    assert step["parameters"]["input_source"] == INPUT_RAW
    assert step["parameters"]["input_step_count"] == 0
    assert step["parameters"]["input_points"] == len(values)
    assert step["diagnostics"]["n_points"] == len(values)
    assert step["diagnostics"]["rms_change"] >= 0.0
    assert "scipy" in step["software"]
    assert step["source_sha256"] == "abc123"
    assert step["applied_at_utc"].endswith("+00:00")
    json.dumps(record, allow_nan=False)


def test_mixed_record_order_and_input_source() -> None:
    field, values = spectrum(baseline=3.0, noise=0.01)
    session = session_for(field, values)
    session.apply(baseline_spec())
    result = session.apply_savgol(SavgolSpec(9, 3), input_source=INPUT_CURRENT)

    record = build_preprocessing_record(result)

    assert record["data_kind"] == "baseline_corrected_and_smoothed"
    assert record["step_order"] == ["linear_baseline", "savitzky_golay"]
    assert [step["operation"] for step in record["steps"]] == [
        "linear_baseline",
        "savitzky_golay",
    ]
    smoothing = record["steps"][1]
    assert smoothing["parameters"]["input_source"] == INPUT_CURRENT
    assert smoothing["parameters"]["input_step_count"] == 1
    assert "smoothing" not in record["not_applied"]
    assert "baseline_correction" not in record["not_applied"]
    json.dumps(record, allow_nan=False)
