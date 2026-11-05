"""Explicit importer registry and format dispatch.

The registry never imports technique packages, discovers plugins or retries a
different importer after a failed read. Extensions only narrow the candidate
set; a content-based ``probe`` must still support the entry.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from spectralab.core.errors import (
    AmbiguousFormatError,
    ImportFailure,
    ImporterRegistrationError,
    UnsupportedFormatError,
)
from spectralab.core.importers.base import (
    ImportedDataset,
    ImportRequest,
    Importer,
    ProbeResult,
)
from spectralab.core.importers.validation import entry_suffixes, validate_importer


class ImporterRegistry:
    """An ordered collection of explicitly registered importers."""

    def __init__(self) -> None:
        self._importers: dict[str, Importer] = {}

    @property
    def importers(self) -> tuple[Importer, ...]:
        return tuple(self._importers.values())

    def register(self, importer: Importer, *, replace: bool = False) -> None:
        """Register one importer by its stable ``id``.

        Duplicate IDs are rejected unless ``replace=True`` is explicitly
        supplied. Registering a different object under an existing ID is never
        silent.
        """
        validate_importer(importer)
        existing = self._importers.get(importer.id)
        if existing is not None and not replace:
            raise ImporterRegistrationError(
                f"An importer with id {importer.id!r} is already registered. "
                "Pass replace=True only when replacing it intentionally.",
                code="duplicate_importer_id",
                context={"importer_id": importer.id},
            )
        self._importers[importer.id] = importer

    def candidates(self, entry: str | Path) -> tuple[ProbeResult, ...]:
        """Return supported probe results for the entry.

        Files whose suffix is not declared by any importer are not probed.
        Probe failures are reported explicitly rather than converted into a
        silent "unsupported" result.
        """
        probes = self._probe(entry)
        return tuple(result for _importer, result in probes if result.supported)

    def select(
        self,
        entry: str | Path,
        *,
        technique: str | None = None,
        format_id: str | None = None,
    ) -> Importer:
        """Select exactly one importer, or raise a stable coded error."""
        probes = self._probe(entry)
        supported = [
            (importer, result)
            for importer, result in probes
            if result.supported
        ]

        if technique is not None:
            supported = [
                (importer, result)
                for importer, result in supported
                if (result.technique or importer.technique) == technique
            ]
        if format_id is not None:
            supported = [
                (importer, result)
                for importer, result in supported
                if result.format_id == format_id
            ]

        path = Path(entry)
        if not supported:
            available = sorted(
                {
                    (
                        result.technique or importer.technique,
                        result.format_id,
                    )
                    for importer, result in probes
                    if result.supported
                }
            )
            details = [
                {
                    "importer_id": importer.id,
                    "format_id": result.format_id,
                    "technique": result.technique or importer.technique,
                    "reason": result.reason,
                }
                for importer, result in probes
            ]
            filters = {"technique": technique, "format_id": format_id}
            raise UnsupportedFormatError(
                f"No registered importer can safely read {path.name!r} "
                f"(suffix {path.suffix or '<none>'!r}).",
                context={
                    "entry": str(path),
                    "suffix": path.suffix,
                    "filters": filters,
                    "available": available,
                    "probes": details,
                },
            )

        if len(supported) > 1:
            choices = [
                {
                    "importer_id": importer.id,
                    "format_id": result.format_id,
                    "technique": result.technique or importer.technique,
                    "confidence": float(result.confidence),
                }
                for importer, result in supported
            ]
            raise AmbiguousFormatError(
                f"Multiple importers claim {path.name!r}. Supply an explicit "
                "technique or format_id; the registry does not choose by "
                "confidence.",
                context={
                    "entry": str(path),
                    "technique": technique,
                    "format_id": format_id,
                    "candidates": choices,
                },
            )

        return supported[0][0]

    def read(
        self,
        entry: str | Path,
        *,
        technique: str | None = None,
        format_id: str | None = None,
        companions: Mapping[str, str | Path] | None = None,
        options: Mapping[str, Any] | None = None,
        allow_ambiguous: bool = False,
    ) -> ImportedDataset:
        """Select one importer and return its complete dataset.

        There is no fallback: a failed read is propagated as
        :class:`ImportFailure` and never retried with another importer.
        """
        importer = self.select(entry, technique=technique, format_id=format_id)
        request = ImportRequest(
            entry=Path(entry),
            companions=companions or {},
            technique_hint=technique,
            options=options or {},
            allow_ambiguous=allow_ambiguous,
        )

        try:
            dataset = importer.read(request)
        except ImportFailure:
            raise
        except Exception as exc:
            raise ImportFailure(
                f"Importer {importer.id!r} failed while reading "
                f"{Path(entry).name!r}.",
                code="importer_read_failed",
                context={
                    "importer_id": importer.id,
                    "entry": str(entry),
                    "cause_type": type(exc).__name__,
                    "error": str(exc),
                },
            ) from exc

        if not isinstance(dataset, ImportedDataset):
            raise ImportFailure(
                f"Importer {importer.id!r} returned an invalid result object.",
                code="invalid_import_result",
                context={
                    "importer_id": importer.id,
                    "entry": str(entry),
                    "type": type(dataset).__name__,
                },
            )
        return dataset

    def _probe(
        self,
        entry: str | Path,
    ) -> list[tuple[Importer, ProbeResult]]:
        path = Path(entry)
        if not path.is_file():
            raise ImportFailure(
                f"Import entry does not exist or is not a file: {path}",
                code="entry_not_found",
                context={"entry": str(path)},
            )

        suffix = path.suffix.casefold()
        results: list[tuple[Importer, ProbeResult]] = []
        for importer in self._importers.values():
            if suffix not in entry_suffixes(importer):
                continue
            try:
                result = importer.probe(path)
            except ImportFailure:
                raise
            except Exception as exc:
                raise ImportFailure(
                    f"Importer {importer.id!r} failed while probing "
                    f"{path.name!r}.",
                    code="importer_probe_failed",
                    context={
                        "importer_id": importer.id,
                        "entry": str(path),
                        "cause_type": type(exc).__name__,
                        "error": str(exc),
                    },
                ) from exc
            if not isinstance(result, ProbeResult):
                raise ImportFailure(
                    f"Importer {importer.id!r} returned an invalid probe "
                    "result.",
                    code="invalid_probe_result",
                    context={
                        "importer_id": importer.id,
                        "entry": str(path),
                        "type": type(result).__name__,
                    },
                )
            results.append((importer, result))
        return results


__all__ = ["ImporterRegistry"]
