"""Generic operation protocol, output and processed-spectrum container."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

import numpy as np

from spectralab.core.errors import (
    InvalidProcessingOperationError,
    InvalidProcessingOutputError,
    ProcessingError,
)
from spectralab.core.model import Axis1D, Signal1D, Spectrum1D
from spectralab.core.model.values import optional_text, required_text
from spectralab.core.processing.records import ProcessingOperation

_DECLARATION_FIELDS = (
    "changes_axis",
    "changes_signal_semantics",
    "changes_signal_unit",
)


def _freeze_mapping(
    value: Mapping[str, Any],
    *,
    field_name: str,
    error_cls: type[ProcessingError] = InvalidProcessingOperationError,
    code: str = "invalid_operation_parameters",
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise error_cls(
            f"{field_name} must be a mapping.",
            code=code,
            context={"field": field_name},
        )
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise error_cls(
                f"{field_name} keys must be non-empty text.",
                code=code,
                context={"field": field_name},
            )
        result[key] = item
    return MappingProxyType(result)


@dataclass(frozen=True)
class OperationOutput:
    """The complete output of one operation execution."""

    axis: Axis1D
    signal: Signal1D
    warnings: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.axis, Axis1D):
            raise InvalidProcessingOutputError(
                "OperationOutput.axis must be an Axis1D.",
                code="invalid_operation_output",
            )
        if not isinstance(self.signal, Signal1D):
            raise InvalidProcessingOutputError(
                "OperationOutput.signal must be a Signal1D.",
                code="invalid_operation_output",
            )
        if self.axis.point_count != self.signal.point_count:
            raise InvalidProcessingOutputError(
                "OperationOutput axis and signal lengths differ.",
                code="invalid_operation_output",
                context={
                    "axis": self.axis.point_count,
                    "signal": self.signal.point_count,
                },
            )

        for field_name in ("warnings", "assumptions"):
            values = tuple(getattr(self, field_name))
            if any(not isinstance(item, str) for item in values):
                raise InvalidProcessingOutputError(
                    f"OperationOutput.{field_name} must contain text.",
                    code="invalid_operation_output",
                    context={"field": field_name},
                )
            object.__setattr__(self, field_name, values)

        object.__setattr__(
            self,
            "diagnostics",
            _freeze_mapping(
                self.diagnostics,
                field_name="OperationOutput.diagnostics",
                error_cls=InvalidProcessingOutputError,
                code="invalid_operation_output",
            ),
        )


@runtime_checkable
class OperationImplementation(Protocol):
    """Executable operation interface implemented by technique modules."""

    operation_id: str
    name: str
    technique: str
    version: str
    parameters: Mapping[str, Any]
    changes_axis: bool
    axis_change_description: str | None
    changes_signal_semantics: bool
    changes_signal_unit: bool
    signal_change_description: str | None

    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput:
        """Return a complete new axis/signal state or raise."""


@dataclass(frozen=True)
class ProcessedSpectrum:
    """A processed view associated with one unchanged source Spectrum1D.

    The source object is retained, so original metadata and provenance are
    never discarded. ``history`` contains only successfully applied operation
    records, in order. Processed axis/signal arrays are immutable.
    """

    source: Spectrum1D
    axis: Axis1D
    signal: Signal1D
    history: tuple[ProcessingOperation, ...] = ()
    session_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source, Spectrum1D):
            raise ProcessingError(
                "ProcessedSpectrum.source must be a Spectrum1D.",
                code="processed_source",
            )
        if not isinstance(self.axis, Axis1D):
            raise ProcessingError(
                "ProcessedSpectrum.axis must be an Axis1D.",
                code="processed_axis",
            )
        if not isinstance(self.signal, Signal1D):
            raise ProcessingError(
                "ProcessedSpectrum.signal must be a Signal1D.",
                code="processed_signal",
            )
        if self.axis.point_count != self.signal.point_count:
            raise ProcessingError(
                "ProcessedSpectrum axis and signal lengths differ.",
                code="processed_length",
                context={
                    "axis": self.axis.point_count,
                    "signal": self.signal.point_count,
                },
            )

        history = tuple(self.history)
        if any(not isinstance(item, ProcessingOperation) for item in history):
            raise ProcessingError(
                "ProcessedSpectrum.history must contain ProcessingOperation "
                "records.",
                code="processed_history",
            )
        for index, record in enumerate(history, start=1):
            if record.order != index:
                raise ProcessingError(
                    "ProcessedSpectrum history order is not contiguous.",
                    code="processed_history_order",
                    context={
                        "position": index,
                        "record_order": record.order,
                    },
                )
        object.__setattr__(self, "history", history)

        session_id = optional_text(
            self.session_id,
            field="processed.session_id",
            error_cls=ProcessingError,
        )
        object.__setattr__(self, "session_id", session_id)

    @property
    def source_spectrum(self) -> Spectrum1D:
        return self.source

    @property
    def raw_spectrum(self) -> Spectrum1D:
        return self.source

    @property
    def processing_history(self) -> tuple[ProcessingOperation, ...]:
        return self.history

    @property
    def metadata(self):
        return self.source.metadata

    @property
    def provenance(self):
        return self.source.provenance

    @property
    def technique(self) -> str:
        return self.source.technique

    @property
    def source_format(self) -> str | None:
        return self.source.source_format

    @property
    def point_count(self) -> int:
        return self.axis.point_count

    @property
    def x_values(self):
        return self.axis.values

    @property
    def y_values(self):
        return self.signal.values

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(record.operation_id for record in self.history)

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(
            warning
            for record in self.history
            for warning in record.warnings
        )

    @property
    def assumptions(self) -> tuple[str, ...]:
        return tuple(
            assumption
            for record in self.history
            for assumption in record.assumptions
        )

    @property
    def is_original(self) -> bool:
        return not self.history

    def __len__(self) -> int:
        return self.point_count


def _operation_attr(operation: Any, name: str) -> Any:
    try:
        return getattr(operation, name)
    except Exception as exc:
        raise InvalidProcessingOperationError(
            f"Operation attribute {name!r} could not be read.",
            code="invalid_operation",
            context={"attribute": name, "error": str(exc)},
        ) from exc


def validate_operation_definition(operation: Any) -> None:
    """Validate an operation definition before execution."""
    for name in (
        "operation_id",
        "name",
        "technique",
        "version",
        "changes_axis",
        "axis_change_description",
        "changes_signal_semantics",
        "changes_signal_unit",
        "signal_change_description",
    ):
        if not hasattr(operation, name):
            raise InvalidProcessingOperationError(
                f"Operation is missing required attribute {name!r}.",
                code="invalid_operation",
                context={"attribute": name},
            )
    for name in ("operation_id", "name", "technique", "version"):
        value = _operation_attr(operation, name)
        if not isinstance(value, str) or not value.strip():
            raise InvalidProcessingOperationError(
                f"Operation.{name} must be non-empty text.",
                code="invalid_operation",
                context={"attribute": name},
            )
        if value != value.strip():
            raise InvalidProcessingOperationError(
                f"Operation.{name} must not have surrounding whitespace.",
                code="invalid_operation",
                context={"attribute": name, "value": value},
            )

    for name in _DECLARATION_FIELDS:
        if not isinstance(_operation_attr(operation, name), bool):
            raise InvalidProcessingOperationError(
                f"Operation.{name} must be a boolean.",
                code="invalid_operation",
                context={"attribute": name},
            )

    axis_description = _operation_attr(operation, "axis_change_description")
    signal_description = _operation_attr(operation, "signal_change_description")
    for name, value in (
        ("axis_change_description", axis_description),
        ("signal_change_description", signal_description),
    ):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise InvalidProcessingOperationError(
                f"Operation.{name} must be non-empty text or None.",
                code="invalid_operation",
                context={"attribute": name},
            )
    if operation.changes_axis and axis_description is None:
        raise InvalidProcessingOperationError(
            "An axis-changing operation needs axis_change_description.",
            code="axis_change_description",
        )
    if (
        operation.changes_signal_semantics or operation.changes_signal_unit
    ) and signal_description is None:
        raise InvalidProcessingOperationError(
            "An operation that changes signal semantics or unit needs "
            "signal_change_description.",
            code="signal_change_description",
        )

    parameters = _operation_attr(operation, "parameters")
    if not isinstance(parameters, Mapping):
        raise InvalidProcessingOperationError(
            "Operation.parameters must be a mapping.",
            code="invalid_operation_parameters",
        )
    if any(not isinstance(key, str) or not key for key in parameters):
        raise InvalidProcessingOperationError(
            "Operation parameter keys must be non-empty text.",
            code="invalid_operation_parameters",
        )

    if not callable(_operation_attr(operation, "apply")):
        raise InvalidProcessingOperationError(
            "Operation.apply must be callable.",
            code="invalid_operation",
        )


def _axes_equal(first: Axis1D, second: Axis1D) -> bool:
    return (
        np.array_equal(first.values, second.values)
        and first.quantity == second.quantity
        and first.unit == second.unit
        and first.name == second.name
        and first.direction == second.direction
        and first.metadata_source == second.metadata_source
        and first.missing_reason == second.missing_reason
    )


def validate_operation_output(
    operation: Any,
    input_axis: Axis1D,
    input_signal: Signal1D,
    output: Any,
) -> None:
    """Reject undeclared axis or signal-semantic changes."""
    if not isinstance(output, OperationOutput):
        raise InvalidProcessingOutputError(
            "Operation.apply() must return an OperationOutput.",
            code="invalid_operation_output",
            context={"type": type(output).__name__},
        )

    if not operation.changes_axis and not _axes_equal(input_axis, output.axis):
        raise InvalidProcessingOutputError(
            "The operation changed the X axis without declaring "
            "changes_axis=True and describing the change.",
            code="undeclared_axis_change",
        )
    if (
        output.signal.semantics != input_signal.semantics
        and not operation.changes_signal_semantics
    ):
        raise InvalidProcessingOutputError(
            "The operation changed signal semantics without declaring "
            "changes_signal_semantics=True.",
            code="undeclared_signal_semantics_change",
            context={
                "input": input_signal.semantics,
                "output": output.signal.semantics,
            },
        )
    if (
        output.signal.unit != input_signal.unit
        and not operation.changes_signal_unit
    ):
        raise InvalidProcessingOutputError(
            "The operation changed the signal unit without declaring "
            "changes_signal_unit=True.",
            code="undeclared_signal_unit_change",
            context={
                "input": input_signal.unit,
                "output": output.signal.unit,
            },
        )


def operation_parameters(operation: Any) -> Mapping[str, Any]:
    """Return an immutable snapshot of the operation parameters."""
    return _freeze_mapping(
        _operation_attr(operation, "parameters"),
        field_name="Operation.parameters",
    )


__all__ = [
    "OperationImplementation",
    "OperationOutput",
    "ProcessedSpectrum",
    "operation_parameters",
    "validate_operation_definition",
    "validate_operation_output",
]
