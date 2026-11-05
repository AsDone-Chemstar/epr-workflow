"""Neutral importer protocol, source helper and explicit registry."""

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
from spectralab.core.importers.registry import ImporterRegistry
from spectralab.core.importers.sources import source_file, source_file_from_bytes

__all__ = [
    "AmbiguousFormatError",
    "ImportFailure",
    "ImportRequest",
    "ImportedDataset",
    "Importer",
    "ImporterRegistrationError",
    "ImporterRegistry",
    "ProbeResult",
    "UnsupportedFormatError",
    "source_file",
    "source_file_from_bytes",
]
