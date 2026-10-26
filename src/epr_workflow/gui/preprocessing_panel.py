"""Qt panel for user-selected preprocessing.

The panel is a pure view: it collects baseline or Savitzky-Golay parameters
and emits intent signals. All validation, fitting and state live in
:mod:`epr_workflow.preprocessing` and the GUI controller.

The baseline fields start empty (no interval selected) and smoothing is not
selected by default. Nothing is applied until the user previews and applies.
"""

from __future__ import annotations

from PySide6.QtCore import QLocale, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from epr_workflow.preprocessing import (
    BASELINE_OPERATION,
    INPUT_CURRENT,
    INPUT_RAW,
    SAVGOL_OPERATION,
)

#: Translation keys consumed by :meth:`PreprocessingPanel.set_texts`.
TEXT_KEYS = (
    "prep_group",
    "prep_method_label",
    "prep_method_linear",
    "prep_method_savgol",
    "prep_window_left",
    "prep_window_right",
    "prep_window_length",
    "prep_polyorder",
    "prep_input_source",
    "prep_input_current",
    "prep_input_raw",
    "prep_savgol_note",
    "prep_preview",
    "prep_cancel_preview",
    "prep_apply",
    "prep_undo",
    "prep_reset",
    "prep_export",
    "prep_scope_note",
)


