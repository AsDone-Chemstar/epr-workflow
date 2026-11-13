"""M15 headless GUI tests for FTIR export."""

from __future__ import annotations

import json
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
from spectralab.core.errors import OutputExistsError  # noqa: E402
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
        atr_correction_status="not_applied",
    )


def _write_csv(path: Path, rows: list[tuple[float, float]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"{x},{y}" for x, y in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _two_spectra(tmp_path: Path):
    a = _write_csv(
        tmp_path / "a.csv",
        [(0.0, 10.0), (1.0, 20.0), (2.0, 30.0), (3.0, 40.0)],
    )
    b = _write_csv(
        tmp_path / "b.csv",
        [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0)],
    )
    return a, b


def _import_pair(panel, a: Path, b: Path) -> None:
    options = _options()
    assert panel.import_file(a, options) is True
    assert panel.import_file(b, options) is True


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# UI and programmatic export
# ---------------------------------------------------------------------------
def test_export_tab_and_controls(app: QApplication, tmp_path: Path) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    assert panel.bottom_tabs.count() == 4
    assert panel.bottom_tabs.tabText(3) == "导出"
    assert panel.export_button.isEnabled() is False

    assert panel.import_file(a, _options()) is True
    assert panel.export_button.isEnabled() is True
    assert panel.export_source_combo.count() == 2
    assert panel.export_format_combo.count() == 3
    assert panel.export_overwrite_check.isChecked() is False
    window.close()


def test_raw_csv_json_png_export_through_panel(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    source = panel.source_spectrum
    x_before = source.axis.values.copy()
    y_before = source.raw_signal.values.copy()

    out = tmp_path / "out"
    csv_paths = panel.export_current_spectrum(
        out / "raw.csv",
        export_format="csv",
        source="raw",
    )
    json_paths = panel.export_current_spectrum(
        out / "raw.json",
        export_format="json",
        source="raw",
    )
    png_paths = panel.export_current_spectrum(
        out / "raw.png",
        export_format="png",
        source="raw",
    )
    assert len(csv_paths) == 2
    assert csv_paths[0].exists()
    assert csv_paths[1].exists()
    assert json_paths[0].exists()
    assert png_paths[0].exists()
    assert _json(json_paths[0])["export"]["source_selection"] == "raw"
    assert _json(csv_paths[1])["csv"]["columns"] == ["x", "y"]
    np.testing.assert_array_equal(source.axis.values, x_before)
    np.testing.assert_array_equal(source.raw_signal.values, y_before)
    window.close()


def test_processed_export_uses_current_processed_state(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    panel.dataset_combo.setCurrentIndex(0)
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("normalization")
    )
    panel._preview()
    panel._apply()
    processed = panel.processing_session.current

    path = panel.export_current_spectrum(
        tmp_path / "out" / "processed.json",
        export_format="json",
        source="processed",
    )[0]
    document = _json(path)
    assert document["export"]["source_selection"] == "processed"
    assert document["processing"]["operation_ids"] == [
        "ftir.normalize.min_max"
    ]
    np.testing.assert_allclose(document["signal"]["values"], processed.signal.values)
    assert panel.processing_session.history[0].operation_id == (
        "ftir.normalize.min_max"
    )
    window.close()


def test_difference_export_through_panel_exact_and_interpolated(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    panel._preview_difference()
    assert panel.difference_preview_result is not None

    csv_paths = panel.export_saved_difference(
        tmp_path / "out" / "difference.csv",
        export_format="csv",
    )
    json_paths = panel.export_saved_difference(
        tmp_path / "out" / "difference.json",
        export_format="json",
    )
    png_paths = panel.export_saved_difference(
        tmp_path / "out" / "difference.png",
        export_format="png",
    )
    assert csv_paths[0].exists()
    assert csv_paths[1].exists()
    assert json_paths[0].exists()
    assert png_paths[0].exists()
    document = _json(json_paths[0])
    assert document["export"]["axis_match"] == "exact"
    assert document["export"]["result_role"] == "preview"
    assert document["sources"]["a"]["dataset_id"] == "a"
    assert document["sources"]["b"]["dataset_id"] == "b"
    assert panel.difference_preview_result is not None
    window.close()


def test_difference_interpolation_export_uses_aligned_values(
    app: QApplication, tmp_path: Path
) -> None:
    a = _write_csv(
        tmp_path / "a.csv",
        [(0.0, 10.0), (2.0, 20.0), (4.0, 30.0), (6.0, 40.0)],
    )
    b = _write_csv(
        tmp_path / "b.csv",
        [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0), (4.0, 5.0), (5.0, 6.0), (6.0, 7.0)],
    )
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    panel.difference_axis_match_combo.setCurrentIndex(
        panel.difference_axis_match_combo.findData("interpolate")
    )
    panel._preview_difference()
    path = panel.export_saved_difference(
        tmp_path / "out" / "interp.json",
        export_format="json",
    )[0]
    document = _json(path)
    assert document["interpolation"]["extrapolation"] == "none"
    assert document["difference"]["b_values"] == [1.0, 3.0, 5.0, 7.0]
    assert document["difference"]["difference_values"] == [
        9.0,
        17.0,
        25.0,
        33.0,
    ]
    window.close()


# ---------------------------------------------------------------------------
# Overwrite, errors, state integrity
# ---------------------------------------------------------------------------
def test_overwrite_protection_and_explicit_override(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    target = tmp_path / "out" / "existing.json"
    target.parent.mkdir(parents=True)
    target.write_text("sentinel\n", encoding="utf-8")

    with pytest.raises(OutputExistsError):
        panel.export_current_spectrum(
            target,
            export_format="json",
            source="raw",
            overwrite=False,
        )
    assert target.read_text(encoding="utf-8") == "sentinel\n"

    panel.export_current_spectrum(
        target,
        export_format="json",
        source="raw",
        overwrite=True,
    )
    assert _json(target)["export"]["source_selection"] == "raw"
    window.close()


def test_gui_export_reports_success_and_failure(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    target = tmp_path / "out" / "button.json"
    panel._choose_export_path = lambda *args, **kwargs: target
    panel.export_format_combo.setCurrentIndex(
        panel.export_format_combo.findData("json")
    )
    panel.export_source_combo.setCurrentIndex(
        panel.export_source_combo.findData("raw")
    )
    panel._export_spectrum()
    assert target.exists()
    assert window.status_event.key == "ftir.export_completed"
    assert "Exported" in panel.export_status_label.text() or "已导出" in (
        panel.export_status_label.text()
    )

    panel._choose_export_path = lambda *args, **kwargs: target
    panel._export_spectrum()
    assert window.status_event.level == "error"
    assert window.status_event.key == "ftir.export_failed"
    assert panel.export_status_label.text()
    window.close()


def test_difference_export_requires_a_result(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    assert panel.difference_export_button.isEnabled() is False
    panel._choose_export_path = lambda *args, **kwargs: tmp_path / "out" / "none.json"
    panel.difference_export_format_combo.setCurrentIndex(
        panel.difference_export_format_combo.findData("json")
    )
    panel._export_difference()
    assert window.status_event.level == "error"
    assert window.status_event.key == "ftir.export_failed"
    assert panel.difference_export_status_label.text()
    window.close()


def test_export_does_not_modify_processing_peak_or_difference_state(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window()
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    panel.dataset_combo.setCurrentIndex(0)
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("normalization")
    )
    panel._preview()
    panel._apply()
    panel._preview_peaks()
    panel._preview_difference()
    history = tuple(
        record.operation_id for record in panel.processing_session.history
    )
    peak_result = panel.peak_result
    difference_result = panel.difference_result

    panel.export_current_spectrum(
        tmp_path / "out" / "state.csv",
        export_format="csv",
        source="processed",
    )
    panel.export_saved_difference(
        tmp_path / "out" / "state.json",
        export_format="json",
    )

    assert tuple(
        record.operation_id for record in panel.processing_session.history
    ) == history
    assert panel.peak_result is peak_result
    assert panel.difference_result is difference_result
    window.close()


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------
def test_language_switch_updates_export_controls(
    app: QApplication, tmp_path: Path
) -> None:
    a, b = _two_spectra(tmp_path)
    window = _window("en")
    panel = _ftir_panel(window)
    _import_pair(panel, a, b)
    window.set_language("en")

    assert panel.bottom_tabs.tabText(3) == "Export"
    assert panel.export_source_label.text() == "Export data"
    assert panel.export_format_label.text() == "Export format"
    assert panel.export_button.text() == "Export current spectrum…"
    assert panel.export_overwrite_check.text() == (
        "Allow overwriting existing files"
    )
    assert panel.difference_export_button.text() == "Export difference…"
    assert panel.export_format_combo.itemText(0) == (
        "CSV (X/Y data + metadata)"
    )
    window.close()
