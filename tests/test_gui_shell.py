"""Headless tests for the generic SpectraLab GUI shell and EPR panel."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402
from PySide6.QtCore import Signal  # noqa: E402

from spectralab.app.gui.app import build_controller, build_technique_registry  # noqa: E402
from spectralab.app.gui.controller import ApplicationController  # noqa: E402
from spectralab.app.gui.i18n import Translator  # noqa: E402
from spectralab.app.gui.main_window import MainWindow  # noqa: E402
from spectralab.app.gui.settings import SettingsService  # noqa: E402
from spectralab.app.gui.technique import (  # noqa: E402
    TechniqueDescriptor,
    TechniqueRegistry,
)
from spectralab.core.importers import ImporterRegistry  # noqa: E402
from spectralab.core.processing import ProcessedSpectrum  # noqa: E402

HEADER = "     index           Field [G]        Intensity []\n\n"


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _write_asc(path: Path, n: int = 21) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [f"{i + 1} {i * 0.5} {10.0 + i * 2.0}" for i in range(n)]
    path.write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DummyPanel(QWidget):
    spectrum_changed = Signal(object)
    status_event = Signal(object)

    def __init__(self, controller, translator, label_key="dummy.label", parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._label_key = label_key
        self._display = None
        self.label = QLabel(parent=self)
        self.retranslate()

    def open_file(self, path: Path) -> bool:
        self.status_event.emit(
            {
                "level": "info",
                "key": "dummy.loaded",
                "params": {"name": Path(path).name},
            }
        )
        return True

    def retranslate(self) -> None:
        self.label.setText(self._translator.tr(self._label_key))

    def current_display(self):
        return self._display


def _dummy_registry() -> TechniqueRegistry:
    registry = TechniqueRegistry()
    registry.register(
        TechniqueDescriptor(
            id="dummy.one",
            display_name_key="dummy.one",
            panel_factory=lambda c, t: DummyPanel(c, t, "dummy.one.label"),
            file_patterns=("*.fake",),
            translations={
                "zh": {
                    "dummy.one": "测试技术一",
                    "dummy.one.label": "一",
                    "dummy.loaded": "已加载 {name}",
                },
                "en": {
                    "dummy.one": "Dummy Technique One",
                    "dummy.one.label": "One",
                    "dummy.loaded": "Loaded {name}",
                },
            },
        )
    )
    registry.register(
        TechniqueDescriptor(
            id="dummy.two",
            display_name_key="dummy.two",
            panel_factory=lambda c, t: DummyPanel(c, t, "dummy.two.label"),
            file_patterns=("*.fake",),
            translations={
                "zh": {
                    "dummy.two": "测试技术二",
                    "dummy.two.label": "二",
                    "dummy.loaded": "已加载 {name}",
                },
                "en": {
                    "dummy.two": "Dummy Technique Two",
                    "dummy.two.label": "Two",
                    "dummy.loaded": "Loaded {name}",
                },
            },
        )
    )
    return registry


def _dummy_window() -> MainWindow:
    controller = ApplicationController(_dummy_registry(), importers=ImporterRegistry())
    return MainWindow(
        controller,
        Translator("zh"),
        SettingsService(None),
    )


def _epr_window(settings_service: SettingsService | None = None, language="zh"):
    return MainWindow(
        build_controller(),
        Translator(language),
        settings_service or SettingsService(None),
    )


# --------------------------------------------------------------------------
# Generic shell and dummy technique
# --------------------------------------------------------------------------
def test_dummy_techniques_register_and_switch_without_shell_changes(
    app: QApplication,
) -> None:
    window = _dummy_window()

    assert window.technique_combo.count() == 2
    assert window.technique_combo.currentData() == "dummy.one"
    assert window._controller.techniques.active_id == "dummy.one"
    first = window._panels["dummy.one"]
    assert window.panel_stack.currentWidget() is first

    index = window.technique_combo.findData("dummy.two")
    window.technique_combo.setCurrentIndex(index)

    assert window._controller.techniques.active_id == "dummy.two"
    assert window.panel_stack.currentWidget() is window._panels["dummy.two"]
    assert window._panels["dummy.two"].label.text() == "二"
    window.close()


def test_generic_shell_language_switch_updates_dummy_panels(
    app: QApplication,
) -> None:
    window = _dummy_window()
    window._panels["dummy.one"].label.setText("一")

    window.set_language("en")

    assert window._translator.language == "en"
    assert window.technique_combo.itemText(0) == "Dummy Technique One"
    assert window._panels["dummy.one"].label.text() == "One"
    assert "Metadata" in window.metadata_group.title()

    window.set_language("zh")
    assert window._panels["dummy.one"].label.text() == "一"
    window.close()


def test_dummy_panel_open_status_is_displayed(app: QApplication, tmp_path: Path) -> None:
    window = _dummy_window()
    fake = tmp_path / "sample.fake"
    fake.write_text("fake", encoding="utf-8")

    assert window.open_file(fake) is True
    assert window.status_event.level == "info"
    assert window.status_event.key == "dummy.loaded"
    assert "sample.fake" in window.status_view.text()
    window.close()


# --------------------------------------------------------------------------
# EPR integration
# --------------------------------------------------------------------------
def test_epr_import_and_raw_plot(app: QApplication, tmp_path: Path) -> None:
    source = _write_asc(tmp_path / "epr.ASC")
    before = _sha256(source)
    window = _epr_window()
    assert window.technique_combo.count() == 2
    assert window.technique_combo.currentData() == "epr"

    assert window.open_file(source) is True

    panel = window._panels["epr"]
    display = window.current_display
    assert display is not None
    assert display.point_count == 21
    assert window.metadata_view.toPlainText() != ""
    assert "点数：21" in window.metadata_view.toPlainText()
    assert panel.processing_session is not None
    assert panel.processing_session.history == ()
    assert panel.axes.get_xlabel() == "Magnetic field (G)"
    assert panel.axes.get_ylabel() == "Intensity"
    assert len(panel.axes.lines) == 1
    assert panel.axes.lines[0].get_label() == "原始"
    assert window.status_event.level == "success"
    assert _sha256(source) == before
    window.close()


def test_epr_real_bes3t_import_when_available(app: QApplication) -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "Test data"
        / "BSA3mal1h.DSC"
    )
    if not source.is_file():
        pytest.skip(f"local BES3T dataset not present: {source}")

    window = _epr_window()
    assert window.open_file(source) is True
    panel = window._panels["epr"]
    assert panel.current_display().point_count == 1024
    assert len(panel.axes.lines) == 1
    window.close()


def test_epr_explicit_processing_undo_redo_reset(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_asc(tmp_path / "process.ASC")
    window = _epr_window()
    assert window.open_file(source)
    panel = window._panels["epr"]
    session = panel.processing_session
    assert session is not None
    assert isinstance(window.current_display, type(session.source))
    assert len(panel.axes.lines) == 1

    panel.left_start.setText("0.0")
    panel.left_end.setText("1.0")
    panel.right_start.setText("9.0")
    panel.right_end.setText("10.0")
    panel._apply_baseline()

    assert isinstance(window.current_display, ProcessedSpectrum)
    assert len(session.history) == 1
    assert len(panel.axes.lines) == 2
    assert "处理历史：1 步" in window.metadata_view.toPlainText()
    assert window.status_event.level == "success"

    panel._undo()
    assert len(session.history) == 0
    assert window.current_display is panel._source
    assert len(panel.axes.lines) == 1

    panel._redo()
    assert len(session.history) == 1
    assert isinstance(window.current_display, ProcessedSpectrum)

    panel._reset()
    assert len(session.history) == 0
    assert window.current_display is panel._source
    assert len(panel.axes.lines) == 1
    window.close()


def test_epr_invalid_parameters_are_reported_without_session_change(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_asc(tmp_path / "badparams.ASC")
    window = _epr_window()
    assert window.open_file(source)
    panel = window._panels["epr"]
    session = panel.processing_session
    assert session is not None

    panel._apply_baseline()

    assert window.status_event.level == "error"
    assert panel.current_display() is panel._source
    assert session.history == ()
    assert len(panel.axes.lines) == 1
    window.close()


def test_epr_import_failure_is_reported(app: QApplication, tmp_path: Path) -> None:
    bad = tmp_path / "bad.ASC"
    bad.write_text("not a spectrum\n", encoding="utf-8")
    window = _epr_window()
    assert window.open_file(bad) is False
    assert window.status_event.level == "error"
    assert window.current_display is None
    assert "导入失败" in window.status_view.text()
    window.close()


def test_epr_language_switch_updates_panel_labels_and_legend(
    app: QApplication, tmp_path: Path
) -> None:
    source = _write_asc(tmp_path / "language.ASC")
    window = _epr_window()
    assert window.open_file(source)
    panel = window._panels["epr"]
    assert panel.axes.lines[0].get_label() == "原始"

    window.set_language("en")

    assert panel.apply_baseline_btn.text() == "Apply linear baseline"
    assert panel.axes.lines[0].get_label() == "Raw"
    assert "Points: 21" in window.metadata_view.toPlainText()
    assert "Loaded 21 points" in window.status_view.text()

    window.set_language("zh")
    assert panel.axes.lines[0].get_label() == "原始"
    window.close()


# --------------------------------------------------------------------------
# Settings persistence
# --------------------------------------------------------------------------
def test_language_and_technique_persist_across_windows(
    app: QApplication, tmp_path: Path
) -> None:
    settings = SettingsService(tmp_path / "settings.json")
    first = _epr_window(settings)
    first.set_language("en")
    first.close()

    second = _epr_window(SettingsService(tmp_path / "settings.json"))
    assert second._translator.language == "en"
    assert second._controller.techniques.active_id == "epr"
    assert second.windowTitle() == second._translator.tr("app.title")
    second.close()


def test_malformed_settings_do_not_break_window(
    app: QApplication, tmp_path: Path
) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{bad", encoding="utf-8")
    window = _epr_window(SettingsService(path))
    assert window._translator.language == "zh"
    assert window.technique_combo.count() == 2
    window.close()


def test_main_window_requires_controller(app: QApplication) -> None:
    with pytest.raises(Exception):
        MainWindow("not a controller")  # type: ignore[arg-type]
