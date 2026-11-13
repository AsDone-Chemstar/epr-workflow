"""M15 tests for FTIR spectrum and difference export."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib.image as mpimg
import numpy as np
import pytest

from spectralab.app.batch import run_batch, summary_path
from spectralab.app.ftir_export import (
    DIFFERENCE_CSV_COLUMNS,
    FTIR_DIFFERENCE_EXPORT_SCHEMA_ID,
    FTIR_EXPORT_SCHEMA_ID,
    build_ftir_difference_document,
    build_ftir_spectrum_document,
    export_ftir_difference_csv,
    export_ftir_difference_json,
    export_ftir_difference_png,
    export_ftir_spectrum_csv,
    export_ftir_spectrum_json,
    export_ftir_spectrum_png,
)
from spectralab.app.registry import build_importer_registry
from spectralab.core.errors import ExportPathError, OutputExistsError
from spectralab.core.processing import ProcessingSession
from spectralab.techniques.ftir import (
    ColumnMapping,
    DifferenceParameters,
    FTIRImportOptions,
    PeakDetectionParameters,
    compute_difference,
    create_normalization_operation,
    detect_peaks,
)

FIXED_TIME = "2026-11-05T12:00:00Z"


def _write_csv(path: Path, rows: list[tuple[float, float]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"{x},{y}" for x, y in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _options() -> FTIRImportOptions:
    return FTIRImportOptions(
        mapping=ColumnMapping(
            x=0,
            y=1,
            x_name="Wavenumber",
            x_unit="cm^-1",
            y_name="Absorbance",
            y_semantics="absorbance",
        ),
        acquisition_mode="ATR",
        atr_correction_status="not_applied",
        instrument_vendor="Vendor",
        instrument_model="Model",
    )


def _import(path: Path):
    dataset = build_importer_registry().read(
        path,
        technique="ftir",
        options={"ftir": _options()},
    )
    return dataset.primary


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _spectra(tmp_path: Path, *, b_rows=None):
    a = _write_csv(
        tmp_path / "a.csv",
        [(0.0, 10.0), (1.0, 20.0), (2.0, 30.0), (3.0, 40.0)],
    )
    b = _write_csv(
        tmp_path / "b.csv",
        b_rows or [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0), (3.0, 4.0)],
    )
    return a, b


def _processed(spectrum, method: str = "min_max"):
    session = ProcessingSession(spectrum)
    session.apply(create_normalization_operation(method))
    return session.current


def _difference(spectrum_a, spectrum_b, *, axis_match="exact"):
    return compute_difference(
        spectrum_a.axis,
        spectrum_a.raw_signal,
        spectrum_b.axis,
        spectrum_b.raw_signal,
        DifferenceParameters(axis_match=axis_match),
        dataset_a_id=spectrum_a.dataset_id,
        dataset_b_id=spectrum_b.dataset_id,
    )


# ---------------------------------------------------------------------------
# Single-spectrum export
# ---------------------------------------------------------------------------
def test_raw_csv_and_sidecar_preserve_data_and_provenance(
    tmp_path: Path,
) -> None:
    source = _write_csv(tmp_path / "raw.csv", [(0.0, 10.0), (1.0, 20.0)])
    spectrum = _import(source)
    before = _sha256(source)
    out = tmp_path / "out"

    outputs = export_ftir_spectrum_csv(
        spectrum,
        out / "raw.csv",
        exported_at=FIXED_TIME,
    )

    rows = _rows(outputs["csv"])
    assert [row["x"] for row in rows] == ["0.0", "1.0"]
    assert [row["y"] for row in rows] == ["10.0", "20.0"]
    document = _json(outputs["metadata"])
    assert document["schema_id"] == FTIR_EXPORT_SCHEMA_ID
    assert document["export"]["format"] == "csv_metadata"
    assert document["export"]["source_selection"] == "raw"
    assert document["export"]["exported_at_utc"] == FIXED_TIME
    assert document["export"]["processing_applied"] == []
    assert document["dataset"]["dataset_id"] == "raw"
    assert document["axis"]["unit"] == "cm^-1"
    assert document["signal"]["semantics"] == "absorbance"
    assert document["metadata"]["acquisition"]["mode"] == "ATR"
    assert document["metadata"]["acquisition"]["atr_correction_status"] == (
        "not_applied"
    )
    assert document["metadata"]["instrument"] == {
        "vendor": "Vendor",
        "model": "Model",
    }
    assert document["provenance"]["source_files"][0]["sha256"] == before
    assert document["provenance"]["canonical_sha256"] == before
    assert document["provenance"]["format_metadata"]["import_options"][
        "acquisition_mode"
    ] == "ATR"
    assert document["processing"]["history"] == []
    assert _sha256(source) == before


def test_processed_json_contains_values_and_full_history(
    tmp_path: Path,
) -> None:
    source = _write_csv(tmp_path / "proc.csv", [(0.0, 10.0), (1.0, 20.0)])
    spectrum = _import(source)
    processed = _processed(spectrum)
    before = _sha256(source)

    out = export_ftir_spectrum_json(
        processed,
        tmp_path / "processed.json",
        exported_at=FIXED_TIME,
    )
    document = _json(out)
    assert document["export"]["source_selection"] == "processed"
    np.testing.assert_allclose(document["axis"]["values"], processed.axis.values)
    np.testing.assert_allclose(
        document["signal"]["values"], processed.signal.values
    )
    assert document["processing"]["operation_ids"] == [
        "ftir.normalize.min_max"
    ]
    assert document["processing"]["history"][0]["operation_id"] == (
        "ftir.normalize.min_max"
    )
    assert document["processing"]["history"][0]["parameters"]["method"] == (
        "min_max"
    )
    assert document["export"]["processing_applied"] == [
        "ftir.normalize.min_max"
    ]
    assert document["provenance"]["source_files"][0]["sha256"] == before
    assert _sha256(source) == before


def test_processed_csv_uses_processed_values(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "proc.csv", [(0.0, 10.0), (1.0, 20.0)])
    spectrum = _import(source)
    processed = _processed(spectrum)
    outputs = export_ftir_spectrum_csv(
        processed,
        tmp_path / "processed.csv",
        exported_at=FIXED_TIME,
    )
    rows = _rows(outputs["csv"])
    np.testing.assert_allclose(
        [float(row["y"]) for row in rows],
        processed.signal.values,
    )
    assert _json(outputs["metadata"])["export"]["source_selection"] == (
        "processed"
    )


def test_peak_parameters_are_exported_and_must_match_dataset(
    tmp_path: Path,
) -> None:
    source = _write_csv(tmp_path / "peak.csv", [(0.0, 0.0), (1.0, 5.0), (2.0, 0.0)])
    other = _write_csv(tmp_path / "other.csv", [(0.0, 0.0), (1.0, 5.0), (2.0, 0.0)])
    spectrum = _import(source)
    other_spectrum = _import(other)
    peak = detect_peaks(
        spectrum.axis,
        spectrum.raw_signal,
        PeakDetectionParameters(polarity="positive"),
        dataset_id=spectrum.dataset_id,
    )

    document = build_ftir_spectrum_document(
        spectrum,
        include_values=False,
        peak_result=peak,
        exported_at=FIXED_TIME,
    )
    assert document["peak_detection"]["parameters"]["polarity"] == "positive"
    assert document["peak_detection"]["dataset_id"] == spectrum.dataset_id

    with pytest.raises(Exception) as excinfo:
        build_ftir_spectrum_document(
            other_spectrum,
            peak_result=peak,
        )
    assert getattr(excinfo.value, "code", "") == (
        "peak_result_dataset_mismatch"
    )


def test_single_png_exports_are_valid_images(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "png.csv", [(0.0, 10.0), (1.0, 20.0)])
    spectrum = _import(source)
    processed = _processed(spectrum)

    raw_png = export_ftir_spectrum_png(spectrum, tmp_path / "raw.png")
    processed_png = export_ftir_spectrum_png(
        processed,
        tmp_path / "processed.png",
    )

    for path in (raw_png, processed_png):
        assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        image = mpimg.imread(path)
        assert image.shape[0] > 100
        assert image.shape[1] > 100


def test_export_timestamp_and_software_versions(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "time.csv", [(0.0, 1.0), (1.0, 2.0)])
    spectrum = _import(source)
    out = export_ftir_spectrum_json(spectrum, tmp_path / "time.json")
    document = _json(out)
    timestamp = document["export"]["exported_at_utc"]
    assert timestamp.endswith("Z")
    assert len(timestamp) == len("2026-11-05T12:00:00Z")
    versions = document["export"]["software_versions"]
    assert set(versions) >= {
        "python",
        "numpy",
        "scipy",
        "matplotlib",
        "spectralab",
    }


# ---------------------------------------------------------------------------
# Difference export
# ---------------------------------------------------------------------------
def test_exact_difference_csv_and_json(tmp_path: Path) -> None:
    a, b = _spectra(tmp_path)
    spectrum_a = _import(a)
    spectrum_b = _import(b)
    result = _difference(spectrum_a, spectrum_b)

    outputs = export_ftir_difference_csv(
        result,
        tmp_path / "exact.csv",
        source_a=spectrum_a,
        source_b=spectrum_b,
        exported_at=FIXED_TIME,
    )
    rows = _rows(outputs["csv"])
    assert tuple(rows[0].keys()) == DIFFERENCE_CSV_COLUMNS
    assert [row["a"] for row in rows] == ["10.0", "20.0", "30.0", "40.0"]
    assert [row["b"] for row in rows] == ["1.0", "2.0", "3.0", "4.0"]
    assert [row["difference"] for row in rows] == [
        "9.0",
        "18.0",
        "27.0",
        "36.0",
    ]
    sidecar = _json(outputs["metadata"])
    assert sidecar["schema_id"] == FTIR_DIFFERENCE_EXPORT_SCHEMA_ID
    assert sidecar["export"]["axis_match"] == "exact"
    assert sidecar["sources"]["a"]["dataset_id"] == "a"
    assert sidecar["sources"]["b"]["dataset_id"] == "b"
    assert sidecar["sources"]["a"]["provenance"]["source_files"][0][
        "sha256"
    ] == _sha256(a)

    json_path = export_ftir_difference_json(
        result,
        tmp_path / "exact.json",
        source_a=spectrum_a,
        source_b=spectrum_b,
        exported_at=FIXED_TIME,
    )
    document = _json(json_path)
    assert document["difference"]["analysis"]["operation"] == "A - B"
    assert document["difference"]["a_values"] == [10.0, 20.0, 30.0, 40.0]
    assert document["difference"]["b_values"] == [1.0, 2.0, 3.0, 4.0]
    assert document["difference"]["difference_values"] == [
        9.0,
        18.0,
        27.0,
        36.0,
    ]
    assert document["sources"]["a"]["provenance"]["canonical_sha256"] == (
        _sha256(a)
    )
    assert document["sources"]["b"]["provenance"]["canonical_sha256"] == (
        _sha256(b)
    )


def test_interpolated_difference_csv_uses_aligned_b(tmp_path: Path) -> None:
    a, b = _spectra(
        tmp_path,
        b_rows=[
            (0.0, 1.0),
            (1.0, 2.0),
            (2.0, 3.0),
            (3.0, 4.0),
            (4.0, 5.0),
        ],
    )
    spectrum_a = _import(a)
    spectrum_b = _import(b)
    # A has x = 0,1,2,3; B has 0..4, so B is interpolated onto A.
    result = _difference(spectrum_a, spectrum_b, axis_match="interpolate")

    outputs = export_ftir_difference_csv(
        result,
        tmp_path / "interp.csv",
        source_a=spectrum_a,
        source_b=spectrum_b,
        exported_at=FIXED_TIME,
    )
    rows = _rows(outputs["csv"])
    assert [row["x"] for row in rows] == ["0.0", "1.0", "2.0", "3.0"]
    assert [row["b"] for row in rows] == ["1.0", "2.0", "3.0", "4.0"]
    sidecar = _json(outputs["metadata"])
    assert sidecar["export"]["axis_match"] == "interpolate"
    assert sidecar["interpolation"]["method"] == "linear"
    assert sidecar["interpolation"]["b_original_point_count"] == 5
    assert "linear interpolation" in sidecar["csv"]["b_column"]

    json_path = export_ftir_difference_json(
        result,
        tmp_path / "interp.json",
        source_a=spectrum_a,
        source_b=spectrum_b,
        exported_at=FIXED_TIME,
    )
    document = _json(json_path)
    assert document["interpolation"]["extrapolation"] == "none"
    assert document["interpolation"]["target_dataset_id"] == "a"
    assert document["interpolation"]["interpolated_dataset_id"] == "b"
    assert document["difference"]["b_values"] == [1.0, 2.0, 3.0, 4.0]


def test_difference_export_requires_matching_and_processed_sources(
    tmp_path: Path,
) -> None:
    a, b = _spectra(tmp_path)
    spectrum_a = _import(a)
    spectrum_b = _import(b)
    result = _difference(spectrum_a, spectrum_b)

    with pytest.raises(Exception) as excinfo:
        build_ftir_difference_document(
            result,
            source_a=spectrum_b,
            source_b=spectrum_a,
        )
    assert getattr(excinfo.value, "code", "") == "difference_source_mismatch"

    processed_a = _processed(spectrum_a)
    processed_result = compute_difference(
        processed_a.axis,
        processed_a.signal,
        spectrum_b.axis,
        spectrum_b.raw_signal,
        DifferenceParameters(source_a="processed"),
        dataset_a_id=spectrum_a.dataset_id,
        dataset_b_id=spectrum_b.dataset_id,
        source_operation_history_a=("ftir.normalize.min_max",),
    )
    with pytest.raises(Exception) as excinfo:
        build_ftir_difference_document(
            processed_result,
            source_a=spectrum_a,
            source_b=spectrum_b,
        )
    assert getattr(excinfo.value, "code", "") == "missing_processed_source"

    document = build_ftir_difference_document(
        processed_result,
        source_a=spectrum_a,
        source_b=spectrum_b,
        processed_a=processed_a,
        exported_at=FIXED_TIME,
    )
    assert document["sources"]["a"]["selection"] == "processed"
    assert document["sources"]["a"]["operation_ids"] == [
        "ftir.normalize.min_max"
    ]
    assert document["sources"]["a"]["processing_history"][0]["operation_id"] == (
        "ftir.normalize.min_max"
    )


def test_difference_processed_b_is_exported_and_plotted(
    tmp_path: Path,
) -> None:
    a, b = _spectra(tmp_path)
    spectrum_a = _import(a)
    spectrum_b = _import(b)
    processed_b = _processed(spectrum_b)
    result = compute_difference(
        spectrum_a.axis,
        spectrum_a.raw_signal,
        processed_b.axis,
        processed_b.signal,
        DifferenceParameters(source_b="processed"),
        dataset_a_id=spectrum_a.dataset_id,
        dataset_b_id=spectrum_b.dataset_id,
        source_operation_history_b=("ftir.normalize.min_max",),
    )
    document = build_ftir_difference_document(
        result,
        source_a=spectrum_a,
        source_b=spectrum_b,
        processed_b=processed_b,
        exported_at=FIXED_TIME,
    )
    assert document["sources"]["b"]["selection"] == "processed"
    assert document["sources"]["b"]["processing_history"][0]["operation_id"] == (
        "ftir.normalize.min_max"
    )

    path = export_ftir_difference_png(
        result,
        tmp_path / "processed_b.png",
        source_a=spectrum_a,
        source_b=spectrum_b,
        processed_b=processed_b,
    )
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_difference_png_is_valid_and_labels_are_preserved(
    tmp_path: Path,
) -> None:
    a, b = _spectra(tmp_path)
    spectrum_a = _import(a)
    spectrum_b = _import(b)
    result = _difference(spectrum_a, spectrum_b)

    path = export_ftir_difference_png(
        result,
        tmp_path / "difference.png",
        source_a=spectrum_a,
        source_b=spectrum_b,
        labels={
            "title": "测试差谱",
            "a": "A",
            "b": "B",
            "b_interpolated": "B interp",
            "difference": "A - B",
        },
    )
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    image = mpimg.imread(path)
    assert image.shape[0] > 100
    assert image.shape[1] > 100


# ---------------------------------------------------------------------------
# Path safety and source integrity
# ---------------------------------------------------------------------------
def test_overwrite_and_source_protection(tmp_path: Path) -> None:
    source = _write_csv(tmp_path / "safe.csv", [(0.0, 1.0), (1.0, 2.0)])
    spectrum = _import(source)
    target = tmp_path / "existing.json"
    target.write_text("sentinel\n", encoding="utf-8")

    with pytest.raises(OutputExistsError):
        export_ftir_spectrum_json(spectrum, target)
    assert target.read_text(encoding="utf-8") == "sentinel\n"

    export_ftir_spectrum_json(spectrum, target, overwrite=True)
    assert _json(target)["schema_id"] == FTIR_EXPORT_SCHEMA_ID

    with pytest.raises(ExportPathError):
        export_ftir_spectrum_json(spectrum, source)


def test_difference_overwrite_and_source_protection(tmp_path: Path) -> None:
    a, b = _spectra(tmp_path)
    spectrum_a = _import(a)
    spectrum_b = _import(b)
    result = _difference(spectrum_a, spectrum_b)
    target = tmp_path / "existing_difference.json"
    target.write_text("sentinel\n", encoding="utf-8")

    with pytest.raises(OutputExistsError):
        export_ftir_difference_json(
            result,
            target,
            source_a=spectrum_a,
            source_b=spectrum_b,
        )
    assert target.read_text(encoding="utf-8") == "sentinel\n"

    export_ftir_difference_json(
        result,
        target,
        source_a=spectrum_a,
        source_b=spectrum_b,
        overwrite=True,
    )
    assert _json(target)["schema_id"] == FTIR_DIFFERENCE_EXPORT_SCHEMA_ID

    with pytest.raises(ExportPathError):
        export_ftir_difference_json(
            result,
            a,
            source_a=spectrum_a,
            source_b=spectrum_b,
        )


def test_export_does_not_modify_sources_sessions_or_results(
    tmp_path: Path,
) -> None:
    a, b = _spectra(tmp_path)
    spectrum_a = _import(a)
    spectrum_b = _import(b)
    processed_a = _processed(spectrum_a)
    result = _difference(processed_a.source, spectrum_b)
    before = {
        "a": _sha256(a),
        "b": _sha256(b),
        "a_x": spectrum_a.axis.values.copy(),
        "a_y": spectrum_a.raw_signal.values.copy(),
        "b_x": spectrum_b.axis.values.copy(),
        "b_y": spectrum_b.raw_signal.values.copy(),
        "history": tuple(
            record.operation_id for record in processed_a.history
        ),
        "difference": result.signal.values.copy(),
    }

    export_ftir_spectrum_csv(spectrum_a, tmp_path / "out" / "a.csv")
    export_ftir_spectrum_json(processed_a, tmp_path / "out" / "a.json")
    export_ftir_spectrum_png(processed_a, tmp_path / "out" / "a.png")
    export_ftir_difference_csv(
        result,
        tmp_path / "out" / "d.csv",
        source_a=spectrum_a,
        source_b=spectrum_b,
    )
    export_ftir_difference_json(
        result,
        tmp_path / "out" / "d.json",
        source_a=spectrum_a,
        source_b=spectrum_b,
    )
    export_ftir_difference_png(
        result,
        tmp_path / "out" / "d.png",
        source_a=spectrum_a,
        source_b=spectrum_b,
    )

    assert _sha256(a) == before["a"]
    assert _sha256(b) == before["b"]
    np.testing.assert_array_equal(spectrum_a.axis.values, before["a_x"])
    np.testing.assert_array_equal(spectrum_a.raw_signal.values, before["a_y"])
    np.testing.assert_array_equal(spectrum_b.axis.values, before["b_x"])
    np.testing.assert_array_equal(spectrum_b.raw_signal.values, before["b_y"])
    assert tuple(
        record.operation_id for record in processed_a.history
    ) == before["history"]
    np.testing.assert_array_equal(result.signal.values, before["difference"])
    assert not processed_a.axis.values.flags.writeable
    assert not result.signal.values.flags.writeable


# ---------------------------------------------------------------------------
# Batch mapping
# ---------------------------------------------------------------------------
def test_batch_records_mapping_for_each_file(tmp_path: Path) -> None:
    first = _write_csv(tmp_path / "one.csv", [(0.0, 1.0), (1.0, 2.0)])
    second = _write_csv(tmp_path / "two.csv", [(0.0, 3.0), (1.0, 4.0)])
    out = tmp_path / "out"
    options = {"ftir": _options()}

    result = run_batch([first, second], out, options=options)
    assert result.exit_code == 0
    summary = json.loads(summary_path(out).read_text(encoding="utf-8"))
    assert len(summary["files"]) == 2
    for record in summary["files"]:
        assert record["status"] == "success"
        assert record["resolved_mapping"] == {"x": 0, "y": 1, "requested_x": 0, "requested_y": 1}
        assert record["parsing"]["delimiter"] == ","
        assert record["parsing"]["decimal_separator"] == "."
        assert record["parsing"]["encoding"] == "utf-8-sig"
        assert record["parsing"]["header"] is False
        assert record["parsing"]["skip_rows"] == 0
        assert record["import_options"]["mapping"]["x_unit"] == "cm^-1"
        assert record["import_options"]["mapping"]["y_semantics"] == (
            "absorbance"
        )
