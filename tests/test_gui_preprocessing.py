"""Headless GUI tests for the baseline-correction workflow."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

import numpy as np  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import epr_workflow.gui.main_window as main_window_module  # noqa: E402
from epr_workflow.gui.controller import load_spectrum  # noqa: E402
from epr_workflow.gui.main_window import MainWindow  # noqa: E402
from epr_workflow.preprocessing import (  # noqa: E402
    BASELINE_OPERATION,
    INPUT_CURRENT,
    INPUT_RAW,
    SAVGOL_OPERATION,
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
        intensity = 2.0 * field + 5.0 + peak * np.exp(-((field - 3330.0) / 5.0) ** 2)
        rows.append(f"{i + 1} {field!r} {float(intensity)!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_window(window: MainWindow, path: Path) -> None:
    window._load_and_display(path)
    window.preprocessing_panel.set_values(3280.0, 3284.0, 3376.0, 3380.0)


def select_savgol(
    window: MainWindow,
    *,
    window_length: int = 9,
    polyorder: int = 3,
    input_source: str = INPUT_CURRENT,
) -> None:
    panel = window.preprocessing_panel
    panel.set_operation(SAVGOL_OPERATION)
    panel.set_savgol_values(window_length, polyorder)
    panel.set_smoothing_input_source(input_source)


def status(window: MainWindow) -> str:
    return window.preprocessing_panel.status_label.text()


def metadata(window: MainWindow) -> str:
    return window.metadata_text.toPlainText()


# --------------------------------------------------------------------------
# Panel state
# --------------------------------------------------------------------------
def test_panel_disabled_without_data(app: QApplication) -> None:
    window = MainWindow()

    assert not window.preprocessing_panel.preview_btn.isEnabled()
    assert not window.preprocessing_panel.apply_btn.isEnabled()
    assert status(window) == "状态：原始数据"


def test_no_windows_selected_by_default(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        staticmethod(lambda parent, title, text, *a, **k: messages.append((title, text))),
    )
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window._load_and_display(source)
    panel = window.preprocessing_panel

    assert panel.values() == (None, None, None, None)
    assert panel.has_selection() is False
    assert panel.left_start.text() == ""
    assert status(window) == "状态：原始数据"

    panel.preview_requested.emit()

    assert messages[-1][0] == "预处理参数无效"
    assert "请先选择基线区间" in messages[-1][1]
    assert len(window.canvas.axes.lines) == 1
    assert window._session is not None and window._session.steps == ()
    assert window._preview_result is None

    panel.set_values(3280.0, 3284.0, 3376.0, 3380.0)
    assert panel.has_selection() is True
    panel.preview_requested.emit()
    assert len(window.canvas.axes.lines) == 3


def test_panel_enabled_after_load(app: QApplication, tmp_path: Path) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()

    load_window(window, source)

    assert window.preprocessing_panel.preview_btn.isEnabled()
    assert window.preprocessing_panel.apply_btn.isEnabled()
    assert not window.preprocessing_panel.undo_btn.isEnabled()
    assert not window.preprocessing_panel.export_btn.isEnabled()
    assert status(window) == "状态：原始数据"
    assert len(window.canvas.axes.lines) == 1


# --------------------------------------------------------------------------
# Preview
# --------------------------------------------------------------------------
def test_preview_shows_three_curves_and_writes_nothing(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    raw_before = window._current_view.data["intensity"].to_numpy().copy()
    files_before = set(tmp_path.rglob("*"))

    window.preprocessing_panel.preview_requested.emit()

    assert len(window.canvas.axes.lines) == 3
    assert status(window) == "状态：预览（未应用）"
    assert window._preview_result is not None
    assert window._preview_result.is_preview is True
    assert window._session is not None and not window._session.has_steps
    assert set(tmp_path.rglob("*")) == files_before
    np.testing.assert_array_equal(
        window._current_view.data["intensity"].to_numpy(), raw_before
    )
    text = metadata(window)
    assert "模式：预览（未应用，未写入文件）" in text
    assert "线性拟合：" in text
    assert "R² 只描述窗口内直线拟合的贴合程度" in text
    assert not window.preprocessing_panel.export_btn.isEnabled()


def test_cancel_preview_restores_raw_without_history(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    files_before = set(tmp_path.rglob("*"))
    window.preprocessing_panel.preview_requested.emit()
    assert window.preprocessing_panel.cancel_btn.isEnabled()

    window.preprocessing_panel.cancel_preview_requested.emit()

    assert window._preview_result is None
    assert window._session is not None and window._session.steps == ()
    assert len(window.canvas.axes.lines) == 1
    assert status(window) == "状态：原始数据"
    assert set(tmp_path.rglob("*")) == files_before
    assert not window.preprocessing_panel.cancel_btn.isEnabled()


def test_cancel_preview_returns_to_applied_state(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    window.preprocessing_panel.apply_requested.emit()
    window.preprocessing_panel.set_values(3280.0, 3286.0, 3374.0, 3380.0)
    window.preprocessing_panel.preview_requested.emit()
    assert window._preview_result is not None

    window.preprocessing_panel.cancel_preview_requested.emit()

    assert window._preview_result is None
    assert window._session is not None and len(window._session.steps) == 1
    assert len(window.canvas.axes.lines) == 3
    assert status(window) == "状态：已应用 1 步"
    assert "模式：已应用 1 步" in metadata(window)


def test_changing_parameters_invalidates_preview(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    window.preprocessing_panel.preview_requested.emit()
    assert len(window.canvas.axes.lines) == 3

    window.preprocessing_panel.left_end.setText("3285.0000")

    assert window._preview_result is None
    assert len(window.canvas.axes.lines) == 1
    assert status(window) == "状态：原始数据"


# --------------------------------------------------------------------------
# Apply / undo / reset
# --------------------------------------------------------------------------
def test_apply_commits_step_and_keeps_raw_data(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    before = sha256(source)
    window = MainWindow()
    load_window(window, source)
    raw_before = window._current_view.data["intensity"].to_numpy().copy()

    window.preprocessing_panel.apply_requested.emit()

    assert window._session is not None
    assert len(window._session.steps) == 1
    assert status(window) == "状态：已应用 1 步"
    assert len(window.canvas.axes.lines) == 3
    assert window.preprocessing_panel.undo_btn.isEnabled()
    assert window.preprocessing_panel.reset_btn.isEnabled()
    assert window.preprocessing_panel.export_btn.isEnabled()
    np.testing.assert_array_equal(
        window._current_view.data["intensity"].to_numpy(), raw_before
    )
    assert sha256(source) == before
    assert "原始数据未被修改" in metadata(window)


def test_undo_and_reset_return_to_raw(app: QApplication, tmp_path: Path) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    window.preprocessing_panel.apply_requested.emit()

    window.preprocessing_panel.undo_requested.emit()

    assert window._session is not None and window._session.steps == ()
    assert len(window.canvas.axes.lines) == 1
    assert status(window) == "状态：原始数据"

    window.preprocessing_panel.apply_requested.emit()
    window.preprocessing_panel.reset_requested.emit()

    assert window._session.steps == ()
    assert len(window.canvas.axes.lines) == 1
    assert not window.preprocessing_panel.undo_btn.isEnabled()


def test_preview_then_apply_uses_preview_parameters(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    window.preprocessing_panel.preview_requested.emit()
    window.preprocessing_panel.left_end.setText("3284.0000")  # unchanged value

    window.preprocessing_panel.apply_requested.emit()

    assert window._session is not None
    assert len(window._session.steps) == 1
    assert window._preview_result is None
    assert status(window) == "状态：已应用 1 步"


# --------------------------------------------------------------------------
# Validation errors
# --------------------------------------------------------------------------
def test_invalid_window_shows_translated_warning(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        staticmethod(lambda parent, title, text, *a, **k: messages.append((title, text))),
    )
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    window.preprocessing_panel.left_start.setText("3300.0000")

    window.preprocessing_panel.preview_requested.emit()

    assert len(window.canvas.axes.lines) == 1
    assert window._session is not None and window._session.steps == ()
    assert messages[-1][0] == "预处理参数无效"
    assert "起点必须小于终点" in messages[-1][1]

    window._set_language("en")
    window.preprocessing_panel.preview_requested.emit()

    assert messages[-1][0] == "Invalid Preprocessing Parameters"
    assert "must be less than" in messages[-1][1]


def test_window_with_too_few_points_is_reported(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        staticmethod(lambda parent, title, text, *a, **k: messages.append((title, text))),
    )
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    window.preprocessing_panel.left_end.setText("3280.5000")

    window.preprocessing_panel.preview_requested.emit()

    assert "只包含" in messages[-1][1]
    assert "至少需要 3 个" in messages[-1][1]


# --------------------------------------------------------------------------
# Language switching
# --------------------------------------------------------------------------
def test_language_switch_preserves_applied_state(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    window.preprocessing_panel.apply_requested.emit()
    values_before = window.preprocessing_panel.values()

    window._set_language("en")

    assert window._session is not None and len(window._session.steps) == 1
    assert window.preprocessing_panel.values() == values_before
    assert status(window) == "Status: 1 step(s) applied"
    assert window.preprocessing_panel.preview_btn.text() == "Preview"
    assert window.preprocessing_panel.export_btn.text() == "Export Processed Results…"
    text = metadata(window)
    assert "Preprocessing:" in text
    assert "Linear fit:" in text
    assert "Baseline windows:" in text
    assert "R² only describes" in text
    assert len(window.canvas.axes.lines) == 3
    assert window.canvas.axes.get_title() == "sample - Linear Baseline Corrected CW-EPR Spectrum"

    window._set_language("zh")

    assert len(window._session.steps) == 1
    assert status(window) == "状态：已应用 1 步"
    assert "线性拟合：" in metadata(window)


def test_language_switch_preserves_preview(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    window.preprocessing_panel.preview_requested.emit()

    window._set_language("en")

    assert window._preview_result is not None
    assert len(window.canvas.axes.lines) == 3
    assert status(window) == "Status: preview (not applied)"
    assert "Mode: preview" in metadata(window)
    assert window.canvas.axes.get_title() == "sample - Baseline Correction Preview"


def test_language_switch_does_not_refit_or_reapply(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import epr_workflow.preprocessing as preprocessing_module

    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    window.preprocessing_panel.apply_requested.emit()
    panel = window.preprocessing_panel
    panel.set_values(3280.0, 3286.0, 3374.0, 3380.0)
    panel.preview_requested.emit()
    steps_before = len(window._session.steps)

    def _fail_if_refit(*args, **kwargs):
        raise AssertionError("language switch must not refit the baseline")

    monkeypatch.setattr(
        preprocessing_module, "fit_linear_baseline", _fail_if_refit
    )

    window._set_language("en")
    window._set_language("zh")

    assert window._session is not None
    assert len(window._session.steps) == steps_before == 1
    assert window._preview_result is not None
    assert len(window.canvas.axes.lines) == 3


def test_cursor_readout_marks_corrected_data(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    event = type(
        "Event", (), {"inaxes": object(), "xdata": 3330.0, "ydata": 10.0}
    )()
    window._on_mouse_move(event)
    assert "（校正后）" not in window.cursor_label.text()

    window.preprocessing_panel.apply_requested.emit()
    # The y value at a field point changes after correction, so the stale
    # cursor readout is cleared rather than relabelled.
    assert "校正后" not in window.cursor_label.text()

    window._on_mouse_move(event)
    assert "（校正后）" in window.cursor_label.text()
    window._set_language("en")
    assert "(corrected)" in window.cursor_label.text()


# --------------------------------------------------------------------------
# Per-file sessions
# --------------------------------------------------------------------------
def test_switching_samples_keeps_each_file_session(
    app: QApplication, tmp_path: Path
) -> None:
    first = write_asc(tmp_path / "a.ASC")
    second = write_asc(tmp_path / "b.ASC")
    window = MainWindow()
    load_window(window, first)
    window.preprocessing_panel.apply_requested.emit()

    window._load_and_display(second)
    assert window._session is not None
    assert window._session.steps == ()
    assert len(window.canvas.axes.lines) == 1

    window._load_and_display(first)
    assert window._session is not None
    assert len(window._session.steps) == 1
    assert len(window.canvas.axes.lines) == 3
    assert window.preprocessing_panel.values() == (
        3280.0,
        3284.0,
        3376.0,
        3380.0,
    )


def test_changed_source_discards_stale_session(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    window.preprocessing_panel.apply_requested.emit()
    assert len(window._session.steps) == 1

    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    window._load_and_display(source)

    assert window._session is not None
    assert window._session.steps == ()
    assert len(window.canvas.axes.lines) == 1


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
def test_export_writes_files_and_updates_open_buttons(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    before = sha256(source)
    window = MainWindow()
    window.output_base = tmp_path / "out"
    load_window(window, source)
    window.preprocessing_panel.apply_requested.emit()

    window.preprocessing_panel.export_requested.emit()

    csv_path = tmp_path / "out" / "tables" / "sample_baseline.csv"
    assert csv_path.exists()
    assert (tmp_path / "out" / "figures" / "sample_baseline.png").exists()
    metadata_path = tmp_path / "out" / "logs" / "sample_baseline_metadata.json"
    assert metadata_path.exists()
    assert status(window) == "状态：已应用 1 步，已导出"
    assert window._selected_outputs["csv"] == str(csv_path.resolve())
    assert window.open_csv_btn.isEnabled()
    assert window.open_png_btn.isEnabled()
    assert window.open_json_btn.isEnabled()
    assert "已导出：" in metadata(window)
    assert sha256(source) == before

    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert payload["preprocessing"]["applied"] is True
    assert payload["processing"]["applied_in_this_run"]["baseline_correction"] is True

    window._set_language("en")
    assert window._selected_outputs["csv"] == str(csv_path.resolve())
    assert status(window) == "Status: 1 step(s) applied, exported"

    window.preprocessing_panel.reset_requested.emit()

    assert not window.open_csv_btn.isEnabled()
    assert status(window) == "Status: raw data"


def test_export_refuses_overwrite_until_allowed(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        staticmethod(lambda parent, title, text, *a, **k: messages.append((title, text))),
    )
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window.output_base = tmp_path / "out"
    load_window(window, source)
    window.preprocessing_panel.apply_requested.emit()
    window.preprocessing_panel.export_requested.emit()
    csv_path = tmp_path / "out" / "tables" / "sample_baseline.csv"
    first_hash = sha256(csv_path)

    window.preprocessing_panel.export_requested.emit()

    assert messages[-1][0] == "已存在输出"
    assert "允许覆盖" in messages[-1][1]
    assert sha256(csv_path) == first_hash

    window.overwrite_check.setChecked(True)
    window.preprocessing_panel.export_requested.emit()

    assert status(window) == "状态：已应用 1 步，已导出"


def test_export_is_impossible_for_preview_only(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window.output_base = tmp_path / "out"
    load_window(window, source)
    window.preprocessing_panel.preview_requested.emit()

    assert not window.preprocessing_panel.export_btn.isEnabled()
    window.preprocessing_panel.export_requested.emit()  # defensive no-op

    assert not (tmp_path / "out" / "tables").exists()


# --------------------------------------------------------------------------
# Raw-data integrity
# --------------------------------------------------------------------------
def test_full_workflow_does_not_modify_sources(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    before = sha256(source)
    window = MainWindow()
    window.output_base = tmp_path / "out"
    load_window(window, source)

    window.preprocessing_panel.preview_requested.emit()
    window.preprocessing_panel.apply_requested.emit()
    window.preprocessing_panel.undo_requested.emit()
    window.preprocessing_panel.apply_requested.emit()
    window.preprocessing_panel.export_requested.emit()
    window.preprocessing_panel.reset_requested.emit()
    window._set_language("en")
    window._set_language("zh")

    assert sha256(source) == before
    view = load_spectrum(source)
    assert len(view.data) == 101


# --------------------------------------------------------------------------
# Savitzky-Golay GUI workflow
# --------------------------------------------------------------------------
def test_smoothing_is_off_by_default(app: QApplication, tmp_path: Path) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)

    panel = window.preprocessing_panel
    assert panel.selected_operation() == BASELINE_OPERATION
    assert panel.smoothing_widget.isHidden() is True
    assert panel.baseline_widget.isHidden() is False
    assert window._session is not None and window._session.steps == ()
    assert window._preview_result is None
    assert status(window) == "状态：原始数据"


def test_switching_to_smoothing_shows_parameters(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window._load_and_display(source)

    select_savgol(window)

    panel = window.preprocessing_panel
    assert panel.selected_operation() == SAVGOL_OPERATION
    assert panel.smoothing_widget.isHidden() is False
    assert panel.baseline_widget.isHidden() is True
    assert panel.savgol_values() == (9, 3)
    assert panel.smoothing_input_source() == INPUT_CURRENT


def test_smoothing_preview_shows_raw_smoothed_and_difference(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window._load_and_display(source)
    select_savgol(window)
    files_before = set(tmp_path.rglob("*"))
    raw_before = window._current_view.data["intensity"].to_numpy().copy()

    window.preprocessing_panel.preview_requested.emit()

    assert len(window.canvas.axes.lines) == 3
    legend = window.canvas.axes.get_legend()
    labels = [text.get_text() for text in legend.get_texts()]
    assert "原始" in labels
    assert "平滑后" in labels
    assert "差异（原始 − 处理后）" in labels
    assert window._preview_result is not None
    assert window._preview_result.operations == (SAVGOL_OPERATION,)
    assert status(window) == "状态：预览（未应用）"
    assert set(tmp_path.rglob("*")) == files_before
    np.testing.assert_array_equal(
        window._current_view.data["intensity"].to_numpy(), raw_before
    )
    text = metadata(window)
    assert "处理顺序：" in text
    assert "Savitzky–Golay 平滑" in text
    assert "窗口长度 9，多项式阶数 3" in text
    assert "平滑会改变峰高" in text
    assert not window.preprocessing_panel.export_btn.isEnabled()


def test_invalid_even_window_shows_translated_warning(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        staticmethod(lambda parent, title, text, *a, **k: messages.append((title, text))),
    )
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window._load_and_display(source)
    select_savgol(window)
    window.preprocessing_panel.window_length_spin.setValue(4)

    window.preprocessing_panel.preview_requested.emit()

    assert messages[-1][0] == "预处理参数无效"
    assert "窗口长度必须为奇数：4" in messages[-1][1]
    assert len(window.canvas.axes.lines) == 1
    assert window._session is not None and window._session.steps == ()
    assert window._preview_result is None

    window._set_language("en")
    window.preprocessing_panel.preview_requested.emit()

    assert messages[-1][0] == "Invalid Preprocessing Parameters"
    assert "window_length must be odd" in messages[-1][1]


def test_smoothing_apply_undo_reset_and_raw_integrity(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    before = sha256(source)
    window = MainWindow()
    window._load_and_display(source)
    select_savgol(window)
    raw_before = window._current_view.data["intensity"].to_numpy().copy()

    window.preprocessing_panel.apply_requested.emit()

    assert window._session is not None
    assert window._session.operations == (SAVGOL_OPERATION,)
    assert status(window) == "状态：已应用 1 步"
    assert len(window.canvas.axes.lines) == 3
    assert window.preprocessing_panel.export_btn.isEnabled()
    np.testing.assert_array_equal(
        window._current_view.data["intensity"].to_numpy(), raw_before
    )
    assert sha256(source) == before

    window.preprocessing_panel.undo_requested.emit()

    assert window._session.operations == ()
    assert len(window.canvas.axes.lines) == 1
    assert status(window) == "状态：原始数据"

    window.preprocessing_panel.apply_requested.emit()
    window.preprocessing_panel.reset_requested.emit()

    assert window._session.operations == ()
    assert len(window.canvas.axes.lines) == 1
    assert sha256(source) == before


def test_cancel_smoothing_preview_restores_raw(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window._load_and_display(source)
    select_savgol(window)
    window.preprocessing_panel.preview_requested.emit()
    assert window._preview_result is not None

    window.preprocessing_panel.cancel_preview_requested.emit()

    assert window._preview_result is None
    assert window._session is not None and window._session.steps == ()
    assert len(window.canvas.axes.lines) == 1
    assert status(window) == "状态：原始数据"


def test_smoothing_raw_input_is_ordered_before_baseline(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    load_window(window, source)
    window.preprocessing_panel.apply_requested.emit()
    select_savgol(window, input_source=INPUT_RAW)

    window.preprocessing_panel.preview_requested.emit()
    window.preprocessing_panel.apply_requested.emit()

    assert window._session is not None
    assert window._session.operations == (
        SAVGOL_OPERATION,
        BASELINE_OPERATION,
    )
    text = metadata(window)
    assert "处理顺序：" in text
    assert text.index("Savitzky–Golay 平滑") < text.index("线性基线校正")
    assert "平滑作用于原始数据并置于已有步骤之前" in text
    assert status(window) == "状态：已应用 2 步"


def test_language_switch_preserves_smoothing_state_and_parameters(
    app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import epr_workflow.preprocessing as preprocessing_module

    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window._load_and_display(source)
    select_savgol(window, window_length=11, polyorder=2)
    window.preprocessing_panel.apply_requested.emit()
    panel = window.preprocessing_panel

    def _fail_if_resmoothed(*args, **kwargs):
        raise AssertionError("language switch must not re-run smoothing")

    monkeypatch.setattr(
        preprocessing_module, "smooth_savgol", _fail_if_resmoothed
    )

    window._set_language("en")

    assert window._session is not None
    assert window._session.operations == (SAVGOL_OPERATION,)
    assert panel.selected_operation() == SAVGOL_OPERATION
    assert panel.savgol_values() == (11, 2)
    assert panel.smoothing_input_source() == INPUT_CURRENT
    assert panel.method_combo.currentText() == "Savitzky–Golay smoothing"
    assert panel.window_length_label.text() == "Window length"
    assert status(window) == "Status: 1 step(s) applied"
    assert "Savitzky–Golay smoothing" in metadata(window)
    assert len(window.canvas.axes.lines) == 3
    assert window._preview_result is None

    window._set_language("zh")

    assert panel.savgol_values() == (11, 2)
    assert status(window) == "状态：已应用 1 步"


def test_smoothing_export_writes_smoothed_files(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    before = sha256(source)
    window = MainWindow()
    window.output_base = tmp_path / "out"
    window._load_and_display(source)
    select_savgol(window)
    window.preprocessing_panel.apply_requested.emit()

    window.preprocessing_panel.export_requested.emit()

    csv_path = tmp_path / "out" / "tables" / "sample_smoothed.csv"
    metadata_path = tmp_path / "out" / "logs" / "sample_smoothed_metadata.json"
    assert csv_path.exists()
    assert (tmp_path / "out" / "figures" / "sample_smoothed.png").exists()
    assert metadata_path.exists()
    assert window._selected_outputs["csv"] == str(csv_path.resolve())
    assert window.open_csv_btn.isEnabled()
    assert status(window) == "状态：已应用 1 步，已导出"
    assert sha256(source) == before

    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert payload["data_kind"] == "smoothed"
    assert payload["processing"]["applied_in_this_run"]["smoothing"] is True
    assert payload["preprocessing"]["step_order"] == ["savitzky_golay"]


def test_mixed_baseline_and_smoothing_export(
    app: QApplication, tmp_path: Path
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    window = MainWindow()
    window.output_base = tmp_path / "out"
    load_window(window, source)
    window.preprocessing_panel.apply_requested.emit()
    select_savgol(window, input_source=INPUT_CURRENT)
    window.preprocessing_panel.apply_requested.emit()

    window.preprocessing_panel.export_requested.emit()

    csv_path = tmp_path / "out" / "tables" / "sample_baseline_smoothed.csv"
    metadata_path = (
        tmp_path / "out" / "logs" / "sample_baseline_smoothed_metadata.json"
    )
    assert csv_path.exists()
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert payload["data_kind"] == "baseline_corrected_and_smoothed"
    assert payload["preprocessing"]["step_order"] == [
        "linear_baseline",
        "savitzky_golay",
    ]
    assert status(window) == "状态：已应用 2 步，已导出"


def test_switching_samples_restores_smoothing_parameters(
    app: QApplication, tmp_path: Path
) -> None:
    first = write_asc(tmp_path / "a.ASC")
    second = write_asc(tmp_path / "b.ASC")
    window = MainWindow()
    window._load_and_display(first)
    select_savgol(window, window_length=7, polyorder=2)
    window.preprocessing_panel.apply_requested.emit()

    window._load_and_display(second)
    assert window._session is not None and window._session.steps == ()

    window._load_and_display(first)

    assert window._session is not None
    assert window._session.operations == (SAVGOL_OPERATION,)
    assert window.preprocessing_panel.selected_operation() == SAVGOL_OPERATION
    assert window.preprocessing_panel.savgol_values() == (7, 2)
    assert len(window.canvas.axes.lines) == 3
