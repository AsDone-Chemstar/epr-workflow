"""Independent BES3T importer adapter.

The reader is the SpectraLab EPR backend's own strict implementation. The
``.DSC`` is the only entry point; ``.DTA`` is never treated as an independent
dataset. Legacy ``epr_workflow`` is not imported.
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
from spectralab.techniques.epr.importers._bes3t_reader import (
    find_companion_dta,
    read_bes3t,
)
from spectralab.techniques.epr.importers._common import (
    dataset_from_spectrum,
    raise_import_failure,
    request_entry,
)

_FORMAT_ID = "BES3T"


def _desc_section_found(entry: Path) -> bool:
    try:
        text = entry.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        header = stripped[1:].strip().split(None, 1)
        if header and header[0].upper() == "DESC":
            return True
    return False


class Bes3tImporter:
    """Importer for the existing 1D real BES3T DSC/DTA pair."""

    id = "epr.bes3t"
    version = "0.1.0"
    technique = "epr"
    entry_suffixes = (".dsc",)

    def probe(self, entry: Path) -> ProbeResult:
        path = Path(entry)
        if path.suffix.casefold() != ".dsc":
            return ProbeResult(
                supported=False,
                confidence=0.0,
                format_id=_FORMAT_ID,
                technique=self.technique,
                reason="The entry suffix is not '.dsc'.",
            )
        if not path.is_file():
            return ProbeResult(
                supported=False,
                confidence=0.0,
                format_id=_FORMAT_ID,
                technique=self.technique,
                reason="The entry is not a readable file.",
            )
        if not _desc_section_found(path):
            return ProbeResult(
                supported=False,
                confidence=0.0,
                format_id=_FORMAT_ID,
                technique=self.technique,
                reason=(
                    "No #DESC section was found; the layout was not guessed."
                ),
            )
        return ProbeResult(
            supported=True,
            confidence=1.0,
            format_id=_FORMAT_ID,
            technique=self.technique,
            reason="BES3T descriptor with a #DESC section.",
        )

    def collect_sources(self, entry: Path) -> tuple[SourceFile, ...]:
        path = Path(entry)
        try:
            companion = find_companion_dta(path)
            return (
                source_file(path, role="descriptor", format_id=_FORMAT_ID),
                source_file(companion, role="data", format_id=_FORMAT_ID),
            )
        except Exception as exc:
            raise_import_failure(exc, importer_id=self.id, entry=path)

    def read(self, request: ImportRequest) -> ImportedDataset:
        entry = request_entry(request, technique=self.technique)
        try:
            legacy = read_bes3t(entry)
            spectrum = spectrum1d_from_import_result(
                legacy,
                importer_id=self.id,
                importer_version=self.version,
            )
            return dataset_from_spectrum(spectrum)
        except Exception as exc:
            raise_import_failure(exc, importer_id=self.id, entry=entry)


# Architecture spelling retained as a public alias.
BES3TImporter = Bes3tImporter

__all__ = ["BES3TImporter", "Bes3tImporter"]
