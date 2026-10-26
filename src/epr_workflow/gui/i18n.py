"""Bilingual (Simplified Chinese / English) UI strings for the desktop GUI.

This module deliberately has **no Qt imports**, so the translation catalog can
be imported and unit-tested without a display server.

Design notes
------------
* Keys are stable identifiers (``open_asc``, ``batch_process``, ...). Every
  language catalog must contain the same key set; the test suite enforces it.
* :func:`tr_text` is the single lookup entry point. Missing keys fall back to
  Simplified Chinese and then to the key itself, so a missing translation is
  visible instead of raising.
* Core data-processing diagnostics are **not** translated here. They are
  produced by :mod:`epr_workflow.plot_asc`, written verbatim into the JSON
  metadata and the batch summary, and are therefore part of the scientific
  record. The GUI displays them unchanged and labels the surrounding section
  in the selected language.
"""

from __future__ import annotations

from typing import Any

DEFAULT_LANGUAGE = "zh"

#: Language code -> name shown in the language selector. The selector label is
#: intentionally bilingual and never translated.
LANGUAGES: dict[str, str] = {
    "zh": "简体中文",
    "en": "English",
}

_ZH: dict[str, str] = {
    # Window and controls
    "window_title": "EPR Workflow — ASC 导入与绘图",
    "open_asc": "打开单个 ASC 文件",
    "batch_process": "批量处理文件夹…",
    "output_directory": "输出目录…",
    "recursive_subdirs": "递归子目录",
    "allow_overwrite": "允许覆盖",
    "sample_list": "样品列表",
    "batch_not_run": "尚未批量处理",
    # Plot panel
    "cursor_idle": "光标：—",
    "cursor_value": "光标：磁场 {field:.4f} G　强度 {intensity:.4f}",
    "open_csv": "打开 CSV",
    "open_png": "打开 PNG",
    "open_json": "打开 JSON",
    "tip_open_csv": "打开本次批处理生成的 CSV 文件",
    "tip_open_png": "打开本次批处理生成的 PNG 图像",
    "tip_open_json": "打开本次批处理生成的 JSON 元数据",
    "metadata_section": "元数据与校验",
    "toolbar_home": "复位到初始视图",
    "toolbar_back": "返回上一个视图",
    "toolbar_forward": "前进到下一个视图",
    "toolbar_pan": "左键平移，右键缩放\nx/y 固定单轴，CTRL 固定纵横比",
    "toolbar_zoom": "框选缩放\nx/y 固定单轴",
    "toolbar_subplots": "调整子图布局",
    "toolbar_customize": "编辑坐标轴、曲线与图像参数",
    "toolbar_save": "保存图像",
    # Preprocessing panel
    "prep_group": "预处理",
    "prep_method_label": "方法",
    "prep_method_linear": "线性基线校正",
    "prep_method_savgol": "Savitzky–Golay 平滑",
    "prep_window_length": "窗口长度",
    "prep_polyorder": "多项式阶数",
    "prep_input_source": "平滑输入",
    "prep_input_current": "当前处理结果",
    "prep_input_raw": "原始数据",
    "prep_savgol_note": (
        "平滑会改变峰高、峰宽与线形；不会自动应用，也不代表数据质量一定改善。"
    ),
    "prep_window_left": "左区间（G）",
    "prep_window_right": "右区间（G）",
    "prep_preview": "预览",
    "prep_cancel_preview": "取消预览",
    "prep_apply": "应用",
    "prep_undo": "撤销",
    "prep_reset": "重置",
    "prep_export": "导出处理结果…",
    "prep_scope_note": (
        "仅在内存中处理；原始 ASC 文件不会被修改，预览不会写入任何文件。"
    ),
    "prep_status_raw": "状态：原始数据",
    "prep_status_preview": "状态：预览（未应用）",
    "prep_status_applied": "状态：已应用 {n} 步",
    "prep_status_exported": "状态：已应用 {n} 步，已导出",
    # Preprocessing dialogs
    "title_preprocessing_invalid": "预处理参数无效",
    "title_preprocessing_failed": "预处理失败",
    "title_export_failed": "导出失败",
    "msg_error_detail": "{type}: {error}",
    # Preprocessing metadata
    "meta_prep_header": "预处理：",
    "meta_prep_order": "处理顺序：{order}",
    "meta_operation_baseline": "线性基线校正",
    "meta_operation_savgol": "Savitzky–Golay 平滑",
    "meta_prep_savgol_step": "步骤 {index}：Savitzky–Golay 平滑",
    "meta_prep_savgol_params": "窗口长度 {window_length}，多项式阶数 {polyorder}",
    "meta_prep_savgol_input": "输入数据：{source}（前置步骤 {count}）",
    "meta_prep_savgol_change": (
        "变化：RMS {rms:.6g}，最大绝对变化 {max_change:.6g}"
    ),
    "meta_input_raw": "原始数据",
    "meta_input_current": "当前处理结果",
    "meta_prep_input": "输入数据：{source}（前置步骤 {count}）",
    "meta_prep_fit_input_note": "（拟合参数来自原输入：{source}）",
    "meta_prep_none": "预处理：未应用",
    "meta_prep_mode_preview": "模式：预览（未应用，未写入文件）",
    "meta_prep_mode_applied": "模式：已应用 {n} 步",
    "meta_prep_mode_exported": "模式：已应用 {n} 步，已导出",
    "meta_prep_step": "步骤 {index}：线性基线校正",
    "meta_prep_windows": (
        "基线窗口：{left_start:.4f}–{left_end:.4f} G 与 "
        "{right_start:.4f}–{right_end:.4f} G"
    ),
    "meta_prep_points": (
        "窗口点数：左 {left}，右 {right}"
        "（3 点只是拟合可计算的下限，不代表基线可靠）"
    ),
    "meta_prep_fit": (
        "线性拟合：斜率 {slope:.6g} 强度/G，截距 {intercept:.6g}，R² {r2}"
    ),
    "meta_prep_r2_none": "不适用（窗口内强度恒定）",
    "meta_prep_rms": "残差 RMS：总 {rms:.6g}，左 {left:.6g}，右 {right:.6g}",
    "meta_prep_extrapolation": "外推距离：左侧 {left:.4f} G，右侧 {right:.4f} G",
    "meta_prep_warnings": "预处理警告：",
    "meta_prep_caution": (
        "R² 只描述窗口内直线拟合的贴合程度，不能证明所选区域就是基线；"
        "请结合残差、点数和外推距离判断。"
    ),
    "meta_prep_savgol_caution": (
        "平滑会改变峰高、峰宽与线形；曲线更光滑并不等于数据质量提高。"
    ),
    "meta_prep_raw_note": "原始数据未被修改；撤销与重置都从原始数据重算。",
    "meta_prep_exported_path": "已导出：{path}",
    # Processed plot
    "plot_title_corrected": "{sample} - 线性基线校正后 CW-EPR 谱图",
    "plot_title_preview": "{sample} - 线性基线校正预览",
    "plot_title_smoothed": "{sample} - Savitzky–Golay 平滑后 CW-EPR 谱图",
    "plot_title_savgol_preview": "{sample} - Savitzky–Golay 平滑预览",
    "plot_title_processed": "{sample} - 预处理后 CW-EPR 谱图",
    "plot_title_processed_preview": "{sample} - 预处理预览",
    "plot_ylabel_corrected": "强度（原始单位，已校正）",
    "plot_ylabel_smoothed": "强度（原始单位，已平滑）",
    "plot_ylabel_processed": "强度（原始单位，已预处理）",
    "plot_legend_raw": "原始",
    "plot_legend_corrected": "校正后",
    "plot_legend_smoothed": "平滑后",
    "plot_legend_processed": "处理后",
    "plot_legend_removed": "移除的基线",
    "plot_legend_difference": "差异（原始 − 处理后）",
    "cursor_value_corrected": (
        "光标：磁场 {field:.4f} G　强度 {intensity:.4f}（校正后）"
    ),
    "cursor_value_smoothed": (
        "光标：磁场 {field:.4f} G　强度 {intensity:.4f}（已平滑）"
    ),
    "cursor_value_processed": (
        "光标：磁场 {field:.4f} G　强度 {intensity:.4f}（已处理）"
    ),
    "cursor_value_preview": "光标：磁场 {field:.4f} G　强度 {intensity:.4f}（预览）",
    # Plot Editor
    "plot_tab_preprocessing": "预处理",
    "plot_tab_plot": "绘图",
    "plot_curves_label": "曲线（勾选以显示）",
    "plot_curve_style_group": "选中曲线的样式",
    "plot_curve_name_label": "显示名称",
    "plot_curve_color": "颜色",
    "plot_curve_width": "线宽",
    "plot_curve_linestyle": "线型",
    "plot_axis_group": "坐标轴与图例",
    "plot_title_label": "标题",
    "plot_xlabel_label": "X 轴标签",
    "plot_ylabel_label": "Y 轴标签",
    "plot_x_range_label": "X 轴范围",
    "plot_y_range_label": "Y 轴范围",
    "plot_x_auto": "自动",
    "plot_y_auto": "自动",
    "plot_legend_visible": "显示图例",
    "plot_legend_location": "图例位置",
    "plot_font_group": "字体大小",
    "plot_font_title": "标题",
    "plot_font_axis": "轴标签",
    "plot_font_tick": "刻度",
    "plot_font_legend": "图例",
    "plot_reset": "重置绘图设置",
    "plot_restore_visibility": "恢复默认可见性",
    "plot_export": "导出绘图…",
    "plot_scope_note": (
        "绘图设置只改变显示方式；不会修改原始数据、处理结果或预处理历史。"
    ),
    "plot_error_color": "颜色必须使用 #RRGGBB 格式。",
    "plot_error_axis_range": "坐标轴范围必须是有限数值，且最小值小于最大值。",
    "plot_error_no_visible_curve": "至少需要一条可见曲线才能导出绘图。",
    "plot_error_unavailable_curve": (
        "所选曲线当前不可用；请重新加载或调整预处理状态。"
    ),
    "plot_error_missing_curve": "绘图设置缺少当前可用曲线的参数。",
    "plot_error_export_size": "图像宽度和高度必须在 0.5–100 英寸之间。",
    "plot_error_export_dpi": "DPI 必须在 50–1200 之间。",
    "plot_status_preview": (
        "处于预处理预览：应用或取消预览后才能导出绘图。"
    ),
    "plot_status_exported": "绘图已导出：{path}",
    "plot_export_dialog_title": "导出绘图 PNG",
    "plot_export_width": "宽度（英寸）",
    "plot_export_height": "高度（英寸）",
    "plot_export_dpi": "DPI",
    "plot_export_include_title": "包含标题",
    "plot_export_include_legend": "包含图例",
    "plot_export_path": "输出文件",
    "plot_export_browse": "浏览…",
    "plot_export_overwrite": "允许覆盖已有文件",
    "plot_export_invalid_path": "输出路径必须是以 .png 结尾的文件。",
    "plot_export_ok": "导出",
    "title_plot_export_unavailable": "无法导出绘图",
    "title_plot_export_failed": "绘图导出失败",
    "msg_plot_export_preview": (
        "当前显示的是未应用的预处理预览。请先应用或取消预览，再导出绘图。"
    ),
    "plot_legend_fitted_baseline": "拟合基线",
    "plot_line_solid": "实线",
    "plot_line_dashed": "虚线",
    "plot_line_dotted": "点线",
    "plot_line_dashdot": "点划线",
    "plot_legend_best": "自动选择",
    "plot_legend_upper_right": "右上",
    "plot_legend_upper_left": "左上",
    "plot_legend_lower_right": "右下",
    "plot_legend_lower_left": "左下",
    "plot_legend_center_right": "右侧居中",
    "plot_legend_center_left": "左侧居中",
    "plot_legend_upper_center": "上方居中",
    "plot_legend_lower_center": "下方居中",
    "plot_legend_center": "居中",
    # Preprocessing errors
    "prep_error_array": (
        "数据数组无效：field 与 intensity 必须是一维、等长、非空的数值数组。"
    ),
    "prep_error_nonfinite": "数据中存在 NaN 或 Inf，无法进行基线校正。",
    "prep_error_field_duplicate": (
        "磁场轴包含 {duplicates} 处相邻重复值，不是严格单调的；"
        "已拒绝基线校正，未删除或合并任何数据点。"
    ),
    "prep_error_field_not_monotonic": (
        "磁场轴不是严格单调的（{decreasing_steps} 个递减步）；"
        "已拒绝基线校正，未排序或修复数据。"
    ),
    "prep_error_window_bounds": (
        "区间起点必须小于终点：{start:.4f} G ≥ {end:.4f} G。"
    ),
    "prep_error_windows_unset": (
        "请先选择基线区间：填写左、右两个区间后再预览或应用。"
    ),
    "prep_error_window_order": (
        "左区间必须位于右区间之前：左起点 {left_start:.4f} G，"
        "右起点 {right_start:.4f} G。"
    ),
    "prep_error_window_outside": (
        "区间 {start:.4f}–{end:.4f} G 超出磁场范围 "
        "{field_min:.4f}–{field_max:.4f} G。"
    ),
    "prep_error_window_points": (
        "区间 {start:.4f}–{end:.4f} G 只包含 {count} 个数据点，"
        "至少需要 {required} 个。{required} 个点只是拟合可计算的最低要求，"
        "不代表基线区域可靠。"
    ),
    "prep_error_window_overlap": (
        "两个区间重叠或共享端点（左区间终点 {left_end:.4f} G ≥ "
        "右区间起点 {right_start:.4f} G）。"
    ),
    "prep_error_window_gap": (
        "两个区间之间至少需要 {required} 个未选数据点，当前为 {count} 个。"
    ),
    "prep_error_degenerate": "区间内磁场方差为零，无法定义直线。",
    "prep_error_fit_nonfinite": "拟合结果包含非有限值，已中止。",
    "prep_error_source_changed": (
        "源文件自导入后已改变（SHA-256 不匹配），已拒绝导出处理结果。"
    ),
    "prep_error_preview_export": "预览结果不能导出；请先应用。",
    "prep_error_no_steps": "尚未应用任何预处理步骤。",
    "prep_error_no_pending": "没有待应用的预览参数。",
    "prep_error_data_mismatch": "处理结果与导入数据不一致。",
    "prep_error_savgol_window_even": "窗口长度必须为奇数：{window_length}。",
    "prep_error_savgol_window_too_small": "窗口长度至少为 3：{window_length}。",
    "prep_error_savgol_window_too_large": (
        "窗口长度（{window_length}）超过数据点数（{n_points}）。"
    ),
    "prep_error_savgol_polyorder": (
        "多项式阶数必须满足 0 ≤ 阶数 < 窗口长度"
        "（阶数 {polyorder}，窗口长度 {window_length}）。"
    ),
    "prep_error_savgol_parameter": "Savitzky–Golay 参数无效。",
    "prep_error_savgol_unavailable": "SciPy 不可用，无法执行 Savitzky–Golay 平滑。",
    "prep_error_savgol_failed": "Savitzky–Golay 平滑执行失败。",
    "prep_error_savgol_output_invalid": "Savitzky–Golay 返回了无效数组。",
    "prep_error_savgol_input_source": "平滑输入来源无效。",
    "prep_error_unsupported_operation": "不支持的处理操作。",
    # Preprocessing warnings
    "prep_warning_few_points": (
        "区间 {start:.4f}–{end:.4f} G 仅有 {count} 个点（最低 {required} 个）；"
        "这只是计算下限，不足以证明该区域是可靠基线。"
    ),
    "prep_warning_extrapolation": (
        "窗口外侧外推较大：左侧 {left:.4f} G，右侧 {right:.4f} G"
        "（阈值 {threshold:.4f} G）。"
    ),
    "prep_warning_coverage_low": (
        "基线窗口只包含 {fraction:.2%} 的数据点，覆盖过少。"
    ),
    "prep_warning_coverage_high": (
        "两个窗口合计覆盖 {fraction:.2%} 的场跨度，可能包含真实信号。"
    ),
    "prep_warning_noisy_window": (
        "某基线窗口明显偏离拟合直线（残差 RMS 左 {left_rms:.6g}，"
        "右 {right_rms:.6g}；全局噪声估计 {noise:.6g}），"
        "该区域可能含有真实信号。"
    ),
    "prep_warning_r2_undefined": "窗口内强度完全恒定，R² 无法定义（斜率可能为 0）。",
    "prep_warning_smoothing_reorders": (
        "平滑作用于原始数据并置于已有步骤之前；当前顺序为先平滑、后原有步骤"
        "（共 {step_count} 步）。原有步骤沿用其拟合参数并作用于平滑后的数据。"
    ),
    # File dialogs
    "dialog_select_asc": "选择 ASC 文件",
    "asc_filter": "Xepr ASCII (*.asc *.ASC);;所有文件 (*.*)",
    "dialog_select_batch_dir": "选择包含 ASC 文件的文件夹",
    "dialog_select_output_dir": "选择输出目录",
    # Dialogs and error messages
    "title_outputs_exist": "已存在输出",
    "msg_outputs_exist": (
        "{error}\n\n如需覆盖，请勾选“允许覆盖”后重试，或更换输出目录。"
    ),
    "title_write_failed": "写入失败",
    "msg_write_failed": "无法写入批次汇总：{error}",
    "title_read_failed": "读取失败",
    "msg_read_failed": "{name}\n{type}: {error}",
    "metadata_read_error": "无法读取 {path}：\n{type}: {error}",
    "title_file_missing": "文件不存在",
    "no_samples": "没有可显示的样品。",
    # Metadata panel
    "meta_file": "文件：{path}",
    "meta_points": "数据点数：{n}",
    "meta_field_range": "磁场范围：{low:.4f} – {high:.4f} G",
    "meta_field_direction": "磁场方向：{order}",
    "meta_signal": (
        "信号：min {smin:.4f} | max {smax:.4f} | "
        "mean {mean:.4f} | std {std:.4f} (ddof=1)"
    ),
    "meta_warnings": "校验警告：",
    "meta_warnings_none": "校验警告：无",
    "meta_warnings_note": (
        "（核心校验信息按英文原文显示，并原样写入 JSON 元数据。）"
    ),
    # Plot text
    "plot_xlabel": "磁场 (G)",
    "plot_ylabel": "强度（原始单位）",
    "plot_title": "{sample} - 原始 CW-EPR 谱图",
    # Batch summary
    "batch_counts": (
        "发现 {discovered} | 成功 {succeeded} | "
        "有警告 {warnings} | 失败 {failed}"
    ),
    "batch_overall": "总体状态：{status}",
    "batch_summary_path": "汇总：{path}",
    # Per-file status
    "status_success": "成功",
    "status_warnings": "成功（有警告）",
    "status_failed": "失败",
    # Overall batch status
    "overall_success": "成功",
    "overall_success_with_warnings": "成功（有警告）",
    "overall_partial_failure": "部分失败",
    "overall_failed": "失败",
    # Field direction (values emitted by plot_asc.read_asc)
    "field_order_increasing": "严格递增",
    "field_order_decreasing": "严格递减",
    "field_order_non_monotonic": "非单调",
    "field_order_unknown": "未知",
}

