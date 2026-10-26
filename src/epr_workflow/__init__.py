"""EPR data analysis workflow.

Provides raw Bruker Xepr ASCII (``.ASC``) import, validation, plotting and
export, plus an explicit, user-triggered linear baseline correction step.
Nothing is applied automatically and raw data are never modified.
"""

from epr_workflow.plot_asc import (
    AscDataError,
    AscFormatError,
    ImportResult,
    batch_process_directory,
    build_metadata,
    discover_asc_files,
    main,
    plot_spectrum,
    read_asc,
)
from epr_workflow.preprocessing import (
    INPUT_CURRENT,
    INPUT_RAW,
    SAVGOL_OPERATION,
    BaselineWindow,
    LinearBaselineSpec,
    PreprocessingError,
    PreprocessingResult,
    PreprocessingSession,
    PreprocessingStep,
    SavgolDiagnostics,
    SavgolSpec,
    apply_linear_baseline,
    build_preprocessing_record,
    fit_linear_baseline,
    processing_data_kind,
    smooth_savgol,
    validate_baseline_data,
    validate_baseline_spec,
    validate_savgol_spec,
)

__all__ = [
    "AscDataError",
    "AscFormatError",
    "BaselineWindow",
    "INPUT_CURRENT",
    "INPUT_RAW",
    "ImportResult",
    "LinearBaselineSpec",
    "PreprocessingError",
    "PreprocessingResult",
    "PreprocessingSession",
    "PreprocessingStep",
    "SAVGOL_OPERATION",
    "SavgolDiagnostics",
    "SavgolSpec",
    "apply_linear_baseline",
    "batch_process_directory",
    "build_metadata",
    "build_preprocessing_record",
    "discover_asc_files",
    "fit_linear_baseline",
    "main",
    "plot_spectrum",
    "processing_data_kind",
    "read_asc",
    "smooth_savgol",
    "validate_baseline_data",
    "validate_baseline_spec",
    "validate_savgol_spec",
]

__version__ = "0.1.0"
