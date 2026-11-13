"""M14 tests for explicit FTIR difference spectra."""

from __future__ import annotations

import numpy as np
import pytest

from spectralab.core.errors import AxisValidationError, SignalValidationError
from spectralab.core.model import Axis1D, Signal1D
from spectralab.techniques.ftir import (
    ALGORITHM_EXACT,
    ALGORITHM_INTERPOLATED,
    DIFFERENCE_ALGORITHM_VERSION,
    EXACT_COMPARISON_POLICY,
    FTIRDifferenceError,
    DifferenceParameters,
    compute_difference,
)


def _axis(
    x,
    *,
    direction=None,
    quantity="wavenumber",
    unit="cm^-1",
) -> Axis1D:
    return Axis1D(
        values=np.asarray(x, dtype=np.float64),
        quantity=quantity,
        unit=unit,
        name="Wavenumber",
        direction=direction,
        metadata_source="test",
    )


def _signal(
    y,
    *,
    semantics="absorbance",
    unit="a.u.",
) -> Signal1D:
    return Signal1D(
        values=np.asarray(y, dtype=np.float64),
        semantics=semantics,
        unit=unit,
        name="Absorbance",
        metadata_source="test",
    )


def _difference(
    a_x,
    a_y,
    b_x,
    b_y,
    *,
    axis_match="exact",
    source_a="raw",
    source_b="raw",
    dataset_a_id="A",
    dataset_b_id="B",
    a_kwargs=None,
    b_kwargs=None,
    history_a=(),
    history_b=(),
):
    return compute_difference(
        _axis(a_x, **(a_kwargs or {})),
        _signal(a_y),
        _axis(b_x, **(b_kwargs or {})),
        _signal(b_y),
        DifferenceParameters(
            axis_match=axis_match,
            source_a=source_a,
            source_b=source_b,
        ),
        dataset_a_id=dataset_a_id,
        dataset_b_id=dataset_b_id,
        source_operation_history_a=history_a,
        source_operation_history_b=history_b,
    )


# ---------------------------------------------------------------------------
# Direct subtraction
# ---------------------------------------------------------------------------
def test_exact_increasing_axis_subtracts_elementwise() -> None:
    result = _difference(
        [0.0, 1.0, 2.0, 3.0],
        [10.0, 20.0, 30.0, 40.0],
        [0.0, 1.0, 2.0, 3.0],
        [1.0, 2.0, 3.0, 4.0],
    )
    np.testing.assert_array_equal(result.axis.values, [0.0, 1.0, 2.0, 3.0])
    np.testing.assert_array_equal(result.signal.values, [9.0, 18.0, 27.0, 36.0])
    assert result.axis_match == "exact"
    assert result.algorithm == ALGORITHM_EXACT
    assert result.algorithm_version == DIFFERENCE_ALGORITHM_VERSION
    assert result.operation == "A - B"
    assert result.interpolation is None
    assert result.dataset_a_id == "A"
    assert result.dataset_b_id == "B"


def test_exact_decreasing_axis_preserves_order() -> None:
    result = _difference(
        [3.0, 2.0, 1.0, 0.0],
        [40.0, 30.0, 20.0, 10.0],
        [3.0, 2.0, 1.0, 0.0],
        [4.0, 3.0, 2.0, 1.0],
    )
    np.testing.assert_array_equal(result.axis.values, [3.0, 2.0, 1.0, 0.0])
    np.testing.assert_array_equal(result.signal.values, [36.0, 27.0, 18.0, 9.0])
    assert result.axis.direction == "decreasing"


def test_exact_axis_uses_no_tolerance() -> None:
    with pytest.raises(FTIRDifferenceError) as excinfo:
        _difference(
            [0.0, 1.0, 2.0],
            [1.0, 2.0, 3.0],
            [0.0, 1.0, 2.0 + 1.0e-12],
            [1.0, 2.0, 3.0],
        )
    assert excinfo.value.code == "ftir_difference_axis_values"
    assert "array_equal" in str(excinfo.value.context["policy"])


