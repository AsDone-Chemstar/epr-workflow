"""M14 headless GUI tests for FTIR difference spectra."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from spectralab.app.gui.app import build_controller  # noqa: E402
from spectralab.app.gui.ftir_translations import FTIR_TECHNIQUE_ID  # noqa: E402
from spectralab.app.gui.i18n import Translator  # noqa: E402
from spectralab.app.gui.main_window import MainWindow  # noqa: E402
from spectralab.app.gui.settings import SettingsService  # noqa: E402
from spectralab.techniques.ftir import ColumnMapping, FTIRImportOptions  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _window(language: str = "zh") -> MainWindow:
    return MainWindow(
        build_controller(),
        Translator(language),
        SettingsService(None),
    )


def _ftir_panel(window: MainWindow):
    index = window.technique_combo.findData(FTIR_TECHNIQUE_ID)
    window.technique_combo.setCurrentIndex(index)
    return window._panels[FTIR_TECHNIQUE_ID]


def _options() -> FTIRImportOptions:
    return FTIRImportOptions(
        mapping=ColumnMapping(
            x=0,
            y=1,
            x_unit="cm^-1",
            y_semantics="absorbance",
        ),
        acquisition_mode="ATR",
    )


def _write_csv(path: Path, rows: list[tuple[float, float]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"{x},{y}" for x, y in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _two_spectra(
    tmp_path: Path,
    *,
    a_rows=None,
    b_rows=None,
) -> tuple[Path, Path]:
    a = _write_csv(
        tmp_path / "a.csv",
        a_rows or [(0.0, 10.0), (1.0, 20.0), (2.0, 30.0), (3.0, 40.0)],
    )
    b = _write_csv(
        tmp_path / "b.csv",
        b_rows or [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0)],
    )
    return a, b


def _import_pair(panel, a: Path, b: Path) -> None:
    options = _options()
    assert panel.import_file(a, options) is True
    assert panel.import_file(b, options) is True


# ---------------------------------------------------------------------------
# UI state
# ---------------------------------------------------------------------------
def test_difference_tab_requires_two_compatible_spectra(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    assert panel.bottom_tabs.count() == 4
    assert panel.bottom_tabs.tabText(2) == "差谱"
    assert panel.bottom_tabs.tabText(3) == "导出"
    assert panel.difference_preview_button.isEnabled() is False

    assert panel.import_file(a, _options()) is True
    assert panel.loaded_dataset_ids == ("a",)
    assert panel.difference_preview_button.isEnabled() is False
    assert panel.difference_b_combo.count() == 0

    assert panel.import_file(b, _options()) is True
    assert panel.loaded_dataset_ids == ("a", "b")
    assert panel.difference_preview_button.isEnabled() is True
    assert panel.difference_a_combo.currentData() != (
        panel.difference_b_combo.currentData()
    )
    window.close()


def test_same_dataset_id_is_not_offered_as_spectrum_b(
    app: QApplication, tmp_path: Path
) -> None:
    first = _write_csv(tmp_path / "one" / "same.csv", [(0.0, 1.0), (1.0, 2.0)])
    second = _write_csv(tmp_path / "two" / "same.csv", [(0.0, 2.0), (1.0, 3.0)])
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(first, _options()) is True
    assert panel.import_file(second, _options()) is True
    assert panel.loaded_dataset_ids == ("same", "same")
    assert panel.difference_a_combo.count() == 2
    assert panel.difference_b_combo.count() == 0
    assert panel.difference_preview_button.isEnabled() is False
    window.close()


def test_apply_requires_a_preview(app: QApplication, tmp_path: Path) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    panel._apply_difference()
    assert panel.difference_applied_result is None
    assert window.status_event.key == "ftir.difference_preview_required"
    window.close()


# ---------------------------------------------------------------------------
# Exact difference
# ---------------------------------------------------------------------------
def test_exact_preview_apply_clear_and_source_integrity(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)

    before = [
        (
            workspace.spectrum.dataset_id,
            workspace.spectrum.axis.values.copy(),
            workspace.spectrum.raw_signal.values.copy(),
            tuple(workspace.session.history),
        )
        for workspace in panel._workspaces
    ]
    panel._preview_difference()
    result = panel.difference_preview_result
    assert result is not None
    np.testing.assert_array_equal(
        result.signal.values,
        np.array([9.0, 18.0, 27.0, 36.0]),
    )
    assert result.axis_match == "exact"
    assert result.dataset_a_id == "a"
    assert result.dataset_b_id == "b"
    assert [line.get_label() for line in panel.axes.lines] == [
        "A：a.csv",
        "B：b.csv",
        "A − B",
    ]

    for workspace, (dataset_id, x_before, y_before, history) in zip(
        panel._workspaces, before
    ):
        assert workspace.spectrum.dataset_id == dataset_id
        np.testing.assert_array_equal(workspace.spectrum.axis.values, x_before)
        np.testing.assert_array_equal(
            workspace.spectrum.raw_signal.values, y_before
        )
        assert tuple(workspace.session.history) == history
    assert panel.processing_session.history == ()

    panel._apply_difference()
    assert panel.difference_preview_result is None
    assert panel.difference_applied_result is not None
    panel._clear_difference_results()
    assert panel.difference_result is None
    assert panel._plot_mode == "normal"
    window.close()


def test_interpolation_preview_shows_original_and_aligned_b(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(
        tmp_path,
        a_rows=[(0.0, 10.0), (2.0, 20.0), (4.0, 30.0), (6.0, 40.0)],
        b_rows=[
            (0.0, 1.0),
            (1.0, 2.0),
            (2.0, 3.0),
            (3.0, 4.0),
            (4.0, 5.0),
            (5.0, 6.0),
            (6.0, 7.0),
        ],
    )
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    panel.difference_axis_match_combo.setCurrentIndex(
        panel.difference_axis_match_combo.findData("interpolate")
    )
    panel._preview_difference()
    result = panel.difference_preview_result
    assert result is not None
    assert result.interpolation is not None
    np.testing.assert_allclose(
        result.interpolation.aligned_b_signal.values,
        [1.0, 3.0, 5.0, 7.0],
    )
    np.testing.assert_allclose(result.signal.values, [9.0, 17.0, 25.0, 33.0])
    labels = [line.get_label() for line in panel.axes.lines]
    assert len(labels) == 4
    assert "线性插值" in labels[2]
    window.close()


def test_parameter_changes_invalidate_preview(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    panel._preview_difference()
    assert panel.difference_preview_result is not None

    panel.difference_source_b_combo.setCurrentIndex(
        panel.difference_source_b_combo.findData("processed")
    )
    assert panel.difference_preview_result is None
    assert panel.difference_apply_button.isEnabled() is False
    assert window.status_event.key == "ftir.difference_preview_cancelled"
    window.close()


def test_dataset_selection_changes_invalidate_preview(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    panel._preview_difference()
    assert panel.difference_preview_result is not None

    panel.difference_a_combo.setCurrentIndex(1)
    assert panel.difference_preview_result is None
    assert panel.difference_apply_button.isEnabled() is False
    window.close()


# ---------------------------------------------------------------------------
# Processed sources and invalidation
# ---------------------------------------------------------------------------
def test_processed_source_history_is_recorded_and_processing_invalidates_result(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)

    panel.dataset_combo.setCurrentIndex(0)
    assert panel.processing_session is panel._workspaces[0].session
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("normalization")
    )
    panel._preview()
    panel._apply()
    assert panel.processing_session.history[0].operation_id == (
        "ftir.normalize.min_max"
    )

    panel.difference_source_a_combo.setCurrentIndex(
        panel.difference_source_a_combo.findData("processed")
    )
    panel._preview_difference()
    result = panel.difference_preview_result
    assert result is not None
    assert result.source_a == "processed"
    assert result.source_operation_history_a == ("ftir.normalize.min_max",)

    panel._apply_difference()
    assert panel.difference_applied_result is not None
    panel._undo()
    assert panel.difference_preview_result is None
    assert panel.difference_applied_result is None
    window.close()


def test_new_import_clears_difference_results(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    c = _write_csv(tmp_path / "c.csv", [(0.0, 5.0), (1.0, 6.0)])
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    panel._preview_difference()
    panel._apply_difference()
    assert panel.difference_applied_result is not None

    assert panel.import_file(c, _options()) is True
    assert panel.difference_preview_result is None
    assert panel.difference_applied_result is None
    window.close()


def test_no_overlap_reports_error_without_creating_result(
    app: QApplication, tmp_path: Path
) -> None:
    a = _write_csv(tmp_path / "a.csv", [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)])
    b = _write_csv(
        tmp_path / "b.csv",
        [(10.0, 1.0), (11.0, 2.0), (12.0, 3.0)],
    )
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    panel.difference_axis_match_combo.setCurrentIndex(
        panel.difference_axis_match_combo.findData("interpolate")
    )
    panel._preview_difference()
    assert panel.difference_preview_result is None
    assert window.status_event.level == "error"
    assert window.status_event.key == "ftir.difference_failed"
    window.close()


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------
def test_failed_difference_preserves_both_sources(
    app: QApplication, tmp_path: Path
) -> None:
    a = _write_csv(tmp_path / "a.csv", [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)])
    b = _write_csv(
        tmp_path / "b.csv",
        [(10.0, 1.0), (11.0, 2.0), (12.0, 3.0)],
    )
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    before = [
        (
            workspace.spectrum.axis.values.copy(),
            workspace.spectrum.raw_signal.values.copy(),
        )
        for workspace in panel._workspaces
    ]
    panel.difference_axis_match_combo.setCurrentIndex(
        panel.difference_axis_match_combo.findData("interpolate")
    )
    panel._preview_difference()
    assert panel.difference_result is None
    for workspace, (x_before, y_before) in zip(panel._workspaces, before):
        np.testing.assert_array_equal(workspace.spectrum.axis.values, x_before)
        np.testing.assert_array_equal(
            workspace.spectrum.raw_signal.values,
            y_before,
        )
    window.close()


def test_difference_tab_restores_the_saved_difference_plot(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    panel._preview_difference()
    panel._apply_difference()

    panel.bottom_tabs.setCurrentWidget(panel.peak_tab)
    panel.bottom_tabs.setCurrentWidget(panel.difference_tab)
    labels = [line.get_label() for line in panel.axes.lines]
    assert labels[-1] == "A − B"
    assert panel._plot_mode == "difference"
    window.close()


def test_language_switch_updates_difference_controls(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window("en")
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    window.set_language("en")

    assert panel.bottom_tabs.tabText(2) == "Difference"
    assert panel.difference_a_label.text() == "Spectrum A"
    assert panel.difference_b_label.text() == "Spectrum B"
    assert panel.difference_preview_button.text() == "Preview difference"
    assert panel.difference_apply_button.text() == "Apply/Save result"
    assert panel.difference_clear_button.text() == "Clear result"
    window.close()
