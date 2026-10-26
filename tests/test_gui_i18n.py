"""Tests for the bilingual UI catalog and lookup helpers (no Qt required)."""

from __future__ import annotations

import pytest

from epr_workflow.gui import i18n
from epr_workflow.gui.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    TRANSLATIONS,
    field_order_text,
    has_text,
    normalize_language,
    overall_status_text,
    status_text,
    tr_text,
)


def test_languages_and_default() -> None:
    assert LANGUAGES == {"zh": "简体中文", "en": "English"}
    assert DEFAULT_LANGUAGE == "zh"
    assert set(TRANSLATIONS) == {"zh", "en"}


def test_catalogs_have_identical_key_sets() -> None:
    assert set(TRANSLATIONS["zh"]) == set(TRANSLATIONS["en"])


def test_catalog_values_are_non_empty_strings() -> None:
    for language, catalog in TRANSLATIONS.items():
        for key, value in catalog.items():
            assert isinstance(value, str), (language, key)
            assert value.strip(), (language, key)


def test_representative_translations() -> None:
    assert tr_text("open_asc", "zh") == "打开单个 ASC 文件"
    assert tr_text("open_asc", "en") == "Open ASC File"
    assert tr_text("batch_process", "en") == "Batch Process Folder…"
    assert tr_text("sample_list", "en") == "Sample List"
    assert tr_text("output_directory", "en") == "Output Directory…"
    assert tr_text("allow_overwrite", "en") == "Allow Overwrite"
    assert tr_text("recursive_subdirs", "en") == "Include Subdirectories"
    assert tr_text("open_csv", "en") == "Open CSV"


def test_formatting_in_both_languages() -> None:
    assert tr_text("meta_points", "zh", n=4) == "数据点数：4"
    assert tr_text("meta_points", "en", n=4) == "Number of Data Points: 4"
    assert tr_text(
        "meta_field_range", "en", low=3280.0, high=3380.0
    ) == "Magnetic Field Range: 3280.0000 – 3380.0000 G"
    english_counts = tr_text(
        "batch_counts", "en", discovered=3, succeeded=2, warnings=1, failed=0
    )
    assert english_counts == "Found: 3 | Succeeded: 2 | Warnings: 1 | Failed: 0"
    chinese_counts = tr_text(
        "batch_counts", "zh", discovered=3, succeeded=2, warnings=1, failed=0
    )
    assert chinese_counts == "发现 3 | 成功 2 | 有警告 1 | 失败 0"


def test_unknown_key_returns_key() -> None:
    assert tr_text("__no_such_key__", "en") == "__no_such_key__"
    assert tr_text("__no_such_key__", "zh") == "__no_such_key__"


