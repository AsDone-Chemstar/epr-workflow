"""PySide6 main window for the EPR workflow desktop GUI.

The window is a thin view layer: it collects user input, calls the
GUI-agnostic controller in :mod:`epr_workflow.gui.controller`, and renders
the returned data. No signal processing is performed here.

All user-facing text goes through :func:`epr_workflow.gui.i18n.tr_text`; the
selected language can be switched at run time without reloading any file.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from matplotlib.backends.backend_qtagg import NavigationToolbar2QT

from epr_workflow.gui.controller import (
    BatchOutcome,
    PreprocessingStore,
    SpectrumView,
    load_spectrum,
    open_path,
    run_batch_processing,
)
from epr_workflow.gui.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    field_order_text,
    has_text,
    normalize_language,
    overall_status_text,
    status_text,
    tr_text,
)
from epr_workflow.gui.mpl_canvas import MplCanvas
from epr_workflow.gui.plot_editor_panel import (
    TEXT_KEYS as PLOT_EDITOR_TEXT_KEYS,
    PlotEditorPanel,
)
from epr_workflow.gui.plot_export_dialog import (
    TEXT_KEYS as PLOT_EXPORT_TEXT_KEYS,
    PlotExportDialog,
)
from epr_workflow.gui.preprocessing_panel import TEXT_KEYS, PreprocessingPanel
from epr_workflow.plot_asc import PROJECT_ROOT
from epr_workflow.plot_export import (
    PlotExportSettings,
    default_plot_path,
    export_plot_png,
)
from epr_workflow.plot_settings import (
    CURVE_KEYS,
    PlotSettings,
    PlotSettingsError,
    PlotSettingsStore,
    available_curve_keys,
    build_curves,
    curve_data_ranges,
    default_curve_label_key,
    default_settings as default_plot_settings,
    default_title_key,
    default_ylabel_key,
    draw_spectrum,
    reconcile_settings,
    restore_default_visibility,
)
from epr_workflow.preprocessing import (
    BASELINE_OPERATION,
    INPUT_CURRENT,
    INPUT_RAW,
    SAVGOL_OPERATION,
    BaselineWindow,
    LinearBaselineSpec,
    PreprocessingError,
    PreprocessingResult,
    PreprocessingSession,
    PreprocessingWarning,
    SavgolSpec,
)
from epr_workflow.processed_export import export_processed

STATUS_COLORS = {
    "success": "#1e7d32",
    "success_with_warnings": "#b26a00",
    "failed": "#c62828",
}

#: UI preference file (language only). Kept inside the project root so no
#: global/registry settings are touched.
SETTINGS_PATH = PROJECT_ROOT / "config" / "gui_settings.ini"
LANGUAGE_SETTING_KEY = "ui/language"

#: Matplotlib toolbar actions whose built-in English tooltips we translate.
TOOLBAR_TOOLTIP_KEYS = {
    "Home": "toolbar_home",
    "Back": "toolbar_back",
    "Forward": "toolbar_forward",
    "Pan": "toolbar_pan",
    "Zoom": "toolbar_zoom",
    "Subplots": "toolbar_subplots",
    "Customize": "toolbar_customize",
    "Save": "toolbar_save",
}

#: Stable plot-settings error codes -> translated GUI messages.
PLOT_ERROR_KEYS = {
    "plot_no_visible_curve": "plot_error_no_visible_curve",
    "plot_unavailable_curve": "plot_error_unavailable_curve",
    "plot_missing_curve": "plot_error_missing_curve",
    "plot_export_size": "plot_error_export_size",
    "plot_export_dpi": "plot_error_export_dpi",
    "plot_axis_range": "plot_error_axis_range",
    "plot_color": "plot_error_color",
}


def default_settings() -> QSettings | None:
    """Return QSettings backed by ``config/gui_settings.ini``.

    Returns ``None`` if the settings file cannot be created; the GUI then runs
    with the default language and simply does not persist the choice.
    """
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        return QSettings(str(SETTINGS_PATH), QSettings.Format.IniFormat)
    except OSError:
        return None


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self._settings = settings
        self._language = self._initial_language()

        # State
        self.output_base: Path = PROJECT_ROOT / "results"
        self._row_records: list[dict | None] = []  # aligned with the sample list
        self._row_paths: list[Path] = []  # source path per list row
        self._current_view: SpectrumView | None = None
        self._current_record: dict | None = None
        self._error_state: dict | None = None
        self._placeholder_key: str | None = None
        self._cursor_point: tuple[float, float] | None = None
        self._batch_batch: dict | None = None
        self._batch_summary_path: Path | None = None
        self._selected_outputs: dict = {}
        self._store = PreprocessingStore()
        self._session: PreprocessingSession | None = None
        self._preview_result: PreprocessingResult | None = None
        self._processed_outputs: dict[str, str] = {}
        self._plot_store = PlotSettingsStore()
        self._plot_settings: PlotSettings | None = None
        self._plot_source: Path | None = None
        self._plot_sha: str | None = None
        self._plot_output: Path | None = None
        self._plot_legend_default: bool | None = None

        self._build_ui()
        self._retranslate()

    # ------------------------------------------------------- language
    def _initial_language(self) -> str:
        if self._settings is None:
            return DEFAULT_LANGUAGE
        return normalize_language(self._settings.value(LANGUAGE_SETTING_KEY, DEFAULT_LANGUAGE))

    def _t(self, key: str, **fmt) -> str:
        """Translate ``key`` into the currently selected language."""
        return tr_text(key, self._language, **fmt)

    def _set_language(self, lang: str) -> None:
        """Switch the UI language without touching any loaded data."""
        new_language = normalize_language(lang)
        if new_language == self._language:
            return
        self._language = new_language
        index = self.language_combo.findData(new_language)
        if index >= 0 and self.language_combo.currentIndex() != index:
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(index)
            self.language_combo.blockSignals(False)
        self._save_language()
        self._retranslate()

    def _save_language(self) -> None:
        if self._settings is None:
            return
        self._settings.setValue(LANGUAGE_SETTING_KEY, self._language)
        self._settings.sync()

    def _on_language_selected(self, index: int) -> None:
        code = self.language_combo.itemData(index)
        if code:
            self._set_language(str(code))

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        root.addLayout(self._build_controls())

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self._build_sample_panel())
        splitter.addWidget(self._build_plot_panel())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 760])
        root.addWidget(splitter, stretch=1)

    def _build_controls(self) -> QVBoxLayout:
        controls = QVBoxLayout()

        row = QHBoxLayout()
        self.open_file_btn = QPushButton()
        self.open_file_btn.clicked.connect(self._choose_single_file)
        row.addWidget(self.open_file_btn)

        self.batch_btn = QPushButton()
        self.batch_btn.clicked.connect(self._choose_batch_dir)
        row.addWidget(self.batch_btn)

        self.output_btn = QPushButton()
        self.output_btn.clicked.connect(self._choose_output_dir)
        row.addWidget(self.output_btn)

        self.output_edit = QLineEdit(str(self.output_base))
        self.output_edit.setReadOnly(True)
        self.output_edit.setMinimumWidth(220)
        row.addWidget(self.output_edit, stretch=1)
        controls.addLayout(row)

        self.recursive_check = QCheckBox()
        self.overwrite_check = QCheckBox()

        # Language selector, top-right. Its label is intentionally bilingual
        # and never translated.
        options_row = QHBoxLayout()
        options_row.addWidget(self.recursive_check)
        options_row.addWidget(self.overwrite_check)
        options_row.addStretch(1)
        self.language_label = QLabel("语言 / Language")
        self.language_label.setToolTip("切换界面语言 / Switch interface language")
        options_row.addWidget(self.language_label)
        self.language_combo = QComboBox()
        for code, name in LANGUAGES.items():
            self.language_combo.addItem(name, code)
        selected = self.language_combo.findData(self._language)
        if selected >= 0:
            self.language_combo.setCurrentIndex(selected)
        self.language_combo.setToolTip("切换界面语言 / Switch interface language")
        self.language_combo.currentIndexChanged.connect(self._on_language_selected)
        options_row.addWidget(self.language_combo)
        controls.addLayout(options_row)
        return controls

    def _build_sample_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.sample_list_label = QLabel()
        layout.addWidget(self.sample_list_label)
        self.sample_list = QListWidget()
        self.sample_list.currentRowChanged.connect(self._on_sample_selected)
        layout.addWidget(self.sample_list, stretch=1)

        self.batch_summary_label = QLabel()
        self.batch_summary_label.setWordWrap(True)
        layout.addWidget(self.batch_summary_label)

        self.preprocessing_panel = PreprocessingPanel()
        self.preprocessing_panel.preview_requested.connect(
            self._on_preview_requested
        )
        self.preprocessing_panel.cancel_preview_requested.connect(
            self._on_cancel_preview_requested
        )
        self.preprocessing_panel.apply_requested.connect(self._on_apply_requested)
        self.preprocessing_panel.undo_requested.connect(self._on_undo_requested)
        self.preprocessing_panel.reset_requested.connect(self._on_reset_requested)
        self.preprocessing_panel.export_requested.connect(
            self._on_export_requested
        )
        self.preprocessing_panel.parameters_changed.connect(
            self._on_parameters_changed
        )

        preprocessing_tab = QWidget()
        preprocessing_layout = QVBoxLayout(preprocessing_tab)
        preprocessing_layout.setContentsMargins(0, 0, 0, 0)
        preprocessing_layout.addWidget(self.preprocessing_panel)
        preprocessing_layout.addStretch(1)

        self.plot_editor_panel = PlotEditorPanel()
        self.plot_editor_panel.settings_changed.connect(
            self._on_plot_settings_changed
        )
        self.plot_editor_panel.reset_requested.connect(
            self._on_plot_reset_requested
        )
        self.plot_editor_panel.restore_visibility_requested.connect(
            self._on_restore_visibility_requested
        )
        self.plot_editor_panel.export_requested.connect(
            self._on_plot_export_requested
        )
        plot_scroll = QScrollArea()
        plot_scroll.setWidgetResizable(True)
        plot_scroll.setWidget(self.plot_editor_panel)

        self.left_tabs = QTabWidget()
        self.left_tabs.addTab(preprocessing_tab, "")
        self.left_tabs.addTab(plot_scroll, "")
        layout.addWidget(self.left_tabs, stretch=2)
        return panel

    def _build_plot_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = MplCanvas(self)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas, stretch=1)

        self.cursor_label = QLabel()
        self.cursor_label.setMinimumHeight(20)
        layout.addWidget(self.cursor_label)

        open_row = QHBoxLayout()
        self.open_csv_btn = QPushButton()
        self.open_png_btn = QPushButton()
        self.open_json_btn = QPushButton()
        for button in (self.open_csv_btn, self.open_png_btn, self.open_json_btn):
            button.setEnabled(False)
            open_row.addWidget(button)
        open_row.addStretch(1)
        layout.addLayout(open_row)

        self.open_csv_btn.clicked.connect(lambda: self._open_output("csv"))
        self.open_png_btn.clicked.connect(lambda: self._open_output("figure"))
        self.open_json_btn.clicked.connect(lambda: self._open_output("metadata_json"))

        self.metadata_label = QLabel()
        layout.addWidget(self.metadata_label)
        self.metadata_text = QPlainTextEdit()
        self.metadata_text.setReadOnly(True)
        self.metadata_text.setMinimumHeight(160)
        layout.addWidget(self.metadata_text)

        self.canvas.mpl_connect("motion_notify_event", self._on_mouse_move)
        return panel

    # ------------------------------------------------------- translation
    def _retranslate(self) -> None:
        """Apply the current language to every visible widget.

        Widgets are updated in place; loaded data, batch results, the selected
        sample, and the cursor readout are re-rendered from cached state only.
        """
        self.setWindowTitle(self._t("window_title"))

        self.open_file_btn.setText(self._t("open_dataset"))
        self.batch_btn.setText(self._t("batch_process"))
        self.output_btn.setText(self._t("output_directory"))
        self.recursive_check.setText(self._t("recursive_subdirs"))
        self.overwrite_check.setText(self._t("allow_overwrite"))

        self.sample_list_label.setText(self._t("sample_list"))
        self.metadata_label.setText(self._t("metadata_section"))

        self.open_csv_btn.setText(self._t("open_csv"))
        self.open_png_btn.setText(self._t("open_png"))
        self.open_json_btn.setText(self._t("open_json"))
        self.open_csv_btn.setToolTip(self._t("tip_open_csv"))
        self.open_png_btn.setToolTip(self._t("tip_open_png"))
        self.open_json_btn.setToolTip(self._t("tip_open_json"))
        self.preprocessing_panel.set_texts(
            {key: self._t(key) for key in TEXT_KEYS}
        )
        self.left_tabs.setTabText(0, self._t("plot_tab_preprocessing"))
        self.left_tabs.setTabText(1, self._t("plot_tab_plot"))
        self.plot_editor_panel.set_texts(
            {key: self._t(key) for key in PLOT_EDITOR_TEXT_KEYS}
        )
        self._retranslate_toolbar()

        self._render_sample_list()
        self._render_batch_summary()
        if self._current_view is not None:
            self._render_plot()
            self._update_plot_editor()
        else:
            self.plot_editor_panel.clear()
        self._render_metadata()
        self._render_cursor()
        self._update_preprocessing_panel()
        self._update_plot_editor_actions()

    def _retranslate_toolbar(self) -> None:
        """Translate the matplotlib toolbar tooltips (zoom, pan, save, ...)."""
        for action in self.toolbar.actions():
            key = TOOLBAR_TOOLTIP_KEYS.get(action.text())
            if key:
                action.setToolTip(self._t(key))

    def _render_sample_list(self) -> None:
        for row, source in enumerate(self._row_paths):
            item = self.sample_list.item(row)
            if item is None:
                continue
            record = self._row_records[row] if row < len(self._row_records) else None
            item.setText(self._sample_item_text(record, source))

    def _sample_item_text(self, record: dict | None, source: Path) -> str:
        if record is None:
            return source.name
        return f"{status_text(record.get('status', ''), self._language)}  {source.name}"

    def _render_batch_summary(self) -> None:
        if self._batch_batch is None:
            self.batch_summary_label.setText(self._t("batch_not_run"))
            return
        batch = self._batch_batch
        lines = [
            self._t(
                "batch_counts",
                discovered=batch.get("files_discovered", 0),
                succeeded=batch.get("files_succeeded", 0),
                warnings=batch.get("files_succeeded_with_warnings", 0),
                failed=batch.get("files_failed", 0),
            ),
            self._t(
                "batch_overall",
                status=overall_status_text(
                    batch.get("overall_status", ""), self._language
                ),
            ),
        ]
        if self._batch_summary_path is not None:
            lines.append(self._t("batch_summary_path", path=self._batch_summary_path))
        self.batch_summary_label.setText("\n".join(lines))

    def _render_cursor(self) -> None:
        result = self._active_result()
        if result is not None and result.is_preview:
            key = "cursor_value_preview"
        elif result is not None and result.has_smoothing:
            only_smoothing = set(result.operations) == {SAVGOL_OPERATION}
            key = (
                "cursor_value_smoothed"
                if only_smoothing
                else "cursor_value_processed"
            )
        elif result is not None:
            key = "cursor_value_corrected"
        else:
            key = "cursor_value"
        if self._cursor_point is None:
            self.cursor_label.setText(self._t("cursor_idle"))
        else:
            field, intensity = self._cursor_point
            self.cursor_label.setText(
                self._t(key, field=field, intensity=intensity)
            )

    def _active_result(self) -> PreprocessingResult | None:
        if self._preview_result is not None:
            return self._preview_result
        if self._session is not None and self._session.has_steps:
            return self._session.current_result()
        return None

    def _raw_outputs(self) -> dict:
        return (self._current_record or {}).get("outputs", {})

    def _render_metadata(self) -> None:
        view = self._current_view
        if view is None:
            if self._error_state is not None:
                state = dict(self._error_state)
                code = state.get("code")
                if isinstance(code, str):
                    key = f"bes3t_error_{code}"
                    if has_text(key, self._language):
                        state["error"] = self._t(
                            key, **state.get("context", {})
                        )
                self.metadata_text.setPlainText(
                    self._t("metadata_read_error", **state)
                )
            elif self._placeholder_key is not None:
                self.metadata_text.setPlainText(self._t(self._placeholder_key))
            return

        lines = [
            self._t("meta_file", path=view.source),
            self._t("meta_format", format=view.source_format),
            self._t("meta_points", n=view.n_points),
            self._t("meta_field_range", low=view.field_min, high=view.field_max),
            self._t(
                "meta_field_direction",
                order=field_order_text(view.field_order, self._language),
            ),
            self._t(
                "meta_signal",
                smin=view.signal_min,
                smax=view.signal_max,
                mean=view.signal_mean,
                std=view.signal_std,
            ),
            "",
        ]
        result = view.import_result
        if result is not None and result.source_format == "BES3T":
            source_files = result.source_files
            lines.insert(
                2,
                self._t(
                    "meta_source_files",
                    descriptor=Path(
                        source_files.get("descriptor", str(view.source))
                    ).name,
                    data=Path(
                        source_files.get("data", "?")
                    ).name,
                ),
            )
            axis = result.format_metadata.get("axis", {})
            binary = result.format_metadata.get("binary", {})
            if axis:
                lines.insert(
                    4,
                    self._t(
                        "meta_bes3t_axis",
                        axis_type=axis.get("type", "?"),
                        xmin=axis.get("XMIN", float("nan")),
                        xwid=axis.get("XWID", float("nan")),
                        unit=axis.get("unit", "?"),
                    ),
                )
            if binary:
                lines.insert(
                    5,
                    self._t(
                        "meta_bes3t_data",
                        ikkf=binary.get("IKKF", "?"),
                        irfmt=binary.get("IRFMT", "?"),
                        dtype=binary.get("numpy_dtype", "?"),
                        byte_order=binary.get("byte_order", "?"),
                        points=result.format_metadata.get("axis", {}).get(
                            "points", view.n_points
                        ),
                    ),
                )
        if view.warnings:
            lines.append(self._t("meta_warnings"))
            lines.append(self._t("meta_warnings_note"))
            lines.extend(f"  • {warning}" for warning in view.warnings)
        else:
            lines.append(self._t("meta_warnings_none"))

        result = self._active_result()
        if result is not None:
            lines.extend(self._preprocessing_metadata_lines(result))
        self.metadata_text.setPlainText("\n".join(lines))

    def _preprocessing_metadata_lines(
        self, result: PreprocessingResult
    ) -> list[str]:
        if result.is_preview:
            mode = self._t("meta_prep_mode_preview")
        elif self._processed_outputs:
            mode = self._t(
                "meta_prep_mode_exported", n=len(result.steps)
            )
        else:
            mode = self._t("meta_prep_mode_applied", n=len(result.steps))

        order = " → ".join(
            self._operation_text(operation) for operation in result.operations
        )
        lines = [
            "",
            self._t("meta_prep_header"),
            mode,
            self._t("meta_prep_order", order=order),
        ]
        for index, step in enumerate(result.steps, start=1):
            effective_code = INPUT_RAW if index == 1 else INPUT_CURRENT
            effective_source = self._t(
                "meta_input_raw"
                if effective_code == INPUT_RAW
                else "meta_input_current"
            )
            effective_count = 0 if index == 1 else index - 1
            stored_source = self._t(
                "meta_input_raw"
                if step.input_source == INPUT_RAW
                else "meta_input_current"
            )
            if (
                step.operation == SAVGOL_OPERATION
                and step.smoothing is not None
            ):
                lines.append(
                    self._t("meta_prep_savgol_step", index=index)
                )
                lines.append(
                    "  "
                    + self._t(
                        "meta_prep_savgol_params",
                        window_length=step.spec.window_length,
                        polyorder=step.spec.polyorder,
                    )
                )
                lines.append(
                    "  "
                    + self._t(
                        "meta_prep_savgol_input",
                        source=effective_source,
                        count=effective_count,
                    )
                )
                if step.input_source != effective_code:
                    lines.append(
                        "  "
                        + self._t(
                            "meta_prep_fit_input_note", source=stored_source
                        )
                    )
                lines.append(
                    "  "
                    + self._t(
                        "meta_prep_savgol_change",
                        rms=step.smoothing.rms_change,
                        max_change=step.smoothing.max_abs_change,
                    )
                )
            elif step.operation == BASELINE_OPERATION and step.fit is not None:
                fit = step.fit
                r2 = (
                    self._t("meta_prep_r2_none")
                    if fit.r_squared is None
                    else f"{fit.r_squared:.6g}"
                )
                lines.append(self._t("meta_prep_step", index=index))
                lines.append(
                    "  "
                    + self._t(
                        "meta_prep_input",
                        source=effective_source,
                        count=effective_count,
                    )
                )
                if step.input_source != effective_code:
                    lines.append(
                        "  "
                        + self._t(
                            "meta_prep_fit_input_note", source=stored_source
                        )
                    )
                lines.append(
                    "  "
                    + self._t(
                        "meta_prep_windows",
                        left_start=step.spec.window_left.start,
                        left_end=step.spec.window_left.end,
                        right_start=step.spec.window_right.start,
                        right_end=step.spec.window_right.end,
                    )
                )
                lines.append(
                    "  "
                    + self._t(
                        "meta_prep_points",
                        left=fit.n_points_left,
                        right=fit.n_points_right,
                    )
                )
                lines.append(
                    "  "
                    + self._t(
                        "meta_prep_fit",
                        slope=fit.slope,
                        intercept=fit.intercept,
                        r2=r2,
                    )
                )
                lines.append(
                    "  "
                    + self._t(
                        "meta_prep_rms",
                        rms=fit.rms_residual,
                        left=fit.residual_rms_left,
                        right=fit.residual_rms_right,
                    )
                )
                lines.append(
                    "  "
                    + self._t(
                        "meta_prep_extrapolation",
                        left=fit.extrapolation_left_G,
                        right=fit.extrapolation_right_G,
                    )
                )
            if step.warnings:
                lines.append("  " + self._t("meta_prep_warnings"))
                lines.extend(
                    "    • " + self._warning_text(warning)
                    for warning in step.warnings
                )
        if BASELINE_OPERATION in result.operations:
            lines.append(self._t("meta_prep_caution"))
        if SAVGOL_OPERATION in result.operations:
            lines.append(self._t("meta_prep_savgol_caution"))
        lines.append(self._t("meta_prep_raw_note"))
        if self._processed_outputs.get("csv"):
            lines.append(
                self._t(
                    "meta_prep_exported_path", path=self._processed_outputs["csv"]
                )
            )
        return lines

    def _operation_text(self, operation: str) -> str:
        if operation == BASELINE_OPERATION:
            return self._t("meta_operation_baseline")
        if operation == SAVGOL_OPERATION:
            return self._t("meta_operation_savgol")
        return operation

    def _warning_text(self, warning: PreprocessingWarning) -> str:
        if has_text(warning.code, self._language):
            return self._t(warning.code, **warning.context)
        return warning.message

    def _describe_preprocessing_error(self, exc: PreprocessingError) -> str:
        key = f"prep_error_{exc.code}"
        if has_text(key, self._language):
            return self._t(key, **exc.context)
        return f"{type(exc).__name__}: {exc}"

    def _describe_import_error(self, exc: Exception) -> str:
        """Translate coded BES3T errors; preserve ASC diagnostics verbatim."""
        code = getattr(exc, "code", None)
        if isinstance(code, str):
            key = f"bes3t_error_{code}"
            if has_text(key, self._language):
                return self._t(key, **getattr(exc, "context", {}))
        return str(exc)

    def _record_error_text(self, record: dict) -> str:
        code = record.get("error_code")
        if isinstance(code, str):
            key = f"bes3t_error_{code}"
            if has_text(key, self._language):
                return self._t(key, **record.get("error_context", {}))
        return str(record.get("error") or "")

    # ----------------------------------------------------------- handlers
    def _choose_single_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t("dialog_select_dataset"),
            str(PROJECT_ROOT / "data" / "raw"),
            self._t("dataset_filter"),
        )
        if not path:
            return
        self._load_and_display(Path(path))

    def _choose_batch_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            self._t("dialog_select_batch_dir"),
            str(PROJECT_ROOT / "data" / "raw"),
        )
        if not directory:
            return
        self._run_batch(Path(directory))

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, self._t("dialog_select_output_dir"), str(self.output_base)
        )
        if directory:
            self.output_base = Path(directory)
            self.output_edit.setText(str(self.output_base))

    def _run_batch(self, input_dir: Path) -> None:
        try:
            outcome = run_batch_processing(
                input_dir,
                self.output_base,
                recursive=self.recursive_check.isChecked(),
                overwrite=self.overwrite_check.isChecked(),
            )
        except FileExistsError as exc:
            QMessageBox.warning(
                self,
                self._t("title_outputs_exist"),
                self._t("msg_outputs_exist", error=exc),
            )
            return
        except OSError as exc:
            QMessageBox.critical(
                self,
                self._t("title_write_failed"),
                self._t("msg_write_failed", error=exc),
            )
            return

        self._populate_samples(outcome)

    def _populate_samples(self, outcome: BatchOutcome) -> None:
        records = outcome.summary.get("files", [])
        self._row_records = []
        self._row_paths = []
        self.sample_list.blockSignals(True)
        self.sample_list.clear()
        for record in records:
            source = Path(record["source_path"])
            self._row_records.append(record)
            self._row_paths.append(source)
            item = QListWidgetItem(self._sample_item_text(record, source))
            item.setForeground(QColor(STATUS_COLORS.get(record["status"], "#000000")))
            if record.get("error"):
                item.setToolTip(self._record_error_text(record))
            self.sample_list.addItem(item)
        self.sample_list.blockSignals(False)

        self._batch_batch = dict(outcome.summary["batch"])
        self._batch_summary_path = Path(outcome.summary_path)
        self._render_batch_summary()

        if records:
            self.sample_list.setCurrentRow(0)
        else:
            self._clear_plot()
            self._placeholder_key = "no_samples"
            self._render_metadata()

    def _on_sample_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._row_paths):
            return
        source = self._row_paths[row]
        record = self._row_records[row] if self._row_records else None
        self._load_and_display(source, record=record)

    def _load_and_display(self, path: Path, record: dict | None = None) -> None:
        try:
            view = load_spectrum(path)
        except Exception as exc:  # surface a clear, non-crashing message
            self._clear_plot()
            error_text = self._describe_import_error(exc)
            self._error_state = {
                "path": path,
                "type": type(exc).__name__,
                "error": str(exc),
                "code": getattr(exc, "code", None),
                "context": dict(getattr(exc, "context", {})),
            }
            self._render_metadata()
            QMessageBox.warning(
                self,
                self._t("title_read_failed"),
                self._t(
                    "msg_read_failed",
                    name=path.name,
                    type=type(exc).__name__,
                    error=error_text,
                ),
            )
            return
        self._display(view, record=record)

    def _display(self, view: SpectrumView, record: dict | None = None) -> None:
        self._current_view = view
        self._current_record = record
        self._error_state = None
        self._placeholder_key = None
        self._preview_result = None
        self._processed_outputs = {}
        self._plot_settings = None
        self._plot_source = view.source.resolve()
        self._plot_sha = view.sha256
        self._plot_output = None
        self._plot_legend_default = None
        try:
            self._session = self._store.session_for(view)
        except PreprocessingError:
            # The importer already refuses non-monotonic axes by default; this
            # is a defensive fallback for programmatically built views.
            self._session = None
        self.preprocessing_panel.set_enabled(self._session is not None)
        if self._session is not None:
            self.preprocessing_panel.set_field_range(
                view.field_min, view.field_max, view.n_points
            )
            if self._session.has_steps:
                last_step = self._session.steps[-1]
                if last_step.operation == BASELINE_OPERATION and isinstance(
                    last_step.spec, LinearBaselineSpec
                ):
                    self.preprocessing_panel.set_operation(BASELINE_OPERATION)
                    self.preprocessing_panel.set_values(
                        last_step.spec.window_left.start,
                        last_step.spec.window_left.end,
                        last_step.spec.window_right.start,
                        last_step.spec.window_right.end,
                    )
                elif last_step.operation == SAVGOL_OPERATION and isinstance(
                    last_step.spec, SavgolSpec
                ):
                    self.preprocessing_panel.set_operation(SAVGOL_OPERATION)
                    self.preprocessing_panel.set_savgol_values(
                        last_step.spec.window_length, last_step.spec.polyorder
                    )
                    self.preprocessing_panel.set_smoothing_input_source(
                        last_step.input_source
                    )
        self._set_open_buttons(self._raw_outputs())
        self._refresh_display()

    def _refresh_display(self, *, clear_cursor: bool = True) -> None:
        if clear_cursor:
            self._cursor_point = None
        self._plot_output = None
        self._render_plot()
        self._update_plot_editor()
        self._render_metadata()
        self._render_cursor()
        self._update_preprocessing_panel()
        self._update_plot_editor_actions()

    # ----------------------------------------------------------- plot
    def _sync_plot_settings(self) -> PlotSettings | None:
        """Load/reconcile display settings for the selected sample only."""
        view = self._current_view
        if view is None:
            return None
        result = self._active_result()
        source = view.source.resolve()
        defaults = default_plot_settings(result)
        if (
            self._plot_settings is None
            or self._plot_source != source
            or self._plot_sha != view.sha256
        ):
            self._plot_settings = self._plot_store.settings_for(
                view.source, view.sha256, result
            )
            self._plot_source = source
            self._plot_sha = view.sha256
        else:
            # The processed default shows a legend; the raw default does not.
            # Only follow the changing default when the user has not made an
            # explicit choice that differs from the previous default.
            if (
                self._plot_legend_default is not None
                and self._plot_settings.axis.legend_visible
                == self._plot_legend_default
            ):
                self._plot_settings.axis.legend_visible = (
                    defaults.axis.legend_visible
                )
            self._plot_settings = reconcile_settings(
                self._plot_settings, defaults
            )
            self._plot_store.update(
                view.source, view.sha256, self._plot_settings
            )
        self._plot_legend_default = defaults.axis.legend_visible
        return self._plot_settings

    def _plot_curve_labels(
        self, result: PreprocessingResult | None
    ) -> dict[str, str]:
        return {
            key: self._t(default_curve_label_key(key, result))
            for key in CURVE_KEYS
        }

    def _resolved_plot_settings(
        self,
        settings: PlotSettings,
        view: SpectrumView,
        result: PreprocessingResult | None,
    ) -> PlotSettings:
        """Fill auto title/labels with the current language's defaults."""
        resolved = settings.copy()
        if resolved.axis.title is None:
            resolved.axis.title = self._t(
                default_title_key(result), sample=view.source.stem
            )
        if resolved.axis.xlabel is None:
            resolved.axis.xlabel = self._t("plot_xlabel")
        if resolved.axis.ylabel is None:
            resolved.axis.ylabel = self._t(default_ylabel_key(result))
        return resolved

    def _build_plot_curves(
        self, settings: PlotSettings
    ) -> tuple[list, PlotSettings, PreprocessingResult | None] | None:
        view = self._current_view
        if view is None:
            return None
        result = self._active_result()
        curves = build_curves(
            view.data["field_G"].to_numpy(),
            view.data["intensity"].to_numpy(),
            result,
            settings,
            self._plot_curve_labels(result),
        )
        resolved = self._resolved_plot_settings(settings, view, result)
        return curves, resolved, result

    def _render_plot(self) -> None:
        view = self._current_view
        if view is None:
            return
        settings = self._sync_plot_settings()
        if settings is None:
            return
        built = self._build_plot_curves(settings)
        if built is None:
            return
        curves, resolved, _result = built
        # The same renderer is used for the PNG export, so the saved figure
        # cannot silently differ from the live preview.
        draw_spectrum(
            self.canvas.axes,
            curves,
            resolved,
            cjk_font=self.canvas.cjk_font,
        )
        self.canvas.draw()

    def _update_plot_editor(self) -> None:
        view = self._current_view
        if view is None:
            self.plot_editor_panel.clear()
            return
        settings = self._sync_plot_settings()
        if settings is None:
            self.plot_editor_panel.clear()
            return
        result = self._active_result()
        built = self._build_plot_curves(settings)
        if built is None:
            self.plot_editor_panel.clear()
            return
        curves, _resolved, _result = built
        data_xlim, data_ylim = curve_data_ranges(curves, visible_only=False)
        self.plot_editor_panel.set_context(
            settings,
            available_curve_keys(result),
            self._plot_curve_labels(result),
            default_title=self._t(
                default_title_key(result), sample=view.source.stem
            ),
            default_xlabel=self._t("plot_xlabel"),
            default_ylabel=self._t(default_ylabel_key(result)),
            data_xlim=data_xlim,
            data_ylim=data_ylim,
        )
        self.plot_editor_panel.set_status_text(self._plot_status_text())

    def _plot_status_text(self) -> str:
        if self._preview_result is not None:
            return self._t("plot_status_preview")
        if self._plot_output is not None:
            return self._t("plot_status_exported", path=self._plot_output)
        return ""

    def _update_plot_editor_actions(self) -> None:
        enabled = (
            self._current_view is not None
            and self._plot_settings is not None
            and self._preview_result is None
        )
        self.plot_editor_panel.set_export_enabled(enabled)

    def _set_open_buttons(self, outputs: dict | None) -> None:
        outputs = outputs or {}
        self.open_csv_btn.setEnabled(bool(outputs.get("csv")))
        self.open_png_btn.setEnabled(bool(outputs.get("figure")))
        self.open_json_btn.setEnabled(bool(outputs.get("metadata_json")))
        self._selected_outputs = outputs

    # ----------------------------------------------------- preprocessing
    def _panel_spec(self) -> LinearBaselineSpec:
        if not self.preprocessing_panel.has_selection():
            raise PreprocessingError(
                "Select both baseline windows before previewing or applying.",
                code="windows_unset",
            )
        left_start, left_end, right_start, right_end = (
            self.preprocessing_panel.values()
        )
        if None in (left_start, left_end, right_start, right_end):
            raise PreprocessingError(
                "Select both baseline windows before previewing or applying.",
                code="windows_unset",
            )
        return LinearBaselineSpec(
            window_left=BaselineWindow(float(left_start), float(left_end)),
            window_right=BaselineWindow(float(right_start), float(right_end)),
        )

    def _show_preprocessing_error(
        self, exc: PreprocessingError, title_key: str
    ) -> None:
        QMessageBox.warning(
            self, self._t(title_key), self._describe_preprocessing_error(exc)
        )

    def _on_preview_requested(self) -> None:
        if self._session is None:
            return
        try:
            if (
                self.preprocessing_panel.selected_operation()
                == SAVGOL_OPERATION
            ):
                result = self._session.preview_savgol(
                    SavgolSpec(*self.preprocessing_panel.savgol_values()),
                    input_source=self.preprocessing_panel.smoothing_input_source(),
                )
            else:
                result = self._session.preview(self._panel_spec())
        except PreprocessingError as exc:
            self._show_preprocessing_error(exc, "title_preprocessing_invalid")
            return
        self._preview_result = result
        self._processed_outputs = {}
        self._set_open_buttons(self._raw_outputs())
        self._refresh_display()

    def _on_cancel_preview_requested(self) -> None:
        if self._session is not None:
            self._session.discard_preview()
        if self._preview_result is None:
            return
        self._preview_result = None
        self._set_open_buttons(self._raw_outputs())
        self._refresh_display()

    def _on_apply_requested(self) -> None:
        if self._session is None:
            return
        try:
            if self._preview_result is not None:
                self._session.apply_pending()
            elif (
                self.preprocessing_panel.selected_operation()
                == SAVGOL_OPERATION
            ):
                self._session.apply_savgol(
                    SavgolSpec(*self.preprocessing_panel.savgol_values()),
                    input_source=self.preprocessing_panel.smoothing_input_source(),
                )
            else:
                self._session.apply(self._panel_spec())
        except PreprocessingError as exc:
            self._show_preprocessing_error(exc, "title_preprocessing_invalid")
            return
        self._preview_result = None
        self._processed_outputs = {}
        self._set_open_buttons(self._raw_outputs())
        self._refresh_display()

    def _on_undo_requested(self) -> None:
        if self._session is None:
            return
        self._session.undo()
        self._preview_result = None
        self._processed_outputs = {}
        self._set_open_buttons(self._raw_outputs())
        self._refresh_display()

    def _on_reset_requested(self) -> None:
        if self._session is None:
            return
        self._session.reset()
        self._preview_result = None
        self._processed_outputs = {}
        self._set_open_buttons(self._raw_outputs())
        self._refresh_display()

    def _on_parameters_changed(self) -> None:
        if self._session is not None:
            self._session.discard_preview()
        if self._preview_result is not None:
            self._preview_result = None
            self._set_open_buttons(self._raw_outputs())
            self._refresh_display()

    # ------------------------------------------------------- plot editor
    def _on_plot_settings_changed(self) -> None:
        view = self._current_view
        settings = self.plot_editor_panel.settings()
        if view is None or settings is None:
            return
        self._plot_settings = settings
        self._plot_store.update(view.source, view.sha256, settings)
        self._plot_output = None
        self._render_plot()
        self._update_plot_editor_actions()
        self.plot_editor_panel.set_status_text(self._plot_status_text())

    def _on_plot_reset_requested(self) -> None:
        view = self._current_view
        if view is None:
            return
        self._plot_settings = default_plot_settings(self._active_result())
        self._plot_store.update(
            view.source, view.sha256, self._plot_settings
        )
        self._plot_output = None
        self._render_plot()
        self._update_plot_editor()
        self._update_plot_editor_actions()

    def _on_restore_visibility_requested(self) -> None:
        view = self._current_view
        settings = self._sync_plot_settings()
        if view is None or settings is None:
            return
        settings = restore_default_visibility(
            settings, default_plot_settings(self._active_result())
        )
        self._plot_settings = settings
        self._plot_store.update(view.source, view.sha256, settings)
        self._plot_output = None
        self._render_plot()
        self._update_plot_editor()
        self._update_plot_editor_actions()

    def _on_plot_export_requested(self) -> None:
        view = self._current_view
        if view is None:
            return
        if self._preview_result is not None:
            QMessageBox.warning(
                self,
                self._t("title_plot_export_unavailable"),
                self._t("msg_plot_export_preview"),
            )
            return
        settings = self._sync_plot_settings()
        if settings is None:
            return
        dialog = PlotExportDialog(
            self,
            texts={key: self._t(key) for key in PLOT_EXPORT_TEXT_KEYS},
            default_path=default_plot_path(
                view.source.stem, self.output_base
            ),
            options=PlotExportSettings(),
            overwrite=False,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._export_plot_to(
            dialog.output_path(),
            dialog.export_settings(),
            overwrite=dialog.overwrite(),
        )

    def _export_plot_to(
        self,
        output_path: str | Path,
        export_settings: PlotExportSettings | None,
        *,
        overwrite: bool = False,
    ) -> Path | None:
        """Render the current plot to PNG; return the path only on success."""
        view = self._current_view
        settings = self._sync_plot_settings()
        if view is None or settings is None:
            return None
        built = self._build_plot_curves(settings)
        if built is None:
            return None
        curves, resolved, result = built
        try:
            target = export_plot_png(
                curves=curves,
                settings=resolved,
                available_keys=available_curve_keys(result),
                output_path=output_path,
                export_settings=export_settings,
                source_path=view.source,
                source_paths=list(view.source_files.values()),
                overwrite=overwrite,
                cjk_font=self.canvas.cjk_font,
            )
        except FileExistsError as exc:
            QMessageBox.warning(
                self,
                self._t("title_outputs_exist"),
                self._t("msg_outputs_exist", error=exc),
            )
            return None
        except PlotSettingsError as exc:
            QMessageBox.warning(
                self,
                self._t("title_plot_export_failed"),
                self._describe_plot_error(exc),
            )
            return None
        except (OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                self._t("title_plot_export_failed"),
                self._t(
                    "msg_error_detail",
                    type=type(exc).__name__,
                    error=exc,
                ),
            )
            return None
        self._plot_output = target
        self._plot_store.update(view.source, view.sha256, settings)
        self.plot_editor_panel.set_status_text(self._plot_status_text())
        return target

    def _describe_plot_error(self, exc: PlotSettingsError) -> str:
        key = PLOT_ERROR_KEYS.get(exc.code)
        if key is not None and has_text(key, self._language):
            return self._t(key)
        return f"{type(exc).__name__}: {exc}"

    def _on_export_requested(self) -> None:
        if (
            self._session is None
            or not self._session.has_steps
            or self._preview_result is not None
        ):
            return
        view = self._current_view
        if view is None or view.import_result is None:
            QMessageBox.warning(
                self,
                self._t("title_export_failed"),
                self._t("prep_error_data_mismatch"),
            )
            return
        try:
            outputs = export_processed(
                import_result=view.import_result,
                result=self._session.current_result(),
                output_base=self.output_base,
                overwrite=self.overwrite_check.isChecked(),
            )
        except FileExistsError as exc:
            QMessageBox.warning(
                self,
                self._t("title_outputs_exist"),
                self._t("msg_outputs_exist", error=exc),
            )
            return
        except PreprocessingError as exc:
            QMessageBox.warning(
                self,
                self._t("title_export_failed"),
                self._describe_preprocessing_error(exc),
            )
            return
        except (OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                self._t("title_export_failed"),
                self._t(
                    "msg_error_detail",
                    type=type(exc).__name__,
                    error=exc,
                ),
            )
            return
        self._processed_outputs = {
            key: str(path) for key, path in outputs.items()
        }
        self._set_open_buttons(self._processed_outputs)
        self._refresh_display()

    def _update_preprocessing_panel(self) -> None:
        session = self._session
        data_loaded = session is not None and self._current_view is not None
        self.preprocessing_panel.set_enabled(data_loaded)
        if not data_loaded:
            self.preprocessing_panel.set_status_text(self._t("prep_status_raw"))
            self.preprocessing_panel.set_action_states(
                preview=False,
                cancel=False,
                apply=False,
                undo=False,
                reset=False,
                export=False,
            )
            return
        steps = len(session.steps)
        preview = self._preview_result is not None
        if preview:
            status = self._t("prep_status_preview")
        elif steps and self._processed_outputs:
            status = self._t("prep_status_exported", n=steps)
        elif steps:
            status = self._t("prep_status_applied", n=steps)
        else:
            status = self._t("prep_status_raw")
        self.preprocessing_panel.set_status_text(status)
        self.preprocessing_panel.set_action_states(
            preview=True,
            cancel=preview,
            apply=True,
            undo=steps > 0,
            reset=steps > 0,
            export=steps > 0 and not preview,
        )

    def _open_output(self, kind: str) -> None:
        path = self._selected_outputs.get(kind)
        if not path:
            return
        try:
            open_path(path)
        except FileNotFoundError as exc:
            QMessageBox.warning(self, self._t("title_file_missing"), str(exc))

    def _on_mouse_move(self, event) -> None:
        if event.inaxes and event.xdata is not None and event.ydata is not None:
            self._cursor_point = (float(event.xdata), float(event.ydata))
        else:
            self._cursor_point = None
        self._render_cursor()

    def _clear_plot(self) -> None:
        self._current_view = None
        self._current_record = None
        self._error_state = None
        self._placeholder_key = None
        self._cursor_point = None
        self._session = None
        self._preview_result = None
        self._processed_outputs = {}
        self._plot_settings = None
        self._plot_source = None
        self._plot_sha = None
        self._plot_output = None
        self._plot_legend_default = None
        self.canvas.axes.clear()
        self.canvas.draw()
        self.metadata_text.setPlainText("")
        self._render_cursor()
        self._set_open_buttons(None)
        self.plot_editor_panel.clear()
        self.preprocessing_panel.set_enabled(False)
        self.preprocessing_panel.set_status_text(self._t("prep_status_raw"))
        self.preprocessing_panel.set_action_states(
            preview=False,
            cancel=False,
            apply=False,
            undo=False,
            reset=False,
            export=False,
        )
