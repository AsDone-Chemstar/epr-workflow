"""M13 tests for explicit FTIR peak picking."""

from __future__ import annotations

import numpy as np
import pytest

from spectralab.core.model import Axis1D, Signal1D
from spectralab.techniques.ftir import (
    LIMITATIONS,
    PeakDetectionError,
    PeakDetectionParameters,
    PeakDetectionResult,
    PeakPolarity,
    detect_peak_values,
    detect_peaks,
)


def _axis(x: np.ndarray | list[float], *, direction="increasing") -> Axis1D:
    return Axis1D(
        values=np.asarray(x, dtype=np.float64),
        quantity="wavenumber",
        unit="cm^-1",
        name="Wavenumber",
        direction=direction,
        metadata_source="test",
    )


def _signal(y: np.ndarray | list[float], *, unit: str | None = "a.u.") -> Signal1D:
    return Signal1D(
        values=np.asarray(y, dtype=np.float64),
        semantics="absorbance",
        unit=unit,
        name="Absorbance",
        metadata_source="test",
    )


def _detect(
    y,
    *,
    x=None,
    direction="increasing",
    polarity="positive",
    **kwargs,
):
    x_values = np.arange(len(y), dtype=np.float64) if x is None else np.asarray(x, dtype=np.float64)
    params = PeakDetectionParameters(
        polarity=polarity,
        **kwargs,
    )
    return detect_peaks(
        _axis(x_values, direction=direction),
        _signal(y),
        params,
        dataset_id="peak-test",
    )


# ---------------------------------------------------------------------------
# Polarity and thresholds
# ---------------------------------------------------------------------------
def test_positive_peaks_detect_local_maxima() -> None:
    result = _detect([0.0, 1.0, 0.0, 0.0, 3.0, 0.0, 0.0, 2.0, 0.0])
    assert [peak.index for peak in result.peaks] == [1, 4, 7]
    assert [peak.x for peak in result.peaks] == [1.0, 4.0, 7.0]
    assert all(peak.polarity == "positive" for peak in result.peaks)
    assert result.positive_count == 3
    assert result.negative_count == 0
    assert result.parameters.source == "raw"
    assert result.dataset_id == "peak-test"
    assert result.axis_unit == "cm^-1"
    assert result.signal_unit == "a.u."


def test_negative_peaks_detect_local_minima_with_magnitude_thresholds() -> None:
    y = [0.0, -1.0, 0.0, 0.0, -3.0, 0.0, 0.0, -2.0, 0.0]
    result = _detect(y, polarity="negative", height=2.0, prominence=0.5)
    assert [peak.index for peak in result.peaks] == [4, 7]
    assert [peak.y for peak in result.peaks] == [-3.0, -2.0]
    assert all(peak.polarity == "negative" for peak in result.peaks)
    assert all(peak.prominence > 0 for peak in result.peaks)
    assert result.negative_count == 2
    assert result.positive_count == 0


def test_both_polarities_are_combined_in_original_order() -> None:
    y = [0.0, 2.0, 0.0, 0.0, -3.0, 0.0, 0.0, 1.0, 0.0]
    result = _detect(y, polarity="both")
    assert [peak.index for peak in result.peaks] == [1, 4, 7]
    assert [peak.polarity for peak in result.peaks] == [
        "positive",
        "negative",
        "positive",
    ]
    assert result.positive_count == 2
    assert result.negative_count == 1


def test_height_and_prominence_thresholds_filter_peaks() -> None:
    y = [0.0, 1.0, 0.0, 0.0, 3.0, 0.0, 0.0, 5.0, 0.0]
    result = _detect(y, height=2.0)
    assert [peak.index for peak in result.peaks] == [4, 7]
    result_prominence = _detect(y, prominence=2.0)
    assert [peak.index for peak in result_prominence.peaks] == [4, 7]


def test_minimum_distance_and_width() -> None:
    y = [0.0, 1.0, 0.0, 2.0, 0.0]
    result = _detect(y, distance_points=3)
    assert result.peak_count == 1
    assert result.peaks[0].index == 3

    broad = [0.0, 0.0, 0.0, 1.0, 2.0, 1.0, 0.0, 0.0, 0.0]
    unfiltered = _detect(broad)
    filtered = _detect(broad, min_width_points=3.0)
    assert unfiltered.peak_count == 1
    assert filtered.peak_count == 0
    assert unfiltered.peaks[0].width_samples > 0
    assert unfiltered.peaks[0].width_x > 0


def test_width_and_x_units_are_reported_for_increasing_axis() -> None:
    result = _detect([0.0, 1.0, 0.0], x=[1000.0, 1002.0, 1004.0])
    peak = result.peaks[0]
    assert peak.width_samples > 0
    assert peak.width_x > 0
    assert peak.x == 1002.0


