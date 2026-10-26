"""Tests for exporting baseline-corrected spectra."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epr_workflow.plot_asc import PROJECT_ROOT, read_asc
from epr_workflow.preprocessing import (
    BaselineWindow,
    LinearBaselineSpec,
    PreprocessingError,
    PreprocessingSession,
    SavgolSpec,
)
from epr_workflow.processed_export import (
    PROCESSED_COLUMNS,
    SMOOTHED_COLUMNS,
    export_processed,
)

HEADER = "     index           Field [G]        Intensity []\n\n"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_asc(path: Path, n: int = 101) -> Path:
    rows = []
    for i in range(n):
        field = 3280.0 + i
        intensity = 2.0 * field + 5.0 + 500.0 * np.exp(-((field - 3330.0) / 5.0) ** 2)
        rows.append(f"{i + 1} {field!r} {float(intensity)!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    return path


def default_spec() -> LinearBaselineSpec:
    return LinearBaselineSpec(
        window_left=BaselineWindow(3280.0, 3284.0),
        window_right=BaselineWindow(3376.0, 3380.0),
    )


def prepared(tmp_path: Path):
    source = write_asc(tmp_path / "sample.ASC")
    imported = read_asc(source)
    session = PreprocessingSession(
        source=source,
        field_G=imported.data["field_G"].to_numpy(),
        intensity=imported.data["intensity"].to_numpy(),
        source_sha256=imported.sha256,
    )
    applied = session.apply(default_spec())
    return imported, session, applied


def prepared_smoothing(tmp_path: Path):
    source = write_asc(tmp_path / "sample.ASC")
    imported = read_asc(source)
    session = PreprocessingSession(
        source=source,
        field_G=imported.data["field_G"].to_numpy(),
        intensity=imported.data["intensity"].to_numpy(),
        source_sha256=imported.sha256,
    )
    applied = session.apply_savgol(SavgolSpec(9, 3))
    return imported, session, applied


def test_processed_export_writes_three_files(tmp_path: Path) -> None:
    imported, _, result = prepared(tmp_path)
    out = tmp_path / "out"

    outputs = export_processed(
        import_result=imported, result=result, output_base=out
    )

    assert outputs["csv"] == out / "tables" / "sample_baseline.csv"
    assert outputs["figure"] == out / "figures" / "sample_baseline.png"
    assert outputs["metadata_json"] == out / "logs" / "sample_baseline_metadata.json"
    for path in outputs.values():
        assert path.exists() and path.stat().st_size > 0


def test_processed_csv_columns_and_values(tmp_path: Path) -> None:
    imported, _, result = prepared(tmp_path)
    out = tmp_path / "out"
    outputs = export_processed(import_result=imported, result=result, output_base=out)

    frame = pd.read_csv(outputs["csv"])

    assert list(frame.columns) == PROCESSED_COLUMNS
    np.testing.assert_array_equal(
        frame["index"].to_numpy(), imported.data["index"].to_numpy()
    )
    np.testing.assert_array_equal(
        frame["field_G"].to_numpy(), imported.data["field_G"].to_numpy()
    )
    np.testing.assert_array_equal(
        frame["intensity_raw"].to_numpy(), imported.data["intensity"].to_numpy()
    )
    np.testing.assert_array_equal(
        frame["intensity_corrected"].to_numpy(), result.intensity_processed
    )
    np.testing.assert_array_equal(
        frame["baseline_removed"].to_numpy(), result.removed_baseline
    )
    # Values are related exactly, not just approximately.
    np.testing.assert_array_equal(
        frame["baseline_removed"].to_numpy(),
        frame["intensity_raw"].to_numpy() - frame["intensity_corrected"].to_numpy(),
    )


def test_metadata_records_steps_and_does_not_deny_processing(tmp_path: Path) -> None:
    imported, _, result = prepared(tmp_path)
    out = tmp_path / "out"
    outputs = export_processed(import_result=imported, result=result, output_base=out)

    text = outputs["metadata_json"].read_text(encoding="utf-8")
    metadata = json.loads(text)

    assert metadata["sha256"] == imported.sha256
    assert metadata["raw_file_unchanged"] is True
    assert metadata["processing"]["applied_in_this_run"]["baseline_correction"] is True
    assert metadata["processing"]["applied_in_this_run"]["smoothing"] is False
    assert metadata["processing"]["preprocessing_step_order"] == ["linear_baseline"]

    preprocessing = metadata["preprocessing"]
    assert metadata["data_kind"] == "baseline_corrected"
    assert preprocessing["data_kind"] == "baseline_corrected"
    assert preprocessing["algorithm"] == {
        "name": "ordinary_least_squares_union_of_windows",
        "version": "1.0",
    }
    assert preprocessing["output_columns"] == PROCESSED_COLUMNS
    assert preprocessing["raw_values_included_in_csv"] is True
    assert preprocessing["applied"] is True
    assert preprocessing["is_preview"] is False
    assert preprocessing["source_sha256"] == imported.sha256
    assert preprocessing["raw_data_modified"] is False
    assert preprocessing["steps"][0]["source_sha256"] == imported.sha256
    assert preprocessing["steps"][0]["parameters"]["windows_G"][0]["start"] == 3280.0
    assert preprocessing["steps"][0]["applied_at_utc"].endswith("+00:00")
    assert "exported_at_utc" in preprocessing
    assert set(preprocessing["output_statistics"]) == {
        "intensity_raw",
        "intensity_corrected",
        "baseline_removed",
    }

    # The processed metadata must not claim that no baseline correction ran.
    assert not any("No baseline correction" in item for item in metadata["assumptions"])
    assert any("baseline" in item.lower() for item in metadata["assumptions"])

    # Exported metadata is English by design.
    assert "预处理" not in text
    assert "基线" not in text


def test_processed_export_refuses_overwrite_by_default(tmp_path: Path) -> None:
    imported, _, result = prepared(tmp_path)
    out = tmp_path / "out"
    first = export_processed(import_result=imported, result=result, output_base=out)
    csv_hash = sha256(first["csv"])

    with pytest.raises(FileExistsError, match="already exist"):
        export_processed(import_result=imported, result=result, output_base=out)

    assert sha256(first["csv"]) == csv_hash


def test_processed_export_allows_explicit_overwrite(tmp_path: Path) -> None:
    imported, _, result = prepared(tmp_path)
    out = tmp_path / "out"
    export_processed(import_result=imported, result=result, output_base=out)

    outputs = export_processed(
        import_result=imported, result=result, output_base=out, overwrite=True
    )

    assert outputs["csv"].exists()


def test_processed_export_refuses_writes_inside_data_raw(tmp_path: Path) -> None:
    imported, _, result = prepared(tmp_path)
    raw_base = PROJECT_ROOT / "data" / "raw"
    tables = raw_base / "tables"

    with pytest.raises(ValueError, match="data/raw"):
        export_processed(
            import_result=imported, result=result, output_base=raw_base
        )

    assert not tables.exists()


def test_preview_cannot_be_exported(tmp_path: Path) -> None:
    imported, session, _ = prepared(tmp_path)
    preview = session.preview(default_spec())

    with pytest.raises(PreprocessingError) as excinfo:
        export_processed(
            import_result=imported, result=preview, output_base=tmp_path / "out"
        )

    assert excinfo.value.code == "preview_export"


def test_export_without_steps_is_refused(tmp_path: Path) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    imported = read_asc(source)
    session = PreprocessingSession(
        source=source,
        field_G=imported.data["field_G"].to_numpy(),
        intensity=imported.data["intensity"].to_numpy(),
        source_sha256=imported.sha256,
    )

    with pytest.raises(PreprocessingError) as excinfo:
        export_processed(
            import_result=imported,
            result=session.current_result(),
            output_base=tmp_path / "out",
        )

    assert excinfo.value.code == "no_steps"


def test_source_change_after_import_is_refused(tmp_path: Path) -> None:
    imported, _, result = prepared(tmp_path)
    source = Path(imported.source)
    source.write_text(source.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(PreprocessingError) as excinfo:
        export_processed(
            import_result=imported, result=result, output_base=tmp_path / "out"
        )

    assert excinfo.value.code == "source_changed"
    assert not (tmp_path / "out" / "tables" / "sample_baseline.csv").exists()


def test_export_does_not_modify_source(tmp_path: Path) -> None:
    imported, _, result = prepared(tmp_path)
    source = Path(imported.source)
    before = sha256(source)

    export_processed(
        import_result=imported, result=result, output_base=tmp_path / "out"
    )

    assert sha256(source) == before


def test_export_accepts_missing_session_sha_when_file_matches(
    tmp_path: Path,
) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    imported = read_asc(source)
    session = PreprocessingSession(
        source=source,
        field_G=imported.data["field_G"].to_numpy(),
        intensity=imported.data["intensity"].to_numpy(),
    )
    result = session.apply(default_spec())

    outputs = export_processed(
        import_result=imported, result=result, output_base=tmp_path / "out"
    )
    metadata = json.loads(outputs["metadata_json"].read_text(encoding="utf-8"))

    assert metadata["preprocessing"]["source_sha256"] == imported.sha256
    assert metadata["preprocessing"]["steps"][0]["source_sha256"] == imported.sha256


# --------------------------------------------------------------------------
# Savitzky-Golay exports
# --------------------------------------------------------------------------
def test_smoothing_export_uses_smoothed_suffix_and_difference_column(
    tmp_path: Path,
) -> None:
    imported, _, result = prepared_smoothing(tmp_path)
    source = Path(imported.source)
    before = sha256(source)
    out = tmp_path / "out"

    outputs = export_processed(
        import_result=imported, result=result, output_base=out
    )

    assert outputs["csv"] == out / "tables" / "sample_smoothed.csv"
    assert outputs["figure"] == out / "figures" / "sample_smoothed.png"
    assert (
        outputs["metadata_json"]
        == out / "logs" / "sample_smoothed_metadata.json"
    )
    for path in outputs.values():
        assert path.exists() and path.stat().st_size > 0

    frame = pd.read_csv(outputs["csv"])
    assert list(frame.columns) == SMOOTHED_COLUMNS
    np.testing.assert_array_equal(
        frame["intensity_corrected"].to_numpy(), result.intensity_processed
    )
    np.testing.assert_array_equal(
        frame["difference_from_raw"].to_numpy(), result.difference
    )
    np.testing.assert_array_equal(
        frame["difference_from_raw"].to_numpy(),
        frame["intensity_raw"].to_numpy()
        - frame["intensity_corrected"].to_numpy(),
    )
    assert sha256(source) == before


def test_smoothing_metadata_records_parameters_input_and_order(
    tmp_path: Path,
) -> None:
    imported, _, result = prepared_smoothing(tmp_path)
    outputs = export_processed(
        import_result=imported, result=result, output_base=tmp_path / "out"
    )
    text = outputs["metadata_json"].read_text(encoding="utf-8")
    metadata = json.loads(text)

    assert metadata["data_kind"] == "smoothed"
    assert metadata["processing"]["applied_in_this_run"]["smoothing"] is True
    assert metadata["processing"]["applied_in_this_run"]["baseline_correction"] is False
    assert metadata["processing"]["data_kind"] == "smoothed"
    assert metadata["processing"]["preprocessing_step_order"] == [
        "savitzky_golay"
    ]

    preprocessing = metadata["preprocessing"]
    assert preprocessing["data_kind"] == "smoothed"
    assert preprocessing["algorithm"] == {
        "name": "scipy.signal.savgol_filter",
        "version": "1.0",
    }
    assert preprocessing["output_columns"] == SMOOTHED_COLUMNS
    assert "difference_from_raw" in preprocessing["output_statistics"]
    assert "baseline_removed" not in preprocessing["output_statistics"]
    assert preprocessing["export_software"]["scipy"] != "not installed"
    assert "smoothing" not in preprocessing["not_applied"]
    assert "baseline_correction" in preprocessing["not_applied"]

    step = preprocessing["steps"][0]
    assert step["operation"] == "savitzky_golay"
    assert step["parameters"]["window_length"] == 9
    assert step["parameters"]["polyorder"] == 3
    assert step["parameters"]["input_source"] == "raw_data"
    assert step["parameters"]["input_step_count"] == 0
    assert step["diagnostics"]["n_points"] == len(imported.data)

    assert any("Savitzky-Golay" in item for item in metadata["assumptions"])
    assert "预处理" not in text
    assert "平滑" not in text


def test_mixed_export_records_order_and_suffix(tmp_path: Path) -> None:
    source = write_asc(tmp_path / "sample.ASC")
    imported = read_asc(source)
    session = PreprocessingSession(
        source=source,
        field_G=imported.data["field_G"].to_numpy(),
        intensity=imported.data["intensity"].to_numpy(),
        source_sha256=imported.sha256,
    )
    session.apply(default_spec())
    result = session.apply_savgol(SavgolSpec(9, 3))

    out = tmp_path / "out"
    outputs = export_processed(
        import_result=imported, result=result, output_base=out
    )

    assert outputs["csv"] == out / "tables" / "sample_baseline_smoothed.csv"
    metadata = json.loads(outputs["metadata_json"].read_text(encoding="utf-8"))
    assert metadata["data_kind"] == "baseline_corrected_and_smoothed"
    assert metadata["preprocessing"]["step_order"] == [
        "linear_baseline",
        "savitzky_golay",
    ]
    assert metadata["preprocessing"]["steps"][1]["parameters"][
        "input_source"
    ] == "current_processed_result"
    assert metadata["preprocessing"]["steps"][1]["parameters"][
        "input_step_count"
    ] == 1
    assert metadata["preprocessing"]["output_columns"] == SMOOTHED_COLUMNS
    frame = pd.read_csv(outputs["csv"])
    np.testing.assert_array_equal(
        frame["difference_from_raw"].to_numpy(), result.difference
    )


def test_smoothing_export_respects_overwrite_protection(tmp_path: Path) -> None:
    imported, _, result = prepared_smoothing(tmp_path)
    out = tmp_path / "out"
    first = export_processed(
        import_result=imported, result=result, output_base=out
    )
    csv_hash = sha256(first["csv"])

    with pytest.raises(FileExistsError, match="already exist"):
        export_processed(import_result=imported, result=result, output_base=out)

    assert sha256(first["csv"]) == csv_hash
