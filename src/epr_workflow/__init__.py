"""EPR data analysis workflow.

Provides raw Bruker Xepr ASCII (``.ASC``) and BES3T (``.DSC`` + ``.DTA``)
import, validation, plotting and export, plus explicit, user-triggered
preprocessing. Nothing is applied automatically and raw data are never
modified.
"""

from epr_workflow.bes3t import (
    Bes3tDataError,
    Bes3tError,
    Bes3tFormatError,
    find_companion_dta,
    read_bes3t,
)
from epr_workflow.plot_asc import (
    AscDataError,
    AscFormatError,
    ImportResult,
    batch_process_directory,
    build_metadata,
    discover_asc_files,
    discover_dataset_files,
    main,
    plot_spectrum,
    read_asc,
    read_dataset,
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
    "Bes3tDataError",
    "Bes3tError",
    "Bes3tFormatError",
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
    "discover_dataset_files",
    "find_companion_dta",
    "fit_linear_baseline",
    "main",
    "plot_spectrum",
    "processing_data_kind",
    "read_asc",
    "read_bes3t",
    "read_dataset",
    "smooth_savgol",
    "validate_baseline_data",
    "validate_baseline_spec",
    "validate_savgol_spec",
]

__version__ = "0.2.0"