_EN: dict[str, str] = {
    # Window and controls
    "window_title": "EPR Workflow — ASC Import and Plotting",
    "open_asc": "Open ASC File",
    "batch_process": "Batch Process Folder…",
    "output_directory": "Output Directory…",
    "recursive_subdirs": "Include Subdirectories",
    "allow_overwrite": "Allow Overwrite",
    "sample_list": "Sample List",
    "batch_not_run": "Batch processing not run yet",
    # Plot panel
    "cursor_idle": "Cursor: —",
    "cursor_value": "Cursor: field {field:.4f} G   intensity {intensity:.4f}",
    "open_csv": "Open CSV",
    "open_png": "Open PNG",
    "open_json": "Open JSON",
    "tip_open_csv": "Open the CSV file generated by this batch run",
    "tip_open_png": "Open the PNG figure generated by this batch run",
    "tip_open_json": "Open the JSON metadata generated by this batch run",
    "metadata_section": "Metadata and Validation",
    "toolbar_home": "Reset original view",
    "toolbar_back": "Back to previous view",
    "toolbar_forward": "Forward to next view",
    "toolbar_pan": "Left button pans, Right button zooms\nx/y fixes axis, CTRL fixes aspect",
    "toolbar_zoom": "Zoom to rectangle\nx/y fixes axis",
    "toolbar_subplots": "Configure subplots",
    "toolbar_customize": "Edit axis, curve and image parameters",
    "toolbar_save": "Save the figure",
    # Preprocessing panel
    "prep_group": "Preprocessing",
    "prep_method_label": "Method",
    "prep_method_linear": "Linear baseline correction",
    "prep_method_savgol": "Savitzky–Golay smoothing",
    "prep_window_length": "Window length",
    "prep_polyorder": "Polynomial order",
    "prep_input_source": "Smoothing input",
    "prep_input_current": "Current processed result",
    "prep_input_raw": "Raw data",
    "prep_savgol_note": (
        "Smoothing can change peak height, peak width and line shape; it is "
        "never applied automatically and does not guarantee improved data "
        "quality."
    ),
    "prep_window_left": "Left window (G)",
    "prep_window_right": "Right window (G)",
    "prep_preview": "Preview",
    "prep_cancel_preview": "Cancel Preview",
    "prep_apply": "Apply",
    "prep_undo": "Undo",
    "prep_reset": "Reset",
    "prep_export": "Export Processed Results…",
    "prep_scope_note": (
        "Processing is in-memory only; the raw ASC file is never modified, "
        "and previews write no files."
    ),
    "prep_status_raw": "Status: raw data",
    "prep_status_preview": "Status: preview (not applied)",
    "prep_status_applied": "Status: {n} step(s) applied",
    "prep_status_exported": "Status: {n} step(s) applied, exported",
    # Preprocessing dialogs
    "title_preprocessing_invalid": "Invalid Preprocessing Parameters",
    "title_preprocessing_failed": "Preprocessing Failed",
    "title_export_failed": "Export Failed",
    "msg_error_detail": "{type}: {error}",
    # Preprocessing metadata
    "meta_prep_header": "Preprocessing:",
    "meta_prep_order": "Processing order: {order}",
    "meta_operation_baseline": "Linear baseline correction",
    "meta_operation_savgol": "Savitzky–Golay smoothing",
    "meta_prep_savgol_step": "Step {index}: Savitzky–Golay smoothing",
    "meta_prep_savgol_params": (
        "Window length {window_length}, polynomial order {polyorder}"
    ),
    "meta_prep_savgol_input": (
        "Input data: {source} (preceded by {count} step(s))"
    ),
    "meta_prep_savgol_change": (
        "Change: RMS {rms:.6g}, max absolute change {max_change:.6g}"
    ),
    "meta_input_raw": "Raw data",
    "meta_input_current": "Current processed result",
    "meta_prep_input": "Input data: {source} (preceded by {count} step(s))",
    "meta_prep_fit_input_note": (
        "(parameters were fitted on the original input: {source})"
    ),
    "meta_prep_none": "Preprocessing: not applied",
    "meta_prep_mode_preview": "Mode: preview (not applied; nothing written to disk)",
    "meta_prep_mode_applied": "Mode: {n} step(s) applied",
    "meta_prep_mode_exported": "Mode: {n} step(s) applied, exported",
    "meta_prep_step": "Step {index}: linear baseline correction",
    "meta_prep_windows": (
        "Baseline windows: {left_start:.4f}–{left_end:.4f} G and "
        "{right_start:.4f}–{right_end:.4f} G"
    ),
    "meta_prep_points": (
        "Points in windows: left {left}, right {right} (3 points is only the "
        "minimum for a defined fit, not evidence of reliability)"
    ),
    "meta_prep_fit": (
        "Linear fit: slope {slope:.6g} intensity/G, intercept {intercept:.6g}, "
        "R² {r2}"
    ),
    "meta_prep_r2_none": "not defined (constant intensity in the windows)",
    "meta_prep_rms": (
        "Residual RMS: total {rms:.6g}, left {left:.6g}, right {right:.6g}"
    ),
    "meta_prep_extrapolation": (
        "Extrapolation distance: left {left:.4f} G, right {right:.4f} G"
    ),
    "meta_prep_warnings": "Preprocessing warnings:",
    "meta_prep_caution": (
        "R² only describes how closely a line fits the selected windows; it "
        "does not prove those regions are baseline. Also consider residuals, "
        "point counts and extrapolation."
    ),
    "meta_prep_savgol_caution": (
        "Smoothing can change peak height, peak width and line shape; a "
        "smoother curve does not by itself mean better data quality."
    ),
    "meta_prep_raw_note": (
        "Raw data are unchanged; undo and reset recompute from the raw data."
    ),
    "meta_prep_exported_path": "Exported: {path}",
    # Processed plot
    "plot_title_corrected": "{sample} - Linear Baseline Corrected CW-EPR Spectrum",
    "plot_title_preview": "{sample} - Baseline Correction Preview",
    "plot_title_smoothed": "{sample} - Savitzky–Golay Smoothed CW-EPR Spectrum",
    "plot_title_savgol_preview": "{sample} - Savitzky–Golay Smoothing Preview",
    "plot_title_processed": "{sample} - Preprocessed CW-EPR Spectrum",
    "plot_title_processed_preview": "{sample} - Preprocessing Preview",
    "plot_ylabel_corrected": "Intensity (original units, baseline corrected)",
    "plot_ylabel_smoothed": "Intensity (original units, smoothed)",
    "plot_ylabel_processed": "Intensity (original units, preprocessed)",
    "plot_legend_raw": "Raw",
    "plot_legend_corrected": "Corrected",
    "plot_legend_smoothed": "Smoothed",
    "plot_legend_processed": "Processed",
    "plot_legend_removed": "Removed baseline",
    "plot_legend_difference": "Difference (raw − processed)",
    "cursor_value_corrected": (
        "Cursor: field {field:.4f} G   intensity {intensity:.4f} (corrected)"
    ),
    "cursor_value_smoothed": (
        "Cursor: field {field:.4f} G   intensity {intensity:.4f} (smoothed)"
    ),
    "cursor_value_processed": (
        "Cursor: field {field:.4f} G   intensity {intensity:.4f} (processed)"
    ),
    "cursor_value_preview": (
        "Cursor: field {field:.4f} G   intensity {intensity:.4f} (preview)"
    ),
    # Plot Editor
    "plot_tab_preprocessing": "Preprocessing",
    "plot_tab_plot": "Plot",
    "plot_curves_label": "Curves (tick to show)",
    "plot_curve_style_group": "Style of Selected Curve",
    "plot_curve_name_label": "Display name",
    "plot_curve_color": "Colour",
    "plot_curve_width": "Line width",
    "plot_curve_linestyle": "Line style",
    "plot_axis_group": "Axes and Legend",
    "plot_title_label": "Title",
    "plot_xlabel_label": "X-axis label",
    "plot_ylabel_label": "Y-axis label",
    "plot_x_range_label": "X-axis range",
    "plot_y_range_label": "Y-axis range",
    "plot_x_auto": "Auto",
    "plot_y_auto": "Auto",
    "plot_legend_visible": "Show legend",
    "plot_legend_location": "Legend location",
    "plot_font_group": "Font Sizes",
    "plot_font_title": "Title",
    "plot_font_axis": "Axis labels",
    "plot_font_tick": "Ticks",
    "plot_font_legend": "Legend",
    "plot_reset": "Reset Plot Settings",
    "plot_restore_visibility": "Restore Default Visibility",
    "plot_export": "Export Plot…",
    "plot_scope_note": (
        "Plot settings change display only; they never modify raw data, "
        "processed data or the preprocessing history."
    ),
    "plot_error_color": "The colour must use the #RRGGBB format.",
    "plot_error_axis_range": (
        "Axis limits must be finite numbers with the minimum below the maximum."
    ),
    "plot_error_no_visible_curve": (
        "At least one curve must be visible to export a plot."
    ),
    "plot_error_unavailable_curve": (
        "The selected curve is not available; reload the sample or adjust "
        "the preprocessing state."
    ),
    "plot_error_missing_curve": (
        "The plot settings are missing a curve that is currently available."
    ),
    "plot_error_export_size": (
        "Figure width and height must be between 0.5 and 100 inches."
    ),
    "plot_error_export_dpi": "DPI must be between 50 and 1200.",
    "plot_status_preview": (
        "Preprocessing preview is active; apply or cancel it before exporting "
        "the plot."
    ),
    "plot_status_exported": "Plot exported: {path}",
    "plot_export_dialog_title": "Export Plot PNG",
    "plot_export_width": "Width (inches)",
    "plot_export_height": "Height (inches)",
    "plot_export_dpi": "DPI",
    "plot_export_include_title": "Include title",
    "plot_export_include_legend": "Include legend",
    "plot_export_path": "Output file",
    "plot_export_browse": "Browse…",
    "plot_export_overwrite": "Allow overwriting an existing file",
    "plot_export_invalid_path": "The output path must end with .png.",
    "plot_export_ok": "Export",
    "title_plot_export_unavailable": "Cannot Export Plot",
    "title_plot_export_failed": "Plot Export Failed",
    "msg_plot_export_preview": (
        "The current plot shows an unapplied preprocessing preview. Apply or "
        "cancel the preview before exporting the plot."
    ),
    "plot_legend_fitted_baseline": "Fitted baseline",
    "plot_line_solid": "Solid",
    "plot_line_dashed": "Dashed",
    "plot_line_dotted": "Dotted",
    "plot_line_dashdot": "Dash-dot",
    "plot_legend_best": "Best",
    "plot_legend_upper_right": "Upper right",
    "plot_legend_upper_left": "Upper left",
    "plot_legend_lower_right": "Lower right",
    "plot_legend_lower_left": "Lower left",
    "plot_legend_center_right": "Center right",
    "plot_legend_center_left": "Center left",
    "plot_legend_upper_center": "Upper center",
    "plot_legend_lower_center": "Lower center",
    "plot_legend_center": "Center",
    # Preprocessing errors
    "prep_error_array": (
        "Invalid data arrays: field and intensity must be one-dimensional, "
        "equally sized, non-empty numeric arrays."
    ),
    "prep_error_nonfinite": (
        "The data contain NaN or infinite values; baseline correction is not "
        "possible."
    ),
    "prep_error_field_duplicate": (
        "The magnetic-field axis contains {duplicates} repeated adjacent "
        "value(s) and is not strictly monotonic; baseline correction was "
        "refused. No rows were removed or merged."
    ),
    "prep_error_field_not_monotonic": (
        "The magnetic-field axis is not strictly monotonic "
        "({decreasing_steps} decreasing step(s)); baseline correction was "
        "refused. No sorting or repair was performed."
    ),
    "prep_error_window_bounds": (
        "A window start must be less than its end: {start:.4f} G ≥ {end:.4f} G."
    ),
    "prep_error_windows_unset": (
        "Select baseline windows first: fill in both windows before previewing "
        "or applying."
    ),
    "prep_error_window_order": (
        "The left window must start below the right window: left start "
        "{left_start:.4f} G, right start {right_start:.4f} G."
    ),
    "prep_error_window_outside": (
        "Window {start:.4f}–{end:.4f} G lies outside the field range "
        "{field_min:.4f}–{field_max:.4f} G."
    ),
    "prep_error_window_points": (
        "Window {start:.4f}–{end:.4f} G contains only {count} data point(s); "
        "at least {required} are required. That minimum only makes the fit "
        "computable; it does not establish that the baseline region is reliable."
    ),
    "prep_error_window_overlap": (
        "The two windows overlap or share an endpoint (left end {left_end:.4f} G "
        "≥ right start {right_start:.4f} G)."
    ),
    "prep_error_window_gap": (
        "At least {required} unselected data point(s) must remain between the "
        "windows; found {count}."
    ),
    "prep_error_degenerate": (
        "The field values in the windows have zero variance, so a straight "
        "line is undefined."
    ),
    "prep_error_fit_nonfinite": "The fit produced non-finite values; aborted.",
    "prep_error_source_changed": (
        "The source file changed after import (SHA-256 mismatch); exporting "
        "processed results was refused."
    ),
    "prep_error_preview_export": (
        "Preview results cannot be exported; apply the step first."
    ),
    "prep_error_no_steps": "No preprocessing steps have been applied.",
    "prep_error_no_pending": "There are no pending preview parameters to apply.",
    "prep_error_data_mismatch": (
        "The processed result does not match the imported data."
    ),
    "prep_error_savgol_window_even": (
        "window_length must be odd; got {window_length}."
    ),
    "prep_error_savgol_window_too_small": (
        "window_length must be at least 3; got {window_length}."
    ),
    "prep_error_savgol_window_too_large": (
        "window_length ({window_length}) exceeds the number of data points "
        "({n_points})."
    ),
    "prep_error_savgol_polyorder": (
        "polyorder must satisfy 0 <= polyorder < window_length "
        "(polyorder={polyorder}, window_length={window_length})."
    ),
    "prep_error_savgol_parameter": "Invalid Savitzky–Golay parameters.",
    "prep_error_savgol_unavailable": (
        "SciPy is not available, so Savitzky–Golay smoothing cannot run."
    ),
    "prep_error_savgol_failed": "Savitzky–Golay smoothing failed.",
    "prep_error_savgol_output_invalid": (
        "Savitzky–Golay smoothing returned an invalid array."
    ),
    "prep_error_savgol_input_source": "Invalid smoothing input source.",
    "prep_error_unsupported_operation": "Unsupported preprocessing operation.",
    # Preprocessing warnings
    "prep_warning_few_points": (
        "Window {start:.4f}–{end:.4f} G has only {count} point(s) (minimum "
        "{required}). This is a computational minimum, not evidence that the "
        "region is a valid baseline."
    ),
    "prep_warning_extrapolation": (
        "Large extrapolation beyond the windows: left {left:.4f} G, right "
        "{right:.4f} G (threshold {threshold:.4f} G)."
    ),
    "prep_warning_coverage_low": (
        "The baseline windows contain only {fraction:.2%} of the data points, "
        "which is very sparse."
    ),
    "prep_warning_coverage_high": (
        "The two windows together cover {fraction:.2%} of the field span and "
        "may include real signal."
    ),
    "prep_warning_noisy_window": (
        "A baseline window deviates strongly from the fitted line (residual "
        "RMS left {left_rms:.6g}, right {right_rms:.6g}; global noise estimate "
        "{noise:.6g}). That region may contain real signal rather than a pure "
        "baseline."
    ),
    "prep_warning_r2_undefined": (
        "Intensity is constant within the selected windows, so R-squared is "
        "undefined (the slope may be zero)."
    ),
    "prep_warning_smoothing_reorders": (
        "Smoothing was applied to the raw data before the {step_count} "
        "existing step(s); the processing order is now smoothing, then the "
        "existing steps. Existing steps keep their fitted parameters and are "
        "applied to the smoothed data."
    ),
    # File dialogs
    "dialog_select_asc": "Select ASC File",
    "asc_filter": "Xepr ASCII (*.asc *.ASC);;All Files (*.*)",
    "dialog_select_batch_dir": "Select a Folder Containing ASC Files",
    "dialog_select_output_dir": "Select Output Directory",
    # Dialogs and error messages
    "title_outputs_exist": "Outputs Already Exist",
    "msg_outputs_exist": (
        "{error}\n\nTo overwrite, enable “Allow Overwrite” and retry, "
        "or choose a different output directory."
    ),
    "title_write_failed": "Write Failed",
    "msg_write_failed": "Could not write the batch summary: {error}",
    "title_read_failed": "Read Failed",
    "msg_read_failed": "{name}\n{type}: {error}",
    "metadata_read_error": "Could not read {path}:\n{type}: {error}",
    "title_file_missing": "File Not Found",
    "no_samples": "No samples to display.",
    # Metadata panel
    "meta_file": "File: {path}",
    "meta_points": "Number of Data Points: {n}",
    "meta_field_range": "Magnetic Field Range: {low:.4f} – {high:.4f} G",
    "meta_field_direction": "Field Direction: {order}",
    "meta_signal": (
        "Signal Statistics: min {smin:.4f} | max {smax:.4f} | "
        "mean {mean:.4f} | std {std:.4f} (ddof=1)"
    ),
    "meta_warnings": "Validation Warnings:",
    "meta_warnings_none": "Validation Warnings: None",
    "meta_warnings_note": (
        "(Core validation messages are shown in their original English "
        "wording and are written unchanged to the JSON metadata.)"
    ),
    # Plot text
    "plot_xlabel": "Magnetic field (G)",
    "plot_ylabel": "Intensity (original units)",
    "plot_title": "{sample} - Raw CW-EPR Spectrum",
    # Batch summary
    "batch_counts": (
        "Found: {discovered} | Succeeded: {succeeded} | "
        "Warnings: {warnings} | Failed: {failed}"
    ),
    "batch_overall": "Overall status: {status}",
    "batch_summary_path": "Summary: {path}",
    # Per-file status
    "status_success": "Succeeded",
    "status_warnings": "Succeeded (with warnings)",
    "status_failed": "Failed",
    # Overall batch status
    "overall_success": "Success",
    "overall_success_with_warnings": "Success (with warnings)",
    "overall_partial_failure": "Partial failure",
    "overall_failed": "Failed",
    # Field direction (values emitted by plot_asc.read_asc)
    "field_order_increasing": "Strictly increasing",
    "field_order_decreasing": "Strictly decreasing",
    "field_order_non_monotonic": "Non-monotonic",
    "field_order_unknown": "Unknown",
}

