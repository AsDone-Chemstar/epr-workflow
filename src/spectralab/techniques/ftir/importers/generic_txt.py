"""Generic FTIR TXT/DPT importer.

TXT and DPT-style files default to whitespace-separated columns (which also
covers tab-separated data). The parser preserves decreasing axes exactly and
requires explicit column mappings for files with more than two columns.
"""

from __future__ import annotations

from spectralab.techniques.ftir.formats import FTIR_TXT_SUFFIXES
from spectralab.techniques.ftir.importers._generic import GenericTextImporter


class GenericTXTImporter(GenericTextImporter):
    """Single-spectrum whitespace/tab-delimited text importer."""

    id = "ftir.txt"
    version = "1.0.0"
    technique = "ftir"
    entry_suffixes = FTIR_TXT_SUFFIXES
    format_id = "FTIR_TXT"
    default_delimiter = None


# Tolerate the conventional capitalisation used in architecture discussions.
GenericTxtImporter = GenericTXTImporter

__all__ = ["GenericTXTImporter", "GenericTxtImporter"]
