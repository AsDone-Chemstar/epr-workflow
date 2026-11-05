"""M12 tests for explicit FTIR baseline correction."""

from __future__ import annotations

import numpy as np
import pytest

from spectralab.core.model import (
    Axis1D,
    Provenance,
    Signal1D,
    Spectrum1D,
    SpectrumMetadata,
)
from spectralab.core.processing import ProcessingSession
from spectralab.techniques.ftir import (
    BaselineRegion,
    FTIRBaselineError,
    FTIRBaselineOperation,
    create_baseline_operation,
    fit_baseline,
    normalize_regions,
)
from spectralab.techniques.ftir import baseline as baseline_module
from spectralab.techniques.ftir import create_normalization_operation


def _peak(x: np.ndarray, *, center: float = 10.0) -> np.ndarray:
    return 2.0 * np.exp(-0.5 * ((x - center) / 0.5) ** 2)


def _axis(x: np.ndarray, *, direction: str = "increasing") -> Axis1D:
    return Axis1D(
        values=np.asarray(x, dtype=np.float64),
        quantity="wavenumber",
        unit="cm^-1",
        name="Wavenumber",
        direction=direction,
        metadata_source="test",
    )


def _signal(y: np.ndarray) -> Signal1D:
    return Signal1D(
        values=np.asarray(y, dtype=np.float64),
        semantics="absorbance",
        unit="a.u.",
        name="Absorbance",
        metadata_source="test",
    )


def _spectrum(x: np.ndarray, y: np.ndarray, *, direction: str = "increasing") -> Spectrum1D:
    return Spectrum1D(
        dataset_id="baseline",
        axis=_axis(x, direction=direction),
        raw_signal=_signal(y),
        metadata=SpectrumMetadata(technique="ftir"),
        provenance=Provenance(importer_id="ftir.test", importer_version="1"),
    )


def _regions() -> tuple[BaselineRegion, ...]:
    return (BaselineRegion(0.0, 3.0), BaselineRegion(17.0, 20.0))


# ---------------------------------------------------------------------------
# Numerical recovery
# ---------------------------------------------------------------------------
def test_linear_baseline_recovers_synthetic_baseline() -> None:
    x = np.linspace(0.0, 20.0, 101)
    baseline = 2.0 + 3.0 * x
    y = baseline + _peak(x)
    fit = fit_baseline(x, y, _regions(), 1)

    np.testing.assert_allclose(fit.evaluate(x), baseline, rtol=0.0, atol=1e-10)
    np.testing.assert_allclose(y - fit.evaluate(x), _peak(x), rtol=0.0, atol=1e-10)
    assert fit.algorithm == "linear"
    assert fit.degree == 1
    assert fit.fitting_point_count > 1


@pytest.mark.parametrize(
    "degree",
    [2, 3, 4, 5],
)
def test_polynomial_baseline_recovers_synthetic_baseline(degree: int) -> None:
    x = np.linspace(0.0, 20.0, 101)
    coefficients = np.array(
        [1.0, 0.5, -0.02, 0.001, -0.00002, 1e-7],
        dtype=np.float64,
    )[: degree + 1]
    baseline = np.polynomial.polynomial.polyval(x, coefficients)
    y = baseline + _peak(x)
    fit = fit_baseline(x, y, _regions(), degree)

    np.testing.assert_allclose(fit.evaluate(x), baseline, rtol=0.0, atol=1e-8)
    np.testing.assert_allclose(y - fit.evaluate(x), _peak(x), rtol=0.0, atol=1e-8)
    assert fit.algorithm == "polynomial"
    assert fit.degree == degree


def test_decreasing_axis_recovers_baseline_without_reversal() -> None:
    x_inc = np.linspace(0.0, 20.0, 101)
    coefficients = np.array([1.0, 0.5, -0.02], dtype=np.float64)
    baseline = np.polynomial.polynomial.polyval(x_inc, coefficients)
    y_inc = baseline + _peak(x_inc)

    x = x_inc[::-1].copy()
    y = y_inc[::-1].copy()
    x_before = x.copy()
    y_before = y.copy()
    fit = fit_baseline(x, y, _regions(), 2)

    np.testing.assert_array_equal(x, x_before)
    np.testing.assert_array_equal(y, y_before)
    np.testing.assert_allclose(fit.evaluate(x), baseline[::-1], rtol=0.0, atol=1e-8)
    np.testing.assert_allclose(
        y - fit.evaluate(x),
        _peak(x),
        rtol=0.0,
        atol=1e-8,
    )


