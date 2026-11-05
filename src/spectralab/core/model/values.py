"""Shared validation helpers for the neutral Spectrum1D model."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

import numpy as np

from spectralab.core.errors import SpectrumModelError


def readonly_float_array(
    values: Any,
    *,
    field: str,
    error_cls: type[SpectrumModelError],
    min_points: int = 2,
) -> np.ndarray:
    """Return a copied, finite, one-dimensional float64 read-only array.

    The input is never modified. Numeric values are copied into float64;
    integer/float32 values therefore share their numerical meaning but the
    original storage dtype is not retained in the model (source provenance may
    retain it separately).

    Read-only is a practical guard against accidental mutation of this object,
    not a security boundary: a caller that deliberately calls
    ``setflags(write=True)`` on its own copy can bypass it.
    """
    try:
        array = np.asarray(values)
    except Exception as exc:  # ragged lists, unsupported array-like objects
        raise error_cls(
            f"{field} cannot be converted to a one-dimensional numeric array.",
            code="array",
            context={"field": field, "error": str(exc)},
        ) from exc

    if array.ndim != 1:
        raise error_cls(
            f"{field} must be one-dimensional; got {array.ndim} dimensions.",
            code="array",
            context={"field": field, "ndim": int(array.ndim)},
        )
    if array.size < min_points:
        raise error_cls(
            f"{field} must contain at least {min_points} points; got "
            f"{array.size}.",
            code="array",
            context={"field": field, "size": int(array.size), "min": min_points},
        )
    if np.iscomplexobj(array):
        raise error_cls(
            f"{field} must be real-valued; complex data are not supported.",
            code="complex",
            context={"field": field},
        )
    if array.dtype.kind not in "iuf":
        raise error_cls(
            f"{field} must contain real numeric values; got dtype "
            f"{array.dtype}.",
            code="array",
            context={"field": field, "dtype": str(array.dtype)},
        )

    try:
        copied = np.array(array, dtype=np.float64, copy=True)
    except (TypeError, ValueError, OverflowError) as exc:
        raise error_cls(
            f"{field} could not be converted to float64.",
            code="array",
            context={"field": field, "error": str(exc)},
        ) from exc

    if not np.all(np.isfinite(copied)):
        bad = int(np.flatnonzero(~np.isfinite(copied))[0])
        raise error_cls(
            f"{field} contains a non-finite value at index {bad}.",
            code="nonfinite",
            context={"field": field, "index": bad},
        )

    copied.setflags(write=False)
    return copied


def optional_text(
    value: Any,
    *,
    field: str,
    error_cls: type[SpectrumModelError],
) -> str | None:
    """Validate optional metadata text without inventing a value.

    ``None`` means unknown. Non-empty strings are preserved exactly; empty or
    whitespace-only strings and surrounding whitespace are rejected so that
    the model never silently normalizes metadata.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise error_cls(
            f"{field} must be text or None.",
            code="text",
            context={"field": field, "type": type(value).__name__},
        )
    if not value.strip():
        raise error_cls(
            f"{field} must not be empty; use None for unknown metadata.",
            code="text",
            context={"field": field},
        )
    if value != value.strip():
        raise error_cls(
            f"{field} must not have leading or trailing whitespace.",
            code="text",
            context={"field": field, "value": value},
        )
    return value


def required_text(
    value: Any,
    *,
    field: str,
    error_cls: type[SpectrumModelError],
) -> str:
    """Validate required non-empty text."""
    result = optional_text(value, field=field, error_cls=error_cls)
    if result is None:
        raise error_cls(
            f"{field} is required.",
            code="text",
            context={"field": field},
        )
    return result


def freeze_mapping(
    value: Mapping[str, Any] | None,
    *,
    field: str,
    error_cls: type[SpectrumModelError],
) -> Mapping[str, Any]:
    """Shallow-copy a mapping into an immutable mapping proxy.

    Nested values are not deep-frozen. This is intentional: source format
    metadata can be arbitrarily nested, and deep-copying/freezing it on every
    construction would add cost without a clear need in M1.
    """
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise error_cls(
            f"{field} must be a mapping or None.",
            code="mapping",
            context={"field": field, "type": type(value).__name__},
        )
    return MappingProxyType(dict(value))


__all__ = [
    "freeze_mapping",
    "optional_text",
    "readonly_float_array",
    "required_text",
]
