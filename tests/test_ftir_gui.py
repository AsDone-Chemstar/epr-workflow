"""Headless M10 tests for FTIR GUI import and raw display."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QDialogButtonBox,
)

from spectralab.app.gui.app import (  # noqa: E402
    build_controller,
    build_technique_registry,
)
from spectralab.app.gui.file_filter import build_file_filter  # noqa: E402
from spectralab.app.gui.ftir_import_dialog import FtirImportDialog  # noqa: E402
from spectralab.app.gui.ftir_translations import (  # noqa: E402
    FTIR_DISPLAY_NAME_KEY,
    FTIR_FILE_PATTERNS,
    FTIR_TECHNIQUE_ID,
)
from spectralab.techniques.ftir import FTIR_ENTRY_SUFFIXES  # noqa: E402
from spectralab.app.gui.i18n import Translator  # noqa: E402
from spectralab.app.gui.main_window import MainWindow  # noqa: E402
from spectralab.app.gui.settings import SettingsService  # noqa: E402
from spectralab.app.gui.technique import TechniquePanelProtocol  # noqa: E402
from spectralab.core.processing import ProcessedSpectrum  # noqa: E402
from spectralab.techniques.ftir import (  # noqa: E402
    ColumnMapping,
    FTIRImportOptions,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_SAMPLE = PROJECT_ROOT / "S-BSAPEG-10.0.dpt"
HEADER = "     index           Field [G]        Intensity []\n\n"


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


def _options(
    mapping: ColumnMapping | None = None,
    **kwargs,
) -> FTIRImportOptions:
    return FTIRImportOptions(
        mapping=mapping or ColumnMapping(x=0, y=1),
        **kwargs,
    )


def _write_csv(
    path: Path,
    rows: list[tuple[float, ...]],
    *,
    header: str | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [] if header is None else [header]
    lines.extend(",".join(str(value) for value in row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _write_txt(path: Path, rows: list[tuple[float, float]], delimiter: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"{x}{delimiter}{y}" for x, y in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _write_asc(path: Path, n: int = 21) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [f"{i + 1} {i * 0.5} {10.0 + i * 2.0}" for i in range(n)]
    path.write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def _baseline_rows(
    *,
    decreasing: bool = False,
    polynomial: bool = False,
) -> list[tuple[float, float]]:
    x = np.linspace(1000.0, 1040.0, 81)
    if polynomial:
        baseline = 0.002 * (x - 1020.0) ** 3 - 0.1 * (x - 1020.0)
    else:
        baseline = 0.02 * (x - 1000.0)
    peak = 5.0 * np.exp(-0.5 * ((x - 1020.0) / 1.0) ** 2)
    y = baseline + peak
    rows = [(float(xv), float(yv)) for xv, yv in zip(x, y)]
    return list(reversed(rows)) if decreasing else rows


def _add_baseline_regions(panel, regions: list[tuple[float, float]]) -> None:
    for start, end in regions:
        panel.region_start.setText(str(start))
        panel.region_end.setText(str(end))
        panel._add_region()


def _peak_rows(*, decreasing: bool = False) -> list[tuple[float, float]]:
    x = np.arange(0.0, 21.0)
    y = np.zeros_like(x)
    y[5] = 5.0
    y[10] = -4.0
    y[15] = 3.0
    rows = [(float(xv), float(yv)) for xv, yv in zip(x, y)]
    return list(reversed(rows)) if decreasing else rows


def _set_peak_params(
    panel,
    *,
    source: str = "raw",
    polarity: str = "both",
    height: str = "",
    prominence: str = "",
    distance: int = 1,
    width: str = "",
) -> None:
    panel.peak_source_combo.setCurrentIndex(
        panel.peak_source_combo.findData(source)
    )
    panel.peak_polarity_combo.setCurrentIndex(
        panel.peak_polarity_combo.findData(polarity)
    )
    panel.peak_height.setText(height)
    panel.peak_prominence.setText(prominence)
    panel.peak_distance.setValue(distance)
    panel.peak_min_width.setText(width)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Registration and protocol
# ---------------------------------------------------------------------------
def test_ftir_technique_is_explicitly_registered(app: QApplication) -> None:
    registry = build_technique_registry()
    assert registry.ids == ("epr", "ftir")
    descriptor = registry.get(FTIR_TECHNIQUE_ID)
    assert descriptor.display_name_key == FTIR_DISPLAY_NAME_KEY
    assert set(FTIR_FILE_PATTERNS).issubset(set(descriptor.file_patterns))
    assert {".csv", ".txt", ".dpt"} == {
        pattern.casefold().lstrip("*") for pattern in FTIR_FILE_PATTERNS
    }

    window = _window()
    assert window.technique_combo.count() == 2
    index = window.technique_combo.findData("ftir")
    assert index >= 0
    assert "FTIR" in window.technique_combo.itemText(index)
    window.close()


def test_ftir_file_patterns_and_filter_are_derived() -> None:
    for suffix in FTIR_ENTRY_SUFFIXES:
        assert f"*{suffix}" in FTIR_FILE_PATTERNS
        assert f"*{suffix.upper()}" in FTIR_FILE_PATTERNS
    file_filter = build_file_filter(Translator("en"), FTIR_FILE_PATTERNS)
    assert "Data files" in file_filter
    assert "All files" in file_filter
    assert "*.dpt" in file_filter


def test_ftir_panel_implements_the_panel_protocol(app: QApplication) -> None:
    window = _window()
    panel = _ftir_panel(window)
    assert isinstance(panel, TechniquePanelProtocol)
    assert isinstance(panel.current_display(), type(None))
    assert panel.processing_session is None
    window.close()


# ---------------------------------------------------------------------------
# File import and option propagation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("suffix", "delimiter", "expected_format"),
    [
        ("csv", ",", "FTIR_CSV"),
        ("txt", " ", "FTIR_TXT"),
        ("dpt", "\t", "FTIR_TXT"),
    ],
)
def test_csv_txt_dpt_import_through_generic_window(
    app: QApplication,
    tmp_path: Path,
    suffix: str,
    delimiter: str,
    expected_format: str,
) -> None:
    rows = [(4000.0, 0.1), (3999.0, 0.2), (3998.0, -0.1)]
    source = (
        _write_csv(tmp_path / f"sample.{suffix}", rows)
        if suffix == "csv"
        else _write_txt(tmp_path / f"sample.{suffix}", rows, delimiter)
    )
    window = _window()
    panel = _ftir_panel(window)
    panel.options_widget.set_options(
        _options(
            mapping=ColumnMapping(
                x=0,
                y=1,
                x_unit="cm^-1",
                y_semantics="absorbance",
            ),
            acquisition_mode="ATR",
        )
    )

    assert window.open_file(source) is True
    display = window.current_display
    assert display is panel.current_display()
    assert display.point_count == 3
    assert display.source_format == expected_format
    np.testing.assert_array_equal(
        display.x_values, np.array([4000.0, 3999.0, 3998.0])
    )
    assert len(panel.axes.lines) == 1
    assert len(panel.axes.lines[0].get_xdata()) == 3
    assert panel.axes.get_title() == "sample"
    assert window.status_event.level == "success"
    window.close()


def test_generic_open_uses_inline_column_mapping(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(
        tmp_path / "wide.csv",
        [(1.0, 4000.0, 0.1), (2.0, 3999.0, 0.2)],
        header="index,Wavenumber,Absorbance",
    )
    window = _window()
    panel = _ftir_panel(window)
    widget = panel.options_widget
    widget.x_column.setText("Wavenumber")
    widget.y_column.setText("Absorbance")
    widget.header.setChecked(True)
    widget.x_unit.setCurrentIndex(widget.x_unit.findData("cm^-1"))
    widget.y_semantics.setCurrentIndex(
        widget.y_semantics.findData("absorbance")
    )
    widget.acquisition_mode.setCurrentIndex(
        widget.acquisition_mode.findData("ATR")
    )

    assert window.open_file(source) is True
    display = panel.current_display()
    np.testing.assert_array_equal(
        display.x_values, np.array([4000.0, 3999.0])
    )
    np.testing.assert_array_equal(display.y_values, np.array([0.1, 0.2]))
    assert display.metadata.technique_metadata["header_fields"] == [
        "index",
        "Wavenumber",
        "Absorbance",
    ]
    window.close()


def test_import_options_reach_the_m9_backend(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "options.csv", [(4000.0, 0.1), (3999.0, 0.2)])
    window = _window()
    panel = _ftir_panel(window)
    controller = window._controller
    original = controller.load_spectrum
    seen: dict = {}

    def recording_load(path, **kwargs):
        seen.update(kwargs)
        return original(path, **kwargs)

    controller.load_spectrum = recording_load  # type: ignore[method-assign]
    options = _options(
        mapping=ColumnMapping(
            x=0,
            y=1,
            x_unit="cm^-1",
            y_semantics="transmittance",
        ),
        acquisition_mode="Transmission",
        atr_correction_status="not_applicable",
        instrument_vendor="Vendor",
        instrument_model="Model",
    )

    assert panel.import_file(source, options) is True
    assert seen["technique_hint"] == "ftir"
    assert seen["options"] == {"ftir": options}
    assert panel.current_display().metadata.instrument["vendor"] == "Vendor"
    window.close()


# ---------------------------------------------------------------------------
# Metadata and display
# ---------------------------------------------------------------------------
def test_explicit_ftir_metadata_is_preserved_and_shown(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "metadata.csv", [(4000.0, 0.1), (3999.0, 0.2)])
    window = _window()
    panel = _ftir_panel(window)
    options = _options(
        mapping=ColumnMapping(
            x=0,
            y=1,
            x_name="Wavenumber",
            x_unit="cm^-1",
            x_quantity="wavenumber",
            y_name="Absorbance",
            y_unit="a.u.",
            y_semantics="absorbance",
        ),
        acquisition_mode="ATR",
        atr_correction_status="not_applied",
        instrument_vendor="Example Instruments",
        instrument_model="FTIR-1",
    )
    assert panel.import_file(source, options) is True
    spectrum = panel.current_display()
    assert spectrum.axis.quantity == "wavenumber"
    assert spectrum.axis.unit == "cm^-1"
    assert spectrum.raw_signal.semantics == "absorbance"
    assert spectrum.metadata.acquisition["mode"] == "ATR"
    assert (
        spectrum.metadata.acquisition["atr_correction_status"] == "not_applied"
    )
    assert spectrum.metadata.instrument["vendor"] == "Example Instruments"
    assert spectrum.metadata.instrument["model"] == "FTIR-1"

    text = window.metadata_view.toPlainText()
    assert "wavenumber" in text
    assert "cm^-1" in text
    assert "absorbance" in text
    assert "ATR" in text
    assert "not_applied" in text
    assert "Example Instruments" in text
    assert "FTIR-1" in text
    assert "导入选项" in text
    assert "导入假设" in text
    assert '"ftir_metadata"' not in text
    assert '"resolved_import_options"' not in text
    assert set(spectrum.metadata.technique_metadata) == {
        "format_id",
        "column_mapping",
        "header_fields",
    }
    assert panel.axes.get_xlabel() == "Wavenumber (cm^-1)"
    assert panel.axes.get_ylabel() == "Absorbance (a.u.)"
    window.close()


def test_unknown_metadata_is_displayed_explicitly(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "unknown.csv", [(4000.0, 0.1), (3999.0, 0.2)])
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping())) is True
    spectrum = panel.current_display()
    assert spectrum.axis.quantity == "unknown"
    assert spectrum.axis.unit is None
    assert spectrum.raw_signal.semantics == "unknown"
    assert spectrum.metadata.acquisition["mode"] == "Unknown"
    assert spectrum.metadata.acquisition["atr_correction_status"] == "unknown"
    assert "axis.quantity" in spectrum.metadata.unknown_fields
    assert "atr_correction_status" in spectrum.metadata.unknown_fields
    assert panel.axes.get_xlabel() == "X 轴（未知）"
    assert panel.axes.get_ylabel() == "Y 信号（未知）"
    assert "unknown" in window.metadata_view.toPlainText()
    window.close()


@pytest.mark.parametrize(
    ("rows", "direction", "values"),
    [
        ([(1000.0, 0.1), (1001.0, 0.2)], "increasing", [1000.0, 1001.0]),
        ([(1001.0, 0.2), (1000.0, 0.1)], "decreasing", [1001.0, 1000.0]),
    ],
)
def test_axis_direction_is_visual_only(
    app: QApplication,
    tmp_path: Path,
    rows: list[tuple[float, float]],
    direction: str,
    values: list[float],
) -> None:
    source = _write_csv(tmp_path / f"{direction}.csv", rows)
    window = _window()
    panel = _ftir_panel(window)
    options = _options(
        mapping=ColumnMapping(
            x=0,
            y=1,
            x_unit="cm^-1",
            y_semantics="absorbance",
        )
    )
    assert panel.import_file(source, options) is True
    spectrum = panel.current_display()

    assert spectrum.axis.direction == direction
    np.testing.assert_array_equal(spectrum.x_values, np.array(values))
    np.testing.assert_array_equal(
        panel.axes.lines[0].get_xdata(), np.array(values)
    )
    assert panel.invert_axis_check.isChecked()
    xlim = panel.axes.get_xlim()
    assert xlim[0] > xlim[1]

    panel.invert_axis_check.setChecked(False)
    xlim = panel.axes.get_xlim()
    assert xlim[0] < xlim[1]
    np.testing.assert_array_equal(spectrum.x_values, np.array(values))
    window.close()


def test_raw_data_integrity_across_redraw_and_language_switch(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(
        tmp_path / "integrity.csv",
        [(4000.0, 0.1), (3999.0, 0.2), (3998.0, 0.3)],
    )
    before = _sha256(source)
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(
        source,
        _options(
            mapping=ColumnMapping(
                x=0, y=1, x_unit="cm^-1", y_semantics="absorbance"
            )
        ),
    )
    spectrum = panel.current_display()
    x_before = spectrum.x_values.copy()
    y_before = spectrum.y_values.copy()

    panel.retranslate()
    panel.invert_axis_check.setChecked(False)
    panel.invert_axis_check.setChecked(True)
    window.set_language("en")
    window.set_language("zh")

    np.testing.assert_array_equal(spectrum.x_values, x_before)
    np.testing.assert_array_equal(spectrum.y_values, y_before)
    np.testing.assert_array_equal(panel.axes.lines[0].get_xdata(), x_before)
    assert panel.processing_session is not None
    assert panel.processing_session.history == ()
    assert _sha256(source) == before
    assert "处理历史：无" in window.metadata_view.toPlainText()
    window.close()


# ---------------------------------------------------------------------------
# Errors, warnings and status
# ---------------------------------------------------------------------------
def test_import_failure_preserves_previous_spectrum(
    app: QApplication, tmp_path: Path
) -> None:
    good = _write_csv(tmp_path / "good.csv", [(4000.0, 0.1), (3999.0, 0.2)])
    broken = tmp_path / "broken.csv"
    broken.write_text("4000,0.1\n3999\n3998,0.3\n", encoding="utf-8")
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(good, _options(mapping=ColumnMapping())) is True
    previous = panel.current_display()
    values = previous.x_values.copy()

    assert panel.import_file(broken, _options(mapping=ColumnMapping())) is False

    assert panel.current_display() is previous
    np.testing.assert_array_equal(panel.current_display().x_values, values)
    assert window.status_event.level == "error"
    assert window.status_event.key == "ftir.import_failed"
    assert "FTIR" in window.status_view.text()
    assert "ftir_inconsistent_columns" in window.status_view.text()
    window.close()


def test_extra_columns_produce_a_warning_status(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(
        tmp_path / "extra.csv",
        [(9.0, 4000.0, 0.1), (8.0, 3999.0, 0.2)],
    )
    window = _window()
    panel = _ftir_panel(window)
    options = _options(mapping=ColumnMapping(x=1, y=2))
    assert panel.import_file(source, options) is True

    assert panel.warnings
    assert window.status_event.level == "warning"
    assert window.status_event.key == "ftir.loaded_with_warnings"
    assert "多光谱拆分" not in window.status_view.text()
    assert "only X column 1 and Y column 2" in window.status_view.text()
    assert "导入警告" in window.metadata_view.toPlainText()
    window.close()


def test_invalid_ui_options_are_reported_without_import(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "one.csv", [(4000.0, 0.1), (3999.0, 0.2)])
    window = _window()
    panel = _ftir_panel(window)
    widget = panel.options_widget
    widget.delimiter.setCurrentIndex(widget.delimiter.findData("custom"))
    widget.custom_delimiter.clear()

    assert window.open_file(source) is False
    assert window.current_display is None
    assert window.status_event.level == "error"
    assert window.status_event.key == "ftir.options_invalid"
    window.close()


# ---------------------------------------------------------------------------
# Explicit FTIR normalization
# ---------------------------------------------------------------------------
def test_normalization_preview_apply_cancel_undo_redo_reset(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(
        tmp_path / "normalize.csv",
        [(1000.0, -2.0), (1001.0, -1.0), (1002.0, 0.0), (1003.0, 3.0)],
    )
    before = _sha256(source)
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(
        source,
        _options(
            mapping=ColumnMapping(
                x=0, y=1, x_unit="cm^-1", y_semantics="absorbance"
            )
        ),
    )
    source_spectrum = panel.current_display()
    x_before = source_spectrum.x_values.copy()
    y_before = source_spectrum.y_values.copy()
    session = panel.processing_session
    assert session is not None
    assert session.history == ()

    panel.method_combo.setCurrentIndex(
        panel.method_combo.findData("min_max")
    )
    panel._preview()

    assert panel.preview_output is not None
    assert session.history == ()
    assert panel.current_display() is source_spectrum
    assert [line.get_label() for line in panel.axes.lines] == [
        "原始",
        "预览（未应用）",
    ]
    np.testing.assert_allclose(
        panel.axes.lines[1].get_ydata(),
        np.array([0.0, 0.2, 0.4, 1.0]),
        rtol=1e-15,
        atol=0.0,
    )
    assert window.status_event.key == "ftir.preview_ready"
    assert panel.apply_button.isEnabled()
    assert panel.cancel_preview_button.isEnabled()

    panel._cancel_preview()
    assert panel.preview_output is None
    assert session.history == ()
    assert panel.current_display() is source_spectrum
    assert [line.get_label() for line in panel.axes.lines] == ["原始"]
    assert window.status_event.key == "ftir.preview_cancelled"

    panel._preview()
    panel._apply()
    display = panel.current_display()
    assert isinstance(display, ProcessedSpectrum)
    assert len(session.history) == 1
    assert session.history[0].operation_id == "ftir.normalize.min_max"
    assert session.history[0].parameters["method"] == "min_max"
    assert [line.get_label() for line in panel.axes.lines] == [
        "原始",
        "归一化",
    ]
    assert "处理历史：1 步" in window.metadata_view.toPlainText()
    assert window.status_event.key == "ftir.normalization_applied"
    np.testing.assert_array_equal(source_spectrum.x_values, x_before)
    np.testing.assert_array_equal(source_spectrum.y_values, y_before)
    assert _sha256(source) == before

    panel._undo()
    assert session.history == ()
    assert panel.current_display() is source_spectrum
    assert len(panel.axes.lines) == 1

    panel._redo()
    assert len(session.history) == 1
    assert isinstance(panel.current_display(), ProcessedSpectrum)

    panel._reset()
    assert session.history == ()
    assert panel.current_display() is source_spectrum
    assert len(panel.axes.lines) == 1
    window.close()


def test_normalization_preview_requires_explicit_apply(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(
        tmp_path / "cancel.csv",
        [(1000.0, -2.0), (1001.0, -1.0), (1002.0, 0.0), (1003.0, 3.0)],
    )
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    session = panel.processing_session
    assert session is not None
    assert panel.apply_button.isEnabled() is False

    panel._apply()
    assert window.status_event.key == "ftir.preview_required"
    assert session.history == ()
    assert isinstance(panel.current_display(), type(session.source))
    window.close()


def test_normalization_constant_signal_is_reported_without_mutation(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(
        tmp_path / "constant.csv",
        [(1000.0, 2.0), (1001.0, 2.0), (1002.0, 2.0), (1003.0, 2.0)],
    )
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    session = panel.processing_session
    assert session is not None
    previous = panel.current_display()

    panel.method_combo.setCurrentIndex(
        panel.method_combo.findData("min_max")
    )
    panel._preview()

    assert panel.preview_output is None
    assert session.history == ()
    assert panel.current_display() is previous
    assert window.status_event.level == "error"
    assert window.status_event.key == "ftir.processing_failed"
    assert "ftir_normalization_zero_denominator" in window.status_view.text()
    window.close()


def test_method_change_cancels_preview(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(
        tmp_path / "method.csv",
        [(1000.0, -2.0), (1001.0, -1.0), (1002.0, 0.0), (1003.0, 3.0)],
    )
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    panel._preview()
    assert panel.preview_output is not None

    panel.method_combo.setCurrentIndex(panel.method_combo.findData("l2"))

    assert panel.preview_output is None
    assert panel.processing_session.history == ()
    assert panel.apply_button.isEnabled() is False
    assert window.status_event.key == "ftir.preview_cancelled"
    window.close()


def test_normalization_preview_labels_follow_language(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(
        tmp_path / "language-normalize.csv",
        [(1000.0, -2.0), (1001.0, -1.0), (1002.0, 0.0), (1003.0, 3.0)],
    )
    window = _window("zh")
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    panel._preview()
    assert [line.get_label() for line in panel.axes.lines] == [
        "原始",
        "预览（未应用）",
    ]
    assert panel.method_label.text() == "归一化方法"
    assert panel.preview_button.text() == "预览"

    window.set_language("en")

    assert [line.get_label() for line in panel.axes.lines] == [
        "Raw",
        "Preview (not applied)",
    ]
    assert panel.method_label.text() == "Normalization method"
    assert panel.preview_button.text() == "Preview"
    assert panel.apply_button.text() == "Apply"
    assert "Preview:" in panel.state_label.text()
    window.close()


# ---------------------------------------------------------------------------
# Explicit FTIR baseline correction
# ---------------------------------------------------------------------------
def test_baseline_regions_degree_preview_apply_undo_redo_reset(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(
        tmp_path / "baseline.csv",
        _baseline_rows(),
    )
    before = _sha256(source)
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(
        source,
        _options(
            mapping=ColumnMapping(
                x=0, y=1, x_unit="cm^-1", y_semantics="absorbance"
            )
        ),
    )
    raw = panel.current_display()
    x_before = raw.x_values.copy()
    y_before = raw.y_values.copy()

    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("baseline")
    )
    panel.baseline_algorithm.setCurrentIndex(
        panel.baseline_algorithm.findData("linear")
    )
    _add_baseline_regions(panel, [(1000.0, 1005.0), (1035.0, 1040.0)])

    assert panel.region_list.count() == 2
    assert "阶数：1" in panel.fit_info_label.text()
    assert all(
        "拟合点" in panel.region_list.item(index).text()
        for index in range(panel.region_list.count())
    )

    panel._preview()

    assert panel.preview_output is not None
    assert panel.processing_session.history == ()
    assert panel.current_display() is raw
    labels = [line.get_label() for line in panel.axes.lines]
    assert labels == ["原始", "预览（未应用）", "估计基线"]
    assert len(panel.axes.patches) == 2
    assert "基线预览" in panel.state_label.text()
    assert "拟合点数" in panel.fit_info_label.text()
    assert window.status_event.key == "ftir.baseline_preview_ready"

    panel._cancel_preview()
    assert panel.preview_output is None
    assert panel.processing_session.history == ()
    assert panel.current_display() is raw
    assert window.status_event.key == "ftir.preview_cancelled"
    assert [line.get_label() for line in panel.axes.lines] == ["原始"]

    panel._preview()
    panel._apply()

    display = panel.current_display()
    assert isinstance(display, ProcessedSpectrum)
    history = panel.processing_session.history
    assert len(history) == 1
    assert history[0].operation_id == "ftir.baseline.linear"
    assert history[0].parameters["regions"] == [
        {"start": 1000.0, "end": 1005.0},
        {"start": 1035.0, "end": 1040.0},
    ]
    assert history[0].diagnostics["fitting_point_count"] > 1
    assert len(history[0].diagnostics["coefficients"]) == 2
    assert [line.get_label() for line in panel.axes.lines] == [
        "原始",
        "基线校正",
    ]
    assert "处理历史：1 步" in window.metadata_view.toPlainText()
    assert window.status_event.key == "ftir.baseline_applied"
    assert "已应用" in panel.fit_info_label.text()
    assert "拟合点数" in panel.fit_info_label.text()
    np.testing.assert_array_equal(raw.x_values, x_before)
    np.testing.assert_array_equal(raw.y_values, y_before)
    assert _sha256(source) == before

    panel._undo()
    assert panel.processing_session.history == ()
    assert panel.current_display() is raw

    panel._redo()
    assert len(panel.processing_session.history) == 1
    assert isinstance(panel.current_display(), ProcessedSpectrum)

    panel._reset()
    assert panel.processing_session.history == ()
    assert panel.current_display() is raw
    window.close()


def test_polynomial_baseline_degree_and_preview_invalidation(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "polynomial.csv", _baseline_rows(polynomial=True))
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("baseline")
    )
    panel.baseline_algorithm.setCurrentIndex(
        panel.baseline_algorithm.findData("polynomial")
    )
    panel.degree_spin.setValue(3)
    _add_baseline_regions(panel, [(1000.0, 1005.0), (1035.0, 1040.0)])

    panel._preview()
    assert panel.preview_output is not None
    assert panel.processing_session.history == ()
    assert "阶数：3" in panel.fit_info_label.text()
    assert "拟合点数" in panel.fit_info_label.text()

    panel.degree_spin.setValue(4)
    assert panel.preview_output is None
    assert panel.processing_session.history == ()
    assert window.status_event.key == "ftir.preview_cancelled"
    assert panel.apply_button.isEnabled() is False

    panel._preview()
    panel._apply()
    record = panel.processing_session.history[0]
    assert record.operation_id == "ftir.baseline.polynomial"
    assert record.parameters["degree"] == 4
    assert len(record.diagnostics["coefficients"]) == 5
    assert record.diagnostics["degree"] == 4
    window.close()


def test_region_add_remove_and_invalid_region(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "regions.csv", _baseline_rows())
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("baseline")
    )

    _add_baseline_regions(panel, [(1000.0, 1005.0), (1035.0, 1040.0)])
    assert panel.region_list.count() == 2

    panel._preview()
    assert panel.preview_output is not None
    panel.region_start.setText("1004")
    panel.region_end.setText("1036")
    panel._add_region()
    assert panel.region_list.count() == 2
    assert window.status_event.level == "error"
    assert window.status_event.key == "ftir.invalid_region"

    panel.region_list.setCurrentRow(0)
    panel._remove_region()
    assert panel.region_list.count() == 1
    assert panel.preview_output is None
    assert panel.processing_session.history == ()

    panel.region_list.setCurrentRow(-1)
    panel._remove_region()
    assert panel.region_list.count() == 0
    assert panel.remove_region_button.isEnabled() is False
    window.close()


def test_region_text_edit_invalidates_preview_and_apply(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "edit-region.csv", _baseline_rows())
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("baseline")
    )
    _add_baseline_regions(panel, [(1000.0, 1005.0), (1035.0, 1040.0)])
    panel._preview()
    assert panel.preview_output is not None
    assert panel.apply_button.isEnabled() is True

    panel.region_start.setText("1001")

    assert panel.preview_output is None
    assert panel.apply_button.isEnabled() is False
    assert panel.processing_session.history == ()
    assert window.status_event.key == "ftir.preview_cancelled"

    panel._preview()
    assert panel.preview_output is not None
    assert panel.apply_button.isEnabled() is True
    window.close()


def test_empty_region_is_rejected_by_gui(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "empty-region.csv", _baseline_rows())
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("baseline")
    )

    panel.region_start.setText("0")
    panel.region_end.setText("5")
    panel._add_region()

    assert panel.region_list.count() == 0
    assert window.status_event.level == "error"
    assert window.status_event.key == "ftir.invalid_region"
    assert "不包含任何数据点" in window.status_view.text()
    window.close()


def test_import_failure_invalidates_stale_preview(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "previous.csv", _baseline_rows())
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    previous = panel.current_display()
    session = panel.processing_session
    assert session is not None
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("baseline")
    )
    _add_baseline_regions(panel, [(1000.0, 1005.0), (1035.0, 1040.0)])
    panel._preview()
    assert panel.preview_output is not None

    assert panel.import_file(
        tmp_path / "missing.csv",
        _options(mapping=ColumnMapping(x=0, y=1)),
    ) is False

    assert panel.preview_output is None
    assert panel.current_display() is previous
    assert panel.processing_session is session
    assert session.history == ()
    assert panel.apply_button.isEnabled() is False
    assert window.status_event.level == "error"
    assert window.status_event.key == "ftir.import_failed"
    window.close()


def test_baseline_preview_requires_explicit_regions(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "no-regions.csv", _baseline_rows())
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("baseline")
    )

    panel._preview()

    assert panel.preview_output is None
    assert window.status_event.level == "error"
    assert "ftir_baseline_regions" in window.status_view.text()
    assert panel.processing_session.history == ()
    window.close()


def test_baseline_preview_after_normalization_shows_all_states(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "normalize-baseline.csv", _baseline_rows())
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("normalization")
    )
    panel._preview()
    panel._apply()
    normalized = panel.current_display()
    assert isinstance(normalized, ProcessedSpectrum)
    assert len(panel.processing_session.history) == 1

    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("baseline")
    )
    panel.baseline_algorithm.setCurrentIndex(
        panel.baseline_algorithm.findData("linear")
    )
    _add_baseline_regions(panel, [(1000.0, 1005.0), (1035.0, 1040.0)])
    panel._preview()

    labels = [line.get_label() for line in panel.axes.lines]
    assert labels == [
        "原始",
        "预览（未应用）",
        "当前处理谱",
        "估计基线",
    ]
    assert len(panel.processing_session.history) == 1

    panel._apply()
    assert [record.operation_id for record in panel.processing_session.history] == [
        "ftir.normalize.min_max",
        "ftir.baseline.linear",
    ]
    panel._undo()
    assert [record.operation_id for record in panel.processing_session.history] == [
        "ftir.normalize.min_max"
    ]
    assert isinstance(panel.current_display(), ProcessedSpectrum)
    assert [line.get_label() for line in panel.axes.lines] == ["原始", "归一化"]
    window.close()


def test_baseline_preview_language_and_descending_axis(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "descending.csv", _baseline_rows(decreasing=True))
    window = _window("zh")
    panel = _ftir_panel(window)
    assert panel.import_file(
        source,
        _options(
            mapping=ColumnMapping(
                x=0, y=1, x_unit="cm^-1", y_semantics="absorbance"
            )
        ),
    )
    x_before = panel.current_display().x_values.copy()
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("baseline")
    )
    _add_baseline_regions(panel, [(1000.0, 1005.0), (1035.0, 1040.0)])
    panel._preview()

    assert "基线预览" in panel.state_label.text()
    assert [line.get_label() for line in panel.axes.lines] == [
        "原始",
        "预览（未应用）",
        "估计基线",
    ]
    np.testing.assert_array_equal(panel.current_display().x_values, x_before)
    assert panel.axes.get_xlim()[0] > panel.axes.get_xlim()[1]

    window.set_language("en")

    assert panel.operation_label.text() == "Processing operation"
    assert panel.baseline_algorithm_label.text() == "Baseline algorithm"
    assert panel.add_region_button.text() == "Add region"
    assert "Baseline preview:" in panel.state_label.text()
    assert [line.get_label() for line in panel.axes.lines] == [
        "Raw",
        "Preview (not applied)",
        "Estimated baseline",
    ]
    np.testing.assert_array_equal(panel.current_display().x_values, x_before)
    window.close()


def test_new_import_clears_active_baseline_preview(
    app: QApplication, tmp_path: Path
) -> None:
    first = _write_csv(tmp_path / "first.csv", _baseline_rows())
    second = _write_csv(tmp_path / "second.csv", _baseline_rows(decreasing=True))
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(first, _options(mapping=ColumnMapping(x=0, y=1)))
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("baseline")
    )
    _add_baseline_regions(panel, [(1000.0, 1005.0), (1035.0, 1040.0)])
    panel._preview()
    assert panel.preview_output is not None

    assert panel.import_file(second, _options(mapping=ColumnMapping(x=0, y=1)))

    assert panel.preview_output is None
    assert panel.processing_session.history == ()
    assert panel.region_list.count() == 0
    assert panel.current_display().point_count == 81
    assert panel.current_display().axis.direction == "decreasing"
    window.close()


def test_real_ftir_sample_baseline_through_gui(app: QApplication) -> None:
    if not REAL_SAMPLE.is_file():
        pytest.skip(f"real FTIR sample not present: {REAL_SAMPLE}")
    before = _sha256(REAL_SAMPLE)
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(
        REAL_SAMPLE,
        _options(
            mapping=ColumnMapping(
                x=0,
                y=1,
                x_unit="cm^-1",
                y_semantics="absorbance",
            ),
            acquisition_mode="ATR",
        ),
    )
    source = panel.current_display()
    x_before = source.x_values.copy()
    y_before = source.y_values.copy()
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("baseline")
    )
    panel.baseline_algorithm.setCurrentIndex(
        panel.baseline_algorithm.findData("linear")
    )
    _add_baseline_regions(panel, [(3800.0, 3900.0), (950.0, 1000.0)])

    panel._preview()
    assert panel.preview_output is not None
    assert len(panel.axes.patches) == 2
    assert panel.processing_session.history == ()
    panel._apply()

    assert isinstance(panel.current_display(), ProcessedSpectrum)
    assert panel.current_display().point_count == 4350
    assert panel.processing_session.history[0].operation_id == (
        "ftir.baseline.linear"
    )
    np.testing.assert_array_equal(source.x_values, x_before)
    np.testing.assert_array_equal(source.y_values, y_before)
    assert _sha256(REAL_SAMPLE) == before
    window.close()


# ---------------------------------------------------------------------------
# Peak picking
# ---------------------------------------------------------------------------
def test_peak_preview_apply_and_clear(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "peaks.csv", _peak_rows())
    before = _sha256(source)
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(
        source,
        _options(
            mapping=ColumnMapping(
                x=0, y=1, x_unit="cm^-1", y_semantics="absorbance"
            )
        ),
    )
    display = panel.current_display()
    session = panel.processing_session
    assert session is not None
    _set_peak_params(panel, source="raw", polarity="both")

    panel._preview_peaks()

    result = panel.peak_result
    assert result is not None
    assert result.parameters.source == "raw"
    assert result.parameters.polarity == "both"
    assert result.positive_count == 2
    assert result.negative_count == 1
    assert panel.peak_preview_result is result
    assert panel.peak_applied_result is None
    assert panel.peak_table.rowCount() == 3
    assert panel.peak_table.horizontalHeaderItem(0).text() == "序号"
    assert "cm^-1" in panel.peak_table.horizontalHeaderItem(2).text()
    labels = [line.get_label() for line in panel.axes.lines]
    assert "原始谱" in labels
    assert "正向峰" in labels
    assert "负向峰" in labels
    assert panel.current_display() is display
    assert session.history == ()
    assert panel.peak_apply_button.isEnabled() is True
    assert window.status_event.key == "ftir.peak_preview_ready"

    panel._apply_peaks()

    assert panel.peak_preview_result is None
    assert panel.peak_applied_result is result
    assert panel.peak_table.rowCount() == 3
    assert panel.peak_apply_button.isEnabled() is False
    assert panel.current_display() is display
    assert session.history == ()
    assert window.status_event.key == "ftir.peak_applied"
    assert _sha256(source) == before

    panel._clear_peak_results()

    assert panel.peak_result is None
    assert panel.peak_table.rowCount() == 0
    assert panel.current_display() is display
    assert len(panel.axes.lines) == 1
    assert window.status_event.key == "ftir.peak_cleared"
    window.close()


def test_peak_source_processed_and_session_provenance(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "processed-peaks.csv", _peak_rows())
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("normalization")
    )
    panel._preview()
    panel._apply()
    normalized = panel.current_display()
    assert isinstance(normalized, ProcessedSpectrum)
    _set_peak_params(panel, source="processed", polarity="positive")

    panel._preview_peaks()

    result = panel.peak_result
    assert result is not None
    assert result.parameters.source == "processed"
    assert result.source_operation_history == ("ftir.normalize.min_max",)
    assert result.dataset_id == "processed-peaks"
    assert panel.peak_table.rowCount() == 2
    assert panel.current_display() is normalized
    assert len(panel.processing_session.history) == 1
    window.close()


def test_peak_parameter_change_invalidates_preview(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "peak-params.csv", _peak_rows())
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    _set_peak_params(panel, polarity="both")
    panel._preview_peaks()
    assert panel.peak_preview_result is not None
    assert panel.peak_apply_button.isEnabled() is True

    panel.peak_polarity_combo.setCurrentIndex(
        panel.peak_polarity_combo.findData("positive")
    )
    assert panel.peak_preview_result is None
    assert panel.peak_apply_button.isEnabled() is False
    assert window.status_event.key == "ftir.peak_preview_cancelled"

    panel._preview_peaks()
    panel.peak_height.setText("4")
    assert panel.peak_preview_result is None
    assert panel.peak_apply_button.isEnabled() is False

    panel._preview_peaks()
    panel.peak_distance.setValue(5)
    assert panel.peak_preview_result is None

    panel._preview_peaks()
    panel.peak_prominence.setText("1")
    assert panel.peak_preview_result is None

    panel._preview_peaks()
    panel.peak_min_width.setText("2")
    assert panel.peak_preview_result is None

    panel._preview_peaks()
    panel.peak_source_combo.setCurrentIndex(
        panel.peak_source_combo.findData("processed")
    )
    assert panel.peak_preview_result is None
    assert panel.peak_apply_button.isEnabled() is False
    window.close()


def test_peak_preview_does_not_modify_session_or_source(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "peak-immutable.csv", _peak_rows())
    before = _sha256(source)
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    display = panel.current_display()
    session = panel.processing_session
    x_before = display.x_values.copy()
    y_before = display.y_values.copy()
    _set_peak_params(panel, polarity="both")

    panel._preview_peaks()

    assert panel.peak_result is not None
    assert panel.current_display() is display
    assert session.history == ()
    assert session.can_undo is False
    assert session.can_redo is False
    np.testing.assert_array_equal(display.x_values, x_before)
    np.testing.assert_array_equal(display.y_values, y_before)
    assert _sha256(source) == before
    window.close()


def test_peak_descending_axis_and_table_order(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(
        tmp_path / "descending-peaks.csv",
        _peak_rows(decreasing=True),
    )
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(
        source,
        _options(
            mapping=ColumnMapping(
                x=0, y=1, x_unit="cm^-1", y_semantics="absorbance"
            )
        ),
    )
    x_before = panel.current_display().x_values.copy()
    _set_peak_params(panel, polarity="both")
    panel._preview_peaks()

    result = panel.peak_result
    assert result is not None
    assert result.axis_direction == "decreasing"
    assert [peak.x for peak in result.peaks] == [15.0, 10.0, 5.0]
    assert [peak.polarity for peak in result.peaks] == [
        "positive",
        "negative",
        "positive",
    ]
    np.testing.assert_array_equal(panel.current_display().x_values, x_before)
    assert panel.axes.get_xlim()[0] > panel.axes.get_xlim()[1]
    window.close()


def test_peak_parameter_change_invalidates_preview_and_language(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "peak-language.csv", _peak_rows())
    window = _window("zh")
    panel = _ftir_panel(window)
    assert panel.import_file(source, _options(mapping=ColumnMapping(x=0, y=1)))
    _set_peak_params(panel, polarity="both")
    panel._preview_peaks()
    assert "正向峰" in [line.get_label() for line in panel.axes.lines]
    assert panel.peak_table.horizontalHeaderItem(0).text() == "序号"

    window.set_language("en")

    assert panel.bottom_tabs.tabText(1) == "Peak picking"
    assert panel.peak_source_label.text() == "Detection source"
    assert panel.peak_polarity_label.text() == "Peak polarity"
    assert panel.peak_table.horizontalHeaderItem(0).text() == "Index"
    assert "Positive peaks" in [
        line.get_label() for line in panel.axes.lines
    ]
    assert "Preview:" in panel.peak_status_label.text()
    window.close()


def test_new_import_and_processing_change_clear_peak_results(
    app: QApplication, tmp_path: Path
) -> None:
    first = _write_csv(tmp_path / "first-peaks.csv", _peak_rows())
    second = _write_csv(
        tmp_path / "second-peaks.csv",
        _peak_rows(decreasing=True),
    )
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(first, _options(mapping=ColumnMapping(x=0, y=1)))
    _set_peak_params(panel, polarity="both")
    panel._preview_peaks()
    panel._apply_peaks()
    assert panel.peak_result is not None

    assert panel.import_file(second, _options(mapping=ColumnMapping(x=0, y=1)))
    assert panel.peak_result is None
    assert panel.peak_table.rowCount() == 0

    _set_peak_params(panel, polarity="both")
    panel._preview_peaks()
    assert panel.peak_result is not None
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("normalization")
    )
    panel._preview()
    panel._apply()
    assert panel.peak_result is None
    assert panel.peak_table.rowCount() == 0
    window.close()


def test_real_ftir_sample_peak_preview(app: QApplication) -> None:
    if not REAL_SAMPLE.is_file():
        pytest.skip(f"real FTIR sample not present: {REAL_SAMPLE}")
    before = _sha256(REAL_SAMPLE)
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(
        REAL_SAMPLE,
        _options(
            mapping=ColumnMapping(
                x=0,
                y=1,
                x_unit="cm^-1",
                y_semantics="absorbance",
            ),
            acquisition_mode="ATR",
        ),
    )
    display = panel.current_display()
    x_before = display.x_values.copy()
    y_before = display.y_values.copy()
    _set_peak_params(panel, source="raw", polarity="both")

    panel._preview_peaks()

    result = panel.peak_result
    assert result is not None
    assert result.dataset_id == "S-BSAPEG-10.0"
    assert result.axis_unit == "cm^-1"
    assert result.signal_unit is None
    assert panel.peak_table.rowCount() == result.peak_count
    assert panel.current_display() is display
    assert panel.processing_session.history == ()
    np.testing.assert_array_equal(display.x_values, x_before)
    np.testing.assert_array_equal(display.y_values, y_before)
    assert _sha256(REAL_SAMPLE) == before
    window.close()


# ---------------------------------------------------------------------------
# Language and dialog
# ---------------------------------------------------------------------------
def test_runtime_language_switch_updates_ftir_panel_and_plot(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "language.csv", [(4000.0, 0.1), (3999.0, 0.2)])
    window = _window("zh")
    panel = _ftir_panel(window)
    assert panel.import_file(
        source,
        _options(
            mapping=ColumnMapping(
                x=0, y=1, x_unit="cm^-1", y_semantics="absorbance"
            ),
            acquisition_mode="ATR",
        ),
    )
    assert panel.axes.get_xlabel() == "波数 (cm^-1)"
    assert panel.axes.get_ylabel() == "吸光度"
    assert panel.axes.lines[0].get_label() == "原始"
    assert panel.import_options_button.text() == "使用选项导入 FTIR 文件…"

    window.set_language("en")

    assert panel.import_options_button.text() == "Import FTIR file with options…"
    assert panel.options_widget.x_column_label.text() == "X column"
    assert panel.axes.get_xlabel() == "Wavenumber (cm^-1)"
    assert panel.axes.get_ylabel() == "Absorbance"
    assert panel.axes.lines[0].get_label() == "Raw"
    assert "Loaded 2 points" in window.status_view.text()
    assert "Import options" in window.metadata_view.toPlainText()

    window.set_language("zh")
    assert panel.axes.get_xlabel() == "波数 (cm^-1)"
    window.close()


def test_import_dialog_builds_and_translates_options(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_csv(tmp_path / "dialog.csv", [(4000.0, 0.1), (3999.0, 0.2)])
    window = _window("zh")
    _ftir_panel(window)
    dialog = FtirImportDialog(window._translator, path=source)
    assert dialog.windowTitle() == "FTIR 导入选项"
    assert dialog.file_label.text() == "文件"
    assert dialog.options_widget.columns_group.title() == "列与文本解析"
    assert dialog.options_widget.x_column_label.text() == "X 列"
    assert dialog.selected_path() == source
    defaults = dialog.selected_options()
    assert defaults.acquisition_mode == "Unknown"
    assert defaults.atr_correction_status == "unknown"
    assert defaults.mapping.x is None and defaults.mapping.y is None

    widget = dialog.options_widget
    widget.x_column.setText("0")
    widget.y_column.setText("1")
    widget.header.setChecked(False)
    widget.x_unit.setCurrentIndex(widget.x_unit.findData("cm^-1"))
    widget.x_quantity.setCurrentIndex(
        widget.x_quantity.findData("wavenumber")
    )
    widget.y_semantics.setCurrentIndex(
        widget.y_semantics.findData("absorbance")
    )
    widget.acquisition_mode.setCurrentIndex(
        widget.acquisition_mode.findData("ATR")
    )
    widget.atr_status.setCurrentIndex(
        widget.atr_status.findData("unknown")
    )
    options = dialog.selected_options()
    assert options.mapping.x == 0
    assert options.mapping.y == 1
    assert options.mapping.x_unit == "cm^-1"
    assert options.mapping.x_quantity == "wavenumber"
    assert options.mapping.y_semantics == "absorbance"
    assert options.acquisition_mode == "ATR"

    window.set_language("en")
    dialog.retranslate()
    assert dialog.windowTitle() == "FTIR import options"
    assert dialog.file_label.text() == "File"
    assert dialog.options_widget.columns_group.title() == "Columns and text parsing"
    assert dialog.options_widget.x_column_label.text() == "X column"
    ok = dialog.buttons.button(QDialogButtonBox.Ok)
    assert ok is not None and ok.text() == "Import"
    window.close()


def test_import_dialog_validates_path_without_closing(
    app: QApplication, tmp_path: Path
) -> None:
    window = _window()
    _ftir_panel(window)
    dialog = FtirImportDialog(window._translator, path=tmp_path / "missing.csv")
    dialog.accept()
    assert dialog.result() == 0
    assert "不存在" in dialog.error_label.text()

    valid = _write_csv(tmp_path / "valid.csv", [(4000.0, 0.1), (3999.0, 0.2)])
    dialog.set_path(valid)
    dialog.accept()
    assert dialog.result() == QDialog.Accepted
    window.close()


# ---------------------------------------------------------------------------
# Real sample and EPR regression
# ---------------------------------------------------------------------------
def test_real_ftir_sample_through_gui(app: QApplication) -> None:
    if not REAL_SAMPLE.is_file():
        pytest.skip(f"real FTIR sample not present: {REAL_SAMPLE}")
    before = _sha256(REAL_SAMPLE)
    window = _window()
    panel = _ftir_panel(window)
    options = _options(
        mapping=ColumnMapping(
            x=0,
            y=1,
            x_unit="cm^-1",
            y_semantics="absorbance",
        ),
        acquisition_mode="ATR",
        atr_correction_status="unknown",
    )
    panel.options_widget.set_options(options)

    assert window.open_file(REAL_SAMPLE) is True
    # The generic open button uses the currently visible options.
    assert panel.current_display().point_count == 4350
    assert len(panel.axes.lines) == 1
    assert len(panel.axes.lines[0].get_xdata()) == 4350
    assert panel.axes.lines[0].get_xdata()[0] == pytest.approx(3998.83701)
    assert panel.axes.lines[0].get_xdata()[-1] == pytest.approx(899.39981)
    xlim = panel.axes.get_xlim()
    assert xlim[0] > xlim[1]
    assert panel.current_display().axis.direction == "decreasing"
    assert panel.current_display().axis.quantity == "wavenumber"
    assert panel.current_display().raw_signal.semantics == "absorbance"
    assert panel.current_display().metadata.acquisition["mode"] == "ATR"
    assert (
        panel.current_display().metadata.acquisition["atr_correction_status"]
        == "unknown"
    )
    assert panel.processing_session is not None
    assert panel.processing_session.history == ()
    assert window.status_event.level == "success"
    metadata = window.metadata_view.toPlainText()
    assert "点数：4350" in metadata
    assert "cm^-1" in metadata
    assert "absorbance" in metadata
    assert "ATR" in metadata
    assert "导入选项" in metadata
    assert _sha256(REAL_SAMPLE) == before
    window.close()


def test_real_ftir_sample_normalization_through_gui(app: QApplication) -> None:
    if not REAL_SAMPLE.is_file():
        pytest.skip(f"real FTIR sample not present: {REAL_SAMPLE}")
    before = _sha256(REAL_SAMPLE)
    window = _window()
    panel = _ftir_panel(window)
    assert panel.import_file(
        REAL_SAMPLE,
        _options(
            mapping=ColumnMapping(
                x=0,
                y=1,
                x_unit="cm^-1",
                y_semantics="absorbance",
            ),
            acquisition_mode="ATR",
        ),
    )
    source = panel.current_display()
    x_before = source.x_values.copy()
    y_before = source.y_values.copy()

    panel.method_combo.setCurrentIndex(
        panel.method_combo.findData("max_abs")
    )
    panel._preview()
    panel._apply()

    display = panel.current_display()
    assert isinstance(display, ProcessedSpectrum)
    assert display.point_count == 4350
    assert np.max(np.abs(display.y_values)) == pytest.approx(1.0)
    np.testing.assert_array_equal(display.x_values, x_before)
    np.testing.assert_array_equal(source.x_values, x_before)
    np.testing.assert_array_equal(source.y_values, y_before)
    assert panel.processing_session.history[0].operation_id == (
        "ftir.normalize.max_abs"
    )
    assert "处理历史：1 步" in window.metadata_view.toPlainText()
    assert window.status_event.level == "success"
    assert _sha256(REAL_SAMPLE) == before
    window.close()


def test_epr_gui_remains_usable_after_ftir_registration(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_asc(tmp_path / "epr.ASC")
    window = _window()
    index = window.technique_combo.findData("epr")
    window.technique_combo.setCurrentIndex(index)
    assert window.technique_combo.count() == 2
    assert window.open_file(source) is True
    panel = window._panels["epr"]
    assert panel.current_display().point_count == 21
    assert len(panel.axes.lines) == 1
    assert window.status_event.level == "success"
    window.close()


def test_ftir_active_technique_persists_across_windows(
    app: QApplication, tmp_path: Path
) -> None:
    settings_path = tmp_path / "settings.json"
    first = MainWindow(
        build_controller(),
        Translator("zh"),
        SettingsService(settings_path),
    )
    _ftir_panel(first)
    first.close()

    second = MainWindow(
        build_controller(),
        Translator("zh"),
        SettingsService(settings_path),
    )
    try:
        assert second._controller.techniques.active_id == "ftir"
        assert second.technique_combo.currentData() == "ftir"
        assert second.panel_stack.currentWidget() is second._panels["ftir"]
    finally:
        second.close()


def test_switching_techniques_preserves_each_panel_display(
    app: QApplication, tmp_path: Path
) -> None:
    epr_source = _write_asc(tmp_path / "epr.ASC")
    ftir_source = _write_csv(
        tmp_path / "ftir.csv", [(4000.0, 0.1), (3999.0, 0.2)]
    )
    window = _window()
    window.technique_combo.setCurrentIndex(
        window.technique_combo.findData("epr")
    )
    assert window.open_file(epr_source)
    epr_display = window.current_display
    ftir_panel = _ftir_panel(window)
    assert ftir_panel.import_file(
        ftir_source,
        _options(
            mapping=ColumnMapping(
                x=0, y=1, x_unit="cm^-1", y_semantics="absorbance"
            )
        ),
    )
    ftir_display = window.current_display
    assert ftir_display is not epr_display

    window.technique_combo.setCurrentIndex(
        window.technique_combo.findData("epr")
    )
    assert window.current_display is epr_display
    window.technique_combo.setCurrentIndex(
        window.technique_combo.findData("ftir")
    )
    assert window.current_display is ftir_display
    window.close()
