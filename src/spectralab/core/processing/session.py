"""Explicit, transactional processing session for one Spectrum1D."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from spectralab.core.errors import (
    InvalidProcessingOutputError,
    ProcessingError,
    ProcessingExecutionError,
)
from spectralab.core.model import Axis1D, Signal1D, Spectrum1D
from spectralab.core.model.values import optional_text
from spectralab.core.processing.base import (
    OperationImplementation,
    OperationOutput,
    ProcessedSpectrum,
    operation_parameters,
    validate_operation_definition,
    validate_operation_output,
)
from spectralab.core.processing.records import ProcessingOperation


@dataclass(frozen=True)
class _OperationSnapshot:
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


@dataclass(frozen=True)
class _Applied:
    axis: Axis1D
    signal: Signal1D
    record: ProcessingOperation


def _snapshot(operation: OperationImplementation) -> _OperationSnapshot:
    return _OperationSnapshot(
        operation_id=operation.operation_id,
        name=operation.name,
        technique=operation.technique,
        version=operation.version,
        parameters=operation_parameters(operation),
        changes_axis=operation.changes_axis,
        axis_change_description=operation.axis_change_description,
        changes_signal_semantics=operation.changes_signal_semantics,
        changes_signal_unit=operation.changes_signal_unit,
        signal_change_description=operation.signal_change_description,
    )


class ProcessingSession:
    """Apply explicitly requested operations to one immutable Spectrum1D.

    Successful operation outputs are stored as immutable axis/signal states.
    Undo/redo restores those exact stored states rather than replaying
    algorithms, so non-deterministic implementations cannot change an already
    recorded result. The original Spectrum1D is never modified or replaced.
    """

    def __init__(
        self,
        spectrum: Spectrum1D,
        *,
        session_id: str | None = None,
    ) -> None:
        if not isinstance(spectrum, Spectrum1D):
            raise ProcessingError(
                "ProcessingSession requires a Spectrum1D.",
                code="session_source",
                context={"type": type(spectrum).__name__},
            )
        self._source = spectrum
        self._session_id = optional_text(
            session_id,
            field="processing.session_id",
            error_cls=ProcessingError,
        )
        self._applied: list[_Applied] = []
        self._redo: list[_Applied] = []

    @property
    def source(self) -> Spectrum1D:
        return self._source

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def history(self) -> tuple[ProcessingOperation, ...]:
        return tuple(entry.record for entry in self._applied)

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(record.operation_id for record in self.history)

    @property
    def can_undo(self) -> bool:
        return bool(self._applied)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def current(self) -> ProcessedSpectrum:
        """Return the current immutable processed state."""
        axis, signal = self._current_axis_signal()
        return ProcessedSpectrum(
            source=self._source,
            axis=axis,
            signal=signal,
            history=self.history,
            session_id=self._session_id,
        )

    def current_spectrum(self) -> ProcessedSpectrum:
        """Return the current immutable processed state."""
        return self.current

    def _execute(
        self,
        operation: OperationImplementation,
    ) -> tuple[_OperationSnapshot, OperationOutput]:
        """Execute and validate an operation without changing session state."""
        validate_operation_definition(operation)
        snapshot = _snapshot(operation)
        input_axis, input_signal = self._current_axis_signal()

        try:
            output = operation.apply(input_axis, input_signal)
        except ProcessingError:
            raise
        except Exception as exc:
            code = getattr(exc, "code", None)
            if not isinstance(code, str) or not code.strip():
                code = "operation_failed"
            context: dict[str, Any] = {
                "operation_id": snapshot.operation_id,
                "cause_type": type(exc).__name__,
            }
            legacy_context = getattr(exc, "context", None)
            if isinstance(legacy_context, Mapping):
                context.update(legacy_context)
            raise ProcessingExecutionError(
                f"Operation {snapshot.operation_id!r} failed; the previous "
                f"session state was kept: {exc}",
                code=code,
                context=context,
            ) from exc

        if not isinstance(output, OperationOutput):
            raise InvalidProcessingOutputError(
                "Operation.apply() must return an OperationOutput.",
                code="invalid_operation_output",
                context={
                    "operation_id": snapshot.operation_id,
                    "type": type(output).__name__,
                },
            )
        validate_operation_output(
            snapshot,
            input_axis,
            input_signal,
            output,
        )
        return snapshot, output

    def preview(self, operation: OperationImplementation) -> OperationOutput:
        """Execute one operation without committing history or redo state."""
        _snapshot_value, output = self._execute(operation)
        return output

    def apply(self, operation: OperationImplementation) -> ProcessedSpectrum:
        """Execute one operation and commit it only after full validation."""
        snapshot, output = self._execute(operation)
        order = len(self._applied) + 1
        input_state_id = "original" if order == 1 else f"step-{order - 1}"
        output_state_id = f"step-{order}"
        record = ProcessingOperation(
            order=order,
            operation_id=snapshot.operation_id,
            name=snapshot.name,
            technique=snapshot.technique,
            version=snapshot.version,
            parameters=snapshot.parameters,
            input_state_id=input_state_id,
            output_state_id=output_state_id,
            input_dataset_id=self._source.dataset_id,
            changes_axis=snapshot.changes_axis,
            axis_change_description=snapshot.axis_change_description,
            changes_signal_semantics=snapshot.changes_signal_semantics,
            changes_signal_unit=snapshot.changes_signal_unit,
            signal_change_description=snapshot.signal_change_description,
            warnings=output.warnings,
            assumptions=output.assumptions,
            diagnostics=output.diagnostics,
        )

        # Build the candidate before mutating the session. Any failure above
        # therefore leaves the previous state and redo stack untouched.
        candidate_history = (*self.history, record)
        candidate = ProcessedSpectrum(
            source=self._source,
            axis=output.axis,
            signal=output.signal,
            history=candidate_history,
            session_id=self._session_id,
        )

        self._applied.append(
            _Applied(
                axis=output.axis,
                signal=output.signal,
                record=record,
            )
        )
        self._redo.clear()
        return candidate

    def undo(self) -> ProcessedSpectrum:
        """Undo the last applied operation and return the exact prior state."""
        if self._applied:
            self._redo.append(self._applied.pop())
        return self.current

    def redo(self) -> ProcessedSpectrum:
        """Restore the next undone state exactly, without replaying it."""
        if self._redo:
            self._applied.append(self._redo.pop())
        return self.current

    def reset(self) -> ProcessedSpectrum:
        """Discard all applied and undone operations, returning to the source."""
        self._applied.clear()
        self._redo.clear()
        return self.current

    def _current_axis_signal(self):
        if self._applied:
            entry = self._applied[-1]
            return entry.axis, entry.signal
        return self._source.axis, self._source.raw_signal


__all__ = ["ProcessingSession"]
