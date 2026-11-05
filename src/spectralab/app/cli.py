"""Generic SpectraLab command-line entry point.

Examples
--------
python -m spectralab.app sample.ASC --output-dir results/generic
python -m spectralab.app sample.ASC other.DSC --output-dir results/generic
python -m spectralab.app data/raw --output-dir results/generic --recursive
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from spectralab.app.batch import BatchResult, run_batch
from spectralab.core.errors import ImportFailure


def _build_import_options(args: argparse.Namespace) -> dict | None:
    """Build explicit FTIR options only when at least one was requested."""
    option_names = (
        "x_column",
        "y_column",
        "header",
        "delimiter",
        "decimal",
        "comment",
        "encoding",
        "skip_rows",
        "x_quantity",
        "x_unit",
        "x_name",
        "y_semantics",
        "y_unit",
        "y_name",
        "acquisition_mode",
        "atr_correction_status",
        "instrument_vendor",
        "instrument_model",
    )
    if not any(getattr(args, name, None) not in (None, False, []) for name in option_names):
        return None

    from spectralab.techniques.ftir.importers import (
        ColumnMapping,
        FTIRImportOptions,
        parse_column_reference,
    )

    mapping = ColumnMapping(
        x=parse_column_reference(args.x_column),
        y=parse_column_reference(args.y_column),
        x_name=args.x_name,
        x_unit=args.x_unit,
        y_name=args.y_name,
        y_unit=args.y_unit,
        y_semantics=args.y_semantics or "unknown",
        header=bool(args.header),
        delimiter=args.delimiter,
        comment=tuple(args.comment) if args.comment else None,
        decimal=args.decimal or ".",
        encoding=args.encoding or "utf-8-sig",
        skip_rows=args.skip_rows or 0,
        x_quantity=args.x_quantity,
    )
    options = FTIRImportOptions(
        mapping=mapping,
        acquisition_mode=args.acquisition_mode or "Unknown",
        atr_correction_status=args.atr_correction_status or "unknown",
        instrument_vendor=args.instrument_vendor,
        instrument_model=args.instrument_model,
    )
    return {"ftir": options}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spectralab",
        description=(
            "Import 1D spectra through the explicit importer registry and "
            "write generic raw x/y CSV plus JSON metadata. No processing is "
            "applied."
        ),
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="One or more input files or directories.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Explicit output directory for tables, JSON and the batch summary.",
    )
    parser.add_argument(
        "--format-id",
        "--format",
        dest="format_id",
        default=None,
        help="Optional explicit importer format ID, for example ASC or BES3T.",
    )
    parser.add_argument(
        "--technique",
        default=None,
        help="Optional explicit technique filter, for example epr.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search directories recursively for registered input suffixes.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing existing output files (default: refuse).",
    )

    text = parser.add_argument_group(
        "FTIR text import options",
        "Explicit parsing and metadata options for generic CSV/TXT/DPT files. "
        "These values are applied to every input in this run.",
    )
    text.add_argument(
        "--x-column",
        "--x-col",
        dest="x_column",
        default=None,
        help="X column index (zero-based) or header name.",
    )
    text.add_argument(
        "--y-column",
        "--y-col",
        dest="y_column",
        default=None,
        help="Y column index (zero-based) or header name.",
    )
    text.add_argument(
        "--header",
        action="store_true",
        help="Treat the first non-comment row as a header.",
    )
    text.add_argument(
        "--delimiter",
        "--separator",
        dest="delimiter",
        default=None,
        help="comma, tab, semicolon, whitespace, auto, or one character.",
    )
    text.add_argument(
        "--decimal",
        "--decimal-separator",
        dest="decimal",
        default=None,
        help="Decimal separator: dot or comma (default: dot).",
    )
    text.add_argument(
        "--comment",
        "--comments",
        dest="comment",
        action="append",
        default=None,
        help="Comment marker at the start of a line; repeat for several.",
    )
    text.add_argument(
        "--encoding",
        default=None,
        help="Text encoding (default: utf-8-sig).",
    )
    text.add_argument(
        "--skip-rows",
        dest="skip_rows",
        type=int,
        default=None,
        help="Skip this many physical lines at the start of the file.",
    )
    text.add_argument(
        "--x-quantity",
        "--axis-quantity",
        dest="x_quantity",
        default=None,
        help="wavenumber or unknown; omit to preserve unknown.",
    )
    text.add_argument(
        "--x-unit",
        "--axis-unit",
        dest="x_unit",
        default=None,
        help="Explicit X unit; only cm^-1 is accepted in M9.",
    )
    text.add_argument(
        "--x-name",
        "--axis-name",
        dest="x_name",
        default=None,
        help="Optional X-axis display name.",
    )
    text.add_argument(
        "--y-semantics",
        "--signal-semantics",
        dest="y_semantics",
        default=None,
        help="absorbance, transmittance or unknown.",
    )
    text.add_argument(
        "--y-unit",
        "--signal-unit",
        dest="y_unit",
        default=None,
        help="Optional explicit Y unit; never inferred.",
    )
    text.add_argument(
        "--y-name",
        "--signal-name",
        dest="y_name",
        default=None,
        help="Optional Y-axis display name.",
    )
    text.add_argument(
        "--acquisition-mode",
        dest="acquisition_mode",
        default=None,
        help="ATR, Transmission or Unknown.",
    )
    text.add_argument(
        "--atr-correction",
        "--atr-correction-status",
        dest="atr_correction_status",
        default=None,
        help="applied, not_applied, not_applicable or unknown.",
    )
    text.add_argument(
        "--instrument-vendor",
        dest="instrument_vendor",
        default=None,
        help="Optional instrument vendor; never inferred.",
    )
    text.add_argument(
        "--instrument-model",
        dest="instrument_model",
        default=None,
        help="Optional instrument model; never inferred.",
    )
    return parser


def _print_result(result: BatchResult) -> None:
    records = result.summary.get("files", [])
    total = len(records)
    for index, record in enumerate(records, start=1):
        status = str(record.get("status", "unknown")).upper()
        print(f"[{index}/{total}] {status}: {record.get('input_name', '')}")
        if record.get("status") == "failed":
            code = record.get("error_code")
            suffix = f" [{code}]" if code else ""
            print(f"    error{suffix}: {record.get('error', '')}")
        else:
            for label, path in record.get("outputs", {}).items():
                print(f"    {label}: {path}")
        for warning in record.get("warnings", [])[:5]:
            print(f"    warning: {warning}")

    for error in result.summary.get("batch", {}).get("errors", []):
        code = error.get("code")
        suffix = f" [{code}]" if code else ""
        print(f"BATCH ERROR{suffix}: {error.get('message', '')}")

    batch = result.summary.get("batch", {})
    print(
        "Batch summary: "
        f"{batch.get('files_succeeded', 0)} succeeded, "
        f"{batch.get('files_failed', 0)} failed, "
        f"status={batch.get('overall_status', 'unknown')}"
    )
    if result.summary_path is not None:
        print(f"Summary: {result.summary_path.resolve()}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the generic CLI and return a process exit code."""
    args = build_parser().parse_args(argv)
    try:
        options = _build_import_options(args)
    except ImportFailure as exc:
        print(f"Invalid import option [{exc.code}]: {exc}", file=sys.stderr)
        return 2
    result = run_batch(
        args.inputs,
        args.output_dir,
        format_id=args.format_id,
        technique=args.technique,
        recursive=args.recursive,
        overwrite=args.overwrite,
        options=options,
    )
    _print_result(result)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
