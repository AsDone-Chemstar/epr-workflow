"""Generic raw/processed series extraction without processing or reordering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from spectralab.core.errors import PlottingError
from spectralab.core.model import Axis1D, Signal1D, Spectrum1D
from spectralab.core.model.values import required_text
from spectralab.core.plotting.settings import PlotConfig
from spectralab.core.processing import ProcessedSpectrum

SeriesKind = Literal["raw", "processed"]
SERIES_KINDS = frozenset({"raw", "processed"})


def format_axis_label(axis: Axis1D) -> str:
    """Format only recorded axis name/unit; unknown values stay blank."""
    if axis.name and axis.unit:
        return f"{axis.name} ({axis.unit})"
    if axis.name:
        return axis.name
    if axis.unit:
        return axis.unit
    return ""


def format_signal_label(signal: Signal1D) -> str:
    """Format only recorded signal name/unit; unknown values stay blank."""
    if signal.name and signal.unit:
        return f"{signal.name} ({signal.unit})"
    if signal.name:
        return signal.name
    if signal.unit:
        return signal.unit
    return ""


@dataclass(frozen=True)
class Series1D:
    """One immutable X/Y view for plotting.

    The series holds references to already-immutable ``Axis1D``/``Signal1D``
    objects. It never copies, sorts, reverses, crops or processes their arrays.
    """

    kind: SeriesKind
    axis: Axis1D
    signal: Signal1D
    label: str
    dataset_id: str

    def __post_init__(self) -> None:
        if self.kind not in SERIES_KINDS:
            raise PlottingError(
                f"Unsupported series kind: {self.kind!r}",
                code="plot_series_kind",
                context={"kind": self.kind},
            )
        if not isinstance(self.axis, Axis1D):
            raise PlottingError(
                "Series1D.axis must be an Axis1D.",
                code="plot_series_data",
            )
        if not isinstance(self.signal, Signal1D):
            raise PlottingError(
                "Series1D.signal must be a Signal1D.",
                code="plot_series_data",
            )
        if self.axis.point_count != self.signal.point_count:
            raise PlottingError(
                "Series1D axis and signal lengths differ.",
                code="plot_series_data",
                context={
                    "axis": self.axis.point_count,
                    "signal": self.signal.point_count,
                },
            )
        label = required_text(
            self.label,
            field="series.label",
            error_cls=PlottingError,
        )
        dataset_id = required_text(
            self.dataset_id,
            field="series.dataset_id",
            error_cls=PlottingError,
        )
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "dataset_id", dataset_id)
        if not np.all(np.isfinite(self.axis.values)) or not np.all(
            np.isfinite(self.signal.values)
        ):
            raise PlottingError(
                "Series data contain non-finite values and cannot be plotted.",
                code="plot_nonfinite_data",
            )

    @property
    def x_values(self) -> np.ndarray:
        return self.axis.values

    @property
    def y_values(self) -> np.ndarray:
        return self.signal.values

    @property
    def x(self) -> np.ndarray:
        return self.axis.values

    @property
    def y(self) -> np.ndarray:
        return self.signal.values

    @property
    def point_count(self) -> int:
        return self.axis.point_count

    @property
    def is_raw(self) -> bool:
        return self.kind == "raw"


def series_from_spectrum(
    spectrum: Spectrum1D,
    *,
    label: str = "Raw",
) -> tuple[Series1D, ...]:
    """Return the single raw series for a ``Spectrum1D``."""
    if not isinstance(spectrum, Spectrum1D):
        raise PlottingError(
            "series_from_spectrum requires a Spectrum1D.",
            code="plot_unsupported_input",
            context={"type": type(spectrum).__name__},
        )
    return (
        Series1D(
            kind="raw",
            axis=spectrum.axis,
            signal=spectrum.raw_signal,
            label=label,
            dataset_id=spectrum.dataset_id,
        ),
    )


def series_from_processed(
    processed: ProcessedSpectrum,
    *,
    include_raw: bool = True,
    raw_label: str = "Raw",
    processed_label: str = "Processed",
) -> tuple[Series1D, ...]:
    """Return raw and/or processed series without replaying any operation."""
    if not isinstance(processed, ProcessedSpectrum):
        raise PlottingError(
            "series_from_processed requires a ProcessedSpectrum.",
            code="plot_unsupported_input",
            context={"type": type(processed).__name__},
        )
    if not isinstance(include_raw, bool):
        raise PlottingError(
            "include_raw must be a boolean.",
            code="plot_config",
            context={"field": "include_raw"},
        )

    series: list[Series1D] = []
    if include_raw:
        source = processed.source
        series.append(
            Series1D(
                kind="raw",
                axis=source.axis,
                signal=source.raw_signal,
                label=raw_label,
                dataset_id=source.dataset_id,
            )
        )
    series.append(
        Series1D(
            kind="processed",
            axis=processed.axis,
            signal=processed.signal,
            label=processed_label,
            dataset_id=processed.source.dataset_id,
        )
    )
    return tuple(series)


def build_series(
    source: Spectrum1D | ProcessedSpectrum,
    *,
    config: PlotConfig | None = None,
    include_raw: bool = True,
) -> tuple[Series1D, ...]:
    """Build plot series for either supported input type.

    For ``Spectrum1D`` the raw series is always returned; ``include_raw`` only
    controls whether a ``ProcessedSpectrum`` also includes its source raw
    series.
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
    if isinstance(source, Spectrum1D):
        return series_from_spectrum(source, label=options.raw_label)
    if isinstance(source, ProcessedSpectrum):
        return series_from_processed(
            source,
            include_raw=include_raw,
            raw_label=options.raw_label,
            processed_label=options.processed_label,
        )
    raise PlottingError(
        "Plotting supports Spectrum1D and ProcessedSpectrum only.",
        code="plot_unsupported_input",
        context={"type": type(source).__name__},
    )


__all__ = [
    "SERIES_KINDS",
    "Series1D",
    "SeriesKind",
    "build_series",
    "format_axis_label",
    "format_signal_label",
    "series_from_processed",
    "series_from_spectrum",
]
