"""FTIR import and raw-display panel for the generic SpectraLab shell.

The FTIR backend remains Qt-free. This app-layer panel builds explicit M9
``FTIRImportOptions``, asks the generic controller to import, and displays the
returned ``Spectrum1D`` through the M5 plotting API. It never processes data.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    QFileDialog,
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

from spectralab.app.ftir_export import (
    export_ftir_difference_csv,
    export_ftir_difference_json,
    export_ftir_difference_png,
    export_ftir_spectrum_csv,
    export_ftir_spectrum_json,
    export_ftir_spectrum_png,
)
from spectralab.app.gui.controller import ApplicationController
from spectralab.app.gui.ftir_import_dialog import FtirImportDialog
from spectralab.app.gui.ftir_options_widget import FtirOptionsWidget
from spectralab.app.gui.i18n import Translator
from spectralab.core.errors import ExportSerializationError
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
    DIFFERENCE_AXIS_MATCHES,
    DIFFERENCE_SOURCES,
    DifferenceParameters,
    DifferenceResult,
    FTIRBaselineError,
    FTIRBaselineOperation,
    FTIRDifferenceError,
    FTIRImportOptions,
    NORMALIZATION_METHODS,
    PEAK_POLARITIES,
    PEAK_SOURCES,
    PeakDetectionError,
    PeakDetectionParameters,
    PeakDetectionResult,
    compute_difference,
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
_DIFFERENCE_SOURCE_KEYS = {
    "raw": "ftir.peak_source_raw",
    "processed": "ftir.peak_source_processed",
}
_DIFFERENCE_AXIS_MATCH_KEYS = {
    "exact": "ftir.difference_exact",
    "interpolate": "ftir.difference_interpolate",
}
_EXPORT_FORMATS = ("csv", "json", "png")
_EXPORT_FORMAT_KEYS = {
    "csv": "ftir.export_format_csv",
    "json": "ftir.export_format_json",
    "png": "ftir.export_format_png",
}
_EXPORT_FORMAT_FILTERS = {
    "csv": "CSV (*.csv)",
    "json": "JSON (*.json)",
    "png": "PNG (*.png)",
}


@dataclass
class _FtirWorkspace:
    """One imported FTIR spectrum with its own independent processing session."""

    key: str
    path: Path
    spectrum: Spectrum1D
    session: ProcessingSession
    options: FTIRImportOptions
    warnings: tuple[str, ...]
    display: Spectrum1D | ProcessedSpectrum
    baseline_regions: tuple[BaselineRegion, ...] = ()


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
        self._difference_preview_result: DifferenceResult | None = None
        self._difference_applied_result: DifferenceResult | None = None
        self._difference_preview_workspaces: tuple[str, str] | None = None
        self._difference_applied_workspaces: tuple[str, str] | None = None
        self._plot_mode = "normal"
        self._workspaces: list[_FtirWorkspace] = []
        self._active_key: str | None = None
        self._workspace_counter = 0
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
        self.dataset_label = QLabel()
        file_row.addWidget(self.dataset_label)
        self.dataset_combo = QComboBox()
        self.dataset_combo.currentIndexChanged.connect(
            self._on_dataset_selected
        )
        file_row.addWidget(self.dataset_combo, 1)
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

        self.difference_tab = QWidget()
        self._build_difference_tab(self.difference_tab)
        self.bottom_tabs.addTab(self.difference_tab, "")

        self.export_tab = QWidget()
        self._build_export_tab(self.export_tab)
        self.bottom_tabs.addTab(self.export_tab, "")
        self.bottom_tabs.currentChanged.connect(self._on_bottom_tab_changed)
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

    def _build_difference_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(4, 4, 4, 4)
        form = QFormLayout()

        self.difference_a_label = QLabel()
        self.difference_a_combo = QComboBox()
        self.difference_a_combo.currentIndexChanged.connect(
            self._on_difference_a_changed
        )
        form.addRow(self.difference_a_label, self.difference_a_combo)

        self.difference_b_label = QLabel()
        self.difference_b_combo = QComboBox()
        self.difference_b_combo.currentIndexChanged.connect(
            self._on_difference_parameters_changed
        )
        form.addRow(self.difference_b_label, self.difference_b_combo)

        self.difference_source_a_label = QLabel()
        self.difference_source_a_combo = QComboBox()
        for source in DIFFERENCE_SOURCES:
            self.difference_source_a_combo.addItem("", source)
        self.difference_source_a_combo.currentIndexChanged.connect(
            self._on_difference_parameters_changed
        )
        form.addRow(self.difference_source_a_label, self.difference_source_a_combo)

        self.difference_source_b_label = QLabel()
        self.difference_source_b_combo = QComboBox()
        for source in DIFFERENCE_SOURCES:
            self.difference_source_b_combo.addItem("", source)
        self.difference_source_b_combo.currentIndexChanged.connect(
            self._on_difference_parameters_changed
        )
        form.addRow(self.difference_source_b_label, self.difference_source_b_combo)

        self.difference_axis_match_label = QLabel()
        self.difference_axis_match_combo = QComboBox()
        for mode in DIFFERENCE_AXIS_MATCHES:
            self.difference_axis_match_combo.addItem("", mode)
        self.difference_axis_match_combo.currentIndexChanged.connect(
            self._on_difference_parameters_changed
        )
        form.addRow(
            self.difference_axis_match_label,
            self.difference_axis_match_combo,
        )
        layout.addLayout(form)

        self.difference_target_label = QLabel()
        self.difference_target_label.setWordWrap(True)
        layout.addWidget(self.difference_target_label)

        actions = QHBoxLayout()
        self.difference_preview_button = QPushButton()
        self.difference_preview_button.clicked.connect(self._preview_difference)
        self.difference_apply_button = QPushButton()
        self.difference_apply_button.clicked.connect(self._apply_difference)
        self.difference_clear_button = QPushButton()
        self.difference_clear_button.clicked.connect(self._clear_difference_results)
        actions.addWidget(self.difference_preview_button)
        actions.addWidget(self.difference_apply_button)
        actions.addWidget(self.difference_clear_button)
        layout.addLayout(actions)

        self.difference_status_label = QLabel()
        self.difference_status_label.setWordWrap(True)
        layout.addWidget(self.difference_status_label)
        self.difference_parameter_label = QLabel()
        self.difference_parameter_label.setWordWrap(True)
        layout.addWidget(self.difference_parameter_label)
        self.difference_warning_label = QLabel()
        self.difference_warning_label.setWordWrap(True)
        layout.addWidget(self.difference_warning_label)

        export_row = QHBoxLayout()
        self.difference_export_format_label = QLabel()
        export_row.addWidget(self.difference_export_format_label)
        self.difference_export_format_combo = QComboBox()
        for export_format in _EXPORT_FORMATS:
            self.difference_export_format_combo.addItem("", export_format)
        export_row.addWidget(self.difference_export_format_combo)
        self.difference_export_overwrite_check = QCheckBox()
        export_row.addWidget(self.difference_export_overwrite_check)
        self.difference_export_button = QPushButton()
        self.difference_export_button.clicked.connect(self._export_difference)
        export_row.addWidget(self.difference_export_button)
        layout.addLayout(export_row)
        self.difference_export_status_label = QLabel()
        self.difference_export_status_label.setWordWrap(True)
        layout.addWidget(self.difference_export_status_label)
        layout.addStretch(1)

    def _build_export_tab(self, parent: QWidget) -> None:
        layout = QVBoxLayout(parent)
        layout.setContentsMargins(4, 4, 4, 4)
        form = QFormLayout()
        self.export_source_label = QLabel()
        self.export_source_combo = QComboBox()
        for source in DIFFERENCE_SOURCES:
            self.export_source_combo.addItem("", source)
        form.addRow(self.export_source_label, self.export_source_combo)

        self.export_format_label = QLabel()
        self.export_format_combo = QComboBox()
        for export_format in _EXPORT_FORMATS:
            self.export_format_combo.addItem("", export_format)
        form.addRow(self.export_format_label, self.export_format_combo)
        layout.addLayout(form)

        self.export_overwrite_check = QCheckBox()
        layout.addWidget(self.export_overwrite_check)
        self.export_button = QPushButton()
        self.export_button.clicked.connect(self._export_spectrum)
        layout.addWidget(self.export_button)
        self.export_status_label = QLabel()
        self.export_status_label.setWordWrap(True)
        layout.addWidget(self.export_status_label)
        layout.addStretch(1)

    # ------------------------------------------------------------- language
    def retranslate(self) -> None:
        self.dataset_label.setText(self._t("ftir.dataset_selector"))
        self._sync_dataset_combo()
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
        self.bottom_tabs.setTabText(2, self._t("ftir.tab_difference"))
        self.bottom_tabs.setTabText(3, self._t("ftir.tab_export"))
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
        self.difference_a_label.setText(self._t("ftir.difference_a"))
        self.difference_b_label.setText(self._t("ftir.difference_b"))
        self.difference_source_a_label.setText(
            self._t("ftir.difference_source_a")
        )
        self.difference_source_b_label.setText(
            self._t("ftir.difference_source_b")
        )
        self.difference_axis_match_label.setText(
            self._t("ftir.difference_axis_match")
        )
        self._retranslate_difference_sources()
        self._retranslate_difference_axis_matches()
        self.difference_target_label.setText(
            self._t("ftir.difference_target_note")
        )
        self.difference_preview_button.setText(
            self._t("ftir.difference_preview")
        )
        self.difference_apply_button.setText(self._t("ftir.difference_apply"))
        self.difference_clear_button.setText(self._t("ftir.difference_clear"))
        self.difference_export_format_label.setText(
            self._t("ftir.export_format")
        )
        self._retranslate_export_formats()
        self.difference_export_overwrite_check.setText(
            self._t("ftir.export_overwrite")
        )
        self.difference_export_button.setText(
            self._t("ftir.difference_export_button")
        )
        self.export_source_label.setText(self._t("ftir.export_source"))
        self.export_format_label.setText(self._t("ftir.export_format"))
        self.export_overwrite_check.setText(self._t("ftir.export_overwrite"))
        self.export_button.setText(self._t("ftir.export_spectrum_button"))
        self._retranslate_export_sources()
        self._populate_difference_selectors()
        self._update_difference_panel()
        self._update_export_controls()
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

    def _retranslate_difference_sources(self) -> None:
        for combo in (
            self.difference_source_a_combo,
            self.difference_source_b_combo,
        ):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for source in DIFFERENCE_SOURCES:
                combo.addItem(self._t(_DIFFERENCE_SOURCE_KEYS[source]), source)
            index = combo.findData(current)
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.blockSignals(False)

    def _retranslate_difference_axis_matches(self) -> None:
        current = self.difference_axis_match_combo.currentData()
        self.difference_axis_match_combo.blockSignals(True)
        self.difference_axis_match_combo.clear()
        for mode in DIFFERENCE_AXIS_MATCHES:
            self.difference_axis_match_combo.addItem(
                self._t(_DIFFERENCE_AXIS_MATCH_KEYS[mode]),
                mode,
            )
        index = self.difference_axis_match_combo.findData(current)
        if index >= 0:
            self.difference_axis_match_combo.setCurrentIndex(index)
        self.difference_axis_match_combo.blockSignals(False)

    def _retranslate_export_formats(self) -> None:
        for combo in (
            self.export_format_combo,
            self.difference_export_format_combo,
        ):
            current = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for export_format in _EXPORT_FORMATS:
                combo.addItem(
                    self._t(_EXPORT_FORMAT_KEYS[export_format]),
                    export_format,
                )
            index = combo.findData(current)
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.blockSignals(False)

    def _retranslate_export_sources(self) -> None:
        current = self.export_source_combo.currentData()
        self.export_source_combo.blockSignals(True)
        self.export_source_combo.clear()
        for source in DIFFERENCE_SOURCES:
            self.export_source_combo.addItem(
                self._t(_DIFFERENCE_SOURCE_KEYS[source]),
                source,
            )
        index = self.export_source_combo.findData(current)
        if index >= 0:
            self.export_source_combo.setCurrentIndex(index)
        self.export_source_combo.blockSignals(False)

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

        self._workspace_counter += 1
        existing = next(
            (item for item in self._workspaces if item.path == source_path),
            None,
        )
        key = (
            existing.key
            if existing is not None
            else f"ftir-workspace-{self._workspace_counter}"
        )
        workspace = _FtirWorkspace(
            key=key,
            path=source_path,
            spectrum=loaded.spectrum,
            session=ProcessingSession(loaded.spectrum),
            options=options,
            warnings=tuple(loaded.dataset.warnings),
            display=loaded.spectrum,
        )
        if existing is not None:
            self._workspaces[self._workspaces.index(existing)] = workspace
        else:
            self._workspaces.append(workspace)
        self._clear_difference_results_silent()
        self.export_status_label.clear()
        self.difference_export_status_label.clear()
        self._activate_workspace(workspace, reset=True)
        self.options_widget.set_effective_metadata(loaded.spectrum)
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

    def _workspace_label(self, workspace: _FtirWorkspace) -> str:
        return self._t(
            "ftir.dataset_item",
            name=workspace.path.name,
            dataset_id=workspace.spectrum.dataset_id,
        )

    def _workspace_by_key(self, key: str | None) -> _FtirWorkspace | None:
        if key is None:
            return None
        return next(
            (item for item in self._workspaces if item.key == key),
            None,
        )

    def _active_workspace(self) -> _FtirWorkspace | None:
        return self._workspace_by_key(self._active_key)

    def _store_active_workspace(self) -> None:
        workspace = self._active_workspace()
        if workspace is None:
            return
        workspace.display = self._display
        workspace.baseline_regions = tuple(self._baseline_regions)

    def _sync_dataset_combo(self) -> None:
        current = self._active_key
        self.dataset_combo.blockSignals(True)
        self.dataset_combo.clear()
        for workspace in self._workspaces:
            self.dataset_combo.addItem(
                self._workspace_label(workspace),
                workspace.key,
            )
        index = self.dataset_combo.findData(current)
        if index >= 0:
            self.dataset_combo.setCurrentIndex(index)
        self.dataset_combo.blockSignals(False)
        self.dataset_combo.setEnabled(bool(self._workspaces))

    def _activate_workspace(
        self,
        workspace: _FtirWorkspace,
        *,
        reset: bool,
    ) -> None:
        self._active_key = workspace.key
        self._source = workspace.spectrum
        self._session = workspace.session
        self._display = workspace.display
        self._path = workspace.path
        self._warnings = workspace.warnings
        self._baseline_regions = list(workspace.baseline_regions)
        self._clear_preview()
        self._clear_peak_results_silent()
        self._plot_mode = "normal"
        self.export_status_label.clear()
        self.difference_export_status_label.clear()
        self.options_widget.set_options(workspace.options)
        self._sync_dataset_combo()
        self._update_display_controls(reset=reset)
        self._refresh_region_list()
        self._update_action_state()
        self._populate_difference_selectors()
        self._update_difference_panel()

    def _on_dataset_selected(self, index: int) -> None:
        key = self.dataset_combo.itemData(index)
        if not isinstance(key, str) or key == self._active_key:
            return
        workspace = self._workspace_by_key(key)
        if workspace is None:
            return
        self._store_active_workspace()
        self._clear_preview()
        self._clear_peak_results_silent()
        self._plot_mode = "normal"
        self._activate_workspace(workspace, reset=False)
        self.retranslate()
        self.spectrum_changed.emit(self._display)
        self.status_event.emit(
            {
                "level": "info",
                "key": "ftir.dataset_switched",
                "params": {"name": workspace.path.name},
            }
        )

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
        if self._plot_mode == "difference":
            difference_result = (
                self._difference_preview_result
                or self._difference_applied_result
            )
            if difference_result is not None:
                self._draw_difference_result(difference_result)
                return
            self._plot_mode = "normal"
        elif self._plot_mode == "peak":
            peak_result = (
                self._peak_preview_result or self._peak_applied_result
            )
            if peak_result is not None:
                self._draw_peak_result(peak_result)
                return
            self._plot_mode = "normal"
        title = self._source.metadata.title or self._source.dataset_id
        config = PlotConfig(
            title=title,
            xlabel=self._axis_label(self._source.axis),
            ylabel=self._signal_label(self._source.raw_signal),
            raw_label=self._t("ftir.raw_label"),
            processed_label=self._processed_label(),
        )
        if self._plot_mode == "processing" and self._preview_output is not None:
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

    def _difference_source_arrays(
        self,
        workspace: _FtirWorkspace,
        source: str,
    ) -> tuple[Axis1D, Signal1D]:
        if source == "raw":
            return workspace.spectrum.axis, workspace.spectrum.raw_signal
        current = workspace.session.current
        return current.axis, current.signal

    def _draw_difference_result(self, result: DifferenceResult) -> None:
        keys = (
            self._difference_preview_workspaces
            if result is self._difference_preview_result
            else self._difference_applied_workspaces
        )
        workspace_a = self._workspace_by_key(keys[0]) if keys else None
        workspace_b = self._workspace_by_key(keys[1]) if keys else None

        self.axes.clear()
        if workspace_a is not None:
            axis_a, signal_a = self._difference_source_arrays(
                workspace_a,
                result.source_a,
            )
            self.axes.plot(
                axis_a.values,
                signal_a.values,
                color="#1f77b4",
                linewidth=1.1,
                linestyle="-",
                label=self._t(
                    "ftir.difference_plot_a",
                    name=workspace_a.path.name,
                ),
            )
        if workspace_b is not None:
            axis_b, signal_b = self._difference_source_arrays(
                workspace_b,
                result.source_b,
            )
            self.axes.plot(
                axis_b.values,
                signal_b.values,
                color="#ff7f0e",
                linewidth=1.1,
                linestyle="-",
                label=self._t(
                    "ftir.difference_plot_b",
                    name=workspace_b.path.name,
                ),
            )
        if result.interpolation is not None:
            self.axes.plot(
                result.axis.values,
                result.interpolation.aligned_b_signal.values,
                color="#8c564b",
                linewidth=1.0,
                linestyle="--",
                label=self._t("ftir.difference_plot_b_interpolated"),
            )
        self.axes.plot(
            result.axis.values,
            result.signal.values,
            color="#2e7d32",
            linewidth=1.8,
            linestyle="-",
            label=self._t("ftir.difference_plot_difference"),
        )
        self.axes.set_title(self._t("ftir.difference_plot_title"))
        self.axes.set_xlabel(self._axis_label(result.axis))
        self.axes.set_ylabel(self._signal_label(result.signal))
        self.axes.grid(
            True,
            which="major",
            color="#b0b0b0",
            alpha=0.35,
            linewidth=0.6,
        )
        self.axes.legend(loc="best", frameon=False)
        if (
            self.invert_axis_check.isChecked()
            and result.axis.quantity == "wavenumber"
        ):
            x_min = float(result.axis.values.min())
            x_max = float(result.axis.values.max())
            self.axes.set_xlim(x_max, x_min)
        self.canvas.draw_idle()

    def _on_bottom_tab_changed(self, index: int) -> None:
        widget = self.bottom_tabs.widget(index)
        if widget is self.difference_tab and self.difference_result is not None:
            self._plot_mode = "difference"
        elif widget is self.peak_tab and (
            self._peak_preview_result is not None
            or self._peak_applied_result is not None
        ):
            self._plot_mode = "peak"
        elif self._preview_output is not None:
            self._plot_mode = "processing"
        else:
            self._plot_mode = "normal"
        if self._source is not None:
            self._draw()

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
            if self._plot_mode == "processing":
                self._plot_mode = "normal"
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
        self._store_active_workspace()
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
        self._store_active_workspace()
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
        self._plot_mode = "processing"
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
        self._store_active_workspace()
        self._clear_preview()
        self._clear_peak_results_silent()
        self._clear_difference_results_silent()
        self._plot_mode = "normal"
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
        if self._plot_mode == "processing":
            self._plot_mode = "normal"
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
        self._store_active_workspace()
        self._clear_peak_results_silent()
        self._clear_difference_results_silent()
        self._plot_mode = "normal"
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
        self._update_export_controls()

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
        self._plot_mode = "peak"
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
        self._plot_mode = "peak"
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
        if self._plot_mode == "peak":
            self._plot_mode = "normal"
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
            self._plot_mode = (
                "peak"
                if self._peak_applied_result is not None
                else "normal"
            )
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

    # ------------------------------------------------------------ difference
    def _difference_source_value(self, combo: QComboBox) -> str:
        return str(combo.currentData() or "raw")

    def _difference_axis_match_value(self) -> str:
        return str(self.difference_axis_match_combo.currentData() or "exact")

    def _difference_axis_match_label(self, value: str | None = None) -> str:
        return self._t(
            _DIFFERENCE_AXIS_MATCH_KEYS[value or self._difference_axis_match_value()]
        )

    def _difference_source_label(self, value: str) -> str:
        return self._t(_DIFFERENCE_SOURCE_KEYS[value])

    def _populate_difference_selectors(self) -> None:
        a_key = self.difference_a_combo.currentData()
        if self._workspace_by_key(a_key) is None:
            a_key = self._workspaces[0].key if self._workspaces else None
        a_workspace = self._workspace_by_key(a_key)

        self.difference_a_combo.blockSignals(True)
        self.difference_a_combo.clear()
        for workspace in self._workspaces:
            self.difference_a_combo.addItem(
                self._workspace_label(workspace),
                workspace.key,
            )
        index = self.difference_a_combo.findData(a_key)
        if index >= 0:
            self.difference_a_combo.setCurrentIndex(index)
        self.difference_a_combo.blockSignals(False)

        b_key = self.difference_b_combo.currentData()
        b_workspace = self._workspace_by_key(b_key)
        if (
            b_workspace is None
            or a_workspace is None
            or b_workspace.key == a_workspace.key
            or b_workspace.spectrum.dataset_id
            == a_workspace.spectrum.dataset_id
        ):
            b_key = None
        if b_key is None and a_workspace is not None:
            candidate = next(
                (
                    workspace
                    for workspace in self._workspaces
                    if workspace.key != a_workspace.key
                    and workspace.spectrum.dataset_id
                    != a_workspace.spectrum.dataset_id
                ),
                None,
            )
            if candidate is not None:
                b_key = candidate.key

        self.difference_b_combo.blockSignals(True)
        self.difference_b_combo.clear()
        for workspace in self._workspaces:
            if a_workspace is not None and (
                workspace.key == a_workspace.key
                or workspace.spectrum.dataset_id
                == a_workspace.spectrum.dataset_id
            ):
                continue
            self.difference_b_combo.addItem(
                self._workspace_label(workspace),
                workspace.key,
            )
        index = self.difference_b_combo.findData(b_key)
        if index >= 0:
            self.difference_b_combo.setCurrentIndex(index)
        self.difference_b_combo.blockSignals(False)
        self._update_difference_panel()

    def _on_difference_a_changed(self, _index: int = 0) -> None:
        self._populate_difference_selectors()
        self._on_difference_parameters_changed()

    def _on_difference_parameters_changed(self, _value=None) -> None:
        had_preview = self._difference_preview_result is not None
        if had_preview:
            self._difference_preview_result = None
            self._difference_preview_workspaces = None
            if self._difference_applied_result is not None:
                self._plot_mode = "difference"
            elif self._plot_mode == "difference":
                self._plot_mode = "normal"
            if self._source is not None:
                self._draw()
            self.status_event.emit(
                {
                    "level": "info",
                    "key": "ftir.difference_preview_cancelled",
                }
            )
        self._update_difference_panel()

    def _build_difference_parameters(self) -> DifferenceParameters:
        return DifferenceParameters(
            axis_match=self._difference_axis_match_value(),
            source_a=self._difference_source_value(
                self.difference_source_a_combo
            ),
            source_b=self._difference_source_value(
                self.difference_source_b_combo
            ),
        )

    def _difference_source_data(
        self,
        workspace_combo: QComboBox,
        source_combo: QComboBox,
    ):
        key = workspace_combo.currentData()
        workspace = self._workspace_by_key(key)
        if workspace is None:
            raise FTIRDifferenceError(
                self._t("ftir.difference_select_spectra"),
                code="ftir_difference_selection",
            )
        source = self._difference_source_value(source_combo)
        if source == "raw":
            return (
                workspace,
                source,
                workspace.spectrum.axis,
                workspace.spectrum.raw_signal,
                (),
            )
        current = workspace.session.current
        return (
            workspace,
            source,
            current.axis,
            current.signal,
            tuple(record.operation_id for record in workspace.session.history),
        )

    def _preview_difference(self) -> None:
        try:
            parameters = self._build_difference_parameters()
            workspace_a, source_a, axis_a, signal_a, history_a = (
                self._difference_source_data(
                    self.difference_a_combo,
                    self.difference_source_a_combo,
                )
            )
            workspace_b, source_b, axis_b, signal_b, history_b = (
                self._difference_source_data(
                    self.difference_b_combo,
                    self.difference_source_b_combo,
                )
            )
            result = compute_difference(
                axis_a,
                signal_a,
                axis_b,
                signal_b,
                parameters,
                dataset_a_id=workspace_a.spectrum.dataset_id,
                dataset_b_id=workspace_b.spectrum.dataset_id,
                source_operation_history_a=history_a,
                source_operation_history_b=history_b,
            )
        except Exception as exc:
            self._report_difference_error(exc)
            return

        if self._preview_output is not None:
            self._clear_preview()
        self._clear_peak_preview_silent()
        self._difference_preview_result = result
        self._difference_preview_workspaces = (
            workspace_a.key,
            workspace_b.key,
        )
        self._plot_mode = "difference"
        self._update_difference_panel()
        self._draw()
        self.status_event.emit(
            {
                "level": "info",
                "key": "ftir.difference_preview_ready",
                "params": {
                    "points": result.point_count,
                    "axis_match": self._difference_axis_match_label(
                        result.axis_match
                    ),
                },
            }
        )

    def _apply_difference(self) -> None:
        if self._difference_preview_result is None:
            self.status_event.emit(
                {
                    "level": "error",
                    "key": "ftir.difference_preview_required",
                }
            )
            return
        result = self._difference_preview_result
        keys = self._difference_preview_workspaces
        self._difference_applied_result = result
        self._difference_applied_workspaces = keys
        self._difference_preview_result = None
        self._difference_preview_workspaces = None
        self._plot_mode = "difference"
        self._update_difference_panel()
        self._draw()
        self.status_event.emit(
            {
                "level": "success",
                "key": "ftir.difference_applied",
                "params": {
                    "points": result.point_count,
                    "axis_match": self._difference_axis_match_label(
                        result.axis_match
                    ),
                },
            }
        )

    def _clear_difference_results(self) -> None:
        if (
            self._difference_preview_result is None
            and self._difference_applied_result is None
        ):
            return
        self._clear_difference_results_silent()
        if self._plot_mode == "difference":
            self._plot_mode = "normal"
        if self._source is not None:
            self._draw()
        self.status_event.emit(
            {"level": "info", "key": "ftir.difference_cleared"}
        )

    def _clear_difference_results_silent(self) -> None:
        self._difference_preview_result = None
        self._difference_applied_result = None
        self._difference_preview_workspaces = None
        self._difference_applied_workspaces = None
        if self._plot_mode == "difference":
            self._plot_mode = "normal"
        self._update_difference_panel()

    def _update_difference_panel(self) -> None:
        result = (
            self._difference_preview_result
            or self._difference_applied_result
        )
        self._update_export_controls()
        has_workspaces = bool(self._workspaces)
        has_two = (
            len(self._workspaces) >= 2
            and self.difference_b_combo.count() > 0
        )
        for widget in (
            self.difference_a_combo,
            self.difference_b_combo,
            self.difference_source_a_combo,
            self.difference_source_b_combo,
            self.difference_axis_match_combo,
        ):
            widget.setEnabled(has_workspaces)
        self.difference_preview_button.setEnabled(has_two)
        self.difference_apply_button.setEnabled(
            self._difference_preview_result is not None
        )
        self.difference_clear_button.setEnabled(result is not None)
        if result is None:
            self.difference_status_label.setText(
                self._t("ftir.difference_no_result")
            )
            self.difference_parameter_label.clear()
            self.difference_warning_label.clear()
            self.difference_warning_label.setToolTip("")
            self.difference_export_status_label.clear()
            return

        is_preview = self._difference_preview_result is result
        keys = (
            self._difference_preview_workspaces
            if is_preview
            else self._difference_applied_workspaces
        )
        workspace_a = self._workspace_by_key(keys[0]) if keys else None
        workspace_b = self._workspace_by_key(keys[1]) if keys else None
        name_a = (
            workspace_a.path.name
            if workspace_a is not None
            else result.dataset_a_id
        )
        name_b = (
            workspace_b.path.name
            if workspace_b is not None
            else result.dataset_b_id
        )
        self.difference_status_label.setText(
            self._t(
                (
                    "ftir.difference_preview_summary"
                    if is_preview
                    else "ftir.difference_applied_summary"
                ),
                a=name_a,
                b=name_b,
                axis_match=self._difference_axis_match_label(
                    result.axis_match
                ),
                points=result.point_count,
            )
        )
        self.difference_parameter_label.setText(
            self._t(
                "ftir.difference_parameter_summary",
                source_a=self._difference_source_label(result.source_a),
                source_b=self._difference_source_label(result.source_b),
                axis_match=self._difference_axis_match_label(
                    result.axis_match
                ),
            )
        )
        if result.warnings:
            self.difference_warning_label.setText(
                self._t(
                    "ftir.difference_warnings",
                    warnings="; ".join(result.warnings),
                )
            )
        else:
            self.difference_warning_label.clear()
        self.difference_warning_label.setToolTip(
            "; ".join(result.limitations)
        )

    def _report_difference_error(self, exc: Exception) -> None:
        self.status_event.emit(
            {
                "level": "error",
                "key": "ftir.difference_failed",
                "params": {
                    "error": str(exc),
                    "code": getattr(exc, "code", "") or "",
                },
            }
        )

    # --------------------------------------------------------------- export
    def _export_format_value(self, combo: QComboBox) -> str:
        return str(combo.currentData() or "csv")

    def _export_source_value(self) -> str:
        return str(self.export_source_combo.currentData() or "raw")

    def _peak_result_for(
        self,
        dataset_id: str,
        source: str,
    ) -> PeakDetectionResult | None:
        result = self._peak_preview_result or self._peak_applied_result
        if (
            result is None
            or result.dataset_id != dataset_id
            or result.source != source
        ):
            return None
        return result

    def _default_export_name(self, stem: str, suffix: str, export_format: str) -> str:
        return f"{stem}_{suffix}.{export_format}"

    def _ensure_export_suffix(self, path: Path, export_format: str) -> Path:
        expected = f".{export_format}"
        if path.suffix.casefold() == expected:
            return path
        return path.with_name(path.name + expected)

    def _current_export_source(self):
        if self._source is None:
            raise ExportSerializationError(
                self._t("ftir.export_no_spectrum"),
                code="ftir_export_no_spectrum",
            )
        selection = self._export_source_value()
        if selection == "raw":
            return selection, self._source
        if self._session is None:
            raise ExportSerializationError(
                self._t("ftir.export_no_spectrum"),
                code="ftir_export_no_spectrum",
            )
        return selection, self._session.current

    def export_current_spectrum(
        self,
        output_path: str | Path,
        *,
        export_format: str | None = None,
        source: str | None = None,
        overwrite: bool | None = None,
    ) -> list[Path]:
        """Export the selected raw/processed spectrum; return written paths."""
        if self._source is None:
            raise ExportSerializationError(
                self._t("ftir.export_no_spectrum"),
                code="ftir_export_no_spectrum",
            )
        selection = source or self._export_source_value()
        if selection not in ("raw", "processed"):
            raise ExportSerializationError(
                "Export source must be 'raw' or 'processed'.",
                code="ftir_export_invalid_source",
            )
        if selection == "processed":
            if self._session is None:
                raise ExportSerializationError(
                    self._t("ftir.export_no_spectrum"),
                    code="ftir_export_no_spectrum",
                )
            export_source = self._session.current
        else:
            export_source = self._source
        fmt = export_format or self._export_format_value(self.export_format_combo)
        overwrite_value = (
            self.export_overwrite_check.isChecked()
            if overwrite is None
            else bool(overwrite)
        )
        peak_result = self._peak_result_for(
            self._source.dataset_id,
            selection,
        )
        target = self._ensure_export_suffix(Path(output_path), fmt)
        if fmt == "csv":
            outputs = export_ftir_spectrum_csv(
                export_source,
                target,
                overwrite=overwrite_value,
                peak_result=peak_result,
            )
            return [outputs["csv"], outputs["metadata"]]
        if fmt == "json":
            return [
                export_ftir_spectrum_json(
                    export_source,
                    target,
                    overwrite=overwrite_value,
                    peak_result=peak_result,
                )
            ]
        if fmt == "png":
            return [
                export_ftir_spectrum_png(
                    export_source,
                    target,
                    overwrite=overwrite_value,
                )
            ]
        raise ExportSerializationError(
            f"Unsupported export format: {fmt!r}",
            code="ftir_export_invalid_format",
        )

    def _choose_export_path(
        self,
        default_name: str,
        export_format: str,
        *,
        title_key: str,
    ) -> Path | None:
        filename, _selected = QFileDialog.getSaveFileName(
            self,
            self._t(title_key),
            str(Path.cwd() / default_name),
            _EXPORT_FORMAT_FILTERS[export_format],
        )
        if not filename:
            return None
        return self._ensure_export_suffix(Path(filename), export_format)

    def _export_spectrum(self) -> None:
        if self._source is None:
            self.status_event.emit(
                {"level": "error", "key": "ftir.export_no_spectrum"}
            )
            return
        fmt = self._export_format_value(self.export_format_combo)
        selection = self._export_source_value()
        stem = self._path.stem if self._path is not None else self._source.dataset_id
        target = self._choose_export_path(
            self._default_export_name(stem, selection, fmt),
            fmt,
            title_key="ftir.export_dialog_title",
        )
        if target is None:
            self.status_event.emit(
                {"level": "info", "key": "ftir.export_cancelled"}
            )
            return
        try:
            paths = self.export_current_spectrum(
                target,
                export_format=fmt,
                source=selection,
            )
        except Exception as exc:
            self._report_export_error(exc, label=self.export_status_label)
            return
        joined = "; ".join(str(path) for path in paths)
        self.export_status_label.setText(
            self._t("ftir.export_completed", paths=joined)
        )
        self.status_event.emit(
            {
                "level": "success",
                "key": "ftir.export_completed",
                "params": {"paths": joined},
            }
        )

    def _difference_export_result(self) -> DifferenceResult:
        result = self._difference_preview_result or self._difference_applied_result
        if result is None:
            raise ExportSerializationError(
                self._t("ftir.difference_export_required"),
                code="ftir_difference_export_required",
            )
        return result

    def _difference_export_sources(self, result: DifferenceResult):
        keys = (
            self._difference_preview_workspaces
            if result is self._difference_preview_result
            else self._difference_applied_workspaces
        )
        if keys is None:
            raise ExportSerializationError(
                "Difference source workspaces are unavailable.",
                code="ftir_difference_export_sources",
            )
        workspace_a = self._workspace_by_key(keys[0])
        workspace_b = self._workspace_by_key(keys[1])
        if workspace_a is None or workspace_b is None:
            raise ExportSerializationError(
                "Difference source workspaces are no longer available.",
                code="ftir_difference_export_sources",
            )
        processed_a = (
            workspace_a.session.current
            if result.source_a == "processed"
            else None
        )
        processed_b = (
            workspace_b.session.current
            if result.source_b == "processed"
            else None
        )
        return workspace_a, workspace_b, processed_a, processed_b

    def export_saved_difference(
        self,
        output_path: str | Path,
        *,
        export_format: str | None = None,
        overwrite: bool | None = None,
    ) -> list[Path]:
        """Export the current preview/applied difference result."""
        result = self._difference_export_result()
        workspace_a, workspace_b, processed_a, processed_b = (
            self._difference_export_sources(result)
        )
        fmt = (
            export_format
            or self._export_format_value(self.difference_export_format_combo)
        )
        overwrite_value = (
            self.difference_export_overwrite_check.isChecked()
            if overwrite is None
            else bool(overwrite)
        )
        target = self._ensure_export_suffix(Path(output_path), fmt)
        role = "preview" if result is self._difference_preview_result else "applied"
        peak_a = self._peak_result_for(
            workspace_a.spectrum.dataset_id,
            result.source_a,
        )
        peak_b = self._peak_result_for(
            workspace_b.spectrum.dataset_id,
            result.source_b,
        )
        common = {
            "source_a": workspace_a.spectrum,
            "source_b": workspace_b.spectrum,
            "processed_a": processed_a,
            "processed_b": processed_b,
            "peak_result_a": peak_a,
            "peak_result_b": peak_b,
            "overwrite": overwrite_value,
            "result_role": role,
        }
        if fmt == "csv":
            outputs = export_ftir_difference_csv(result, target, **common)
            return [outputs["csv"], outputs["metadata"]]
        if fmt == "json":
            return [export_ftir_difference_json(result, target, **common)]
        if fmt == "png":
            labels = {
                "title": self._t("ftir.difference_plot_title"),
                "a": self._t(
                    "ftir.difference_plot_a",
                    name=workspace_a.path.name,
                ),
                "b": self._t(
                    "ftir.difference_plot_b",
                    name=workspace_b.path.name,
                ),
                "b_interpolated": self._t(
                    "ftir.difference_plot_b_interpolated"
                ),
                "difference": self._t(
                    "ftir.difference_plot_difference"
                ),
            }
            return [
                export_ftir_difference_png(
                    result,
                    target,
                    source_a=workspace_a.spectrum,
                    source_b=workspace_b.spectrum,
                    processed_b=processed_b,
                    overwrite=overwrite_value,
                    labels=labels,
                )
            ]
        raise ExportSerializationError(
            f"Unsupported export format: {fmt!r}",
            code="ftir_export_invalid_format",
        )

    def _export_difference(self) -> None:
        try:
            result = self._difference_export_result()
            workspace_a, workspace_b, _processed_a, _processed_b = (
                self._difference_export_sources(result)
            )
        except Exception as exc:
            self._report_export_error(
                exc,
                label=self.difference_export_status_label,
            )
            return
        fmt = self._export_format_value(
            self.difference_export_format_combo
        )
        target = self._choose_export_path(
            (
                f"{workspace_a.path.stem}_{workspace_b.path.stem}"
                f"_difference.{fmt}"
            ),
            fmt,
            title_key="ftir.difference_export_dialog_title",
        )
        if target is None:
            self.status_event.emit(
                {"level": "info", "key": "ftir.export_cancelled"}
            )
            return
        try:
            paths = self.export_saved_difference(
                target,
                export_format=fmt,
            )
        except Exception as exc:
            self._report_export_error(
                exc,
                label=self.difference_export_status_label,
            )
            return
        joined = "; ".join(str(path) for path in paths)
        self.difference_export_status_label.setText(
            self._t("ftir.export_completed", paths=joined)
        )
        self.status_event.emit(
            {
                "level": "success",
                "key": "ftir.export_completed",
                "params": {"paths": joined},
            }
        )

    def _report_export_error(
        self,
        exc: Exception,
        *,
        label: QLabel,
    ) -> None:
        code = getattr(exc, "code", "") or ""
        message = str(exc)
        label.setText(
            self._t("ftir.export_failed", code=code, error=message)
        )
        self.status_event.emit(
            {
                "level": "error",
                "key": "ftir.export_failed",
                "params": {"code": code, "error": message},
            }
        )

    def _update_export_controls(self) -> None:
        has_source = self._source is not None
        self.export_source_combo.setEnabled(has_source)
        self.export_format_combo.setEnabled(has_source)
        self.export_overwrite_check.setEnabled(has_source)
        self.export_button.setEnabled(has_source)
        has_difference = self.difference_result is not None
        self.difference_export_format_combo.setEnabled(has_difference)
        self.difference_export_overwrite_check.setEnabled(has_difference)
        self.difference_export_button.setEnabled(has_difference)

    # ---------------------------------------------------------------- access
    def current_display(self):
        return self._display

    @property
    def difference_result(self) -> DifferenceResult | None:
        return (
            self._difference_preview_result
            or self._difference_applied_result
        )

    @property
    def difference_preview_result(self) -> DifferenceResult | None:
        return self._difference_preview_result

    @property
    def difference_applied_result(self) -> DifferenceResult | None:
        return self._difference_applied_result

    @property
    def loaded_dataset_ids(self) -> tuple[str, ...]:
        return tuple(
            workspace.spectrum.dataset_id for workspace in self._workspaces
        )

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