TRANSLATIONS: dict[str, dict[str, str]] = {"zh": _ZH, "en": _EN}

_STATUS_KEYS = {
    "success": "status_success",
    "success_with_warnings": "status_warnings",
    "failed": "status_failed",
}

_OVERALL_STATUS_KEYS = {
    "success": "overall_success",
    "success_with_warnings": "overall_success_with_warnings",
    "partial_failure": "overall_partial_failure",
    "failed": "overall_failed",
}

_FIELD_ORDER_KEYS = {
    "strictly increasing": "field_order_increasing",
    "strictly decreasing": "field_order_decreasing",
    "non-monotonic": "field_order_non_monotonic",
    "unknown": "field_order_unknown",
}


def normalize_language(lang: Any) -> str:
    """Return a supported language code, defaulting to Simplified Chinese."""
    return lang if isinstance(lang, str) and lang in TRANSLATIONS else DEFAULT_LANGUAGE


def tr_text(key: str, lang: str | None = DEFAULT_LANGUAGE, **fmt: Any) -> str:
    """Look up ``key`` in the catalog for ``lang`` and format it.

    Fallbacks, in order: the requested language, Simplified Chinese, the key
    itself. If formatting placeholders do not match, the unformatted template
    is returned rather than raising.
    """
    catalog = TRANSLATIONS[normalize_language(lang)]
    template = catalog.get(key)
    if template is None:
        template = _ZH.get(key, key)
    if not fmt:
        return template
    try:
        return template.format(**fmt)
    except (KeyError, IndexError, ValueError):
        return template


def has_text(key: str, lang: str | None = DEFAULT_LANGUAGE) -> bool:
    """Return whether ``key`` exists in the catalog for ``lang``."""
    return key in TRANSLATIONS[normalize_language(lang)]


def status_text(status: str, lang: str | None = DEFAULT_LANGUAGE) -> str:
    """Translate a per-file batch status; unknown values are returned as-is."""
    key = _STATUS_KEYS.get(status)
    return tr_text(key, lang) if key else status


def overall_status_text(status: str, lang: str | None = DEFAULT_LANGUAGE) -> str:
    """Translate an overall batch status; unknown values are returned as-is."""
    key = _OVERALL_STATUS_KEYS.get(status)
    return tr_text(key, lang) if key else status


def field_order_text(field_order: str, lang: str | None = DEFAULT_LANGUAGE) -> str:
    """Translate a ``field_order`` value from ``read_asc`` for display."""
    key = _FIELD_ORDER_KEYS.get(field_order)
    return tr_text(key, lang) if key else field_order
