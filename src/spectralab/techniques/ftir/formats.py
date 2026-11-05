"""Authoritative FTIR text entry suffixes.

The importers and GUI file filters both derive from these constants so adding
a supported suffix cannot silently desynchronise discovery and dialogs.
"""

from __future__ import annotations

FTIR_CSV_SUFFIXES: tuple[str, ...] = (".csv",)
FTIR_TXT_SUFFIXES: tuple[str, ...] = (".txt", ".dpt")
FTIR_ENTRY_SUFFIXES: tuple[str, ...] = (
    *FTIR_CSV_SUFFIXES,
    *FTIR_TXT_SUFFIXES,
)


def file_patterns() -> tuple[str, ...]:
    """Return lower/upper file-dialog patterns derived from the suffixes."""
    patterns: list[str] = []
    for suffix in FTIR_ENTRY_SUFFIXES:
        patterns.append(f"*{suffix}")
        upper = f"*{suffix.upper()}"
        if upper not in patterns:
            patterns.append(upper)
    return tuple(patterns)


__all__ = [
    "FTIR_CSV_SUFFIXES",
    "FTIR_ENTRY_SUFFIXES",
    "FTIR_TXT_SUFFIXES",
    "file_patterns",
]
