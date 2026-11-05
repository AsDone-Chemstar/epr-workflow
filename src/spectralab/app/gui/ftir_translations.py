"""FTIR GUI translation catalog and file metadata (Qt-free)."""

from __future__ import annotations

from spectralab.app.gui.i18n import Translator
from spectralab.techniques.ftir.formats import file_patterns

FTIR_TECHNIQUE_ID = "ftir"
FTIR_DISPLAY_NAME_KEY = "technique.ftir.name"
FTIR_FILE_PATTERNS = file_patterns()

FTIR_TRANSLATIONS = {
    "zh": {
        "technique.ftir.name": "FTIR（CSV / TXT / DPT）",
        "ftir.file_label": "文件",
        "ftir.file": "文件：{name}",
        "ftir.file_none": "尚未加载 FTIR 光谱。",
        "ftir.import_options": "使用选项导入 FTIR 文件…",
        "ftir.import_dialog_title": "FTIR 导入选项",
        "ftir.choose_file_title": "选择 FTIR 光谱文件",
        "ftir.columns_group": "列与文本解析",
        "ftir.metadata_group": "FTIR 元数据（显式输入）",
        "ftir.plot_group": "原始 FTIR 光谱",
        "ftir.x_column": "X 列",
        "ftir.y_column": "Y 列",
        "ftir.x_column_hint": "索引或表头名称；两列文件可留空",
        "ftir.y_column_hint": "索引或表头名称；两列文件可留空",
        "ftir.header": "首行是表头",
        "ftir.delimiter": "分隔符",
        "ftir.delimiter_auto": "自动（按文件后缀）",
        "ftir.delimiter_comma": "逗号",
        "ftir.delimiter_tab": "Tab",
        "ftir.delimiter_semicolon": "分号",
        "ftir.delimiter_whitespace": "空白字符",
        "ftir.delimiter_custom": "自定义…",
        "ftir.custom_delimiter": "自定义分隔符",
        "ftir.custom_delimiter_placeholder": "单个字符",
        "ftir.decimal": "小数分隔符",
        "ftir.decimal_dot": "点（.）",
        "ftir.decimal_comma": "逗号（,）",
        "ftir.comment": "注释标记",
        "ftir.comment_hint": "例如 # ；多个标记用空格分隔",
        "ftir.encoding": "文本编码",
        "ftir.skip_rows": "跳过开头行数",
        "ftir.x_name": "X 轴名称（可选）",
        "ftir.y_name": "Y 轴名称（可选）",
        "ftir.x_quantity": "X 轴物理量",
        "ftir.x_unit": "X 轴单位",
        "ftir.y_semantics": "Y 信号语义",
        "ftir.y_unit": "Y 信号单位（可选）",
        "ftir.acquisition_mode": "采集模式",
        "ftir.atr_status": "ATR 校正状态",
        "ftir.instrument_vendor": "仪器厂商（可选）",
        "ftir.instrument_model": "仪器型号（可选）",
        "ftir.quantity_unknown": "未知",
        "ftir.quantity_wavenumber": "波数",
        "ftir.unit_unknown": "未知",
        "ftir.unit_cm_inverse": "cm^-1",
        "ftir.semantics_unknown": "未知",
        "ftir.semantics_absorbance": "吸光度",
        "ftir.semantics_transmittance": "透过率",
        "ftir.acq_unknown": "未知（Unknown）",
        "ftir.acq_atr": "ATR",
        "ftir.acq_transmission": "透射（Transmission）",
        "ftir.atr_unknown": "未知（unknown）",
        "ftir.atr_applied": "已应用（applied）",
        "ftir.atr_not_applied": "未应用（not_applied）",
        "ftir.atr_not_applicable": "不适用（not_applicable）",
        "ftir.raw_group": "仅原始数据",
        "ftir.raw_label": "原始",
        "ftir.processed_label": "归一化",
        "ftir.baseline_processed_label": "基线校正",
        "ftir.preview_label": "预览（未应用）",
        "ftir.raw_note": (
            "原始数据保持只读；只有显式应用处理后才显示处理后曲线；"
            "不会自动平滑、基线、归一化或 ATR 校正。"
        ),
        "ftir.tab_import_options": "导入选项",
        "ftir.tab_peak_picking": "峰值检测",
        "ftir.peak_source": "检测来源",
        "ftir.peak_source_raw": "原始谱",
        "ftir.peak_source_processed": "当前处理谱",
        "ftir.peak_polarity": "峰极性",
        "ftir.peak_positive": "正向峰",
        "ftir.peak_negative": "负向峰",
        "ftir.peak_both": "正负峰",
        "ftir.peak_height": "高度阈值（取向信号单位；负峰为幅值）",
        "ftir.peak_prominence": "显著度阈值（信号单位）",
        "ftir.peak_distance": "最小距离（采样点）",
        "ftir.peak_min_width": "最小宽度（采样点）",
        "ftir.peak_blank_none": "留空 = 无",
        "ftir.peak_samples_suffix": " 点",
        "ftir.peak_preview": "预览峰值",
        "ftir.peak_apply": "应用/保存结果",
        "ftir.peak_clear": "清除结果",
        "ftir.peak_no_result": "尚无峰值结果。",
        "ftir.peak_preview_summary": (
            "预览：{source}，{polarity}，正峰 {positive}，负峰 {negative}。"
        ),
        "ftir.peak_applied_summary": (
            "已应用：{source}，{polarity}，正峰 {positive}，负峰 {negative}。"
        ),
        "ftir.peak_preview_ready": (
            "峰值预览完成：正峰 {positive}，负峰 {negative}。"
        ),
        "ftir.peak_applied": (
            "峰值结果已保存：正峰 {positive}，负峰 {negative}。"
        ),
        "ftir.peak_cleared": "已清除峰值结果。",
        "ftir.peak_preview_cancelled": "参数已更改，旧峰值预览已失效。",
        "ftir.peak_parameter_summary": (
            "高度={height}，显著度={prominence}，距离={distance} 点，"
            "最小宽度={width} 点"
        ),
        "ftir.peak_preview_required": "请先生成峰值预览。",
        "ftir.peak_detection_failed": "峰值检测失败 [{code}]：{error}",
        "ftir.peak_warnings": "警告：{warnings}",
        "ftir.peak_index": "序号",
        "ftir.peak_polarity_col": "极性",
        "ftir.peak_x_header": "X（{unit}）",
        "ftir.peak_y_header": "Y（{unit}）",
        "ftir.peak_prominence_header": "显著度（{unit}）",
        "ftir.peak_width_samples_header": "宽度（采样点）",
        "ftir.peak_width_x_header": "宽度（{unit}）",
        "ftir.processing_group": "显式处理",
        "ftir.operation": "处理操作",
        "ftir.operation_normalization": "归一化",
        "ftir.operation_baseline": "基线校正",
        "ftir.normalization_method": "归一化方法",
        "ftir.method_min_max": "Min-Max（[0, 1]）",
        "ftir.method_max_abs": "最大绝对值",
        "ftir.method_l2": "L2 范数",
        "ftir.preview": "预览",
        "ftir.apply": "应用",
        "ftir.cancel_preview": "取消预览",
        "ftir.undo": "撤销",
        "ftir.redo": "重做",
        "ftir.reset": "重置到原始",
        "ftir.processing_state": "处理历史：{count} 步",
        "ftir.preview_active": "预览：{method}；尚未写入处理历史。",
        "ftir.preview_required": "请先生成预览，再应用处理。",
        "ftir.baseline_algorithm": "基线算法",
        "ftir.baseline_linear": "线性",
        "ftir.baseline_polynomial": "多项式",
        "ftir.polynomial_degree": "多项式阶数",
        "ftir.fitting_regions": "拟合区域",
        "ftir.region_start": "起点 X",
        "ftir.region_end": "终点 X",
        "ftir.region_start_hint": "例如 3800",
        "ftir.region_end_hint": "例如 4000",
        "ftir.add_region": "添加区域",
        "ftir.remove_region": "删除区域",
        "ftir.fit_info": "阶数：{degree}；拟合点数：{points}",
        "ftir.fit_info_applied": "已应用：阶数 {degree}；拟合点数 {points}",
        "ftir.fit_info_pending": "阶数：{degree}；拟合点数：尚未拟合",
        "ftir.invalid_region": "无效拟合区域：{error}",
        "ftir.region_no_points": "该区域不包含任何数据点。",
        "ftir.region_points": "（{points} 个拟合点）",
        "ftir.baseline_preview_ready": (
            "基线预览已生成：{algorithm}，阶数 {degree}，{points} 个拟合点。"
        ),
        "ftir.baseline_preview_active": (
            "基线预览：{algorithm}，阶数 {degree}，{points} 个拟合点；"
            "尚未写入处理历史。"
        ),
        "ftir.baseline_applied": (
            "已应用{algorithm}基线校正（阶数 {degree}）。"
        ),
        "ftir.current_label": "当前处理谱",
        "ftir.baseline_label": "估计基线",
        "ftir.preview_cancelled": "已取消预览。",
        "ftir.preview_ready": "预览已生成：{method}。",
        "ftir.normalization_applied": "已应用 {method}。",
        "ftir.undo_applied": "已撤销上一步归一化。",
        "ftir.redo_applied": "已恢复下一步归一化。",
        "ftir.reset_applied": "已重置到原始光谱。",
        "ftir.processing_failed": "归一化失败 [{code}]：{error}",
        "ftir.no_spectrum": "尚未加载光谱。",
        "ftir.high_wavenumber_left": "高波数显示在左侧（仅视觉，不改变数据）",
        "ftir.axis_unknown": "X 轴（未知）",
        "ftir.signal_unknown": "Y 信号（未知）",
        "ftir.loaded": "已加载 {points} 个点（{format_id}）。",
        "ftir.loaded_with_warnings": (
            "已加载 {points} 个点（{format_id}），有 {count} 条警告："
            "{warnings}"
        ),
        "ftir.import_failed": "FTIR 导入失败 [{code}]：{error}",
        "ftir.options_invalid": "FTIR 导入选项无效：{error}",
        "ftir.no_file": "请选择 FTIR 光谱文件。",
        "ftir.file_required": "文件不存在或不是文件：{path}",
        "ftir.custom_delimiter_required": "请输入一个自定义分隔符字符。",
        "ftir.browse": "浏览…",
        "ftir.ok": "导入",
        "ftir.cancel": "取消",
    },
    "en": {
        "technique.ftir.name": "FTIR (CSV / TXT / DPT)",
        "ftir.file_label": "File",
        "ftir.file": "File: {name}",
        "ftir.file_none": "No FTIR spectrum loaded.",
        "ftir.import_options": "Import FTIR file with options…",
        "ftir.import_dialog_title": "FTIR import options",
        "ftir.choose_file_title": "Choose an FTIR spectrum file",
        "ftir.columns_group": "Columns and text parsing",
        "ftir.metadata_group": "FTIR metadata (explicit input)",
        "ftir.plot_group": "Raw FTIR spectrum",
        "ftir.x_column": "X column",
        "ftir.y_column": "Y column",
        "ftir.x_column_hint": "Index or header name; blank for two-column files",
        "ftir.y_column_hint": "Index or header name; blank for two-column files",
        "ftir.header": "First row is a header",
        "ftir.delimiter": "Delimiter",
        "ftir.delimiter_auto": "Auto (from file suffix)",
        "ftir.delimiter_comma": "Comma",
        "ftir.delimiter_tab": "Tab",
        "ftir.delimiter_semicolon": "Semicolon",
        "ftir.delimiter_whitespace": "Whitespace",
        "ftir.delimiter_custom": "Custom…",
        "ftir.custom_delimiter": "Custom delimiter",
        "ftir.custom_delimiter_placeholder": "One character",
        "ftir.decimal": "Decimal separator",
        "ftir.decimal_dot": "Dot (.)",
        "ftir.decimal_comma": "Comma (,)",
        "ftir.comment": "Comment markers",
        "ftir.comment_hint": "For example # ; separate multiple markers with spaces",
        "ftir.encoding": "Text encoding",
        "ftir.skip_rows": "Rows to skip at start",
        "ftir.x_name": "X-axis name (optional)",
        "ftir.y_name": "Y-axis name (optional)",
        "ftir.x_quantity": "X-axis quantity",
        "ftir.x_unit": "X-axis unit",
        "ftir.y_semantics": "Y signal semantics",
        "ftir.y_unit": "Y signal unit (optional)",
        "ftir.acquisition_mode": "Acquisition mode",
        "ftir.atr_status": "ATR correction status",
        "ftir.instrument_vendor": "Instrument vendor (optional)",
        "ftir.instrument_model": "Instrument model (optional)",
        "ftir.quantity_unknown": "Unknown",
        "ftir.quantity_wavenumber": "Wavenumber",
        "ftir.unit_unknown": "Unknown",
        "ftir.unit_cm_inverse": "cm^-1",
        "ftir.semantics_unknown": "Unknown",
        "ftir.semantics_absorbance": "Absorbance",
        "ftir.semantics_transmittance": "Transmittance",
        "ftir.acq_unknown": "Unknown",
        "ftir.acq_atr": "ATR",
        "ftir.acq_transmission": "Transmission",
        "ftir.atr_unknown": "unknown",
        "ftir.atr_applied": "applied",
        "ftir.atr_not_applied": "not_applied",
        "ftir.atr_not_applicable": "not_applicable",
        "ftir.raw_group": "Raw data only",
        "ftir.raw_label": "Raw",
        "ftir.processed_label": "Normalized",
        "ftir.baseline_processed_label": "Baseline-corrected",
        "ftir.preview_label": "Preview (not applied)",
        "ftir.raw_note": (
            "Source data remain read-only; processed curves appear only after "
            "explicit application. No automatic smoothing, baseline, "
            "normalization or ATR correction is applied."
        ),
        "ftir.tab_import_options": "Import options",
        "ftir.tab_peak_picking": "Peak picking",
        "ftir.peak_source": "Detection source",
        "ftir.peak_source_raw": "Raw spectrum",
        "ftir.peak_source_processed": "Current processed spectrum",
        "ftir.peak_polarity": "Peak polarity",
        "ftir.peak_positive": "Positive peaks",
        "ftir.peak_negative": "Negative peaks",
        "ftir.peak_both": "Positive and negative",
        "ftir.peak_height": "Height threshold (oriented signal units; magnitude for negative)",
        "ftir.peak_prominence": "Prominence threshold (signal units)",
        "ftir.peak_distance": "Minimum distance (samples)",
        "ftir.peak_min_width": "Minimum width (samples)",
        "ftir.peak_blank_none": "Blank = none",
        "ftir.peak_samples_suffix": " pts",
        "ftir.peak_preview": "Preview peaks",
        "ftir.peak_apply": "Apply/Save results",
        "ftir.peak_clear": "Clear results",
        "ftir.peak_no_result": "No peak results.",
        "ftir.peak_preview_summary": (
            "Preview: {source}, {polarity}, {positive} positive, "
            "{negative} negative."
        ),
        "ftir.peak_applied_summary": (
            "Applied: {source}, {polarity}, {positive} positive, "
            "{negative} negative."
        ),
        "ftir.peak_preview_ready": (
            "Peak preview complete: {positive} positive, {negative} negative."
        ),
        "ftir.peak_applied": (
            "Peak results saved: {positive} positive, {negative} negative."
        ),
        "ftir.peak_cleared": "Peak results cleared.",
        "ftir.peak_preview_cancelled": (
            "Parameters changed; the previous peak preview was invalidated."
        ),
        "ftir.peak_parameter_summary": (
            "height={height}, prominence={prominence}, distance={distance} pts, "
            "min width={width} pts"
        ),
        "ftir.peak_preview_required": "Generate a peak preview first.",
        "ftir.peak_detection_failed": "Peak detection failed [{code}]: {error}",
        "ftir.peak_warnings": "Warnings: {warnings}",
        "ftir.peak_index": "Index",
        "ftir.peak_polarity_col": "Polarity",
        "ftir.peak_x_header": "X ({unit})",
        "ftir.peak_y_header": "Y ({unit})",
        "ftir.peak_prominence_header": "Prominence ({unit})",
        "ftir.peak_width_samples_header": "Width (samples)",
        "ftir.peak_width_x_header": "Width ({unit})",
        "ftir.processing_group": "Explicit processing",
        "ftir.operation": "Processing operation",
        "ftir.operation_normalization": "Normalization",
        "ftir.operation_baseline": "Baseline correction",
        "ftir.normalization_method": "Normalization method",
        "ftir.method_min_max": "Min-Max ([0, 1])",
        "ftir.method_max_abs": "Maximum absolute value",
        "ftir.method_l2": "L2 norm",
        "ftir.preview": "Preview",
        "ftir.apply": "Apply",
        "ftir.cancel_preview": "Cancel preview",
        "ftir.undo": "Undo",
        "ftir.redo": "Redo",
        "ftir.reset": "Reset to raw",
        "ftir.processing_state": "Processing history: {count} step(s)",
        "ftir.preview_active": (
            "Preview: {method}; it is not yet in the processing history."
        ),
        "ftir.preview_required": "Generate a preview before applying a processing operation.",
        "ftir.baseline_algorithm": "Baseline algorithm",
        "ftir.baseline_linear": "Linear",
        "ftir.baseline_polynomial": "Polynomial",
        "ftir.polynomial_degree": "Polynomial degree",
        "ftir.fitting_regions": "Fitting regions",
        "ftir.region_start": "Start X",
        "ftir.region_end": "End X",
        "ftir.region_start_hint": "For example 3800",
        "ftir.region_end_hint": "For example 4000",
        "ftir.add_region": "Add region",
        "ftir.remove_region": "Remove region",
        "ftir.fit_info": "Degree: {degree}; fitting points: {points}",
        "ftir.fit_info_applied": "Applied: degree {degree}; fitting points {points}",
        "ftir.fit_info_pending": "Degree: {degree}; fitting points: not fitted",
        "ftir.invalid_region": "Invalid fitting region: {error}",
        "ftir.region_no_points": "This region contains no data points.",
        "ftir.region_points": " ({points} fitting points)",
        "ftir.baseline_preview_ready": (
            "Baseline preview generated: {algorithm}, degree {degree}, "
            "{points} fitting points."
        ),
        "ftir.baseline_preview_active": (
            "Baseline preview: {algorithm}, degree {degree}, {points} "
            "fitting points; not yet in the processing history."
        ),
        "ftir.baseline_applied": (
            "Applied {algorithm} baseline correction (degree {degree})."
        ),
        "ftir.current_label": "Current processed",
        "ftir.baseline_label": "Estimated baseline",
        "ftir.preview_cancelled": "Preview cancelled.",
        "ftir.preview_ready": "Preview generated: {method}.",
        "ftir.normalization_applied": "Applied {method}.",
        "ftir.undo_applied": "Undid the last normalization.",
        "ftir.redo_applied": "Redid the next normalization.",
        "ftir.reset_applied": "Reset to the raw spectrum.",
        "ftir.processing_failed": "Normalization failed [{code}]: {error}",
        "ftir.no_spectrum": "No spectrum loaded.",
        "ftir.high_wavenumber_left": (
            "Show high wavenumber on the left (visual only; data unchanged)"
        ),
        "ftir.axis_unknown": "X axis (unknown)",
        "ftir.signal_unknown": "Y signal (unknown)",
        "ftir.loaded": "Loaded {points} points ({format_id}).",
        "ftir.loaded_with_warnings": (
            "Loaded {points} points ({format_id}) with {count} warning(s): "
            "{warnings}"
        ),
        "ftir.import_failed": "FTIR import failed [{code}]: {error}",
        "ftir.options_invalid": "Invalid FTIR import options: {error}",
        "ftir.no_file": "Select an FTIR spectrum file.",
        "ftir.file_required": "File does not exist or is not a file: {path}",
        "ftir.custom_delimiter_required": "Enter one custom delimiter character.",
        "ftir.browse": "Browse…",
        "ftir.ok": "Import",
        "ftir.cancel": "Cancel",
    },
}

def register_ftir_translations(translator: Translator) -> None:
    """Register the FTIR catalog; identical duplicate registration is safe."""
    translator.register_catalog(FTIR_TRANSLATIONS, source="ftir")


__all__ = [
    "FTIR_DISPLAY_NAME_KEY",
    "FTIR_FILE_PATTERNS",
    "FTIR_TECHNIQUE_ID",
    "FTIR_TRANSLATIONS",
    "register_ftir_translations",
]
