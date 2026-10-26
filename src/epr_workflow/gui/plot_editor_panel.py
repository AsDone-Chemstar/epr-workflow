"""Qt panel for user-controlled plot styling.

The panel is a view over :mod:`epr_workflow.plot_settings`. It never touches
ASC files, preprocessing steps or scientific outputs: it only reports style
changes through Qt signals.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from epr_workflow.plot_settings import (
    CURVE_KEYS,
    DEFAULT_AXIS_FONTSIZE,
    DEFAULT_LEGEND_FONTSIZE,
    DEFAULT_TICK_FONTSIZE,
    DEFAULT_TITLE_FONTSIZE,
    LEGEND_LOCATIONS,
    LINE_STYLES,
    AxisSettings,
    PlotSettings,
    PlotSettingsError,
    normalize_color,
)

#: Translation keys consumed by :meth:`PlotEditorPanel.set_texts`.
TEXT_KEYS = (
    "plot_curves_label",
    "plot_curve_style_group",
    "plot_curve_name_label",
    "plot_curve_color",
    "plot_curve_width",
    "plot_curve_linestyle",
    "plot_axis_group",
    "plot_title_label",
    "plot_xlabel_label",
    "plot_ylabel_label",
    "plot_x_range_label",
    "plot_y_range_label",
    "plot_x_auto",
    "plot_y_auto",
    "plot_legend_visible",
    "plot_legend_location",
    "plot_font_group",
    "plot_font_title",
    "plot_font_axis",
    "plot_font_tick",
    "plot_font_legend",
    "plot_reset",
    "plot_restore_visibility",
    "plot_export",
    "plot_scope_note",
    "plot_error_color",
    "plot_error_axis_range",
    "plot_line_solid",
    "plot_line_dashed",
    "plot_line_dotted",
    "plot_line_dashdot",
    "plot_legend_best",
    "plot_legend_upper_right",
    "plot_legend_upper_left",
    "plot_legend_lower_right",
    "plot_legend_lower_left",
    "plot_legend_center_right",
    "plot_legend_center_left",
    "plot_legend_upper_center",
    "plot_legend_lower_center",
    "plot_legend_center",
)

_LINE_STYLE_KEYS = {
    "-": "plot_line_solid",
    "--": "plot_line_dashed",
    ":": "plot_line_dotted",
    "-.": "plot_line_dashdot",
}

_LEGEND_LOCATION_KEYS = {
    "best": "plot_legend_best",
    "upper right": "plot_legend_upper_right",
    "upper left": "plot_legend_upper_left",
    "lower right": "plot_legend_lower_right",
    "lower left": "plot_legend_lower_left",
    "center right": "plot_legend_center_right",
    "center left": "plot_legend_center_left",
    "upper center": "plot_legend_upper_center",
    "lower center": "plot_legend_lower_center",
    "center": "plot_legend_center",
}


class PlotEditorPanel(QWidget):
    """Curve/axis style controls for the currently selected sample."""

    settings_changed = Signal()
    reset_requested = Signal()
    restore_visibility_requested = Signal()
    export_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._settings: PlotSettings | None = None
        self._available: tuple[str, ...] = ()
        self._default_labels: dict[str, str] = {}
        self._default_title = ""
        self._default_xlabel = ""
        self._default_ylabel = ""
        self._data_xlim = (0.0, 1.0)
        self._data_ylim = (0.0, 1.0)
        self._current_key: str | None = None
        self._enabled = False
        self._updating = False
        self._texts: dict[str, str] = {}
        self._build_ui()
        self.set_enabled(False)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.curves_label = QLabel()
        layout.addWidget(self.curves_label)

        self.curve_list = QListWidget()
        self.curve_list.setMaximumHeight(130)
        self.curve_list.itemChanged.connect(self._on_item_changed)
        self.curve_list.currentItemChanged.connect(self._on_curve_selected)
        layout.addWidget(self.curve_list)

        self.style_group = QGroupBox()
        style_form = QFormLayout(self.style_group)
        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._on_name_changed)
        self.name_label = QLabel()
        style_form.addRow(self.name_label, self.name_edit)

        self.color_widget = QWidget()
        color_row = QHBoxLayout(self.color_widget)
        color_row.setContentsMargins(0, 0, 0, 0)
        self.color_button = QPushButton()
        self.color_button.setFixedWidth(34)
        self.color_button.clicked.connect(self._choose_color)
        color_row.addWidget(self.color_button)
        self.color_edit = QLineEdit()
        self.color_edit.setMaxLength(7)
        self.color_edit.setPlaceholderText("#RRGGBB")
        self.color_edit.editingFinished.connect(self._on_color_edited)
        color_row.addWidget(self.color_edit)
        self.color_label = QLabel()
        style_form.addRow(self.color_label, self.color_widget)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.1, 10.0)
        self.width_spin.setDecimals(1)
        self.width_spin.setSingleStep(0.1)
        self.width_spin.setSuffix(" pt")
        self.width_spin.valueChanged.connect(self._on_width_changed)
        self.width_label = QLabel()
        style_form.addRow(self.width_label, self.width_spin)

        self.style_combo = QComboBox()
        for linestyle in LINE_STYLES:
            self.style_combo.addItem("", linestyle)
        self.style_combo.currentIndexChanged.connect(self._on_linestyle_changed)
        self.linestyle_label = QLabel()
        style_form.addRow(self.linestyle_label, self.style_combo)
        layout.addWidget(self.style_group)

        self.axis_group = QGroupBox()
        axis_form = QFormLayout(self.axis_group)
        self.title_edit = QLineEdit()
        self.title_edit.textChanged.connect(self._on_title_changed)
        self.title_label = QLabel()
        axis_form.addRow(self.title_label, self.title_edit)

        self.xlabel_edit = QLineEdit()
        self.xlabel_edit.textChanged.connect(self._on_xlabel_changed)
        self.xlabel_label = QLabel()
        axis_form.addRow(self.xlabel_label, self.xlabel_edit)

        self.ylabel_edit = QLineEdit()
        self.ylabel_edit.textChanged.connect(self._on_ylabel_changed)
        self.ylabel_label = QLabel()
        axis_form.addRow(self.ylabel_label, self.ylabel_edit)

        self.x_auto_check = QCheckBox()
        self.x_min_edit = self._make_range_field()
        self.x_max_edit = self._make_range_field()
        x_range = QHBoxLayout()
        x_range.setContentsMargins(0, 0, 0, 0)
        x_range.addWidget(self.x_auto_check)
        x_range.addWidget(self.x_min_edit)
        x_range.addWidget(QLabel("–"))
        x_range.addWidget(self.x_max_edit)
        self.x_range_label = QLabel()
        axis_form.addRow(self.x_range_label, x_range)

        self.y_auto_check = QCheckBox()
        self.y_min_edit = self._make_range_field()
        self.y_max_edit = self._make_range_field()
        y_range = QHBoxLayout()
        y_range.setContentsMargins(0, 0, 0, 0)
        y_range.addWidget(self.y_auto_check)
        y_range.addWidget(self.y_min_edit)
        y_range.addWidget(QLabel("–"))
        y_range.addWidget(self.y_max_edit)
        self.y_range_label = QLabel()
        axis_form.addRow(self.y_range_label, y_range)

        self.legend_check = QCheckBox()
        self.legend_combo = QComboBox()
        for location in LEGEND_LOCATIONS:
            self.legend_combo.addItem("", location)
        self.legend_check.toggled.connect(self._on_legend_visible_changed)
        self.legend_combo.currentIndexChanged.connect(
            self._on_legend_location_changed
        )
        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(0, 0, 0, 0)
        legend_row.addWidget(self.legend_check)
        legend_row.addWidget(self.legend_combo, stretch=1)
        self.legend_label = QLabel()
        axis_form.addRow(self.legend_label, legend_row)

        self.font_group = QGroupBox()
        font_grid = QGridLayout(self.font_group)
        self.font_title_label = QLabel()
        self.font_axis_label = QLabel()
        self.font_tick_label = QLabel()
        self.font_legend_label = QLabel()
        self.font_title_spin = self._make_font_spin(DEFAULT_TITLE_FONTSIZE)
        self.font_axis_spin = self._make_font_spin(DEFAULT_AXIS_FONTSIZE)
        self.font_tick_spin = self._make_font_spin(DEFAULT_TICK_FONTSIZE)
        self.font_legend_spin = self._make_font_spin(DEFAULT_LEGEND_FONTSIZE)
        font_grid.addWidget(self.font_title_label, 0, 0)
        font_grid.addWidget(self.font_title_spin, 0, 1)
        font_grid.addWidget(self.font_axis_label, 0, 2)
        font_grid.addWidget(self.font_axis_spin, 0, 3)
        font_grid.addWidget(self.font_tick_label, 1, 0)
        font_grid.addWidget(self.font_tick_spin, 1, 1)
        font_grid.addWidget(self.font_legend_label, 1, 2)
        font_grid.addWidget(self.font_legend_spin, 1, 3)
        for spin in (
            self.font_title_spin,
            self.font_axis_spin,
            self.font_tick_spin,
            self.font_legend_spin,
        ):
            spin.valueChanged.connect(self._on_fonts_changed)
        layout.addWidget(self.font_group)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #c62828;")
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        self.reset_btn = QPushButton()
        self.reset_btn.clicked.connect(self.reset_requested.emit)
        self.restore_btn = QPushButton()
        self.restore_btn.clicked.connect(self.restore_visibility_requested.emit)
        buttons.addWidget(self.reset_btn)
        buttons.addWidget(self.restore_btn)
        layout.addLayout(buttons)

        self.export_btn = QPushButton()
        self.export_btn.clicked.connect(self.export_requested.emit)
        layout.addWidget(self.export_btn)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.scope_label = QLabel()
        self.scope_label.setWordWrap(True)
        layout.addWidget(self.scope_label)

        self.x_auto_check.toggled.connect(self._on_x_auto_changed)
        self.y_auto_check.toggled.connect(self._on_y_auto_changed)
        self.x_min_edit.editingFinished.connect(self._on_x_range_edited)
        self.x_max_edit.editingFinished.connect(self._on_x_range_edited)
        self.y_min_edit.editingFinished.connect(self._on_y_range_edited)
        self.y_max_edit.editingFinished.connect(self._on_y_range_edited)

    @staticmethod
    def _make_range_field() -> QLineEdit:
        field = QLineEdit()
        field.setPlaceholderText("—")
        field.setMinimumWidth(64)
        return field

    @staticmethod
    def _make_font_spin(value: float) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(6, 40)
        spin.setValue(int(round(value)))
        return spin

    # ------------------------------------------------------------ interface
    def set_texts(self, texts: Mapping[str, str]) -> None:
        self._texts = dict(texts)
        self.style_group.setTitle(texts["plot_curve_style_group"])
        self.curves_label.setText(texts["plot_curves_label"])
        self.name_label.setText(texts["plot_curve_name_label"])
        self.color_label.setText(texts["plot_curve_color"])
        self.width_label.setText(texts["plot_curve_width"])
        self.linestyle_label.setText(texts["plot_curve_linestyle"])
        self.axis_group.setTitle(texts["plot_axis_group"])
        self.title_label.setText(texts["plot_title_label"])
        self.xlabel_label.setText(texts["plot_xlabel_label"])
        self.ylabel_label.setText(texts["plot_ylabel_label"])
        self.x_range_label.setText(texts["plot_x_range_label"])
        self.y_range_label.setText(texts["plot_y_range_label"])
        self.x_auto_check.setText(texts["plot_x_auto"])
        self.y_auto_check.setText(texts["plot_y_auto"])
        self.legend_label.setText(texts["plot_legend_location"])
        self.legend_check.setText(texts["plot_legend_visible"])
        self.font_group.setTitle(texts["plot_font_group"])
        self.font_title_label.setText(texts["plot_font_title"])
        self.font_axis_label.setText(texts["plot_font_axis"])
        self.font_tick_label.setText(texts["plot_font_tick"])
        self.font_legend_label.setText(texts["plot_font_legend"])
        self.reset_btn.setText(texts["plot_reset"])
        self.restore_btn.setText(texts["plot_restore_visibility"])
        self.export_btn.setText(texts["plot_export"])
        self.scope_label.setText(texts["plot_scope_note"])
        for index, linestyle in enumerate(LINE_STYLES):
            self.style_combo.setItemText(
                index, texts[_LINE_STYLE_KEYS[linestyle]]
            )
        for index, location in enumerate(LEGEND_LOCATIONS):
            self.legend_combo.setItemText(
                index, texts[_LEGEND_LOCATION_KEYS[location]]
            )

    def set_context(
        self,
        settings: PlotSettings,
        available: Iterable[str],
        default_labels: Mapping[str, str],
        *,
        default_title: str,
        default_xlabel: str,
        default_ylabel: str,
        data_xlim: tuple[float, float],
        data_ylim: tuple[float, float],
    ) -> None:
        """Populate the panel from *settings* and the current result."""
        self._settings = settings.copy()
        self._available = tuple(
            key for key in available if key in self._settings.curves
        )
        self._default_labels = dict(default_labels)
        self._default_title = default_title
        self._default_xlabel = default_xlabel
        self._default_ylabel = default_ylabel
        self._data_xlim = tuple(float(v) for v in data_xlim)  # type: ignore[assignment]
        self._data_ylim = tuple(float(v) for v in data_ylim)  # type: ignore[assignment]
        self._rebuild_curve_list()
        self._populate_axis()
        self.set_enabled(True)
        self.set_error("")

    def settings(self) -> PlotSettings | None:
        return self._settings.copy() if self._settings is not None else None

    def curve_keys(self) -> tuple[str, ...]:
        return self._available

    def select_curve(self, key: str) -> None:
        for row in range(self.curve_list.count()):
            item = self.curve_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                self.curve_list.setCurrentItem(item)
                return

    def set_curve_visible(self, key: str, visible: bool) -> None:
        if self._settings is None or key not in self._settings.curves:
            return
        self._settings.curves[key].visible = bool(visible)
        self._refresh_curve_item(key)
        self._emit_changed()

    def set_curve_display_name(self, key: str, name: str) -> None:
        if self._settings is None or key not in self._settings.curves:
            return
        style = self._settings.curves[key]
        default = self._default_labels.get(key, "")
        style.display_name = None if not name.strip() or name == default else name
        self._refresh_curve_item(key)
        if key == self._current_key:
            self._populate_selected_curve()
        self._emit_changed()

    def set_curve_color(self, key: str, color: str) -> None:
        if self._settings is None or key not in self._settings.curves:
            return
        normalized = normalize_color(color)
        self._settings.curves[key].color = normalized
        if key == self._current_key:
            self._populate_selected_curve()
        self._clear_error()
        self._emit_changed()

    def set_curve_linewidth(self, key: str, width: float) -> None:
        if self._settings is None or key not in self._settings.curves:
            return
        self._settings.curves[key] = replace(
            self._settings.curves[key], linewidth=width
        )
        if key == self._current_key:
            self._populate_selected_curve()
        self._emit_changed()

    def set_curve_linestyle(self, key: str, linestyle: str) -> None:
        if self._settings is None or key not in self._settings.curves:
            return
        if linestyle not in LINE_STYLES:
            raise PlotSettingsError(
                f"Unsupported line style: {linestyle!r}",
                code="plot_linestyle",
                context={"linestyle": linestyle},
            )
        self._settings.curves[key].linestyle = linestyle
        if key == self._current_key:
            self._populate_selected_curve()
        self._emit_changed()

    def set_title(self, text: str) -> None:
        self._set_axis_text("title", text)

    def set_xlabel(self, text: str) -> None:
        self._set_axis_text("xlabel", text)

    def set_ylabel(self, text: str) -> None:
        self._set_axis_text("ylabel", text)

    def _set_axis_text(self, name: str, text: str) -> None:
        if self._settings is None:
            return
        default = {
            "title": self._default_title,
            "xlabel": self._default_xlabel,
            "ylabel": self._default_ylabel,
        }[name]
        setattr(self._settings.axis, name, None if text == default else text)
        self._populate_axis()
        self._emit_changed()

    def set_x_range(
        self, low: float | None = None, high: float | None = None
    ) -> None:
        if self._settings is None:
            return
        value = None if low is None or high is None else (float(low), float(high))
        self._settings.axis = replace(self._settings.axis, xlim=value)
        self._populate_axis()
        self._emit_changed()

    def set_y_range(
        self, low: float | None = None, high: float | None = None
    ) -> None:
        if self._settings is None:
            return
        value = None if low is None or high is None else (float(low), float(high))
        self._settings.axis = replace(self._settings.axis, ylim=value)
        self._populate_axis()
        self._emit_changed()

    def set_legend_visible(self, visible: bool) -> None:
        if self._settings is None:
            return
        self._settings.axis.legend_visible = bool(visible)
        self._populate_axis()
        self._emit_changed()

    def set_legend_location(self, location: str) -> None:
        if self._settings is None:
            return
        self._settings.axis = replace(
            self._settings.axis, legend_location=location
        )
        self._populate_axis()
        self._emit_changed()

    def set_font_sizes(
        self,
        *,
        title: float,
        axis: float,
        tick: float,
        legend: float,
    ) -> None:
        if self._settings is None:
            return
        self._settings.axis = replace(
            self._settings.axis,
            title_fontsize=float(title),
            axis_fontsize=float(axis),
            tick_fontsize=float(tick),
            legend_fontsize=float(legend),
        )
        self._populate_axis()
        self._emit_changed()

    def set_error(self, text: str) -> None:
        self.error_label.setText(text)

    def _clear_error(self) -> None:
        self.error_label.setText("")

    def set_status_text(self, text: str) -> None:
        self.status_label.setText(text)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self.curve_list.setEnabled(self._enabled)
        self.axis_group.setEnabled(self._enabled)
        self.font_group.setEnabled(self._enabled)
        self.reset_btn.setEnabled(self._enabled)
        self.restore_btn.setEnabled(self._enabled)
        self.style_group.setEnabled(
            self._enabled and self._current_key is not None
        )
        if not self._enabled:
            self.export_btn.setEnabled(False)

    def set_export_enabled(self, enabled: bool) -> None:
        self.export_btn.setEnabled(bool(enabled and self._enabled))

    def clear(self) -> None:
        self._settings = None
        self._available = ()
        self._current_key = None
        self._updating = True
        self.curve_list.clear()
        self._updating = False
        self.set_enabled(False)
        self.set_error("")
        self.set_status_text("")
        self._clear_detail_fields()

    # ------------------------------------------------------------ internals
    def _rebuild_curve_list(self) -> None:
        current = self._current_key
        self._updating = True
        self.curve_list.clear()
        selected_item: QListWidgetItem | None = None
        for key in self._available:
            if self._settings is None or key not in self._settings.curves:
                continue
            item = QListWidgetItem(self._curve_text(key))
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked
                if self._settings.curves[key].visible
                else Qt.CheckState.Unchecked
            )
            self.curve_list.addItem(item)
            if key == current:
                selected_item = item
        if selected_item is None and self.curve_list.count():
            selected_item = self.curve_list.item(0)
        if selected_item is not None:
            self.curve_list.setCurrentItem(selected_item)
            self._current_key = selected_item.data(Qt.ItemDataRole.UserRole)
        else:
            self._current_key = None
        self._updating = False
        self._populate_selected_curve()

    def _curve_text(self, key: str) -> str:
        if self._settings is not None:
            style = self._settings.curves.get(key)
            if style is not None and style.display_name is not None:
                return style.display_name
        return self._default_labels.get(key, key)

    def _refresh_curve_item(self, key: str) -> None:
        for row in range(self.curve_list.count()):
            item = self.curve_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) != key:
                continue
            self._updating = True
            item.setText(self._curve_text(key))
            if self._settings is not None and key in self._settings.curves:
                item.setCheckState(
                    Qt.CheckState.Checked
                    if self._settings.curves[key].visible
                    else Qt.CheckState.Unchecked
                )
            self._updating = False
            return

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._updating or self._settings is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if key not in self._settings.curves:
            return
        self._settings.curves[key].visible = (
            item.checkState() == Qt.CheckState.Checked
        )
        self._emit_changed()

    def _on_curve_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if self._updating:
            return
        self._current_key = (
            current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        )
        self._populate_selected_curve()

    def _populate_selected_curve(self) -> None:
        key = self._current_key
        style = (
            self._settings.curves.get(key)
            if self._settings is not None and key is not None
            else None
        )
        if style is None:
            self.style_group.setEnabled(False)
            self._clear_detail_fields()
            return
        self.style_group.setEnabled(self._enabled)
        self._updating = True
        default = self._default_labels.get(key, "")
        self.name_edit.setText(
            style.display_name if style.display_name is not None else default
        )
        self.color_edit.setText(style.color)
        self.color_button.setStyleSheet(
            f"background-color: {style.color}; border: 1px solid #777;"
        )
        self.width_spin.setValue(style.linewidth)
        index = self.style_combo.findData(style.linestyle)
        if index >= 0:
            self.style_combo.setCurrentIndex(index)
        self._updating = False

    def _clear_detail_fields(self) -> None:
        self._updating = True
        self.name_edit.clear()
        self.color_edit.clear()
        self.color_button.setStyleSheet("")
        self.width_spin.setValue(1.0)
        self.style_combo.setCurrentIndex(0)
        self._updating = False

    def _on_name_changed(self, text: str) -> None:
        if self._updating or self._settings is None or self._current_key is None:
            return
        style = self._settings.curves.get(self._current_key)
        if style is None:
            return
        default = self._default_labels.get(self._current_key, "")
        style.display_name = None if not text.strip() or text == default else text
        self._refresh_curve_item(self._current_key)
        self._emit_changed()

    def _choose_color(self) -> None:
        if self._settings is None or self._current_key is None:
            return
        style = self._settings.curves.get(self._current_key)
        if style is None:
            return
        color = QColorDialog.getColor(
            QColor(style.color),
            self,
            self._texts.get("plot_curve_color", "Color"),
        )
        if color.isValid():
            self.color_edit.setText(color.name())
            self._apply_color(color.name())

    def _on_color_edited(self) -> None:
        if self._updating or self._settings is None or self._current_key is None:
            return
        self._apply_color(self.color_edit.text())

    def _apply_color(self, text: str) -> None:
        if self._settings is None or self._current_key is None:
            return
        style = self._settings.curves.get(self._current_key)
        if style is None:
            return
        try:
            normalized = normalize_color(text)
        except PlotSettingsError:
            self.set_error(
                self._texts.get(
                    "plot_error_color",
                    "Colour must use the #RRGGBB format.",
                )
            )
            return
        style.color = normalized
        self._updating = True
        self.color_edit.setText(normalized)
        self.color_button.setStyleSheet(
            f"background-color: {normalized}; border: 1px solid #777;"
        )
        self._updating = False
        self._clear_error()
        self._emit_changed()

    def _on_width_changed(self, value: float) -> None:
        if self._updating or self._settings is None or self._current_key is None:
            return
        style = self._settings.curves.get(self._current_key)
        if style is not None:
            style.linewidth = float(value)
            self._emit_changed()

    def _on_linestyle_changed(self, _index: int) -> None:
        if self._updating or self._settings is None or self._current_key is None:
            return
        style = self._settings.curves.get(self._current_key)
        if style is None:
            return
        linestyle = self.style_combo.currentData()
        if linestyle:
            style.linestyle = str(linestyle)
            self._emit_changed()

    def _populate_axis(self) -> None:
        if self._settings is None:
            return
        axis = self._settings.axis
        self._updating = True
        self.title_edit.setText(
            axis.title if axis.title is not None else self._default_title
        )
        self.xlabel_edit.setText(
            axis.xlabel if axis.xlabel is not None else self._default_xlabel
        )
        self.ylabel_edit.setText(
            axis.ylabel if axis.ylabel is not None else self._default_ylabel
        )
        self.x_auto_check.setChecked(axis.xlim is None)
        self.y_auto_check.setChecked(axis.ylim is None)
        self._set_range_fields(
            self.x_min_edit,
            self.x_max_edit,
            axis.xlim,
            self._data_xlim,
        )
        self._set_range_fields(
            self.y_min_edit,
            self.y_max_edit,
            axis.ylim,
            self._data_ylim,
        )
        self.x_min_edit.setEnabled(axis.xlim is not None)
        self.x_max_edit.setEnabled(axis.xlim is not None)
        self.y_min_edit.setEnabled(axis.ylim is not None)
        self.y_max_edit.setEnabled(axis.ylim is not None)
        self.legend_check.setChecked(axis.legend_visible)
        index = self.legend_combo.findData(axis.legend_location)
        if index >= 0:
            self.legend_combo.setCurrentIndex(index)
        self.font_title_spin.setValue(int(round(axis.title_fontsize)))
        self.font_axis_spin.setValue(int(round(axis.axis_fontsize)))
        self.font_tick_spin.setValue(int(round(axis.tick_fontsize)))
        self.font_legend_spin.setValue(int(round(axis.legend_fontsize)))
        self._updating = False

    @staticmethod
    def _set_range_fields(
        min_edit: QLineEdit,
        max_edit: QLineEdit,
        limits: tuple[float, float] | None,
        data_limits: tuple[float, float],
    ) -> None:
        low, high = limits if limits is not None else data_limits
        min_edit.setText(f"{low:.10g}")
        max_edit.setText(f"{high:.10g}")

    def _on_title_changed(self, text: str) -> None:
        self._on_axis_text_changed("title", text, self._default_title)

    def _on_xlabel_changed(self, text: str) -> None:
        self._on_axis_text_changed("xlabel", text, self._default_xlabel)

    def _on_ylabel_changed(self, text: str) -> None:
        self._on_axis_text_changed("ylabel", text, self._default_ylabel)

    def _on_axis_text_changed(
        self, name: str, text: str, default: str
    ) -> None:
        if self._updating or self._settings is None:
            return
        setattr(self._settings.axis, name, None if text == default else text)
        self._emit_changed()

    def _on_x_auto_changed(self, checked: bool) -> None:
        if self._updating or self._settings is None:
            return
        self.x_min_edit.setEnabled(not checked)
        self.x_max_edit.setEnabled(not checked)
        if checked:
            self._settings.axis.xlim = None
            self._set_range_fields(
                self.x_min_edit, self.x_max_edit, None, self._data_xlim
            )
            self._clear_error()
            self._emit_changed()
        else:
            self._on_x_range_edited()

    def _on_y_auto_changed(self, checked: bool) -> None:
        if self._updating or self._settings is None:
            return
        self.y_min_edit.setEnabled(not checked)
        self.y_max_edit.setEnabled(not checked)
        if checked:
            self._settings.axis.ylim = None
            self._set_range_fields(
                self.y_min_edit, self.y_max_edit, None, self._data_ylim
            )
            self._clear_error()
            self._emit_changed()
        else:
            self._on_y_range_edited()

    def _on_x_range_edited(self) -> None:
        self._apply_range("x", self.x_min_edit, self.x_max_edit)

    def _on_y_range_edited(self) -> None:
        self._apply_range("y", self.y_min_edit, self.y_max_edit)

    def _apply_range(self, axis: str, low_edit: QLineEdit, high_edit: QLineEdit) -> None:
        if self._updating or self._settings is None:
            return
        auto = (
            self.x_auto_check.isChecked()
            if axis == "x"
            else self.y_auto_check.isChecked()
        )
        if auto:
            return
        try:
            low = float(low_edit.text())
            high = float(high_edit.text())
            value = (low, high)
            axis_settings = replace(
                self._settings.axis,
                **({"xlim": value} if axis == "x" else {"ylim": value}),
            )
        except (TypeError, ValueError, PlotSettingsError):
            self.set_error(
                self._texts.get(
                    "plot_error_axis_range",
                    "Axis limits must be finite numbers with min < max.",
                )
            )
            return
        self._settings.axis = axis_settings
        self._clear_error()
        self._emit_changed()

    def _on_legend_visible_changed(self, checked: bool) -> None:
        if self._updating or self._settings is None:
            return
        self._settings.axis.legend_visible = bool(checked)
        self._emit_changed()

    def _on_legend_location_changed(self, _index: int) -> None:
        if self._updating or self._settings is None:
            return
        location = self.legend_combo.currentData()
        if location:
            self._settings.axis = replace(
                self._settings.axis, legend_location=str(location)
            )
            self._emit_changed()

    def _on_fonts_changed(self, _value: int) -> None:
        if self._updating or self._settings is None:
            return
        self._settings.axis = replace(
            self._settings.axis,
            title_fontsize=float(self.font_title_spin.value()),
            axis_fontsize=float(self.font_axis_spin.value()),
            tick_fontsize=float(self.font_tick_spin.value()),
            legend_fontsize=float(self.font_legend_spin.value()),
        )
        self._emit_changed()

    def _emit_changed(self) -> None:
        self.settings_changed.emit()
