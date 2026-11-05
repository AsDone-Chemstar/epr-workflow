"""Independent Xepr ASC reader for the SpectraLab EPR backend.

The validation, row acceptance and diagnostic behavior mirror the legacy
``epr_workflow.plot_asc.read_asc`` reader without importing it.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from spectralab.techniques.epr.importers._import_result import (
    MIN_VALID_POINTS,
    REQUIRED_COLUMNS,
    EprImportResult,
)

LOGGER = logging.getLogger("spectralab.techniques.epr.asc")
EXPECTED_COLUMNS = ("index", "field", "intensity")


class AscFormatError(ValueError):
    """The file does not look like a supported Xepr ASCII export."""


class AscDataError(ValueError):
    """The file parses but cannot form a safe spectrum."""


def _is_finite_row(values: tuple[float, float, float]) -> bool:
    return all(np.isfinite(value) for value in values)


def read_asc(
    path: str | Path,
    *,
    allow_non_monotonic: bool = False,
) -> EprImportResult:
    """Read and validate an Xepr ASCII export.

    The source is opened read-only. Valid rows retain their original order;
    rejected rows are excluded but reported. No sorting, repair, interpolation
    or unit conversion is performed.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"ASC file not found: {path}\n"
            "Check the path, e.g. data/raw/BSA3T275.ASC"
        )

    raw_bytes = path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()

    header_index, header_tokens = _find_header(lines, path)

    warnings: list[str] = []
    if header_index > 0 and any(line.strip() for line in lines[:header_index]):
        warnings.append(
            f"{header_index} non-blank line(s) before the header were ignored."
        )

    _check_column_order(header_tokens, path)

    records: list[tuple[float, float, float]] = []
    rejected: list[dict[str, Any]] = []
    missing_count = 0
    nonfinite_count = 0

    for line_no, line in enumerate(
        lines[header_index + 1 :],
        start=header_index + 2,
    ):
        stripped = line.strip()
        if not stripped:
            continue

        tokens = stripped.split()
        if len(tokens) != 3:
            if len(tokens) < 3:
                missing_count += 1
            rejected.append(
                {
                    "line": line_no,
                    "reason": f"expected 3 columns, found {len(tokens)}",
                    "text": stripped[:120],
                }
            )
            continue

        try:
            values = (float(tokens[0]), float(tokens[1]), float(tokens[2]))
        except ValueError:
            rejected.append(
                {
                    "line": line_no,
                    "reason": "non-numeric value in data row",
                    "text": stripped[:120],
                }
            )
            continue

        if not _is_finite_row(values):
            nonfinite_count += 1
            rejected.append(
                {
                    "line": line_no,
                    "reason": "non-finite value (NaN or infinity) rejected",
                    "text": stripped[:120],
                }
            )
            continue

        records.append(values)

    if not records:
        raise AscDataError(
            f"No valid numeric data rows found in {path.name}. "
            f"{len(rejected)} row(s) were rejected. "
            "Refusing to produce a spectrum from invalid data."
        )

    data = pd.DataFrame(records, columns=REQUIRED_COLUMNS)

    index_values = data["index"].to_numpy()
    index_is_integral = bool(
        np.all(np.isfinite(index_values))
        and np.all(index_values == np.round(index_values))
        and np.all(np.abs(index_values) < 2**62)
    )
    if index_is_integral:
        data["index"] = data["index"].astype("int64")
    else:
        warnings.append(
            "The 'index' column contains non-integer values; it is preserved "
            "as-is (not rounded) and is not treated as a physical quantity."
        )

    if len(data) < MIN_VALID_POINTS:
        raise AscDataError(
            f"Only {len(data)} valid data point(s) found; at least "
            f"{MIN_VALID_POINTS} are required to plot a spectrum."
        )

    duplicate_count = int(data["field_G"].duplicated().sum())
    field_diffs = np.diff(data["field_G"].to_numpy())
    if np.all(field_diffs > 0):
        field_order = "strictly increasing"
    elif np.all(field_diffs < 0):
        field_order = "strictly decreasing"
    else:
        field_order = "non-monotonic"
        if not allow_non_monotonic:
            raise AscDataError(
                "The magnetic-field column is non-monotonic "
                f"({duplicate_count} duplicated field value(s), "
                f"{int(np.sum(field_diffs == 0))} repeated adjacent step(s), "
                f"{int(np.sum(field_diffs < 0))} decreasing step(s)). "
                "Plotting the rows in their original order would produce a "
                "misleading spectrum. Use --allow-non-monotonic only if the "
                "acquisition order is genuinely unordered."
            )
        if duplicate_count:
            warnings.append(
                f"{duplicate_count} duplicate magnetic-field value(s) "
                "detected; rows were kept unchanged (not de-duplicated)."
            )

    index_continuity = _check_index_continuity(
        data["index"].to_numpy(),
        warnings,
    )

    if rejected:
        shown = ", ".join(str(row["line"]) for row in rejected[:10])
        more = "" if len(rejected) <= 10 else f" (+{len(rejected) - 10} more)"
        warnings.append(
            f"{len(rejected)} data row(s) rejected and excluded from the "
            f"spectrum (line numbers: {shown}{more})."
        )
    if nonfinite_count:
        warnings.append(
            f"{nonfinite_count} row(s) contained non-finite values and were "
            "excluded from the spectrum."
        )

    for message in warnings:
        LOGGER.warning("%s", message)

    return EprImportResult(
        source=path,
        data=data,
        rejected_rows=rejected,
        warnings=warnings,
        sha256=digest,
        file_size_bytes=len(raw_bytes),
        field_order=field_order,
        missing_value_count=missing_count,
        nonfinite_value_count=nonfinite_count,
        duplicate_field_count=duplicate_count,
        index_continuity=index_continuity,
    )


