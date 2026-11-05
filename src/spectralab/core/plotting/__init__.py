"""Technique-independent plotting foundation for Spectrum1D."""

from spectralab.core.errors import PlottingError
from spectralab.core.plotting.renderer import (
    plot_spectrum,
    render_series,
    resolve_xlabel,
    resolve_ylabel,
)
from spectralab.core.plotting.series import (
    SERIES_KINDS,
    Series1D,
    SeriesKind,
    build_series,
    format_axis_label,
    format_signal_label,
    series_from_processed,
    series_from_spectrum,
)
from spectralab.core.plotting.settings import (
    LEGEND_LOCATIONS,
    LINE_STYLES,
    LineStyle,
    PlotConfig,
)

__all__ = [
    "LEGEND_LOCATIONS",
    "LINE_STYLES",
    "LineStyle",
    "PlotConfig",
    "PlottingError",
    "SERIES_KINDS",
    "Series1D",
    "SeriesKind",
    "build_series",
    "format_axis_label",
    "format_signal_label",
    "plot_spectrum",
    "render_series",
    "resolve_xlabel",
    "resolve_ylabel",
    "series_from_processed",
    "series_from_spectrum",
]
