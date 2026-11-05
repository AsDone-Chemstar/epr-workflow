"""M11 Part B tests for explicit FTIR normalization."""

from __future__ import annotations

import math

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
    FTIRNormalizationError,
    FTIRNormalizationOperation,
    NORMALIZATION_METHODS,
    create_normalization_operation,
    normalize_values,
)


def _axis(values: list[float] | None = None) -> Axis1D:
    values = values or [1000.0, 1001.0, 1002.0, 1003.0]
    return Axis1D(
        values=np.asarray(values, dtype=np.float64),
        quantity="wavenumber",
        unit="cm^-1",
        name="Wavenumber",
        direction="increasing",
        metadata_source="test",
    )


def _signal(values: list[float], *, unit: str | None = None) -> Signal1D:
    return Signal1D(
        values=np.asarray(values, dtype=np.float64),
        semantics="absorbance",
        unit=unit,
        name="Absorbance",
        metadata_source="test",
    )


def _spectrum(values: list[float]) -> Spectrum1D:
    return Spectrum1D(
        dataset_id="normalization",
        axis=_axis(),
        raw_signal=_signal(values, unit="a.u."),
        metadata=SpectrumMetadata(technique="ftir"),
        provenance=Provenance(importer_id="ftir.test", importer_version="1"),
    )


# ---------------------------------------------------------------------------
# Mathematical definitions
# ---------------------------------------------------------------------------
def test_min_max_expected_values() -> None:
    values = [-2.0, -1.0, 0.0, 3.0]
    expected = [0.0, 0.2, 0.4, 1.0]
    result = normalize_values(values, "min_max")
    np.testing.assert_allclose(result, expected, rtol=1e-15, atol=0.0)
    assert result.dtype == np.float64
    assert result.min() == pytest.approx(0.0)
    assert result.max() == pytest.approx(1.0)


def test_max_abs_expected_values() -> None:
    values = [-2.0, -1.0, 0.0, 3.0]
    expected = [-2.0 / 3.0, -1.0 / 3.0, 0.0, 1.0]
    result = normalize_values(values, "max_abs")
    np.testing.assert_allclose(result, expected, rtol=1e-15, atol=0.0)
    assert np.max(np.abs(result)) == pytest.approx(1.0)


def test_l2_expected_values() -> None:
    values = [-2.0, -1.0, 0.0, 3.0]
    denominator = math.sqrt(14.0)
    expected = [value / denominator for value in values]
    result = normalize_values(values, "l2")
    np.testing.assert_allclose(result, expected, rtol=1e-15, atol=0.0)
    assert math.sqrt(float(np.sum(result * result))) == pytest.approx(1.0)


def test_constant_signal_behavior() -> None:
    values = [2.0, 2.0, 2.0]
    with pytest.raises(FTIRNormalizationError) as exc:
        normalize_values(values, "min_max")
    assert exc.value.code == "ftir_normalization_zero_denominator"

    np.testing.assert_allclose(
        normalize_values(values, "max_abs"),
        [1.0, 1.0, 1.0],
        rtol=1e-15,
    )
    np.testing.assert_allclose(
        normalize_values(values, "l2"),
        [1.0 / math.sqrt(3.0)] * 3,
        rtol=1e-15,
    )


@pytest.mark.parametrize("method", NORMALIZATION_METHODS)
def test_all_zero_signal_is_rejected(method: str) -> None:
    with pytest.raises(FTIRNormalizationError) as exc:
        normalize_values([0.0, 0.0, 0.0], method)
    assert exc.value.code == "ftir_normalization_zero_denominator"


def test_near_zero_denominators_are_explicit() -> None:
    values = [1e-300, 2e-300]
    np.testing.assert_allclose(
        normalize_values(values, "min_max"),
        [0.0, 1.0],
        rtol=0.0,
        atol=0.0,
    )
    np.testing.assert_allclose(
        normalize_values(values, "max_abs"),
        [0.5, 1.0],
        rtol=1e-15,
    )
    with pytest.raises(FTIRNormalizationError) as exc:
        normalize_values(values, "l2")
    assert exc.value.code == "ftir_normalization_zero_denominator"


def test_empty_and_complex_inputs_are_rejected() -> None:
    with pytest.raises(FTIRNormalizationError) as empty:
        normalize_values([], "min_max")
    assert empty.value.code == "ftir_normalization_input"
    with pytest.raises(FTIRNormalizationError) as complex_input:
        normalize_values([1.0 + 1.0j], "min_max")
    assert complex_input.value.code == "ftir_normalization_input"


