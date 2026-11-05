"""Explicit generic FTIR CSV/TXT importers and their options."""

from spectralab.techniques.ftir.importers.generic_csv import (
    GenericCSVImporter,
    GenericCsvImporter,
)
from spectralab.techniques.ftir.importers.generic_txt import (
    GenericTXTImporter,
    GenericTxtImporter,
)
from spectralab.techniques.ftir.importers.mapping import (
    ColumnMapping,
    FTIRImportOptions,
    options_from_mapping,
    parse_column_reference,
)
from spectralab.techniques.ftir.importers.semantics import (
    ACQUISITION_MODES,
    ATR_CORRECTION_STATUSES,
    ATRCorrectionStatus,
    AcquisitionMode,
    FTIRMetadata,
)

__all__ = [
    "ACQUISITION_MODES",
    "ATR_CORRECTION_STATUSES",
    "ATRCorrectionStatus",
    "AcquisitionMode",
    "ColumnMapping",
    "FTIRImportOptions",
    "FTIRMetadata",
    "GenericCSVImporter",
    "GenericCsvImporter",
    "GenericTXTImporter",
    "GenericTxtImporter",
    "options_from_mapping",
    "parse_column_reference",
]
