"""Explicit FTIR file-selection and import-options dialog."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from spectralab.app.gui.file_filter import build_file_filter
from spectralab.app.gui.ftir_options_widget import FtirOptionsWidget
from spectralab.app.gui.ftir_translations import FTIR_FILE_PATTERNS
from spectralab.app.gui.i18n import Translator
from spectralab.techniques.ftir import FTIRImportOptions


class FtirImportDialog(QDialog):
    """Select one FTIR file and configure every M9 import option explicitly."""

    def __init__(
        self,
        translator: Translator,
        path: str | Path | None = None,
        *,
        options: FTIRImportOptions | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator
        self._error_key: str | None = None
        self._error_params: dict[str, Any] = {}
        self._build_ui()
        if path is not None:
            self.set_path(path)
        if options is not None:
            self.options_widget.set_options(options)
        self.retranslate()

    def _t(self, key: str, **params: Any) -> str:
        return self._translator.tr(key, **params)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        file_row = QHBoxLayout()
        self.file_label = QLabel()
        file_row.addWidget(self.file_label)
        self.path_edit = QLineEdit()
        file_row.addWidget(self.path_edit, 1)
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._browse)
        file_row.addWidget(self.browse_button)
        layout.addLayout(file_row)

        self.options_widget = FtirOptionsWidget(self._translator)
        layout.addWidget(self.options_widget, 1)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #c62828;")
        layout.addWidget(self.error_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.resize(820, 560)

    # -------------------------------------------------------------- language
    def _set_error(self, key: str, **params: Any) -> None:
        self._error_key = key
        self._error_params = dict(params)
        self.error_label.setText(self._t(key, **params))

    def _clear_error(self) -> None:
        self._error_key = None
        self._error_params = {}
        self.error_label.clear()

    def retranslate(self) -> None:
        self.setWindowTitle(self._t("ftir.import_dialog_title"))
        self.file_label.setText(self._t("ftir.file_label"))
        self.browse_button.setText(self._t("ftir.browse"))
        self.options_widget.retranslate()
        ok = self.buttons.button(QDialogButtonBox.Ok)
        cancel = self.buttons.button(QDialogButtonBox.Cancel)
        if ok is not None:
            ok.setText(self._t("ftir.ok"))
        if cancel is not None:
            cancel.setText(self._t("ftir.cancel"))
        if self._error_key is not None:
            self.error_label.setText(
                self._t(self._error_key, **self._error_params)
            )

    # ------------------------------------------------------------------ file
    def _file_filter(self) -> str:
        return build_file_filter(self._translator, FTIR_FILE_PATTERNS)

    def _browse(self) -> None:
        start = self.path_edit.text().strip()
        directory = str(Path(start).parent) if start else ""
        filename, _selected = QFileDialog.getOpenFileName(
            self,
            self._t("ftir.choose_file_title"),
            directory,
            self._file_filter(),
        )
        if filename:
            self.path_edit.setText(filename)
            self._clear_error()

    def set_path(self, path: str | Path) -> None:
        self.path_edit.setText(str(path))

    def selected_path(self) -> Path | None:
        value = self.path_edit.text().strip()
        return Path(value) if value else None

    def selected_options(self) -> FTIRImportOptions:
        return self.options_widget.options_from_ui()

    def accept(self) -> None:  # noqa: D401 - Qt API
        path = self.selected_path()
        if path is None or not path.is_file():
            self._set_error(
                "ftir.file_required",
                path=str(path) if path is not None else "",
            )
            return
        try:
            self.selected_options()
        except Exception as exc:
            self._set_error("ftir.options_invalid", error=str(exc))
            return
        self._clear_error()
        super().accept()


__all__ = ["FtirImportDialog"]
