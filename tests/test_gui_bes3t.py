"""Offscreen GUI tests for BES3T loading, metadata and error translation."""

from __future__ import annotations

import hashlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

import epr_workflow.gui.main_window as main_window_module  # noqa: E402
from epr_workflow.gui.controller import load_spectrum  # noqa: E402
from epr_workflow.gui.main_window import MainWindow  # noqa: E402
from epr_workflow.plot_export import PlotExportSettings  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def no_modal_dialogs(monkeypatch: pytest.MonkeyPatch) -> None:
    def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(
        main_window_module.QMessageBox, "warning", staticmethod(_noop)
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox, "critical", staticmethod(_noop)
    )


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_bes3t(tmp_path, values=(1.5, -2.0, 3.25, 0.125)):
    dsc = tmp_path / "native.DSC"
    dta = tmp_path / "native.DTA"
    lines = [
        "#DESC 1.2",
        "DSRC EXP",
        "BSEQ BIG",
        "IKKF REAL",
        "XTYP IDX",
        "YTYP NODATA",
        "ZTYP NODATA",
        "IRFMT D",
        "XPTS 4",
        "XMIN 3300.0",
        "XWID 3.0",
        "XNAM 'Field'",
        "XUNI 'G'",
        "IRNAM 'Intensity'",
        "IRUNI ''",
        "#SPL 1.2",
        "EXPT CW",
    ]
    dsc.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    dta.write_bytes(np.asarray(values, dtype=">f8").tobytes())
    return dsc, dta


def test_gui_loads_bes3t_and_reports_format(
    app: QApplication, tmp_path
) -> None:
    dsc, _dta = write_bes3t(tmp_path)
    before = sha256(dsc)
    window = MainWindow()

    window._load_and_display(dsc)

    assert window._current_view is not None
    assert window._current_view.source_format == "BES3T"
    assert window._current_view.n_points == 4
    assert len(window.canvas.axes.lines) == 1
    text = window.metadata_text.toPlainText()
    assert "格式：BES3T" in text
    assert "source.DSC" not in text
    assert "native.DSC" in text
    assert "native.DTA" in text
    assert "BES3T 轴：IDX" in text
    assert "BES3T 数据：REAL" in text
    assert sha256(dsc) == before


def test_gui_metadata_retranslates_bes3t(
    app: QApplication, tmp_path
) -> None:
    dsc, _dta = write_bes3t(tmp_path)
    window = MainWindow()
    window._load_and_display(dsc)

    window._set_language("en")

    text = window.metadata_text.toPlainText()
    assert "Format: BES3T" in text
    assert "Source files: native.DSC + native.DTA" in text
    assert "BES3T axis: IDX" in text
    assert "BES3T data: REAL" in text
    assert "BIG byte order" in text


def test_gui_reports_missing_dta_in_both_languages(
    app: QApplication, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dsc, dta = write_bes3t(tmp_path)
    dta.unlink()
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "warning",
        staticmethod(
            lambda parent, title, text, *a, **k: messages.append((title, text))
        ),
    )
    window = MainWindow()

    window._load_and_display(dsc)

    assert window.metadata_text.toPlainText().startswith("无法读取")
    assert "缺少" in window.metadata_text.toPlainText()
    assert messages and "缺少" in messages[-1][1]

    window._set_language("en")

    assert window.metadata_text.toPlainText().startswith("Could not read")
    assert "Missing .DTA companion" in window.metadata_text.toPlainText()


def test_gui_file_filter_accepts_dsc(
    app: QApplication, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dsc, _dta = write_bes3t(tmp_path)
    captured: dict[str, str] = {}

    def fake_dialog(parent, title, start, filters):
        captured["title"] = title
        captured["filters"] = filters
        return str(dsc), filters

    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        staticmethod(fake_dialog),
    )
    window = MainWindow()

    window._choose_single_file()

    assert ".dsc" in captured["filters"].lower()
    assert window._current_view is not None
    assert window._current_view.source_format == "BES3T"


def test_gui_plot_export_cannot_overwrite_dta(
    app: QApplication, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dsc, dta = write_bes3t(tmp_path)
    before = sha256(dta)
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "critical",
        staticmethod(
            lambda parent, title, text, *a, **k: messages.append((title, text))
        ),
    )
    window = MainWindow()
    window._load_and_display(dsc)

    result = window._export_plot_to(
        dta,
        PlotExportSettings(dpi=100),
        overwrite=True,
    )

    assert result is None
    assert sha256(dta) == before
    assert messages


def test_controller_view_exposes_source_hashes(tmp_path) -> None:
    dsc, dta = write_bes3t(tmp_path)
    view = load_spectrum(dsc)

    assert view.source_format == "BES3T"
    assert view.source_hashes["descriptor"] == sha256(dsc)
    assert view.source_hashes["data"] == sha256(dta)
    assert set(view.source_files) == {"descriptor", "data"}
