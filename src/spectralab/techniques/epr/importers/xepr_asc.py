"""Independent Xepr ASC importer adapter.

The parser is the SpectraLab EPR backend's own implementation. This adapter
probes, collects source files, and converts its result through the neutral M1
result-to-Spectrum1D bridge. Legacy ``epr_workflow`` is not imported.
"""

from __future__ import annotations

from pathlib import Path

from spectralab.core.errors import ImportFailure
from spectralab.core.importers import (
    ImportedDataset,
    ImportRequest,
    ProbeResult,
    source_file,
)
from spectralab.core.legacy_adapter import spectrum1d_from_import_result
from spectralab.core.model import SourceFile
from spectralab.techniques.epr.importers._asc_reader import read_asc
from spectralab.techniques.epr.importers._common import (
    dataset_from_spectrum,
    raise_import_failure,
    request_entry,
)

_FORMAT_ID = "ASC"
_REQUIRED_HEADER = frozenset({"index", "field", "intensity"})


def _header_found(entry: Path) -> bool:
    try:
        text = entry.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return False
    for line in text.splitlines():
        lowered = {token.lower().strip("[]") for token in line.split()}
        if _REQUIRED_HEADER.issubset(lowered):
            return True
    return False


class XeprAscImporter:
    """Importer for the existing three-column Xepr ASCII export."""

    id = "epr.xepr_asc"
    version = "0.1.0"
    technique = "epr"
    entry_suffixes = (".asc",)

    def probe(self, entry: Path) -> ProbeResult:
        path = Path(entry)
        if path.suffix.casefold() != ".asc":
            return ProbeResult(
                supported=False,
                confidence=0.0,
                format_id=_FORMAT_ID,
                technique=self.technique,
                reason="The entry suffix is not '.asc'.",
            )
        if not path.is_file():
            return ProbeResult(
                supported=False,
                confidence=0.0,
                format_id=_FORMAT_ID,
                technique=self.technique,
                reason="The entry is not a readable file.",
            )
        if not _header_found(path):
            return ProbeResult(
                supported=False,
                confidence=0.0,
                format_id=_FORMAT_ID,
                technique=self.technique,
                reason=(
                    "No header containing index, Field and Intensity was "
                    "found; no columns were guessed."
                ),
            )
        return ProbeResult(
            supported=True,
            confidence=1.0,
            format_id=_FORMAT_ID,
            technique=self.technique,
            reason="Xepr ASCII header with index/Field/Intensity columns.",
        )

    def collect_sources(self, entry: Path) -> tuple[SourceFile, ...]:
        path = Path(entry)
        try:
            return (source_file(path, role="source", format_id=_FORMAT_ID),)
        except ImportFailure:
            raise
        except Exception as exc:
            raise_import_failure(exc, importer_id=self.id, entry=path)

    def read(self, request: ImportRequest) -> ImportedDataset:
        entry = request_entry(request, technique=self.technique)
        try:
            legacy = read_asc(entry)
            spectrum = spectrum1d_from_import_result(
                legacy,
                importer_id=self.id,
                importer_version=self.version,
            )
            return dataset_from_spectrum(spectrum)
        except Exception as exc:
            raise_import_failure(exc, importer_id=self.id, entry=entry)


# Architecture spelling retained as a public alias.
XeprASCImporter = XeprAscImporter

__all__ = ["XeprASCImporter", "XeprAscImporter"]
