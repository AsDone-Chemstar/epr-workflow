"""Qt-free translation service for the SpectraLab GUI shell."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DEFAULT_LANGUAGE = "zh"
LANGUAGES: dict[str, str] = {
    "zh": "简体中文",
    "en": "English",
}


class TranslationError(ValueError):
    """A translation catalog is malformed or conflicts with another catalog."""


_ZH: dict[str, str] = {
    "app.title": "SpectraLab — 光谱工作台",
    "app.technique": "技术",
    "app.open_file": "打开光谱…",
    "app.language": "语言",
    "app.metadata": "元数据",
    "app.status_ready": "就绪",
    "app.no_technique": "没有注册任何技术。",
    "app.no_panel": "当前技术没有可用的面板。",
    "app.panel_invalid": "技术面板没有实现所需接口。",
    "app.open_failed": "无法打开文件：{error}",
    "app.unknown": "未知",
    "app.none": "无",
    "app.all_files": "所有文件",
    "app.data_files": "数据文件",
    "app.open_dialog_title": "打开光谱文件",
    "app.metadata_empty": "尚未加载光谱。",
    "status.success": "成功",
    "status.info": "信息",
    "status.warning": "警告",
    "status.error": "错误",
    "meta.kind": "显示类型：{kind}",
    "meta.kind_raw": "原始 Spectrum1D",
    "meta.kind_processed": "ProcessedSpectrum（含处理历史）",
    "meta.technique": "技术：{value}",
    "meta.dataset_id": "数据集：{value}",
    "meta.points": "点数：{value}",
    "meta.axis": "X 轴",
    "meta.signal": "Y 信号",
    "meta.axis_quantity": "  物理量：{value}",
    "meta.axis_unit": "  单位：{value}",
    "meta.axis_name": "  名称：{value}",
    "meta.axis_direction": "  方向：{value}",
    "meta.axis_source": "  元数据来源：{value}",
    "meta.signal_semantics": "  语义：{value}",
    "meta.signal_unit": "  单位：{value}",
    "meta.signal_name": "  名称：{value}",
    "meta.signal_source": "  元数据来源：{value}",
    "meta.source_format": "来源格式：{value}",
    "meta.title_field": "标题：{value}",
    "meta.instrument": "仪器：{value}",
    "meta.acquisition": "采集：{value}",
    "meta.sample": "样品：{value}",
    "meta.technique_metadata": "技术元数据：{value}",
    "meta.extra": "其他元数据：{value}",
    "meta.unknown_fields": "显式未知字段：{value}",
    "meta.metadata_origin": "元数据来源：{value}",
    "meta.source_files": "源文件：",
    "meta.source_none": "  无记录",
    "meta.source_file": "  [{role}] {path}",
    "meta.source_details": "    格式={format_id}，大小={size}，SHA-256={sha}",
    "meta.import_options": "导入选项：{value}",
    "meta.warnings": "导入警告：{value}",
    "meta.assumptions": "导入假设：{value}",
    "meta.processing_history": "处理历史：{count} 步",
    "meta.processing_none": "处理历史：无",
    "meta.operation": "  {order}. {operation_id}（{technique} {version}）",
    "meta.operation_parameters": "    参数：{value}",
    "meta.operation_warnings": "    警告：{value}",
    "meta.operation_assumptions": "    假设：{value}",
    "meta.operation_diagnostics": "    诊断：{value}",
}

_EN: dict[str, str] = {
    "app.title": "SpectraLab — Spectroscopy Workbench",
    "app.technique": "Technique",
    "app.open_file": "Open Spectrum…",
    "app.language": "Language",
    "app.metadata": "Metadata",
    "app.status_ready": "Ready",
    "app.no_technique": "No technique is registered.",
    "app.no_panel": "The active technique has no available panel.",
    "app.panel_invalid": "The technique panel does not implement the required interface.",
    "app.open_failed": "Could not open file: {error}",
    "app.unknown": "unknown",
    "app.none": "none",
    "app.all_files": "All files",
    "app.data_files": "Data files",
    "app.open_dialog_title": "Open spectrum file",
    "app.metadata_empty": "No spectrum loaded.",
    "status.success": "Success",
    "status.info": "Info",
    "status.warning": "Warning",
    "status.error": "Error",
    "meta.kind": "Display type: {kind}",
    "meta.kind_raw": "Raw Spectrum1D",
    "meta.kind_processed": "ProcessedSpectrum (with processing history)",
    "meta.technique": "Technique: {value}",
    "meta.dataset_id": "Dataset: {value}",
    "meta.points": "Points: {value}",
    "meta.axis": "X axis",
    "meta.signal": "Y signal",
    "meta.axis_quantity": "  Quantity: {value}",
    "meta.axis_unit": "  Unit: {value}",
    "meta.axis_name": "  Name: {value}",
    "meta.axis_direction": "  Direction: {value}",
    "meta.axis_source": "  Metadata source: {value}",
    "meta.signal_semantics": "  Semantics: {value}",
    "meta.signal_unit": "  Unit: {value}",
    "meta.signal_name": "  Name: {value}",
    "meta.signal_source": "  Metadata source: {value}",
    "meta.source_format": "Source format: {value}",
    "meta.title_field": "Title: {value}",
    "meta.instrument": "Instrument: {value}",
    "meta.acquisition": "Acquisition: {value}",
    "meta.sample": "Sample: {value}",
    "meta.technique_metadata": "Technique metadata: {value}",
    "meta.extra": "Extra metadata: {value}",
    "meta.unknown_fields": "Explicit unknown fields: {value}",
    "meta.metadata_origin": "Metadata origin: {value}",
    "meta.source_files": "Source files:",
    "meta.source_none": "  none recorded",
    "meta.source_file": "  [{role}] {path}",
    "meta.source_details": "    format={format_id}, size={size}, SHA-256={sha}",
    "meta.import_options": "Import options: {value}",
    "meta.warnings": "Import warnings: {value}",
    "meta.assumptions": "Import assumptions: {value}",
    "meta.processing_history": "Processing history: {count} step(s)",
    "meta.processing_none": "Processing history: none",
    "meta.operation": "  {order}. {operation_id} ({technique} {version})",
    "meta.operation_parameters": "    Parameters: {value}",
    "meta.operation_warnings": "    Warnings: {value}",
    "meta.operation_assumptions": "    Assumptions: {value}",
    "meta.operation_diagnostics": "    Diagnostics: {value}",
}

_BASE_CATALOGS = {"zh": _ZH, "en": _EN}


def normalize_language(language: Any) -> str:
    """Return a supported language code, falling back to Simplified Chinese."""
    if isinstance(language, str) and language in LANGUAGES:
        return language
    return DEFAULT_LANGUAGE


class Translator:
    """Central translation service with deterministic fallback.

    Lookup order: requested language, default language (``zh``), then the key.
    Formatting errors return the unformatted template rather than raising.
    """

    def __init__(self, language: str = DEFAULT_LANGUAGE) -> None:
        self._language = normalize_language(language)
        self._catalogs: dict[str, dict[str, str]] = {
            code: dict(catalog) for code, catalog in _BASE_CATALOGS.items()
        }

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        self._language = normalize_language(language)

    def register_catalog(
        self,
        translations: Mapping[str, Mapping[str, str]],
        *,
        source: str = "technique",
    ) -> None:
        """Merge one technique catalog, rejecting conflicting duplicate keys."""
        if not isinstance(translations, Mapping):
            raise TranslationError(f"{source} translations must be a mapping.")
        for language, catalog in translations.items():
            if language not in LANGUAGES:
                raise TranslationError(
                    f"{source} uses unsupported language {language!r}."
                )
            code = normalize_language(language)
            if not isinstance(catalog, Mapping):
                raise TranslationError(
                    f"{source} translations for {language!r} must be a mapping."
                )
            target = self._catalogs.setdefault(code, {})
            for key, value in catalog.items():
                if not isinstance(key, str) or not key:
                    raise TranslationError(
                        f"{source} translation keys must be non-empty text."
                    )
                if not isinstance(value, str) or not value.strip():
                    raise TranslationError(
                        f"{source} translation {key!r} must be non-empty text."
                    )
                existing = target.get(key)
                if existing is not None and existing != value:
                    raise TranslationError(
                        f"Conflicting translation for key {key!r} in {source}."
                    )
                target[key] = value

    def has(self, key: str) -> bool:
        return any(key in catalog for catalog in self._catalogs.values())

    def tr(self, key: str, **params: Any) -> str:
        template = None
        catalog = self._catalogs.get(self._language, {})
        if key in catalog:
            template = catalog[key]
        else:
            fallback = self._catalogs.get(DEFAULT_LANGUAGE, {})
            template = fallback.get(key, key)
        try:
            return template.format(**params)
        except (KeyError, ValueError, IndexError):
            return template


__all__ = [
    "DEFAULT_LANGUAGE",
    "LANGUAGES",
    "TranslationError",
    "Translator",
    "normalize_language",
]
