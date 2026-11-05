"""Qt metadata view backed by the generic metadata formatter."""

from __future__ import annotations

from PySide6.QtWidgets import QPlainTextEdit

from spectralab.app.gui.i18n import Translator
from spectralab.app.gui.metadata import format_metadata


class MetadataView(QPlainTextEdit):
    """Read-only metadata pane for Spectrum1D/ProcessedSpectrum."""

    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._display = None
        self.setReadOnly(True)
        self.setMinimumWidth(280)
        self.retranslate()

    @property
    def display(self):
        return self._display

    def set_display(self, display) -> None:
        self._display = display
        self.retranslate()

    def retranslate(self) -> None:
        if self._display is None:
            self.setPlainText(self._translator.tr("app.metadata_empty"))
            return
        self.setPlainText(format_metadata(self._display, self._translator))


__all__ = ["MetadataView"]