def test_descending_axis_preserves_original_order() -> None:
    x = np.array([1004.0, 1002.0, 1000.0, 998.0, 996.0])
    y = np.array([0.0, 1.0, 0.0, 2.0, 0.0])
    result = _detect(y, x=x, direction="decreasing")
    assert result.axis_direction == "decreasing"
    assert [peak.index for peak in result.peaks] == [1, 3]
    assert [peak.x for peak in result.peaks] == [1002.0, 998.0]
    assert all(peak.width_x > 0 for peak in result.peaks)
    assert result.peaks[0].width_x == pytest.approx(2.0)


def test_peaks_near_but_not_at_boundaries_are_detected() -> None:
    result = _detect([0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0])
    assert [peak.index for peak in result.peaks] == [1, 6]


def test_boundary_peaks_and_limitations() -> None:
    y = [5.0, 1.0, 0.0, 1.0, 5.0]
    result = _detect(y)
    assert result.peak_count == 0
    assert any("first or last sample" in item for item in result.limitations)
    assert LIMITATIONS == result.limitations


def test_no_peaks_and_constant_signal_are_explicit() -> None:
    no_peaks = _detect([0.0, 0.0, 0.0, 0.0])
    assert no_peaks.peaks == ()
    assert any("constant" in warning for warning in no_peaks.warnings)
    assert any("No peaks" in warning for warning in no_peaks.warnings)

    flat = _detect([2.0, 2.0, 2.0])
    assert flat.peaks == ()
    assert any("constant" in warning for warning in flat.warnings)


def test_empty_mismatched_and_nonfinite_arrays_are_rejected() -> None:
    params = PeakDetectionParameters()
    with pytest.raises(PeakDetectionError) as empty:
        detect_peak_values([], [], params, dataset_id="empty")
    assert empty.value.code == "ftir_peak_invalid_input"

    with pytest.raises(PeakDetectionError) as mismatch:
        detect_peak_values([0.0, 1.0, 2.0], [0.0, 1.0], params, dataset_id="mismatch")
    assert mismatch.value.code == "ftir_peak_invalid_input"

    with pytest.raises(PeakDetectionError) as nonfinite:
        detect_peak_values([0.0, 1.0, 2.0], [0.0, np.nan, 1.0], params, dataset_id="nan")
    assert nonfinite.value.code == "ftir_peak_nonfinite_input"


def test_parameters_validate_explicitly() -> None:
    for kwargs in (
        {"height": -1.0},
        {"prominence": -1.0},
        {"height": float("nan")},
        {"distance_points": 0},
        {"distance_points": 1.5},
        {"min_width_points": -0.1},
    ):
        with pytest.raises(PeakDetectionError):
            PeakDetectionParameters(**kwargs)

    with pytest.raises(PeakDetectionError):
        PeakDetectionParameters(polarity="up")
    with pytest.raises(PeakDetectionError):
        PeakDetectionParameters(source="baseline")


def test_result_provenance_and_independence() -> None:
    x = [1000.0, 1001.0, 1002.0, 1003.0, 1004.0]
    y = [0.0, 3.0, 0.0, 2.0, 0.0]
    params = PeakDetectionParameters(
        polarity="positive",
        source="processed",
        height=0.5,
        prominence=0.2,
        distance_points=1,
        min_width_points=None,
    )
    history = ("ftir.normalize.min_max", "ftir.baseline.linear")
    result = detect_peaks(
        _axis(x),
        _signal(y),
        params,
        dataset_id="dataset-1",
        source_operation_history=history,
    )
    payload = result.as_dict()
    assert payload["algorithm"] == "scipy.signal.find_peaks"
    assert payload["algorithm_version"] == "1.0.0"
    assert payload["source"] == "processed"
    assert payload["polarity"] == "positive"
    assert payload["parameters"]["source"] == "processed"
    assert payload["parameters"]["polarity"] == "positive"
    assert payload["dataset_id"] == "dataset-1"
    assert payload["source_operation_history"] == list(history)
    assert payload["positive_count"] == 2
    assert payload["negative_count"] == 0
    assert payload["axis_unit"] == "cm^-1"
    assert payload["signal_unit"] == "a.u."
    assert payload["limitations"] == list(LIMITATIONS)
    assert len(payload["peaks"]) == 2
    assert "values" not in payload["peaks"][0]
    assert result.peaks[0].width_samples >= 0


def test_peak_result_rejects_invalid_objects() -> None:
    from spectralab.techniques.ftir.peaks import Peak1D

    with pytest.raises(PeakDetectionError):
        Peak1D(
            index=-1,
            polarity="positive",
            x=1.0,
            y=1.0,
            prominence=1.0,
            width_samples=1.0,
            width_x=1.0,
        )
    with pytest.raises(PeakDetectionError):
        Peak1D(
            index=0,
            polarity="both",  # type: ignore[arg-type]
            x=1.0,
            y=1.0,
            prominence=1.0,
            width_samples=1.0,
            width_x=1.0,
        )
