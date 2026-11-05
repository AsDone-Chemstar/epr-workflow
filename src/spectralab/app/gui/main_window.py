"""Generic SpectraLab main window and technique panel host."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from spectralab.app.gui.controller import ApplicationController, ControllerError
from spectralab.app.gui.file_filter import build_file_filter
from spectralab.app.gui.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    TranslationError,
    Translator,
    normalize_language,
)
from spectralab.app.gui.metadata_view import MetadataView
from spectralab.app.gui.settings import GuiSettings, SettingsError, SettingsService
from spectralab.app.gui.status import StatusError, StatusEvent, status_from_payload
from spectralab.app.gui.status_view import StatusView
from spectralab.app.gui.technique import TechniquePanelProtocol


class MainWindow(QMainWindow):
    """Thin generic shell. Concrete techniques are supplied by the registry."""

    def __init__(
        self,
        controller: ApplicationController,
        translator: Translator | None = None,
        settings_service: SettingsService | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        if not isinstance(controller, ApplicationController):
            raise ControllerError("MainWindow requires an ApplicationController.")
        self._controller = controller
        self._translator = translator or Translator()
        self._settings_service = settings_service or SettingsService(None)
        self._settings = self._settings_service.load()
        self._translator.set_language(self._settings.language)
        self._register_translations()

        self._panels: dict[str, QWidget] = {}
        self._display = None
        self._status = StatusEvent(level="info", key="app.status_ready")

        self._build_ui()
        self._initialise_techniques()
        self.resize(
            self._settings.window_width,
            self._settings.window_height,
        )
        self._retranslate()

    # ------------------------------------------------------------------ setup
    def _register_translations(self) -> None:
        for descriptor in self._controller.techniques.descriptors:
            try:
                self._translator.register_catalog(
                    descriptor.translations,
                    source=descriptor.id,
                )
            except TranslationError as exc:
                raise ControllerError(
                    f"Technique translation catalog is invalid: {exc}",
                    code="invalid_translation_catalog",
                    context={"technique_id": descriptor.id},
                ) from exc

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top = QHBoxLayout()
        self.technique_label = QLabel()
        top.addWidget(self.technique_label)
        self.technique_combo = QComboBox()
        self.technique_combo.currentIndexChanged.connect(
            self._on_technique_selected
        )
        top.addWidget(self.technique_combo)

        self.open_button = QPushButton()
        self.open_button.clicked.connect(self._choose_file)
        top.addWidget(self.open_button)

        top.addStretch(1)
        self.language_label = QLabel()
        top.addWidget(self.language_label)
        self.language_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.language_combo.addItem(name, code)
        self.language_combo.currentIndexChanged.connect(
            self._on_language_selected
        )
        top.addWidget(self.language_combo)
        root.addLayout(top)

        splitter = QSplitter(Qt.Horizontal, self)
        self.metadata_group = QGroupBox()
        metadata_layout = QVBoxLayout(self.metadata_group)
        self.metadata_view = MetadataView(self._translator)
        metadata_layout.addWidget(self.metadata_view)
        splitter.addWidget(self.metadata_group)

        self.panel_stack = QStackedWidget()
        splitter.addWidget(self.panel_stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 800])
        root.addWidget(splitter, stretch=1)

        self.status_view = StatusView(self._translator)
        root.addWidget(self.status_view)

    def _initialise_techniques(self) -> None:
        ids = self._controller.techniques.ids
        self.technique_combo.blockSignals(True)
        for technique_id in ids:
            descriptor = self._controller.techniques.get(technique_id)
            self.technique_combo.addItem(
                self._translator.tr(descriptor.display_name_key),
                technique_id,
            )
        preferred = self._settings.active_technique
        if preferred not in ids:
            preferred = ids[0] if ids else None
        self.technique_combo.blockSignals(False)

        if preferred is not None:
            self._activate_technique(preferred, persist=False)
        else:
            self._set_status(
                StatusEvent(level="error", key="app.no_technique")
            )
            self._sync_language_combo()

    # ------------------------------------------------------------- techniques
    def _panel_for(self, technique_id: str) -> QWidget:
        panel = self._panels.get(technique_id)
        if panel is not None:
            return panel
        descriptor = self._controller.techniques.get(technique_id)
        panel = descriptor.panel_factory(self._controller, self._translator)
        if (
            not isinstance(panel, QWidget)
            or not isinstance(panel, TechniquePanelProtocol)
        ):
            raise ControllerError(
                f"Technique {technique_id!r} returned an invalid panel.",
                code="invalid_technique_panel",
                context={"technique_id": technique_id},
            )
        self._panels[technique_id] = panel
        self.panel_stack.addWidget(panel)
        panel.spectrum_changed.connect(self._on_spectrum_changed)
        panel.status_event.connect(self._on_panel_status)
        panel.retranslate()
        return panel

    def _activate_technique(
        self,
        technique_id: str,
        *,
        persist: bool = True,
    ) -> bool:
        try:
            descriptor = self._controller.select_technique(technique_id)
            panel = self._panel_for(technique_id)
        except Exception as exc:
            self._set_status(
                StatusEvent(
                    level="error",
                    key="app.no_panel",
                    params={"error": str(exc)},
                )
            )
            return False

        self.panel_stack.setCurrentWidget(panel)
        index = self.technique_combo.findData(technique_id)
        if index >= 0:
            self.technique_combo.blockSignals(True)
            self.technique_combo.setCurrentIndex(index)
            self.technique_combo.blockSignals(False)
        display = panel.current_display()
        self._display = display
        self.metadata_view.set_display(display)
        if persist:
            self._settings = self._settings.with_technique(descriptor.id)
            self._save_settings()
        return True

    def _on_technique_selected(self, index: int) -> None:
        technique_id = self.technique_combo.itemData(index)
        if isinstance(technique_id, str):
            self._activate_technique(technique_id)

    # ------------------------------------------------------------------ files
    def _choose_file(self) -> None:
        descriptor = self._controller.active_technique
        if descriptor is None:
            self._set_status(StatusEvent(level="error", key="app.no_technique"))
            return
        file_filter = build_file_filter(
            self._translator,
            descriptor.file_patterns,
        )
        filename, _selected = QFileDialog.getOpenFileName(
            self,
            self._translator.tr("app.open_dialog_title"),
            "",
            file_filter,
        )
        if filename:
            self.open_file(filename)

    def open_file(self, path: str | Path) -> bool:
        technique_id = self._controller.techniques.active_id
        if technique_id is None:
            self._set_status(StatusEvent(level="error", key="app.no_technique"))
            return False
        try:
            panel = self._panel_for(technique_id)
            succeeded = panel.open_file(Path(path))
            return bool(succeeded)
        except Exception as exc:
            self._set_status(
                StatusEvent(
                    level="error",
                    key="app.open_failed",
                    params={"error": str(exc)},
                )
            )
            return False

    def _on_spectrum_changed(self, display) -> None:
        self._display = display
        self.metadata_view.set_display(display)

    def _on_panel_status(self, payload) -> None:
        try:
            event = status_from_payload(payload)
        except (StatusError, KeyError, TypeError, ValueError) as exc:
            event = StatusEvent(
                level="error",
                text=f"Invalid panel status: {exc}",
            )
        self._set_status(event)

    # -------------------------------------------------------------- language
    def _on_language_selected(self, index: int) -> None:
        language = self.language_combo.itemData(index)
        if isinstance(language, str):
            self.set_language(language)

    def set_language(self, language: str) -> None:
        code = normalize_language(language)
        if code != self._translator.language:
            self._translator.set_language(code)
        index = self.language_combo.findData(self._translator.language)
        if index >= 0:
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(index)
            self.language_combo.blockSignals(False)
        self._settings = self._settings.with_language(self._translator.language)
        self._save_settings()
        self._retranslate()

    def _sync_language_combo(self) -> None:
        index = self.language_combo.findData(self._translator.language)
        if index >= 0:
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(index)
            self.language_combo.blockSignals(False)

    def _retranslate(self) -> None:
        self.setWindowTitle(self._translator.tr("app.title"))
        self.technique_label.setText(self._translator.tr("app.technique"))
        self.open_button.setText(self._translator.tr("app.open_file"))
        self.language_label.setText(self._translator.tr("app.language"))
        self.metadata_group.setTitle(self._translator.tr("app.metadata"))
        for index in range(self.technique_combo.count()):
            technique_id = self.technique_combo.itemData(index)
            if isinstance(technique_id, str):
                descriptor = self._controller.techniques.get(technique_id)
                self.technique_combo.setItemText(
                    index,
                    self._translator.tr(descriptor.display_name_key),
                )
        self._sync_language_combo()
        self.metadata_view.retranslate()
        self.status_view.retranslate()
        for panel in self._panels.values():
            panel.retranslate()

    # ---------------------------------------------------------------- status
    def _set_status(self, event: StatusEvent) -> None:
        self._status = event
        self.status_view.set_event(event)

    @property
    def status_event(self) -> StatusEvent:
        return self._status

    @property
    def current_display(self):
        return self._display

    # -------------------------------------------------------------- settings
    def _save_settings(self) -> None:
        try:
            self._settings = GuiSettings(
                language=self._translator.language,
                active_technique=self._controller.techniques.active_id,
                window_width=max(self.width(), 1),
                window_height=max(self.height(), 1),
            )
            self._settings_service.save(self._settings)
        except SettingsError as exc:
            self._set_status(
                StatusEvent(
                    level="warning",
                    text=f"Could not save GUI settings: {exc}",
                )
            )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._save_settings()
        super().closeEvent(event)


__all__ = ["MainWindow"]
