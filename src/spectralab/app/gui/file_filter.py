"""Shared file-dialog filter construction for the generic shell."""

from __future__ import annotations

from spectralab.app.gui.i18n import Translator


def build_file_filter(
    translator: Translator,
    patterns: tuple[str, ...],
) -> str:
    """Build the standard data/all-files filter from explicit patterns."""
    joined = " ".join(patterns)
    return (
        f"{translator.tr('app.data_files')} ({joined});;"
        f"{translator.tr('app.all_files')} (*.*)"
    )


__all__ = ["build_file_filter"]
