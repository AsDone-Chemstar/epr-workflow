"""Generic processing primitives for immutable Spectrum1D data."""

from spectralab.core.errors import (
    InvalidProcessingOperationError,
    InvalidProcessingOutputError,
    ProcessingError,
    ProcessingExecutionError,
)
from spectralab.core.processing.base import (
    OperationImplementation,
    OperationOutput,
    ProcessedSpectrum,
    operation_parameters,
    validate_operation_definition,
    validate_operation_output,
)
from spectralab.core.processing.records import ProcessingOperation
from spectralab.core.processing.session import ProcessingSession

__all__ = [
    "InvalidProcessingOperationError",
    "InvalidProcessingOutputError",
    "OperationImplementation",
    "OperationOutput",
    "ProcessedSpectrum",
    "ProcessingError",
    "ProcessingExecutionError",
    "ProcessingOperation",
    "ProcessingSession",
    "operation_parameters",
    "validate_operation_definition",
    "validate_operation_output",
]
