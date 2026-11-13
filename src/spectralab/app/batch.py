"""Technique-independent batch import and generic CSV/JSON export.

The module is intentionally independent of the legacy EPR CLI. It consumes the
M2 importer registry and the M3 raw Spectrum1D export renderers. It never runs
processing, plotting or technique-specific code.
"""

from __future__ import annotations

import dataclasses
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from spectralab.app.registry import build_importer_registry
from spectralab.core.export import (
    atomic_write_text,
    check_output_path,
    render_csv_metadata_json,
    render_spectrum_csv,
    render_spectrum_json,
)
from spectralab.core.importers import ImporterRegistry
from spectralab.core.model import Spectrum1D

BATCH_SCHEMA_ID = "spectralab.batch_summary"
BATCH_SCHEMA_VERSION = 1
SUMMARY_RELATIVE_PATH = Path("logs") / "spectralab_batch_summary.json"


@dataclass(frozen=True)
class BatchResult:
    """Outcome of one explicit batch run."""

    exit_code: int
    summary: dict[str, Any]
    summary_path: Path | None


def _input_key(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve(strict=False)))
    except OSError:
        return os.path.normcase(str(path.absolute()))


def _output_key(path: Path) -> str:
    return _input_key(path)


def _registered_suffixes(registry: ImporterRegistry) -> frozenset[str]:
    return frozenset(
        suffix.casefold()
        for importer in registry.importers
        for suffix in importer.entry_suffixes
    )


def discover_inputs(
    inputs: Sequence[str | Path],
    registry: ImporterRegistry,
    *,
    recursive: bool = False,
) -> tuple[list[Path], list[dict[str, Any]]]:
    """Expand explicit files and directory entries in stable input order.

    Explicit files are accepted regardless of suffix so unsupported formats
    fail explicitly rather than disappearing. Directory expansion includes
    only suffixes declared by registered importers; ``.DTA`` is therefore not
    discovered as an independent dataset.
    """
    entries: list[Path] = []
    errors: list[dict[str, Any]] = []
    suffixes = _registered_suffixes(registry)

    for value in inputs:
        path = Path(value)
        if path.is_file():
            entries.append(path)
            continue
        if path.is_dir():
            iterator = path.rglob("*") if recursive else path.glob("*")
            candidates = [
                item
                for item in iterator
                if item.is_file() and item.suffix.casefold() in suffixes
            ]
            candidates.sort(
                key=lambda item: (
                    item.relative_to(path).as_posix().casefold(),
                    item.relative_to(path).as_posix(),
                )
            )
            if not candidates:
                errors.append(
                    {
                        "code": "no_inputs",
                        "path": str(path),
                        "message": (
                            f"No supported input files found in {path} "
                            f"(recursive={recursive})."
                        ),
                    }
                )
            entries.extend(candidates)
            continue
        errors.append(
            {
                "code": "input_not_found",
                "path": str(path),
                "message": (
                    "Input path does not exist or is not a file/directory: "
                    f"{path}"
                ),
            }
        )
    return entries, errors


def output_paths(output_dir: str | Path, stem: str) -> dict[str, Path]:
    """Return the three per-file output paths for one input stem."""
    base = Path(output_dir)
    return {
        "csv": base / "tables" / f"{stem}.csv",
        "metadata": base / "tables" / f"{stem}_metadata.json",
        "json": base / "json" / f"{stem}.json",
    }