class PreprocessingPanel(QGroupBox):
    """Baseline/Savitzky-Golay controls plus shared action buttons."""

    preview_requested = Signal()
    cancel_preview_requested = Signal()
    apply_requested = Signal()
    undo_requested = Signal()
    reset_requested = Signal()
    export_requested = Signal()
    parameters_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._field_min: float | None = None
        self._field_max: float | None = None
        self._n_points = 0
        self._data_enabled = False
        self._build_ui()
        self._update_visibility()
        self.set_enabled(False)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        method_row = QHBoxLayout()
        self.method_label = QLabel()
        method_row.addWidget(self.method_label)
        self.method_combo = QComboBox()
        self.method_combo.addItem("", BASELINE_OPERATION)
        self.method_combo.addItem("", SAVGOL_OPERATION)
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        method_row.addWidget(self.method_combo, stretch=1)
        layout.addLayout(method_row)

        self.baseline_widget = QWidget()
        baseline_layout = QVBoxLayout(self.baseline_widget)
        baseline_layout.setContentsMargins(0, 0, 0, 0)
        self.left_label = QLabel()
        baseline_layout.addWidget(self.left_label)
        left_row = QHBoxLayout()
        self.left_start = self._make_field()
        self.left_end = self._make_field()
        left_row.addWidget(self.left_start)
        left_row.addWidget(QLabel("–"))
        left_row.addWidget(self.left_end)
        baseline_layout.addLayout(left_row)
        self.right_label = QLabel()
        baseline_layout.addWidget(self.right_label)
        right_row = QHBoxLayout()
        self.right_start = self._make_field()
        self.right_end = self._make_field()
        right_row.addWidget(self.right_start)
        right_row.addWidget(QLabel("–"))
        right_row.addWidget(self.right_end)
        baseline_layout.addLayout(right_row)
        layout.addWidget(self.baseline_widget)

        self.smoothing_widget = QWidget()
        smoothing_layout = QGridLayout(self.smoothing_widget)
        smoothing_layout.setContentsMargins(0, 0, 0, 0)
        self.window_length_label = QLabel()
        smoothing_layout.addWidget(self.window_length_label, 0, 0)
        self.window_length_spin = QSpinBox()
        self.window_length_spin.setRange(3, 3)
        self.window_length_spin.setSingleStep(2)
        self.window_length_spin.setValue(3)
        self.window_length_spin.valueChanged.connect(
            self._on_window_length_changed
        )
        smoothing_layout.addWidget(self.window_length_spin, 0, 1)
        self.polyorder_label = QLabel()
        smoothing_layout.addWidget(self.polyorder_label, 1, 0)
        self.polyorder_spin = QSpinBox()
        self.polyorder_spin.setRange(0, 2)
        self.polyorder_spin.setValue(2)
        self.polyorder_spin.valueChanged.connect(
            lambda _value: self.parameters_changed.emit()
        )
        smoothing_layout.addWidget(self.polyorder_spin, 1, 1)
        self.input_label = QLabel()
        smoothing_layout.addWidget(self.input_label, 2, 0)
        self.input_combo = QComboBox()
        self.input_combo.addItem("", INPUT_CURRENT)
        self.input_combo.addItem("", INPUT_RAW)
        self.input_combo.currentIndexChanged.connect(
            lambda _index: self.parameters_changed.emit()
        )
        smoothing_layout.addWidget(self.input_combo, 2, 1)
        self.smoothing_note = QLabel()
        self.smoothing_note.setWordWrap(True)
        self.smoothing_note.setMinimumHeight(64)
        smoothing_layout.addWidget(self.smoothing_note, 3, 0, 1, 2)
        layout.addWidget(self.smoothing_widget)

        actions = QGridLayout()
        self.preview_btn = QPushButton()
        self.preview_btn.clicked.connect(self.preview_requested.emit)
        actions.addWidget(self.preview_btn, 0, 0)

        self.cancel_btn = QPushButton()
        self.cancel_btn.clicked.connect(self.cancel_preview_requested.emit)
        actions.addWidget(self.cancel_btn, 0, 1)

        self.apply_btn = QPushButton()
        self.apply_btn.clicked.connect(self.apply_requested.emit)
        actions.addWidget(self.apply_btn, 1, 0)

        self.undo_btn = QPushButton()
        self.undo_btn.clicked.connect(self.undo_requested.emit)
        actions.addWidget(self.undo_btn, 1, 1)

        self.reset_btn = QPushButton()
        self.reset_btn.clicked.connect(self.reset_requested.emit)
        actions.addWidget(self.reset_btn, 2, 0, 1, 2)
        layout.addLayout(actions)

        self.export_btn = QPushButton()
        self.export_btn.clicked.connect(self.export_requested.emit)
        layout.addWidget(self.export_btn)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.scope_label = QLabel()
        self.scope_label.setWordWrap(True)
        layout.addWidget(self.scope_label)

    def _make_field(self) -> QLineEdit:
        field = QLineEdit()
        field.setPlaceholderText("—")
        field.setClearButtonEnabled(True)
        field.setMinimumWidth(80)
        validator = QDoubleValidator(self)
        validator.setLocale(QLocale.c())
        validator.setDecimals(4)
        validator.setNotation(QDoubleValidator.StandardNotation)
        field.setValidator(validator)
        field.textChanged.connect(lambda _text: self.parameters_changed.emit())
        return field

    # ------------------------------------------------------------ interface
    def set_texts(self, texts: dict[str, str]) -> None:
        self.setTitle(texts["prep_group"])
        self.method_label.setText(texts["prep_method_label"])
        self.method_combo.setItemText(0, texts["prep_method_linear"])
        self.method_combo.setItemText(1, texts["prep_method_savgol"])
        self.left_label.setText(texts["prep_window_left"])
        self.right_label.setText(texts["prep_window_right"])
        self.window_length_label.setText(texts["prep_window_length"])
        self.polyorder_label.setText(texts["prep_polyorder"])
        self.input_label.setText(texts["prep_input_source"])
        self.input_combo.setItemText(0, texts["prep_input_current"])
        self.input_combo.setItemText(1, texts["prep_input_raw"])
        self.smoothing_note.setText(texts["prep_savgol_note"])
        self.preview_btn.setText(texts["prep_preview"])
        self.cancel_btn.setText(texts["prep_cancel_preview"])
        self.apply_btn.setText(texts["prep_apply"])
        self.undo_btn.setText(texts["prep_undo"])
        self.reset_btn.setText(texts["prep_reset"])
        self.export_btn.setText(texts["prep_export"])
        self.scope_label.setText(texts["prep_scope_note"])

    def selected_operation(self) -> str:
        value = self.method_combo.currentData()
        return str(value) if value else BASELINE_OPERATION

    def set_operation(self, operation: str) -> None:
        index = self.method_combo.findData(operation)
        if index < 0:
            return
        self.method_combo.blockSignals(True)
        self.method_combo.setCurrentIndex(index)
        self.method_combo.blockSignals(False)
        self._update_visibility()

    def _on_method_changed(self, _index: int) -> None:
        self._update_visibility()
        self.parameters_changed.emit()

    def _update_visibility(self) -> None:
        is_baseline = self.selected_operation() == BASELINE_OPERATION
        self.baseline_widget.setVisible(is_baseline)
        self.smoothing_widget.setVisible(not is_baseline)

    def set_field_range(
        self, field_min: float, field_max: float, n_points: int
    ) -> None:
        """Configure limits and clear all inputs for a new file."""
        self._field_min = float(field_min)
        self._field_max = float(field_max)
        self._n_points = max(0, int(n_points))

        for field in self._fields():
            validator = field.validator()
            if isinstance(validator, QDoubleValidator):
                validator.setRange(self._field_min, self._field_max)
            field.blockSignals(True)
            field.clear()
            field.blockSignals(False)

        max_window = max(3, self._n_points)
        default_window = 5 if self._n_points >= 5 else 3
        default_window = min(default_window, max_window)
        self.window_length_spin.blockSignals(True)
        self.window_length_spin.setRange(3, max_window)
        self.window_length_spin.setValue(default_window)
        self.window_length_spin.blockSignals(False)

        max_poly = max(0, default_window - 1)
        self.polyorder_spin.blockSignals(True)
        self.polyorder_spin.setRange(0, max_poly)
        self.polyorder_spin.setValue(min(2, max_poly))
        self.polyorder_spin.blockSignals(False)

        self.input_combo.blockSignals(True)
        self.input_combo.setCurrentIndex(self.input_combo.findData(INPUT_CURRENT))
        self.input_combo.blockSignals(False)

    def _fields(self) -> tuple[QLineEdit, QLineEdit, QLineEdit, QLineEdit]:
        return (self.left_start, self.left_end, self.right_start, self.right_end)

    def values(
        self,
    ) -> tuple[float | None, float | None, float | None, float | None]:
        return tuple(self._parse(field) for field in self._fields())  # type: ignore[return-value]

    @staticmethod
    def _parse(field: QLineEdit) -> float | None:
        text = field.text().strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def has_selection(self) -> bool:
        """True only when all four baseline fields contain in-range numbers."""
        if self._field_min is None or self._field_max is None:
            return False
        values = self.values()
        return all(
            value is not None
            and self._field_min <= value <= self._field_max
            for value in values
        )

    def savgol_values(self) -> tuple[int, int]:
        return (
            int(self.window_length_spin.value()),
            int(self.polyorder_spin.value()),
        )

    def has_savgol_selection(self) -> bool:
        window_length, polyorder = self.savgol_values()
        return (
            self._n_points >= 3
            and window_length % 2 == 1
            and window_length >= 3
            and 0 <= polyorder < window_length
        )

    def smoothing_input_source(self) -> str:
        value = self.input_combo.currentData()
        return str(value) if value else INPUT_CURRENT

    def set_smoothing_input_source(self, source: str) -> None:
        index = self.input_combo.findData(source)
        if index < 0:
            return
        self.input_combo.blockSignals(True)
        self.input_combo.setCurrentIndex(index)
        self.input_combo.blockSignals(False)

    def set_savgol_values(self, window_length: int, polyorder: int) -> None:
        self.window_length_spin.blockSignals(True)
        self.window_length_spin.setValue(int(window_length))
        self.window_length_spin.blockSignals(False)
        self.polyorder_spin.blockSignals(True)
        self.polyorder_spin.setMaximum(max(0, int(window_length) - 1))
        self.polyorder_spin.setValue(int(polyorder))
        self.polyorder_spin.blockSignals(False)

    def _on_window_length_changed(self, value: int) -> None:
        self.polyorder_spin.blockSignals(True)
        self.polyorder_spin.setMaximum(max(0, int(value) - 1))
        if self.polyorder_spin.value() > self.polyorder_spin.maximum():
            self.polyorder_spin.setValue(self.polyorder_spin.maximum())
        self.polyorder_spin.blockSignals(False)
        self.parameters_changed.emit()

    def set_values(
        self,
        left_start: float,
        left_end: float,
        right_start: float,
        right_end: float,
    ) -> None:
        for field, value in zip(
            self._fields(), (left_start, left_end, right_start, right_end)
        ):
            field.blockSignals(True)
            field.setText(f"{float(value):.4f}")
            field.blockSignals(False)

    def set_status_text(self, text: str) -> None:
        self.status_label.setText(text)

    def set_enabled(self, enabled: bool) -> None:
        self._data_enabled = bool(enabled)
        self.method_combo.setEnabled(self._data_enabled)
        for field in self._fields():
            field.setEnabled(self._data_enabled)
        self.window_length_spin.setEnabled(self._data_enabled)
        self.polyorder_spin.setEnabled(self._data_enabled)
        self.input_combo.setEnabled(self._data_enabled)
        self.preview_btn.setEnabled(self._data_enabled)
        self.apply_btn.setEnabled(self._data_enabled)
        if not self._data_enabled:
            for button in (
                self.cancel_btn,
                self.undo_btn,
                self.reset_btn,
                self.export_btn,
            ):
                button.setEnabled(False)

    def set_action_states(
        self,
        *,
        preview: bool,
        cancel: bool,
        apply: bool,
        undo: bool,
        reset: bool,
        export: bool,
    ) -> None:
        self.preview_btn.setEnabled(preview)
        self.cancel_btn.setEnabled(cancel)
        self.apply_btn.setEnabled(apply)
        self.undo_btn.setEnabled(undo)
        self.reset_btn.setEnabled(reset)
        self.export_btn.setEnabled(export)
