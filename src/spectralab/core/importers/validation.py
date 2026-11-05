"""Small validation helpers for importer registration."""

from __future__ import annotations

from typing import Any

from spectralab.core.errors import ImporterRegistrationError


def _text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImporterRegistrationError(
            f"Importer.{field} must be non-empty text.",
            code="invalid_importer",
            context={"field": field, "type": type(value).__name__},
        )
    if value != value.strip():
        raise ImporterRegistrationError(
            f"Importer.{field} must not have surrounding whitespace.",
            code="invalid_importer",
            context={"field": field, "value": value},
        )
    return value


def validate_importer(importer: Any) -> None:
    """Validate the stable attributes and callables of an importer.

    The registry does not accept duck-typed objects with missing or malformed
    metadata. Validation is explicit so a broken registration fails at startup
    rather than during a scientific import.
    """
    for field in ("id", "version", "technique"):
        _text(getattr(importer, field, None), field=field)

    suffixes = getattr(importer, "entry_suffixes", None)
    if not isinstance(suffixes, tuple) or not suffixes:
        raise ImporterRegistrationError(
            "Importer.entry_suffixes must be a non-empty tuple.",
            code="invalid_importer",
            context={"field": "entry_suffixes"},
        )
    normalized: set[str] = set()
    for suffix in suffixes:
        value = _text(suffix, field="entry_suffixes")
        if not value.startswith(".") or any(char.isspace() for char in value):
            raise ImporterRegistrationError(
                "Importer entry suffixes must start with '.' and contain no "
                "whitespace.",
                code="invalid_importer",
                context={"field": "entry_suffixes", "value": value},
            )
        folded = value.casefold()
        if folded in normalized:
            raise ImporterRegistrationError(
                "Importer entry suffixes must be unique ignoring case.",
                code="invalid_importer",
                context={"field": "entry_suffixes", "value": value},
            )
        normalized.add(folded)

    for method in ("probe", "collect_sources", "read"):
        if not callable(getattr(importer, method, None)):
            raise ImporterRegistrationError(
                f"Importer.{method} must be callable.",
                code="invalid_importer",
                context={"field": method},
            )


def entry_suffixes(importer: Any) -> frozenset[str]:
    """Return validated suffixes in a case-insensitive comparison form."""
    return frozenset(
        value.casefold()
        for value in importer.entry_suffixes
    )


__all__ = ["entry_suffixes", "validate_importer"]
