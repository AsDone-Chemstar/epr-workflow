"""Independent SpectraLab EPR technique backend.

The package contains its own ASC/BES3T readers and baseline/Savitzky-Golay
implementation. It does not import the legacy ``epr_workflow`` package.
"""

from spectralab.techniques.epr.importers import (
    BES3TImporter,
    EPR_IMPORTERS,
    Bes3tImporter,
    XeprASCImporter,
    XeprAscImporter,
    register_epr_importers,
)
from spectralab.techniques.epr.processing_adapter import (
    EPRLinearBaselineOperation,
    EPRSavitzkyGolayOperation,
    BaselineWindow,
    EprLinearBaselineOperation,
    EprProcessingError,
    EprSavitzkyGolayOperation,
    LinearBaselineSpec,
    SavgolSpec,
)

__all__ = [
    "BES3TImporter",
    "BaselineWindow",
    "EPRLinearBaselineOperation",
    "EPR_IMPORTERS",
    "EPRSavitzkyGolayOperation",
    "Bes3tImporter",
    "EprLinearBaselineOperation",
    "EprProcessingError",
    "EprSavitzkyGolayOperation",
    "LinearBaselineSpec",
    "SavgolSpec",
    "XeprASCImporter",
    "XeprAscImporter",
    "register_epr_importers",
]
