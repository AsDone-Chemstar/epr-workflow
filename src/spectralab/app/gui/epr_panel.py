"""EPR technique panel for the generic SpectraLab GUI shell.

The panel imports no ``spectralab.app`` module. It implements the shell's
structural panel protocol directly: ``spectrum_changed`` and ``status_event``
signals, ``open_file()``, ``retranslate()`` and ``current_display()``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from spectralab.core.model import Spectrum1D
from spectralab.core.plotting import PlotConfig, plot_spectrum
from spectralab.core.processing import ProcessedSpectrum, ProcessingSession
from spectralab.techniques.epr import (
    BaselineWindow,
    EprLinearBaselineOperation,
    EprSavitzkyGolayOperation,
    LinearBaselineSpec,
    SavgolSpec,
)


class EprPanel(QWidget):
    """EPR import, plot, metadata, and explicit baseline/Savgol session UI."""

    spectrum_changed = Signal(object)
    status_event = Signal(object)

    def __init__(self, controller: Any, translator: Any, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._translator = translator
        self._source: Spectrum1D | None = None
        self._session: ProcessingSession | None = None
        self._display: Spectrum1D | ProcessedSpectrum | None = None
        self._path: Path | None = None
        self._build_ui()
        self.retranslate()

    def _t(self, key: str, **params) -> str:
        return self._translator.tr(key, **params)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.file_label = QLabel()
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        self.plot_group = QGroupBox()
        plot_layout = QVBoxLayout(self.plot_group)
        self.figure = Figure(figsize=(7.0, 4.5))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(111)
        plot_layout.addWidget(self.canvas)
        layout.addWidget(self.plot_group, stretch=1)

        self.processing_group = QGroupBox()
        processing_layout = QVBoxLayout(self.processing_group)

        self.baseline_group = QGroupBox()
        baseline_form = QFormLayout(self.baseline_group)
        self.left_start = self._window_field()
        self.left_end = self._window_field()
        self.right_start = self._window_field()
        self.right_end = self._window_field()
        self.left_start_label = QLabel()
        self.left_end_label = QLabel()
        self.right_start_label = QLabel()
        self.right_end_label = QLabel()
        baseline_form.addRow(self.left_start_label, self.left_start)
        baseline_form.addRow(self.left_end_label, self.left_end)
        baseline_form.addRow(self.right_start_label, self.right_start)
        baseline_form.addRow(self.right_end_label, self.right_end)
        self.apply_baseline_btn = QPushButton()
        self.apply_baseline_btn.clicked.connect(self._apply_baseline)
        baseline_form.addRow(self.apply_baseline_btn)
        processing_layout.addWidget(self.baseline_group)

        self.savgol_group = QGroupBox()
        savgol_form = QFormLayout(self.savgol_group)
        self.window_length_label = QLabel()
        self.window_length_spin = QSpinBox()
        self.window_length_spin.setRange(3, 99)
        self.window_length_spin.setSingleStep(2)
        self.window_length_spin.setValue(5)
        self.window_length_spin.valueChanged.connect(
            self._on_window_length_changed
        )
        savgol_form.addRow(self.window_length_label, self.window_length_spin)
        self.polyorder_label = QLabel()
        self.polyorder_spin = QSpinBox()
        self.polyorder_spin.setRange(0, 4)
        self.polyorder_spin.setValue(2)
        savgol_form.addRow(self.polyorder_label, self.polyorder_spin)
        self.apply_savgol_btn = QPushButton()
        self.apply_savgol_btn.clicked.connect(self._apply_savgol)
        savgol_form.addRow(self.apply_savgol_btn)
        processing_layout.addWidget(self.savgol_group)

        actions = QHBoxLayout()
        self.undo_btn = QPushButton()
        self.undo_btn.clicked.connect(self._undo)
        self.redo_btn = QPushButton()
        self.redo_btn.clicked.connect(self._redo)
        self.reset_btn = QPushButton()
        self.reset_btn.clicked.connect(self._reset)
        actions.addWidget(self.undo_btn)
        actions.addWidget(self.redo_btn)
        actions.addWidget(self.reset_btn)
        processing_layout.addLayout(actions)

        self.state_label = QLabel()
        self.state_label.setWordWrap(True)
        processing_layout.addWidget(self.state_label)
        layout.addWidget(self.processing_group)
        self._update_action_state()

    def _window_field(self) -> QLineEdit:
        field = QLineEdit()
        field.setPlaceholderText("—")
        return field

    # ------------------------------------------------------------- language
    def retranslate(self) -> None:
        self.file_label.setText(
            self._t("epr.file_none")
            if self._path is None
            else self._t("epr.file", name=self._path.name)
        )
        self.plot_group.setTitle(self._t("epr.plot_group"))
        self.processing_group.setTitle(self._t("epr.processing_group"))
        self.baseline_group.setTitle(self._t("epr.baseline_group"))
        self.left_start_label.setText(self._t("epr.left_start"))
        self.left_end_label.setText(self._t("epr.left_end"))
        self.right_start_label.setText(self._t("epr.right_start"))
        self.right_end_label.setText(self._t("epr.right_end"))
        self.apply_baseline_btn.setText(self._t("epr.apply_baseline"))
        self.savgol_group.setTitle(self._t("epr.savgol_group"))
        self.window_length_label.setText(self._t("epr.window_length"))
        self.polyorder_label.setText(self._t("epr.polyorder"))
        self.apply_savgol_btn.setText(self._t("epr.apply_savgol"))
        self.undo_btn.setText(self._t("epr.undo"))
        self.redo_btn.setText(self._t("epr.redo"))
        self.reset_btn.setText(self._t("epr.reset"))
        self._update_state_label()
        if self._display is not None:
            self._draw(self._display)

    # ---------------------------------------------------------------- import
    def open_file(self, path: str | Path) -> bool:
        source = Path(path)
        try:
            loaded = self._controller.load_spectrum(source)
        except Exception as exc:
            code = getattr(exc, "code", None)
            self.status_event.emit(
                {
                    "level": "error",
                    "key": "epr.import_failed",
                    "params": {
                        "error": str(exc),
                        "code": code or "",
                    },
                }
            )
            return False

        self._source = loaded.spectrum
        self._session = ProcessingSession(self._source)
        self._display = self._source
        self._path = source
        for field in (
            self.left_start,
            self.left_end,
            self.right_start,
            self.right_end,
        ):
            field.clear()
        self._sync_savgol_ranges(self._source.point_count)
        self.retranslate()
        self._draw(self._source)
        self.spectrum_changed.emit(self._source)
        self.status_event.emit(
            {
                "level": "success",
                "key": "epr.loaded",
                "params": {
                    "points": self._source.point_count,
                    "format_id": loaded.dataset.format_id,
                },
            }
        )
        self._update_action_state()
        return True

    def _draw(self, display: Spectrum1D | ProcessedSpectrum) -> None:
        title = (
            self._source.dataset_id
            if self._source is not None
            else ""
        )
        config = PlotConfig(
            title=title,
            raw_label=self._t("epr.raw_label"),
            processed_label=self._t("epr.processed_label"),
        )
        plot_spectrum(
            self.axes,
            display,
            config,
            include_raw=isinstance(display, ProcessedSpectrum),
        )
        self.canvas.draw_idle()

    def _sync_savgol_ranges(self, n_points: int) -> None:
        max_window = n_points if n_points % 2 == 1 else n_points - 1
        max_window = min(max_window, 99)
        if max_window < 3:
            self.window_length_spin.setRange(3, 3)
            return
        current = min(self.window_length_spin.value(), max_window)
        if current % 2 == 0:
            current -= 1
        current = max(3, current)
        self.window_length_spin.blockSignals(True)
        self.window_length_spin.setRange(3, max_window)
        self.window_length_spin.setValue(current)
        self.window_length_spin.blockSignals(False)
        self.polyorder_spin.setMaximum(max(0, current - 1))
        self.polyorder_spin.setValue(min(self.polyorder_spin.value(), current - 1))

    def _on_window_length_changed(self, value: int) -> None:
        self.polyorder_spin.setMaximum(max(0, value - 1))
        if self.polyorder_spin.value() > value - 1:
            self.polyorder_spin.setValue(max(0, value - 1))

    # ------------------------------------------------------------- processing
    def _parse_window_value(self, field: QLineEdit) -> float:
        text = field.text().strip()
        if not text:
            raise ValueError(self._t("epr.baseline_empty"))
        return float(text)

    def _apply_baseline(self) -> None:
        if self._session is None:
            self._report_error(ValueError(self._t("epr.no_spectrum")))
            return
        try:
            spec = LinearBaselineSpec(
                BaselineWindow(
                    self._parse_window_value(self.left_start),
                    self._parse_window_value(self.left_end),
                ),
                BaselineWindow(
                    self._parse_window_value(self.right_start),
                    self._parse_window_value(self.right_end),
                ),
            )
            display = self._session.apply(EprLinearBaselineOperation(spec))
        except Exception as exc:
            self._report_error(exc)
            return
        self._commit(display, "epr.baseline_applied")

    def _apply_savgol(self) -> None:
        if self._session is None:
            self._report_error(ValueError(self._t("epr.no_spectrum")))
            return
        try:
            spec = SavgolSpec(
                window_length=int(self.window_length_spin.value()),
                polyorder=int(self.polyorder_spin.value()),
            )
            display = self._session.apply(EprSavitzkyGolayOperation(spec))
        except Exception as exc:
            self._report_error(exc)
            return
        self._commit(display, "epr.savgol_applied")

    def _commit(self, display: ProcessedSpectrum, status_key: str) -> None:
        self._display = display
        self._draw(display)
        self.spectrum_changed.emit(display)
        self.status_event.emit({"level": "success", "key": status_key})
        self._update_action_state()

    def _undo(self) -> None:
        if self._session is None:
            return
        result = self._session.undo()
        self._set_result(result, "epr.undo_applied")

    def _redo(self) -> None:
        if self._session is None:
            return
        result = self._session.redo()
        self._set_result(result, "epr.redo_applied")

    def _reset(self) -> None:
        if self._session is None:
            return
        result = self._session.reset()
        self._set_result(result, "epr.reset_applied")

    def _set_result(self, result: ProcessedSpectrum, status_key: str) -> None:
        display = self._source if result.is_original else result
        self._display = display
        self._draw(display)
        self.spectrum_changed.emit(display)
        self.status_event.emit({"level": "info", "key": status_key})
        self._update_action_state()

    def _report_error(self, exc: Exception) -> None:
        self.status_event.emit(
            {
                "level": "error",
                "key": "epr.operation_failed",
                "params": {
                    "error": str(exc),
                    "code": getattr(exc, "code", ""),
                },
            }
        )

    def _update_action_state(self) -> None:
        session = self._session
        self.undo_btn.setEnabled(bool(session and session.can_undo))
        self.redo_btn.setEnabled(bool(session and session.can_redo))
        self.reset_btn.setEnabled(
            bool(session and (session.can_undo or session.can_redo))
        )
        self._update_state_label()

    def _update_state_label(self) -> None:
        count = len(self._session.history) if self._session is not None else 0
        self.state_label.setText(self._t("epr.processing_state", count=count))

    # ---------------------------------------------------------------- access
    def current_display(self):
        return self._display

    @property
    def processing_session(self) -> ProcessingSession | None:
        return self._session


def create_panel(controller, translator):
    """Create one EPR panel for the generic shell."""
    return EprPanel(controller, translator)


__all__ = ["EprPanel", "create_panel"]
