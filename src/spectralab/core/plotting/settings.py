"""Technique-independent plotting configuration."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from spectralab.core.errors import PlottingError

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


def _positive_number(value: Any, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlottingError(
            f"{field_name} must be a positive number.",
            code="plot_line_style",
            context={"field": field_name, "value": value},
        )
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise PlottingError(
            f"{field_name} must be finite and greater than zero.",
            code="plot_line_style",
            context={"field": field_name, "value": value},
        )
    return number


def _color(value: Any) -> str:
    if not isinstance(value, str) or not _HEX_COLOR.match(value.strip()):
        raise PlottingError(
            "Line colour must use the '#RRGGBB' format.",
            code="plot_line_style",
            context={"color": value},
        )
    return value.strip().lower()


def _limit_range(
    value: tuple[float, float] | None,
    *,
    axis: str,
) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise PlottingError(
            f"{axis} limits must contain exactly two numbers.",
            code="plot_limits",
            context={"axis": axis, "value": value},
        )
    low, high = value
    for number in (low, high):
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise PlottingError(
                f"{axis} limits must contain numbers.",
                code="plot_limits",
                context={"axis": axis, "value": value},
            )
        if not math.isfinite(float(number)):
            raise PlottingError(
                f"{axis} limits must be finite.",
                code="plot_limits",
                context={"axis": axis, "value": value},
            )
    if float(low) >= float(high):
        raise PlottingError(
            f"{axis} lower limit must be below its upper limit.",
            code="plot_limits",
            context={"axis": axis, "value": value},
        )
    return (float(low), float(high))


def _label(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlottingError(
            f"{field_name} must be non-empty text.",
            code="plot_config",
            context={"field": field_name},
        )
    if value != value.strip():
        raise PlottingError(
            f"{field_name} must not have surrounding whitespace.",
            code="plot_config",
            context={"field": field_name},
        )
    return value


def _optional_label(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PlottingError(
            f"{field_name} must be text or None.",
            code="plot_config",
            context={"field": field_name},
        )
    return value


@dataclass(frozen=True)
class LineStyle:
    """Generic colour, width and dash style for one series kind."""

    color: str = "#1f4e79"
    linewidth: float = 1.0
    linestyle: str = "-"

    def __post_init__(self) -> None:
        object.__setattr__(self, "color", _color(self.color))
        object.__setattr__(
            self,
            "linewidth",
            _positive_number(self.linewidth, field_name="linewidth"),
        )
        if self.linestyle not in LINE_STYLES:
            raise PlottingError(
                f"Unsupported line style: {self.linestyle!r}",
                code="plot_line_style",
                context={"linestyle": self.linestyle},
            )


@dataclass(frozen=True)
class PlotConfig:
    """Display configuration for one or two generic 1D series.

    ``title``, ``xlabel`` and ``ylabel`` use ``None`` to mean "derive from
    metadata". An explicit string, including ``""``, overrides metadata.
    Unknown metadata never gets a fabricated label.
    """

    title: str | None = None
    xlabel: str | None = None
    ylabel: str | None = None
    xlim: tuple[float, float] | None = None
    ylim: tuple[float, float] | None = None
    grid_visible: bool = True
    legend_visible: bool = True
    legend_location: str = "best"
    raw_label: str = "Raw"
    processed_label: str = "Processed"
    raw_style: LineStyle = field(
        default_factory=lambda: LineStyle("#7f7f7f", 0.8, "--")
    )
    processed_style: LineStyle = field(
        default_factory=lambda: LineStyle("#1f4e79", 1.0, "-")
    )

    def __post_init__(self) -> None:
        for name in ("title", "xlabel", "ylabel"):
            object.__setattr__(
                self,
                name,
                _optional_label(getattr(self, name), field_name=name),
            )
        object.__setattr__(self, "raw_label", _label(self.raw_label, field_name="raw_label"))
        object.__setattr__(
            self,
            "processed_label",
            _label(self.processed_label, field_name="processed_label"),
        )
        object.__setattr__(self, "xlim", _limit_range(self.xlim, axis="x"))
        object.__setattr__(self, "ylim", _limit_range(self.ylim, axis="y"))
        for name in ("grid_visible", "legend_visible"):
            if not isinstance(getattr(self, name), bool):
                raise PlottingError(
                    f"{name} must be a boolean.",
                    code="plot_config",
                    context={"field": name},
                )
        if self.legend_location not in LEGEND_LOCATIONS:
            raise PlottingError(
                f"Unsupported legend location: {self.legend_location!r}",
                code="plot_legend",
                context={"location": self.legend_location},
            )
        if not isinstance(self.raw_style, LineStyle):
            raise PlottingError(
                "raw_style must be a LineStyle.",
                code="plot_line_style",
                context={"type": type(self.raw_style).__name__},
            )
        if not isinstance(self.processed_style, LineStyle):
            raise PlottingError(
                "processed_style must be a LineStyle.",
                code="plot_line_style",
                context={"type": type(self.processed_style).__name__},
            )

    def label_for(self, kind: str) -> str:
        if kind == "raw":
            return self.raw_label
        if kind == "processed":
            return self.processed_label
        raise PlottingError(
            f"Unknown series kind: {kind!r}",
            code="plot_series_kind",
            context={"kind": kind},
        )

    def style_for(self, kind: str) -> LineStyle:
        if kind == "raw":
            return self.raw_style
        if kind == "processed":
            return self.processed_style
        raise PlottingError(
            f"Unknown series kind: {kind!r}",
            code="plot_series_kind",
            context={"kind": kind},
        )


__all__ = [
    "LEGEND_LOCATIONS",
    "LINE_STYLES",
    "LineStyle",
    "PlotConfig",
]
