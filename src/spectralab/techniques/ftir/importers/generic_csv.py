"""Generic FTIR CSV importer.

CSV defaults to a comma delimiter, but the delimiter, decimal separator,
header, column mapping and all FTIR semantics remain explicit options. The
importer never infers a vendor, acquisition mode or signal meaning.
"""

from __future__ import annotations

from spectralab.techniques.ftir.formats import FTIR_CSV_SUFFIXES
from spectralab.techniques.ftir.importers._generic import GenericTextImporter


class GenericCSVImporter(GenericTextImporter):
    """Single-spectrum comma-separated text importer."""

    id = "ftir.csv"
    version = "1.0.0"
    technique = "ftir"
    entry_suffixes = FTIR_CSV_SUFFIXES
    format_id = "FTIR_CSV"
    default_delimiter = ","


# Tolerate the conventional capitalisation used in architecture discussions.
GenericCsvImporter = GenericCSVImporter

__all__ = ["GenericCSVImporter", "GenericCsvImporter"]
