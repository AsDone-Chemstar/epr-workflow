"""Shared strict parser for generic two-column FTIR CSV/TXT files.

The parser preserves the source point order exactly. It never sorts, reverses,
removes duplicate points, interpolates, smooths, baselines or normalises. A
malformed row is an error, not a row to discard.
"""

from __future__ import annotations

import csv
import math
import os
import re
from pathlib import Path
from typing import Any

import numpy as np

from spectralab.core.errors import AxisValidationError, ImportFailure
from spectralab.core.importers import (
    ImportedDataset,
    ImportRequest,
    ProbeResult,
    source_file_from_bytes,
)
from spectralab.core.model import (
    Axis1D,
    Provenance,
    Signal1D,
    Spectrum1D,
    SpectrumMetadata,
)
from spectralab.techniques.ftir.importers.mapping import (
    ColumnMapping,
    FTIRImportOptions,
    options_from_mapping,
)

_NUMBER_RE = re.compile(
    r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
)
_NONFINITE_TOKENS = {
    "nan",
    "+nan",
    "-nan",
    "inf",
    "+inf",
    "-inf",
    "infinity",
    "+infinity",
    "-infinity",
}
PROBE_READ_LIMIT = 64 * 1024


def _failure(message: str, *, code: str, **context: Any) -> ImportFailure:
    return ImportFailure(message, code=code, context=context)


def _validate_request(request: ImportRequest, *, technique: str) -> Path:
    if not isinstance(request, ImportRequest):
        raise _failure(
            "Importer.read() requires an ImportRequest.",
            code="invalid_import_request",
            type=type(request).__name__,
        )
    if request.companions:
        raise _failure(
            "Generic FTIR text import reads a single file and accepts no "
            "companion overrides.",
            code="unsupported_companion_override",
            companions=sorted(request.companions),
        )
    if request.technique_hint is not None and request.technique_hint != technique:
        raise _failure(
            f"Technique hint {request.technique_hint!r} does not match this "
            f"{technique!r} importer.",
            code="technique_mismatch",
            technique_hint=request.technique_hint,
            technique=technique,
        )
    return request.entry


def _options(request: ImportRequest) -> FTIRImportOptions:
    if not request.options:
        return FTIRImportOptions()
    return options_from_mapping(request.options)


def _resolve_delimiter(
    configured: str | None,
    *,
    suffix: str,
    default_delimiter: str | None,
) -> str | None:
    """Resolve a delimiter to ``None`` (whitespace) or one character."""
    if configured is None:
        return default_delimiter
    if configured == "whitespace":
        return None
    if configured == "auto":
        return default_delimiter
    if not isinstance(configured, str) or len(configured) != 1:
        raise _failure(
            "A resolved delimiter must be one character or whitespace.",
            code="ftir_invalid_delimiter",
            delimiter=configured,
            suffix=suffix,
        )
    return configured


def _split_line(line: str, delimiter: str | None, *, line_number: int) -> list[str]:
    if delimiter is None:
        return line.split()
    try:
        row = next(csv.reader([line], delimiter=delimiter))
    except csv.Error as exc:
        raise _failure(
            f"Could not parse line {line_number} as delimited text: {exc}",
            code="ftir_row_parse_error",
            line=line_number,
            delimiter=delimiter,
        ) from exc
    return [field.strip() for field in row]


def _parse_number(
    token: str,
    *,
    decimal: str,
    line_number: int,
    column: int,
    axis: str,
) -> float:
    text = token.strip()
    if not text:
        raise _failure(
            f"Missing numeric value at line {line_number}, column "
            f"{column}.",
            code="ftir_missing_value",
            line=line_number,
            column=column,
            axis=axis,
        )
    if text.casefold() in _NONFINITE_TOKENS:
        raise _failure(
            f"Non-finite value {text!r} at line {line_number}, column "
            f"{column}; NaN and infinity are not accepted.",
            code="ftir_nonfinite",
            line=line_number,
            column=column,
            value=text,
            axis=axis,
        )
    if decimal == ",":
        if text.count(",") > 1:
            raise _failure(
                f"Invalid decimal-comma number {text!r} at line "
                f"{line_number}, column {column}.",
                code="ftir_invalid_number",
                line=line_number,
                column=column,
                value=text,
                axis=axis,
            )
        text = text.replace(",", ".")
    elif "," in text:
        raise _failure(
            f"Comma is not the configured decimal separator, but {text!r} "
            f"contains one at line {line_number}, column {column}.",
            code="ftir_invalid_number",
            line=line_number,
            column=column,
            value=token,
            axis=axis,
        )
    if _NUMBER_RE.fullmatch(text) is None:
        raise _failure(
            f"Invalid numeric value {token!r} at line {line_number}, column "
            f"{column}.",
            code="ftir_invalid_number",
            line=line_number,
            column=column,
            value=token,
            axis=axis,
        )
    value = float(text)
    if not math.isfinite(value):
        raise _failure(
            f"Non-finite numeric value {token!r} at line {line_number}, "
            f"column {column}; NaN and infinity are not accepted.",
            code="ftir_nonfinite",
            line=line_number,
            column=column,
            value=token,
            axis=axis,
        )
    return value


