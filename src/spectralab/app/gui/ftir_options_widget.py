"""Reusable explicit FTIR import-options editor.

The widget only builds an :class:`FTIRImportOptions` object. Parsing and all
scientific validation remain in the Qt-free M9 backend.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from spectralab.app.gui.i18n import Translator
from spectralab.techniques.ftir import (
    ColumnMapping,
    FTIRImportOptions,
    parse_column_reference,
)

_DELIMITER_ITEMS = (
    ("ftir.delimiter_auto", "auto"),
    ("ftir.delimiter_comma", ","),
    ("ftir.delimiter_tab", "\t"),
    ("ftir.delimiter_semicolon", ";"),
    ("ftir.delimiter_whitespace", "whitespace"),
    ("ftir.delimiter_custom", "custom"),
)
_DECIMAL_ITEMS = (
    ("ftir.decimal_dot", "."),
    ("ftir.decimal_comma", ","),
)
_QUANTITY_ITEMS = (
    ("ftir.quantity_unknown", "unknown"),
    ("ftir.quantity_wavenumber", "wavenumber"),
)
_UNIT_ITEMS = (
    ("ftir.unit_unknown", "unknown"),
    ("ftir.unit_cm_inverse", "cm^-1"),
)
_SEMANTICS_ITEMS = (
    ("ftir.semantics_unknown", "unknown"),
    ("ftir.semantics_absorbance", "absorbance"),
    ("ftir.semantics_transmittance", "transmittance"),
)
_ACQUISITION_ITEMS = (
    ("ftir.acq_unknown", "Unknown"),
    ("ftir.acq_atr", "ATR"),
    ("ftir.acq_transmission", "Transmission"),
)
_ATR_ITEMS = (
    ("ftir.atr_unknown", "unknown"),
    ("ftir.atr_applied", "applied"),
    ("ftir.atr_not_applied", "not_applied"),
    ("ftir.atr_not_applicable", "not_applicable"),
)


def _optional_text(text: str) -> str | None:
    value = text.strip()
    return value or None


class FtirOptionsWidget(QWidget):
    """Explicit column, parsing and FTIR metadata controls."""

    def __init__(self, translator: Translator, parent=None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._build_ui()
        self.retranslate()

    def _t(self, key: str, **params: Any) -> str:
        return self._translator.tr(key, **params)

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.columns_group = QGroupBox()
        columns_form = QFormLayout(self.columns_group)
        self.x_column_label = QLabel()
        self.x_column = QLineEdit()
        columns_form.addRow(self.x_column_label, self.x_column)
        self.y_column_label = QLabel()
        self.y_column = QLineEdit()
        columns_form.addRow(self.y_column_label, self.y_column)

        self.header = QCheckBox()
        columns_form.addRow(self.header)

        self.delimiter_label = QLabel()
        delimiter_row = QWidget()
        delimiter_layout = QHBoxLayout(delimiter_row)
        delimiter_layout.setContentsMargins(0, 0, 0, 0)
        self.delimiter = QComboBox()
        self.delimiter.currentIndexChanged.connect(self._on_delimiter_changed)
        delimiter_layout.addWidget(self.delimiter, 1)
        self.custom_delimiter = QLineEdit()
        self.custom_delimiter.setMaxLength(1)
        delimiter_layout.addWidget(self.custom_delimiter)
        columns_form.addRow(self.delimiter_label, delimiter_row)

        self.decimal_label = QLabel()
        self.decimal = QComboBox()
        columns_form.addRow(self.decimal_label, self.decimal)

        self.comment_label = QLabel()
        self.comment = QLineEdit()
        columns_form.addRow(self.comment_label, self.comment)

        self.encoding_label = QLabel()
        self.encoding = QComboBox()
        self.encoding.setEditable(True)
        for value in ("utf-8-sig", "utf-8", "utf-16", "latin-1", "cp1252"):
            self.encoding.addItem(value, value)
        columns_form.addRow(self.encoding_label, self.encoding)

        self.skip_rows_label = QLabel()
        self.skip_rows = QSpinBox()
        self.skip_rows.setRange(0, 10_000_000)
        columns_form.addRow(self.skip_rows_label, self.skip_rows)

        self.metadata_group = QGroupBox()
        metadata_form = QFormLayout(self.metadata_group)
        self.x_name_label = QLabel()
        self.x_name = QLineEdit()
        metadata_form.addRow(self.x_name_label, self.x_name)
        self.y_name_label = QLabel()
        self.y_name = QLineEdit()
        metadata_form.addRow(self.y_name_label, self.y_name)

        self.x_quantity_label = QLabel()
        self.x_quantity = QComboBox()
        metadata_form.addRow(self.x_quantity_label, self.x_quantity)
        self.x_unit_label = QLabel()
        self.x_unit = QComboBox()
        metadata_form.addRow(self.x_unit_label, self.x_unit)

        self.y_semantics_label = QLabel()
        self.y_semantics = QComboBox()
        metadata_form.addRow(self.y_semantics_label, self.y_semantics)
        self.y_unit_label = QLabel()
        self.y_unit = QLineEdit()
        metadata_form.addRow(self.y_unit_label, self.y_unit)

        self.acquisition_mode_label = QLabel()
        self.acquisition_mode = QComboBox()
        metadata_form.addRow(self.acquisition_mode_label, self.acquisition_mode)
        self.atr_status_label = QLabel()
        self.atr_status = QComboBox()
        metadata_form.addRow(self.atr_status_label, self.atr_status)

        self.instrument_vendor_label = QLabel()
        self.instrument_vendor = QLineEdit()
        metadata_form.addRow(self.instrument_vendor_label, self.instrument_vendor)
        self.instrument_model_label = QLabel()
        self.instrument_model = QLineEdit()
        metadata_form.addRow(self.instrument_model_label, self.instrument_model)

        layout.addWidget(self.columns_group, 1)
        layout.addWidget(self.metadata_group, 1)
        self._on_delimiter_changed()

    # ------------------------------------------------------------- language
    def _repopulate(
        self,
        combo: QComboBox,
        items: tuple[tuple[str, str], ...],
    ) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for key, value in items:
            combo.addItem(self._t(key), value)
        if current is not None:
            index = combo.findData(current)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def retranslate(self) -> None:
        self.columns_group.setTitle(self._t("ftir.columns_group"))
        self.metadata_group.setTitle(self._t("ftir.metadata_group"))
        self.x_column_label.setText(self._t("ftir.x_column"))
        self.y_column_label.setText(self._t("ftir.y_column"))
        self.x_column.setPlaceholderText(self._t("ftir.x_column_hint"))
        self.y_column.setPlaceholderText(self._t("ftir.y_column_hint"))
        self.header.setText(self._t("ftir.header"))
        self.delimiter_label.setText(self._t("ftir.delimiter"))
        self.custom_delimiter.setPlaceholderText(
            self._t("ftir.custom_delimiter_placeholder")
        )
        self.decimal_label.setText(self._t("ftir.decimal"))
        self.comment_label.setText(self._t("ftir.comment"))
        self.comment.setPlaceholderText(self._t("ftir.comment_hint"))
        self.encoding_label.setText(self._t("ftir.encoding"))
        self.skip_rows_label.setText(self._t("ftir.skip_rows"))
        self.x_name_label.setText(self._t("ftir.x_name"))
        self.y_name_label.setText(self._t("ftir.y_name"))
        self.x_quantity_label.setText(self._t("ftir.x_quantity"))
        self.x_unit_label.setText(self._t("ftir.x_unit"))
        self.y_semantics_label.setText(self._t("ftir.y_semantics"))
        self.y_unit_label.setText(self._t("ftir.y_unit"))
        self.acquisition_mode_label.setText(self._t("ftir.acquisition_mode"))
        self.atr_status_label.setText(self._t("ftir.atr_status"))
        self.instrument_vendor_label.setText(self._t("ftir.instrument_vendor"))
        self.instrument_model_label.setText(self._t("ftir.instrument_model"))

        self._repopulate(self.delimiter, _DELIMITER_ITEMS)
        self._repopulate(self.decimal, _DECIMAL_ITEMS)
        self._repopulate(self.x_quantity, _QUANTITY_ITEMS)
        self._repopulate(self.x_unit, _UNIT_ITEMS)
        self._repopulate(self.y_semantics, _SEMANTICS_ITEMS)
        self._repopulate(self.acquisition_mode, _ACQUISITION_ITEMS)
        self._repopulate(self.atr_status, _ATR_ITEMS)

    # --------------------------------------------------------------- options
    def _delimiter_value(self) -> str | None:
        selected = self.delimiter.currentData()
        if selected == "auto":
            return None
        if selected == "custom":
            value = self.custom_delimiter.text()
            if len(value) != 1:
                raise ValueError(
                    self._t("ftir.custom_delimiter_required")
                )
            return value
        return str(selected)

    def _comment_markers(self) -> tuple[str, ...] | None:
        tokens = self.comment.text().split()
        return tuple(tokens) if tokens else None

    def options_from_ui(self) -> FTIRImportOptions:
        encoding = self.encoding.currentText().strip()
        if not encoding:
            raise ValueError(self._t("ftir.options_invalid", error="encoding"))
        x_quantity = self.x_quantity.currentData()
        x_unit = self.x_unit.currentData()
        mapping = ColumnMapping(
            x=parse_column_reference(self.x_column.text()),
            y=parse_column_reference(self.y_column.text()),
            x_name=_optional_text(self.x_name.text()),
            x_unit=(
                "cm^-1"
                if x_unit == "cm^-1"
                else None
            ),
            x_quantity=(
                "wavenumber"
                if x_quantity == "wavenumber"
                else None
            ),
            y_name=_optional_text(self.y_name.text()),
            y_unit=_optional_text(self.y_unit.text()),
            y_semantics=str(self.y_semantics.currentData() or "unknown"),
            header=bool(self.header.isChecked()),
            delimiter=self._delimiter_value(),
            comment=self._comment_markers(),
            decimal=str(self.decimal.currentData() or "."),
            encoding=encoding,
            skip_rows=int(self.skip_rows.value()),
        )
        return FTIRImportOptions(
            mapping=mapping,
            acquisition_mode=str(
                self.acquisition_mode.currentData() or "Unknown"
            ),
            atr_correction_status=str(self.atr_status.currentData() or "unknown"),
            instrument_vendor=_optional_text(self.instrument_vendor.text()),
            instrument_model=_optional_text(self.instrument_model.text()),
        )

    def set_options(self, options: FTIRImportOptions) -> None:
        mapping = options.mapping
        self.x_column.setText("" if mapping.x is None else str(mapping.x))
        self.y_column.setText("" if mapping.y is None else str(mapping.y))
        self.x_name.setText(mapping.x_name or "")
        self.y_name.setText(mapping.y_name or "")
        self.header.setChecked(mapping.header)
        if mapping.delimiter is None:
            self._set_combo_data(self.delimiter, "auto")
            self.custom_delimiter.clear()
        elif mapping.delimiter == "whitespace":
            self._set_combo_data(self.delimiter, "whitespace")
            self.custom_delimiter.clear()
        else:
            known = {value for _key, value in _DELIMITER_ITEMS if len(value) == 1}
            if mapping.delimiter in known:
                self._set_combo_data(self.delimiter, mapping.delimiter)
                self.custom_delimiter.clear()
            else:
                self._set_combo_data(self.delimiter, "custom")
                self.custom_delimiter.setText(mapping.delimiter)
        self._set_combo_data(self.decimal, mapping.decimal)
        self.comment.setText(" ".join(mapping.comment_markers))
        index = self.encoding.findText(mapping.encoding)
        if index >= 0:
            self.encoding.setCurrentIndex(index)
        else:
            self.encoding.setEditText(mapping.encoding)
        self.skip_rows.setValue(mapping.skip_rows)
        self._set_combo_data(
            self.x_quantity,
            "wavenumber" if mapping.x_quantity == "wavenumber" else "unknown",
        )
        self._set_combo_data(
            self.x_unit,
            "cm^-1" if mapping.x_unit == "cm^-1" else "unknown",
        )
        self._set_combo_data(self.y_semantics, mapping.y_semantics)
        self.y_unit.setText(mapping.y_unit or "")
        self._set_combo_data(self.acquisition_mode, options.acquisition_mode)
        self._set_combo_data(
            self.atr_status, options.atr_correction_status
        )
        self.instrument_vendor.setText(options.instrument_vendor or "")
        self.instrument_model.setText(options.instrument_model or "")
        self._on_delimiter_changed()

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def set_effective_metadata(self, spectrum) -> None:
        """Reflect the explicitly resolved metadata returned by the backend."""
        axis = spectrum.axis
        signal = spectrum.raw_signal
        metadata = spectrum.metadata
        self._set_combo_data(
            self.x_quantity,
            "wavenumber" if axis.quantity == "wavenumber" else "unknown",
        )
        self._set_combo_data(
            self.x_unit,
            "cm^-1" if axis.unit == "cm^-1" else "unknown",
        )
        self.x_name.setText(axis.name or "")
        self._set_combo_data(self.y_semantics, signal.semantics)
        self.y_unit.setText(signal.unit or "")
        self.y_name.setText(signal.name or "")
        mode = metadata.acquisition.get("mode")
        if isinstance(mode, str):
            self._set_combo_data(self.acquisition_mode, mode)
        atr = metadata.acquisition.get("atr_correction_status")
        if isinstance(atr, str):
            self._set_combo_data(self.atr_status, atr)
        vendor = metadata.instrument.get("vendor")
        model = metadata.instrument.get("model")
        self.instrument_vendor.setText(vendor if isinstance(vendor, str) else "")
        self.instrument_model.setText(model if isinstance(model, str) else "")

    def _on_delimiter_changed(self) -> None:
        self.custom_delimiter.setEnabled(
            self.delimiter.currentData() == "custom"
        )


__all__ = ["FtirOptionsWidget"]
