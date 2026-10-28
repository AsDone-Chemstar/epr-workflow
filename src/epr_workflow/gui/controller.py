"""GUI-agnostic controller for the EPR workflow desktop app.

This module contains **no Qt imports** so it can be unit-tested headlessly.
It wraps the data-processing core in :mod:`epr_workflow.plot_asc` and exposes
the small set of operations the graphical interface needs.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from epr_workflow.gui.i18n import DEFAULT_LANGUAGE, status_text
from epr_workflow.plot_asc import (
    ImportResult,
    batch_process_directory,
    read_dataset,
)
from epr_workflow.preprocessing import PreprocessingSession


@dataclass
class SpectrumView:
    """A parsed spectrum ready for display, plus summary numbers."""

    source: Path
    data: Any  # pandas.DataFrame with columns index, field_G, intensity
    warnings: list[str] = field(default_factory=list)
    field_order: str = "unknown"
    n_points: int = 0
    field_min: float = 0.0
    field_max: float = 0.0
    signal_min: float = 0.0
    signal_max: float = 0.0
    signal_mean: float = 0.0
    signal_std: float = 0.0
    sha256: str = ""
    source_format: str = "ASC"
    source_files: dict[str, str] = field(default_factory=dict)
    source_hashes: dict[str, str] = field(default_factory=dict)
    import_result: ImportResult | None = None


def load_spectrum(path: str | Path) -> SpectrumView:
    """Read one supported dataset for display, returning a :class:`SpectrumView`.

    ``.ASC`` and BES3T ``.DSC`` entry points are dispatched by
    :func:`epr_workflow.plot_asc.read_dataset`. This is read-only: it never
    writes outputs and never modifies source files.
    """
    path = Path(path)
    result = read_dataset(path)
    data = result.data
    field = data["field_G"].to_numpy()
    signal = data["intensity"].to_numpy()
    return SpectrumView(
        source=path,
        data=data,
        warnings=list(result.warnings),
        field_order=result.field_order,
        n_points=int(len(data)),
        field_min=float(field.min()),
        field_max=float(field.max()),
        signal_min=float(signal.min()),
        signal_max=float(signal.max()),
        signal_mean=float(signal.mean()),
        signal_std=float(signal.std(ddof=1)) if len(signal) > 1 else 0.0,
        sha256=result.sha256,
        source_format=result.source_format,
        source_files=dict(result.source_files),
        source_hashes=dict(result.source_hashes),
        import_result=result,
    )


@dataclass
class BatchOutcome:
    """The result of one batch run."""

    summary: dict[str, Any]
    summary_path: Path


def run_batch_processing(
    input_dir: str | Path,
    output_base: str | Path,
    *,
    recursive: bool = False,
    overwrite: bool = False,
    allow_non_monotonic: bool = False,
) -> BatchOutcome:
    """Run a batch and return its summary plus summary path.

    Per-file failures are recorded inside the summary rather than raised.
    Raises :class:`FileExistsError` when the batch summary already exists and
    ``overwrite`` is False.
    """
    summary, summary_path = batch_process_directory(
        input_dir,
        output_base,
        recursive=recursive,
        overwrite=overwrite,
        allow_non_monotonic=allow_non_monotonic,
    )
    return BatchOutcome(summary=summary, summary_path=Path(summary_path))


def open_path(path: str | Path) -> None:
    """Open a file with the operating system's default application."""
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"File not found: {target}")
    if sys.platform == "win32":
        os.startfile(str(target))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(target)], check=False)
    else:
        subprocess.run(["xdg-open", str(target)], check=False)


def status_label(status: str, lang: str | None = DEFAULT_LANGUAGE) -> str:
    """Map a record status to a short label in the requested language.

    Defaults to Simplified Chinese, which preserves the original behaviour for
    callers that do not pass ``lang``.
    """
    return status_text(status, lang)


class PreprocessingStore:
    """In-memory preprocessing sessions keyed by resolved source path.

    Nothing here is written to disk. A session is discarded automatically when
    the source file's SHA-256 no longer matches the imported file, so a stale
    correction can never be applied to changed data.
    """

    def __init__(self) -> None:
        self._sessions: dict[Path, PreprocessingSession] = {}

    def session_for(self, view: SpectrumView) -> PreprocessingSession:
        key = view.source.resolve()
        session = self._sessions.get(key)
        if session is not None and session.source_sha256 == view.sha256:
            return session
        session = PreprocessingSession(
            source=view.source,
            field_G=view.data["field_G"].to_numpy(),
            intensity=view.data["intensity"].to_numpy(),
            source_sha256=view.sha256,
        )
        self._sessions[key] = session
        return session

    def discard(self, source: str | Path) -> None:
        self._sessions.pop(Path(source).resolve(), None)

    def clear(self) -> None:
        self._sessions.clear()

    def __len__(self) -> int:
        return len(self._sessions)