def test_exact_rejects_different_point_counts() -> None:
    with pytest.raises(FTIRDifferenceError) as excinfo:
        _difference(
            [0.0, 1.0, 2.0],
            [1.0, 2.0, 3.0],
            [0.0, 1.0],
            [1.0, 2.0],
        )
    assert excinfo.value.code == "ftir_difference_point_count"


def test_exact_rejects_different_point_order() -> None:
    with pytest.raises(FTIRDifferenceError) as excinfo:
        _difference(
            [0.0, 1.0, 2.0],
            [1.0, 2.0, 3.0],
            [2.0, 1.0, 0.0],
            [1.0, 2.0, 3.0],
        )
    assert excinfo.value.code == "ftir_difference_axis_values"


def test_exact_rejects_slightly_different_x_values() -> None:
    with pytest.raises(FTIRDifferenceError) as excinfo:
        _difference(
            [0.0, 1.0, 2.0],
            [1.0, 2.0, 3.0],
            [0.0, 1.0, 2.0000001],
            [1.0, 2.0, 3.0],
        )
    assert excinfo.value.code == "ftir_difference_axis_values"


# ---------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------
def test_interpolation_uses_a_as_target_and_interpolates_b() -> None:
    result = _difference(
        [0.0, 2.0, 4.0, 6.0],
        [10.0, 20.0, 30.0, 40.0],
        [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        axis_match="interpolate",
    )
    np.testing.assert_array_equal(result.axis.values, [0.0, 2.0, 4.0, 6.0])
    np.testing.assert_allclose(
        result.interpolation.aligned_b_signal.values,
        [1.0, 3.0, 5.0, 7.0],
    )
    np.testing.assert_allclose(result.signal.values, [9.0, 17.0, 25.0, 33.0])
    assert result.algorithm == ALGORITHM_INTERPOLATED
    assert result.interpolation.method == "linear"
    assert result.interpolation.target_dataset_id == "A"
    assert result.interpolation.interpolated_dataset_id == "B"
    assert result.interpolation.extrapolation == "none"
    assert result.interpolation.target_point_count == 4


def test_interpolation_preserves_decreasing_target_order() -> None:
    result = _difference(
        [20.0, 15.0, 10.0, 5.0, 0.0],
        [100.0, 90.0, 80.0, 70.0, 60.0],
        [0.0, 5.0, 10.0, 15.0, 20.0],
        [1.0, 2.0, 3.0, 4.0, 5.0],
        axis_match="interpolate",
    )
    np.testing.assert_array_equal(
        result.axis.values,
        [20.0, 15.0, 10.0, 5.0, 0.0],
    )
    np.testing.assert_allclose(
        result.interpolation.aligned_b_signal.values,
        [5.0, 4.0, 3.0, 2.0, 1.0],
    )
    assert result.axis.direction == "decreasing"


def test_interpolation_supports_decreasing_b_without_reversing_output() -> None:
    result = _difference(
        [0.0, 2.0, 4.0, 6.0],
        [10.0, 20.0, 30.0, 40.0],
        [6.0, 4.0, 2.0, 0.0],
        [7.0, 5.0, 3.0, 1.0],
        axis_match="interpolate",
    )
    np.testing.assert_array_equal(result.axis.values, [0.0, 2.0, 4.0, 6.0])
    np.testing.assert_allclose(
        result.interpolation.aligned_b_signal.values,
        [1.0, 3.0, 5.0, 7.0],
    )


def test_interpolation_uses_only_common_overlap_and_keeps_endpoints() -> None:
    result = _difference(
        [0.0, 5.0, 10.0, 15.0, 20.0],
        [10.0, 20.0, 30.0, 40.0, 50.0],
        [5.0, 10.0, 15.0],
        [1.0, 2.0, 3.0],
        axis_match="interpolate",
    )
    np.testing.assert_array_equal(result.axis.values, [5.0, 10.0, 15.0])
    np.testing.assert_allclose(result.signal.values, [19.0, 28.0, 37.0])
    assert result.interpolation.overlap_low == 5.0
    assert result.interpolation.overlap_high == 15.0


def test_interpolation_rejects_no_overlap() -> None:
    with pytest.raises(FTIRDifferenceError) as excinfo:
        _difference(
            [0.0, 1.0, 2.0],
            [1.0, 2.0, 3.0],
            [10.0, 11.0, 12.0],
            [1.0, 2.0, 3.0],
            axis_match="interpolate",
        )
    assert excinfo.value.code == "ftir_difference_no_overlap"


def test_interpolation_rejects_single_a_target_point() -> None:
    with pytest.raises(FTIRDifferenceError) as excinfo:
        _difference(
            [0.0, 10.0, 20.0],
            [1.0, 2.0, 3.0],
            [5.0, 10.0, 15.0],
            [1.0, 2.0, 3.0],
            axis_match="interpolate",
        )
    assert excinfo.value.code == "ftir_difference_insufficient_points"


def test_interpolation_rejects_duplicate_b_axis() -> None:
    with pytest.raises(FTIRDifferenceError) as excinfo:
        _difference(
            [0.0, 1.0, 2.0],
            [1.0, 2.0, 3.0],
            [0.0, 0.0, 2.0],
            [1.0, 2.0, 3.0],
            axis_match="interpolate",
            b_kwargs={"direction": "unknown"},
        )
    assert excinfo.value.code == "ftir_difference_axis_not_monotonic"


def test_interpolation_rejects_non_monotonic_b_axis() -> None:
    with pytest.raises(FTIRDifferenceError) as excinfo:
        _difference(
            [0.0, 1.0, 2.0],
            [1.0, 2.0, 3.0],
            [0.0, 2.0, 1.0],
            [1.0, 2.0, 3.0],
            axis_match="interpolate",
            b_kwargs={"direction": "unknown"},
        )
    assert excinfo.value.code == "ftir_difference_axis_not_monotonic"


# ---------------------------------------------------------------------------
# Compatibility
# ---------------------------------------------------------------------------
def test_compatible_metadata_is_required() -> None:
    with pytest.raises(FTIRDifferenceError) as quantity:
        _difference(
            [0.0, 1.0],
            [1.0, 2.0],
            [0.0, 1.0],
            [1.0, 2.0],
            b_kwargs={"quantity": "wavelength"},
        )
    assert quantity.value.code == "ftir_difference_axis_quantity"

    with pytest.raises(FTIRDifferenceError) as unknown_quantity:
        _difference(
            [0.0, 1.0],
            [1.0, 2.0],
            [0.0, 1.0],
            [1.0, 2.0],
            a_kwargs={"quantity": "unknown"},
            b_kwargs={"quantity": "unknown"},
        )
    assert unknown_quantity.value.code == "ftir_difference_axis_quantity_unknown"

    with pytest.raises(FTIRDifferenceError) as unit:
        _difference(
            [0.0, 1.0],
            [1.0, 2.0],
            [0.0, 1.0],
            [1.0, 2.0],
            b_kwargs={"unit": "nm"},
        )
    assert unit.value.code == "ftir_difference_axis_unit"


def test_signal_semantics_and_units_are_checked() -> None:
    with pytest.raises(FTIRDifferenceError) as semantics:
        compute_difference(
            _axis([0.0, 1.0]),
            _signal([1.0, 2.0], semantics="absorbance"),
            _axis([0.0, 1.0]),
            _signal([1.0, 2.0], semantics="transmittance"),
            DifferenceParameters(),
            dataset_a_id="A",
            dataset_b_id="B",
        )
    assert semantics.value.code == "ftir_difference_signal_semantics"

    with pytest.raises(FTIRDifferenceError) as unknown_semantics:
        compute_difference(
            _axis([0.0, 1.0]),
            _signal([1.0, 2.0], semantics="unknown"),
            _axis([0.0, 1.0]),
            _signal([1.0, 2.0], semantics="unknown"),
            DifferenceParameters(),
            dataset_a_id="A",
            dataset_b_id="B",
        )
    assert unknown_semantics.value.code == "ftir_difference_signal_semantics_unknown"

    with pytest.raises(FTIRDifferenceError) as unit:
        compute_difference(
            _axis([0.0, 1.0]),
            _signal([1.0, 2.0], unit="a.u."),
            _axis([0.0, 1.0]),
            _signal([1.0, 2.0], unit="%"),
            DifferenceParameters(),
            dataset_a_id="A",
            dataset_b_id="B",
        )
    assert unit.value.code == "ftir_difference_signal_unit"


def test_missing_units_are_preserved_when_both_are_unknown() -> None:
    result = compute_difference(
        _axis([0.0, 1.0], unit=None),
        _signal([1.0, 2.0], unit=None),
        _axis([0.0, 1.0], unit=None),
        _signal([1.0, 2.0], unit=None),
        DifferenceParameters(),
        dataset_a_id="A",
        dataset_b_id="B",
    )
    assert result.axis.unit is None
    assert result.signal.unit is None
    np.testing.assert_array_equal(result.signal.values, [0.0, 0.0])


def test_same_dataset_identity_is_rejected() -> None:
    with pytest.raises(FTIRDifferenceError) as excinfo:
        _difference(
            [0.0, 1.0],
            [1.0, 2.0],
            [0.0, 1.0],
            [1.0, 2.0],
            dataset_b_id="A",
        )
    assert excinfo.value.code == "ftir_difference_same_dataset"


# ---------------------------------------------------------------------------
# Provenance and independence
# ---------------------------------------------------------------------------
def test_result_provenance_and_no_arrays_in_metadata() -> None:
    result = _difference(
        [0.0, 2.0, 4.0],
        [10.0, 20.0, 30.0],
        [0.0, 1.0, 2.0, 3.0, 4.0],
        [1.0, 2.0, 3.0, 4.0, 5.0],
        axis_match="interpolate",
        source_a="processed",
        source_b="raw",
        history_a=("ftir.normalize.min_max",),
        history_b=(),
    )
    payload = result.as_dict()
    assert payload["operation"] == "A - B"
    assert payload["axis_match"] == "interpolate"
    assert payload["source_a"] == "processed"
    assert payload["source_b"] == "raw"
    assert payload["source_operation_history_a"] == ["ftir.normalize.min_max"]
    assert payload["interpolation"]["method"] == "linear"
    assert payload["interpolation"]["target_dataset_id"] == "A"
    assert payload["interpolation"]["interpolated_dataset_id"] == "B"
    assert payload["interpolation"]["extrapolation"] == "none"
    assert payload["axis"]["point_count"] == 3
    assert payload["signal"]["semantics"] == "absorbance"
    assert "values" not in payload["interpolation"]


def test_result_does_not_hold_mutable_source_arrays() -> None:
    a_x = np.array([0.0, 1.0, 2.0])
    a_y = np.array([10.0, 20.0, 30.0])
    b_x = np.array([0.0, 2.0])
    b_y = np.array([1.0, 3.0])
    a_axis = _axis(a_x)
    a_signal = _signal(a_y)
    b_axis = _axis(b_x)
    b_signal = _signal(b_y)
    result = compute_difference(
        a_axis,
        a_signal,
        b_axis,
        b_signal,
        DifferenceParameters(axis_match="interpolate"),
        dataset_a_id="A",
        dataset_b_id="B",
    )
    np.testing.assert_array_equal(a_axis.values, a_x)
    np.testing.assert_array_equal(a_signal.values, a_y)
    np.testing.assert_array_equal(b_axis.values, b_x)
    np.testing.assert_array_equal(b_signal.values, b_y)
    assert not result.axis.values.flags.writeable
    assert not result.signal.values.flags.writeable
    assert not result.aligned_a_signal.values.flags.writeable
    assert not result.aligned_b_signal.values.flags.writeable
    assert not result.interpolation.aligned_b_signal.values.flags.writeable


def test_nonfinite_values_are_rejected_by_the_model_before_difference() -> None:
    with pytest.raises(SignalValidationError):
        _signal([1.0, float("nan"), 3.0])
    with pytest.raises(AxisValidationError):
        _axis([0.0, float("inf"), 2.0])


def test_exact_policy_is_recorded() -> None:
    result = _difference(
        [0.0, 1.0],
        [1.0, 2.0],
        [0.0, 1.0],
        [1.0, 2.0],
    )
    assert EXACT_COMPARISON_POLICY in result.assumptions
    assert result.algorithm == ALGORITHM_EXACT