def test_single_region_pair_shorthand_is_supported() -> None:
    x = np.linspace(0.0, 20.0, 101)
    baseline = 2.0 + 3.0 * x
    y = baseline + _peak(x)
    fit = fit_baseline(x, y, (0.0, 3.0), 1)
    assert len(fit.regions) == 1
    np.testing.assert_allclose(fit.evaluate(x), baseline, rtol=0.0, atol=1e-10)


def test_multiple_regions_are_combined() -> None:
    x = np.linspace(0.0, 20.0, 101)
    baseline = 2.0 + 3.0 * x
    y = baseline + _peak(x)
    fit = fit_baseline(
        x,
        y,
        [(0.0, 2.0), (4.0, 6.0), (17.0, 20.0)],
        1,
    )
    assert len(fit.regions) == 3
    assert fit.fitting_point_count == sum(
        1 for value in x if 0 <= value <= 2 or 4 <= value <= 6 or 17 <= value <= 20
    )


# ---------------------------------------------------------------------------
# Invalid input and unstable fits
# ---------------------------------------------------------------------------
def test_empty_or_out_of_range_region_is_rejected() -> None:
    x = np.linspace(1000.0, 1010.0, 11)
    y = 1.0 + 2.0 * x
    with pytest.raises(FTIRBaselineError) as exc:
        fit_baseline(x, y, [(0.0, 5.0), (1000.0, 1005.0)], 1)
    assert exc.value.code == "ftir_baseline_empty_region"
    assert exc.value.context["region_index"] == 0
    assert exc.value.context["region"] == {"start": 0.0, "end": 5.0}
    assert exc.value.context["point_count"] == 0


def test_adjacent_region_endpoint_is_counted_once_with_contributions() -> None:
    x = np.arange(0.0, 7.0)
    y = 2.0 + 3.0 * x
    fit = fit_baseline(x, y, [(0.0, 3.0), (3.0, 6.0)], 1)
    assert fit.fitting_point_count == 7
    assert fit.region_point_counts == (4, 4)
    assert fit.region_unique_point_counts == (4, 3)
    assert sum(fit.region_unique_point_counts) == fit.fitting_point_count


def test_insufficient_fitting_points_are_rejected() -> None:
    x = np.arange(5.0)
    y = np.arange(5.0)
    with pytest.raises(FTIRBaselineError) as exc:
        fit_baseline(x, y, [(0.0, 4.0)], 5)
    assert exc.value.code == "ftir_baseline_insufficient_points"


def test_empty_and_mismatched_arrays_are_rejected() -> None:
    with pytest.raises(FTIRBaselineError) as empty:
        fit_baseline([], [], [(0.0, 1.0)], 1)
    assert empty.value.code == "ftir_baseline_input"

    with pytest.raises(FTIRBaselineError) as mismatch:
        fit_baseline([0.0, 1.0, 2.0], [1.0, 2.0], [(0.0, 2.0)], 1)
    assert mismatch.value.code == "ftir_baseline_input"


def test_nonfinite_arrays_are_rejected() -> None:
    x = np.linspace(0.0, 2.0, 4)
    y = np.array([1.0, np.nan, 2.0, 3.0])
    with pytest.raises(FTIRBaselineError) as exc:
        fit_baseline(x, y, [(0.0, 2.0)], 1)
    assert exc.value.code == "ftir_baseline_nonfinite_input"


def test_rank_deficient_fit_is_rejected() -> None:
    x = np.ones(7)
    y = np.linspace(0.0, 1.0, 7)
    with pytest.raises(FTIRBaselineError) as exc:
        fit_baseline(x, y, [(0.0, 2.0)], 5)
    assert exc.value.code == "ftir_baseline_rank_deficient"


def test_ill_conditioned_fit_is_rejected() -> None:
    x = np.array([0.0, 0.0005, 0.0010, 0.0015, 0.0020, 0.0025, 1.0])
    y = 1.0 + 2.0 * x
    with pytest.raises(FTIRBaselineError) as exc:
        fit_baseline(x, y, [(0.0, 1.0)], 5)
    assert exc.value.code == "ftir_baseline_ill_conditioned"


