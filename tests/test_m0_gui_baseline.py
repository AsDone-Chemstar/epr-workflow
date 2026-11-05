"""M0 GUI/workflow baseline: loading a file must not process it."""

from __future__ import annotations

import hashlib
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from epr_workflow.gui.main_window import MainWindow  # noqa: E402
from epr_workflow.plot_settings import CURVE_RAW  # noqa: E402

HEADER = "     index           Field [G]        Intensity []\n\n"


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_asc(tmp_path):
    source = tmp_path / "sample.ASC"
    rows = [
        f"{i + 1} {3300 + i * 0.5} {100 + i}"
        for i in range(5)
    ]
    source.write_text(
        HEADER + "\n".join(rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return [source]


def _write_bes3t(tmp_path):
    dsc = tmp_path / "sample.DSC"
    dta = tmp_path / "sample.DTA"
    lines = [
        "#DESC 1.2",
        "DSRC EXP",
        "BSEQ BIG",
        "IKKF REAL",
        "XTYP IDX",
        "YTYP NODATA",
        "ZTYP NODATA",
        "IRFMT D",
        "XPTS 5",
        "XMIN 3300.0",
        "XWID 2.0",
        "XNAM 'Field'",
        "XUNI 'G'",
        "IRNAM 'Intensity'",
        "IRUNI ''",
        "#SPL 1.2",
        "EXPT CW",
    ]
    dsc.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    dta.write_bytes(
        np.asarray([1.5, -2.0, 3.25, 0.125, 9.0], dtype=">f8").tobytes()
    )
    return [dsc, dta]


@pytest.mark.parametrize("kind", ["asc", "bes3t"])
def test_gui_load_does_not_apply_any_processing(
    app: QApplication, tmp_path, kind: str
) -> None:
    paths = _write_asc(tmp_path) if kind == "asc" else _write_bes3t(tmp_path)
    source = paths[0]
    before = {str(path): _sha256(path) for path in paths}
    window = MainWindow()

    window._load_and_display(source)

    assert window._current_view is not None
    assert window._current_view.source_format == (
        "ASC" if kind == "asc" else "BES3T"
    )
    assert window._preview_result is None
    assert window._session is not None
    assert window._session.steps == ()
    assert window._session.has_steps is False
    assert window._active_result() is None
    assert len(window.canvas.axes.lines) == 1
    assert window.plot_editor_panel.curve_keys() == (CURVE_RAW,)
    assert {str(path): _sha256(path) for path in paths} == before
