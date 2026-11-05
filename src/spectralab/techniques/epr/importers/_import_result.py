"""Internal EPR import result and source-hash helpers.

This is the SpectraLab EPR backend's own representation. It deliberately does
not import ``epr_workflow``; the core legacy adapter accepts it by structure.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

MIN_VALID_POINTS = 3
REQUIRED_COLUMNS = ["index", "field_G", "intensity"]


@dataclass
class EprImportResult:
    """Validated EPR import data before conversion to Spectrum1D."""

    source: Path
    data: pd.DataFrame
    rejected_rows: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sha256: str = ""
    file_size_bytes: int = 0
    field_order: str = "unknown"
    missing_value_count: int = 0
    nonfinite_value_count: int = 0
    duplicate_field_count: int = 0
    index_continuity: str = "not checked"
    source_format: str = "ASC"
    source_files: dict[str, str] = field(default_factory=dict)
    source_hashes: dict[str, str] = field(default_factory=dict)
    sha256_definition: str = "SHA-256 of the source file bytes."
    format_metadata: dict[str, Any] = field(default_factory=dict)
    format_assumptions: list[str] = field(default_factory=list)


def combine_source_hashes(
    source_format: str,
    source_hashes: dict[str, str],
) -> str:
    """Return the legacy-compatible canonical dataset hash."""
    if source_format == "BES3T":
        try:
            descriptor = source_hashes["descriptor"]
            data = source_hashes["data"]
        except KeyError as exc:
            raise ValueError(
                "BES3T provenance requires both descriptor and data hashes."
            ) from exc
        payload = (
            b"BES3T:"
            + descriptor.encode("ascii")
            + b":"
            + data.encode("ascii")
        )
        return hashlib.sha256(payload).hexdigest()
    if "source" in source_hashes:
        return source_hashes["source"]
    if len(source_hashes) == 1:
        return next(iter(source_hashes.values()))
    raise ValueError("Cannot combine source hashes for an unknown format.")


__all__ = [
    "MIN_VALID_POINTS",
    "REQUIRED_COLUMNS",
    "EprImportResult",
    "combine_source_hashes",
]
