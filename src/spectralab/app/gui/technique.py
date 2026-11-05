"""Technique descriptors, panel protocol and explicit registry."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class TechniqueRegistryError(ValueError):
    """A technique registration or lookup failed."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "technique_registry",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


@runtime_checkable
class TechniquePanelProtocol(Protocol):
    """Stable interface implemented by technique panels.

    ``spectrum_changed`` emits Spectrum1D/ProcessedSpectrum and
    ``status_event`` emits a status payload understood by the shell.
    """

    spectrum_changed: Any
    status_event: Any

    def open_file(self, path: Path) -> bool:
        """Load one file and return whether it succeeded."""

    def retranslate(self) -> None:
        """Refresh all user-visible text for the current language."""

    def current_display(self) -> Any:
        """Return the currently displayed Spectrum1D/ProcessedSpectrum."""


@dataclass(frozen=True)
class TechniqueDescriptor:
    """One explicitly registered technique and its GUI panel factory."""

    id: str
    display_name_key: str
    panel_factory: Callable[[Any, Any], Any]
    file_patterns: tuple[str, ...]
    translations: Mapping[str, Mapping[str, str]]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise TechniqueRegistryError(
                "Technique id must be non-empty text.",
                code="invalid_technique",
            )
        if not isinstance(self.display_name_key, str) or not self.display_name_key.strip():
            raise TechniqueRegistryError(
                "Technique display_name_key must be non-empty text.",
                code="invalid_technique",
            )
        if not callable(self.panel_factory):
            raise TechniqueRegistryError(
                "Technique panel_factory must be callable.",
                code="invalid_technique",
            )
        if not isinstance(self.file_patterns, tuple) or not self.file_patterns:
            raise TechniqueRegistryError(
                "Technique file_patterns must be a non-empty tuple.",
                code="invalid_technique",
            )
        for pattern in self.file_patterns:
            if not isinstance(pattern, str) or not pattern.startswith("*."):
                raise TechniqueRegistryError(
                    "Technique file patterns must start with '*.'.",
                    code="invalid_technique",
                    context={"pattern": pattern},
                )
        if not isinstance(self.translations, Mapping):
            raise TechniqueRegistryError(
                "Technique translations must be a mapping.",
                code="invalid_technique",
            )

    @property
    def file_filter_patterns(self) -> str:
        return " ".join(self.file_patterns)


class TechniqueRegistry:
    """Ordered, explicit registry of GUI techniques."""

    def __init__(self) -> None:
        self._techniques: dict[str, TechniqueDescriptor] = {}
        self._active_id: str | None = None

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(self._techniques)

    @property
    def descriptors(self) -> tuple[TechniqueDescriptor, ...]:
        return tuple(self._techniques.values())

    @property
    def techniques(self) -> tuple[TechniqueDescriptor, ...]:
        """Alias for descriptors used by callers that list techniques."""
        return self.descriptors

    def __len__(self) -> int:
        return len(self._techniques)

    def __contains__(self, technique_id: object) -> bool:
        return technique_id in self._techniques

    @property
    def active_id(self) -> str | None:
        return self._active_id

    @property
    def active(self) -> TechniqueDescriptor | None:
        return (
            self._techniques.get(self._active_id)
            if self._active_id is not None
            else None
        )

    def register(
        self,
        descriptor: TechniqueDescriptor,
        *,
        replace: bool = False,
    ) -> None:
        if not isinstance(descriptor, TechniqueDescriptor):
            raise TechniqueRegistryError(
                "register() requires a TechniqueDescriptor.",
                code="invalid_technique",
            )
        if descriptor.id in self._techniques and not replace:
            raise TechniqueRegistryError(
                f"Technique {descriptor.id!r} is already registered.",
                code="duplicate_technique",
                context={"technique_id": descriptor.id},
            )
        self._techniques[descriptor.id] = descriptor
        if self._active_id is None:
            self._active_id = descriptor.id

    def get(self, technique_id: str) -> TechniqueDescriptor:
        try:
            return self._techniques[technique_id]
        except KeyError as exc:
            raise TechniqueRegistryError(
                f"Unknown technique: {technique_id!r}",
                code="unknown_technique",
                context={"technique_id": technique_id},
            ) from exc

    def select(self, technique_id: str) -> TechniqueDescriptor:
        descriptor = self.get(technique_id)
        self._active_id = descriptor.id
        return descriptor


__all__ = [
    "TechniqueDescriptor",
    "TechniquePanelProtocol",
    "TechniqueRegistry",
    "TechniqueRegistryError",
]