def _find_header(lines: list[str], path: Path) -> tuple[int, list[str]]:
    for line_index, line in enumerate(lines):
        tokens = line.split()
        lowered = {token.lower().strip("[]") for token in tokens}
        if all(key in lowered for key in EXPECTED_COLUMNS):
            return line_index, tokens

    raise AscFormatError(
        f"Could not find a valid header in {path.name}. Expected a line "
        "containing 'index', 'Field [G]' and 'Intensity []' (any whitespace "
        "delimiter). The file was not imported, so no columns were guessed."
    )


def _check_column_order(header_tokens: list[str], path: Path) -> None:
    positions: dict[str, int] = {}
    for position, token in enumerate(header_tokens):
        key = token.lower().strip("[]")
        if key in EXPECTED_COLUMNS and key not in positions:
            positions[key] = position

    order = tuple(sorted(positions, key=positions.__getitem__))
    if order != EXPECTED_COLUMNS:
        raise AscFormatError(
            f"Unexpected column order in {path.name}: found {order}, expected "
            f"{EXPECTED_COLUMNS}. Refusing to import possibly mis-assigned "
            "columns."
        )


def _check_index_continuity(index: np.ndarray, warnings: list[str]) -> str:
    if index.size < 2:
        return "not checked (fewer than 2 points)"
    if index.dtype.kind not in "iu":
        return "not checked (non-integer index)"

    diffs = np.diff(index)
    if not np.all(diffs > 0):
        return "not checked (index not strictly increasing)"

    gap_positions = np.flatnonzero(diffs != 1)
    if gap_positions.size == 0:
        return "consecutive"

    first = int(gap_positions[0])
    warnings.append(
        f"Index is not consecutive: {gap_positions.size} gap(s), first between "
        f"data rows {first + 1} and {first + 2} (index {int(index[first])} -> "
        f"{int(index[first + 1])}). Rows were preserved and not renumbered."
    )
    return f"gaps ({gap_positions.size})"


__all__ = ["AscDataError", "AscFormatError", "read_asc"]
