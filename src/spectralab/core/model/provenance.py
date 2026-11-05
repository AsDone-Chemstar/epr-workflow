"""Source-file and provenance records for Spectrum1D."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from spectralab.core.errors import SpectrumModelError
from spectralab.core.model.values import (
    freeze_mapping,
    optional_text,
    required_text,
)


@dataclass(frozen=True)
class SourceFile:
    """One source file participating in a dataset.

    A source hash may be empty to mean that it was not recorded; this is
    different from inventing a hash. ``size_bytes=None`` means unknown size.
    """

    role: str
    path: Path
    sha256: str = ""
    size_bytes: int | None = None
    format_id: str = "unknown"

    def __post_init__(self) -> None:
        role = required_text(
            self.role,
            field="source_file.role",
            error_cls=SpectrumModelError,
        )
        format_id = required_text(
            self.format_id,
            field="source_file.format_id",
            error_cls=SpectrumModelError,
        )
        if not isinstance(self.sha256, str):
            raise SpectrumModelError(
                "source_file.sha256 must be text (empty means unknown).",
                code="source_hash",
            )
        if self.size_bytes is not None:
            if isinstance(self.size_bytes, bool) or not isinstance(
                self.size_bytes, int
            ):
                raise SpectrumModelError(
                    "source_file.size_bytes must be an integer or None.",
                    code="source_size",
                )
            if self.size_bytes < 0:
                raise SpectrumModelError(
                    "source_file.size_bytes must not be negative.",
                    code="source_size",
                )
        try:
            path = Path(self.path)
        except (TypeError, ValueError) as exc:
            raise SpectrumModelError(
                "source_file.path must be a filesystem path.",
                code="source_path",
            ) from exc
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "format_id", format_id)
        object.__setattr__(self, "path", path)


@dataclass(frozen=True)
class Provenance:
    """How a Spectrum1D was obtained and what remains unknown.

    Optional fields deliberately use ``None``/empty collections rather than
    default units, hashes or timestamps. The adapter fills only values that
    are actually present in the legacy import result.
    """

    source_files: tuple[SourceFile, ...] = ()
    canonical_sha256: str | None = None
    sha256_definition: str | None = None
    file_size_bytes: int | None = None
    warnings: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    format_metadata: Mapping[str, Any] = field(default_factory=dict)
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    software_versions: Mapping[str, str] = field(default_factory=dict)
    importer_id: str = "unknown"
    importer_version: str = "unknown"
    imported_at_utc: str | None = None

    def __post_init__(self) -> None:
        source_files = tuple(self.source_files)
        if any(not isinstance(item, SourceFile) for item in source_files):
            raise SpectrumModelError(
                "provenance.source_files must contain SourceFile objects.",
                code="source_files",
            )
        object.__setattr__(self, "source_files", source_files)

        canonical = optional_text(
            self.canonical_sha256,
            field="provenance.canonical_sha256",
            error_cls=SpectrumModelError,
        )
        definition = optional_text(
            self.sha256_definition,
            field="provenance.sha256_definition",
            error_cls=SpectrumModelError,
        )
        imported_at = optional_text(
            self.imported_at_utc,
            field="provenance.imported_at_utc",
            error_cls=SpectrumModelError,
        )
        object.__setattr__(self, "canonical_sha256", canonical)
        object.__setattr__(self, "sha256_definition", definition)
        object.__setattr__(self, "imported_at_utc", imported_at)

        if self.file_size_bytes is not None:
            if isinstance(self.file_size_bytes, bool) or not isinstance(
                self.file_size_bytes, int
            ):
                raise SpectrumModelError(
                    "provenance.file_size_bytes must be an integer or None.",
                    code="file_size",
                )
            if self.file_size_bytes < 0:
                raise SpectrumModelError(
                    "provenance.file_size_bytes must not be negative.",
                    code="file_size",
                )

        for name in ("warnings", "assumptions"):
            values = tuple(getattr(self, name))
            if any(not isinstance(item, str) for item in values):
                raise SpectrumModelError(
                    f"provenance.{name} must contain text.",
                    code=name,
                )
            object.__setattr__(self, name, values)

        for name in ("format_metadata", "diagnostics", "software_versions"):
            object.__setattr__(
                self,
                name,
                freeze_mapping(
                    getattr(self, name),
                    field=f"provenance.{name}",
                    error_cls=SpectrumModelError,
                ),
            )

        importer_id = required_text(
            self.importer_id,
            field="provenance.importer_id",
            error_cls=SpectrumModelError,
        )
        importer_version = required_text(
            self.importer_version,
            field="provenance.importer_version",
            error_cls=SpectrumModelError,
        )
        object.__setattr__(self, "importer_id", importer_id)
        object.__setattr__(self, "importer_version", importer_version)


__all__ = ["Provenance", "SourceFile"]
