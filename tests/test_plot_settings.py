"""Tests for the pure plot-settings model and renderer."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from epr_workflow.plot_settings import (
    CURVE_DIFFERENCE,
    CURVE_FITTED_BASELINE,
    CURVE_PROCESSED,
    CURVE_RAW,
    AxisSettings,
    CurveStyle,
    PlotSettingsError,
    PlotSettingsStore,
    available_curve_keys,
    build_curves,
    curve_arrays,
    curve_data_ranges,
    default_curve_label_key,
    default_settings,
    default_title_key,
    default_ylabel_key,
    draw_spectrum,
    normalize_color,
    reconcile_settings,
    restore_default_visibility,
    validate_plot_settings,
)
from epr_workflow.preprocessing import (
    BASELINE_OPERATION,
    SAVGOL_OPERATION,
    BaselineWindow,
    LinearBaselineSpec,
    PreprocessingSession,
    SavgolSpec,
)


def make_session(
    source: Path, *, peak: float = 500.0
) -> tuple[PreprocessingSession, np.ndarray, np.ndarray]:
    field = np.linspace(3280.0, 3380.0, 101)
    intensity = (
        2.0 * field
        + 5.0
        + peak * np.exp(-((field - 3330.0) / 5.0) ** 2)
    )
    session = PreprocessingSession(
        source=source,
        field_G=field,
        intensity=intensity,
        source_sha256="sha",
    )
    return session, field, intensity


def baseline_spec() -> LinearBaselineSpec:
    return LinearBaselineSpec(
        window_left=BaselineWindow(3280.0, 3284.0),
        window_right=BaselineWindow(3376.0, 3380.0),
    )


def processed_result(source: Path):
    session, _field, _intensity = make_session(source)
    return session.apply(baseline_spec())


# --------------------------------------------------------------------------
# Availability and defaults
# --------------------------------------------------------------------------
def test_raw_only_has_one_visible_curve_and_no_legend(tmp_path: Path) -> None:
    settings = default_settings(None)

    assert available_curve_keys(None) == (CURVE_RAW,)
    assert set(settings.curves) == {CURVE_RAW}
    assert settings.visible_keys == (CURVE_RAW,)
    assert settings.axis.legend_visible is False
    assert settings.curves[CURVE_RAW].color == "#1f4e79"
    assert settings.curves[CURVE_RAW].linewidth == 1.0


def test_processed_result_exposes_raw_processed_difference_and_fit(
    tmp_path: Path,
) -> None:
    result = processed_result(tmp_path / "sample.ASC")
    defaults = default_settings(result)
    keys = available_curve_keys(result)

    assert set(keys) == {
        CURVE_RAW,
        CURVE_PROCESSED,
        CURVE_DIFFERENCE,
        CURVE_FITTED_BASELINE,
    }
    assert defaults.curves[CURVE_FITTED_BASELINE].visible is False
    assert defaults.visible_keys == (
        CURVE_RAW,
        CURVE_PROCESSED,
        CURVE_DIFFERENCE,
    )
    assert defaults.axis.legend_visible is True
    assert result.last_fit is not None


def test_smoothing_uses_smoothed_labels_and_ylabel(tmp_path: Path) -> None:
    session, _field, _intensity = make_session(tmp_path / "sample.ASC")
    result = session.apply_savgol(SavgolSpec(9, 3))

    assert result.operations == (SAVGOL_OPERATION,)
    assert default_curve_label_key(CURVE_PROCESSED, result) == "plot_legend_smoothed"
    assert default_curve_label_key(CURVE_DIFFERENCE, result) == "plot_legend_difference"
    assert default_ylabel_key(result) == "plot_ylabel_smoothed"
    assert default_title_key(result) == "plot_title_smoothed"


def test_baseline_defaults_use_corrected_labels(tmp_path: Path) -> None:
    result = processed_result(tmp_path / "sample.ASC")
    defaults = default_settings(result)

    assert result.operations == (BASELINE_OPERATION,)
    assert default_curve_label_key(CURVE_PROCESSED, result) == "plot_legend_corrected"
    assert default_curve_label_key(CURVE_DIFFERENCE, result) == "plot_legend_removed"
    assert default_ylabel_key(result) == "plot_ylabel_corrected"
    assert defaults.axis.legend_visible is True


def test_fitted_baseline_is_evaluated_not_refit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = processed_result(tmp_path / "sample.ASC")
    fit = result.last_fit
    assert fit is not None

    import epr_workflow.preprocessing as preprocessing_module

    def _fail(*args, **kwargs):
        raise AssertionError("plotting must not refit the baseline")

    monkeypatch.setattr(
        preprocessing_module, "fit_linear_baseline", _fail
    )

    arrays = curve_arrays(None, None, result)
    expected = fit.slope * result.field_G + fit.intercept
    np.testing.assert_allclose(
        arrays[CURVE_FITTED_BASELINE][1], expected
    )
    np.testing.assert_array_equal(
        arrays[CURVE_RAW][1], result.intensity_raw
    )


# --------------------------------------------------------------------------
# Reconciliation and validation
# --------------------------------------------------------------------------
def test_reconcile_keeps_customisations_and_drops_unavailable_curves(
    tmp_path: Path,
) -> None:
    result = processed_result(tmp_path / "sample.ASC")
    custom = default_settings(result)
    custom.curves[CURVE_RAW].color = "#AA0000"
    custom.curves[CURVE_RAW].display_name = "My raw"
    custom.curves[CURVE_PROCESSED].linewidth = 2.4
    custom.axis.title = "Custom title"

    raw_only = reconcile_settings(custom, default_settings(None))
    assert set(raw_only.curves) == {CURVE_RAW}
    assert raw_only.curves[CURVE_RAW].color == "#aa0000"
    assert raw_only.curves[CURVE_RAW].display_name == "My raw"
    assert raw_only.axis.title == "Custom title"

    reprocessed = reconcile_settings(raw_only, default_settings(result))
    assert set(reprocessed.curves) == {
        CURVE_RAW,
        CURVE_PROCESSED,
        CURVE_DIFFERENCE,
        CURVE_FITTED_BASELINE,
    }
    assert reprocessed.curves[CURVE_RAW].display_name == "My raw"
    assert reprocessed.curves[CURVE_PROCESSED].linewidth == 1.0
    assert reprocessed.axis.title == "Custom title"


def test_restore_default_visibility_changes_only_visibility(
    tmp_path: Path,
) -> None:
    result = processed_result(tmp_path / "sample.ASC")
    settings = default_settings(result)
    settings.curves[CURVE_RAW].visible = False
    settings.curves[CURVE_RAW].display_name = "Keep me"
    settings.curves[CURVE_RAW].color = "#123456"
    settings.axis.title = "Keep axis"

    restored = restore_default_visibility(
        settings, default_settings(result)
    )

    assert restored.curves[CURVE_RAW].visible is True
    assert restored.curves[CURVE_RAW].display_name == "Keep me"
    assert restored.curves[CURVE_RAW].color == "#123456"
    assert restored.axis.title == "Keep axis"


def test_validate_rejects_missing_unavailable_and_all_hidden(
    tmp_path: Path,
) -> None:
    result = processed_result(tmp_path / "sample.ASC")
    settings = default_settings(result)
    settings.curves.pop(CURVE_DIFFERENCE)
    with pytest.raises(PlotSettingsError) as missing:
        validate_plot_settings(settings, available_curve_keys(result))
    assert missing.value.code == "plot_missing_curve"

    raw = default_settings(None)
    validate_plot_settings(raw, available_curve_keys(None))
    raw.curves[CURVE_RAW].visible = False
    with pytest.raises(PlotSettingsError) as hidden:
        validate_plot_settings(
            raw, available_curve_keys(None), require_visible=True
        )
    assert hidden.value.code == "plot_no_visible_curve"

    raw.curves[CURVE_RAW].visible = True
    raw.curves[CURVE_PROCESSED] = CurveStyle(CURVE_PROCESSED)
    with pytest.raises(PlotSettingsError) as unavailable:
        validate_plot_settings(raw, available_curve_keys(None))
    assert unavailable.value.code == "plot_unavailable_curve"


def test_invalid_colours_ranges_and_line_styles_are_rejected() -> None:
    with pytest.raises(PlotSettingsError) as colour:
        normalize_color("red")
    assert colour.value.code == "plot_color"
    assert normalize_color(" #AABBCC ") == "#aabbcc"

    with pytest.raises(PlotSettingsError) as axis_range:
        AxisSettings(xlim=(10.0, 10.0))
    assert axis_range.value.code == "plot_axis_range"

    with pytest.raises(PlotSettingsError):
        AxisSettings(legend_location="somewhere")

    with pytest.raises(PlotSettingsError):
        CurveStyle(CURVE_RAW, linewidth=0)

    with pytest.raises(PlotSettingsError):
        CurveStyle("not-a-curve")

    with pytest.raises(PlotSettingsError):
        CurveStyle(CURVE_RAW, color="#12345")


# --------------------------------------------------------------------------
# Rendering and arrays
# --------------------------------------------------------------------------
def test_build_curves_uses_render_order_and_custom_labels(
    tmp_path: Path,
) -> None:
    result = processed_result(tmp_path / "sample.ASC")
    settings = default_settings(result)
    settings.curves[CURVE_FITTED_BASELINE].visible = True
    settings.curves[CURVE_PROCESSED].display_name = "Custom processed"

    curves = build_curves(
        np.zeros(3),
        np.zeros(3),
        result,
        settings,
        {
            CURVE_RAW: "Raw",
            CURVE_PROCESSED: "Processed",
            CURVE_DIFFERENCE: "Difference",
            CURVE_FITTED_BASELINE: "Fitted",
        },
    )

    assert [curve.key for curve in curves] == [
        CURVE_RAW,
        CURVE_FITTED_BASELINE,
        CURVE_DIFFERENCE,
        CURVE_PROCESSED,
    ]
    assert [curve.label for curve in curves] == [
        "Raw",
        "Fitted",
        "Difference",
        "Custom processed",
    ]


def test_curve_data_ranges_respect_visibility() -> None:
    settings = default_settings(None)
    from epr_workflow.plot_settings import CurveData

    visible = CurveData(
        CURVE_RAW,
        np.array([1.0, 3.0]),
        np.array([-2.0, 4.0]),
        "Raw",
        settings.curves[CURVE_RAW],
    )
    hidden = CurveData(
        CURVE_FITTED_BASELINE,
        np.array([1.0, 3.0]),
        np.array([-100.0, 100.0]),
        "Fitted",
        CurveStyle(CURVE_FITTED_BASELINE, visible=False),
    )

    assert curve_data_ranges([visible, hidden]) == ((1.0, 3.0), (-2.0, 4.0))
    assert curve_data_ranges(
        [visible, hidden], visible_only=False
    ) == ((1.0, 3.0), (-100.0, 100.0))


def test_draw_spectrum_applies_visibility_limits_fonts_and_legend(
    tmp_path: Path,
) -> None:
    result = processed_result(tmp_path / "sample.ASC")
    settings = default_settings(result)
    settings.axis.title = "Title"
    settings.axis.xlabel = "Field"
    settings.axis.ylabel = "Signal"
    settings.axis.xlim = (3290.0, 3370.0)
    settings.axis.ylim = (-5.0, 5.0)
    settings.axis.title_fontsize = 15.0
    settings.axis.axis_fontsize = 11.0
    settings.axis.tick_fontsize = 9.0
    settings.axis.legend_fontsize = 7.0
    settings.axis.legend_location = "lower left"

    curves = build_curves(
        np.zeros(3),
        np.zeros(3),
        result,
        settings,
        {
            CURVE_RAW: "Raw",
            CURVE_PROCESSED: "Processed",
            CURVE_DIFFERENCE: "Difference",
            CURVE_FITTED_BASELINE: "Fitted",
        },
    )
    figure = Figure(figsize=(4.0, 3.0))
    FigureCanvasAgg(figure)
    axes = figure.add_subplot(111)

    draw_spectrum(axes, curves, settings)

    assert len(axes.lines) == 3
    assert axes.get_xlim() == (3290.0, 3370.0)
    assert axes.get_ylim() == (-5.0, 5.0)
    assert axes.get_title() == "Title"
    assert axes.get_xlabel() == "Field"
    assert axes.get_ylabel() == "Signal"
    assert axes.title.get_fontsize() == 15.0
    assert axes.xaxis.label.get_fontsize() == 11.0
    assert axes.yaxis.label.get_fontsize() == 11.0
    assert axes.get_legend() is not None
    assert axes.get_legend().get_texts()[0].get_text() == "Raw"
    assert axes.get_legend().get_texts()[0].get_fontsize() == 7.0

    settings.curves[CURVE_RAW].visible = False
    settings.curves[CURVE_PROCESSED].visible = False
    settings.curves[CURVE_DIFFERENCE].visible = False
    settings.axis.legend_visible = False
    draw_spectrum(axes, curves, settings)
    assert len(axes.lines) == 0
    assert axes.get_legend() is None


def test_draw_spectrum_renders_none_labels_as_empty(tmp_path: Path) -> None:
    settings = default_settings(None)
    curves = build_curves(
        np.array([1.0, 2.0, 3.0]),
        np.array([0.0, 1.0, 0.0]),
        None,
        settings,
        {CURVE_RAW: "Raw"},
    )
    figure = Figure()
    FigureCanvasAgg(figure)
    axes = figure.add_subplot(111)

    draw_spectrum(axes, curves, settings)

    assert axes.get_title() == ""
    assert axes.get_xlabel() == ""
    assert axes.get_ylabel() == ""


# --------------------------------------------------------------------------
# Per-sample store
# --------------------------------------------------------------------------
def test_store_is_per_sample_and_discards_on_sha_change(
    tmp_path: Path,
) -> None:
    store = PlotSettingsStore()
    first = tmp_path / "a.ASC"
    second = tmp_path / "b.ASC"

    settings = store.settings_for(first, "sha-a", None)
    settings.curves[CURVE_RAW].display_name = "A"
    settings.curves[CURVE_RAW].color = "#010203"
    store.update(first, "sha-a", settings)

    other = store.settings_for(second, "sha-b", None)
    assert other.curves[CURVE_RAW].display_name is None
    assert other.curves[CURVE_RAW].color == "#1f4e79"

    again = store.settings_for(first, "sha-a", None)
    assert again.curves[CURVE_RAW].display_name == "A"
    assert again.curves[CURVE_RAW].color == "#010203"

    changed = store.settings_for(first, "sha-new", None)
    assert changed.curves[CURVE_RAW].display_name is None
    assert changed.curves[CURVE_RAW].color == "#1f4e79"
    assert len(store) == 2


def test_store_returns_independent_copies(tmp_path: Path) -> None:
    store = PlotSettingsStore()
    source = tmp_path / "a.ASC"
    first = store.settings_for(source, "sha", None)
    first.curves[CURVE_RAW].color = "#ff0000"

    second = store.settings_for(source, "sha", None)

    assert second.curves[CURVE_RAW].color == "#1f4e79"