def _resolve_reference(
    reference: int | str | None,
    *,
    header_fields: tuple[str, ...] | None,
    column_count: int,
    axis: str,
) -> int | None:
    if reference is None:
        return None
    if isinstance(reference, int):
        if reference >= column_count:
            raise _failure(
                f"The {axis} column index {reference} is outside the "
                f"{column_count} available column(s).",
                code="ftir_missing_column",
                axis=axis,
                column=reference,
                column_count=column_count,
            )
        return reference
    if header_fields is None:
        raise _failure(
            f"The {axis} column was given by name but the file has no "
            "header row.",
            code="ftir_header_required",
            axis=axis,
            name=reference,
        )
    matches = [
        index
        for index, value in enumerate(header_fields)
        if value == reference
    ]
    if not matches:
        raise _failure(
            f"No header column named {reference!r} was found.",
            code="ftir_unknown_column_name",
            axis=axis,
            name=reference,
            columns=list(header_fields),
        )
    if len(matches) > 1:
        raise _failure(
            f"The header column name {reference!r} is duplicated; the "
            "mapping is ambiguous.",
            code="ftir_duplicate_column_name",
            axis=axis,
            name=reference,
            matches=matches,
        )
    return matches[0]


def _resolve_mapping(
    mapping: ColumnMapping,
    *,
    header_fields: tuple[str, ...] | None,
    column_count: int,
) -> tuple[int, int, bool]:
    if column_count < 2:
        raise _failure(
            "At least two columns are required for an FTIR spectrum.",
            code="ftir_insufficient_columns",
            column_count=column_count,
        )

    x = _resolve_reference(
        mapping.x,
        header_fields=header_fields,
        column_count=column_count,
        axis="X",
    )
    y = _resolve_reference(
        mapping.y,
        header_fields=header_fields,
        column_count=column_count,
        axis="Y",
    )
    defaulted = False
    if x is None and y is None:
        if column_count != 2:
            raise _failure(
                "This file has more than two columns. Supply explicit X and "
                "Y column mappings; the importer does not guess columns.",
                code="ftir_column_mapping_required",
                column_count=column_count,
            )
        x, y = 0, 1
        defaulted = True
    elif x is None or y is None:
        if column_count != 2:
            raise _failure(
                "Both X and Y column mappings are required for a file with "
                "more than two columns.",
                code="ftir_column_mapping_required",
                column_count=column_count,
            )
        x = 0 if y != 0 else 1
        y = 1 if x == 0 else 0
        defaulted = True

    if x == y:
        raise _failure(
            "X and Y must map to different columns.",
            code="ftir_same_column",
            column=x,
        )
    return int(x), int(y), defaulted


def _read_stable_bytes(path: Path) -> bytes:
    """Read one byte snapshot and reject a file changed during that read."""
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            raw = handle.read()
            after = os.fstat(handle.fileno())
    except FileNotFoundError as exc:
        raise _failure(
            f"Import entry does not exist: {path}",
            code="entry_not_found",
            entry=str(path),
        ) from exc
    except PermissionError as exc:
        raise _failure(
            f"Import entry is not readable: {path}",
            code="entry_not_readable",
            entry=str(path),
        ) from exc
    except OSError as exc:
        raise _failure(
            f"Could not read import entry {path}: {exc}",
            code="entry_not_readable",
            entry=str(path),
            error=str(exc),
        ) from exc

    before_state = (before.st_size, before.st_mtime_ns)
    after_state = (after.st_size, after.st_mtime_ns)
    if before_state != after_state:
        raise _failure(
            "The source file changed while it was being imported.",
            code="source_changed_during_import",
            entry=str(path),
            before_size=before.st_size,
            after_size=after.st_size,
        )
    return raw


