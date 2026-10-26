"""Export a styled EPR plot without touching scientific data.

The exporter renders already-loaded arrays with the same
:func:`epr_workflow.plot_settings.draw_spectrum` function used by the GUI
canvas. It deliberately does not read the ASC file, rerun preprocessing, or
write CSV/JSON scientific records.

A temporary file in the target directory is written first and then atomically
replaced, so a failed save cannot leave a truncated image in place of an
existing output.
"""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from epr_workflow.plot_asc import DEFAULT_DPI, DEFAULT_FIGSIZE, guard_output_paths
from epr_workflow.plot_settings import (
    CurveData,
    PlotSettings,
    PlotSettingsError,
    draw_spectrum,
    validate_plot_settings,
)

MIN_FIGURE_INCH = 0.5
MAX_FIGURE_INCH = 100.0
MIN_DPI = 50
MAX_DPI = 1200


@dataclass(frozen=True)
class PlotExportSettings:
    """Options shown in the Export Plot dialog."""

    width_in: float = DEFAULT_FIGSIZE[0]
    height_in: float = DEFAULT_FIGSIZE[1]
    dpi: int = DEFAULT_DPI
    include_title: bool = True
    include_legend: bool = True

    def __post_init__(self) -> None:
        for name in ("width_in", "height_in"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PlotSettingsError(
                    f"{name} must be a number.",
                    code="plot_export_size",
                    context={name: value},
                )
            number = float(value)
            if (
                not math.isfinite(number)
                or number < MIN_FIGURE_INCH
                or number > MAX_FIGURE_INCH
            ):
                raise PlotSettingsError(
                    f"{name} must be between {MIN_FIGURE_INCH} and "
                    f"{MAX_FIGURE_INCH} inches.",
                    code="plot_export_size",
                    context={name: value},
                )
        if isinstance(self.dpi, bool) or not isinstance(self.dpi, int):
            raise PlotSettingsError(
                "DPI must be an integer.",
                code="plot_export_dpi",
                context={"dpi": self.dpi},
            )
        if not MIN_DPI <= self.dpi <= MAX_DPI:
            raise PlotSettingsError(
                f"DPI must be between {MIN_DPI} and {MAX_DPI}.",
                code="plot_export_dpi",
                context={"dpi": self.dpi},
            )


def default_plot_path(stem: str, output_base: str | Path) -> Path:
    """Default file for a user-styled plot; never a scientific CSV/JSON name."""
    return Path(output_base) / "figures" / f"{stem}_plot.png"


def export_plot_png(
    *,
    curves: Iterable[CurveData],
    settings: PlotSettings,
    available_keys: Iterable[str],
    output_path: str | Path,
    export_settings: PlotExportSettings | None = None,
    source_path: str | Path,
    overwrite: bool = False,
    cjk_font: str | None = None,
) -> Path:
    """Render and save a PNG using the current plot settings.

    The caller supplies already-loaded curve arrays and their labels. Nothing
    in this function reads the source file or runs a preprocessing algorithm.
    """
    options = export_settings or PlotExportSettings()
    curve_list = list(curves)
    settings = settings.copy()

    validate_plot_settings(
        settings, available_keys, require_visible=True
    )
    if not any(curve.style.visible for curve in curve_list):
        raise PlotSettingsError(
            "At least one curve must be visible to export a plot.",
            code="plot_no_visible_curve",
        )

    target = Path(output_path)
    guard_output_paths(Path(source_path), {"figure": target})
    if target.exists() and not overwrite:
        raise FileExistsError(
            f"Output file already exists: {target}. "
            "Enable overwrite or choose another output directory."
        )

    if not options.include_title:
        settings.axis.title = ""
    if not options.include_legend:
        settings.axis.legend_visible = False

    target.parent.mkdir(parents=True, exist_ok=True)
    figure = Figure(figsize=(options.width_in, options.height_in))
    FigureCanvasAgg(figure)
    axes = figure.add_subplot(111)

    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{target.stem}_",
            suffix=".png",
            dir=str(target.parent),
        )
        os.close(fd)
        draw_spectrum(
            axes, curve_list, settings, cjk_font=cjk_font
        )
        figure.savefig(temp_name, dpi=options.dpi, format="png")
        os.replace(temp_name, target)
        temp_name = None
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        figure.clear()

    return target
