"""Headless tests for the PySide6 widgets (offscreen platform)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolButton  # noqa: E402

from epr_workflow.gui.controller import load_spectrum, run_batch_processing  # noqa: E402
import epr_workflow.gui.main_window as main_window_module  # noqa: E402
from epr_workflow.gui.main_window import (  # noqa: E402
    LANGUAGE_SETTING_KEY,
    MainWindow,
)

HEADER = "     index           Field [G]        Intensity []\n\n"


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent blocking modal dialogs from hanging the headless test run."""

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


def _make_named_asc(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        HEADER + "1 3280 400.088\n2 3280.1 272.312\n3 3280.2 364.536\n"
        "4 3280.29 -29.2404\n",
        encoding="utf-8",
    )
    return path


def _make_asc(tmp_path: Path) -> Path:
    return _make_named_asc(tmp_path, "sample.ASC")


def _make_settings(tmp_path: Path) -> QSettings:
    """Isolated QSettings file so tests never touch the real preference file."""
    return QSettings(str(tmp_path / "gui_settings.ini"), QSettings.Format.IniFormat)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# Original smoke tests (Simplified Chinese is the default)
# --------------------------------------------------------------------------
def test_window_constructs_and_displays_spectrum(app: QApplication, tmp_path: Path) -> None:
    window = MainWindow()
    view = load_spectrum(_make_asc(tmp_path))

    window._display(view, record=None)

    assert window.metadata_text.toPlainText() != ""
    assert "数据点数：4" in window.metadata_text.toPlainText()
    assert "3280.0000 – 3280.2900 G" in window.metadata_text.toPlainText()
    assert len(window.canvas.axes.lines) == 1


def test_window_handles_unreadable_file_without_crash(
    app: QApplication, tmp_path: Path
) -> None:
    window = MainWindow()
    window._load_and_display(tmp_path / "missing.ASC")

    assert window.metadata_text.toPlainText().startswith("无法读取")
    assert window.cursor_label.text() == "光标：—"


def test_open_buttons_disabled_without_record(app: QApplication, tmp_path: Path) -> None:
    window = MainWindow()
    view = load_spectrum(_make_asc(tmp_path))
    window._display(view, record=None)

    assert not window.open_csv_btn.isEnabled()
    assert not window.open_png_btn.isEnabled()
    assert not window.open_json_btn.isEnabled()


def test_open_buttons_enabled_with_record(app: QApplication, tmp_path: Path) -> None:
    window = MainWindow()
    view = load_spectrum(_make_asc(tmp_path))
    record = {
        "outputs": {
            "csv": str(tmp_path / "a.csv"),
            "figure": str(tmp_path / "a.png"),
            "metadata_json": str(tmp_path / "a.json"),
        }
    }
    window._display(view, record=record)

    assert window.open_csv_btn.isEnabled()
    assert window.open_png_btn.isEnabled()
    assert window.open_json_btn.isEnabled()


# --------------------------------------------------------------------------
# Default language
# --------------------------------------------------------------------------
def test_default_language_is_chinese(app: QApplication) -> None:
    window = MainWindow()

    assert window._language == "zh"
    assert window.windowTitle() == "EPR Workflow — ASC / BES3T 导入与绘图"
    assert window.open_file_btn.text() == "打开数据文件…"
    assert window.language_combo.currentData() == "zh"
    assert window.batch_summary_label.text() == "尚未批量处理"


