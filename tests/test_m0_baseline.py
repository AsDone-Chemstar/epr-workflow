"""M0 numerical and export baselines for the released EPR workflow.

These tests are intentionally read-only. They compare the current v0.2.0
loaders and exporters with the machine-readable baseline in
``tests/fixtures/m0_baseline.json``.

The real source files are local experimental data and are not distributed with
the repository. Tests that need them skip when the files are absent; the
baseline record still documents the expected values.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epr_workflow.plot_asc import PROJECT_ROOT, main, read_dataset


BASELINE_PATH = Path(__file__).parent / "fixtures" / "m0_baseline.json"
BASELINE = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
DATASETS = BASELINE["datasets"]


def _paths_for(key: str) -> tuple[dict, dict[str, Path]]:
    record = DATASETS[key]
    entry = PROJECT_ROOT / record["relative_path"]
    if record["source_format"] == "BES3T":
        paths = {
            "descriptor": entry,
            "data": PROJECT_ROOT / record["companion_relative_path"],
        }
    else:
        paths = {"source": entry}
    return record, paths


def _require(paths: dict[str, Path]) -> None:
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        pytest.skip("local baseline source file(s) not present: " + ", ".join(missing))


def _hashes(paths: dict[str, Path]) -> dict[str, str]:
    return {
        role: hashlib.sha256(path.read_bytes()).hexdigest()
        for role, path in paths.items()
    }


def _normalized_result_hashes(result) -> dict[str, str]:
    hashes = dict(result.source_hashes)
    if not hashes:
        hashes = {"source": result.sha256}
    return hashes


def _assert_baseline_record(result, record: dict) -> None:
    assert result.source_format == record["source_format"]
    assert result.file_size_bytes == record["file_size_bytes"]
    assert result.sha256 == record["sha256"]
    assert _normalized_result_hashes(result) == record["source_hashes"]
    assert list(result.data.columns) == ["index", "field_G", "intensity"]
    assert len(result.data) == record["n_points"]
    assert result.field_order == record["field_direction"]
    assert result.index_continuity == record["index_continuity"]
    assert result.rejected_rows == []
    assert result.missing_value_count == record["missing_value_count"]
    assert result.nonfinite_value_count == record["nonfinite_value_count"]
    assert result.duplicate_field_count == record["duplicate_field_count"]
    assert result.warnings == record["warnings"]

    field = result.data["field_G"].to_numpy()
    intensity = result.data["intensity"].to_numpy()
    assert field[0] == record["field_first"]
    assert field[-1] == record["field_last"]
    assert field.min() == record["field_min"]
    assert field.max() == record["field_max"]
    assert intensity[0] == record["intensity_first"]
    assert intensity[-1] == record["intensity_last"]
    assert intensity.min() == record["intensity_min"]
    assert intensity.max() == record["intensity_max"]
    np.testing.assert_array_equal(
        intensity[:5], np.asarray(record["intensity_first5"])
    )
    np.testing.assert_array_equal(
        intensity[-5:], np.asarray(record["intensity_last5"])
    )

    if record["source_format"] == "BES3T":
        assert result.format_metadata["axis"] == record["axis"]
        assert result.format_metadata["binary"] == record["binary"]
        assert (
            result.format_metadata["descriptor_version"]
            == record["descriptor_version"]
        )


@pytest.mark.parametrize("key", ["asc_real", "bes3t_real"])
def test_real_dataset_matches_recorded_numerical_baseline(key: str) -> None:
    record, paths = _paths_for(key)
    _require(paths)
    before = _hashes(paths)

    result = read_dataset(paths.get("descriptor", paths.get("source")))

    _assert_baseline_record(result, record)
    assert before == record["source_hashes"]
    assert _hashes(paths) == before


@pytest.mark.parametrize("key", ["asc_real", "bes3t_real"])
def test_real_raw_export_matches_recorded_schema_and_provenance(
    tmp_path: Path, key: str
) -> None:
    record, paths = _paths_for(key)
    _require(paths)
    before = _hashes(paths)
    entry = paths.get("descriptor", paths.get("source"))
    out = tmp_path / key

    exit_code = main([str(entry), "--output-dir", str(out)])

    assert exit_code == 0
    csv_path = out / "tables" / f"{entry.stem}_raw.csv"
    figure_path = out / "figures" / f"{entry.stem}_raw.png"
    metadata_path = out / "logs" / f"{entry.stem}_metadata.json"
    assert csv_path.exists()
    assert figure_path.exists()
    assert metadata_path.exists()

    frame = pd.read_csv(csv_path)
    if key == "asc_real":
        assert list(frame.columns) == ["index", "field_G", "intensity"]
    else:
        assert list(frame.columns) == [
            "index",
            "field_G",
            "intensity",
            "source_format",
        ]
        assert set(frame["source_format"]) == {"BES3T"}
    assert len(frame) == record["n_points"]
    assert frame["field_G"].iloc[0] == record["field_first"]
    assert frame["field_G"].iloc[-1] == record["field_last"]
    assert frame["intensity"].iloc[0] == record["intensity_first"]
    assert frame["intensity"].iloc[-1] == record["intensity_last"]

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    required = {
        "source_file",
        "source_path",
        "file_size_bytes",
        "sha256",
        "import_timestamp_utc",
        "software_versions",
        "data",
        "outputs",
        "processing",
        "rejected_row_details",
        "rejected_row_details_truncated",
        "validation_warnings",
        "assumptions",
        "raw_file_unchanged",
    }
    assert required <= set(metadata)
    assert metadata["source_file"] == entry.name
    assert metadata["file_size_bytes"] == record["file_size_bytes"]
    assert metadata["sha256"] == record["sha256"]
    assert metadata["data"]["valid_points"] == record["n_points"]
    assert metadata["data"]["field_min_G"] == record["field_min"]
    assert metadata["data"]["field_max_G"] == record["field_max"]
    assert metadata["data"]["field_order"] == record["field_direction"]
    assert metadata["validation_warnings"] == record["warnings"]
    assert metadata["raw_file_unchanged"] is True
    assert metadata["rejected_row_details"] == []
    assert metadata["rejected_row_details_truncated"] is False
    assert metadata["outputs"]["csv"] == str(csv_path.resolve())
    assert metadata["outputs"]["figure"] == str(figure_path.resolve())
    assert metadata["outputs"]["metadata_json"] == str(metadata_path.resolve())
    assert metadata["processing"]["applied_in_this_run"] == {
        "smoothing": False,
        "baseline_correction": False,
        "normalisation": False,
        "field_axis_reversal": False,
    }
    assert metadata["assumptions"]

    if key == "asc_real":
        assert "source_format" not in metadata
    else:
        assert metadata["source_format"] == "BES3T"
        by_role = {entry_["role"]: entry_ for entry_ in metadata["source_files"]}
        assert set(by_role) == {"descriptor", "data"}
        assert by_role["descriptor"]["sha256"] == record["source_hashes"]["descriptor"]
        assert by_role["data"]["sha256"] == record["source_hashes"]["data"]
        assert metadata["format_metadata"]["axis"] == record["axis"]
        assert metadata["format_metadata"]["binary"] == record["binary"]

    assert _hashes(paths) == before
