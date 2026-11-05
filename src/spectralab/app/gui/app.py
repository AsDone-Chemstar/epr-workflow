"""Composition root and desktop entry point for the SpectraLab GUI."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from spectralab.app.gui.controller import ApplicationController
from spectralab.app.gui.epr_panel import create_panel
from spectralab.app.gui.epr_translations import (
    EPR_DISPLAY_NAME_KEY,
    EPR_FILE_PATTERNS,
    EPR_TECHNIQUE_ID,
    EPR_TRANSLATIONS,
)
from spectralab.app.gui.ftir_panel import create_panel as create_ftir_panel
from spectralab.app.gui.ftir_translations import (
    FTIR_DISPLAY_NAME_KEY,
    FTIR_FILE_PATTERNS,
    FTIR_TECHNIQUE_ID,
    FTIR_TRANSLATIONS,
)
from spectralab.app.gui.i18n import Translator
from spectralab.app.gui.main_window import MainWindow
from spectralab.app.gui.settings import GuiSettings, SettingsService
from spectralab.app.gui.technique import TechniqueDescriptor, TechniqueRegistry

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SETTINGS_PATH = (
    PROJECT_ROOT / "config" / "spectralab_gui_settings.json"
)


def build_technique_registry() -> TechniqueRegistry:
    """Explicitly register the techniques shipped in this milestone."""
    registry = TechniqueRegistry()
    registry.register(
        TechniqueDescriptor(
            id=EPR_TECHNIQUE_ID,
            display_name_key=EPR_DISPLAY_NAME_KEY,
            panel_factory=create_panel,
            file_patterns=EPR_FILE_PATTERNS,
            translations=EPR_TRANSLATIONS,
        )
    )
    registry.register(
        TechniqueDescriptor(
            id=FTIR_TECHNIQUE_ID,
            display_name_key=FTIR_DISPLAY_NAME_KEY,
            panel_factory=create_ftir_panel,
            file_patterns=FTIR_FILE_PATTERNS,
            translations=FTIR_TRANSLATIONS,
        )
    )
    return registry


def build_controller() -> ApplicationController:
    return ApplicationController(build_technique_registry())


def build_main_window(
    *,
    settings_service: SettingsService | None = None,
) -> MainWindow:
    settings = settings_service or SettingsService(DEFAULT_SETTINGS_PATH)
    loaded: GuiSettings = settings.load()
    translator = Translator(loaded.language)
    controller = build_controller()
    return MainWindow(controller, translator, settings)


def main(argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(
        argv if argv is not None else sys.argv
    )
    window = build_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
