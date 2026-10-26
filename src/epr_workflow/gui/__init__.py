"""EPR workflow desktop GUI package.

Importing this package must not import Qt, so that the CLI and the test suite
keep working when PySide6 is not installed. Only the GUI-agnostic controller
and the translation catalog are re-exported here; Qt widgets live in
:mod:`epr_workflow.gui.main_window`.
"""

from epr_workflow.gui.controller import (
    BatchOutcome,
    PreprocessingStore,
    SpectrumView,
    load_spectrum,
    open_path,
    run_batch_processing,
    status_label,
)
from epr_workflow.gui.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGES,
    field_order_text,
    has_text,
    normalize_language,
    overall_status_text,
    status_text,
    tr_text,
)

__all__ = [
    "DEFAULT_LANGUAGE",
    "LANGUAGES",
    "BatchOutcome",
    "PreprocessingStore",
    "SpectrumView",
    "field_order_text",
    "has_text",
    "load_spectrum",
    "normalize_language",
    "open_path",
    "overall_status_text",
    "run_batch_processing",
    "status_label",
    "status_text",
    "tr_text",
]
