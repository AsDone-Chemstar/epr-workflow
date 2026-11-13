"""Output-path checks and atomic text writes for generic exports."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from spectralab.core.errors import (
    ExportPathError,
    OutputExistsError,
)


def _resolved_key(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve(strict=False)))
    except OSError:
        return os.path.normcase(str(path.absolute()))


def _protected_paths(
    paths: Iterable[str | Path],
) -> tuple[Path, ...]:
    protected: list[Path] = []
    for value in paths:
        if value is None:
            continue
        try:
            protected.append(Path(value))
        except (TypeError, ValueError) as exc:
            raise ExportPathError(
                "A protected source path is not a filesystem path.",
                code="invalid_protected_path",
                context={"path": repr(value)},
            ) from exc
    return tuple(protected)


def _same_existing_file(output: Path, protected: tuple[Path, ...]) -> bool:
    if not output.exists():
        return False
    for source in protected:
        if not source.exists():
            continue
        try:
            if os.path.samefile(output, source):
                return True
        except OSError:
            continue
    return False


def check_output_path(
    path: str | Path,
    *,
    overwrite: bool = False,
    protected_paths: Iterable[str | Path] = (),
) -> Path:
    """Validate one output path without creating anything.

    Protected paths are source files. They are checked first, so even
    ``overwrite=True`` cannot replace a source file through the same path or a
    symlink resolving to it.
    """
    if not isinstance(overwrite, bool):
        raise ExportPathError(
            "overwrite must be a boolean.",
            code="invalid_overwrite_option",
            context={"type": type(overwrite).__name__},
        )
    try:
        raw_path = os.fspath(path)
    except TypeError as exc:
        raise ExportPathError(
            "The output path must be text or a filesystem path.",
            code="invalid_output_path",
            context={"type": type(path).__name__},
        ) from exc
    if isinstance(raw_path, bytes):
        raise ExportPathError(
            "The output path must be text, not bytes.",
            code="invalid_output_path",
            context={"type": "bytes"},
        )
    if not raw_path.strip():
        raise ExportPathError(
            "The output path must not be empty.",
            code="invalid_output_path",
        )

    output = Path(path)
    output_key = _resolved_key(output)
    protected = _protected_paths(protected_paths)
    protected_keys = {_resolved_key(source) for source in protected}
    if output_key in protected_keys or _same_existing_file(output, protected):
        raise ExportPathError(
            f"Refusing to write over a source file: {output}",
            code="output_is_source_file",
            context={"path": str(output)},
        )

    if output.exists() and output.is_dir():
        raise ExportPathError(
            f"The output path is a directory: {output}",
            code="output_is_directory",
            context={"path": str(output)},
        )
    if output.exists() and not overwrite:
        raise OutputExistsError(
            f"Output already exists: {output}. Pass overwrite=True "
            "explicitly to replace it.",
            context={"path": str(output)},
        )
    return output


def atomic_write_bytes(
    path: str | Path,
    payload: bytes,
    *,
    overwrite: bool = False,
    protected_paths: Iterable[str | Path] = (),
) -> Path:
    """Write binary data through a sibling temporary file and os.replace.

    This is the binary counterpart of :func:`atomic_write_text`. The
    destination is validated before and immediately before replacement.
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise ExportPathError(
            "Binary export payload must be bytes.",
            code="invalid_binary_payload",
            context={"type": type(payload).__name__},
        )
    output = check_output_path(
        path,
        overwrite=overwrite,
        protected_paths=protected_paths,
    )
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportPathError(
            f"Could not create the output directory: {output.parent}",
            code="output_directory",
            context={
                "path": str(output),
                "directory": str(output.parent),
                "error": str(exc),
            },
        ) from exc

    temporary: Path | None = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=str(output.parent),
        )
        temporary = Path(temp_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if not overwrite and output.exists():
            raise OutputExistsError(
                f"Output appeared while writing: {output}. It was not "
                "overwritten.",
                context={"path": str(output)},
            )
        os.replace(temporary, output)
        temporary = None
        return output
    except (ExportPathError, OutputExistsError):
        raise
    except OSError as exc:
        raise ExportPathError(
            f"Could not write the output file: {output}",
            code="output_write_failed",
            context={
                "path": str(output),
                "error": str(exc),
            },
        ) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def atomic_write_text(
    path: str | Path,
    text: str,
    *,
    overwrite: bool = False,
    protected_paths: Iterable[str | Path] = (),
) -> Path:
    """Write UTF-8 text through a sibling temporary file and os.replace.

    The destination is checked again immediately before replacement. A failed
    serialization occurs before this function is called and therefore creates
    no output file.
    """
    output = check_output_path(
        path,
        overwrite=overwrite,
        protected_paths=protected_paths,
    )
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportPathError(
            f"Could not create the output directory: {output.parent}",
            code="output_directory",
            context={
                "path": str(output),
                "directory": str(output.parent),
                "error": str(exc),
            },
        ) from exc

    temporary: Path | None = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=str(output.parent),
        )
        temporary = Path(temp_name)
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if not overwrite and output.exists():
            raise OutputExistsError(
                f"Output appeared while writing: {output}. It was not "
                "overwritten.",
                context={"path": str(output)},
            )
        os.replace(temporary, output)
        temporary = None
        return output
    except (ExportPathError, OutputExistsError):
        raise
    except OSError as exc:
        raise ExportPathError(
            f"Could not write the output file: {output}",
            code="output_write_failed",
            context={
                "path": str(output),
                "error": str(exc),
            },
        ) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


__all__ = ["atomic_write_bytes", "atomic_write_text", "check_output_path"]
