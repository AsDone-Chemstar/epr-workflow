"""Explicit column mapping and import options for generic FTIR text files.

No column, delimiter, decimal separator, header or FTIR semantic value is
inferred from the numeric content. Defaults are deliberately narrow and are
recorded in provenance: a file with exactly two columns may use column 0 for X
and column 1 for Y; wider files must supply both mappings explicitly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from spectralab.core.errors import ImportFailure
from spectralab.techniques.ftir.importers.semantics import (
    normalize_acquisition_mode,
    normalize_atr_correction_status,
    normalize_axis_quantity,
    normalize_axis_unit,
    normalize_signal_semantics,
)

_OPTION_ERROR = "ftir_invalid_option"


def _fail(message: str, *, code: str, **context: Any) -> ImportFailure:
    return ImportFailure(message, code=code, context=context)


def _optional_text(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _fail(
            f"{field_name} must be text or None.",
            code=_OPTION_ERROR,
            field=field_name,
        )
    if not value.strip():
        raise _fail(
            f"{field_name} must not be empty; use None for unknown.",
            code=_OPTION_ERROR,
            field=field_name,
        )
    if value != value.strip():
        raise _fail(
            f"{field_name} must not have leading or trailing whitespace.",
            code=_OPTION_ERROR,
            field=field_name,
        )
    return value


def parse_column_reference(value: str | int | None) -> int | str | None:
    """Parse CLI/GUI text into an index or header name without guessing.

    Blank text means no explicit mapping. Signed decimal integers are indices;
    every other non-empty value is preserved as a header column name.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise _fail(
            "Column reference must be a non-negative index, a name or None.",
            code=_OPTION_ERROR,
            value=repr(value),
        )
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        raise _fail(
            "Column reference must be text, an integer or None.",
            code=_OPTION_ERROR,
            type=type(value).__name__,
        )
    text = value.strip()
    if not text:
        return None
    digits = text[1:] if text.startswith(("+", "-")) else text
    if digits.isdigit():
        return int(text)
    return text


def _column_reference(value: Any, *, field_name: str, header: bool) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        raise _fail(
            f"{field_name} must be a non-negative column index or a column "
            "name.",
            code=_OPTION_ERROR,
            field=field_name,
        )
    if isinstance(value, int):
        if value < 0:
            raise _fail(
                f"{field_name} must be a non-negative column index.",
                code=_OPTION_ERROR,
                field=field_name,
                value=value,
            )
        return value
    if isinstance(value, str):
        if not value.strip():
            raise _fail(
                f"{field_name} column name must not be empty.",
                code=_OPTION_ERROR,
                field=field_name,
            )
        if value != value.strip():
            raise _fail(
                f"{field_name} column name must not have surrounding "
                "whitespace.",
                code=_OPTION_ERROR,
                field=field_name,
            )
        if not header:
            raise _fail(
                f"{field_name} was given as a column name but header=False. "
                "Column names require a header row.",
                code="ftir_header_required",
                field=field_name,
            )
        return value
    raise _fail(
        f"{field_name} must be a non-negative integer, a column name or None.",
        code=_OPTION_ERROR,
        field=field_name,
    )


