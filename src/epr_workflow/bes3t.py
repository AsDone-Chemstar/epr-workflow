"""Strict reader for Bruker Xepr BES3T (``.DSC`` + ``.DTA``) datasets.

The first supported use case is a one-dimensional, real-valued CW-EPR
spectrum. This module does **not** attempt to support every BES3T layout.

Verified descriptor semantics used here (BES3T 1.2):

* ``XTYP IDX`` is a linear axis built as
  ``XMIN + i * XWID / (XPTS - 1)``, i.e. ``linspace(XMIN, XMIN+XWID, XPTS)``
  with both endpoints included.
* ``IRFMT`` values ``C``/``S``/``I``/``F``/``D`` select int8/int16/int32/
  float32/float64 storage.
* ``BSEQ`` is ``BIG`` or ``LIT``.
* ``IKKF`` describes the value layout; only a single ``REAL`` value per point
  is accepted here.
* ``YPTS``/``ZPTS`` default to 1 when absent; ``YTYP``/``ZTYP`` must be absent
  or ``NODATA``.

Complex data, multidimensional data, ``IGD`` axis files, ``NTUP`` axes,
non-Gauss axis units, missing required metadata, truncated payloads and
trailing bytes are rejected explicitly. No scaling, offset, smoothing,
baseline correction, interpolation, filtering or fitting is applied.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from epr_workflow.plot_asc import (
    MIN_VALID_POINTS,
    ImportResult,
    combine_source_hashes,
)

_IRFMT = {
    "C": ("i1", 1),
    "S": ("i2", 2),
    "I": ("i4", 4),
    "F": ("f4", 4),
    "D": ("f8", 8),
}
_BSEQ = {"BIG": ">", "LIT": "<"}

#: Descriptor keys whose parsed values are recorded in provenance.
_CORE_KEYS = (
    "DSRC",
    "BSEQ",
    "IKKF",
    "XTYP",
    "YTYP",
    "ZTYP",
    "IRFMT",
    "XPTS",
    "YPTS",
    "ZPTS",
    "XMIN",
    "XWID",
    "XNAM",
    "XUNI",
    "IRNAM",
    "IRUNI",
    "TITL",
)


class Bes3tError(ValueError):
    """Base error for BES3T import failures.

    ``code`` is stable for GUI translation; ``context`` carries values used by
    translated messages and is also stored in the batch record.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


class Bes3tFormatError(Bes3tError):
    """The descriptor or companion file is missing, unreadable or malformed."""


class Bes3tDataError(Bes3tError):
    """The DTA payload or axis cannot be interpreted safely."""


def find_companion_dta(dsc_path: str | Path) -> Path:
    """Locate the ``.DTA`` companion with the same stem, case-insensitively.

    The search is restricted to the descriptor's directory. A same-named
    companion must resolve to exactly one file; other ``.DTA`` files with
    different stems are never paired automatically.
    """
    dsc = Path(dsc_path)
    if not dsc.is_file():
        raise FileNotFoundError(
            f"BES3T descriptor not found: {dsc}\n"
            "Select the .DSC file that belongs to the dataset."
        )
    if dsc.suffix.casefold() != ".dsc":
        raise Bes3tFormatError(
            f"Not a BES3T descriptor: {dsc.name}",
            code="bes3t_entry_not_dsc",
            context={"path": str(dsc)},
        )

    try:
        entries = list(dsc.parent.iterdir())
    except OSError as exc:
        raise Bes3tFormatError(
            f"Could not inspect the descriptor directory: {dsc.parent}",
            code="bes3t_directory_unreadable",
            context={"path": str(dsc.parent), "error": str(exc)},
        ) from exc

    matching = [
        path
        for path in entries
        if path.is_file()
        and path.suffix.casefold() == ".dta"
        and path.stem.casefold() == dsc.stem.casefold()
    ]
    if len(matching) == 1:
        return matching[0]
    if len(matching) > 1:
        names = ", ".join(sorted(path.name for path in matching))
        raise Bes3tFormatError(
            f"Multiple .DTA companions match {dsc.name}: {names}. "
            "Remove or rename the ambiguous companion.",
            code="bes3t_companion_ambiguous",
            context={"descriptor": dsc.name, "candidates": names},
        )

    other = [
        path.name
        for path in entries
        if path.is_file() and path.suffix.casefold() == ".dta"
    ]
    hint = ""
    if other:
        hint = (
            " Found .DTA file(s) with other stems: "
            + ", ".join(sorted(other))
            + ". BES3T requires matching stems; they were not paired."
        )
    raise Bes3tFormatError(
        f"Missing .DTA companion for {dsc.name}. Expected a file named "
        f"'{dsc.stem}.DTA' (case-insensitive) in {dsc.parent}.{hint}",
        code="bes3t_companion_missing",
        context={"descriptor": dsc.name, "directory": str(dsc.parent)},
    )


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return text


