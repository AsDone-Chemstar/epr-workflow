"""Tests for PNG plot export (display output only)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import matplotlib.image as mpimg
import numpy as np
import pytest

import epr_workflow.plot_export as plot_export_module
from epr_workflow.plot_asc import PROJECT_ROOT
from epr_workflow.plot_export import (
    PlotExportSettings,
    default_plot_path,
    export_plot_png,
)
from epr_workflow.plot_settings import (
    CURVE_RAW,
    PlotSettingsError,
    build_curves,
    default_settings,
)


def make_curves(settings):
    return build_curves(
        np.array([1.0, 2.0, 3.0, 4.0]),
        np.array([0.0, 1.0, 0.0, -1.0]),
        None,
        settings,
        {CURVE_RAW: "Raw"},
    )


def make_source(tmp_path: Path) -> Path:
    source = tmp_path / "sample.ASC"
    source.write_text("dummy\n", encoding="utf-8")
    return source


def styled_settings():
    settings = default_settings(None)
    settings.axis.title = "My title"
    settings.axis.xlabel = "Field (G)"
    settings.axis.ylabel = "Signal"
    settings.axis.title_fontsize = 14.0
    settings.axis.axis_fontsize = 11.0
    settings.curves[CURVE_RAW].color = "#aa3300"
    settings.curves[CURVE_RAW].linewidth = 2.0
    settings.curves[CURVE_RAW].linestyle = "--"
    return settings


# --------------------------------------------------------------------------
# Basic export
# --------------------------------------------------------------------------
def test_export_writes_png_with_requested_size_and_dpi(
    tmp_path: Path,
) -> None:
    source = make_source(tmp_path)
    settings = styled_settings()
    target = tmp_path / "figures" / "sample_plot.png"

    result = export_plot_png(
        curves=make_curves(settings),
        settings=settings,
        available_keys=[CURVE_RAW],
        output_path=target,
        export_settings=PlotExportSettings(
            width_in=4.0,
            height_in=2.5,
            dpi=150,
        ),
        source_path=source,
    )

    assert result == target
    assert target.exists()
    image = mpimg.imread(target)
    assert image.shape[0] == 375
    assert image.shape[1] == 600


def test_export_default_options_are_used(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    settings = styled_settings()
    target = tmp_path / "sample_plot.png"

    export_plot_png(
        curves=make_curves(settings),
        settings=settings,
        available_keys=[CURVE_RAW],
        output_path=target,
        source_path=source,
    )

    image = mpimg.imread(target)
    assert image.shape[0] == 1500
    assert image.shape[1] == 2400


def test_export_can_omit_title_and_legend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_source(tmp_path)
    settings = styled_settings()
    captured: dict[str, object] = {}
    real_draw = plot_export_module.draw_spectrum

    def capture(axes, curves, render_settings, *, cjk_font=None):
        captured["title"] = render_settings.axis.title
        captured["legend"] = render_settings.axis.legend_visible
        captured["xlim"] = render_settings.axis.xlim
        return real_draw(axes, curves, render_settings, cjk_font=cjk_font)

    monkeypatch.setattr(plot_export_module, "draw_spectrum", capture)

    export_plot_png(
        curves=make_curves(settings),
        settings=settings,
        available_keys=[CURVE_RAW],
        output_path=tmp_path / "sample_plot.png",
        export_settings=PlotExportSettings(
            include_title=False,
            include_legend=False,
        ),
        source_path=source,
    )

    assert captured["title"] == ""
    assert captured["legend"] is False


def test_export_does_not_modify_source_or_write_other_files(
    tmp_path: Path,
) -> None:
    source = make_source(tmp_path)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    settings = styled_settings()
    target = tmp_path / "figures" / "sample_plot.png"

    export_plot_png(
        curves=make_curves(settings),
        settings=settings,
        available_keys=[CURVE_RAW],
        output_path=target,
        source_path=source,
    )

    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert [path.name for path in target.parent.iterdir()] == [target.name]


# --------------------------------------------------------------------------
# Overwrite and safety
# --------------------------------------------------------------------------
def test_existing_plot_is_not_overwritten_by_default(
    tmp_path: Path,
) -> None:
    source = make_source(tmp_path)
    settings = styled_settings()
    target = tmp_path / "sample_plot.png"
    target.write_bytes(b"keep me")
    before = target.read_bytes()

    with pytest.raises(FileExistsError):
        export_plot_png(
            curves=make_curves(settings),
            settings=settings,
            available_keys=[CURVE_RAW],
            output_path=target,
            source_path=source,
            overwrite=False,
        )

    assert target.read_bytes() == before


def test_overwrite_replaces_existing_plot(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    settings = styled_settings()
    target = tmp_path / "sample_plot.png"
    target.write_bytes(b"old")

    export_plot_png(
        curves=make_curves(settings),
        settings=settings,
        available_keys=[CURVE_RAW],
        output_path=target,
        source_path=source,
        overwrite=True,
    )

    assert target.read_bytes().startswith(b"\x89PNG")


def test_export_refuses_source_overwrite(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    before = source.read_bytes()
    settings = styled_settings()

    with pytest.raises(ValueError):
        export_plot_png(
            curves=make_curves(settings),
            settings=settings,
            available_keys=[CURVE_RAW],
            output_path=source,
            source_path=source,
            overwrite=True,
        )

    assert source.read_bytes() == before


def test_export_protects_companion_source_paths(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    companion = tmp_path / "sample.DTA"
    companion.write_bytes(b"companion bytes")
    before = companion.read_bytes()
    settings = styled_settings()

    with pytest.raises(ValueError):
        export_plot_png(
            curves=make_curves(settings),
            settings=settings,
            available_keys=[CURVE_RAW],
            output_path=companion,
            source_path=source,
            source_paths=[source, companion],
            overwrite=True,
        )

    assert companion.read_bytes() == before


def test_export_refuses_data_raw_directory() -> None:
    raw_target = PROJECT_ROOT / "data" / "raw" / "_pytest_plot_never.png"
    assert not raw_target.exists()
    source = PROJECT_ROOT / "data" / "raw" / "BSA3T275.ASC"
    settings = styled_settings()

    with pytest.raises(ValueError):
        export_plot_png(
            curves=make_curves(settings),
            settings=settings,
            available_keys=[CURVE_RAW],
            output_path=raw_target,
            source_path=source,
        )

    assert not raw_target.exists()


def test_failed_render_leaves_no_target_or_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = make_source(tmp_path)
    settings = styled_settings()
    target = tmp_path / "sample_plot.png"

    def _fail(*args, **kwargs):
        raise RuntimeError("render failed")

    monkeypatch.setattr(plot_export_module, "draw_spectrum", _fail)

    with pytest.raises(RuntimeError):
        export_plot_png(
            curves=make_curves(settings),
            settings=settings,
            available_keys=[CURVE_RAW],
            output_path=target,
            source_path=source,
        )

    assert not target.exists()
    assert list(tmp_path.iterdir()) == [source]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def test_no_visible_curve_is_rejected(tmp_path: Path) -> None:
    source = make_source(tmp_path)
    settings = styled_settings()
    settings.curves[CURVE_RAW].visible = False
    target = tmp_path / "sample_plot.png"

    with pytest.raises(PlotSettingsError) as exc:
        export_plot_png(
            curves=make_curves(settings),
            settings=settings,
            available_keys=[CURVE_RAW],
            output_path=target,
            source_path=source,
        )

    assert exc.value.code == "plot_no_visible_curve"
    assert not target.exists()


def test_invalid_export_size_and_dpi_are_rejected() -> None:
    with pytest.raises(PlotSettingsError) as size:
        PlotExportSettings(width_in=0.1)
    assert size.value.code == "plot_export_size"

    with pytest.raises(PlotSettingsError) as height:
        PlotExportSettings(height_in=float("inf"))
    assert height.value.code == "plot_export_size"

    with pytest.raises(PlotSettingsError) as dpi:
        PlotExportSettings(dpi=10)
    assert dpi.value.code == "plot_export_dpi"

    with pytest.raises(PlotSettingsError):
        PlotExportSettings(dpi=300.0)  # type: ignore[arg-type]


def test_default_plot_path_uses_plot_suffix() -> None:
    path = default_plot_path("sample", Path("out"))

    assert path == Path("out") / "figures" / "sample_plot.png"
    assert path.suffix == ".png"
