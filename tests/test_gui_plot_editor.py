"""Headless GUI tests for the Plot Editor and PNG plot export."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QListWidgetItem  # noqa: E402

import epr_workflow.gui.main_window as main_window_module  # noqa: E402
from epr_workflow.gui.i18n import tr_text  # noqa: E402
from epr_workflow.gui.main_window import MainWindow  # noqa: E402
from epr_workflow.gui.plot_export_dialog import (  # noqa: E402
    TEXT_KEYS as EXPORT_DIALOG_KEYS,
    PlotExportDialog,
)
from epr_workflow.plot_export import PlotExportSettings  # noqa: E402
from epr_workflow.plot_settings import (  # noqa: E402
    CURVE_DIFFERENCE,
    CURVE_FITTED_BASELINE,
    CURVE_PROCESSED,
    CURVE_RAW,
    default_settings,
)

HEADER = "     index           Field [G]        Intensity []\n\n"


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(
        main_window_module.QMessageBox, "warning", staticmethod(_noop)
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox, "critical", staticmethod(_noop)
    )


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def write_asc(path: Path, n: int = 101, peak: float = 500.0) -> Path:
    rows = []
    for i in range(n):
        field = 3280.0 + i
        intensity = (
            2.0 * field
            + 5.0
            + peak * np.exp(-((field - 3330.0) / 5.0) ** 2)
        )
        rows.append(f"{i + 1} {field!r} {float(intensity)!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        HEADER + "\n".join(rows) + "\n", encoding="utf-8", newline="\n"
    )
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_with_windows(window: MainWindow, path: Path) -> None:
    window._load_and_display(path)
    window.preprocessing_panel.set_values(
        3280.0, 3284.0, 3376.0, 3380.0
    )


def apply_baseline(window: MainWindow) -> None:
    window.preprocessing_panel.apply_requested.emit()


def curve_item(window: MainWindow, key: str) -> QListWidgetItem:
    for row in range(window.plot_editor_panel.curve_list.count()):
        item = window.plot_editor_panel.curve_list.item(row)
        if item.data(Qt.ItemDataRole.UserRole) == key:
            return item
    raise AssertionError(f"curve item not found: {key}")


def curve_texts(window: MainWindow) -> list[str]:
    panel = window.plot_editor_panel
    return [
        panel.curve_list.item(row).text()
        for row in range(panel.curve_list.count())
    ]


# --------------------------------------------------------------------------
# Dynamic availability
# --------------------------------------------------------------------------
def test_raw_sample_offers_only_raw_curve(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window._load_and_display(source)

    panel = window.plot_editor_panel
    assert panel.curve_keys() == (CURVE_RAW,)
    assert panel.curve_list.count() == 1
    assert curve_texts(window) == ["原始"]
    assert curve_item(window, CURVE_RAW).checkState() == Qt.CheckState.Checked
    assert len(window.canvas.axes.lines) == 1
    assert panel.export_btn.isEnabled()
    assert panel.settings().axis.legend_visible is False


def test_baseline_adds_curves_and_fitted_baseline_is_hidden(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_with_windows(window, source)
    apply_baseline(window)

    panel = window.plot_editor_panel
    assert set(panel.curve_keys()) == {
        CURVE_RAW,
        CURVE_PROCESSED,
        CURVE_DIFFERENCE,
        CURVE_FITTED_BASELINE,
    }
    assert curve_item(
        window, CURVE_FITTED_BASELINE
    ).checkState() == Qt.CheckState.Unchecked
    assert "拟合基线" in curve_texts(window)
    assert len(window.canvas.axes.lines) == 3
    assert panel.settings().axis.legend_visible is True

    panel.set_curve_visible(CURVE_FITTED_BASELINE, True)
    assert len(window.canvas.axes.lines) == 4
    legend_labels = [
        text.get_text()
        for text in window.canvas.axes.get_legend().get_texts()
    ]
    assert "拟合基线" in legend_labels

    panel.set_curve_visible(CURVE_RAW, False)
    assert len(window.canvas.axes.lines) == 3


def test_cancel_preview_removes_processed_curves_but_keeps_raw_style(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_with_windows(window, source)
    panel = window.plot_editor_panel
    panel.set_curve_color(CURVE_RAW, "#aa0000")
    panel.set_curve_display_name(CURVE_RAW, "My raw")

    window.preprocessing_panel.preview_requested.emit()
    assert CURVE_PROCESSED in panel.curve_keys()
    assert len(window.canvas.axes.lines) == 3

    window.preprocessing_panel.cancel_preview_requested.emit()

    assert panel.curve_keys() == (CURVE_RAW,)
    assert panel.settings().curves[CURVE_RAW].color == "#aa0000"
    assert panel.settings().curves[CURVE_RAW].display_name == "My raw"
    assert len(window.canvas.axes.lines) == 1


# --------------------------------------------------------------------------
# Curve style and axes
# --------------------------------------------------------------------------
def test_curve_style_edits_update_plot_without_touching_data(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window._load_and_display(source)
    before = window._current_view.data["intensity"].to_numpy().copy()
    panel = window.plot_editor_panel

    panel.set_curve_display_name(CURVE_RAW, "My raw")
    panel.set_curve_color(CURVE_RAW, "#112233")
    panel.set_curve_linewidth(CURVE_RAW, 2.5)
    panel.set_curve_linestyle(CURVE_RAW, "--")
    panel.set_legend_visible(True)

    line = window.canvas.axes.lines[0]
    assert line.get_color() == "#112233"
    assert line.get_linewidth() == 2.5
    assert line.get_linestyle() == "--"
    legend = window.canvas.axes.get_legend()
    assert legend is not None
    assert legend.get_texts()[0].get_text() == "My raw"
    np.testing.assert_array_equal(
        window._current_view.data["intensity"].to_numpy(), before
    )


def test_axis_edits_ranges_legend_and_fonts_update_plot(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window._load_and_display(source)
    panel = window.plot_editor_panel

    panel.set_title("Custom title")
    panel.set_xlabel("")
    panel.set_ylabel("Custom Y")
    panel.set_x_range(3290.0, 3370.0)
    panel.set_y_range(-100.0, 1000.0)
    panel.set_legend_visible(True)
    panel.set_legend_location("lower left")
    panel.set_font_sizes(title=14, axis=11, tick=9, legend=7)

    axes = window.canvas.axes
    assert axes.get_title() == "Custom title"
    assert axes.get_xlabel() == ""
    assert axes.get_ylabel() == "Custom Y"
    assert axes.get_xlim() == (3290.0, 3370.0)
    assert axes.get_ylim() == (-100.0, 1000.0)
    assert axes.get_legend() is not None
    assert axes.get_legend()._loc == 3  # lower left
    assert axes.title.get_fontsize() == 14.0
    assert axes.xaxis.label.get_fontsize() == 11.0
    assert axes.get_legend().get_texts()[0].get_fontsize() == 7.0

    panel.set_x_range()  # back to automatic
    assert panel.settings().axis.xlim is None
    low, high = axes.get_xlim()
    # Matplotlib's default autoscale margin keeps the data inside the view.
    assert low < 3280.0 < high
    assert low < 3380.0 < high
    assert (low, high) != (3290.0, 3370.0)


def test_invalid_manual_range_is_reported_and_previous_range_kept(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window._load_and_display(source)
    panel = window.plot_editor_panel

    panel.x_auto_check.setChecked(False)
    previous = panel.settings().axis.xlim
    assert previous is not None

    panel.x_min_edit.setText("10")
    panel.x_max_edit.setText("5")
    panel.x_min_edit.editingFinished.emit()

    assert panel.error_label.text() != ""
    assert panel.settings().axis.xlim == previous

    panel.x_min_edit.setText("3290")
    panel.x_max_edit.setText("3370")
    panel.x_min_edit.editingFinished.emit()

    assert panel.error_label.text() == ""
    assert panel.settings().axis.xlim == (3290.0, 3370.0)


def test_reset_restores_plot_defaults(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_with_windows(window, source)
    apply_baseline(window)
    panel = window.plot_editor_panel
    panel.set_title("Temporary")
    panel.set_curve_color(CURVE_RAW, "#ff0000")
    panel.set_curve_visible(CURVE_RAW, False)

    panel.reset_requested.emit()

    settings = panel.settings()
    expected = default_settings(window._active_result())
    assert settings.axis.title is None
    assert settings.curves[CURVE_RAW].color == expected.curves[CURVE_RAW].color
    assert settings.curves[CURVE_RAW].visible is True
    assert settings.curves[CURVE_FITTED_BASELINE].visible is False
    assert len(window.canvas.axes.lines) == len(expected.visible_keys)
    assert window.canvas.axes.get_title().endswith(
        "线性基线校正后 CW-EPR 谱图"
    )


def test_restore_default_visibility_keeps_style(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window._load_and_display(source)
    panel = window.plot_editor_panel
    panel.set_curve_color(CURVE_RAW, "#123456")
    panel.set_curve_display_name(CURVE_RAW, "Keep")
    panel.set_curve_visible(CURVE_RAW, False)
    assert len(window.canvas.axes.lines) == 0

    panel.restore_visibility_requested.emit()

    assert panel.settings().curves[CURVE_RAW].visible is True
    assert panel.settings().curves[CURVE_RAW].color == "#123456"
    assert panel.settings().curves[CURVE_RAW].display_name == "Keep"
    assert len(window.canvas.axes.lines) == 1


# --------------------------------------------------------------------------
# Per-sample settings and language switching
# --------------------------------------------------------------------------
def test_settings_are_kept_per_sample(
    app: QApplication, tmp_path: Path
) -> None:
    first = write_asc(tmp_path / "a.ASC")
    second = write_asc(tmp_path / "b.ASC")
    window = MainWindow()
    window._load_and_display(first)
    panel = window.plot_editor_panel
    panel.set_curve_display_name(CURVE_RAW, "A raw")
    panel.set_curve_color(CURVE_RAW, "#010203")
    panel.set_title("A title")

    window._load_and_display(second)

    assert panel.settings().curves[CURVE_RAW].display_name is None
    assert panel.settings().curves[CURVE_RAW].color == "#1f4e79"
    assert panel.settings().axis.title is None

    window._load_and_display(first)

    assert panel.settings().curves[CURVE_RAW].display_name == "A raw"
    assert panel.settings().curves[CURVE_RAW].color == "#010203"
    assert panel.settings().axis.title == "A title"
    assert window.canvas.axes.get_title() == "A title"


def test_language_switch_updates_auto_labels_without_reload_or_refit(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import epr_workflow.preprocessing as preprocessing_module

    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_with_windows(window, source)
    apply_baseline(window)
    panel = window.plot_editor_panel
    panel.set_curve_display_name(CURVE_RAW, "我的原始")
    panel.set_curve_color(CURVE_RAW, "#445566")
    steps_before = len(window._session.steps)

    def _fail_reload(path):
        raise AssertionError("language switch must not reload the ASC file")

    def _fail_refit(*args, **kwargs):
        raise AssertionError("language switch must not refit the baseline")

    monkeypatch.setattr(main_window_module, "load_spectrum", _fail_reload)
    monkeypatch.setattr(
        preprocessing_module, "fit_linear_baseline", _fail_refit
    )

    window._set_language("en")

    assert panel.settings().curves[CURVE_RAW].display_name == "我的原始"
    assert panel.settings().curves[CURVE_RAW].color == "#445566"
    assert "我的原始" in curve_texts(window)
    assert window.canvas.axes.get_title() == (
        "sample - Linear Baseline Corrected CW-EPR Spectrum"
    )
    assert window.canvas.axes.get_xlabel() == "Magnetic field (G)"
    assert window.canvas.axes.get_ylabel() == (
        "Intensity (original units, baseline corrected)"
    )
    assert panel.curve_list.item(0).text() == "我的原始"
    assert steps_before == 1

    window._set_language("zh")

    assert window.canvas.axes.get_title() == "sample - 线性基线校正后 CW-EPR 谱图"
    assert panel.settings().curves[CURVE_RAW].display_name == "我的原始"


def test_plot_editor_tab_labels_follow_language(
    app: QApplication,
) -> None:
    window = MainWindow()

    assert window.left_tabs.tabText(0) == "预处理"
    assert window.left_tabs.tabText(1) == "绘图"

    window._set_language("en")

    assert window.left_tabs.tabText(0) == "Preprocessing"
    assert window.left_tabs.tabText(1) == "Plot"


# --------------------------------------------------------------------------
# Plot export
# --------------------------------------------------------------------------
def test_plot_export_writes_png_and_leaves_scientific_outputs_unchanged(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    before = sha256(source)
    window = MainWindow()
    window.output_base = tmp_path / "out"
    load_with_windows(window, source)
    apply_baseline(window)
    window.preprocessing_panel.export_requested.emit()

    csv_path = tmp_path / "out" / "tables" / "sample_baseline.csv"
    json_path = (
        tmp_path / "out" / "logs" / "sample_baseline_metadata.json"
    )
    csv_before = sha256(csv_path)
    json_before = sha256(json_path)

    target = tmp_path / "out" / "figures" / "sample_plot.png"
    result = window._export_plot_to(
        target,
        PlotExportSettings(
            width_in=4.0,
            height_in=3.0,
            dpi=100,
        ),
    )

    assert result == target
    assert target.exists()
    assert target.read_bytes().startswith(b"\x89PNG")
    assert sha256(csv_path) == csv_before
    assert sha256(json_path) == json_before
    assert sha256(source) == before
    assert "绘图已导出" in window.plot_editor_panel.status_label.text()


def test_plot_export_refuses_overwrite_until_allowed(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window._load_and_display(source)
    target = tmp_path / "sample_plot.png"
    target.write_bytes(b"keep me")
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        staticmethod(
            lambda parent, title, text, *a, **k: messages.append((title, text))
        ),
    )

    assert (
        window._export_plot_to(
            target, PlotExportSettings(dpi=100), overwrite=False
        )
        is None
    )
    assert target.read_bytes() == b"keep me"
    assert messages and messages[-1][0] == "已存在输出"

    result = window._export_plot_to(
        target, PlotExportSettings(dpi=100), overwrite=True
    )
    assert result == target
    assert target.read_bytes().startswith(b"\x89PNG")


def test_plot_export_is_disabled_during_preview(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window.output_base = tmp_path / "out"
    load_with_windows(window, source)
    window.preprocessing_panel.preview_requested.emit()

    panel = window.plot_editor_panel
    assert panel.export_btn.isEnabled() is False
    assert "预览" in panel.status_label.text()
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        staticmethod(
            lambda parent, title, text, *a, **k: messages.append((title, text))
        ),
    )

    def _fail_dialog(*args, **kwargs):
        raise AssertionError("preview must not open the export dialog")

    monkeypatch.setattr(main_window_module, "PlotExportDialog", _fail_dialog)

    panel.export_requested.emit()

    assert messages and messages[-1][0] == "无法导出绘图"
    assert not (tmp_path / "out" / "figures").exists()

    window.preprocessing_panel.cancel_preview_requested.emit()
    assert panel.export_btn.isEnabled() is True
    assert panel.status_label.text() == ""


def test_plot_export_with_no_visible_curve_is_reported(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window._load_and_display(source)
    window.plot_editor_panel.set_curve_visible(CURVE_RAW, False)
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        staticmethod(
            lambda parent, title, text, *a, **k: messages.append((title, text))
        ),
    )
    target = tmp_path / "sample_plot.png"

    result = window._export_plot_to(target, PlotExportSettings(dpi=100))

    assert result is None
    assert not target.exists()
    assert "至少需要一条可见曲线" in messages[-1][1]


def test_export_dialog_defaults_and_path_validation(
    app: QApplication, tmp_path: Path
) -> None:
    texts = {key: tr_text(key, "zh") for key in EXPORT_DIALOG_KEYS}
    dialog = PlotExportDialog(
        None,
        texts=texts,
        default_path=tmp_path / "sample_plot.png",
        options=PlotExportSettings(),
        overwrite=False,
    )

    assert dialog.windowTitle() == "导出绘图 PNG"
    assert dialog.output_path() == tmp_path / "sample_plot.png"
    assert dialog.overwrite() is False
    assert dialog.width_spin.value() == 8.0
    assert dialog.height_spin.value() == 5.0
    assert dialog.dpi_spin.value() == 300
    assert dialog.include_title_check.isChecked()
    assert dialog.include_legend_check.isChecked()

    dialog.width_spin.setValue(4.0)
    dialog.height_spin.setValue(3.0)
    dialog.dpi_spin.setValue(600)
    dialog.include_legend_check.setChecked(False)
    options = dialog.export_settings()
    assert options.width_in == 4.0
    assert options.height_in == 3.0
    assert options.dpi == 600
    assert options.include_legend is False

    dialog.path_edit.setText("not-a-png.txt")
    dialog.accept()
    assert dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.error_label.text() == "输出路径必须是以 .png 结尾的文件。"

    dialog.path_edit.setText(str(tmp_path / "ok.png"))
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.close()


def test_export_dialog_uses_default_figures_path_and_current_style(
    app: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window.output_base = tmp_path / "out"
    window._load_and_display(source)
    panel = window.plot_editor_panel
    panel.set_curve_color(CURVE_RAW, "#112233")
    panel.set_curve_linewidth(CURVE_RAW, 3.0)
    panel.set_title("Preview title")
    panel.set_legend_visible(True)
    captured: dict[str, object] = {}
    real_export = main_window_module.export_plot_png

    class FakeDialog:
        def __init__(
            self,
            parent,
            *,
            texts,
            default_path,
            options,
            overwrite,
        ) -> None:
            captured["texts"] = texts
            captured["default_path"] = default_path
            captured["options"] = options
            captured["overwrite"] = overwrite
            self._path = default_path

        def exec(self):
            return QDialog.DialogCode.Accepted

        def output_path(self) -> Path:
            return self._path

        def export_settings(self) -> PlotExportSettings:
            return PlotExportSettings(width_in=4.0, height_in=3.0, dpi=150)

        def overwrite(self) -> bool:
            return False

    def capture_export(**kwargs):
        captured.update(kwargs)
        return real_export(**kwargs)

    monkeypatch.setattr(main_window_module, "PlotExportDialog", FakeDialog)
    monkeypatch.setattr(
        main_window_module, "export_plot_png", capture_export
    )

    panel.export_requested.emit()

    expected = tmp_path / "out" / "figures" / "sample_plot.png"
    assert captured["default_path"] == expected
    assert captured["overwrite"] is False
    rendered = captured["settings"]
    assert rendered.axis.title == "Preview title"
    assert rendered.axis.legend_visible is True
    assert rendered.curves[CURVE_RAW].color == "#112233"
    assert rendered.curves[CURVE_RAW].linewidth == 3.0
    assert expected.exists()
    assert expected.read_bytes().startswith(b"\x89PNG")
    assert "绘图已导出" in panel.status_label.text()


def test_plot_style_changes_do_not_refit_or_resmooth(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import epr_workflow.preprocessing as preprocessing_module

    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window.output_base = tmp_path / "out"
    load_with_windows(window, source)
    apply_baseline(window)

    def _fail(*args, **kwargs):
        raise AssertionError("plot style must not rerun preprocessing")

    # Patch only after the real baseline step has been applied, so any later
    # refit or resmooth caused by the Plot Editor would fail loudly.
    monkeypatch.setattr(
        preprocessing_module, "fit_linear_baseline", _fail
    )
    monkeypatch.setattr(preprocessing_module, "smooth_savgol", _fail)

    window.plot_editor_panel.set_curve_color(CURVE_RAW, "#abcdef")
    window.plot_editor_panel.set_title("Styled")
    window._set_language("en")
    window._set_language("zh")
    window.plot_editor_panel.set_curve_visible(CURVE_FITTED_BASELINE, True)
    assert len(window.canvas.axes.lines) == 4


def test_plot_editor_settings_never_modify_the_source_file(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    before = sha256(source)
    window = MainWindow()
    window.output_base = tmp_path / "out"
    load_with_windows(window, source)
    apply_baseline(window)
    panel = window.plot_editor_panel

    panel.set_curve_color(CURVE_RAW, "#aabbcc")
    panel.set_curve_linestyle(CURVE_RAW, ":")
    panel.set_x_range(3290.0, 3370.0)
    window._set_language("en")
    window._set_language("zh")
    panel.reset_requested.emit()
    panel.restore_visibility_requested.emit()

    assert sha256(source) == before