def _read_descriptor(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Bes3tFormatError(
            f"The BES3T descriptor is not valid UTF-8 text: {path.name}",
            code="bes3t_descriptor_decode",
            context={"path": str(path), "byte_offset": exc.start},
        ) from exc

    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        if stripped.startswith("#"):
            header = stripped[1:].strip()
            parts = header.split(None, 1)
            name = parts[0].upper() if parts else ""
            version = ""
            if len(parts) > 1 and parts[1]:
                version = parts[1].split()[0]
            current = {
                "line": line_no,
                "header": stripped,
                "name": name,
                "version": version,
                "records": [],
            }
            sections.append(current)
            continue
        if current is None:
            continue
        parts = stripped.split(None, 1)
        key = parts[0]
        value = parts[1].strip() if len(parts) > 1 else ""
        current["records"].append(
            {"line": line_no, "key": key, "value": value}
        )

    desc = next((s for s in sections if s["name"] == "DESC"), None)
    if desc is None:
        raise Bes3tFormatError(
            f"No #DESC section found in {path.name}; refusing to guess the "
            "BES3T layout.",
            code="bes3t_descriptor_missing",
            context={"path": str(path)},
        )

    by_key: dict[str, list[dict[str, Any]]] = {}
    for record in desc["records"]:
        by_key.setdefault(record["key"].upper(), []).append(record)

    return {
        "path": path,
        "text": text,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "version": desc["version"],
        "sections": sections,
        "desc": desc,
        "by_key": by_key,
    }


def _record(
    descriptor: dict[str, Any], key: str, *, required: bool = True
) -> dict[str, Any] | None:
    records = descriptor["by_key"].get(key)
    if not records:
        if not required:
            return None
        raise Bes3tFormatError(
            f"Required BES3T parameter {key} is missing from the #DESC "
            "section.",
            code="bes3t_missing_parameter",
            context={"parameter": key, "descriptor": descriptor["path"].name},
        )
    if len(records) > 1:
        lines = ", ".join(str(record["line"]) for record in records)
        raise Bes3tFormatError(
            f"BES3T parameter {key} appears more than once (lines {lines}); "
            "refusing to choose an ambiguous value.",
            code="bes3t_duplicate_parameter",
            context={"parameter": key, "lines": lines},
        )
    return records[0]


def _text(
    descriptor: dict[str, Any], key: str, *, required: bool = True
) -> str | None:
    record = _record(descriptor, key, required=required)
    if record is None:
        return None
    return _unquote(record["value"])


def _parse_int(value: str, key: str, descriptor: dict[str, Any]) -> int:
    try:
        number = int(value, 10)
    except (TypeError, ValueError) as exc:
        raise Bes3tFormatError(
            f"BES3T parameter {key} must be an integer; got {value!r}.",
            code="bes3t_invalid_parameter",
            context={"parameter": key, "value": value},
        ) from exc
    return number


def _parse_float(value: str, key: str, descriptor: dict[str, Any]) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise Bes3tFormatError(
            f"BES3T parameter {key} must be a number; got {value!r}.",
            code="bes3t_invalid_parameter",
            context={"parameter": key, "value": value},
        ) from exc
    if not np.isfinite(number):
        raise Bes3tFormatError(
            f"BES3T parameter {key} must be finite; got {value!r}.",
            code="bes3t_invalid_parameter",
            context={"parameter": key, "value": value},
        )
    return number


def _split_codes(value: str) -> list[str]:
    return [part.strip().upper() for part in value.split(",") if part.strip()]


def _read_dta(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise Bes3tFormatError(
            f"Could not read the .DTA companion: {path}",
            code="bes3t_data_unreadable",
            context={"path": str(path), "error": str(exc)},
        ) from exc


def read_bes3t(path: str | Path) -> ImportResult:
    """Read a one-dimensional, real-valued BES3T dataset.

    ``path`` must be the ``.DSC`` descriptor. The matching ``.DTA`` is located
    case-insensitively and both files are opened read-only, hashed, and
    validated. Unsupported layouts raise :class:`Bes3tError` subclasses with a
    stable ``code``.
    """
    dsc_path = Path(path)
    dta_path = find_companion_dta(dsc_path)
    descriptor = _read_descriptor(dsc_path)
    by_key = descriptor["by_key"]

    bseq_text = _text(descriptor, "BSEQ")
    assert bseq_text is not None
    byte_order = bseq_text.upper()
    if byte_order not in _BSEQ:
        raise Bes3tFormatError(
            f"Unsupported BES3T byte order BSEQ={bseq_text!r}; expected BIG "
            "or LIT.",
            code="bes3t_unsupported_byte_order",
            context={"parameter": "BSEQ", "value": bseq_text},
        )

    ikkf_text = _text(descriptor, "IKKF")
    assert ikkf_text is not None
    ikkf = _split_codes(ikkf_text)
    if not ikkf:
        raise Bes3tFormatError(
            "BES3T IKKF is empty; the value layout is undefined.",
            code="bes3t_invalid_parameter",
            context={"parameter": "IKKF", "value": ikkf_text},
        )
    if any(code == "CPLX" for code in ikkf):
        raise Bes3tDataError(
            "Complex-valued BES3T data are not supported in this release.",
            code="bes3t_unsupported_complex",
            context={"parameter": "IKKF", "value": ikkf_text},
        )
    if len(ikkf) != 1 or ikkf[0] != "REAL":
        raise Bes3tDataError(
            f"Unsupported BES3T IKKF={ikkf_text!r}; only one real value per "
            "point is supported.",
            code="bes3t_unsupported_data_kind",
            context={"parameter": "IKKF", "value": ikkf_text},
        )

    irfmt_text = _text(descriptor, "IRFMT")
    assert irfmt_text is not None
    irfmt_parts = _split_codes(irfmt_text)
    if len(irfmt_parts) != 1:
        raise Bes3tDataError(
            f"Unsupported IRFMT={irfmt_text!r}; exactly one real numeric "
            "format is required.",
            code="bes3t_unsupported_data_kind",
            context={"parameter": "IRFMT", "value": irfmt_text},
        )
    irfmt = irfmt_parts[0]
    try:
        dtype_code, itemsize = _IRFMT[irfmt]
    except KeyError as exc:
        raise Bes3tDataError(
            f"Unsupported BES3T numeric format IRFMT={irfmt!r}.",
            code="bes3t_unsupported_format",
            context={"parameter": "IRFMT", "value": irfmt},
        ) from exc

    xtyp_text = _text(descriptor, "XTYP")
    assert xtyp_text is not None
    xtyp = xtyp_text.upper()
    if xtyp != "IDX":
        raise Bes3tDataError(
            f"Unsupported BES3T axis type XTYP={xtyp_text!r}; this release "
            "supports only IDX (linear) axes. IGD axis files and NTUP axes "
            "are not implemented.",
            code="bes3t_unsupported_axis",
            context={"parameter": "XTYP", "value": xtyp_text},
        )

    xpts_text = _text(descriptor, "XPTS")
    assert xpts_text is not None
    xpts = _parse_int(xpts_text, "XPTS", descriptor)
    if xpts < MIN_VALID_POINTS:
        raise Bes3tDataError(
            f"BES3T XPTS={xpts} is too small; at least {MIN_VALID_POINTS} "
            "points are required to plot a spectrum.",
            code="bes3t_axis_invalid",
            context={
                "parameter": "XPTS",
                "value": xpts,
                "required": MIN_VALID_POINTS,
            },
        )

    xmin_text = _text(descriptor, "XMIN")
    xwid_text = _text(descriptor, "XWID")
    assert xmin_text is not None and xwid_text is not None
    xmin = _parse_float(xmin_text, "XMIN", descriptor)
    xwid = _parse_float(xwid_text, "XWID", descriptor)
    if xwid == 0.0:
        raise Bes3tDataError(
            "BES3T XWID is zero; the field axis would contain duplicate "
            "values.",
            code="bes3t_axis_invalid",
            context={"parameter": "XWID", "value": xwid},
        )

    xuni_text = _text(descriptor, "XUNI")
    assert xuni_text is not None
    xuni = xuni_text.strip().upper()
    if xuni != "G":
        raise Bes3tDataError(
            f"Unsupported BES3T axis unit XUNI={xuni_text!r}; this release "
            "supports only Gauss (XUNI='G'). No unit conversion is applied.",
            code="bes3t_unsupported_units",
            context={"parameter": "XUNI", "value": xuni_text},
        )

    inferred: dict[str, Any] = {}
    dimensions: list[int] = []
    for key, default in (("YPTS", 1), ("ZPTS", 1)):
        text = _text(descriptor, key, required=False)
        if text is None:
            dimensions.append(default)
            inferred[key] = default
        else:
            number = _parse_int(text, key, descriptor)
            if number < 1:
                raise Bes3tFormatError(
                    f"BES3T parameter {key} must be at least 1; got {number}.",
                    code="bes3t_invalid_parameter",
                    context={"parameter": key, "value": number},
                )
            dimensions.append(number)

    for key in ("YTYP", "ZTYP"):
        text = _text(descriptor, key, required=False)
        if text is None:
            inferred[key] = "NODATA"
            continue
        if text.strip().upper() != "NODATA":
            raise Bes3tDataError(
                f"Unsupported multidimensional BES3T dataset: {key}="
                f"{text!r}. Only one-dimensional data are supported.",
                code="bes3t_unsupported_multidimensional",
                context={"parameter": key, "value": text},
            )

    if dimensions[0] != 1 or dimensions[1] != 1:
        raise Bes3tDataError(
            "Unsupported multidimensional BES3T dataset: YPTS="
            f"{dimensions[0]}, ZPTS={dimensions[1]}. Only one-dimensional "
            "data are supported.",
            code="bes3t_unsupported_multidimensional",
            context={"YPTS": dimensions[0], "ZPTS": dimensions[1]},
        )

    dta_bytes = _read_dta(dta_path)
    expected_bytes = xpts * itemsize
    actual_bytes = len(dta_bytes)
    if actual_bytes < expected_bytes:
        raise Bes3tDataError(
            f"Truncated BES3T DTA payload: expected {expected_bytes} bytes "
            f"for {xpts} points at {itemsize} bytes/point, found "
            f"{actual_bytes}.",
            code="bes3t_truncated",
            context={
                "expected_bytes": expected_bytes,
                "actual_bytes": actual_bytes,
                "points": xpts,
            },
        )
    if actual_bytes > expected_bytes:
        raise Bes3tDataError(
            f"Unexpected trailing bytes in BES3T DTA payload: expected "
            f"{expected_bytes} bytes, found {actual_bytes}. The data were not "
            "truncated to make the file load.",
            code="bes3t_trailing_bytes",
            context={
                "expected_bytes": expected_bytes,
                "actual_bytes": actual_bytes,
                "extra_bytes": actual_bytes - expected_bytes,
            },
        )

    dtype = np.dtype(_BSEQ[byte_order] + dtype_code)
    values = np.frombuffer(dta_bytes, dtype=dtype, count=xpts).astype(
        np.float64
    )
    if not np.all(np.isfinite(values)):
        bad = int(np.flatnonzero(~np.isfinite(values))[0])
        raise Bes3tDataError(
            f"Non-finite intensity at BES3T point index {bad} (zero-based). "
            "The dataset was rejected rather than silently corrected.",
            code="bes3t_nonfinite",
            context={"index": bad, "value": str(values[bad])},
        )

    axis = np.linspace(
        xmin, xmin + xwid, xpts, endpoint=True, dtype=np.float64
    )
    if not np.all(np.isfinite(axis)):
        raise Bes3tDataError(
            "The constructed BES3T axis contains non-finite values.",
            code="bes3t_axis_invalid",
            context={"XMIN": xmin, "XWID": xwid, "XPTS": xpts},
        )
    steps = np.diff(axis)
    if np.all(steps > 0):
        field_order = "strictly increasing"
    elif np.all(steps < 0):
        field_order = "strictly decreasing"
    else:
        raise Bes3tDataError(
            "The constructed BES3T axis is not strictly monotonic; the "
            "dataset was rejected.",
            code="bes3t_axis_invalid",
            context={"XMIN": xmin, "XWID": xwid, "XPTS": xpts},
        )

    data = pd.DataFrame(
        {
            "index": np.arange(1, xpts + 1, dtype=np.int64),
            "field_G": axis,
            "intensity": values,
        }
    )

    warnings: list[str] = []
    if xwid < 0:
        warnings.append(
            "BES3T XWID is negative; the field axis is strictly decreasing "
            "as declared. No direction change or sorting was applied."
        )
    dsrc = _text(descriptor, "DSRC", required=False)
    if dsrc is not None and dsrc.strip().upper() != "EXP":
        warnings.append(
            f"BES3T DSRC={dsrc!r} does not indicate an experimental dataset; "
            "the dataset was imported as declared."
        )

    dsc_sha = descriptor["sha256"]
    dta_sha = hashlib.sha256(dta_bytes).hexdigest()
    source_hashes = {"descriptor": dsc_sha, "data": dta_sha}
    combined_sha = combine_source_hashes("BES3T", source_hashes)

    xnam = _text(descriptor, "XNAM", required=False)
    irnam = _text(descriptor, "IRNAM", required=False)
    iruni = _text(descriptor, "IRUNI", required=False)
    titl = _text(descriptor, "TITL", required=False)

    parsed_parameters: dict[str, Any] = {
        "BSEQ": byte_order,
        "IKKF": ikkf[0],
        "IRFMT": irfmt,
        "XTYP": xtyp,
        "XPTS": xpts,
        "XMIN": xmin,
        "XWID": xwid,
        "XUNI": xuni,
    }
    for key, value in (
        ("DSRC", dsrc),
        ("XNAM", xnam),
        ("IRNAM", irnam),
        ("IRUNI", iruni),
        ("TITL", titl),
    ):
        if value is not None:
            parsed_parameters[key] = value
    for key in ("YPTS", "ZPTS"):
        if key not in inferred:
            text = _text(descriptor, key, required=False)
            if text is not None:
                parsed_parameters[key] = _parse_int(text, key, descriptor)
    for key in ("YTYP", "ZTYP"):
        if key not in inferred:
            text = _text(descriptor, key, required=False)
            if text is not None:
                parsed_parameters[key] = text.strip().upper()

    axis_info = {
        "type": "IDX",
        "name": xnam,
        "unit": "G",
        "points": xpts,
        "XMIN": xmin,
        "XWID": xwid,
        "endpoint_included": True,
        "construction": "linspace(XMIN, XMIN + XWID, XPTS)",
        "first": float(axis[0]),
        "last": float(axis[-1]),
        "step": float(axis[1] - axis[0]),
        "field_order": field_order,
    }
    binary_info = {
        "IKKF": ikkf[0],
        "IRFMT": irfmt,
        "numpy_dtype": dtype.str,
        "byte_order": byte_order,
        "itemsize": itemsize,
        "values_per_point": 1,
        "dimensions": {"XPTS": xpts, "YPTS": 1, "ZPTS": 1},
        "expected_bytes": expected_bytes,
        "actual_bytes": actual_bytes,
    }
    raw_parameters = [
        {
            "key": record["key"],
            "value": record["value"],
            "line": record["line"],
        }
        for record in descriptor["desc"]["records"]
        if record["key"].upper() in _CORE_KEYS
    ]
    format_assumptions = [
        "The dataset is a paired BES3T .DSC/.DTA file; the .DSC descriptor is "
        "the entry point and the .DTA has the same stem (case-insensitive).",
        "Only one-dimensional, real-valued BES3T data are supported.",
        "The X axis is XTYP=IDX and is constructed as "
        "linspace(XMIN, XMIN+XWID, XPTS); both endpoints are included.",
        "XUNI declares Gauss (G); no axis unit conversion was applied.",
        "Intensities are decoded using IRFMT and BSEQ without scaling, "
        "offset, normalization, phase correction or baseline removal.",
        "No smoothing, interpolation, filtering, peak removal or curve "
        "fitting was applied.",
        "The source files were opened read-only and their SHA-256 hashes are "
        "recorded before and after export.",
    ]
    if dtype.kind in "iu":
        format_assumptions.append(
            "Integer intensities were represented as float64 in the common "
            "data model; their numerical values were not changed."
        )
    if xwid < 0:
        format_assumptions.append(
            "XWID is negative, so the field axis is decreasing exactly as "
            "declared; no reversal or sorting was applied."
        )

    format_metadata = {
        "descriptor_version": descriptor["version"],
        "descriptor_text": descriptor["text"],
        "descriptor_sections": descriptor["sections"],
        "parsed_parameters": parsed_parameters,
        "inferred_parameters": inferred,
        "raw_parameters": raw_parameters,
        "axis": axis_info,
        "binary": binary_info,
        "diagnostics": list(warnings),
    }

    return ImportResult(
        source=dsc_path,
        data=data,
        rejected_rows=[],
        warnings=warnings,
        sha256=combined_sha,
        file_size_bytes=descriptor["size_bytes"] + actual_bytes,
        field_order=field_order,
        missing_value_count=0,
        nonfinite_value_count=0,
        duplicate_field_count=0,
        index_continuity="consecutive",
        source_format="BES3T",
        source_files={
            "descriptor": str(dsc_path.resolve()),
            "data": str(dta_path.resolve()),
        },
        source_hashes=source_hashes,
        sha256_definition=(
            "SHA-256 of b'BES3T:' + descriptor SHA-256 + b':' + data "
            "SHA-256."
        ),
        format_metadata=format_metadata,
        format_assumptions=format_assumptions,
    )
