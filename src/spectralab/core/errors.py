"""Stable error types for the technique-independent spectrum model."""

from __future__ import annotations

from typing import Any, Mapping


class SpectrumModelError(ValueError):
    """Base error for invalid spectrum-model input.

    The model is intentionally small and does not perform scientific
    processing. Errors carry a stable code and context so later layers can
    translate or report them without parsing messages.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "spectrum_model",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


class AxisValidationError(SpectrumModelError):
    """The X-axis values or direction metadata are invalid."""


class SignalValidationError(SpectrumModelError):
    """The Y-axis values or signal semantics are invalid."""


class SpectrumValidationError(SpectrumModelError):
    """A Spectrum1D is inconsistent (for example mismatched lengths)."""


class ImportFailure(ValueError):
    """Base error for importer selection and import failures.

    ``code`` is stable for display-layer translation and scientific records.
    The core never embeds translated user-facing text in the exception.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "import_failure",
        context: Mapping[str, Any] | None = None,
        severity: str = "error",
    ) -> None:
        super().__init__(message)
        if not isinstance(code, str) or not code.strip():
            raise ValueError("ImportFailure.code must be non-empty text.")
        if severity not in ("error", "warning"):
            raise ValueError("ImportFailure.severity must be 'error' or 'warning'.")
        self.code = code
        self.context = dict(context or {})
        self.severity = severity


class UnsupportedFormatError(ImportFailure):
    """No registered importer can safely handle the entry."""

    def __init__(
        self,
        message: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="unsupported_format",
            context=context,
        )


class AmbiguousFormatError(ImportFailure):
    """More than one importer claims the entry and no hint resolves it."""

    def __init__(
        self,
        message: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="ambiguous_format",
            context=context,
        )


class ImporterRegistrationError(ImportFailure):
    """An importer definition or registration violates registry rules."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "importer_registration",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, context=context)


class ExportError(ValueError):
    """Base error for generic Spectrum1D export failures.

    ``code`` is stable for callers; messages remain in English and contain no
    translated GUI text.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "export_failure",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if not isinstance(code, str) or not code.strip():
            raise ValueError("ExportError.code must be non-empty text.")
        self.code = code
        self.context = dict(context or {})


class ExportPathError(ExportError):
    """The requested output path is invalid or would modify protected input."""


class ExportSerializationError(ExportError):
    """A value cannot be serialized without changing or discarding it."""


class OutputExistsError(ExportError, FileExistsError):
    """An output exists and overwrite was not explicitly requested."""

    def __init__(
        self,
        message: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            message,
            code="output_exists",
            context=context,
        )


class ProcessingError(ValueError):
    """Base error for generic processing operations and sessions."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "processing_failure",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if not isinstance(code, str) or not code.strip():
            raise ValueError("ProcessingError.code must be non-empty text.")
        self.code = code
        self.context = dict(context or {})


class InvalidProcessingOperationError(ProcessingError):
    """An operation definition or parameter set is invalid."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_operation",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, context=context)


class InvalidProcessingOutputError(ProcessingError):
    """An operation returned an invalid or undeclared output state."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_output",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, context=context)


class ProcessingExecutionError(ProcessingError):
    """An operation failed while executing."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "operation_failed",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message, code=code, context=context)


class PlottingError(ValueError):
    """Base error for generic plotting input, labels and configuration.

    The plotting layer never silently repairs invalid input or invents labels.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "plotting_failure",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        if not isinstance(code, str) or not code.strip():
            raise ValueError("PlottingError.code must be non-empty text.")
        self.code = code
        self.context = dict(context or {})


__all__ = [
    "AmbiguousFormatError",
    "AxisValidationError",
    "ExportError",
    "ExportPathError",
    "ExportSerializationError",
    "ImportFailure",
    "ImporterRegistrationError",
    "InvalidProcessingOperationError",
    "InvalidProcessingOutputError",
    "OutputExistsError",
    "PlottingError",
    "ProcessingError",
    "ProcessingExecutionError",
    "SignalValidationError",
    "SpectrumModelError",
    "SpectrumValidationError",
    "UnsupportedFormatError",
]
