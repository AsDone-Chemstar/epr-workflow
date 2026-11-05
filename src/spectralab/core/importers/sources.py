"""Generic source-file collection for importers."""

from __future__ import annotations

import hashlib
from pathlib import Path

from spectralab.core.errors import ImportFailure
from spectralab.core.model import SourceFile


def source_file_from_bytes(
    path: str | Path,
    payload: bytes,
    *,
    role: str,
    format_id: str,
) -> SourceFile:
    """Record one stable byte snapshot without reading the file again."""
    if not isinstance(payload, (bytes, bytearray)):
        raise ImportFailure(
            "source_file_from_bytes requires a bytes snapshot.",
            code="invalid_source_snapshot",
            context={
                "path": str(path),
                "role": role,
                "type": type(payload).__name__,
            },
        )
    source = Path(path)
    return SourceFile(
        role=role,
        path=source,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        format_id=format_id,
    )


def source_file(path: str | Path, *, role: str, format_id: str) -> SourceFile:
    """Read one source file and record its hash and size.

    The file is opened read-only. Hashing the bytes does not modify the file.
    No format-specific interpretation is performed here.
    """
    source = Path(path)
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise ImportFailure(
            f"Could not read source file {source}.",
            code="source_read_failed",
            context={
                "path": str(source),
                "role": role,
                "error": str(exc),
            },
        ) from exc

    return source_file_from_bytes(
        source,
        payload,
        role=role,
        format_id=format_id,
    )


__all__ = ["source_file", "source_file_from_bytes"]
