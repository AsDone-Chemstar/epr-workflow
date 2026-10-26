"""Small dialog for PNG plot-export options.

The dialog only collects display/export choices. Rendering is performed by
:func:`epr_workflow.plot_export.export_plot_png` after the dialog is accepted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from epr_workflow.plot_export import (
    MAX_DPI,
    MAX_FIGURE_INCH,
    MIN_DPI,
    MIN_FIGURE_INCH,
    PlotExportSettings,
)

#: Translation keys consumed by :meth:`PlotExportDialog.set_texts` and the
#: constructor.
TEXT_KEYS = (
    "plot_export_dialog_title",
    "plot_export_width",
    "plot_export_height",
    "plot_export_dpi",
    "plot_export_include_title",
    "plot_export_include_legend",
    "plot_export_path",
    "plot_export_browse",
    "plot_export_overwrite",
    "plot_export_invalid_path",
    "plot_export_ok",
)


class PlotExportDialog(QDialog):
    """Collect figure size, DPI, title/legend inclusion and output path."""

    def __init__(
        self,
        parent=None,
        *,
        texts: Mapping[str, str],
        default_path: str | Path,
        options: PlotExportSettings | None = None,
        overwrite: bool = False,
    ) -> None:
        super().__init__(parent)
        self._texts = dict(texts)
        self._options = options or PlotExportSettings()
        self.setWindowTitle(self._texts["plot_export_dialog_title"])
        self._build_ui(Path(default_path), overwrite)

    def _build_ui(self, default_path: Path, overwrite: bool) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(MIN_FIGURE_INCH, MAX_FIGURE_INCH)
        self.width_spin.setDecimals(2)
        self.width_spin.setSingleStep(0.5)
        self.width_spin.setSuffix(" in")
        self.width_spin.setValue(self._options.width_in)
        self.width_label = QLabel(self._texts["plot_export_width"])
        form.addRow(self.width_label, self.width_spin)

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(MIN_FIGURE_INCH, MAX_FIGURE_INCH)
        self.height_spin.setDecimals(2)
        self.height_spin.setSingleStep(0.5)
        self.height_spin.setSuffix(" in")
        self.height_spin.setValue(self._options.height_in)
        self.height_label = QLabel(self._texts["plot_export_height"])
        form.addRow(self.height_label, self.height_spin)

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(MIN_DPI, MAX_DPI)
        self.dpi_spin.setSingleStep(50)
        self.dpi_spin.setSuffix(" dpi")
        self.dpi_spin.setValue(self._options.dpi)
        self.dpi_label = QLabel(self._texts["plot_export_dpi"])
        form.addRow(self.dpi_label, self.dpi_spin)

        self.include_title_check = QCheckBox(
            self._texts["plot_export_include_title"]
        )
        self.include_title_check.setChecked(self._options.include_title)
        form.addRow(self.include_title_check)

        self.include_legend_check = QCheckBox(
            self._texts["plot_export_include_legend"]
        )
        self.include_legend_check.setChecked(self._options.include_legend)
        form.addRow(self.include_legend_check)

        self.path_edit = QLineEdit(str(default_path))
        self.path_edit.setMinimumWidth(320)
        self.browse_btn = QPushButton(self._texts["plot_export_browse"])
        self.browse_btn.clicked.connect(self._browse)
        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.addWidget(self.path_edit, stretch=1)
        path_row.addWidget(self.browse_btn)
        self.path_label = QLabel(self._texts["plot_export_path"])
        form.addRow(self.path_label, path_row)

        self.overwrite_check = QCheckBox(
            self._texts["plot_export_overwrite"]
        )
        self.overwrite_check.setChecked(bool(overwrite))
        form.addRow(self.overwrite_check)

        layout.addLayout(form)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #c62828;")
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if self.ok_button is not None:
            self.ok_button.setText(self._texts["plot_export_ok"])
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._texts["plot_export_dialog_title"],
            self.path_edit.text(),
            "PNG (*.png);;All Files (*.*)",
        )
        if path:
            self.path_edit.setText(path)

    def output_path(self) -> Path:
        return Path(self.path_edit.text().strip())

    def overwrite(self) -> bool:
        return self.overwrite_check.isChecked()

    def export_settings(self) -> PlotExportSettings:
        return PlotExportSettings(
            width_in=float(self.width_spin.value()),
            height_in=float(self.height_spin.value()),
            dpi=int(self.dpi_spin.value()),
            include_title=self.include_title_check.isChecked(),
            include_legend=self.include_legend_check.isChecked(),
        )

    def accept(self) -> None:  # noqa: D401 - Qt override
        text = self.path_edit.text().strip()
        if not text or Path(text).suffix.lower() != ".png":
            self.error_label.setText(self._texts["plot_export_invalid_path"])
            return
        super().accept()