def _comment_markers(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values: Sequence[Any] = (value,)
    elif isinstance(value, Sequence) and not isinstance(
        value, (bytes, bytearray)
    ):
        values = value
    else:
        raise _fail(
            "comment must be text, a sequence of text markers or None.",
            code=_OPTION_ERROR,
            field="comment",
        )
    markers: list[str] = []
    for marker in values:
        if not isinstance(marker, str) or not marker:
            raise _fail(
                "Each comment marker must be non-empty text.",
                code=_OPTION_ERROR,
                field="comment",
                value=repr(marker),
            )
        markers.append(marker)
    return tuple(markers)


def _delimiter(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise _fail(
            "delimiter must be 'auto', 'comma', 'tab', 'semicolon', "
            "'whitespace', a one-character delimiter or None.",
            code=_OPTION_ERROR,
            field="delimiter",
        )
    key = value.strip().casefold()
    names = {
        "auto": None,
        ",": ",",
        "comma": ",",
        "\\t": "\t",
        "tab": "\t",
        "\t": "\t",
        ";": ";",
        "semicolon": ";",
        "whitespace": "whitespace",
        "space": "whitespace",
        "spaces": "whitespace",
        " ": "whitespace",
    }
    if key in names:
        return names[key]
    if len(value) != 1:
        raise _fail(
            "A custom delimiter must be exactly one character.",
            code="ftir_invalid_delimiter",
            value=value,
        )
    return value


def _decimal(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(
            "decimal must be '.', ',', 'dot' or 'comma'.",
            code=_OPTION_ERROR,
            field="decimal",
        )
    key = value.strip().casefold()
    if key in (".", "dot"):
        return "."
    if key in (",", "comma"):
        return ","
    raise _fail(
        "decimal must be '.', ',', 'dot' or 'comma'.",
        code="ftir_invalid_decimal_separator",
        value=value,
    )


@dataclass(frozen=True)
class ColumnMapping:
    """Explicit mapping of text columns to the generic X/Y model.

    ``delimiter=None`` means the importer's suffix-based default (comma for
    CSV, whitespace for TXT/DPT). ``comment`` may be one marker or a sequence
    of markers. All values here are user-visible provenance, not guesses.
    """

    x: int | str | None = None
    y: int | str | None = None
    x_name: str | None = None
    x_unit: str | None = None
    y_name: str | None = None
    y_unit: str | None = None
    y_semantics: str = "unknown"
    header: bool = False
    delimiter: str | None = None
    comment: str | Sequence[str] | None = None
    decimal: str = "."
    encoding: str = "utf-8-sig"
    skip_rows: int = 0
    x_quantity: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.header, bool):
            raise _fail(
                "header must be a boolean.",
                code=_OPTION_ERROR,
                field="header",
            )
        object.__setattr__(
            self,
            "x",
            _column_reference(self.x, field_name="x", header=self.header),
        )
        object.__setattr__(
            self,
            "y",
            _column_reference(self.y, field_name="y", header=self.header),
        )
        if self.x is not None and self.x == self.y:
            raise _fail(
                "X and Y must map to different columns.",
                code="ftir_same_column",
                column=self.x,
            )

        for name in ("x_name", "x_unit", "y_name", "y_unit"):
            object.__setattr__(
                self,
                name,
                _optional_text(getattr(self, name), field_name=name),
            )
        object.__setattr__(self, "x_unit", normalize_axis_unit(self.x_unit))

        quantity = self.x_quantity
        if quantity is not None:
            quantity = normalize_axis_quantity(quantity)
        if quantity == "unknown" and self.x_unit is not None:
            raise _fail(
                "x_quantity='unknown' contradicts an explicitly supplied "
                "x_unit. Omit x_quantity and let the unit confirm it, or use "
                "x_quantity='wavenumber'.",
                code="ftir_axis_quantity_unit_conflict",
                x_quantity=quantity,
                x_unit=self.x_unit,
            )
        object.__setattr__(self, "x_quantity", quantity)
        object.__setattr__(
            self,
            "y_semantics",
            normalize_signal_semantics(self.y_semantics),
        )
        object.__setattr__(self, "delimiter", _delimiter(self.delimiter))
        object.__setattr__(self, "comment", _comment_markers(self.comment))
        object.__setattr__(self, "decimal", _decimal(self.decimal))

        if not isinstance(self.encoding, str) or not self.encoding.strip():
            raise _fail(
                "encoding must be non-empty text.",
                code=_OPTION_ERROR,
                field="encoding",
            )
        encoding = self.encoding.strip()
        if encoding != self.encoding:
            raise _fail(
                "encoding must not have surrounding whitespace.",
                code=_OPTION_ERROR,
                field="encoding",
            )
        object.__setattr__(self, "encoding", encoding)

        if isinstance(self.skip_rows, bool) or not isinstance(self.skip_rows, int):
            raise _fail(
                "skip_rows must be a non-negative integer.",
                code=_OPTION_ERROR,
                field="skip_rows",
            )
        if self.skip_rows < 0:
            raise _fail(
                "skip_rows must be a non-negative integer.",
                code=_OPTION_ERROR,
                field="skip_rows",
                value=self.skip_rows,
            )

    @property
    def comment_markers(self) -> tuple[str, ...]:
        return tuple(self.comment) if self.comment else ()

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "ColumnMapping":
        return _mapping_from_mapping(values)

    def as_dict(self) -> dict[str, Any]:
        return {
            "x": self.x,
            "y": self.y,
            "x_name": self.x_name,
            "x_unit": self.x_unit,
            "x_quantity": self.x_quantity,
            "y_name": self.y_name,
            "y_unit": self.y_unit,
            "y_semantics": self.y_semantics,
            "header": self.header,
            "delimiter": self.delimiter,
            "comment": list(self.comment_markers),
            "decimal": self.decimal,
            "encoding": self.encoding,
            "skip_rows": self.skip_rows,
        }


@dataclass(frozen=True)
class FTIRImportOptions:
    """All explicit options accepted by the generic FTIR text importers."""

    mapping: ColumnMapping = field(default_factory=ColumnMapping)
    acquisition_mode: str = "Unknown"
    atr_correction_status: str = "unknown"
    instrument_vendor: str | None = None
    instrument_model: str | None = None

    def __post_init__(self) -> None:
        mapping = self.mapping
        if isinstance(mapping, Mapping):
            mapping = ColumnMapping.from_mapping(mapping)
        if not isinstance(mapping, ColumnMapping):
            raise _fail(
                "mapping must be a ColumnMapping or a mapping of its fields.",
                code=_OPTION_ERROR,
                field="mapping",
            )
        object.__setattr__(self, "mapping", mapping)
        object.__setattr__(
            self,
            "acquisition_mode",
            normalize_acquisition_mode(self.acquisition_mode),
        )
        object.__setattr__(
            self,
            "atr_correction_status",
            normalize_atr_correction_status(self.atr_correction_status),
        )
        object.__setattr__(
            self,
            "instrument_vendor",
            _optional_text(self.instrument_vendor, field_name="instrument_vendor"),
        )
        object.__setattr__(
            self,
            "instrument_model",
            _optional_text(self.instrument_model, field_name="instrument_model"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "mapping": self.mapping.as_dict(),
            "acquisition_mode": self.acquisition_mode,
            "atr_correction_status": self.atr_correction_status,
            "instrument_vendor": self.instrument_vendor,
            "instrument_model": self.instrument_model,
        }

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "FTIRImportOptions":
        return _options_from_mapping(values)


_MAPPING_ALIASES = {
    "x": "x",
    "x_column": "x",
    "x_col": "x",
    "x_index": "x",
    "column_x": "x",
    "y": "y",
    "y_column": "y",
    "y_col": "y",
    "y_index": "y",
    "column_y": "y",
    "x_name": "x_name",
    "axis_name": "x_name",
    "x_unit": "x_unit",
    "axis_unit": "x_unit",
    "x_quantity": "x_quantity",
    "axis_quantity": "x_quantity",
    "y_name": "y_name",
    "signal_name": "y_name",
    "y_unit": "y_unit",
    "signal_unit": "y_unit",
    "y_semantics": "y_semantics",
    "signal_semantics": "y_semantics",
    "header": "header",
    "has_header": "header",
    "include_header": "header",
    "delimiter": "delimiter",
    "separator": "delimiter",
    "comment": "comment",
    "comments": "comment",
    "comment_marker": "comment",
    "comment_markers": "comment",
    "decimal": "decimal",
    "decimal_separator": "decimal",
    "encoding": "encoding",
    "text_encoding": "encoding",
    "skip_rows": "skip_rows",
    "skiprows": "skip_rows",
    "skip_lines": "skip_rows",
}
_OPTION_ALIASES = {
    "acquisition_mode": "acquisition_mode",
    "acquisition": "acquisition_mode",
    "atr_correction_status": "atr_correction_status",
    "atr_correction": "atr_correction_status",
    "atr_status": "atr_correction_status",
    "instrument_vendor": "instrument_vendor",
    "vendor": "instrument_vendor",
    "instrument_model": "instrument_model",
    "model": "instrument_model",
}


def _options_from_mapping(values: Mapping[str, Any]) -> FTIRImportOptions:
    """Build options from an explicit mapping, rejecting unknown keys.

    Accepted shapes include flat FTIR keys (``x``, ``header``,
    ``acquisition_mode``) and a nested ``{"ftir": {...}}`` namespace.
    """
    if not isinstance(values, Mapping):
        raise _fail(
            "FTIR import options must be a mapping.",
            code=_OPTION_ERROR,
            type=type(values).__name__,
        )
    data = dict(values)
    if "ftir" in data or "ftir_options" in data:
        if len(data) != 1:
            raise _fail(
                "The 'ftir' option namespace cannot be mixed with other "
                "option keys.",
                code="ftir_unsupported_option",
                keys=sorted(str(key) for key in data),
            )
        namespace = data.get("ftir", data.get("ftir_options"))
        if isinstance(namespace, FTIRImportOptions):
            return namespace
        if not isinstance(namespace, Mapping):
            raise _fail(
                "The 'ftir' option namespace must contain a mapping or "
                "FTIRImportOptions.",
                code=_OPTION_ERROR,
                type=type(namespace).__name__,
            )
        data = dict(namespace)

    option_values: dict[str, Any] = {}
    mapping_values: dict[str, Any] = {}
    explicit_mapping: ColumnMapping | None = None
    for key, value in data.items():
        name = str(key).casefold()
        if name == "mapping":
            if isinstance(value, ColumnMapping):
                explicit_mapping = value
            elif isinstance(value, Mapping):
                explicit_mapping = ColumnMapping.from_mapping(value)
            else:
                raise _fail(
                    "mapping must be a ColumnMapping or a mapping of fields.",
                    code=_OPTION_ERROR,
                    field="mapping",
                )
            continue
        if name in _OPTION_ALIASES:
            option_values[_OPTION_ALIASES[name]] = value
            continue
        if name in _MAPPING_ALIASES:
            mapping_values[_MAPPING_ALIASES[name]] = value
            continue
        raise _fail(
            f"Unsupported FTIR import option: {key!r}",
            code="ftir_unsupported_option",
            option=str(key),
        )

    if explicit_mapping is not None and mapping_values:
        raise _fail(
            "Supply either 'mapping' or individual column options, not both.",
            code="ftir_ambiguous_options",
            keys=sorted(mapping_values),
        )

    mapping = explicit_mapping or ColumnMapping(**mapping_values)
    return FTIRImportOptions(mapping=mapping, **option_values)


def options_from_mapping(values: Mapping[str, Any]) -> FTIRImportOptions:
    """Public helper used by importers, GUI adapters and tests."""
    return _options_from_mapping(values)


def _mapping_from_mapping(values: Mapping[str, Any]) -> ColumnMapping:
    if not isinstance(values, Mapping):
        raise _fail(
            "Column mapping values must be a mapping.",
            code=_OPTION_ERROR,
            type=type(values).__name__,
        )
    remapped: dict[str, Any] = {}
    for key, value in values.items():
        name = str(key).casefold()
        if name not in _MAPPING_ALIASES:
            raise _fail(
                f"Unsupported column mapping key: {key!r}",
                code="ftir_unsupported_option",
                option=str(key),
            )
        remapped[_MAPPING_ALIASES[name]] = value
    return ColumnMapping(**remapped)


__all__ = [
    "ColumnMapping",
    "FTIRImportOptions",
    "options_from_mapping",
    "parse_column_reference",
]