def test_nonfinite_input_is_rejected() -> None:
    with pytest.raises(FTIRNormalizationError) as exc:
        normalize_values([1.0, float("nan")], "min_max")
    assert exc.value.code == "ftir_normalization_nonfinite_input"


def test_nonfinite_denominator_is_rejected() -> None:
    with pytest.raises(FTIRNormalizationError) as exc:
        normalize_values([1e308, -1e308], "min_max")
    assert exc.value.code == "ftir_normalization_nonfinite_denominator"


@pytest.mark.parametrize(
    "method",
    ["min_max", "min-max", "MIN_MAX", "max_abs", "max-abs", "l2", "l2_norm"],
)
def test_method_aliases_are_canonical(method: str) -> None:
    operation = FTIRNormalizationOperation(method)
    assert operation.method in NORMALIZATION_METHODS
    assert operation.operation_id == f"ftir.normalize.{operation.method}"


def test_unknown_method_is_rejected() -> None:
    with pytest.raises(FTIRNormalizationError) as exc:
        create_normalization_operation("normalize-to-one")
    assert exc.value.code == "ftir_normalization_method"


# ---------------------------------------------------------------------------
# Operation integrity and session provenance
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("method", NORMALIZATION_METHODS)
def test_operation_preserves_axis_semantics_unit_and_source(method: str) -> None:
    axis = _axis()
    signal = _signal([-2.0, -1.0, 0.0, 3.0], unit="a.u.")
    x_before = axis.values.copy()
    y_before = signal.values.copy()
    output = create_normalization_operation(method).apply(axis, signal)

    assert output.axis is axis
    np.testing.assert_array_equal(output.axis.values, x_before)
    np.testing.assert_array_equal(signal.values, y_before)
    assert output.signal is not signal
    assert output.signal.semantics == "absorbance"
    assert output.signal.unit == "a.u."
    assert output.signal.name == "Absorbance"
    assert output.signal.metadata_source == "test"
    assert output.axis.direction == "increasing"


def test_session_apply_records_method_and_order() -> None:
    source = _spectrum([-2.0, -1.0, 0.0, 3.0])
    session = ProcessingSession(source)
    first = session.apply(create_normalization_operation("min_max"))
    second = session.apply(create_normalization_operation("l2"))

    assert [record.order for record in session.history] == [1, 2]
    assert [record.operation_id for record in session.history] == [
        "ftir.normalize.min_max",
        "ftir.normalize.l2",
    ]
    assert session.history[0].parameters["method"] == "min_max"
    assert session.history[1].parameters["method"] == "l2"
    assert first.history[0].output_state_id == "step-1"
    assert second.history[1].output_state_id == "step-2"
    assert session.history[0].technique == "ftir"
    assert session.history[0].version == "1.0.0"
    assert session.history[0].input_dataset_id == "normalization"


def test_preview_does_not_change_history_redo_or_source() -> None:
    source = _spectrum([-2.0, -1.0, 0.0, 3.0])
    session = ProcessingSession(source)
    session.apply(create_normalization_operation("min_max"))
    session.undo()
    assert session.can_redo
    x_before = source.x_values.copy()
    y_before = source.y_values.copy()

    preview = session.preview(create_normalization_operation("l2"))

    assert preview.signal.values.dtype == np.float64
    assert session.history == ()
    assert session.can_redo is True
    assert session.current.signal is source.raw_signal
    np.testing.assert_array_equal(source.x_values, x_before)
    np.testing.assert_array_equal(source.y_values, y_before)


def test_preview_apply_undo_redo_reset() -> None:
    source = _spectrum([-2.0, -1.0, 0.0, 3.0])
    session = ProcessingSession(source)
    operation = create_normalization_operation("max_abs")

    preview = session.preview(operation)
    assert session.history == ()
    applied = session.apply(operation)
    assert len(session.history) == 1
    assert applied.source is source
    np.testing.assert_array_equal(applied.signal.values, preview.signal.values)

    undone = session.undo()
    assert session.history == ()
    assert undone.signal is source.raw_signal
    redone = session.redo()
    assert len(session.history) == 1
    np.testing.assert_array_equal(redone.signal.values, applied.signal.values)
    reset = session.reset()
    assert session.history == ()
    assert session.can_redo is False
    assert reset.signal is source.raw_signal
