"""Immutable records for successfully applied processing operations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from spectralab.core.errors import ProcessingError
from spectralab.core.model.values import optional_text, required_text


def _freeze_text_mapping(
    value: Mapping[str, Any],
    *,
    field_name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProcessingError(
            f"{field_name} must be a mapping.",
            code="record_mapping",
            context={"field": field_name},
        )
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ProcessingError(
                f"{field_name} keys must be non-empty text.",
                code="record_mapping",
                context={"field": field_name},
            )
        result[key] = item
    return MappingProxyType(result)


@dataclass(frozen=True)
class ProcessingOperation:
    """One operation that was successfully applied to a session.

    This is a record, not an executable operation. It contains the parameters
    actually stored at apply time, the execution order, state associations,
    the source dataset identifier when known, declarations about axis/semantic
    changes, and any warnings or assumptions.
    """

    order: int
    operation_id: str
    name: str
    technique: str
    version: str
    parameters: Mapping[str, Any]
    input_state_id: str
    output_state_id: str
    changes_axis: bool = False
    axis_change_description: str | None = None
    changes_signal_semantics: bool = False
    changes_signal_unit: bool = False
    signal_change_description: str | None = None
    warnings: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    input_dataset_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.order, bool) or not isinstance(self.order, int):
            raise ProcessingError(
                "ProcessingOperation.order must be an integer.",
                code="record_order",
            )
        if self.order < 1:
            raise ProcessingError(
                "ProcessingOperation.order must be at least 1.",
                code="record_order",
                context={"order": self.order},
            )

        for field_name in (
            "operation_id",
            "name",
            "technique",
            "version",
            "input_state_id",
            "output_state_id",
        ):
            object.__setattr__(
                self,
                field_name,
                required_text(
                    getattr(self, field_name),
                    field=f"operation.{field_name}",
                    error_cls=ProcessingError,
                ),
            )

        parameters = _freeze_text_mapping(
            self.parameters,
            field_name="operation.parameters",
        )
        object.__setattr__(self, "parameters", parameters)
        input_dataset_id = optional_text(
            self.input_dataset_id,
            field="operation.input_dataset_id",
            error_cls=ProcessingError,
        )
        object.__setattr__(self, "input_dataset_id", input_dataset_id)

        for flag_name in (
            "changes_axis",
            "changes_signal_semantics",
            "changes_signal_unit",
        ):
            if not isinstance(getattr(self, flag_name), bool):
                raise ProcessingError(
                    f"operation.{flag_name} must be a boolean.",
                    code="record_declaration",
                    context={"field": flag_name},
                )

        axis_description = optional_text(
            self.axis_change_description,
            field="operation.axis_change_description",
            error_cls=ProcessingError,
        )
        signal_description = optional_text(
            self.signal_change_description,
            field="operation.signal_change_description",
            error_cls=ProcessingError,
        )
        object.__setattr__(self, "axis_change_description", axis_description)
        object.__setattr__(self, "signal_change_description", signal_description)

        if self.changes_axis and axis_description is None:
            raise ProcessingError(
                "An operation that changes the axis needs an explicit "
                "axis_change_description.",
                code="axis_change_description",
            )
        if (
            self.changes_signal_semantics or self.changes_signal_unit
        ) and signal_description is None:
            raise ProcessingError(
                "An operation that changes signal semantics or unit needs an "
                "explicit signal_change_description.",
                code="signal_change_description",
            )

        for field_name in ("warnings", "assumptions"):
            values = tuple(getattr(self, field_name))
            if any(not isinstance(item, str) for item in values):
                raise ProcessingError(
                    f"operation.{field_name} must contain text.",
                    code="record_text",
                    context={"field": field_name},
                )
            object.__setattr__(self, field_name, values)

        object.__setattr__(
            self,
            "diagnostics",
            _freeze_text_mapping(
                self.diagnostics,
                field_name="operation.diagnostics",
            ),
        )

    @property
    def operation_name(self) -> str:
        """Alias for the human-readable operation name."""
        return self.name


__all__ = ["ProcessingOperation"]
