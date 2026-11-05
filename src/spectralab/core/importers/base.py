"""Technique-independent importer protocol and request/result containers.

The core only defines the contract. Concrete parsers live in technique
modules and are registered explicitly by a higher integration layer. No
importer is discovered or imported automatically.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from spectralab.core.errors import ImportFailure
from spectralab.core.model import SourceFile, Spectrum1D

_FORMAT = "import_request"


@dataclass(frozen=True)
class ProbeResult:
    """Cheap, read-only assessment of whether an importer can read an entry.

    ``confidence`` is descriptive only. The registry never uses it to break a
    tie: ambiguous matches require an explicit technique or format choice.
    """

    supported: bool
    confidence: float
    format_id: str
    technique: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.supported, bool):
            raise ImportFailure(
                "ProbeResult.supported must be a boolean.",
                code="invalid_probe_result",
                context={"field": "supported"},
            )
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not 0.0 <= float(self.confidence) <= 1.0
        ):
            raise ImportFailure(
                "ProbeResult.confidence must be a number from 0 to 1.",
                code="invalid_probe_result",
                context={"field": "confidence", "value": self.confidence},
            )
        if not isinstance(self.format_id, str) or not self.format_id.strip():
            raise ImportFailure(
                "ProbeResult.format_id must be non-empty text.",
                code="invalid_probe_result",
                context={"field": "format_id"},
            )
        if self.technique is not None and (
            not isinstance(self.technique, str) or not self.technique.strip()
        ):
            raise ImportFailure(
                "ProbeResult.technique must be non-empty text or None.",
                code="invalid_probe_result",
                context={"field": "technique"},
            )
        if self.reason is not None and not isinstance(self.reason, str):
            raise ImportFailure(
                "ProbeResult.reason must be text or None.",
                code="invalid_probe_result",
                context={"field": "reason"},
            )


@dataclass(frozen=True)
class ImportRequest:
    """One explicit request to read a dataset entry.

    ``companions`` and ``options`` are part of the forward-looking protocol.
    The M2 EPR importers reject non-empty values rather than silently ignoring
    them. ``allow_ambiguous`` is reserved; the registry still refuses an
    ambiguous selection instead of choosing by confidence.
    """

    entry: Path
    companions: Mapping[str, Path] = field(default_factory=dict)
    technique_hint: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)
    allow_ambiguous: bool = False

    def __post_init__(self) -> None:
        try:
            entry = Path(self.entry)
        except (TypeError, ValueError) as exc:
            raise ImportFailure(
                "ImportRequest.entry must be a filesystem path.",
                code=_FORMAT,
                context={"field": "entry"},
            ) from exc
        object.__setattr__(self, "entry", entry)

        companions = self.companions
        if not isinstance(companions, Mapping):
            raise ImportFailure(
                "ImportRequest.companions must be a mapping.",
                code=_FORMAT,
                context={"field": "companions"},
            )
        converted: dict[str, Path] = {}
        for role, path in companions.items():
            if not isinstance(role, str) or not role:
                raise ImportFailure(
                    "ImportRequest.companions keys must be non-empty text.",
                    code=_FORMAT,
                    context={"field": "companions"},
                )
            try:
                converted[role] = Path(path)
            except (TypeError, ValueError) as exc:
                raise ImportFailure(
                    "ImportRequest.companions values must be paths.",
                    code=_FORMAT,
                    context={"field": "companions", "role": role},
                ) from exc
        object.__setattr__(self, "companions", MappingProxyType(converted))

        if self.technique_hint is not None and (
            not isinstance(self.technique_hint, str)
            or not self.technique_hint.strip()
        ):
            raise ImportFailure(
                "ImportRequest.technique_hint must be non-empty text or None.",
                code=_FORMAT,
                context={"field": "technique_hint"},
            )

        if not isinstance(self.options, Mapping):
            raise ImportFailure(
                "ImportRequest.options must be a mapping.",
                code=_FORMAT,
                context={"field": "options"},
            )
        object.__setattr__(
            self,
            "options",
            MappingProxyType(dict(self.options)),
        )

        if not isinstance(self.allow_ambiguous, bool):
            raise ImportFailure(
                "ImportRequest.allow_ambiguous must be a boolean.",
                code=_FORMAT,
                context={"field": "allow_ambiguous"},
            )


@dataclass(frozen=True)
class ImportedDataset:
    """A successful import result containing one or more spectra."""

    spectra: tuple[Spectrum1D, ...]
    primary_index: int
    format_id: str
    technique: str
    warnings: tuple[str, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        spectra = tuple(self.spectra)
        if not spectra:
            raise ImportFailure(
                "ImportedDataset.spectra must contain at least one spectrum.",
                code="invalid_import_result",
                context={"field": "spectra"},
            )
        if any(not isinstance(item, Spectrum1D) for item in spectra):
            raise ImportFailure(
                "ImportedDataset.spectra must contain Spectrum1D objects.",
                code="invalid_import_result",
                context={"field": "spectra"},
            )
        object.__setattr__(self, "spectra", spectra)

        if isinstance(self.primary_index, bool) or not isinstance(
            self.primary_index, int
        ):
            raise ImportFailure(
                "ImportedDataset.primary_index must be an integer.",
                code="invalid_import_result",
                context={"field": "primary_index"},
            )
        if not 0 <= self.primary_index < len(spectra):
            raise ImportFailure(
                "ImportedDataset.primary_index is outside the spectra tuple.",
                code="invalid_import_result",
                context={
                    "field": "primary_index",
                    "primary_index": self.primary_index,
                    "count": len(spectra),
                },
            )

        for field_name in ("format_id", "technique"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ImportFailure(
                    f"ImportedDataset.{field_name} must be non-empty text.",
                    code="invalid_import_result",
                    context={"field": field_name},
                )

        warnings = tuple(self.warnings)
        if any(not isinstance(item, str) for item in warnings):
            raise ImportFailure(
                "ImportedDataset.warnings must contain text.",
                code="invalid_import_result",
                context={"field": "warnings"},
            )
        object.__setattr__(self, "warnings", warnings)

        if not isinstance(self.diagnostics, Mapping):
            raise ImportFailure(
                "ImportedDataset.diagnostics must be a mapping.",
                code="invalid_import_result",
                context={"field": "diagnostics"},
            )
        object.__setattr__(
            self,
            "diagnostics",
            MappingProxyType(dict(self.diagnostics)),
        )

    @property
    def primary(self) -> Spectrum1D:
        return self.spectra[self.primary_index]


@runtime_checkable
class Importer(Protocol):
    """Structural interface implemented by every concrete importer."""

    id: str
    version: str
    technique: str
    entry_suffixes: tuple[str, ...]

    def probe(self, entry: Path) -> ProbeResult:
        """Return a cheap content-based assessment without importing data."""

    def collect_sources(self, entry: Path) -> tuple[SourceFile, ...]:
        """Return every source file participating in the dataset."""

    def read(self, request: ImportRequest) -> ImportedDataset:
        """Read exactly this importer's format and return a complete dataset."""


__all__ = [
    "ImportedDataset",
    "ImportRequest",
    "Importer",
    "ProbeResult",
]
