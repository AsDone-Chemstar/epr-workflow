"""Tests for the raw ASC import and plotting workflow."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epr_workflow import plot_asc
from epr_workflow.plot_asc import (
    AscDataError,
    AscFormatError,
    build_metadata,
    main,
    plot_spectrum,
    read_asc,
)

HEADER = "     index           Field [G]        Intensity []\n\n"

VALID_TEXT = HEADER + (
    "         1                3280             400.088\n"
    "         2              3280.1             272.312\n"
    "         3              3280.2             364.536\n"
    "         4             3280.29            -29.2404\n"
    "         5             3280.39             185.984\n"
)

REAL_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "BSA3T275.ASC"


def write_text(path: Path, text: str) -> Path:
    # newline="\n" keeps the byte count identical on Windows (no CRLF translation).
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# 1-3. Reading valid files, blank lines, headers and column mapping
# --------------------------------------------------------------------------
def test_reads_valid_whitespace_separated_file(tmp_path: Path) -> None:
    result = read_asc(write_text(tmp_path / "valid.ASC", VALID_TEXT))

    assert len(result.data) == 5
    assert list(result.data.columns) == ["index", "field_G", "intensity"]
    assert result.rejected_rows == []
    assert result.file_size_bytes == (tmp_path / "valid.ASC").stat().st_size


def test_ignores_blank_lines_and_header(tmp_path: Path) -> None:
    text = "\n\n" + HEADER + "\n" + VALID_TEXT.split("\n", 2)[2] + "\n\n"
    result = read_asc(write_text(tmp_path / "blank.ASC", text))

    assert len(result.data) == 5


def test_columns_are_mapped_in_the_documented_order(tmp_path: Path) -> None:
    result = read_asc(write_text(tmp_path / "map.ASC", VALID_TEXT))
    first = result.data.iloc[0]

    assert first["index"] == pytest.approx(1.0)
    assert first["field_G"] == pytest.approx(3280.0)
    assert first["intensity"] == pytest.approx(400.088)
    assert result.data["index"].tolist() == [1, 2, 3, 4, 5]


# --------------------------------------------------------------------------
# 4-5. Malformed and non-finite rows
# --------------------------------------------------------------------------
def test_malformed_rows_are_reported_not_silently_dropped(tmp_path: Path) -> None:
    text = HEADER + (
        "         1                3280             400.088\n"
        "         2              3280.1             272.312\n"
        "         oops            3280.2             364.536\n"
        "         4             3280.29\n"
        "         5             3280.39             185.984\n"
    )
    result = read_asc(write_text(tmp_path / "bad.ASC", text))

    assert len(result.data) == 3
    assert len(result.rejected_rows) == 2
    assert result.missing_value_count == 1
    assert any("rejected" in w for w in result.warnings)
    assert any("non-numeric" in r["reason"] for r in result.rejected_rows)


def test_non_finite_values_are_detected_and_excluded(tmp_path: Path) -> None:
    text = HEADER + (
        "         1                3280             400.088\n"
        "         2              3280.1                 nan\n"
        "         3              3280.2                 inf\n"
        "         4             3280.29            -29.2404\n"
        "         5             3280.39             185.984\n"
    )
    result = read_asc(write_text(tmp_path / "nan.ASC", text))

    assert len(result.data) == 3
    assert result.nonfinite_value_count == 2
    assert np.all(np.isfinite(result.data["intensity"].to_numpy()))
    assert any("non-finite" in w for w in result.warnings)


# --------------------------------------------------------------------------
# 6. Non-monotonic field detection
# --------------------------------------------------------------------------
def test_non_monotonic_field_raises_by_default(tmp_path: Path) -> None:
    text = HEADER + (
        "         1                3280             400.088\n"
        "         2              3280.1             272.312\n"
        "         3              3280.0             364.536\n"
        "         4             3280.29            -29.2404\n"
    )
    path = write_text(tmp_path / "nonmono.ASC", text)

    with pytest.raises(AscDataError, match="non-monotonic"):
        read_asc(path)

    result = read_asc(path, allow_non_monotonic=True)
    assert result.field_order == "non-monotonic"
    assert len(result.data) == 4  # original order preserved, nothing sorted


def test_strictly_decreasing_field_is_reported(tmp_path: Path) -> None:
    text = HEADER + (
        "         1                3280             400.088\n"
        "         2              3279.9             272.312\n"
        "         3              3279.8             364.536\n"
    )
    result = read_asc(write_text(tmp_path / "dec.ASC", text))

    assert result.field_order == "strictly decreasing"
    assert result.data["field_G"].iloc[0] == pytest.approx(3280.0)


# --------------------------------------------------------------------------
# 7. Missing file and malformed header
# --------------------------------------------------------------------------
def test_missing_input_file_gives_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="not found"):
        read_asc(tmp_path / "does_not_exist.ASC")


def test_wrong_header_raises_instead_of_guessing(tmp_path: Path) -> None:
    text = "time       amplitude\n1 2\n3 4\n"
    with pytest.raises(AscFormatError, match="header"):
        read_asc(write_text(tmp_path / "wrong.ASC", text))


def test_swapped_columns_raise(tmp_path: Path) -> None:
    text = "Field [G]   index   Intensity []\n3280 1 5\n3280.1 2 6\n3280.2 3 7\n"
    with pytest.raises(AscFormatError, match="column order"):
        read_asc(write_text(tmp_path / "swapped.ASC", text))


def test_too_few_points_raise(tmp_path: Path) -> None:
    text = HEADER + "1 3280 5\n2 3280.1 6\n"
    with pytest.raises(AscDataError, match="at least"):
        read_asc(write_text(tmp_path / "short.ASC", text))


# --------------------------------------------------------------------------
# 8. Invalid data must not silently produce a figure
# --------------------------------------------------------------------------
def test_invalid_data_does_not_write_a_figure(tmp_path: Path) -> None:
    text = HEADER + (
        "         1                3280             400.088\n"
        "         2              3280.1             272.312\n"
        "         3              3280.0             364.536\n"
    )
    source = write_text(tmp_path / "bad.ASC", text)
    figure = tmp_path / "should_not_exist.png"
    csv_file = tmp_path / "should_not_exist.csv"
    json_file = tmp_path / "should_not_exist.json"

    exit_code = main(
        [
            str(source),
            "--figure",
            str(figure),
            "--csv",
            str(csv_file),
            "--json",
            str(json_file),
        ]
    )

    assert exit_code == 1
    assert not figure.exists()
    assert not csv_file.exists()
    assert not json_file.exists()


# --------------------------------------------------------------------------
# 9. The original data file must never be modified
# --------------------------------------------------------------------------
@pytest.mark.skipif(not REAL_FILE.exists(), reason="experimental ASC file not present")
def test_original_file_is_not_modified(tmp_path: Path) -> None:
    before_hash = sha256(REAL_FILE)
    before_mtime = REAL_FILE.stat().st_mtime_ns

    exit_code = main(
        [
            str(REAL_FILE),
            "--figure",
            str(tmp_path / "f.png"),
            "--csv",
            str(tmp_path / "f.csv"),
            "--json",
            str(tmp_path / "f.json"),
        ]
    )

    assert exit_code == 0
    assert sha256(REAL_FILE) == before_hash
    assert REAL_FILE.stat().st_mtime_ns == before_mtime


# --------------------------------------------------------------------------
# Plotting and export
# --------------------------------------------------------------------------
def test_plot_spectrum_creates_png(tmp_path: Path) -> None:
    result = read_asc(write_text(tmp_path / "valid.ASC", VALID_TEXT))
    output = plot_spectrum(
        result.data, tmp_path / "figs" / "spectrum.png", title="Test spectrum"
    )

    assert output.exists()
    assert output.stat().st_size > 1000


def test_main_writes_csv_json_and_png(tmp_path: Path) -> None:
    source = write_text(tmp_path / "sample.ASC", VALID_TEXT)
    csv_file = tmp_path / "tables" / "sample.csv"
    json_file = tmp_path / "logs" / "sample.json"
    figure = tmp_path / "figs" / "sample.png"

    exit_code = main(
        [
            str(source),
            "--figure",
            str(figure),
            "--csv",
            str(csv_file),
            "--json",
            str(json_file),
        ]
    )

    assert exit_code == 0
    assert csv_file.exists() and json_file.exists() and figure.exists()

    metadata = json.loads(json_file.read_text(encoding="utf-8"))
    assert metadata["data"]["valid_points"] == 5
    assert metadata["data"]["field_min_G"] == pytest.approx(3280.0)
    assert metadata["data"]["field_max_G"] == pytest.approx(3280.39)
    assert metadata["data"]["field_order"] == "strictly increasing"
    assert metadata["raw_file_unchanged"] is True
    assert metadata["source_file"] == "sample.ASC"


def test_metadata_never_invents_units_or_parameters() -> None:
    result = read_asc(REAL_FILE) if REAL_FILE.exists() else None
    if result is None:
        pytest.skip("experimental ASC file not present")

    metadata = build_metadata(result, raw_file_unchanged=True)
    assert "intensity_unit" not in metadata["data"]
    assert not any("mT" in item for item in metadata["assumptions"])
    assert "original" in metadata["assumptions"][3]


# --------------------------------------------------------------------------
# Real experimental file end-to-end
# --------------------------------------------------------------------------
@pytest.mark.skipif(not REAL_FILE.exists(), reason="experimental ASC file not present")
def test_real_experimental_file_imports_cleanly() -> None:
    result = read_asc(REAL_FILE)

    assert len(result.data) > 100
    assert result.rejected_rows == []
    assert result.field_order == "strictly increasing"
    assert result.data["field_G"].is_monotonic_increasing
    assert result.data["field_G"].min() == pytest.approx(3280.0)


# --------------------------------------------------------------------------
# CSV fidelity, metadata statistics, endpoint regression
# --------------------------------------------------------------------------
def test_csv_round_trip_matches_parsed_data(tmp_path: Path) -> None:
    source = write_text(tmp_path / "sample.ASC", VALID_TEXT)
    result = read_asc(source)
    csv_file = tmp_path / "out.csv"

    exit_code = main(
        [
            str(source),
            "--csv",
            str(csv_file),
            "--figure",
            str(tmp_path / "f.png"),
            "--json",
            str(tmp_path / "m.json"),
        ]
    )

    assert exit_code == 0
    exported = pd.read_csv(csv_file)
    np.testing.assert_array_equal(
        exported["index"].to_numpy(), result.data["index"].to_numpy()
    )
    np.testing.assert_array_equal(
        exported["field_G"].to_numpy(), result.data["field_G"].to_numpy()
    )
    np.testing.assert_array_equal(
        exported["intensity"].to_numpy(), result.data["intensity"].to_numpy()
    )


def test_integer_index_is_written_as_integer(tmp_path: Path) -> None:
    source = write_text(tmp_path / "int.ASC", VALID_TEXT)
    csv_file = tmp_path / "int.csv"

    assert main([str(source), "--csv", str(csv_file),
                 "--figure", str(tmp_path / "f.png"),
                 "--json", str(tmp_path / "m.json")]) == 0

    exported = pd.read_csv(csv_file)
    assert exported["index"].tolist() == [1, 2, 3, 4, 5]
    assert exported["index"].dtype.kind in "iu"
    assert not csv_file.read_text(encoding="utf-8").splitlines()[1].startswith("1.0")


def test_non_integer_index_is_not_rounded(tmp_path: Path) -> None:
    text = HEADER + "1.5 3280 10\n2.5 3280.1 11\n3.5 3280.2 12\n"
    source = write_text(tmp_path / "frac.ASC", text)
    result = read_asc(source)

    assert result.data["index"].tolist() == [1.5, 2.5, 3.5]
    assert any("non-integer" in w for w in result.warnings)

    csv_file = tmp_path / "frac.csv"
    assert main([str(source), "--csv", str(csv_file),
                 "--figure", str(tmp_path / "f.png"),
                 "--json", str(tmp_path / "m.json")]) == 0
    assert pd.read_csv(csv_file)["index"].tolist() == [1.5, 2.5, 3.5]


@pytest.mark.skipif(not REAL_FILE.exists(), reason="experimental ASC file not present")
def test_metadata_statistics_match_independent_recalculation(tmp_path: Path) -> None:
    reference = np.loadtxt(REAL_FILE, skiprows=2)  # independent parse
    json_file = tmp_path / "meta.json"

    assert main([str(REAL_FILE),
                 "--figure", str(tmp_path / "f.png"),
                 "--csv", str(tmp_path / "f.csv"),
                 "--json", str(json_file)]) == 0

    data = json.loads(json_file.read_text(encoding="utf-8"))["data"]
    signal = reference[:, 2]
    assert data["valid_points"] == reference.shape[0]
    assert data["field_min_G"] == float(reference[:, 1].min())
    assert data["field_max_G"] == float(reference[:, 1].max())
    assert data["signal_min"] == float(signal.min())
    assert data["signal_max"] == float(signal.max())
    assert data["signal_mean"] == pytest.approx(float(signal.mean()), rel=1e-12)
    assert data["signal_std"] == pytest.approx(float(signal.std(ddof=1)), rel=1e-12)
    assert data["field_order"] == "strictly increasing"


@pytest.mark.skipif(not REAL_FILE.exists(), reason="experimental ASC file not present")
def test_bsa3t275_endpoint_regression() -> None:
    result = read_asc(REAL_FILE)

    assert len(result.data) == 1024
    assert float(result.data["field_G"].iloc[0]) == 3280.0
    assert float(result.data["field_G"].iloc[-1]) == 3380.0
    assert float(result.data["intensity"].iloc[0]) == 400.088


# --------------------------------------------------------------------------
# Validation diagnostics: duplicates, missing columns, index gaps
# --------------------------------------------------------------------------
def test_duplicate_field_diagnostics_do_not_alter_data(tmp_path: Path) -> None:
    text = HEADER + (
        "1 3280 10\n2 3280.1 11\n3 3280 12\n4 3280.2 13\n"
    )
    source = write_text(tmp_path / "dup.ASC", text)

    with pytest.raises(AscDataError, match="1 duplicated field value"):
        read_asc(source)

    result = read_asc(source, allow_non_monotonic=True)
    assert result.duplicate_field_count == 1
    assert len(result.data) == 4
    assert result.data["field_G"].tolist() == [3280.0, 3280.1, 3280.0, 3280.2]
    assert any("duplicate" in w.lower() for w in result.warnings)


def test_missing_value_count_is_a_row_count(tmp_path: Path) -> None:
    text = HEADER + "1 3280 5\n2 3280.1\n3 3280.2 6\n4 3280.3 7\n"
    result = read_asc(write_text(tmp_path / "shortrow.ASC", text))

    assert result.missing_value_count == 1
    metadata = build_metadata(result, raw_file_unchanged=True)
    assert metadata["data"]["missing_value_count"] == 1
    assert "row count" in metadata["data"]["missing_value_count_definition"]


def test_index_gaps_are_warned_without_reordering(tmp_path: Path) -> None:
    text = HEADER + "1 3280 10\n2 3280.1 11\n4 3280.2 12\n5 3280.3 13\n"
    result = read_asc(write_text(tmp_path / "gap.ASC", text))

    assert result.index_continuity == "gaps (1)"
    assert any("not consecutive" in w for w in result.warnings)
    assert result.data["index"].tolist() == [1, 2, 4, 5]
    assert result.data["field_G"].tolist() == [3280.0, 3280.1, 3280.2, 3280.3]


def test_index_does_not_have_to_start_at_one(tmp_path: Path) -> None:
    text = HEADER + "10 3280 1\n11 3280.1 2\n12 3280.2 3\n"
    result = read_asc(write_text(tmp_path / "offset.ASC", text))

    assert result.index_continuity == "consecutive"
    assert result.warnings == []


# --------------------------------------------------------------------------
# Metadata outputs / processing record
# --------------------------------------------------------------------------
def test_metadata_records_outputs_and_processing(tmp_path: Path) -> None:
    source = write_text(tmp_path / "sample.ASC", VALID_TEXT)
    csv_file = tmp_path / "out.csv"
    figure = tmp_path / "fig.png"
    json_file = tmp_path / "meta.json"

    assert main([str(source), "--csv", str(csv_file),
                 "--figure", str(figure),
                 "--json", str(json_file)]) == 0

    metadata = json.loads(json_file.read_text(encoding="utf-8"))
    assert metadata["outputs"]["csv"] == str(csv_file.resolve())
    assert metadata["outputs"]["figure"] == str(figure.resolve())
    assert metadata["outputs"]["metadata_json"] == str(json_file.resolve())
    assert Path(metadata["outputs"]["figure"]).exists()

    processing = metadata["processing"]
    assert processing["plot"]["dpi"] == 300
    assert processing["plot"]["figsize_inch"] == [8.0, 5.0]
    assert processing["plot"]["line_width"] == 1.0
    assert processing["applied_in_this_run"] == {
        "smoothing": False,
        "baseline_correction": False,
        "normalisation": False,
        "field_axis_reversal": False,
    }
    assert "this run only" in processing["description"]
    assert "not a guarantee" in processing["description"]
