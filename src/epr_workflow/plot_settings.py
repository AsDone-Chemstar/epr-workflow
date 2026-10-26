"""User-controlled plot styling for already-loaded EPR spectra.

This module is deliberately free of Qt and file-system dependencies. It
describes **how** existing arrays are drawn; it never reads ASC files, never
runs baseline correction or smoothing, and never modifies the arrays it is
given.

Curve availability is derived from the actual :class:`PreprocessingResult`:

* raw data are always available;
* a processed curve and the raw-minus-processed difference exist only when at
  least one preprocessing step has been applied;
* a fitted baseline exists only when a baseline step recorded a fit.

Intermediate arrays (for example "baseline corrected but not yet smoothed")
are not cached by the current preprocessing session, so they are not offered
here. Fabricating such a curve would misrepresent the processing history.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np

from epr_workflow.preprocessing import (
    BASELINE_OPERATION,
    SAVGOL_OPERATION,
    PreprocessingResult,
)

#: Stable curve identifiers used by both the GUI and the plot exporter.
CURVE_RAW = "raw"
CURVE_PROCESSED = "processed"
CURVE_DIFFERENCE = "difference"
CURVE_FITTED_BASELINE = "fitted_baseline"

CURVE_KEYS = (
    CURVE_RAW,
    CURVE_PROCESSED,
    CURVE_DIFFERENCE,
    CURVE_FITTED_BASELINE,
)

#: Drawing order: raw and derived guides behind the final processed curve.
CURVE_RENDER_ORDER = (
    CURVE_RAW,
    CURVE_FITTED_BASELINE,
    CURVE_DIFFERENCE,
    CURVE_PROCESSED,
)

LINE_STYLES = ("-", "--", ":", "-.")

LEGEND_LOCATIONS = (
    "best",
    "upper right",
    "upper left",
    "lower right",
    "lower left",
    "center right",
    "center left",
    "upper center",
    "lower center",
    "center",
)

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

#: Default figure and font sizes, matching the pre-editor GUI conventions.
DEFAULT_TITLE_FONTSIZE = 12.0
DEFAULT_AXIS_FONTSIZE = 10.0
DEFAULT_TICK_FONTSIZE = 10.0
DEFAULT_LEGEND_FONTSIZE = 8.0


class PlotSettingsError(ValueError):
    """Invalid plot settings, with a stable code for GUI translation."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "plot_settings",
        context: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})


def normalize_color(color: str) -> str:
    """Return a lower-case ``#RRGGBB`` colour or raise a coded error."""
    if not isinstance(color, str):
        raise PlotSettingsError(
            f"Colour must be a '#RRGGBB' string; got {type(color).__name__}.",
            code="plot_color",
            context={"color": color},
        )
    text = color.strip()
    if not _HEX_COLOR.match(text):
        raise PlotSettingsError(
            f"Colour must use the '#RRGGBB' format; got {color!r}.",
            code="plot_color",
            context={"color": color},
        )
    return text.lower()


