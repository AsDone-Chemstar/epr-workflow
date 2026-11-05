"""Small status label used by the generic GUI shell."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from spectralab.app.gui.i18n import Translator
from spectralab.app.gui.status import StatusEvent

STATUS_COLORS = {
    "success": "#1e7d32",
    "info": "#1f4e79",
    "warning": "#b26a00",
    "error": "#c62828",
}


class StatusView(QLabel):
    """A colored, word-wrapped status message."""

    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._event = StatusEvent(level="info", key="app.status_ready")
        self.setWordWrap(True)
        self.retranslate()

    @property
    def event(self) -> StatusEvent:
        return self._event

    def set_event(self, event: StatusEvent) -> None:
        self._event = event
        self.retranslate()

    def retranslate(self) -> None:
        level = self._translator.tr(f"status.{self._event.level}")
        message = self._event.message(self._translator)
        self.setText(f"{level}: {message}")
        self.setStyleSheet(
            f"color: {STATUS_COLORS.get(self._event.level, '#333333')};"
        )


__all__ = ["STATUS_COLORS", "StatusView"]