def test_invalid_and_overlapping_regions_are_rejected() -> None:
    with pytest.raises(FTIRBaselineError) as empty:
        normalize_regions([])
    assert empty.value.code == "ftir_baseline_regions"

    with pytest.raises(FTIRBaselineError) as equal:
        BaselineRegion(1.0, 1.0)
    assert equal.value.code == "ftir_baseline_region_invalid"

    with pytest.raises(FTIRBaselineError) as nonfinite:
        BaselineRegion(0.0, float("inf"))
    assert nonfinite.value.code == "ftir_baseline_region_invalid"

    with pytest.raises(FTIRBaselineError) as overlap:
        normalize_regions([(0.0, 3.0), (2.0, 4.0)])
    assert overlap.value.code == "ftir_baseline_region_overlap"
    assert overlap.value.context["first_index"] == 0
    assert overlap.value.context["second_index"] == 1
    assert "not combined" in overlap.value.context["overlap_policy"]


def test_nonfinite_coefficients_are_rejected(monkeypatch) -> None:
    def fake_lstsq(vandermonde, values, rcond=None):
        return (
            np.array([np.inf, 0.0]),
            None,
            2,
            np.array([1.0, 0.5]),
        )

    monkeypatch.setattr(baseline_module.np.linalg, "lstsq", fake_lstsq)
    x = np.linspace(0.0, 2.0, 5)
    with pytest.raises(FTIRBaselineError) as exc:
        fit_baseline(x, x, [(0.0, 2.0)], 1)
    assert exc.value.code == "ftir_baseline_nonfinite_coefficients"


def test_nonfinite_baseline_and_output_are_rejected(monkeypatch) -> None:
    coefficients = [1e308, 1e308]

    def fake_lstsq(vandermonde, values, rcond=None):
        return (
            np.asarray(coefficients, dtype=np.float64),
            None,
            2,
            np.array([1.0, 0.5]),
        )

    monkeypatch.setattr(baseline_module.np.linalg, "lstsq", fake_lstsq)
    x = np.linspace(0.0, 1.0, 5)
    with pytest.raises(FTIRBaselineError) as baseline_error:
        fit_baseline(x, np.ones_like(x), [(0.0, 1.0)], 1)
    assert baseline_error.value.code == "ftir_baseline_nonfinite_baseline"

    coefficients[:] = [-1e308, 0.0]
    with pytest.raises(FTIRBaselineError) as output_error:
        fit_baseline(x, np.full_like(x, 1e308), [(0.0, 1.0)], 1)
    assert output_error.value.code == "ftir_baseline_nonfinite_output"


def test_degree_validation() -> None:
    for degree in (0, 1, 5, 6, True, 2.5):
        if degree in (1, 5) and not isinstance(degree, bool):
            continue
        with pytest.raises(FTIRBaselineError) as exc:
            FTIRBaselineOperation([(0.0, 1.0)], degree)
        assert exc.value.code == "ftir_baseline_degree"


# ---------------------------------------------------------------------------
# Operation and session integration
# ---------------------------------------------------------------------------
def test_operation_preserves_axis_semantics_unit_and_source() -> None:
    x = np.linspace(0.0, 20.0, 101)
    y = 2.0 + 3.0 * x + _peak(x)
    spectrum = _spectrum(x, y)
    operation = create_baseline_operation(_regions(), 1)
    output = operation.apply(spectrum.axis, spectrum.raw_signal)

    np.testing.assert_array_equal(output.axis.values, x)
    assert output.axis is spectrum.axis
    np.testing.assert_array_equal(spectrum.raw_signal.values, y)
    assert output.signal.semantics == "absorbance"
    assert output.signal.unit == "a.u."
    assert output.signal.name == "Absorbance"
    assert output.diagnostics["algorithm"] == "linear"
    assert output.diagnostics["degree"] == 1
    assert output.diagnostics["fitting_point_count"] > 1
    assert len(output.diagnostics["coefficients"]) == 2
    assert output.diagnostics["numerical_method"]