def _read_text(path: Path, encoding: str) -> tuple[bytes, str]:
    raw = _read_stable_bytes(path)
    if not raw:
        raise _failure(
            f"Input file is empty: {path.name}",
            code="ftir_empty_file",
            entry=str(path),
        )
    try:
        text = raw.decode(encoding, errors="strict")
    except LookupError as exc:
        raise _failure(
            f"Unknown text encoding {encoding!r}.",
            code="ftir_invalid_encoding",
            encoding=encoding,
        ) from exc
    except UnicodeDecodeError as exc:
        raise _failure(
            f"Could not decode {path.name!r} using {encoding!r}: {exc}",
            code="ftir_decode_error",
            entry=str(path),
            encoding=encoding,
            byte_offset=exc.start,
        ) from exc
    return raw, text


def _logical_lines(
    text: str,
    *,
    skip_rows: int,
    comment_markers: tuple[str, ...],
) -> tuple[list[tuple[int, str]], int, int, int]:
    lines = text.splitlines()
    body = lines[skip_rows:]
    records: list[tuple[int, str]] = []
    blank_count = 0
    comment_count = 0
    for offset, line in enumerate(body, start=skip_rows + 1):
        stripped = line.lstrip()
        if any(stripped.startswith(marker) for marker in comment_markers):
            comment_count += 1
            continue
        if not line.strip():
            blank_count += 1
            continue
        records.append((offset, line))
    return records, blank_count, comment_count, len(lines)


def _axis_quantity(mapping: ColumnMapping) -> tuple[str, str]:
    if mapping.x_quantity is not None:
        return mapping.x_quantity, "user-supplied x_quantity"
    if mapping.x_unit is not None:
        return "wavenumber", "confirmed by explicit x_unit"
    return "unknown", "not supplied"


def _source_metadata(
    *,
    path: Path,
    raw: bytes,
    format_id: str,
    delimiter: str | None,
    mapping: ColumnMapping,
    options: FTIRImportOptions,
    x_column: int,
    y_column: int,
    data_rows: int,
    blank_count: int,
    comment_count: int,
    line_count: int,
    defaulted_mapping: bool,
) -> tuple[Any, dict[str, Any], tuple[str, ...], tuple[str, ...], dict[str, Any]]:
    source = source_file_from_bytes(
        path,
        raw,
        role="source",
        format_id=format_id,
    )

    resolved_options = options.as_dict()
    format_metadata: dict[str, Any] = {
        "source_format": format_id,
        "delimiter": "whitespace" if delimiter is None else delimiter,
        "decimal_separator": mapping.decimal,
        "encoding": mapping.encoding,
        "header": mapping.header,
        "comment_markers": list(mapping.comment_markers),
        "skip_rows": mapping.skip_rows,
        "defaulted_two_column_mapping": defaulted_mapping,
        "data_row_count": data_rows,
        "blank_line_count": blank_count,
        "comment_line_count": comment_count,
        "total_line_count": line_count,
        "import_options": resolved_options,
        "resolved_mapping": {
            "x": x_column,
            "y": y_column,
            "requested_x": mapping.x,
            "requested_y": mapping.y,
        },
    }
    warnings: list[str] = []
    if blank_count:
        warnings.append(f"Ignored {blank_count} blank line(s).")
    if comment_count:
        warnings.append(
            f"Ignored {comment_count} comment line(s) with configured "
            "markers."
        )
    assumptions: list[str] = []
    if defaulted_mapping:
        assumptions.append(
            "X and Y were assigned to the first two columns because the "
            "file contains exactly two columns and no explicit mapping was "
            "supplied."
        )
    assumptions.append(
        "No baseline correction, normalization, smoothing, filtering, peak "
        "detection, ATR correction, sorting, reversal, interpolation or "
        "extrapolation was applied."
    )
    diagnostics = {
        "data_row_count": data_rows,
        "blank_line_count": blank_count,
        "comment_line_count": comment_count,
        "skipped_line_count": min(mapping.skip_rows, line_count),
        "resolved_x_column": x_column,
        "resolved_y_column": y_column,
    }
    return source, format_metadata, tuple(warnings), tuple(assumptions), diagnostics


