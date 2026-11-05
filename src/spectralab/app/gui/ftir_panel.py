"""FTIR import and raw-display panel for the generic SpectraLab shell.

The FTIR backend remains Qt-free. This app-layer panel builds explicit M9
``FTIRImportOptions``, asks the generic controller to import, and displays the
returned ``Spectrum1D`` through the M5 plotting API. It never processes data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spectralab.app.gui.controller import ApplicationController
from spectralab.app.gui.ftir_import_dialog import FtirImportDialog
from spectralab.app.gui.ftir_options_widget import FtirOptionsWidget
from spectralab.app.gui.i18n import Translator
from spectralab.core.model import Axis1D, Signal1D, Spectrum1D
from spectralab.core.plotting import (
    PlotConfig,
    Series1D,
    plot_spectrum,
    render_series,
    series_from_spectrum,
)
from spectralab.core.processing import (
    OperationOutput,
    ProcessedSpectrum,
    ProcessingSession,
)
from spectralab.techniques.ftir import (
    BaselineRegion,
    FTIRBaselineError,
    FTIRBaselineOperation,
    FTIRImportOptions,
    NORMALIZATION_METHODS,
    PEAK_POLARITIES,
    PEAK_SOURCES,
    PeakDetectionError,
    PeakDetectionParameters,
    PeakDetectionResult,
    create_baseline_operation,
    create_normalization_operation,
    detect_peaks,
    normalize_regions,
)

_METHOD_KEYS = {
    "min_max": "ftir.method_min_max",
    "max_abs": "ftir.method_max_abs",
    "l2": "ftir.method_l2",
}
_OPERATION_KEYS = {
    "normalization": "ftir.operation_normalization",
    "baseline": "ftir.operation_baseline",
}
_BASELINE_ALGORITHM_KEYS = {
    "linear": "ftir.baseline_linear",
    "polynomial": "ftir.baseline_polynomial",
}
_PEAK_SOURCE_KEYS = {
    "raw": "ftir.peak_source_raw",
    "processed": "ftir.peak_source_processed",
}
_PEAK_POLARITY_KEYS = {
    "positive": "ftir.peak_positive",
    "negative": "ftir.peak_negative",
    "both": "ftir.peak_both",
}


class FtirPanel(QWidget):
    """Explicit FTIR import options plus a raw-only spectrum display."""

    spectrum_changed = Signal(object)
    status_event = Signal(object)

    def __init__(
        self,
        controller: ApplicationController,
        translator: Translator,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._translator = translator
        self._source: Spectrum1D | None = None
        self._display: Spectrum1D | ProcessedSpectrum | None = None
        self._session: ProcessingSession | None = None
        self._preview_output: OperationOutput | None = None
        self._preview_operation = None
        self._preview_baseline_values = None
        self._preview_fit = None
        self._baseline_regions: list[BaselineRegion] = []
        self._peak_preview_result: PeakDetectionResult | None = None
        self._peak_applied_result: PeakDetectionResult | None = None
        self._path: Path | None = None
        self._warnings: tuple[str, ...] = ()
        self._dialog: FtirImportDialog | None = None
        self._build_ui()
        self.retranslate()

    def _t(self, key: str, **params: Any) -> str:
        return self._translator.tr(key, **params)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        file_row = QHBoxLayout()
        self.file_label = QLabel()
        self.file_label.setWordWrap(True)
        file_row.addWidget(self.file_label, 1)
        self.import_options_button = QPushButton()
        self.import_options_button.clicked.connect(self.open_import_dialog)
        file_row.addWidget(self.import_options_button)
        layout.addLayout(file_row)

        splitter = QSplitter(Qt.Vertical, self)

        self.plot_group = QGroupBox()
        plot_layout = QVBoxLayout(self.plot_group)
        display_row = QHBoxLayout()
        self.invert_axis_check = QCheckBox()
        self.invert_axis_check.setChecked(True)
        self.invert_axis_check.toggled.connect(self._on_display_direction_toggled)
        display_row.addWidget(self.invert_axis_check)
        display_row.addStretch(1)
        plot_layout.addLayout(display_row)

        self.figure = Figure(figsize=(7.0, 3.8))
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.axes = self.figure.add_subplot(111)
        plot_layout.addWidget(self.canvas, 1)

        self.raw_note_label = QLabel()
        self.raw_note_label.setWordWrap(True)
        plot_layout.addWidget(self.raw_note_label)
        splitter.addWidget(self.plot_group)

        self.processing_group = QGroupBox()
        processing_form = QFormLayout(self.processing_group)
        self.operation_label = QLabel()
        self.operation_combo = QComboBox()
        for operation in ("normalization", "baseline"):
            self.operation_combo.addItem("", operation)
        self.operation_combo.currentIndexChanged.connect(
            self._on_operation_changed
        )
        processing_form.addRow(self.operation_label, self.operation_combo)

        self.operation_stack = QStackedWidget()
        self.normalization_page = QWidget()
        normalization_form = QFormLayout(self.normalization_page)
        normalization_form.setContentsMargins(0, 0, 0, 0)
        self.method_label = QLabel()
        self.method_combo = QComboBox()
        for method in NORMALIZATION_METHODS:
            self.method_combo.addItem("", method)
        self.method_combo.currentIndexChanged.connect(self._on_method_changed)
        normalization_form.addRow(self.method_label, self.method_combo)
        self.operation_stack.addWidget(self.normalization_page)

        self.baseline_page = QWidget()
        baseline_form = QFormLayout(self.baseline_page)
        baseline_form.setContentsMargins(0, 0, 0, 0)
        self.baseline_algorithm_label = QLabel()
        self.baseline_algorithm = QComboBox()
        for algorithm in ("linear", "polynomial"):
            self.baseline_algorithm.addItem("", algorithm)
        self.baseline_algorithm.currentIndexChanged.connect(
            self._on_baseline_parameters_changed
        )
        baseline_form.addRow(self.baseline_algorithm_label, self.baseline_algorithm)

        self.degree_label = QLabel()
        self.degree_spin = QSpinBox()
        self.degree_spin.setRange(2, 5)
        self.degree_spin.setValue(3)
        self.degree_spin.valueChanged.connect(
            self._on_baseline_parameters_changed
        )
        baseline_form.addRow(self.degree_label, self.degree_spin)

        self.fit_info_label = QLabel()
        self.fit_info_label.setWordWrap(True)
        baseline_form.addRow(self.fit_info_label)

        self.regions_label = QLabel()
        self.region_list = QListWidget()
        self.region_list.setMaximumHeight(72)
        baseline_form.addRow(self.regions_label, self.region_list)

        self.region_start_label = QLabel()
        self.region_start = QLineEdit()
        self.region_start.textChanged.connect(self._on_region_fields_changed)
        baseline_form.addRow(self.region_start_label, self.region_start)
        self.region_end_label = QLabel()
        self.region_end = QLineEdit()
        self.region_end.textChanged.connect(self._on_region_fields_changed)
        baseline_form.addRow(self.region_end_label, self.region_end)

        region_actions = QHBoxLayout()
        self.add_region_button = QPushButton()
        self.add_region_button.clicked.connect(self._add_region)
        self.remove_region_button = QPushButton()
        self.remove_region_button.clicked.connect(self._remove_region)
        region_actions.addWidget(self.add_region_button)
        region_actions.addWidget(self.remove_region_button)
        baseline_form.addRow(region_actions)
        self.operation_stack.addWidget(self.baseline_page)
        processing_form.addRow(self.operation_stack)

        actions = QHBoxLayout()
        self.preview_button = QPushButton()
        self.preview_button.clicked.connect(self._preview)
        self.apply_button = QPushButton()
        self.apply_button.clicked.connect(self._apply)
        self.cancel_preview_button = QPushButton()
        self.cancel_preview_button.clicked.connect(self._cancel_preview)
        actions.addWidget(self.preview_button)
        actions.addWidget(self.apply_button)
        actions.addWidget(self.cancel_preview_button)
        self.undo_button = QPushButton()
        self.undo_button.clicked.connect(self._undo)
        self.redo_button = QPushButton()
        self.redo_button.clicked.connect(self._redo)
        self.reset_button = QPushButton()
        self.reset_button.clicked.connect(self._reset)
        actions.addWidget(self.undo_button)
        actions.addWidget(self.redo_button)
        actions.addWidget(self.reset_button)
        processing_form.addRow(actions)

        self.state_label = QLabel()
        self.state_label.setWordWrap(True)
        processing_form.addRow(self.state_label)
        splitter.addWidget(self.processing_group)

        self.options_widget = FtirOptionsWidget(self._translator)
        self.bottom_tabs = QTabWidget()
        self.import_tab = QWidget()
        import_tab_layout = QVBoxLayout(self.import_tab)
        import_tab_layout.setContentsMargins(0, 0, 0, 0)
        import_tab_layout.addWidget(self.options_widget)
        self.bottom_tabs.addTab(self.import_tab, "")

        self.peak_tab = QWidget()
        self._build_peak_tab(self.peak_tab)
        self.bottom_tabs.addTab(self.peak_tab, "")
        splitter.addWidget(self.bottom_tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 3)
        splitter.setSizes([300, 230, 330])
        self._on_operation_changed()
        self._update_peak_controls()
        self._update_display_controls(reset=False)
        self._update_action_state()

    def _build_peak_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(4, 4, 4, 4)
        form = QFormLayout()
        self.peak_source_label = QLabel()
        self.peak_source_combo = QComboBox()
        for source in PEAK_SOURCES:
            self.peak_source_combo.addItem("", source)
        self.peak_source_combo.currentIndexChanged.connect(
            self._on_peak_parameters_changed
        )
        form.addRow(self.peak_source_label, self.peak_source_combo)

        self.peak_polarity_label = QLabel()
        self.peak_polarity_combo = QComboBox()
        for polarity in PEAK_POLARITIES:
            self.peak_polarity_combo.addItem("", polarity)
        self.peak_polarity_combo.currentIndexChanged.connect(
            self._on_peak_parameters_changed
        )
        form.addRow(self.peak_polarity_label, self.peak_polarity_combo)

        self.peak_height_label = QLabel()
        self.peak_height = QLineEdit()
        self.peak_height.textChanged.connect(self._on_peak_parameters_changed)
        form.addRow(self.peak_height_label, self.peak_height)

        self.peak_prominence_label = QLabel()
        self.peak_prominence = QLineEdit()
        self.peak_prominence.textChanged.connect(
            self._on_peak_parameters_changed
        )
        form.addRow(self.peak_prominence_label, self.peak_prominence)

        self.peak_distance_label = QLabel()
        self.peak_distance = QSpinBox()
        self.peak_distance.setRange(1, 10_000_000)
        self.peak_distance.setValue(1)
        self.peak_distance.valueChanged.connect(
            self._on_peak_parameters_changed
        )
        form.addRow(self.peak_distance_label, self.peak_distance)

        self.peak_min_width_label = QLabel()
        self.peak_min_width = QLineEdit()
        self.peak_min_width.textChanged.connect(self._on_peak_parameters_changed)
        form.addRow(self.peak_min_width_label, self.peak_min_width)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.peak_preview_button = QPushButton()
        self.peak_preview_button.clicked.connect(self._preview_peaks)
        self.peak_apply_button = QPushButton()
        self.peak_apply_button.clicked.connect(self._apply_peaks)
        self.peak_clear_button = QPushButton()
        self.peak_clear_button.clicked.connect(self._clear_peak_results)
        actions.addWidget(self.peak_preview_button)
        actions.addWidget(self.peak_apply_button)
        actions.addWidget(self.peak_clear_button)
        layout.addLayout(actions)

        self.peak_status_label = QLabel()
        self.peak_status_label.setWordWrap(True)
        layout.addWidget(self.peak_status_label)
        self.peak_parameter_label = QLabel()
        self.peak_parameter_label.setWordWrap(True)
        layout.addWidget(self.peak_parameter_label)
        self.peak_warning_label = QLabel()
        self.peak_warning_label.setWordWrap(True)
        layout.addWidget(self.peak_warning_label)

        self.peak_table = QTableWidget(0, 7)
        self.peak_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.peak_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.peak_table.setAlternatingRowColors(True)
        self.peak_table.verticalHeader().setVisible(False)
        self.peak_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        layout.addWidget(self.peak_table, 1)

    # ------------------------------------------------------------- language
    def retranslate(self) -> None:
        self.file_label.setText(
            self._t("ftir.file_none")
            if self._path is None
            else self._t("ftir.file", name=self._path.name)
        )
        self.import_options_button.setText(self._t("ftir.import_options"))
        self.plot_group.setTitle(self._t("ftir.plot_group"))
        self.invert_axis_check.setText(self._t("ftir.high_wavenumber_left"))
        self.raw_note_label.setText(self._t("ftir.raw_note"))
        self.processing_group.setTitle(self._t("ftir.processing_group"))
        self.operation_label.setText(self._t("ftir.operation"))
        self._retranslate_operations()
        self.method_label.setText(self._t("ftir.normalization_method"))
        self._retranslate_methods()
        self.baseline_algorithm_label.setText(self._t("ftir.baseline_algorithm"))
        self._retranslate_baseline_algorithms()
        self.degree_label.setText(self._t("ftir.polynomial_degree"))
        self.fit_info_label.setText(self._fit_info_text())
        self.regions_label.setText(self._t("ftir.fitting_regions"))
        self.region_start_label.setText(self._t("ftir.region_start"))
        self.region_end_label.setText(self._t("ftir.region_end"))
        self.add_region_button.setText(self._t("ftir.add_region"))
        self.remove_region_button.setText(self._t("ftir.remove_region"))
        self.region_start.setPlaceholderText(self._t("ftir.region_start_hint"))
        self.region_end.setPlaceholderText(self._t("ftir.region_end_hint"))
        self._refresh_region_list()
        self.bottom_tabs.setTabText(0, self._t("ftir.tab_import_options"))
        self.bottom_tabs.setTabText(1, self._t("ftir.tab_peak_picking"))
        self.peak_source_label.setText(self._t("ftir.peak_source"))
        self._retranslate_peak_sources()
        self.peak_polarity_label.setText(self._t("ftir.peak_polarity"))
        self._retranslate_peak_polarities()
        self.peak_height_label.setText(self._t("ftir.peak_height"))
        self.peak_prominence_label.setText(self._t("ftir.peak_prominence"))
        self.peak_distance_label.setText(self._t("ftir.peak_distance"))
        self.peak_min_width_label.setText(self._t("ftir.peak_min_width"))
        self.peak_height.setPlaceholderText(self._t("ftir.peak_blank_none"))
        self.peak_prominence.setPlaceholderText(self._t("ftir.peak_blank_none"))
        self.peak_min_width.setPlaceholderText(self._t("ftir.peak_blank_none"))
        self.peak_distance.setSuffix(self._t("ftir.peak_samples_suffix"))
        self.peak_preview_button.setText(self._t("ftir.peak_preview"))
        self.peak_apply_button.setText(self._t("ftir.peak_apply"))
        self.peak_clear_button.setText(self._t("ftir.peak_clear"))
        self._update_peak_table()
        self._update_peak_controls()
        self.preview_button.setText(self._t("ftir.preview"))
        self.apply_button.setText(self._t("ftir.apply"))
        self.cancel_preview_button.setText(self._t("ftir.cancel_preview"))
        self.undo_button.setText(self._t("ftir.undo"))
        self.redo_button.setText(self._t("ftir.redo"))
        self.reset_button.setText(self._t("ftir.reset"))
        self.options_widget.retranslate()
        if self._dialog is not None:
            self._dialog.retranslate()
        self._update_state_label()
        if self._display is not None:
            self._draw()
        else:
            self.axes.clear()
            self.canvas.draw_idle()

    def _retranslate_methods(self) -> None:
        current = self.method_combo.currentData()
        self.method_combo.blockSignals(True)
        self.method_combo.clear()
        for method in NORMALIZATION_METHODS:
            self.method_combo.addItem(self._t(_METHOD_KEYS[method]), method)
        index = self.method_combo.findData(current)
        if index >= 0:
            self.method_combo.setCurrentIndex(index)
        self.method_combo.blockSignals(False)

    def _retranslate_operations(self) -> None:
        current = self.operation_combo.currentData()
        self.operation_combo.blockSignals(True)
        self.operation_combo.clear()
        for operation in ("normalization", "baseline"):
            self.operation_combo.addItem(
                self._t(_OPERATION_KEYS[operation]),
                operation,
            )
        index = self.operation_combo.findData(current)
        if index >= 0:
            self.operation_combo.setCurrentIndex(index)
        self.operation_combo.blockSignals(False)

    def _retranslate_peak_sources(self) -> None:
        current = self.peak_source_combo.currentData()
        self.peak_source_combo.blockSignals(True)
        self.peak_source_combo.clear()
        for source in PEAK_SOURCES:
            self.peak_source_combo.addItem(
                self._t(_PEAK_SOURCE_KEYS[source]),
                source,
            )
        index = self.peak_source_combo.findData(current)
        if index >= 0:
            self.peak_source_combo.setCurrentIndex(index)
        self.peak_source_combo.blockSignals(False)

    def _retranslate_peak_polarities(self) -> None:
        current = self.peak_polarity_combo.currentData()
        self.peak_polarity_combo.blockSignals(True)
        self.peak_polarity_combo.clear()
        for polarity in PEAK_POLARITIES:
            self.peak_polarity_combo.addItem(
                self._t(_PEAK_POLARITY_KEYS[polarity]),
                polarity,
            )
        index = self.peak_polarity_combo.findData(current)
        if index >= 0:
            self.peak_polarity_combo.setCurrentIndex(index)
        self.peak_polarity_combo.blockSignals(False)

    def _retranslate_baseline_algorithms(self) -> None:
        current = self.baseline_algorithm.currentData()
        self.baseline_algorithm.blockSignals(True)
        self.baseline_algorithm.clear()
        for algorithm in ("linear", "polynomial"):
            self.baseline_algorithm.addItem(
                self._t(_BASELINE_ALGORITHM_KEYS[algorithm]),
                algorithm,
            )
        index = self.baseline_algorithm.findData(current)
        if index >= 0:
            self.baseline_algorithm.setCurrentIndex(index)
        self.baseline_algorithm.blockSignals(False)

    # ---------------------------------------------------------------- import
    def open_import_dialog(self) -> bool:
        """Open the modal import-options dialog; return whether it imported."""
        dialog = FtirImportDialog(self._translator, parent=self)
        if self._path is not None:
            dialog.set_path(self._path)
        try:
            dialog.options_widget.set_options(self.options_widget.options_from_ui())
        except Exception:
            pass
        self._dialog = dialog
        try:
            if dialog.exec():
                path = dialog.selected_path()
                if path is not None:
                    return self.import_file(path, dialog.selected_options())
        finally:
            self._dialog = None
        return False

    def current_options(self) -> FTIRImportOptions:
        """Return the options currently shown in the inline editor."""
        return self.options_widget.options_from_ui()

    def open_file(self, path: str | Path) -> bool:
        """Import with the currently visible inline options."""
        return self.import_file(path)

    def import_file(
        self,
        path: str | Path,
        options: FTIRImportOptions | None = None,
    ) -> bool:
        source_path = Path(path)
        if options is None:
            try:
                options = self.options_widget.options_from_ui()
            except Exception as exc:
                self._emit_options_error(exc)
                return False
        else:
            self.options_widget.set_options(options)

        try:
            loaded = self._controller.load_spectrum(
                source_path,
                technique_hint="ftir",
                options={"ftir": options},
            )
        except Exception as exc:
            if self._preview_output is not None:
                self._invalidate_preview()
                self._update_action_state()
            code = getattr(exc, "code", None) or ""
            self.status_event.emit(
                {
                    "level": "error",
                    "key": "ftir.import_failed",
                    "params": {"error": str(exc), "code": code},
                }
            )
            return False

        self._source = loaded.spectrum
        self._display = loaded.spectrum
        self._session = ProcessingSession(loaded.spectrum)
        self._preview_output = None
        self._preview_operation = None
        self._preview_baseline_values = None
        self._preview_fit = None
        self._baseline_regions.clear()
        self._path = source_path
        self._warnings = tuple(loaded.dataset.warnings)
        self._clear_peak_results_silent()
        self.options_widget.set_effective_metadata(loaded.spectrum)
        self._update_display_controls(reset=True)
        self._update_action_state()
        self.retranslate()
        self.spectrum_changed.emit(loaded.spectrum)
        if self._warnings:
            self.status_event.emit(
                {
                    "level": "warning",
                    "key": "ftir.loaded_with_warnings",
                    "params": {
                        "points": loaded.spectrum.point_count,
                        "format_id": loaded.dataset.format_id,
                        "count": len(self._warnings),
                        "warnings": "; ".join(self._warnings),
                    },
                }
            )
        else:
            self.status_event.emit(
                {
                    "level": "success",
                    "key": "ftir.loaded",
                    "params": {
                        "points": loaded.spectrum.point_count,
                        "format_id": loaded.dataset.format_id,
                    },
                }
            )
        return True

    def _emit_options_error(self, exc: Exception) -> None:
        self.status_event.emit(
            {
                "level": "error",
                "key": "ftir.options_invalid",
                "params": {"error": str(exc)},
            }
        )

    # ---------------------------------------------------------------- display
    def _axis_label(self, axis: Axis1D) -> str:
        if axis.name:
            base = axis.name
        elif axis.quantity == "wavenumber":
            base = self._t("ftir.quantity_wavenumber")
        else:
            base = self._t("ftir.axis_unknown")
        return f"{base} ({axis.unit})" if axis.unit else base

    def _processed_label(self) -> str:
        if self._session is not None and self._session.history:
            operation_id = self._session.history[-1].operation_id
            if operation_id.startswith("ftir.baseline."):
                return self._t("ftir.baseline_processed_label")
        return self._t("ftir.processed_label")

    def _signal_label(self, signal: Signal1D) -> str:
        if signal.name:
            base = signal.name
        elif signal.semantics == "absorbance":
            base = self._t("ftir.semantics_absorbance")
        elif signal.semantics == "transmittance":
            base = self._t("ftir.semantics_transmittance")
        else:
            base = self._t("ftir.signal_unknown")
        return f"{base} ({signal.unit})" if signal.unit else base

    def _draw(self) -> None:
        if self._source is None or self._display is None:
            self.axes.clear()
            self.canvas.draw_idle()
            return
        if self._preview_output is None:
            peak_result = self._peak_preview_result or self._peak_applied_result
            if peak_result is not None:
                self._draw_peak_result(peak_result)
                return
        title = self._source.metadata.title or self._source.dataset_id
        config = PlotConfig(
            title=title,
            xlabel=self._axis_label(self._source.axis),
            ylabel=self._signal_label(self._source.raw_signal),
            raw_label=self._t("ftir.raw_label"),
            processed_label=self._processed_label(),
        )
        if self._preview_output is not None:
            raw_series = series_from_spectrum(
                self._source,
                label=self._t("ftir.raw_label"),
            )[0]
            preview_series = Series1D(
                kind="processed",
                axis=self._preview_output.axis,
                signal=self._preview_output.signal,
                label=self._t("ftir.preview_label"),
                dataset_id=self._source.dataset_id,
            )
            render_series(
                self.axes,
                (raw_series, preview_series),
                config,
                title=title,
            )
            if (
                isinstance(self._preview_operation, FTIRBaselineOperation)
                and self._preview_baseline_values is not None
            ):
                if self._session is not None and self._session.history:
                    current = self._session.current
                    self.axes.plot(
                        current.axis.values,
                        current.signal.values,
                        color="#2e7d32",
                        linewidth=1.0,
                        linestyle="-",
                        label=self._t("ftir.current_label"),
                    )
                self.axes.plot(
                    self._source.axis.values,
                    self._preview_baseline_values,
                    color="#b26a00",
                    linewidth=1.0,
                    linestyle="--",
                    label=self._t("ftir.baseline_label"),
                )
                self.axes.legend(loc="best", frameon=False)
        else:
            plot_spectrum(self.axes, self._display, config)
        if self._selected_operation() == "baseline":
            for region in self._baseline_regions:
                self.axes.axvspan(
                    region.lower,
                    region.upper,
                    color="#f0c674",
                    alpha=0.12,
                    linewidth=0,
                    zorder=0,
                )
        if (
            self.invert_axis_check.isChecked()
            and self._source.axis.quantity == "wavenumber"
        ):
            x_min = float(self._source.axis.values.min())
            x_max = float(self._source.axis.values.max())
            self.axes.set_xlim(x_max, x_min)
        self.canvas.draw_idle()

    def _draw_peak_result(self, result: PeakDetectionResult) -> None:
        if self._source is None:
            return
        title = self._source.metadata.title or self._source.dataset_id
        config = PlotConfig(
            title=title,
            xlabel=self._axis_label(self._source.axis),
            ylabel=self._signal_label(self._source.raw_signal),
            raw_label=self._t("ftir.peak_source_raw"),
            processed_label=self._t("ftir.peak_source_processed"),
            legend_visible=False,
        )
        if result.source == "raw":
            plot_spectrum(self.axes, self._source, config)
        else:
            if self._session is None:
                return
            plot_spectrum(
                self.axes,
                self._session.current,
                config,
                include_raw=False,
            )
        positive = [
            peak for peak in result.peaks if peak.polarity == "positive"
        ]
        negative = [
            peak for peak in result.peaks if peak.polarity == "negative"
        ]
        if positive:
            self.axes.plot(
                [peak.x for peak in positive],
                [peak.y for peak in positive],
                linestyle="none",
                marker="^",
                color="#2e7d32",
                markersize=7,
                label=self._t("ftir.peak_positive"),
            )
        if negative:
            self.axes.plot(
                [peak.x for peak in negative],
                [peak.y for peak in negative],
                linestyle="none",
                marker="v",
                color="#c62828",
                markersize=7,
                label=self._t("ftir.peak_negative"),
            )
        self.axes.legend(loc="best", frameon=False)
        if (
            self.invert_axis_check.isChecked()
            and self._source.axis.quantity == "wavenumber"
        ):
            x_min = float(self._source.axis.values.min())
            x_max = float(self._source.axis.values.max())
            self.axes.set_xlim(x_max, x_min)
        self.canvas.draw_idle()

    def _on_display_direction_toggled(self, _checked: bool) -> None:
        if self._source is not None:
            self._draw()

    def _update_display_controls(self, *, reset: bool) -> None:
        is_wavenumber = (
            self._source is not None
            and self._source.axis.quantity == "wavenumber"
        )
        self.invert_axis_check.setEnabled(is_wavenumber)
        if reset:
            self.invert_axis_check.blockSignals(True)
            self.invert_axis_check.setChecked(is_wavenumber)
            self.invert_axis_check.blockSignals(False)

    # ------------------------------------------------------------- processing
    def _selected_method(self) -> str:
        return str(self.method_combo.currentData() or "min_max")

    def _method_label(self, method: str | None = None) -> str:
        value = method or self._selected_method()
        return self._t(_METHOD_KEYS[value])

    def _selected_operation(self) -> str:
        return str(self.operation_combo.currentData() or "normalization")

    def _baseline_algorithm_value(self) -> str:
        return str(self.baseline_algorithm.currentData() or "linear")

    def _baseline_algorithm_label(self) -> str:
        return self._t(_BASELINE_ALGORITHM_KEYS[self._baseline_algorithm_value()])

    def _selected_degree(self) -> int:
        if self._baseline_algorithm_value() == "linear":
            return 1
        return int(self.degree_spin.value())

    def _on_operation_changed(self, _index: int = 0) -> None:
        is_baseline = self._selected_operation() == "baseline"
        self.operation_stack.setCurrentWidget(
            self.baseline_page if is_baseline else self.normalization_page
        )
        self.degree_spin.setEnabled(
            is_baseline and self._baseline_algorithm_value() == "polynomial"
        )
        self._invalidate_preview()
        self._update_fit_info()
        self._update_action_state()
        if self._source is not None:
            self._draw()

    def _on_baseline_parameters_changed(self, _value=None) -> None:
        self.degree_spin.setEnabled(
            self._baseline_algorithm_value() == "polynomial"
        )
        self._invalidate_preview()
        self._update_fit_info()
        self._update_action_state()
        if self._source is not None:
            self._draw()

    def _on_method_changed(self, _index: int) -> None:
        self._invalidate_preview()
        self._update_action_state()

    def _on_region_fields_changed(self, _text: str) -> None:
        self._invalidate_preview()
        self._update_fit_info()
        self._update_action_state()

    def _invalidate_preview(self) -> None:
        if self._preview_output is not None:
            self._clear_preview()
            if self._source is not None:
                self._draw()
            self.status_event.emit(
                {"level": "info", "key": "ftir.preview_cancelled"}
            )

    def _fit_info_text(self) -> str:
        if self._selected_operation() != "baseline":
            return ""
        degree = self._selected_degree()
        if isinstance(self._preview_operation, FTIRBaselineOperation) and self._preview_fit is not None:
            return self._t(
                "ftir.fit_info",
                degree=degree,
                points=self._preview_fit.fitting_point_count,
            )
        if self._session is not None and self._session.history:
            last = self._session.history[-1]
            if last.operation_id.startswith("ftir.baseline."):
                return self._t(
                    "ftir.fit_info_applied",
                    degree=last.parameters.get("degree", "unknown"),
                    points=last.diagnostics.get("fitting_point_count", "unknown"),
                )
        return self._t("ftir.fit_info_pending", degree=degree)

    def _update_fit_info(self) -> None:
        self.fit_info_label.setText(self._fit_info_text())

    def _add_region(self) -> None:
        try:
            start = float(self.region_start.text().strip())
            end = float(self.region_end.text().strip())
            region = BaselineRegion(start, end)
            if self._source is not None and not np.any(
                region.mask(self._source.axis.values)
            ):
                raise FTIRBaselineError(
                    self._t("ftir.region_no_points"),
                    code="ftir_baseline_empty_region",
                    context={"region": region.as_dict()},
                )
            updated = normalize_regions([*self._baseline_regions, region])
        except (ValueError, FTIRBaselineError) as exc:
            self.status_event.emit(
                {
                    "level": "error",
                    "key": "ftir.invalid_region",
                    "params": {"error": str(exc)},
                }
            )
            return
        self._baseline_regions = list(updated)
        self.region_start.blockSignals(True)
        self.region_end.blockSignals(True)
        self.region_start.clear()
        self.region_end.clear()
        self.region_start.blockSignals(False)
        self.region_end.blockSignals(False)
        self._refresh_region_list()
        self._invalidate_preview()
        self._update_fit_info()
        self._update_action_state()
        if self._source is not None:
            self._draw()

    def _remove_region(self) -> None:
        if not self._baseline_regions:
            return
        row = self.region_list.currentRow()
        if row < 0 or row >= len(self._baseline_regions):
            row = len(self._baseline_regions) - 1
        self._baseline_regions.pop(row)
        self._refresh_region_list()
        self._invalidate_preview()
        self._update_fit_info()
        self._update_action_state()
        if self._source is not None:
            self._draw()

    def _refresh_region_list(self) -> None:
        unit = ""
        values = None
        covered = None
        if self._source is not None:
            if self._source.axis.unit:
                unit = f" {self._source.axis.unit}"
            values = self._source.axis.values
            covered = np.zeros(values.size, dtype=bool)
        self.region_list.blockSignals(True)
        self.region_list.clear()
        for region in self._baseline_regions:
            suffix = ""
            if values is not None and covered is not None:
                region_mask = region.mask(values)
                unique_mask = region_mask & ~covered
                covered |= region_mask
                suffix = self._t(
                    "ftir.region_points",
                    points=int(np.count_nonzero(unique_mask)),
                )
            self.region_list.addItem(
                f"{region.start:g} – {region.end:g}{unit}{suffix}"
            )
        self.region_list.blockSignals(False)
        self.remove_region_button.setEnabled(
            bool(self._baseline_regions)
            and self._selected_operation() == "baseline"
            and self._session is not None
        )

    def _build_operation(self):
        if self._selected_operation() == "baseline":
            if not self._baseline_regions:
                raise FTIRBaselineError(
                    "At least one explicit fitting region is required.",
                    code="ftir_baseline_regions",
                )
            return create_baseline_operation(
                self._baseline_regions,
                self._selected_degree(),
            )
        return create_normalization_operation(self._selected_method())

    def _preview(self) -> None:
        if self._session is None:
            self._report_processing_error(ValueError(self._t("ftir.no_spectrum")))
            return
        self._clear_peak_preview_silent()
        try:
            operation = self._build_operation()
            if isinstance(operation, FTIRBaselineOperation):
                current = self._session.current
                fit = operation.fit(current.axis, current.signal)
                output = self._session.preview(operation)
                baseline_values = fit.evaluate(self._source.axis.values)
                self._preview_fit = fit
                self._preview_baseline_values = baseline_values
                status_key = "ftir.baseline_preview_ready"
                params = {
                    "algorithm": self._baseline_algorithm_label(),
                    "degree": operation.degree,
                    "points": fit.fitting_point_count,
                }
            else:
                output = self._session.preview(operation)
                self._preview_fit = None
                self._preview_baseline_values = None
                status_key = "ftir.preview_ready"
                params = {"method": self._method_label()}
        except Exception as exc:
            self._report_processing_error(exc)
            return
        self._preview_output = output
        self._preview_operation = operation
        self._draw()
        self._update_fit_info()
        self._update_action_state()
        self.status_event.emit(
            {
                "level": "info",
                "key": status_key,
                "params": params,
            }
        )

    def _apply(self) -> None:
        if self._session is None:
            self._report_processing_error(ValueError(self._t("ftir.no_spectrum")))
            return
        if self._preview_operation is None or self._preview_output is None:
            self.status_event.emit(
                {"level": "error", "key": "ftir.preview_required"}
            )
            return
        operation = self._preview_operation
        try:
            display = self._session.apply(operation)
        except Exception as exc:
            self._report_processing_error(exc)
            return
        self._display = display
        self._clear_preview()
        self._clear_peak_results_silent()
        self._draw()
        self._update_fit_info()
        self._update_action_state()
        self.spectrum_changed.emit(display)
        if isinstance(operation, FTIRBaselineOperation):
            record = display.history[-1]
            self.status_event.emit(
                {
                    "level": "success",
                    "key": "ftir.baseline_applied",
                    "params": {
                        "algorithm": self._baseline_algorithm_label(),
                        "degree": record.parameters["degree"],
                    },
                }
            )
        else:
            method = getattr(operation, "method", self._selected_method())
            self.status_event.emit(
                {
                    "level": "success",
                    "key": "ftir.normalization_applied",
                    "params": {"method": self._method_label(method)},
                }
            )

    def _cancel_preview(self) -> None:
        if self._preview_output is None:
            return
        self._clear_preview()
        self._draw()
        self._update_action_state()
        self.status_event.emit(
            {"level": "info", "key": "ftir.preview_cancelled"}
        )

    def _undo(self) -> None:
        if self._session is None:
            return
        self._clear_preview()
        result = self._session.undo()
        self._commit_result(result, "ftir.undo_applied")

    def _redo(self) -> None:
        if self._session is None:
            return
        self._clear_preview()
        result = self._session.redo()
        self._commit_result(result, "ftir.redo_applied")

    def _reset(self) -> None:
        if self._session is None:
            return
        self._clear_preview()
        result = self._session.reset()
        self._commit_result(result, "ftir.reset_applied")

    def _commit_result(self, result: ProcessedSpectrum, status_key: str) -> None:
        self._display = self._source if result.is_original else result
        self._clear_peak_results_silent()
        self._draw()
        self._update_action_state()
        self.spectrum_changed.emit(self._display)
        self.status_event.emit({"level": "info", "key": status_key})

    def _clear_preview(self) -> None:
        self._preview_output = None
        self._preview_operation = None
        self._preview_baseline_values = None
        self._preview_fit = None

    def _report_processing_error(self, exc: Exception) -> None:
        self.status_event.emit(
            {
                "level": "error",
                "key": "ftir.processing_failed",
                "params": {
                    "error": str(exc),
                    "code": getattr(exc, "code", "") or "",
                },
            }
        )

    def _update_action_state(self) -> None:
        session = self._session
        has_source = session is not None
        has_preview = self._preview_output is not None
        is_baseline = self._selected_operation() == "baseline"
        is_polynomial = self._baseline_algorithm_value() == "polynomial"
        self.operation_combo.setEnabled(has_source)
        self.method_combo.setEnabled(has_source and not is_baseline)
        self.baseline_algorithm.setEnabled(has_source and is_baseline)
        self.degree_spin.setEnabled(has_source and is_baseline and is_polynomial)
        self.region_start.setEnabled(has_source and is_baseline)
        self.region_end.setEnabled(has_source and is_baseline)
        self.add_region_button.setEnabled(has_source and is_baseline)
        self.remove_region_button.setEnabled(
            has_source and is_baseline and bool(self._baseline_regions)
        )
        self.region_list.setEnabled(has_source and is_baseline)
        self.preview_button.setEnabled(has_source)
        self.apply_button.setEnabled(has_source and has_preview)
        self.cancel_preview_button.setEnabled(has_preview)
        self.undo_button.setEnabled(bool(session and session.can_undo))
        self.redo_button.setEnabled(bool(session and session.can_redo))
        self.reset_button.setEnabled(
            bool(session and (session.can_undo or session.can_redo))
        )
        self._refresh_region_list()
        self._update_state_label()

    def _update_state_label(self) -> None:
        count = len(self._session.history) if self._session is not None else 0
        if self._preview_output is not None:
            if isinstance(self._preview_operation, FTIRBaselineOperation):
                fit = self._preview_fit
                self.state_label.setText(
                    self._t(
                        "ftir.baseline_preview_active",
                        algorithm=self._baseline_algorithm_label(),
                        degree=self._preview_operation.degree,
                        points=fit.fitting_point_count if fit else 0,
                    )
                )
            else:
                self.state_label.setText(
                    self._t(
                        "ftir.preview_active",
                        method=self._method_label(),
                    )
                )
        else:
            self.state_label.setText(
                self._t("ftir.processing_state", count=count)
            )

    # ------------------------------------------------------------- peak picking
    def _peak_source_value(self) -> str:
        return str(self.peak_source_combo.currentData() or "raw")

    def _peak_polarity_value(self) -> str:
        return str(self.peak_polarity_combo.currentData() or "positive")

    def _peak_source_label(self, source: str) -> str:
        return self._t(_PEAK_SOURCE_KEYS[source])

    def _peak_polarity_label(self, polarity: str) -> str:
        return self._t(_PEAK_POLARITY_KEYS[polarity])

    def _peak_number(self, field: QLineEdit) -> float | None:
        text = field.text().strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError as exc:
            raise PeakDetectionError(
                f"Peak parameter {text!r} is not a number.",
                code="ftir_peak_invalid_parameter",
                context={"value": text},
            ) from exc

    def _peak_source_data(self):
        if self._source is None:
            raise PeakDetectionError(
                self._t("ftir.no_spectrum"),
                code="ftir_peak_no_spectrum",
            )
        source = self._peak_source_value()
        if source == "raw":
            return source, self._source.axis, self._source.raw_signal, ()
        if self._session is None:
            raise PeakDetectionError(
                self._t("ftir.no_spectrum"),
                code="ftir_peak_no_spectrum",
            )
        current = self._session.current
        return (
            source,
            current.axis,
            current.signal,
            tuple(record.operation_id for record in self._session.history),
        )

    def _build_peak_parameters(self) -> PeakDetectionParameters:
        return PeakDetectionParameters(
            polarity=self._peak_polarity_value(),
            source=self._peak_source_value(),
            height=self._peak_number(self.peak_height),
            prominence=self._peak_number(self.peak_prominence),
            distance_points=int(self.peak_distance.value()),
            min_width_points=self._peak_number(self.peak_min_width),
        )

    def _preview_peaks(self) -> None:
        if self._source is None:
            self._report_peak_error(
                PeakDetectionError(
                    self._t("ftir.no_spectrum"),
                    code="ftir_peak_no_spectrum",
                )
            )
            return
        try:
            parameters = self._build_peak_parameters()
            source, axis, signal, history = self._peak_source_data()
            result = detect_peaks(
                axis,
                signal,
                parameters,
                dataset_id=self._source.dataset_id,
                source_operation_history=history,
            )
        except Exception as exc:
            self._report_peak_error(exc)
            return

        if self._preview_output is not None:
            self._clear_preview()
            self._update_action_state()
            self._update_fit_info()
        self._peak_preview_result = result
        self._update_peak_table()
        self._update_peak_controls()
        self._draw()
        self.status_event.emit(
            {
                "level": "info",
                "key": "ftir.peak_preview_ready",
                "params": {
                    "positive": result.positive_count,
                    "negative": result.negative_count,
                },
            }
        )

    def _apply_peaks(self) -> None:
        if self._peak_preview_result is None:
            self.status_event.emit(
                {"level": "error", "key": "ftir.peak_preview_required"}
            )
            return
        result = self._peak_preview_result
        self._peak_applied_result = result
        self._peak_preview_result = None
        self._update_peak_table()
        self._update_peak_controls()
        self._draw()
        self.status_event.emit(
            {
                "level": "success",
                "key": "ftir.peak_applied",
                "params": {
                    "positive": result.positive_count,
                    "negative": result.negative_count,
                },
            }
        )

    def _clear_peak_results(self) -> None:
        if (
            self._peak_preview_result is None
            and self._peak_applied_result is None
        ):
            return
        self._clear_peak_results_silent()
        if self._source is not None:
            self._draw()
        self.status_event.emit(
            {"level": "info", "key": "ftir.peak_cleared"}
        )

    def _clear_peak_results_silent(self) -> None:
        self._peak_preview_result = None
        self._peak_applied_result = None
        self._update_peak_table()
        self._update_peak_controls()

    def _clear_peak_preview_silent(self) -> None:
        if self._peak_preview_result is None:
            return
        self._peak_preview_result = None
        self._update_peak_table()
        self._update_peak_controls()

    def _on_peak_parameters_changed(self, _value=None) -> None:
        had_preview = self._peak_preview_result is not None
        if had_preview:
            self._peak_preview_result = None
            self._update_peak_table()
            self._update_peak_controls()
            if self._source is not None:
                self._draw()
            self.status_event.emit(
                {"level": "info", "key": "ftir.peak_preview_cancelled"}
            )
        else:
            self._update_peak_controls()

    def _report_peak_error(self, exc: Exception) -> None:
        self.status_event.emit(
            {
                "level": "error",
                "key": "ftir.peak_detection_failed",
                "params": {
                    "error": str(exc),
                    "code": getattr(exc, "code", "") or "",
                },
            }
        )

    def _update_peak_table(self) -> None:
        result = self._peak_preview_result or self._peak_applied_result
        self.peak_table.setRowCount(0)
        unit = self._t("app.unknown")
        signal_unit = self._t("app.unknown")
        if result is not None:
            unit = result.axis_unit or self._t("app.unknown")
            signal_unit = result.signal_unit or self._t("app.unknown")
        self.peak_table.setHorizontalHeaderLabels(
            [
                self._t("ftir.peak_index"),
                self._t("ftir.peak_polarity_col"),
                self._t("ftir.peak_x_header", unit=unit),
                self._t("ftir.peak_y_header", unit=signal_unit),
                self._t(
                    "ftir.peak_prominence_header",
                    unit=signal_unit,
                ),
                self._t("ftir.peak_width_samples_header"),
                self._t("ftir.peak_width_x_header", unit=unit),
            ]
        )
        if result is None:
            self.peak_status_label.setText(self._t("ftir.peak_no_result"))
            self.peak_parameter_label.clear()
            self.peak_warning_label.clear()
            self.peak_warning_label.setToolTip("")
            return

        self.peak_table.setRowCount(len(result.peaks))
        for row, peak in enumerate(result.peaks):
            values = (
                str(peak.index),
                self._peak_polarity_label(peak.polarity),
                f"{peak.x:.12g}",
                f"{peak.y:.12g}",
                f"{peak.prominence:.12g}",
                f"{peak.width_samples:.12g}",
                f"{peak.width_x:.12g}",
            )
            for column, value in enumerate(values):
                self.peak_table.setItem(row, column, QTableWidgetItem(value))
        is_preview = self._peak_preview_result is result
        summary_key = (
            "ftir.peak_preview_summary"
            if is_preview
            else "ftir.peak_applied_summary"
        )
        self.peak_status_label.setText(
            self._t(
                summary_key,
                source=self._peak_source_label(result.source),
                polarity=self._peak_polarity_label(
                    result.parameters.polarity
                ),
                positive=result.positive_count,
                negative=result.negative_count,
            )
        )
        params = result.parameters
        none_text = self._t("app.none")
        self.peak_parameter_label.setText(
            self._t(
                "ftir.peak_parameter_summary",
                height=(
                    none_text if params.height is None else f"{params.height:.12g}"
                ),
                prominence=(
                    none_text
                    if params.prominence is None
                    else f"{params.prominence:.12g}"
                ),
                distance=params.distance_points,
                width=(
                    none_text
                    if params.min_width_points is None
                    else f"{params.min_width_points:.12g}"
                ),
            )
        )
        if result.warnings:
            self.peak_warning_label.setText(
                self._t(
                    "ftir.peak_warnings",
                    warnings="; ".join(result.warnings),
                )
            )
        else:
            self.peak_warning_label.clear()
        self.peak_warning_label.setToolTip("; ".join(result.limitations))

    def _update_peak_controls(self) -> None:
        has_source = self._source is not None
        has_preview = self._peak_preview_result is not None
        has_result = bool(self._peak_preview_result or self._peak_applied_result)
        for widget in (
            self.peak_source_combo,
            self.peak_polarity_combo,
            self.peak_height,
            self.peak_prominence,
            self.peak_distance,
            self.peak_min_width,
            self.peak_preview_button,
        ):
            widget.setEnabled(has_source)
        self.peak_apply_button.setEnabled(has_source and has_preview)
        self.peak_clear_button.setEnabled(has_source and has_result)
        self.peak_table.setEnabled(has_source)

    # ---------------------------------------------------------------- access
    def current_display(self):
        return self._display

    @property
    def processing_session(self) -> ProcessingSession | None:
        return self._session

    @property
    def preview_output(self) -> OperationOutput | None:
        return self._preview_output

    @property
    def peak_result(self) -> PeakDetectionResult | None:
        return self._peak_preview_result or self._peak_applied_result

    @property
    def peak_preview_result(self) -> PeakDetectionResult | None:
        return self._peak_preview_result

    @property
    def peak_applied_result(self) -> PeakDetectionResult | None:
        return self._peak_applied_result

    @property
    def source_spectrum(self) -> Spectrum1D | None:
        return self._source

    @property
    def source_path(self) -> Path | None:
        return self._path

    @property
    def warnings(self) -> tuple[str, ...]:
        return self._warnings


def create_panel(controller, translator):
    """Create one FTIR panel for the generic shell."""
    return FtirPanel(controller, translator)


__all__ = ["FtirPanel", "create_panel"]