def test_apply_records_regions_degree_coefficients_and_input_state() -> None:
    x = np.linspace(0.0, 20.0, 101)
    y = 2.0 + 3.0 * x + _peak(x)
    spectrum = _spectrum(x, y)
    session = ProcessingSession(spectrum)
    operation = create_baseline_operation(_regions(), 1)
    result = session.apply(operation)

    record = session.history[0]
    assert record.order == 1
    assert record.operation_id == "ftir.baseline.linear"
    assert record.technique == "ftir"
    assert record.version == "1.0.0"
    assert record.input_state_id == "original"
    assert record.parameters["algorithm"] == "linear"
    assert record.parameters["degree"] == 1
    assert record.parameters["region_count"] == 2
    assert record.parameters["regions"] == [
        {"start": 0.0, "end": 3.0},
        {"start": 17.0, "end": 20.0},
    ]
    assert record.diagnostics["fitting_point_count"] > 1
    assert len(record.diagnostics["coefficients"]) == 2
    assert record.diagnostics["condition_number"] > 0
    assert record.diagnostics["region_point_counts"] == [
        sum(1 for value in x if 0.0 <= value <= 3.0),
        sum(1 for value in x if 17.0 <= value <= 20.0),
    ]
    assert record.diagnostics["region_unique_point_counts"] == [
        sum(1 for value in x if 0.0 <= value <= 3.0),
        sum(1 for value in x if 17.0 <= value <= 20.0),
    ]
    assert record.input_dataset_id == "baseline"
    assert result.source is spectrum
    np.testing.assert_array_equal(result.axis.values, x)


def test_preview_does_not_modify_history_redo_or_source() -> None:
    x = np.linspace(0.0, 20.0, 101)
    y = 2.0 + 3.0 * x + _peak(x)
    spectrum = _spectrum(x, y)
    session = ProcessingSession(spectrum)
    session.apply(create_baseline_operation(_regions(), 1))
    session.undo()
    x_before = spectrum.x_values.copy()
    y_before = spectrum.y_values.copy()
    assert session.can_redo

    preview = session.preview(create_baseline_operation(_regions(), 2))
    assert preview.signal.values.dtype == np.float64
    assert session.history == ()
    assert session.can_redo is True
    assert session.current.signal is spectrum.raw_signal
    np.testing.assert_array_equal(spectrum.x_values, x_before)
    np.testing.assert_array_equal(spectrum.y_values, y_before)


def test_failed_operation_leaves_session_unchanged() -> None:
    x = np.arange(6.0)
    y = np.arange(6.0)
    spectrum = _spectrum(x, y)
    session = ProcessingSession(spectrum)
    session.apply(create_baseline_operation([(0.0, 5.0)], 1))
    history_before = session.history
    current_before = session.current

    with pytest.raises(FTIRBaselineError):
        session.preview(create_baseline_operation([(0.0, 4.0)], 5))

    assert session.history == history_before
    assert session.current.signal is current_before.signal
    assert session.current.axis is current_before.axis


def test_normalization_then_baseline_and_undo_restores_normalized_state() -> None:
    x = np.linspace(0.0, 20.0, 101)
    y = 2.0 + 3.0 * x + _peak(x)
    spectrum = _spectrum(x, y)
    session = ProcessingSession(spectrum)

    normalized = session.apply(create_normalization_operation("min_max"))
    normalized_signal = normalized.signal.values.copy()
    corrected = session.apply(create_baseline_operation(_regions(), 1))

    assert [record.operation_id for record in session.history] == [
        "ftir.normalize.min_max",
        "ftir.baseline.linear",
    ]
    assert [record.order for record in session.history] == [1, 2]
    assert not np.array_equal(corrected.signal.values, normalized_signal)
    assert session.current.signal is corrected.signal

    undone = session.undo()
    assert len(session.history) == 1
    assert undone.history[0].operation_id == "ftir.normalize.min_max"
    np.testing.assert_array_equal(undone.signal.values, normalized_signal)

    redone = session.redo()
    assert len(session.history) == 2
    assert [record.input_dataset_id for record in session.history] == [
        "baseline",
        "baseline",
    ]
    np.testing.assert_array_equal(redone.signal.values, corrected.signal.values)

    reset = session.reset()
    assert session.history == ()
    assert reset.signal is spectrum.raw_signal