def summary_path(output_dir: str | Path) -> Path:
    """Return the new CLI's summary path, distinct from the legacy summary."""
    return Path(output_dir) / SUMMARY_RELATIVE_PATH


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else str(value)
    if isinstance(value, Path):
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _json_safe(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _failure_record(
    path: Path,
    *,
    error: Exception | str,
    code: str | None = None,
    context: dict[str, Any] | None = None,
    outputs: dict[str, Path] | None = None,
    partial_outputs: bool = False,
) -> dict[str, Any]:
    code_value = code
    context_value = context
    if isinstance(error, Exception):
        message = str(error)
        error_type = type(error).__name__
        if code_value is None:
            candidate = getattr(error, "code", None)
            if isinstance(candidate, str) and candidate:
                code_value = candidate
        if context_value is None:
            candidate = getattr(error, "context", None)
            if isinstance(candidate, dict):
                context_value = dict(candidate)
    else:
        message = error
        error_type = None
    return {
        "input": str(path.resolve()),
        "input_name": path.name,
        "status": "failed",
        "outputs": {
            key: str(value.resolve()) for key, value in (outputs or {}).items()
        },
        "partial_outputs": bool(partial_outputs),
        "error": message,
        "error_type": error_type,
        "error_code": code_value,
        "error_context": _json_safe(context_value or {}),
    }


def _metadata_record(spectrum: Spectrum1D) -> dict[str, Any]:
    metadata = spectrum.metadata
    return {
        "technique": metadata.technique,
        "title": metadata.title,
        "instrument": _json_safe(metadata.instrument),
        "acquisition": _json_safe(metadata.acquisition),
        "sample": _json_safe(metadata.sample),
        "technique_metadata": _json_safe(metadata.technique_metadata),
        "unknown_fields": list(metadata.unknown_fields),
        "metadata_origin": _json_safe(metadata.metadata_origin),
    }


def _success_record(
    path: Path,
    dataset: Any,
    spectrum: Spectrum1D,
    outputs: dict[str, Path],
) -> dict[str, Any]:
    source_files = [
        {
            "role": source.role,
            "path": str(source.path),
            "format_id": source.format_id,
            "size_bytes": source.size_bytes,
            "sha256": source.sha256 or None,
        }
        for source in spectrum.provenance.source_files
    ]
    return {
        "input": str(path.resolve()),
        "input_name": path.name,
        "status": "success",
        "format_id": dataset.format_id,
        "technique": dataset.technique,
        "importer_id": spectrum.provenance.importer_id,
        "importer_version": spectrum.provenance.importer_version,
        "dataset_id": spectrum.dataset_id,
        "source_format": spectrum.source_format,
        "point_count": spectrum.point_count,
        "canonical_sha256": spectrum.provenance.canonical_sha256,
        "warnings": list(dataset.warnings),
        "source_files": source_files,
        "metadata": _metadata_record(spectrum),
        "import_options": _json_safe(
            spectrum.provenance.format_metadata.get("import_options", {})
        ),
        "resolved_mapping": _json_safe(
            spectrum.provenance.format_metadata.get("resolved_mapping", {})
        ),
        "parsing": _json_safe(
            {
                "delimiter": spectrum.provenance.format_metadata.get(
                    "delimiter"
                ),
                "decimal_separator": spectrum.provenance.format_metadata.get(
                    "decimal_separator"
                ),
                "encoding": spectrum.provenance.format_metadata.get("encoding"),
                "header": spectrum.provenance.format_metadata.get("header"),
                "comment_markers": spectrum.provenance.format_metadata.get(
                    "comment_markers"
                ),
                "skip_rows": spectrum.provenance.format_metadata.get("skip_rows"),
                "defaulted_two_column_mapping": (
                    spectrum.provenance.format_metadata.get(
                        "defaulted_two_column_mapping"
                    )
                ),
            }
        ),
        "outputs": {
            key: str(value.resolve()) for key, value in outputs.items()
        },
        "partial_outputs": False,
        "error": None,
        "error_type": None,
        "error_code": None,
        "error_context": {},
    }


def _source_paths(spectrum: Spectrum1D, input_path: Path) -> list[Path]:
    paths: list[Path] = [input_path]
    paths.extend(source.path for source in spectrum.provenance.source_files)
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = _input_key(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _preflight_outputs(
    paths: dict[str, Path],
    *,
    overwrite: bool,
    protected_paths: Sequence[str | Path] = (),
) -> None:
    for path in paths.values():
        check_output_path(
            path,
            overwrite=overwrite,
            protected_paths=protected_paths,
        )


def _process_file(
    path: Path,
    *,
    output_dir: Path,
    registry: ImporterRegistry,
    format_id: str | None,
    technique: str | None,
    overwrite: bool,
    options: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], Spectrum1D | None]:
    planned = output_paths(output_dir, path.stem)
    try:
        dataset = registry.read(
            path,
            format_id=format_id,
            technique=technique,
            options=options,
        )
    except Exception as exc:
        return _failure_record(path, error=exc), None

    if len(dataset.spectra) != 1:
        return (
            _failure_record(
                path,
                error=(
                    "The generic CLI supports exactly one Spectrum1D per "
                    f"input; got {len(dataset.spectra)}."
                ),
                code="multiple_spectra_unsupported",
                outputs={},
            ),
            None,
        )
    spectrum = dataset.primary
    protected = _source_paths(spectrum, path)

    try:
        _preflight_outputs(
            planned,
            overwrite=overwrite,
            protected_paths=protected,
        )
        csv_text = render_spectrum_csv(spectrum)
        metadata_text = render_csv_metadata_json(spectrum)
        json_text = render_spectrum_json(spectrum)
    except Exception as exc:
        return _failure_record(path, error=exc), spectrum

    written: dict[str, Path] = {}
    try:
        for key, text in (
            ("metadata", metadata_text),
            ("csv", csv_text),
            ("json", json_text),
        ):
            written[key] = atomic_write_text(
                planned[key],
                text,
                overwrite=overwrite,
                protected_paths=protected,
            )
    except Exception as exc:
        return (
            _failure_record(
                path,
                error=exc,
                outputs=written,
                partial_outputs=True,
            ),
            spectrum,
        )

    return _success_record(path, dataset, spectrum, written), spectrum


def _build_summary(
    *,
    requested_inputs: Sequence[str | Path],
    output_dir: Path,
    format_id: str | None,
    technique: str | None,
    recursive: bool,
    overwrite: bool,
    options: Mapping[str, Any] | None,
    records: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    summary_target: Path,
) -> dict[str, Any]:
    success = sum(1 for record in records if record["status"] == "success")
    failed = sum(1 for record in records if record["status"] == "failed")
    if failed == 0 and not errors:
        overall = "success"
    elif success == 0:
        overall = "failed"
    else:
        overall = "partial_failure"
    requested_options = _json_safe(options or {})
    for record in records:
        record.setdefault("import_options", requested_options)
    return {
        "schema_id": BATCH_SCHEMA_ID,
        "schema_version": BATCH_SCHEMA_VERSION,
        "batch": {
            "inputs": [str(Path(value)) for value in requested_inputs],
            "output_dir": str(output_dir.resolve()),
            "summary_path": str(summary_target.resolve()),
            "format_id": format_id,
            "technique": technique,
            "recursive": bool(recursive),
            "overwrite": bool(overwrite),
            "import_options": _json_safe(options or {}),
            "files_discovered": len(records),
            "files_succeeded": success,
            "files_failed": failed,
            "overall_status": overall,
            "errors": errors,
            "processing_applied": [],
            "scientific_note": (
                "This summary reports import and raw export status only. "
                "No smoothing, baseline, normalisation or other processing "
                "was applied."
            ),
        },
        "files": records,
    }


def run_batch(
    inputs: Sequence[str | Path],
    output_dir: str | Path,
    *,
    format_id: str | None = None,
    technique: str | None = None,
    recursive: bool = False,
    overwrite: bool = False,
    registry: ImporterRegistry | None = None,
    options: Mapping[str, Any] | None = None,
) -> BatchResult:
    """Process explicit inputs with the generic registry and M3 raw export.

    ``options`` are passed unchanged to every selected importer. Importers that
    accept no options reject non-empty values rather than ignoring them.
    """
    output_path = Path(output_dir)
    summary_target = summary_path(output_path)
    requested = tuple(inputs)
    errors: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []

    if not requested:
        errors.append(
            {
                "code": "no_inputs",
                "path": None,
                "message": "At least one input file or directory is required.",
            }
        )

    if registry is None:
        registry = build_importer_registry()

    entries: list[Path] = []
    if not requested or (output_path.exists() and not output_path.is_dir()):
        if output_path.exists() and not output_path.is_dir():
            errors.append(
                {
                    "code": "invalid_output_dir",
                    "path": str(output_path),
                    "message": f"Output path is not a directory: {output_path}",
                }
            )
        summary = _build_summary(
            requested_inputs=requested,
            output_dir=output_path,
            format_id=format_id,
            technique=technique,
            recursive=recursive,
            overwrite=overwrite,
            options=options,
            records=[],
            errors=errors,
            summary_target=summary_target,
        )
        return BatchResult(exit_code=1, summary=summary, summary_path=None)

    entries, discovery_errors = discover_inputs(
        requested,
        registry,
        recursive=recursive,
    )
    errors.extend(discovery_errors)

    # Resolve planned outputs and detect all per-file output collisions before
    # importing anything. A collision must never be resolved by renaming.
    owners: dict[str, set[str]] = {}
    for entry in entries:
        for planned in output_paths(output_path, entry.stem).values():
            owners.setdefault(_output_key(planned), set()).add(
                _input_key(entry)
            )
    collisions: dict[str, list[str]] = {}
    for entry in entries:
        colliding: list[str] = []
        for planned in output_paths(output_path, entry.stem).values():
            if len(owners[_output_key(planned)]) > 1:
                colliding.extend(
                    sorted(owners[_output_key(planned)] - {_input_key(entry)})
                )
        if colliding:
            collisions[_input_key(entry)] = sorted(set(colliding))

    # Refuse an existing/unwritable summary before any per-file output is
    # written. Discovery errors remain reportable, but a bad summary path is a
    # fatal batch-level preflight failure.
    summary_fatal = False
    summary_parent = summary_target.parent
    if summary_parent.exists() and not summary_parent.is_dir():
        summary_fatal = True
        errors.append(
            {
                "code": "summary_parent_not_directory",
                "path": str(summary_parent),
                "message": (
                    "The batch summary parent path is not a directory: "
                    f"{summary_parent}"
                ),
            }
        )
    try:
        check_output_path(
            summary_target,
            overwrite=overwrite,
            protected_paths=[path for path in entries if path.is_file()],
        )
    except Exception as exc:
        summary_fatal = True
        errors.append(
            {
                "code": getattr(exc, "code", "summary_path"),
                "path": str(summary_target),
                "message": str(exc),
            }
        )

    if not summary_fatal:
        for entry in entries:
            key = _input_key(entry)
            if key in collisions:
                records.append(
                    _failure_record(
                        entry,
                        error=(
                            "Output path collision with input(s): "
                            + ", ".join(collisions[key])
                        ),
                        code="output_collision",
                        context={"collisions": collisions[key]},
                        outputs={},
                    )
                )
                continue

            planned = output_paths(output_path, entry.stem)
            try:
                _preflight_outputs(
                    planned,
                    overwrite=overwrite,
                )
            except Exception as exc:
                records.append(_failure_record(entry, error=exc, outputs={}))
                continue

            try:
                record, _spectrum = _process_file(
                    entry,
                    output_dir=output_path,
                    registry=registry,
                    format_id=format_id,
                    technique=technique,
                    overwrite=overwrite,
                    options=options,
                )
            except Exception as exc:
                record = _failure_record(entry, error=exc, outputs={})
            records.append(record)

    summary = _build_summary(
        requested_inputs=requested,
        output_dir=output_path,
        format_id=format_id,
        technique=technique,
        recursive=recursive,
        overwrite=overwrite,
        options=options,
        records=records,
        errors=errors,
        summary_target=summary_target,
    )

    if summary_fatal:
        return BatchResult(exit_code=1, summary=summary, summary_path=None)

    protected = [path for path in entries if path.is_file()]
    for record in records:
        for source in record.get("source_files", []):
            protected.append(Path(source["path"]))
    try:
        summary_text = (
            json.dumps(
                summary,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        atomic_write_text(
            summary_target,
            summary_text,
            overwrite=overwrite,
            protected_paths=protected,
        )
    except Exception as exc:
        errors.append(
            {
                "code": getattr(exc, "code", "summary_write_failed"),
                "path": str(summary_target),
                "message": f"Could not write batch summary: {exc}",
            }
        )
        summary = _build_summary(
            requested_inputs=requested,
            output_dir=output_path,
            format_id=format_id,
            technique=technique,
            recursive=recursive,
            overwrite=overwrite,
            options=options,
            records=records,
            errors=errors,
            summary_target=summary_target,
        )
        return BatchResult(exit_code=1, summary=summary, summary_path=None)

    exit_code = 0 if summary["batch"]["overall_status"] == "success" else 1
    return BatchResult(
        exit_code=exit_code,
        summary=summary,
        summary_path=summary_target,
    )


__all__ = [
    "BATCH_SCHEMA_ID",
    "BATCH_SCHEMA_VERSION",
    "BatchResult",
    "SUMMARY_RELATIVE_PATH",
    "discover_inputs",
    "output_paths",
    "run_batch",
    "summary_path",
]