# --------------------------------------------------------------------------
# Live switching
# --------------------------------------------------------------------------
def test_switch_to_english_updates_existing_widgets(app: QApplication) -> None:
    window = MainWindow()

    window._set_language("en")

    assert window.windowTitle() == "EPR Workflow — ASC / BES3T Import and Plotting"
    assert window.open_file_btn.text() == "Open Dataset…"
    assert window.batch_btn.text() == "Batch Process Folder…"
    assert window.output_btn.text() == "Output Directory…"
    assert window.recursive_check.text() == "Include Subdirectories"
    assert window.overwrite_check.text() == "Allow Overwrite"
    assert window.sample_list_label.text() == "Sample List"
    assert window.metadata_label.text() == "Metadata and Validation"
    assert window.open_csv_btn.text() == "Open CSV"
    assert window.open_png_btn.text() == "Open PNG"
    assert window.open_json_btn.text() == "Open JSON"
    assert window.cursor_label.text() == "Cursor: —"
    assert window.batch_summary_label.text() == "Batch processing not run yet"
    assert window.language_combo.currentData() == "en"

    window._set_language("zh")

    assert window.windowTitle() == "EPR Workflow — ASC / BES3T 导入与绘图"
    assert window.open_file_btn.text() == "打开数据文件…"
    assert window.language_combo.currentData() == "zh"


def test_combo_selection_drives_language_switch(app: QApplication) -> None:
    window = MainWindow()

    index = window.language_combo.findData("en")
    window.language_combo.setCurrentIndex(index)

    assert window._language == "en"
    assert window.windowTitle() == "EPR Workflow — ASC / BES3T Import and Plotting"