def read_ftir_text(
    entry: Path,
    *,
    options: FTIRImportOptions,
    format_id: str,
    default_delimiter: str | None,
    importer_id: str,
    importer_version: str,
) -> ImportedDataset:
    """Parse one FTIR CSV/TXT file into exactly one ``Spectrum1D``."""
    path = Path(entry)
    mapping = options.mapping
    raw, text = _read_text(path, mapping.encoding)
    delimiter = _resolve_delimiter(
        mapping.delimiter,
        suffix=path.suffix.casefold(),
        default_delimiter=default_delimiter,
    )
    if delimiter == "," and mapping.decimal == ",":
        raise _failure(
            "A comma delimiter cannot be combined with a comma decimal "
            "separator.",
            code="ftir_delimiter_decimal_conflict",
            delimiter=",",
            decimal=mapping.decimal,
        )

    records, blank_count, comment_count, line_count = _logical_lines(
        text,
        skip_rows=mapping.skip_rows,
        comment_markers=mapping.comment_markers,
    )
    if not records:
        raise _failure(
            f"No data rows were found in {path.name!r}.",
            code="ftir_no_data",
            entry=str(path),
            skip_rows=mapping.skip_rows,
            blank_line_count=blank_count,
            comment_line_count=comment_count,
        )

    header_fields: tuple[str, ...] | None = None
    if mapping.header:
        header_number, header_line = records.pop(0)
        parsed_header = tuple(
            field
            for field in _split_line(
                header_line,
                delimiter,
                line_number=header_number,
            )
        )
        if not parsed_header:
            raise _failure(
                f"The header row at line {header_number} is empty.",
                code="ftir_empty_header",
                line=header_number,
            )
        header_fields = parsed_header

    if not records:
        raise _failure(
            f"{path.name!r} contains a header but no data rows.",
            code="ftir_no_data",
            entry=str(path),
        )

    parsed_rows: list[tuple[int, list[str]]] = []
    expected_columns: int | None = None
    for line_number, line in records:
        fields = _split_line(line, delimiter, line_number=line_number)
        if expected_columns is None:
            expected_columns = len(fields)
            if header_fields is not None and len(header_fields) != expected_columns:
                raise _failure(
                    f"The header has {len(header_fields)} column(s) but data "
                    f"line {line_number} has {expected_columns}.",
                    code="ftir_inconsistent_columns",
                    line=line_number,
                    header_columns=len(header_fields),
                    data_columns=expected_columns,
                )
        if len(fields) != expected_columns:
            raise _failure(
                f"Inconsistent column count at line {line_number}: expected "
                f"{expected_columns}, got {len(fields)}.",
                code="ftir_inconsistent_columns",
                line=line_number,
                expected=expected_columns,
                actual=len(fields),
            )
        parsed_rows.append((line_number, fields))

    assert expected_columns is not None
    if header_fields is not None and len(header_fields) != expected_columns:
        raise _failure(
            f"The header has {len(header_fields)} column(s) but the data has "
            f"{expected_columns}.",
            code="ftir_inconsistent_columns",
            header_columns=len(header_fields),
            data_columns=expected_columns,
        )

    x_column, y_column, defaulted = _resolve_mapping(
        mapping,
        header_fields=header_fields,
        column_count=expected_columns,
    )

    x_values: list[float] = []
    y_values: list[float] = []
    for line_number, fields in parsed_rows:
        x_values.append(
            _parse_number(
                fields[x_column],
                decimal=mapping.decimal,
                line_number=line_number,
                column=x_column,
                axis="X",
            )
        )
        y_values.append(
            _parse_number(
                fields[y_column],
                decimal=mapping.decimal,
                line_number=line_number,
                column=y_column,
                axis="Y",
            )
        )

    if len(x_values) < 2:
        raise _failure(
            f"At least two data points are required; {path.name!r} has "
            f"{len(x_values)}.",
            code="ftir_insufficient_points",
            point_count=len(x_values),
        )

    quantity, quantity_origin = _axis_quantity(mapping)
    source, format_metadata, warnings, assumptions, diagnostics = (
        _source_metadata(
            path=path,
            raw=raw,
            format_id=format_id,
            delimiter=delimiter,
            mapping=mapping,
            options=options,
            x_column=x_column,
            y_column=y_column,
            data_rows=len(x_values),
            blank_count=blank_count,
            comment_count=comment_count,
            line_count=line_count,
            defaulted_mapping=defaulted,
        )
    )
    if expected_columns > 2:
        warnings = warnings + (
            f"The file has {expected_columns} columns; only X column "
            f"{x_column} and Y column {y_column} were imported. No "
            "multi-spectrum split was performed.",
        )

    try:
        axis = Axis1D(
            values=np.asarray(x_values, dtype=np.float64),
            quantity=quantity,  # type: ignore[arg-type]
            unit=mapping.x_unit,
            name=mapping.x_name,
            direction=None,
            metadata_source=(
                f"FTIR text column {x_column} (zero-based)"
            ),
            missing_reason=(
                "No X-axis unit was explicitly supplied."
                if mapping.x_unit is None
                else None
            ),
        )
        signal = Signal1D(
            values=np.asarray(y_values, dtype=np.float64),
            semantics=mapping.y_semantics,  # type: ignore[arg-type]
            unit=mapping.y_unit,
            name=mapping.y_name,
            metadata_source=(
                f"FTIR text column {y_column} (zero-based)"
            ),
            missing_reason=(
                "No Y-axis unit was explicitly supplied."
                if mapping.y_unit is None
                else None
            ),
        )
    except AxisValidationError as exc:
        raise _failure(
            f"The imported X axis is not strictly monotonic: {exc}",
            code="axis_not_monotonic",
            source="ftir_text",
            context=dict(exc.context),
        ) from exc

    unknown_fields: list[str] = []
    if mapping.x_unit is None:
        unknown_fields.append("axis.unit")
    if mapping.y_unit is None:
        unknown_fields.append("signal.unit")
    if mapping.y_semantics == "unknown":
        unknown_fields.append("signal.semantics")
    if mapping.x_quantity is None and mapping.x_unit is None:
        unknown_fields.append("axis.quantity")
    unknown_fields.extend(["title", "sample"])
    if options.instrument_vendor is None:
        unknown_fields.append("instrument.vendor")
    if options.instrument_model is None:
        unknown_fields.append("instrument.model")
    if mapping.x_name is None:
        unknown_fields.append("axis.name")
    if mapping.y_name is None:
        unknown_fields.append("signal.name")
    if options.acquisition_mode == "Unknown":
        unknown_fields.append("acquisition_mode")
    if options.atr_correction_status == "unknown":
        unknown_fields.append("atr_correction_status")

    instrument: dict[str, str] = {}
    if options.instrument_vendor is not None:
        instrument["vendor"] = options.instrument_vendor
    if options.instrument_model is not None:
        instrument["model"] = options.instrument_model

    metadata = SpectrumMetadata(
        technique="ftir",
        title=None,
        instrument=instrument,
        acquisition={
            "mode": options.acquisition_mode,
            "atr_correction_status": options.atr_correction_status,
        },
        sample={},
        technique_metadata={
            "format_id": format_id,
            "column_mapping": {
                "x": x_column,
                "y": y_column,
            },
            "header_fields": list(header_fields) if header_fields else None,
        },
        extra={},
        unknown_fields=tuple(dict.fromkeys(unknown_fields)),
        metadata_origin={
            "axis.values": f"FTIR text column {x_column} (zero-based)",
            "axis.direction": "inferred from imported point order",
            "axis.quantity": quantity_origin,
            "axis.unit": (
                "explicit user x_unit"
                if mapping.x_unit is not None
                else "unknown"
            ),
            "signal.values": f"FTIR text column {y_column} (zero-based)",
            "signal.semantics": (
                "explicit user y_semantics"
                if mapping.y_semantics != "unknown"
                else "unknown"
            ),
            "signal.unit": (
                "explicit user y_unit"
                if mapping.y_unit is not None
                else "unknown"
            ),
            "acquisition_mode": "explicit user option"
            if options.acquisition_mode != "Unknown"
            else "default Unknown",
            "atr_correction_status": "explicit user option"
            if options.atr_correction_status != "unknown"
            else "default unknown",
            "instrument.vendor": "explicit user option"
            if options.instrument_vendor is not None
            else "unknown",
            "instrument.model": "explicit user option"
            if options.instrument_model is not None
            else "unknown",
            "source_format": f"explicit importer {importer_id}",
        },
    )

    provenance = Provenance(
        source_files=(source,),
        canonical_sha256=source.sha256,
        sha256_definition="SHA-256 of the complete source file bytes.",
        file_size_bytes=len(raw),
        warnings=warnings,
        assumptions=assumptions,
        format_metadata=format_metadata,
        diagnostics=diagnostics,
        software_versions={},
        importer_id=importer_id,
        importer_version=importer_version,
        imported_at_utc=None,
    )

    spectrum = Spectrum1D(
        dataset_id=path.stem or path.name,
        axis=axis,
        raw_signal=signal,
        metadata=metadata,
        provenance=provenance,
    )
    return ImportedDataset(
        spectra=(spectrum,),
        primary_index=0,
        format_id=format_id,
        technique="ftir",
        warnings=warnings,
        diagnostics=diagnostics,
    )


