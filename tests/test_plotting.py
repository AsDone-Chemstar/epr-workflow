"""Tests for the technique-independent plotting foundation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from spectralab.core.errors import PlottingError
from spectralab.core.model import (
    Axis1D,
    Provenance,
    Signal1D,
    Spectrum1D,
    SpectrumMetadata,
)
from spectralab.core.plotting import (
    LineStyle,
    PlotConfig,
    Series1D,
    build_series,
    format_axis_label,
    format_signal_label,
    plot_spectrum,
    render_series,
    series_from_processed,
    series_from_spectrum,
)
from spectralab.core.processing import (
    OperationOutput,
    ProcessedSpectrum,
    ProcessingSession,
)


def _spectrum(
    *,
    x_values=(1.0, 2.0, 3.0, 4.0),
    y_values=(10.0, 20.0, 30.0, 40.0),
    axis_name: str | None = "Frequency",
    axis_unit: str | None = "Hz",
    signal_name: str | None = "Signal",
    signal_unit: str | None = None,
    title: str | None = "Synthetic title",
) -> Spectrum1D:
    direction = "increasing" if np.all(np.diff(x_values) > 0) else "decreasing"
    return Spectrum1D(
        dataset_id="synthetic",
        axis=Axis1D(
            values=np.asarray(x_values, dtype=np.float64),
            quantity="frequency",
            unit=axis_unit,
            name=axis_name,
            direction=direction,
            metadata_source="test",
        ),
        raw_signal=Signal1D(
            values=np.asarray(y_values, dtype=np.float64),
            semantics="unknown",
            unit=signal_unit,
            name=signal_name,
            metadata_source="test",
        ),
        metadata=SpectrumMetadata(
            technique="test",
            title=title,
        ),
        provenance=Provenance(
            importer_id="test.plot",
            importer_version="1",
        ),
    )


class ScaleOperation:
    operation_id = "test.scale"
    name = "Scale"
    technique = "test"
    version = "1"
    changes_axis = False
    axis_change_description = None
    changes_signal_semantics = False
    changes_signal_unit = False
    signal_change_description = None
    parameters = {"factor": 2.0}

    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput:
        return OperationOutput(
            axis=axis,
            signal=Signal1D(
                values=signal.values * 2.0,
                semantics=signal.semantics,
                unit=signal.unit,
                name=signal.name,
                metadata_source=signal.metadata_source,
            ),
        )


def _processed(source: Spectrum1D) -> ProcessedSpectrum:
    return ProcessingSession(source).apply(ScaleOperation())


def _axes():
    figure = Figure(figsize=(4.0, 3.0))
    FigureCanvasAgg(figure)
    return figure, figure.add_subplot(111)


def _line_data(line):
    return np.asarray(line.get_xdata()), np.asarray(line.get_ydata())


def test_plot_spectrum1d_extracts_exact_xy_and_preserves_order() -> None:
    spectrum = _spectrum(
        x_values=(4.0, 3.0, 2.0, 1.0),
        y_values=(40.0, 30.0, 20.0, 10.0),
    )
    before_x = spectrum.x_values.copy()
    before_y = spectrum.y_values.copy()
    before_x_flags = spectrum.x_values.flags.writeable
    before_y_flags = spectrum.y_values.flags.writeable
    _figure, axes = _axes()

    lines = plot_spectrum(axes, spectrum)

    assert len(lines) == 1
    x_data, y_data = _line_data(lines[0])
    np.testing.assert_array_equal(x_data, before_x)
    np.testing.assert_array_equal(y_data, before_y)
    assert list(x_data) == [4.0, 3.0, 2.0, 1.0]
    assert lines[0].get_label() == "Raw"
    assert axes.get_xlabel() == "Frequency (Hz)"
    assert axes.get_ylabel() == "Signal"
    assert axes.get_title() == "Synthetic title"
    np.testing.assert_array_equal(spectrum.x_values, before_x)
    np.testing.assert_array_equal(spectrum.y_values, before_y)
    assert spectrum.x_values.flags.writeable == before_x_flags
    assert spectrum.y_values.flags.writeable == before_y_flags


def test_processed_spectrum_plots_raw_and_processed_distinctly() -> None:
    source = _spectrum()
    processed = _processed(source)
    _figure, axes = _axes()

    lines = plot_spectrum(axes, processed)

    assert len(lines) == 2
    raw_x, raw_y = _line_data(lines[0])
    processed_x, processed_y = _line_data(lines[1])
    np.testing.assert_array_equal(raw_x, source.x_values)
    np.testing.assert_array_equal(raw_y, source.y_values)
    np.testing.assert_array_equal(processed_x, processed.x_values)
    np.testing.assert_array_equal(processed_y, processed.y_values)
    assert lines[0].get_label() == "Raw"
    assert lines[1].get_label() == "Processed"
    assert lines[0].get_color() != lines[1].get_color()
    assert processed.is_original is False
    assert processed.operations == ("test.scale",)


def test_processed_spectrum_can_omit_raw_series() -> None:
    processed = _processed(_spectrum())
    _figure, axes = _axes()

    lines = plot_spectrum(axes, processed, include_raw=False)

    assert len(lines) == 1
    _x, y = _line_data(lines[0])
    np.testing.assert_array_equal(y, processed.y_values)
    assert lines[0].get_label() == "Processed"


def test_unknown_metadata_does_not_invent_labels() -> None:
    spectrum = _spectrum(
        axis_name=None,
        axis_unit=None,
        signal_name=None,
        signal_unit=None,
        title=None,
    )
    _figure, axes = _axes()

    plot_spectrum(axes, spectrum)

    assert axes.get_xlabel() == ""
    assert axes.get_ylabel() == ""
    assert axes.get_title() == ""
    assert format_axis_label(spectrum.axis) == ""
    assert format_signal_label(spectrum.raw_signal) == ""


def test_known_unit_without_name_is_not_discarded() -> None:
    spectrum = _spectrum(
        axis_name=None,
        axis_unit="Hz",
        signal_name=None,
        signal_unit="V",
    )
    _figure, axes = _axes()

    plot_spectrum(axes, spectrum)

    assert axes.get_xlabel() == "Hz"
    assert axes.get_ylabel() == "V"
    assert format_axis_label(spectrum.axis) == "Hz"
    assert format_signal_label(spectrum.raw_signal) == "V"


def test_explicit_labels_and_title_override_metadata() -> None:
    spectrum = _spectrum()
    _figure, axes = _axes()
    config = PlotConfig(
        title="User title",
        xlabel="User X",
        ylabel="User Y",
    )

    plot_spectrum(axes, spectrum, config)

    assert axes.get_title() == "User title"
    assert axes.get_xlabel() == "User X"
    assert axes.get_ylabel() == "User Y"


def test_explicit_empty_labels_are_respected() -> None:
    spectrum = _spectrum()
    _figure, axes = _axes()

    plot_spectrum(
        axes,
        spectrum,
        PlotConfig(title="", xlabel="", ylabel=""),
    )

    assert axes.get_title() == ""
    assert axes.get_xlabel() == ""
    assert axes.get_ylabel() == ""


def test_explicit_limits_grid_and_legend_configuration() -> None:
    spectrum = _spectrum()
    _figure, axes = _axes()
    config = PlotConfig(
        xlim=(1.5, 3.5),
        ylim=(5.0, 35.0),
        grid_visible=False,
        legend_visible=False,
    )

    plot_spectrum(axes, spectrum, config)

    assert axes.get_xlim() == (1.5, 3.5)
    assert axes.get_ylim() == (5.0, 35.0)
    assert not any(line.get_visible() for line in axes.get_xgridlines())
    assert axes.get_legend() is None

    config = PlotConfig(
        xlim=(1.5, 3.5),
        ylim=(5.0, 35.0),
        grid_visible=True,
        legend_visible=True,
        legend_location="lower left",
    )
    plot_spectrum(axes, spectrum, config)
    assert any(line.get_visible() for line in axes.get_xgridlines())
    assert axes.get_legend() is not None
    assert [text.get_text() for text in axes.get_legend().get_texts()] == [
        "Raw"
    ]


def test_line_style_width_and_color_are_applied() -> None:
    spectrum = _spectrum()
    _figure, axes = _axes()
    style = LineStyle(color="#AA2200", linewidth=2.5, linestyle=":")
    config = PlotConfig(raw_style=style)

    line = plot_spectrum(axes, spectrum, config)[0]

    assert line.get_color() == "#aa2200"
    assert line.get_linewidth() == 2.5
    assert line.get_linestyle() == ":"


def test_series_extraction_keeps_axis_and_signal_metadata() -> None:
    spectrum = _spectrum()
    series = series_from_spectrum(spectrum, label="Data")[0]

    assert isinstance(series, Series1D)
    assert series.kind == "raw"
    assert series.is_raw is True
    assert series.label == "Data"
    assert series.dataset_id == "synthetic"
    assert series.axis is spectrum.axis
    assert series.signal is spectrum.raw_signal
    assert series.point_count == 4
    np.testing.assert_array_equal(series.x_values, spectrum.x_values)
    np.testing.assert_array_equal(series.y_values, spectrum.y_values)

    processed = _processed(spectrum)
    raw, current = series_from_processed(
        processed,
        raw_label="Source",
        processed_label="Result",
    )
    assert raw.kind == "raw"
    assert current.kind == "processed"
    assert raw.axis is spectrum.axis
    assert current.axis is processed.axis
    assert current.signal is processed.signal


def test_build_series_uses_config_labels() -> None:
    source = _spectrum()
    config = PlotConfig(raw_label="Measured", processed_label="Computed")

    raw = build_series(source, config=config)
    assert [item.label for item in raw] == ["Measured"]

    both = build_series(_processed(source), config=config)
    assert [item.kind for item in both] == ["raw", "processed"]
    assert [item.label for item in both] == ["Measured", "Computed"]


def test_ambiguous_axis_labels_require_explicit_xlabel() -> None:
    source = _spectrum()
    shifted = Axis1D(
        values=source.x_values + 1.0,
        quantity="frequency",
        unit="kHz",
        name="Frequency",
        direction="increasing",
        metadata_source="test shifted",
    )
    processed = ProcessedSpectrum(
        source=source,
        axis=shifted,
        signal=source.raw_signal,
    )
    _figure, axes = _axes()

    with pytest.raises(PlottingError) as exc:
        plot_spectrum(axes, processed)
    assert exc.value.code == "plot_ambiguous_xlabel"

    lines = plot_spectrum(
        axes,
        processed,
        PlotConfig(xlabel="Explicit energy axis"),
    )
    assert len(lines) == 2
    assert axes.get_xlabel() == "Explicit energy axis"


def test_ambiguous_signal_labels_require_explicit_ylabel() -> None:
    source = _spectrum(signal_unit="V")
    changed = Signal1D(
        values=source.y_values,
        semantics=source.raw_signal.semantics,
        unit="mV",
        name=source.raw_signal.name,
        metadata_source="test changed",
    )
    processed = ProcessedSpectrum(
        source=source,
        axis=source.axis,
        signal=changed,
    )
    _figure, axes = _axes()

    with pytest.raises(PlottingError) as exc:
        plot_spectrum(axes, processed)
    assert exc.value.code == "plot_ambiguous_ylabel"

    plot_spectrum(axes, processed, PlotConfig(ylabel="Explicit signal label"))
    assert axes.get_ylabel() == "Explicit signal label"


def test_invalid_input_and_config_errors() -> None:
    _figure, axes = _axes()
    with pytest.raises(PlottingError) as unsupported:
        plot_spectrum(axes, "not a spectrum")  # type: ignore[arg-type]
    assert unsupported.value.code == "plot_unsupported_input"

    with pytest.raises(PlottingError) as color:
        LineStyle(color="red")
    assert color.value.code == "plot_line_style"

    with pytest.raises(PlottingError) as limits:
        PlotConfig(xlim=(1.0, 1.0))
    assert limits.value.code == "plot_limits"

    with pytest.raises(PlottingError):
        PlotConfig(legend_location="somewhere")

    with pytest.raises(PlottingError):
        PlotConfig(raw_label="")

    with pytest.raises(PlottingError) as include:
        plot_spectrum(axes, _spectrum(), include_raw="yes")  # type: ignore[arg-type]
    assert include.value.code == "plot_config"


def test_nonfinite_series_data_is_rejected() -> None:
    spectrum = _spectrum()
    values = spectrum.raw_signal.values
    values.setflags(write=True)
    values[1] = np.nan
    values.setflags(write=False)

    with pytest.raises(PlottingError) as exc:
        series_from_spectrum(spectrum)
    assert exc.value.code == "plot_nonfinite_data"


def test_mismatched_series_lengths_are_rejected() -> None:
    spectrum = _spectrum()
    with pytest.raises(PlottingError) as exc:
        Series1D(
            kind="processed",
            axis=spectrum.axis,
            signal=Signal1D(
                values=np.arange(3.0),
                semantics="unknown",
                unit=None,
            ),
            label="Processed",
            dataset_id="synthetic",
        )
    assert exc.value.code == "plot_series_data"


def test_render_series_with_explicit_title_and_no_metadata() -> None:
    spectrum = _spectrum()
    series = series_from_spectrum(spectrum)
    _figure, axes = _axes()

    lines = render_series(axes, series, PlotConfig(), title="Explicit title")

    assert len(lines) == 1
    assert axes.get_title() == "Explicit title"


def test_empty_series_is_rejected() -> None:
    _figure, axes = _axes()
    with pytest.raises(PlottingError) as exc:
        render_series(axes, ())
    assert exc.value.code == "plot_no_series"


def test_plot_does_not_change_processed_arrays() -> None:
    processed = _processed(_spectrum())
    before_x = processed.x_values.copy()
    before_y = processed.y_values.copy()
    _figure, axes = _axes()

    plot_spectrum(axes, processed)

    np.testing.assert_array_equal(processed.x_values, before_x)
    np.testing.assert_array_equal(processed.y_values, before_y)
    assert not processed.x_values.flags.writeable
    assert not processed.y_values.flags.writeable


def test_plot_preserves_decreasing_x_without_reversal() -> None:
    spectrum = _spectrum(
        x_values=(4.0, 3.0, 2.0, 1.0),
        y_values=(1.0, 2.0, 3.0, 4.0),
    )
    _figure, axes = _axes()

    line = plot_spectrum(axes, spectrum)[0]
    x_data, _y_data = _line_data(line)

    assert list(x_data) == [4.0, 3.0, 2.0, 1.0]
    assert spectrum.axis.direction == "decreasing"