def test_switch_updates_metadata_and_plot_without_reload(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow()
    view = load_spectrum(_make_asc(tmp_path))
    window._display(view)

    calls: list[Path] = []

    def _fail_if_reloaded(path):
        calls.append(Path(path))
        raise AssertionError("language switch must not reload the ASC file")

    monkeypatch.setattr(main_window_module, "load_spectrum", _fail_if_reloaded)

    window._set_language("en")

    assert calls == []
    assert len(window.canvas.axes.lines) == 1
    text = window.metadata_text.toPlainText()
    assert "Number of Data Points: 4" in text
    assert "Magnetic Field Range: 3280.0000 – 3280.2900 G" in text
    assert "Field Direction: Strictly increasing" in text
    assert "Signal Statistics:" in text
    assert "Validation Warnings: None" in text
    assert window.canvas.axes.get_xlabel() == "Magnetic field (G)"
    assert window.canvas.axes.get_ylabel() == "Intensity (original units)"
    assert window.canvas.axes.get_title() == "sample - Raw CW-EPR Spectrum"

    window._set_language("zh")

    assert "数据点数：4" in window.metadata_text.toPlainText()
    assert "磁场范围：3280.0000 – 3280.2900 G" in window.metadata_text.toPlainText()
    assert window.canvas.axes.get_xlabel() == "磁场 (G)"


def test_switch_does_not_run_batch_processing(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow()
    source = _make_asc(tmp_path)
    window._display(load_spectrum(source))

    def _fail(*args, **kwargs):
        raise AssertionError("language switch must not run batch processing")

    monkeypatch.setattr(main_window_module, "run_batch_processing", _fail)

    window._set_language("en")
    window._set_language("zh")


def test_switch_preserves_selected_sample_and_batch_results(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    _make_named_asc(input_dir, "a.ASC")
    _make_named_asc(input_dir, "b.ASC")

    window = MainWindow(settings=_make_settings(tmp_path))
    outcome = run_batch_processing(input_dir, output_dir)
    window._populate_samples(outcome)
    window.sample_list.setCurrentRow(1)

    selected_before = window.sample_list.currentRow()
    source_before = window._row_paths[selected_before]
    assert source_before.name == "b.ASC"

    def _fail_if_reloaded(path):
        raise AssertionError(f"language switch must not reload {path}")

    monkeypatch.setattr(main_window_module, "load_spectrum", _fail_if_reloaded)

    window._set_language("en")

    assert window.sample_list.currentRow() == selected_before
    assert window.sample_list.count() == 2
    assert window._row_paths == [input_dir / "a.ASC", input_dir / "b.ASC"]
    assert window._current_view is not None
    assert window._current_view.source == source_before
    assert window.sample_list.item(0).text().startswith("Succeeded")
    assert window.sample_list.item(1).text().startswith("Succeeded")
    summary_text = window.batch_summary_label.text()
    assert "Found: 2 | Succeeded: 2 | Warnings: 0 | Failed: 0" in summary_text
    assert "Overall status: Success" in summary_text
    assert "Summary:" in summary_text

    window._set_language("zh")

    assert window.sample_list.currentRow() == selected_before
    assert window.sample_list.item(0).text().startswith("成功")
    assert "发现 2 | 成功 2 | 有警告 0 | 失败 0" in window.batch_summary_label.text()
    assert "总体状态：成功" in window.batch_summary_label.text()


def test_switch_preserves_cursor_readout(app: QApplication) -> None:
    window = MainWindow()
    window._on_mouse_move(
        SimpleNamespace(inaxes=object(), xdata=3280.1, ydata=123.456)
    )

    assert window.cursor_label.text() == "光标：磁场 3280.1000 G　强度 123.4560"

    window._set_language("en")

    assert (
        window.cursor_label.text()
        == "Cursor: field 3280.1000 G   intensity 123.4560"
    )

    window._set_language("zh")

    assert window.cursor_label.text() == "光标：磁场 3280.1000 G　强度 123.4560"


def test_switch_does_not_modify_source_file(
    app: QApplication, tmp_path: Path
) -> None:
    source = _make_asc(tmp_path)
    before = _sha256(source)
    window = MainWindow()
    window._display(load_spectrum(source))

    window._set_language("en")
    window._set_language("zh")

    assert _sha256(source) == before


# --------------------------------------------------------------------------
# Error and empty states
# --------------------------------------------------------------------------
def test_error_message_is_retranslated(app: QApplication, tmp_path: Path) -> None:
    window = MainWindow()
    window._load_and_display(tmp_path / "missing.ASC")
    assert window.metadata_text.toPlainText().startswith("无法读取")

    window._set_language("en")

    assert window.metadata_text.toPlainText().startswith("Could not read")
    assert window.cursor_label.text() == "Cursor: —"

    window._set_language("zh")

    assert window.metadata_text.toPlainText().startswith("无法读取")


def test_empty_batch_message_is_retranslated(
    app: QApplication, tmp_path: Path
) -> None:
    input_dir = tmp_path / "raw"
    input_dir.mkdir()
    window = MainWindow()
    outcome = run_batch_processing(input_dir, tmp_path / "out")
    window._populate_samples(outcome)

    assert window.metadata_text.toPlainText() == "没有可显示的样品。"

    window._set_language("en")

    assert window.metadata_text.toPlainText() == "No samples to display."


# --------------------------------------------------------------------------
# Dialogs and messages use the selected language
# --------------------------------------------------------------------------
def test_file_dialog_uses_selected_language(
    app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}

    def _fake_dialog(parent, title, directory, file_filter):
        captured["title"] = title
        captured["filter"] = file_filter
        return "", ""

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName", staticmethod(_fake_dialog)
    )
    window = MainWindow()
    window._set_language("en")
    window._choose_single_file()

    assert captured["title"] == "Select an ASC or BES3T DSC File"
    assert captured["filter"].endswith("All Files (*.*)")


def test_overwrite_warning_uses_selected_language(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    _make_named_asc(input_dir, "a.ASC")

    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        staticmethod(lambda parent, title, text, *a, **k: messages.append((title, text))),
    )

    window = MainWindow()
    window.output_base = output_dir
    window._set_language("en")
    window._run_batch(input_dir)  # first run succeeds
    window._run_batch(input_dir)  # second run must be refused

    assert len(messages) == 1
    title, text = messages[0]
    assert title == "Outputs Already Exist"
    assert "Allow Overwrite" in text
    assert "already exists" in text  # core error text, intentionally untranslated


# --------------------------------------------------------------------------
# Language preference persistence
# --------------------------------------------------------------------------
def test_language_preference_is_restored(
    app: QApplication, tmp_path: Path
) -> None:
    settings = _make_settings(tmp_path)
    first = MainWindow(settings=settings)
    assert first._language == "zh"
    first._set_language("en")

    second = MainWindow(settings=settings)

    assert second._language == "en"
    assert second.language_combo.currentData() == "en"
    assert second.windowTitle() == "EPR Workflow — ASC / BES3T Import and Plotting"


def test_invalid_saved_language_falls_back_to_chinese(
    app: QApplication, tmp_path: Path
) -> None:
    settings = _make_settings(tmp_path)
    settings.setValue(LANGUAGE_SETTING_KEY, "fr")
    settings.sync()

    window = MainWindow(settings=settings)

    assert window._language == "zh"
    assert window.windowTitle() == "EPR Workflow — ASC / BES3T 导入与绘图"


def test_window_without_settings_does_not_persist(app: QApplication) -> None:
    stateless = MainWindow()
    assert stateless._language == "zh"
    stateless._set_language("en")
    stateless._set_language("zh")

    # A new stateless window starts from the default, since nothing was saved.
    fresh = MainWindow()
    assert fresh._language == "zh"


# --------------------------------------------------------------------------
# Layout: long English labels must fit the default window width
# --------------------------------------------------------------------------
def test_toolbar_tooltips_follow_language(app: QApplication) -> None:
    window = MainWindow()
    buttons = {
        button.defaultAction().text(): button
        for button in window.toolbar.findChildren(QToolButton)
        if button.defaultAction() is not None
    }
    assert buttons["Home"].toolTip() == "复位到初始视图"

    window._set_language("en")

    assert buttons["Home"].toolTip() == "Reset original view"
    assert buttons["Pan"].toolTip() == (
        "Left button pans, Right button zooms\nx/y fixes axis, CTRL fixes aspect"
    )
    assert buttons["Save"].toolTip() == "Save the figure"

    window._set_language("zh")

    assert buttons["Home"].toolTip() == "复位到初始视图"
    assert buttons["Save"].toolTip() == "保存图像"


def test_controls_layout_contains_file_and_option_rows(app: QApplication) -> None:
    window = MainWindow()
    controls = window.centralWidget().layout().itemAt(0).layout()
    assert controls.count() == 2

    file_row = controls.itemAt(0).layout()
    file_widgets = [file_row.itemAt(i).widget() for i in range(file_row.count())]
    for widget in (
        window.open_file_btn,
        window.batch_btn,
        window.output_btn,
        window.output_edit,
    ):
        assert widget in file_widgets

    options_row = controls.itemAt(1).layout()
    option_widgets = [options_row.itemAt(i).widget() for i in range(options_row.count())]
    for widget in (
        window.recursive_check,
        window.overwrite_check,
        window.language_label,
        window.language_combo,
    ):
        assert widget in option_widgets


def test_english_labels_fit_default_window(app: QApplication) -> None:
    window = MainWindow()
    window._set_language("en")

    file_row = [
        window.open_file_btn,
        window.batch_btn,
        window.output_btn,
        window.output_edit,
    ]
    file_row_width = sum(w.sizeHint().width() for w in file_row)
    assert file_row_width < 1100

    options_row = [
        window.recursive_check,
        window.overwrite_check,
        window.language_label,
        window.language_combo,
    ]
    options_row_width = sum(w.sizeHint().width() for w in options_row)
    assert options_row_width < 1100
    assert window.minimumSizeHint().width() <= 1100


def test_chinese_plot_labels_use_cjk_font(
    app: QApplication, tmp_path: Path
) -> None:
    window = MainWindow()
    if window.canvas.cjk_font is None:  # no CJK font installed on this machine
        pytest.skip("no CJK-capable font available to matplotlib")
    window._display(load_spectrum(_make_asc(tmp_path)))

    family = window.canvas.axes.xaxis.label.get_fontfamily()
    assert window.canvas.cjk_font in family

    window._set_language("en")

    assert window.canvas.cjk_font not in window.canvas.axes.xaxis.label.get_fontfamily()
