"""Import, validate and plot a Bruker Xepr ASCII (``.ASC``) CW-EPR spectrum.

This module only performs *data import, validation, plotting and export*.
It never modifies the source file and never smooths, baselines, normalises,
fits or outlier-corrects the signal.

The supported format is the whitespace-separated Xepr export::

    index           Field [G]        Intensity []

         1                3280             400.088
         2              3280.1             272.312
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("epr_workflow")

#: Project root (``D:\EPR workflow``) resolved from this file's location.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: Minimum number of valid rows required before a spectrum may be plotted.
MIN_VALID_POINTS = 3

#: Column keywords required in the ASC header, in this order.
EXPECTED_COLUMNS = ("index", "field", "intensity")

#: Name of the output dataframe columns produced by :func:`read_asc`.
REQUIRED_COLUMNS = ["index", "field_G", "intensity"]

#: Maximum number of rejected rows echoed into the JSON report.
MAX_REPORTED_ROWS = 50

#: Plot configuration recorded in the metadata for each run.
DEFAULT_FIGSIZE = (8.0, 5.0)
DEFAULT_DPI = 300
DEFAULT_LINEWIDTH = 1.0


class AscFormatError(ValueError):
    """The file does not look like a supported Xepr ASCII export."""


class AscDataError(ValueError):
    """The file parses but its content cannot be plotted safely."""


@dataclass
class ImportResult:
    """Everything learned while reading one supported dataset."""

    source: Path
    data: pd.DataFrame
    rejected_rows: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sha256: str = ""
    file_size_bytes: int = 0
    field_order: str = "unknown"
    #: Rows with fewer than 3 whitespace-separated columns. This is a *row*
    #: count, not a count of individual missing cells.
    missing_value_count: int = 0
    nonfinite_value_count: int = 0
    duplicate_field_count: int = 0
    index_continuity: str = "not checked"
    #: Optional provenance used by format-specific loaders (currently BES3T).
    #: ASC imports keep the historical behaviour and leave these at defaults.
    source_format: str = "ASC"
    source_files: dict[str, str] = field(default_factory=dict)
    source_hashes: dict[str, str] = field(default_factory=dict)
    sha256_definition: str = "SHA-256 of the source file bytes."
    format_metadata: dict[str, Any] = field(default_factory=dict)
    format_assumptions: list[str] = field(default_factory=list)


def _is_finite_row(values: tuple[float, float, float]) -> bool:
    return all(np.isfinite(v) for v in values)


def read_asc(path: str | Path, *, allow_non_monotonic: bool = False) -> ImportResult:
    """Read and validate an Xepr-exported ASCII EPR file.

    Parameters
    ----------
    path
        Path to the ``.ASC`` file. It is opened read-only.
    allow_non_monotonic
        If ``False`` (default), a non-monotonic field axis raises
        :class:`AscDataError`, because plotting it would draw a misleading
        spectrum. Set to ``True`` only when you know why the axis is
        unordered.

    Returns
    -------
    ImportResult
        Valid rows (original row order preserved), rejected rows, warnings
        and file integrity information.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    AscFormatError
        If the header is missing or its columns are in an unexpected order.
    AscDataError
        If too few rows are valid, or the field axis is non-monotonic.
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
    if header_index > 0 and any(ln.strip() for ln in lines[:header_index]):
        warnings.append(
            f"{header_index} non-blank line(s) before the header were ignored."
        )

    _check_column_order(header_tokens, path)

    records: list[tuple[float, float, float]] = []
    rejected: list[dict[str, Any]] = []
    missing_count = 0
    nonfinite_count = 0

    for line_no, line in enumerate(lines[header_index + 1 :], start=header_index + 2):
        stripped = line.strip()
        if not stripped:
            continue  # blank lines are legal separators

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

    # Keep a genuinely integer row index as an integer so the CSV does not
    # turn "1" into "1.0". Non-integral values are never rounded.
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

    # Count duplicate field values before the monotonicity decision so the
    # diagnostic below can distinguish repeated values from decreasing steps.
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

    index_continuity = _check_index_continuity(data["index"].to_numpy(), warnings)

    if rejected:
        shown = ", ".join(str(r["line"]) for r in rejected[:10])
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

    return ImportResult(
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


def read_dataset(
    path: str | Path, *, allow_non_monotonic: bool = False
) -> ImportResult:
    """Read one supported dataset and return a validated :class:`ImportResult`.

    The entry point determines the format: ``.ASC`` uses :func:`read_asc`,
    ``.DSC`` uses the BES3T loader, and ``.DTA`` is explicitly rejected because
    it is a companion file, not an independent dataset. Extension matching is
    case-insensitive.
    """
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix == ".dsc":
        # Lazy import avoids a module cycle: the BES3T loader reuses
        # ImportResult from this module.
        from epr_workflow.bes3t import read_bes3t

        return read_bes3t(path)
    if suffix == ".dta":
        raise ValueError(
            f"{path.name} is a BES3T binary companion; open the matching "
            ".DSC descriptor instead."
        )
    return read_asc(path, allow_non_monotonic=allow_non_monotonic)


def _find_header(lines: list[str], path: Path) -> tuple[int, list[str]]:
    """Return ``(line_index, tokens)`` for the first recognisable header."""
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
    """Refuse to import if the three expected columns are ordered differently."""
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
    """Diagnose gaps in a running row index without touching the data.

    The check only applies when the index behaves like a simple counter
    (integral and strictly increasing). No assumption is made that the
    numbering starts at 1, and rows are never renumbered, sorted or removed.
    """
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


def build_metadata(
    result: ImportResult,
    *,
    raw_file_unchanged: bool,
    outputs: dict[str, str] | None = None,
    processing: dict[str, Any] | None = None,
    source_hashes_after: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble the JSON report for one import.

    ``outputs`` and ``processing`` describe the files produced and the
    configuration used *by the current run*; they make no claim about future
    runs. BES3T imports add provenance blocks; ASC reports retain their
    historical structure.
    """
    import matplotlib

    data = result.data
    signal = data["intensity"].to_numpy()
    field = data["field_G"].to_numpy()

    asc_assumptions = [
        "The file is a whitespace-separated Xepr ASCII export with a "
        "header containing 'index', 'Field [G]' and 'Intensity []'.",
        "Column 1 is a row index and is not a physical quantity.",
        "Column 2 is magnetic field in Gauss (G).",
        "Column 3 intensity has no documented unit; values are reported "
        "in original (arbitrary) units.",
        "No baseline correction, smoothing, normalisation, outlier removal "
        "or curve fitting was applied.",
    ]

    metadata: dict[str, Any] = {
        "source_file": result.source.name,
        "source_path": str(result.source),
        "file_size_bytes": int(result.file_size_bytes),
        "sha256": result.sha256,
        "import_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "software_versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "matplotlib": matplotlib.__version__,
        },
        "data": {
            "valid_points": int(len(data)),
            "rejected_rows": int(len(result.rejected_rows)),
            "missing_value_count": int(result.missing_value_count),
            "missing_value_count_definition": (
                "Number of data rows with fewer than 3 whitespace-separated "
                "columns. This is a row count, not a count of individual "
                "missing cells."
            ),
            "non_finite_value_count": int(result.nonfinite_value_count),
            "duplicate_field_count": int(result.duplicate_field_count),
            "field_min_G": float(field.min()),
            "field_max_G": float(field.max()),
            "field_span_G": float(field.max() - field.min()),
            "field_order": result.field_order,
            "index_continuity": result.index_continuity,
            "signal_min": float(signal.min()),
            "signal_max": float(signal.max()),
            "signal_mean": float(signal.mean()),
            "signal_std": float(signal.std(ddof=1)) if len(signal) > 1 else 0.0,
            "signal_std_ddof": 1,
        },
        "outputs": dict(outputs or {}),
        "processing": dict(processing or {}),
        "rejected_row_details": result.rejected_rows[:MAX_REPORTED_ROWS],
        "rejected_row_details_truncated": len(result.rejected_rows) > MAX_REPORTED_ROWS,
        "validation_warnings": result.warnings,
        "assumptions": asc_assumptions,
        "raw_file_unchanged": raw_file_unchanged,
    }

    if result.source_format != "ASC":
        metadata["source_format"] = result.source_format
        metadata["sha256_definition"] = result.sha256_definition
        metadata["file_size_bytes_definition"] = (
            "Total bytes of all source files in the BES3T descriptor/data "
            "pair."
        )
        metadata["source_files"] = _source_file_entries(
            result, source_hashes_after
        )
        metadata["format_metadata"] = result.format_metadata
        metadata["assumptions"] = list(result.format_assumptions)

    return metadata


def _source_file_entries(
    result: ImportResult,
    source_hashes_after: dict[str, str] | None,
) -> list[dict[str, Any]]:
    """Describe every source file with before/after hashes and sizes."""
    entries: list[dict[str, Any]] = []
    for role, path_text in result.source_files.items():
        path = Path(path_text)
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        entry: dict[str, Any] = {
            "role": role,
            "path": str(path.resolve()),
            "filename": path.name,
            "sha256": result.source_hashes.get(role),
            "size_bytes": size,
        }
        if source_hashes_after is not None:
            after = source_hashes_after.get(role)
            entry["sha256_after"] = after
            entry["unchanged"] = bool(
                after and result.source_hashes.get(role) == after
            )
        entries.append(entry)
    return entries


def plot_spectrum(
    data: pd.DataFrame,
    output_path: str | Path,
    *,
    title: str,
    dpi: int = DEFAULT_DPI,
    show: bool = False,
    figsize: tuple[float, float] = DEFAULT_FIGSIZE,
    line_width: float = DEFAULT_LINEWIDTH,
) -> Path:
    """Save a plain raw spectrum and optionally display it.

    The magnetic-field axis is never reversed and no signal processing is
    applied.
    """
    import matplotlib

    if not show:
        matplotlib.use("Agg", force=True)  # safe in headless environments

    import matplotlib.pyplot as plt

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=figsize)
    ax.plot(
        data["field_G"].to_numpy(),
        data["intensity"].to_numpy(),
        color="#1f4e79",
        linewidth=line_width,
    )
    ax.set_xlabel("Magnetic field (G)")
    ax.set_ylabel("Intensity (original units)")
    ax.set_title(title)
    ax.grid(True, which="major", color="#b0b0b0", alpha=0.35, linewidth=0.6)
    ax.tick_params(direction="out")

    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    if show:
        plt.show()
    plt.close(fig)

    LOGGER.info("Figure saved: %s (%.0f dpi)", output_path, dpi)
    return output_path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _processing_record() -> dict[str, Any]:
    """Describe the plotting/processing configuration used by this run."""
    return {
        "applied_in_this_run": {
            "smoothing": False,
            "baseline_correction": False,
            "normalisation": False,
            "field_axis_reversal": False,
        },
        "plot": {
            "figsize_inch": list(DEFAULT_FIGSIZE),
            "dpi": DEFAULT_DPI,
            "line_width": DEFAULT_LINEWIDTH,
        },
        "description": (
            "Configuration actually used for this import run. These flags "
            "describe this run only and are not a guarantee for future runs "
            "or other files."
        ),
    }


def resolve_output_paths(
    stem: str,
    output_base: Path,
    *,
    figure: Path | None = None,
    csv_path: Path | None = None,
    json_path: Path | None = None,
) -> dict[str, Path]:
    """Return the CSV/PNG/JSON targets for one input file.

    Defaults follow ``<output_base>/tables``, ``<output_base>/figures`` and
    ``<output_base>/logs``.
    """
    return {
        "csv": csv_path or output_base / "tables" / f"{stem}_raw.csv",
        "figure": figure or output_base / "figures" / f"{stem}_raw.png",
        "metadata_json": json_path or output_base / "logs" / f"{stem}_metadata.json",
    }


def _guard_output_paths(input_path: Path, paths: dict[str, Path]) -> None:
    """Refuse to write outputs into ``data/raw`` or over the source file."""
    raw_dir = (PROJECT_ROOT / "data" / "raw").resolve()
    source = input_path.resolve()
    for label, path in paths.items():
        target = Path(path).resolve()
        if target == source:
            raise ValueError(
                f"Refusing to write the {label} output over the source file: {target}"
            )
        try:
            target.relative_to(raw_dir)
        except ValueError:
            continue
        raise ValueError(
            f"Refusing to write the {label} output inside data/raw: {target}"
        )


def guard_output_paths(input_path: Path, paths: dict[str, Path]) -> None:
    """Public wrapper around :func:`_guard_output_paths`.

    Other exporters (for example processed-data exports) must apply the same
    protection: never write over the source file and never write into
    ``data/raw``.
    """
    _guard_output_paths(input_path, paths)


def combine_source_hashes(
    source_format: str, source_hashes: dict[str, str]
) -> str:
    """Return the canonical combined hash for an imported dataset.

    ASC files have one source file. BES3T datasets have a descriptor and a
    binary data file; both hashes are combined in a documented, deterministic
    order so that a change to either companion invalidates sessions and
    processed exports.
    """
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


def verify_source_integrity(
    result: ImportResult,
) -> tuple[bool, dict[str, str]]:
    """Re-hash every imported source file and compare it with the import.

    Returns ``(unchanged, actual_hashes)``. Missing files yield an empty hash
    for that role and therefore fail the comparison instead of raising.
    """
    files = dict(result.source_files)
    if not files:
        files = {"source": str(result.source)}
    expected = dict(result.source_hashes)
    if not expected and files == {"source": str(result.source)}:
        expected = {"source": result.sha256}

    actual: dict[str, str] = {}
    for role, path in files.items():
        try:
            actual[role] = _sha256(Path(path))
        except OSError:
            actual[role] = ""

    try:
        combined = combine_source_hashes(result.source_format, actual)
    except ValueError:
        combined = ""
    unchanged = bool(
        actual == expected
        and combined
        and combined == result.sha256
    )
    return unchanged, actual


def guard_import_output_paths(
    result: ImportResult, paths: dict[str, Path]
) -> None:
    """Protect every source file of an import from being used as output."""
    source_paths = [result.source]
    source_paths.extend(Path(path) for path in result.source_files.values())
    seen: set[Path] = set()
    for source in source_paths:
        resolved = source.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        guard_output_paths(source, paths)


def raw_export_frame(result: ImportResult) -> pd.DataFrame:
    """Return the raw CSV frame, adding format identity for BES3T only.

    ASC CSV output remains the historical three-column frame
    (``index, field_G, intensity``). BES3T output appends a constant
    ``source_format`` column so a CSV file can be identified independently of
    its filename and JSON companion.
    """
    frame = result.data.copy()
    if result.source_format != "ASC":
        frame["source_format"] = result.source_format
    return frame


def _empty_record(input_path: Path, stem: str) -> dict[str, Any]:
    """A per-file batch record with every field present."""
    return {
        "source_file": input_path.name,
        "source_path": str(input_path.resolve()),
        "output_stem": stem,
        "status": "failed",
        "error": None,
        "validation_warnings": [],
        "valid_points": None,
        "field_min_G": None,
        "field_max_G": None,
        "field_order": None,
        "source_sha256_before": None,
        "source_sha256_after": None,
        "source_unchanged": False,
        "outputs": {},
    }


def _process_one(
    input_path: Path,
    *,
    output_base: Path,
    stem: str,
    figure: Path | None = None,
    csv_path: Path | None = None,
    json_path: Path | None = None,
    overwrite: bool = False,
    allow_non_monotonic: bool = False,
    show: bool = False,
) -> dict[str, Any]:
    """Import, plot and export one ASC/BES3T dataset, returning a record.

    Exceptions are converted into a ``failed`` record so that batch mode can
    continue with the remaining files.
    """
    paths = resolve_output_paths(
        stem, output_base, figure=figure, csv_path=csv_path, json_path=json_path
    )
    record = _empty_record(input_path, stem)

    existing = [str(p) for p in paths.values() if p.exists()]
    if existing and not overwrite:
        record["error"] = (
            "Output file(s) already exist: "
            + ", ".join(existing)
            + ". Use --overwrite to replace them, or choose another --output-dir."
        )
        return record

    try:
        result = read_dataset(
            input_path, allow_non_monotonic=allow_non_monotonic
        )
        guard_import_output_paths(result, paths)
    except Exception as exc:  # per-file isolation: one bad file must not stop a batch
        record["error"] = f"{type(exc).__name__}: {exc}"
        code = getattr(exc, "code", None)
        if code:
            record["error_code"] = code
            record["error_context"] = dict(getattr(exc, "context", {}))
        return record

    record["source_sha256_before"] = result.sha256
    if result.source_format != "ASC":
        record["source_format"] = result.source_format
        record["source_files"] = dict(result.source_files)
        record["source_hashes_before"] = dict(result.source_hashes)

    try:
        paths["csv"].parent.mkdir(parents=True, exist_ok=True)
        raw_export_frame(result).to_csv(paths["csv"], index=False)
        LOGGER.info("Data saved: %s (%d rows)", paths["csv"], len(result.data))

        plot_spectrum(
            result.data,
            paths["figure"],
            title=f"{input_path.stem} - Raw CW-EPR Spectrum",
            show=show,
            figsize=DEFAULT_FIGSIZE,
            dpi=DEFAULT_DPI,
            line_width=DEFAULT_LINEWIDTH,
        )

        unchanged, hashes_after = verify_source_integrity(result)
        record["source_unchanged"] = unchanged
        if result.source_format != "ASC":
            record["source_hashes_after"] = hashes_after
        try:
            record["source_sha256_after"] = combine_source_hashes(
                result.source_format, hashes_after
            )
        except ValueError:
            record["source_sha256_after"] = None
        if not record["source_unchanged"]:
            LOGGER.error("Source file changed during processing: %s", input_path)

        outputs = {key: str(path.resolve()) for key, path in paths.items()}
        metadata = build_metadata(
            result,
            raw_file_unchanged=record["source_unchanged"],
            outputs=outputs,
            processing=_processing_record(),
            source_hashes_after=hashes_after,
        )
        paths["metadata_json"].parent.mkdir(parents=True, exist_ok=True)
        paths["metadata_json"].write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        LOGGER.info("Metadata saved: %s", paths["metadata_json"])
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        code = getattr(exc, "code", None)
        if code:
            record["error_code"] = code
            record["error_context"] = dict(getattr(exc, "context", {}))
        record["validation_warnings"] = list(result.warnings)
        record["outputs"] = {
            key: str(path.resolve()) for key, path in paths.items() if path.exists()
        }
        return record

    record["outputs"] = outputs
    record["validation_warnings"] = list(result.warnings)
    record["valid_points"] = int(len(result.data))
    record["field_min_G"] = float(result.data["field_G"].min())
    record["field_max_G"] = float(result.data["field_G"].max())
    record["field_order"] = result.field_order

    if not record["source_unchanged"]:
        record["status"] = "failed"
        record["error"] = "Source file changed during processing."
    elif result.warnings:
        record["status"] = "success_with_warnings"
    else:
        record["status"] = "success"
    return record


def discover_asc_files(input_dir: str | Path, *, recursive: bool = False) -> list[Path]:
    """Return ``.ASC`` files in *input_dir* in deterministic order.

    The extension match is case-insensitive. Sub-directories are only searched
    when *recursive* is true.
    """
    input_dir = Path(input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_dir}")

    iterator = input_dir.rglob("*") if recursive else input_dir.glob("*")
    files = [
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() == ".asc"
    ]

    def sort_key(path: Path) -> tuple[str, str]:
        relative = path.relative_to(input_dir).as_posix()
        return relative.casefold(), relative

    return sorted(files, key=sort_key)


def discover_dataset_files(
    input_dir: str | Path, *, recursive: bool = False
) -> list[Path]:
    """Return ``.ASC`` and ``.DSC`` entry points in deterministic order.

    ``.DTA`` files are intentionally excluded: they are BES3T companions and
    must never be treated as independent datasets.
    """
    input_dir = Path(input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_dir}")

    iterator = input_dir.rglob("*") if recursive else input_dir.glob("*")
    files = [
        path
        for path in iterator
        if path.is_file() and path.suffix.casefold() in {".asc", ".dsc"}
    ]

    def sort_key(path: Path) -> tuple[str, str]:
        relative = path.relative_to(input_dir).as_posix()
        return relative.casefold(), relative

    return sorted(files, key=sort_key)


def _output_stem(path: Path, input_dir: Path, recursive: bool) -> str:
    """Build an output basename from the input filename (and sub-folders)."""
    relative = path.relative_to(input_dir)
    if recursive:
        return "_".join(relative.with_suffix("").parts)
    return relative.stem


def _build_batch_summary(
    *,
    input_dir: Path,
    output_dir: Path,
    recursive: bool,
    records: list[dict[str, Any]],
    errors: list[str],
) -> dict[str, Any]:
    success = sum(1 for r in records if r["status"] == "success")
    with_warnings = sum(
        1 for r in records if r["status"] == "success_with_warnings"
    )
    failed = sum(1 for r in records if r["status"] == "failed")

    if errors and not records:
        overall = "failed"
    elif failed == 0 and with_warnings == 0:
        overall = "success"
    elif failed == 0:
        overall = "success_with_warnings"
    elif success + with_warnings == 0:
        overall = "failed"
    else:
        overall = "partial_failure"

    return {
        "batch": {
            "processed_at_utc": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
            "timezone": "All timestamps are UTC (datetime.now(timezone.utc)).",
            "input_dir": str(input_dir.resolve()),
            "output_dir": str(output_dir.resolve()),
            "recursive": recursive,
            "files_discovered": len(records),
            "files_succeeded": success,
            "files_succeeded_with_warnings": with_warnings,
            "files_failed": failed,
            "overall_status": overall,
            "status_definitions": {
                "success": "Imported, plotted and exported with no validation warnings.",
                "success_with_warnings": (
                    "Processed, but one or more validation warnings were reported; "
                    "inspect the per-file metadata."
                ),
                "failed": "Not processed or output could not be produced; see error.",
            },
            "errors": errors,
            "scientific_note": (
                "This summary reports processing status only. A completed run "
                "does not establish scientific validity of the data."
            ),
        },
        "files": records,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _print_batch_record(index: int, total: int, record: dict[str, Any]) -> None:
    label = record["status"].upper().replace("_", " ")
    print(f"[{index}/{total}] {label}: {record['source_file']}")
    if record["error"]:
        print(f"    error: {record['error']}")
    for warning in record["validation_warnings"][:5]:
        print(f"    warning: {warning}")


def run_single(args: argparse.Namespace) -> int:
    """Process one ASC file or one BES3T DSC entry point."""
    input_path = (
        Path(args.input)
        if args.input
        else PROJECT_ROOT / "data" / "raw" / "BSA3T275.ASC"
    )
    output_base = (
        Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "results"
    )

    record = _process_one(
        input_path,
        output_base=output_base,
        stem=input_path.stem,
        figure=args.figure,
        csv_path=args.csv_path,
        json_path=args.json_path,
        overwrite=args.overwrite,
        allow_non_monotonic=args.allow_non_monotonic,
        show=args.show,
    )

    if record["status"] == "failed":
        LOGGER.error("%s: %s", input_path, record["error"])
        return 1

    for warning in record["validation_warnings"]:
        LOGGER.warning("%s", warning)
    if record["status"] == "success_with_warnings":
        LOGGER.warning(
            "Completed with %d validation warning(s); see the metadata report.",
            len(record["validation_warnings"]),
        )

    print()
    print(f"Imported {record['valid_points']} valid data point(s) from {input_path.name}")
    print(
        f"Field range: {record['field_min_G']:.4f} - {record['field_max_G']:.4f} G "
        f"({record['field_order']})"
    )
    print(f"CSV      -> {record['outputs']['csv']}")
    print(f"Figure   -> {record['outputs']['figure']}")
    print(f"Metadata -> {record['outputs']['metadata_json']}")
    return 0


def batch_process_directory(
    input_dir: str | Path,
    output_base: str | Path,
    *,
    recursive: bool = False,
    overwrite: bool = False,
    allow_non_monotonic: bool = False,
) -> tuple[dict[str, Any], Path]:
    """Discover and process every ASC or BES3T DSC entry point.

    ``.DTA`` companion files are never treated as independent datasets.
    Per-file failures, discovery problems and validation warnings are captured
    in the summary's ``errors`` and per-file records; they do not raise.
    Raises :class:`FileExistsError` when the batch summary already exists and
    ``overwrite`` is False, and :class:`OSError` when the summary cannot be
    written.
    """
    input_dir = Path(input_dir)
    output_base = Path(output_base)
    summary_path = output_base / "logs" / "batch_summary.json"

    if summary_path.exists() and not overwrite:
        raise FileExistsError(
            f"Batch summary already exists: {summary_path}. "
            "Use --overwrite to replace it, or choose another --output-dir."
        )

    errors: list[str] = []
    try:
        files = discover_dataset_files(input_dir, recursive=recursive)
    except (FileNotFoundError, NotADirectoryError) as exc:
        errors.append(str(exc))
        files = []

    if not errors and not files:
        errors.append(
            f"No .ASC files or .DSC datasets found in {input_dir} "
            f"(recursive={recursive})."
        )

    # Detect output-basename collisions before writing anything.
    by_stem: dict[str, list[Path]] = {}
    for path in files:
        stem = _output_stem(path, input_dir, recursive)
        by_stem.setdefault(stem.casefold(), []).append(path)

    records: list[dict[str, Any]] = []
    total = len(files)
    for index, path in enumerate(files, start=1):
        stem = _output_stem(path, input_dir, recursive)
        same_stem = by_stem[stem.casefold()]
        if len(same_stem) > 1:
            record = _empty_record(path, stem)
            others = ", ".join(p.name for p in same_stem if p != path)
            record["error"] = (
                f"Output basename collision for '{stem}' with: {others}. "
                "Rename the input files or use a different --output-dir."
            )
        else:
            record = _process_one(
                path,
                output_base=output_base,
                stem=stem,
                overwrite=overwrite,
                allow_non_monotonic=allow_non_monotonic,
                show=False,
            )
        records.append(record)
        _print_batch_record(index, total, record)

    summary = _build_batch_summary(
        input_dir=input_dir,
        output_dir=output_base,
        recursive=recursive,
        records=records,
        errors=errors,
    )
    _write_json(summary_path, summary)
    return summary, summary_path


def run_batch(args: argparse.Namespace) -> int:
    """Process every ``.ASC`` and ``.DSC`` entry point in ``--input-dir``."""
    input_dir = Path(args.input_dir)
    output_base = (
        Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "results"
    )

    try:
        summary, summary_path = batch_process_directory(
            input_dir,
            output_base,
            recursive=args.recursive,
            overwrite=args.overwrite,
            allow_non_monotonic=args.allow_non_monotonic,
        )
    except FileExistsError as exc:
        LOGGER.error("%s", exc)
        return 1
    except OSError as exc:
        LOGGER.error("Could not write batch summary %s: %s", summary_path, exc)
        return 1

    batch = summary["batch"]
    print()
    for message in batch["errors"]:
        print(f"ERROR: {message}")
    print(
        f"Files discovered: {batch['files_discovered']} | "
        f"succeeded: {batch['files_succeeded']} | "
        f"with warnings: {batch['files_succeeded_with_warnings']} | "
        f"failed: {batch['files_failed']}"
    )
    print(f"Overall status: {batch['overall_status']}")
    print(f"Batch summary -> {summary_path}")

    return 0 if batch["files_failed"] == 0 and not batch["errors"] else 1


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        description=(
            "Import, validate and plot Bruker Xepr ASCII (.ASC) or BES3T "
            "(.DSC + .DTA) CW-EPR files. Use a positional input for one "
            "dataset, or --input-dir for a batch."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help=(
            "Path to one .ASC file or a BES3T .DSC descriptor "
            "(default: data/raw/BSA3T275.ASC)."
        ),
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=None,
        help="Process every .ASC or .DSC entry point in this directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Base output directory (default: <project>/results).",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search --input-dir sub-directories as well (batch mode).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing existing output files (default: refuse).",
    )
    parser.add_argument("--figure", type=Path, default=None, help="PNG output path.")
    parser.add_argument("--csv", type=Path, dest="csv_path", default=None, help="CSV output path.")
    parser.add_argument("--json", type=Path, dest="json_path", default=None, help="JSON report path.")
    parser.add_argument(
        "--show",
        action="store_true",
        help="Display the figure interactively (single-file mode only).",
    )
    parser.add_argument(
        "--allow-non-monotonic",
        action="store_true",
        help="Permit plotting an unordered field axis (not recommended).",
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level (default: INFO).")
    args = parser.parse_args(argv)

    if args.input and args.input_dir:
        parser.error("Provide either an input file or --input-dir, not both.")
    if args.input_dir and args.show:
        parser.error("--show is only available for single-file mode.")
    if args.input_dir and (args.figure or args.csv_path or args.json_path):
        parser.error(
            "--figure/--csv/--json are only available for single-file mode."
        )

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(levelname)s | %(message)s",
        force=True,
    )

    if args.input_dir is not None:
        return run_batch(args)
    return run_single(args)


if __name__ == "__main__":
    sys.exit(main())
