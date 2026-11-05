"""Technique and acquisition metadata for Spectrum1D."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from spectralab.core.errors import SpectrumModelError
from spectralab.core.model.values import (
    freeze_mapping,
    optional_text,
    required_text,
)


@dataclass(frozen=True)
class SpectrumMetadata:
    """Descriptive metadata; unknown values remain ``None`` or empty.

    Mappings are stored as shallow read-only mapping proxies. Nested values are
    not deep-frozen; callers should treat them as read-only provenance data.

    ``technique_metadata`` is the extension point for technique-specific
    metadata (for example FTIR acquisition mode or ATR correction status). The
    core model does not interpret those keys.
    """

    technique: str
    title: str | None = None
    instrument: Mapping[str, Any] = field(default_factory=dict)
    acquisition: Mapping[str, Any] = field(default_factory=dict)
    sample: Mapping[str, Any] = field(default_factory=dict)
    technique_metadata: Mapping[str, Any] = field(default_factory=dict)
    extra: Mapping[str, Any] = field(default_factory=dict)
    unknown_fields: tuple[str, ...] = ()
    metadata_origin: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        technique = required_text(
            self.technique,
            field="metadata.technique",
            error_cls=SpectrumModelError,
        )
        title = optional_text(
            self.title,
            field="metadata.title",
            error_cls=SpectrumModelError,
        )
        object.__setattr__(self, "technique", technique)
        object.__setattr__(self, "title", title)

        for name in (
            "instrument",
            "acquisition",
            "sample",
            "technique_metadata",
            "extra",
        ):
            object.__setattr__(
                self,
                name,
                freeze_mapping(
                    getattr(self, name),
                    field=f"metadata.{name}",
                    error_cls=SpectrumModelError,
                ),
            )

        unknown_fields = tuple(self.unknown_fields)
        if any(not isinstance(item, str) or not item for item in unknown_fields):
            raise SpectrumModelError(
                "metadata.unknown_fields must contain non-empty strings.",
                code="unknown_fields",
            )
        object.__setattr__(self, "unknown_fields", unknown_fields)

        origin = freeze_mapping(
            self.metadata_origin,
            field="metadata.metadata_origin",
            error_cls=SpectrumModelError,
        )
        if any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in origin.items()
        ):
            raise SpectrumModelError(
                "metadata.metadata_origin must map text keys to text values.",
                code="metadata_origin",
            )
        object.__setattr__(self, "metadata_origin", origin)


__all__ = ["SpectrumMetadata"]