def _read_probe_prefix(path: Path) -> tuple[bytes, bool]:
    """Read at most PROBE_READ_LIMIT bytes and report whether more exist."""
    with path.open("rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        prefix = handle.read(PROBE_READ_LIMIT)
    return prefix, size > len(prefix)


def _probe_text(entry: Path, *, entry_suffixes: tuple[str, ...]) -> ProbeResult:
    path = Path(entry)
    suffix = path.suffix.casefold()
    if suffix not in {item.casefold() for item in entry_suffixes}:
        return ProbeResult(
            supported=False,
            confidence=0.0,
            format_id="FTIR_TEXT",
            technique="ftir",
            reason=f"The entry suffix {path.suffix!r} is not supported here.",
        )
    if not path.is_file():
        return ProbeResult(
            supported=False,
            confidence=0.0,
            format_id="FTIR_TEXT",
            technique="ftir",
            reason="The entry is not a readable file.",
        )
    try:
        prefix, truncated = _read_probe_prefix(path)
    except OSError as exc:
        return ProbeResult(
            supported=False,
            confidence=0.0,
            format_id="FTIR_TEXT",
            technique="ftir",
            reason=f"The entry could not be read: {exc}",
        )
    if not prefix:
        # An empty file still belongs to the declared FTIR text format; the
        # parser reports the specific empty-file error.
        return ProbeResult(
            supported=True,
            confidence=1.0,
            format_id="FTIR_TEXT",
            technique="ftir",
            reason="Empty file with a declared FTIR text suffix.",
        )

    text = prefix.decode("utf-8-sig", errors="replace")
    nonempty = [line for line in text.splitlines() if line.strip()]
    if not nonempty:
        return ProbeResult(
            supported=True,
            confidence=1.0,
            format_id="FTIR_TEXT",
            technique="ftir",
            reason="Whitespace-only file with a declared FTIR text suffix.",
        )
    # A one-line file cannot be imported successfully, but it must still reach
    # the parser when the suffix is unambiguous, the line is visibly tabular,
    # or the bounded prefix is truncated and later lines may exist. A single
    # complete prose line with no delimiter is rejected.
    one_line_supported = (
        truncated
        or suffix == ".csv"
        or any(marker in nonempty[0] for marker in (",", "\t", ";", "|"))
    )
    if len(nonempty) < 2 and not one_line_supported:
        return ProbeResult(
            supported=False,
            confidence=0.0,
            format_id="FTIR_TEXT",
            technique="ftir",
            reason=(
                "The file has one non-empty line with no recognisable "
                "tabular delimiter; it is not claimed as FTIR text."
            ),
        )
    return ProbeResult(
        supported=True,
        confidence=1.0,
        format_id="FTIR_TEXT",
        technique="ftir",
        reason=(
            "Delimited text with a declared FTIR suffix. Columns, delimiter "
            "and semantics remain explicit user choices."
        ),
    )


class GenericTextImporter:
    """Common implementation; subclasses declare suffix and format defaults."""

    id = "ftir.text"
    version = "1.0.0"
    technique = "ftir"
    entry_suffixes: tuple[str, ...] = (".txt",)
    format_id = "FTIR_TEXT"
    default_delimiter: str | None = None

    def probe(self, entry: Path) -> ProbeResult:
        result = _probe_text(entry, entry_suffixes=self.entry_suffixes)
        if result.supported:
            return ProbeResult(
                supported=True,
                confidence=result.confidence,
                format_id=self.format_id,
                technique=self.technique,
                reason=result.reason,
            )
        return ProbeResult(
            supported=False,
            confidence=result.confidence,
            format_id=self.format_id,
            technique=self.technique,
            reason=result.reason,
        )

    def collect_sources(self, entry: Path):
        return (source_file(Path(entry), role="source", format_id=self.format_id),)

    def read(self, request: ImportRequest) -> ImportedDataset:
        entry = _validate_request(request, technique=self.technique)
        try:
            options = _options(request)
            return read_ftir_text(
                entry,
                options=options,
                format_id=self.format_id,
                default_delimiter=self.default_delimiter,
                importer_id=self.id,
                importer_version=self.version,
            )
        except ImportFailure:
            raise
        except Exception as exc:
            raise _failure(
                f"Importer {self.id!r} could not read {entry.name!r}: {exc}",
                code="ftir_import_failed",
                importer_id=self.id,
                entry=str(entry),
                cause_type=type(exc).__name__,
            ) from exc


__all__ = ["GenericTextImporter", "read_ftir_text"]