def test_missing_english_key_falls_back_to_chinese(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reduced = {
        key: value
        for key, value in i18n.TRANSLATIONS["en"].items()
        if key != "open_asc"
    }
    monkeypatch.setitem(i18n.TRANSLATIONS, "en", reduced)

    assert tr_text("open_asc", "en") == i18n.TRANSLATIONS["zh"]["open_asc"]


def test_unknown_language_falls_back_to_chinese() -> None:
    assert normalize_language("fr") == "zh"
    assert normalize_language(None) == "zh"
    assert normalize_language(123) == "zh"
    assert normalize_language("en") == "en"
    assert tr_text("open_asc", "fr") == tr_text("open_asc", "zh")


def test_invalid_format_arguments_return_template() -> None:
    assert tr_text("meta_points", "en", wrong=1) == TRANSLATIONS["en"]["meta_points"]
    assert tr_text("meta_points", "zh", wrong=1) == TRANSLATIONS["zh"]["meta_points"]


def test_status_text() -> None:
    assert status_text("success", "zh") == "成功"
    assert status_text("success_with_warnings", "zh") == "成功（有警告）"
    assert status_text("failed", "zh") == "失败"
    assert status_text("success", "en") == "Succeeded"
    assert status_text("success_with_warnings", "en") == "Succeeded (with warnings)"
    assert status_text("failed", "en") == "Failed"
    assert status_text("something_else", "en") == "something_else"


def test_overall_status_text() -> None:
    assert overall_status_text("success", "zh") == "成功"
    assert overall_status_text("partial_failure", "zh") == "部分失败"
    assert overall_status_text("success", "en") == "Success"
    assert overall_status_text("success_with_warnings", "en") == "Success (with warnings)"
    assert overall_status_text("partial_failure", "en") == "Partial failure"
    assert overall_status_text("failed", "en") == "Failed"
    assert overall_status_text("unknown_value", "en") == "unknown_value"


def test_field_order_text() -> None:
    assert field_order_text("strictly increasing", "zh") == "严格递增"
    assert field_order_text("strictly decreasing", "zh") == "严格递减"
    assert field_order_text("non-monotonic", "zh") == "非单调"
    assert field_order_text("strictly increasing", "en") == "Strictly increasing"
    assert field_order_text("unknown", "en") == "Unknown"
    assert field_order_text("some new value", "en") == "some new value"


def test_has_text() -> None:
    assert has_text("prep_group", "zh") is True
    assert has_text("prep_group", "en") is True
    assert has_text("prep_error_window_overlap", "en") is True
    assert has_text("prep_warning_noisy_window", "zh") is True
    assert has_text("__no_such_key__", "en") is False
    assert has_text("__no_such_key__", "fr") is False


def test_preprocessing_translations_and_formatting() -> None:
    assert tr_text("prep_group", "zh") == "预处理"
    assert tr_text("prep_group", "en") == "Preprocessing"
    assert tr_text("prep_export", "en") == "Export Processed Results…"
    assert tr_text("prep_cancel_preview", "zh") == "取消预览"
    assert tr_text("prep_cancel_preview", "en") == "Cancel Preview"
    assert tr_text("prep_method_savgol", "zh") == "Savitzky–Golay 平滑"
    assert tr_text("prep_method_savgol", "en") == "Savitzky–Golay smoothing"
    assert tr_text("prep_window_length", "en") == "Window length"
    assert tr_text("prep_input_raw", "zh") == "原始数据"
    assert "请先选择基线区间" in tr_text("prep_error_windows_unset", "zh")
    assert "Select baseline windows first" in tr_text(
        "prep_error_windows_unset", "en"
    )

    zh_savgol_error = tr_text(
        "prep_error_savgol_window_even", "zh", window_length=4
    )
    assert "窗口长度必须为奇数：4" in zh_savgol_error
    en_savgol_error = tr_text(
        "prep_error_savgol_window_even", "en", window_length=4
    )
    assert "window_length must be odd; got 4" in en_savgol_error
    assert "先平滑、后原有步骤" in tr_text(
        "prep_warning_smoothing_reorders", "zh", step_count=2
    )
    assert tr_text("prep_status_applied", "zh", n=2) == "状态：已应用 2 步"
    assert tr_text("prep_status_applied", "en", n=2) == "Status: 2 step(s) applied"

    zh_error = tr_text(
        "prep_error_window_points",
        "zh",
        start=3280.0,
        end=3280.5,
        count=2,
        required=3,
    )
    assert "只包含 2 个数据点" in zh_error
    assert "至少需要 3 个" in zh_error
    assert "不代表基线区域可靠" in zh_error

    en_error = tr_text(
        "prep_error_window_points",
        "en",
        start=3280.0,
        end=3280.5,
        count=2,
        required=3,
    )
    assert "contains only 2 data point(s)" in en_error
    assert "does not establish that the baseline region is reliable" in en_error

    zh_warning = tr_text(
        "prep_warning_few_points",
        "zh",
        start=3280.0,
        end=3282.0,
        count=3,
        required=3,
    )
    assert "仅有 3 个点" in zh_warning
    assert "不足以证明" in zh_warning
