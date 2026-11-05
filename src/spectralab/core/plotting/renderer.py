"""Matplotlib-axes renderer for generic Spectrum1D/ProcessedSpectrum series."""

from __future__ import annotations

from typing import Any, Iterable

from spectralab.core.errors import PlottingError
from spectralab.core.model import Spectrum1D
from spectralab.core.plotting.series import (
    Series1D,
    build_series,
    format_axis_label,
    format_signal_label,
)
from spectralab.core.plotting.settings import PlotConfig
from spectralab.core.processing import ProcessedSpectrum


def _series_tuple(series: Iterable[Series1D]) -> tuple[Series1D, ...]:
    values = tuple(series)
    if not values:
        raise PlottingError(
            "At least one series is required for plotting.",
            code="plot_no_series",
        )
    if any(not isinstance(item, Series1D) for item in values):
        raise PlottingError(
            "All plot series must be Series1D objects.",
            code="plot_series_data",
        )
    return values


def _common_label(
    values: Iterable[str],
    *,
    axis: str,
) -> str:
    unique = set(values)
    if len(unique) > 1:
        raise PlottingError(
            f"Series have different {axis} labels. Supply an explicit "
            f"{axis}label; the plotting layer does not choose one silently.",
            code=f"plot_ambiguous_{axis}label",
            context={"labels": sorted(unique)},
        )
    return next(iter(unique), "")


def resolve_xlabel(series: Iterable[Series1D], config: PlotConfig) -> str:
    """Return the explicit X label or a shared metadata-derived label."""
    if config.xlabel is not None:
        return config.xlabel
    values = _series_tuple(series)
    return _common_label(
        (format_axis_label(item.axis) for item in values),
        axis="x",
    )


def resolve_ylabel(series: Iterable[Series1D], config: PlotConfig) -> str:
    """Return the explicit Y label or a shared metadata-derived label."""
    if config.ylabel is not None:
        return config.ylabel
    values = _series_tuple(series)
    return _common_label(
        (format_signal_label(item.signal) for item in values),
        axis="y",
    )


def render_series(
    axes: Any,
    series: Iterable[Series1D],
    config: PlotConfig | None = None,
    *,
    title: str | None = None,
) -> list[Any]:
    """Draw generic series into an existing Matplotlib axes.

    The function only reads ``Series1D`` arrays. It does not sort, reverse,
    clip, interpolate, smooth or otherwise process data. The axes are cleared
    before drawing.
    """
    options = config or PlotConfig()
    if not isinstance(options, PlotConfig):
        raise PlottingError(
            "config must be a PlotConfig or None.",
            code="plot_config",
            context={"type": type(options).__name__},
        )
    values = _series_tuple(series)

    xlabel = resolve_xlabel(values, options)
    ylabel = resolve_ylabel(values, options)
    effective_title = (
        title
        if title is not None
        else (options.title if options.title is not None else "")
    )

    axes.clear()
    plotted: list[Any] = []
    for item in values:
        style = options.style_for(item.kind)
        plotted.append(
            axes.plot(
                item.x_values,
                item.y_values,
                color=style.color,
                linewidth=style.linewidth,
                linestyle=style.linestyle,
                label=item.label,
            )[0]
        )

    axes.set_title(effective_title)
    axes.set_xlabel(xlabel)
    axes.set_ylabel(ylabel)
    if options.grid_visible:
        axes.grid(
            True,
            which="major",
            color="#b0b0b0",
            alpha=0.35,
            linewidth=0.6,
        )
    else:
        axes.grid(False)
    if options.xlim is not None:
        axes.set_xlim(*options.xlim)
    if options.ylim is not None:
        axes.set_ylim(*options.ylim)
    if options.legend_visible and plotted:
        axes.legend(loc=options.legend_location, frameon=False)
    return plotted


def plot_spectrum(
    axes: Any,
    source: Spectrum1D | ProcessedSpectrum,
    config: PlotConfig | None = None,
    *,
    include_raw: bool = True,
) -> list[Any]:
    """Plot a Spectrum1D or ProcessedSpectrum into an existing axes.

    For ``ProcessedSpectrum`` the default includes the source raw series and
    the processed series, with different kinds, labels and line styles.
    Metadata title is used only when ``config.title`` is ``None``.
    """
    if not isinstance(include_raw, bool):
        raise PlottingError(
            "include_raw must be a boolean.",
            code="plot_config",
            context={"field": "include_raw"},
        )
    options = config or PlotConfig()
    if not isinstance(options, PlotConfig):
        raise PlottingError(
            "config must be a PlotConfig or None.",
            code="plot_config",
            context={"type": type(options).__name__},
        )
    series = build_series(source, config=options, include_raw=include_raw)
    title = (
        options.title
        if options.title is not None
        else (source.metadata.title or "")
    )
    return render_series(axes, series, options, title=title)


__all__ = [
    "plot_spectrum",
    "render_series",
    "resolve_xlabel",
    "resolve_ylabel",
]
