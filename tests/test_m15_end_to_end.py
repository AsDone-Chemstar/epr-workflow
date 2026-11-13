"""M15 end-to-end test: import, process, peak, difference, export."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from spectralab.app.gui.app import build_controller  # noqa: E402
from spectralab.app.gui.ftir_translations import FTIR_TECHNIQUE_ID  # noqa: E402
from spectralab.app.gui.i18n import Translator  # noqa: E402
from spectralab.app.gui.main_window import MainWindow  # noqa: E402
from spectralab.app.gui.settings import SettingsService  # noqa: E402
from spectralab.techniques.ftir import ColumnMapping, FTIRImportOptions  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_full_ftir_workflow_exports_all_artifacts_without_mutation(
    app: QApplication, tmp_path: Path
) -> None:
    a_path = _write(
        tmp_path / "a.csv",
        "0,10\n1,20\n2,30\n3,40\n4,50\n",
    )
    b_path = _write(
        tmp_path / "b.csv",
        "0,1\n1,2\n2,3\n3,4\n4,5\n",
    )
    before = {_sha256(a_path), _sha256(b_path)}

    window = MainWindow(
        build_controller(),
        Translator("zh"),
        SettingsService(None),
    )
    index = window.technique_combo.findData(FTIR_TECHNIQUE_ID)
    window.technique_combo.setCurrentIndex(index)
    panel = window._panels[FTIR_TECHNIQUE_ID]
    options = FTIRImportOptions(
        mapping=ColumnMapping(
            x=0,
            y=1,
            x_unit="cm^-1",
            y_semantics="absorbance",
        ),
        acquisition_mode="ATR",
        atr_correction_status="not_applied",
    )
    assert panel.import_file(a_path, options) is True
    assert panel.import_file(b_path, options) is True

    panel.dataset_combo.setCurrentIndex(0)
    panel.operation_combo.setCurrentIndex(
        panel.operation_combo.findData("normalization")
    )
    panel._preview()
    panel._apply()
    processed = panel.processing_session.current

    panel.peak_source_combo.setCurrentIndex(
        panel.peak_source_combo.findData("processed")
    )
    panel._preview_peaks()
    panel._apply_peaks()
    peak_result = panel.peak_applied_result
    assert peak_result is not None

    panel.difference_source_a_combo.setCurrentIndex(
        panel.difference_source_a_combo.findData("processed")
    )
    panel._preview_difference()
    panel._apply_difference()
    difference_result = panel.difference_applied_result
    assert difference_result is not None

    out = tmp_path / "out"
    raw_paths = panel.export_current_spectrum(
        out / "spectrum.csv",
        export_format="csv",
        source="raw",
    )
    processed_path = panel.export_current_spectrum(
        out / "processed.json",
        export_format="json",
        source="processed",
    )[0]
    difference_csv = panel.export_saved_difference(
        out / "difference.csv",
        export_format="csv",
    )
    difference_json = panel.export_saved_difference(
        out / "difference.json",
        export_format="json",
    )[0]
    difference_png = panel.export_saved_difference(
        out / "difference.png",
        export_format="png",
    )[0]

    assert all(path.exists() for path in raw_paths)
    assert processed_path.exists()
    assert all(path.exists() for path in difference_csv)
    assert difference_json.exists()
    assert difference_png.exists()
    assert difference_png.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    processed_document = json.loads(processed_path.read_text(encoding="utf-8"))
    assert processed_document["export"]["source_selection"] == "processed"
    assert processed_document["processing"]["operation_ids"] == [
        "ftir.normalize.min_max"
    ]
    assert processed_document["peak_detection"]["parameters"]["polarity"] == (
        "positive"
    )
    assert processed_document["peak_detection"]["dataset_id"] == "a"

    difference_document = json.loads(
        difference_json.read_text(encoding="utf-8")
    )
    assert difference_document["export"]["result_role"] == "applied"
    assert difference_document["sources"]["a"]["selection"] == "processed"
    assert difference_document["sources"]["a"]["operation_ids"] == [
        "ftir.normalize.min_max"
    ]
    assert difference_document["sources"]["a"]["processing_history"][0][
        "operation_id"
    ] == "ftir.normalize.min_max"
    assert difference_document["sources"]["b"]["selection"] == "raw"
    assert difference_document["difference"]["analysis"]["dataset_a_id"] == "a"
    assert difference_document["difference"]["analysis"]["dataset_b_id"] == "b"
    assert difference_document["difference"]["difference_values"] == (
        difference_result.signal.values.tolist()
    )

    # No source or in-memory analysis state changed.
    assert {_sha256(a_path), _sha256(b_path)} == before
    assert panel.processing_session.history[0].operation_id == (
        "ftir.normalize.min_max"
    )
    np.testing.assert_array_equal(
        panel.processing_session.current.signal.values,
        processed.signal.values,
    )
    assert panel.peak_applied_result is peak_result
    assert panel.difference_applied_result is difference_result
    window.close()