def _validate_positive(value: Any, *, code: str, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlotSettingsError(
            f"{name} must be a positive number.", code=code, context={name: value}
        )
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise PlotSettingsError(
            f"{name} must be a finite positive number.",
            code=code,
            context={name: value},
        )
    return number


def _validate_range(
    value: tuple[float, float] | None, *, axis: str
) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise PlotSettingsError(
            f"The {axis} range must contain exactly two numbers.",
            code="plot_axis_range",
            context={"axis": axis, "value": value},
        )
    low, high = value
    for number in (low, high):
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise PlotSettingsError(
                f"The {axis} range must contain numbers.",
                code="plot_axis_range",
                context={"axis": axis, "value": value},
            )
        if not math.isfinite(float(number)):
            raise PlotSettingsError(
                f"The {axis} range must be finite.",
                code="plot_axis_range",
                context={"axis": axis, "value": value},
            )
    if float(low) >= float(high):
        raise PlotSettingsError(
            f"The {axis} range minimum must be below its maximum.",
            code="plot_axis_range",
            context={"axis": axis, "value": value},
        )
    return (float(low), float(high))


@dataclass
class CurveStyle:
    """Display settings for one curve; data are supplied separately."""

    key: str
    visible: bool = True
    display_name: str | None = None
    color: str = "#1f4e79"
    linewidth: float = 1.0
    linestyle: str = "-"

    def __post_init__(self) -> None:
        if self.key not in CURVE_KEYS:
            raise PlotSettingsError(
                f"Unknown curve key: {self.key}",
                code="plot_unknown_curve",
                context={"key": self.key},
            )
        self.visible = bool(self.visible)
        if self.display_name is not None and not isinstance(
            self.display_name, str
        ):
            raise PlotSettingsError(
                "The curve display name must be text or None.",
                code="plot_display_name",
                context={"key": self.key},
            )
        self.color = normalize_color(self.color)
        self.linewidth = _validate_positive(
            self.linewidth, code="plot_linewidth", name="linewidth"
        )
        if self.linestyle not in LINE_STYLES:
            raise PlotSettingsError(
                f"Unsupported line style: {self.linestyle!r}",
                code="plot_linestyle",
                context={"linestyle": self.linestyle},
            )


@dataclass
class AxisSettings:
    """Titles, labels, ranges, legend and font sizes."""

    title: str | None = None
    xlabel: str | None = None
    ylabel: str | None = None
    xlim: tuple[float, float] | None = None
    ylim: tuple[float, float] | None = None
    legend_visible: bool = True
    legend_location: str = "best"
    title_fontsize: float = DEFAULT_TITLE_FONTSIZE
    axis_fontsize: float = DEFAULT_AXIS_FONTSIZE
    tick_fontsize: float = DEFAULT_TICK_FONTSIZE
    legend_fontsize: float = DEFAULT_LEGEND_FONTSIZE

    def __post_init__(self) -> None:
        for name in ("title", "xlabel", "ylabel"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise PlotSettingsError(
                    f"{name} must be text or None.",
                    code="plot_axis_label",
                    context={"name": name},
                )
        self.xlim = _validate_range(self.xlim, axis="x")
        self.ylim = _validate_range(self.ylim, axis="y")
        self.legend_visible = bool(self.legend_visible)
        if self.legend_location not in LEGEND_LOCATIONS:
            raise PlotSettingsError(
                f"Unsupported legend location: {self.legend_location!r}",
                code="plot_legend_location",
                context={"location": self.legend_location},
            )
        self.title_fontsize = _validate_positive(
            self.title_fontsize, code="plot_fontsize", name="title_fontsize"
        )
        self.axis_fontsize = _validate_positive(
            self.axis_fontsize, code="plot_fontsize", name="axis_fontsize"
        )
        self.tick_fontsize = _validate_positive(
            self.tick_fontsize, code="plot_fontsize", name="tick_fontsize"
        )
        self.legend_fontsize = _validate_positive(
            self.legend_fontsize, code="plot_fontsize", name="legend_fontsize"
        )


@dataclass
class PlotSettings:
    """All display settings for one sample."""

    curves: dict[str, CurveStyle] = field(default_factory=dict)
    axis: AxisSettings = field(default_factory=AxisSettings)

    def copy(self) -> PlotSettings:
        return PlotSettings(
            curves={key: replace(style) for key, style in self.curves.items()},
            axis=replace(self.axis),
        )

    def curve(self, key: str) -> CurveStyle | None:
        return self.curves.get(key)

    @property
    def visible_keys(self) -> tuple[str, ...]:
        return tuple(
            key for key in CURVE_KEYS if key in self.curves and self.curves[key].visible
        )


def last_baseline_fit(result: PreprocessingResult | None):
    """Return the most recent recorded baseline fit, or ``None``.

    Evaluating this line is not a refit. It only redraws the parameters that
    were stored when the user applied the baseline step.
    """
    if result is None:
        return None
    for step in reversed(result.steps):
        if step.operation == BASELINE_OPERATION and step.fit is not None:
            return step.fit
    return None


def has_processing(result: PreprocessingResult | None) -> bool:
    return bool(result is not None and result.has_steps)


def available_curve_keys(result: PreprocessingResult | None) -> tuple[str, ...]:
    """Return only the curves that the current result can actually provide."""
    keys = [CURVE_RAW]
    if has_processing(result):
        keys.extend((CURVE_PROCESSED, CURVE_DIFFERENCE))
        if last_baseline_fit(result) is not None:
            keys.append(CURVE_FITTED_BASELINE)
    return tuple(keys)


def default_curve_label_key(key: str, result: PreprocessingResult | None) -> str:
    """Return the i18n key for a curve's default display name."""
    operations = set(result.operations) if result is not None else set()
    if key == CURVE_RAW:
        return "plot_legend_raw"
    if key == CURVE_PROCESSED:
        if operations == {SAVGOL_OPERATION}:
            return "plot_legend_smoothed"
        if operations == {BASELINE_OPERATION}:
            return "plot_legend_corrected"
        return "plot_legend_processed"
    if key == CURVE_DIFFERENCE:
        if SAVGOL_OPERATION in operations:
            return "plot_legend_difference"
        return "plot_legend_removed"
    if key == CURVE_FITTED_BASELINE:
        return "plot_legend_fitted_baseline"
    return key


def default_ylabel_key(result: PreprocessingResult | None) -> str:
    operations = set(result.operations) if result is not None else set()
    if not operations:
        return "plot_ylabel"
    if operations == {SAVGOL_OPERATION}:
        return "plot_ylabel_smoothed"
    if operations == {BASELINE_OPERATION}:
        return "plot_ylabel_corrected"
    return "plot_ylabel_processed"


def default_title_key(result: PreprocessingResult | None) -> str:
    operations = set(result.operations) if result is not None else set()
    if not operations:
        return "plot_title"
    if result is not None and result.is_preview:
        if operations == {SAVGOL_OPERATION}:
            return "plot_title_savgol_preview"
        if operations == {BASELINE_OPERATION}:
            return "plot_title_preview"
        return "plot_title_processed_preview"
    if operations == {SAVGOL_OPERATION}:
        return "plot_title_smoothed"
    if operations == {BASELINE_OPERATION}:
        return "plot_title_corrected"
    return "plot_title_processed"


def default_settings(result: PreprocessingResult | None) -> PlotSettings:
    """Defaults that reproduce the pre-editor plot appearance."""
    processed = has_processing(result)
    if processed:
        raw_style = CurveStyle(CURVE_RAW, True, None, "#8c8c8c", 0.8, "--")
    else:
        raw_style = CurveStyle(CURVE_RAW, True, None, "#1f4e79", 1.0, "-")

    curves: dict[str, CurveStyle] = {CURVE_RAW: raw_style}
    if processed:
        curves[CURVE_PROCESSED] = CurveStyle(
            CURVE_PROCESSED, True, None, "#1f4e79", 1.0, "-"
        )
        curves[CURVE_DIFFERENCE] = CurveStyle(
            CURVE_DIFFERENCE, True, None, "#c55a11", 0.8, ":"
        )
        if last_baseline_fit(result) is not None:
            curves[CURVE_FITTED_BASELINE] = CurveStyle(
                CURVE_FITTED_BASELINE, False, None, "#c55a11", 0.8, "-."
            )

    return PlotSettings(
        curves=curves,
        axis=AxisSettings(
            title=None,
            xlabel=None,
            ylabel=None,
            xlim=None,
            ylim=None,
            legend_visible=processed,
            legend_location="best",
            title_fontsize=DEFAULT_TITLE_FONTSIZE,
            axis_fontsize=DEFAULT_AXIS_FONTSIZE,
            tick_fontsize=DEFAULT_TICK_FONTSIZE,
            legend_fontsize=DEFAULT_LEGEND_FONTSIZE,
        ),
    )


def reconcile_settings(
    settings: PlotSettings, defaults: PlotSettings
) -> PlotSettings:
    """Keep valid customisations while adding/removing curves by availability.

    The axis settings always survive. Curves that still exist keep their
    visibility, label override, colour, width and style. Curves that no longer
    exist are dropped; newly available curves receive their defaults.
    """
    curves: dict[str, CurveStyle] = {}
    for key, default_style in defaults.curves.items():
        existing = settings.curves.get(key)
        curves[key] = replace(existing) if existing is not None else replace(
            default_style
        )
    return PlotSettings(curves=curves, axis=replace(settings.axis))


def restore_default_visibility(
    settings: PlotSettings, defaults: PlotSettings
) -> PlotSettings:
    """Reset only visibility flags, leaving names/colours/axes untouched."""
    curves = {key: replace(style) for key, style in settings.curves.items()}
    for key, style in curves.items():
        default_style = defaults.curves.get(key)
        style.visible = bool(default_style.visible) if default_style else False
    return PlotSettings(curves=curves, axis=replace(settings.axis))


def validate_plot_settings(
    settings: PlotSettings,
    available_keys: Iterable[str],
    *,
    require_visible: bool = False,
) -> None:
    """Validate settings against the curves the current result can provide."""
    available = tuple(available_keys)
    for key in settings.curves:
        if key not in available:
            raise PlotSettingsError(
                f"Curve {key!r} is not available for this sample.",
                code="plot_unavailable_curve",
                context={"key": key},
            )
    for key in available:
        if key not in settings.curves:
            raise PlotSettingsError(
                f"Missing settings for available curve {key!r}.",
                code="plot_missing_curve",
                context={"key": key},
            )
    if require_visible and not any(
        style.visible for style in settings.curves.values()
    ):
        raise PlotSettingsError(
            "At least one curve must be visible to export a plot.",
            code="plot_no_visible_curve",
        )


def curve_arrays(
    field: np.ndarray,
    raw_intensity: np.ndarray,
    result: PreprocessingResult | None,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Return arrays for every curve available for *result*.

    No algorithm is called. The fitted-baseline line is evaluated from the
    slope/intercept already stored in the processing step.
    """
    x = np.asarray(field)
    arrays: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    if has_processing(result):
        assert result is not None
        arrays[CURVE_RAW] = (result.field_G, result.intensity_raw)
        arrays[CURVE_PROCESSED] = (result.field_G, result.intensity_processed)
        arrays[CURVE_DIFFERENCE] = (result.field_G, result.difference)
        fit = last_baseline_fit(result)
        if fit is not None:
            baseline = fit.slope * result.field_G + fit.intercept
            arrays[CURVE_FITTED_BASELINE] = (result.field_G, baseline)
    else:
        arrays[CURVE_RAW] = (x, np.asarray(raw_intensity))
    return arrays


@dataclass(frozen=True)
class CurveData:
    """One curve ready to draw, with its resolved label and style."""

    key: str
    x: np.ndarray
    y: np.ndarray
    label: str
    style: CurveStyle


def build_curves(
    field: np.ndarray,
    raw_intensity: np.ndarray,
    result: PreprocessingResult | None,
    settings: PlotSettings,
    labels: Mapping[str, str],
) -> list[CurveData]:
    """Combine arrays and styles in a stable drawing order."""
    arrays = curve_arrays(field, raw_intensity, result)
    curves: list[CurveData] = []
    for key in CURVE_RENDER_ORDER:
        if key not in arrays or key not in settings.curves:
            continue
        style = settings.curves[key]
        if style.display_name is None:
            label = labels.get(key, key)
        else:
            label = style.display_name
        curves.append(
            CurveData(
                key=key,
                x=arrays[key][0],
                y=arrays[key][1],
                label=label,
                style=style,
            )
        )
    return curves


def curve_data_ranges(
    curves: Iterable[CurveData], *, visible_only: bool = True
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return x/y ranges for manual-range defaults; never clips any data."""
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    for curve in curves:
        if visible_only and not curve.style.visible:
            continue
        if curve.x.size:
            xs.append(curve.x)
            ys.append(curve.y)
    if not xs:
        return (0.0, 1.0), (0.0, 1.0)
    x_all = np.concatenate(xs)
    y_all = np.concatenate(ys)
    x_low, x_high = float(np.min(x_all)), float(np.max(x_all))
    y_low, y_high = float(np.min(y_all)), float(np.max(y_all))
    if x_low == x_high:
        x_high = x_low + 1.0
    if y_low == y_high:
        y_high = y_low + 1.0
    return (x_low, x_high), (y_low, y_high)


def _contains_cjk(text: str) -> bool:
    return any("㐀" <= char <= "鿿" for char in text)


def draw_spectrum(
    axes,
    curves: Iterable[CurveData],
    settings: PlotSettings,
    *,
    cjk_font: str | None = None,
) -> list[Any]:
    """Draw *curves* into *axes* using *settings*.

    This is the single rendering path shared by the live canvas and the PNG
    exporter. It clears the axes but never touches the underlying arrays.
    """
    axes.clear()
    plotted = []
    for curve in curves:
        if not curve.style.visible:
            continue
        plotted.append(
            axes.plot(
                curve.x,
                curve.y,
                color=curve.style.color,
                linewidth=curve.style.linewidth,
                linestyle=curve.style.linestyle,
                label=curve.label,
            )[0]
        )

    axis = settings.axis
    title = "" if axis.title is None else axis.title
    xlabel = "" if axis.xlabel is None else axis.xlabel
    ylabel = "" if axis.ylabel is None else axis.ylabel
    axes.set_title(title, fontsize=axis.title_fontsize)
    axes.set_xlabel(xlabel, fontsize=axis.axis_fontsize)
    axes.set_ylabel(ylabel, fontsize=axis.axis_fontsize)
    axes.tick_params(axis="both", labelsize=axis.tick_fontsize)
    if axis.xlim is not None:
        axes.set_xlim(*axis.xlim)
    if axis.ylim is not None:
        axes.set_ylim(*axis.ylim)

    axes.grid(True, which="major", color="#b0b0b0", alpha=0.35, linewidth=0.6)

    legend_texts = []
    if axis.legend_visible and plotted:
        legend = axes.legend(
            loc=axis.legend_location,
            fontsize=axis.legend_fontsize,
            frameon=False,
        )
        legend_texts = list(legend.get_texts())

    if cjk_font:
        for artist in (
            axes.title,
            axes.xaxis.label,
            axes.yaxis.label,
            *legend_texts,
        ):
            if _contains_cjk(artist.get_text()):
                artist.set_fontfamily(cjk_font)

    axes.figure.tight_layout()
    return plotted


class PlotSettingsStore:
    """Per-sample plot settings kept in memory for the current app session.

    Settings are keyed by resolved source path. If the source SHA-256 changes,
    the stored settings are discarded so old styling is not silently reused
    for different data.
    """

    def __init__(self) -> None:
        self._entries: dict[Path, tuple[str, PlotSettings]] = {}

    def settings_for(
        self,
        source: str | Path,
        source_sha256: str,
        result: PreprocessingResult | None,
    ) -> PlotSettings:
        key = Path(source).resolve()
        defaults = default_settings(result)
        entry = self._entries.get(key)
        if entry is None or entry[0] != source_sha256:
            settings = defaults.copy()
        else:
            settings = reconcile_settings(entry[1], defaults)
        self._entries[key] = (source_sha256, settings.copy())
        return settings

    def update(
        self, source: str | Path, source_sha256: str, settings: PlotSettings
    ) -> None:
        self._entries[Path(source).resolve()] = (source_sha256, settings.copy())

    def discard(self, source: str | Path) -> None:
        self._entries.pop(Path(source).resolve(), None)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
