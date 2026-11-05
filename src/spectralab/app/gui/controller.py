"""Qt-free controller for the SpectraLab GUI shell."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spectralab.app.gui.technique import (
    TechniqueDescriptor,
    TechniqueRegistry,
)
from spectralab.app.registry import build_importer_registry
from spectralab.core.importers import ImporterRegistry


class ControllerError(ValueError):
    """A GUI-facing import or technique operation failed."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "gui_controller",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


@dataclass(frozen=True)
class LoadedSpectrum:
    """One imported dataset plus its primary Spectrum1D."""

    dataset: Any
    spectrum: Any
    path: Path


class ApplicationController:
    """GUI-independent application state and import service."""

    def __init__(
        self,
        techniques: TechniqueRegistry,
        *,
        importers: ImporterRegistry | None = None,
    ) -> None:
        if not isinstance(techniques, TechniqueRegistry):
            raise ControllerError(
                "ApplicationController requires a TechniqueRegistry.",
                code="invalid_technique_registry",
            )
        self._techniques = techniques
        self._importers = importers or build_importer_registry()

    @property
    def techniques(self) -> TechniqueRegistry:
        return self._techniques

    @property
    def active_technique(self) -> TechniqueDescriptor | None:
        return self._techniques.active

    def select_technique(self, technique_id: str) -> TechniqueDescriptor:
        return self._techniques.select(technique_id)

    def load_spectrum(
        self,
        path: str | Path,
        *,
        format_id: str | None = None,
        technique_hint: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> LoadedSpectrum:
        """Load exactly one spectrum through the explicit importer registry.

        ``options`` is an importer-specific mapping passed through unchanged;
        the generic controller does not interpret or default it.
        """
        source = Path(path)
        dataset = self._importers.read(
            source,
            format_id=format_id,
            technique=technique_hint,
            options=options,
        )
        if len(dataset.spectra) != 1:
            raise ControllerError(
                "The GUI currently supports exactly one Spectrum1D per input.",
                code="multiple_spectra_unsupported",
                context={"count": len(dataset.spectra)},
            )
        return LoadedSpectrum(
            dataset=dataset,
            spectrum=dataset.primary,
            path=source,
        )


__all__ = ["ApplicationController", "ControllerError", "LoadedSpectrum"]
