"""Tests for the one-way legacy EPR → Spectrum1D adapter."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from epr_workflow.plot_asc import PROJECT_ROOT, read_dataset
from spectralab.core.legacy_adapter import (
    LegacyAdapterError,
    LegacyEprAdapter,
    spectrum1d_from_import_result,
    to_spectrum1d,
)
from spectralab.core.model import Axis1D, Signal1D, Spectrum1D

BASELINE_PATH = Path(__file__).parent / "fixtures" / "m0_baseline.json"
BASELINE = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

HEADER = "     index           Field [G]        Intensity []\n\n"


def _paths_for(key: str) -> tuple[dict, dict[str, Path]]:
    record = BASELINE["datasets"][key]
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


def _write_asc(path: Path, rows: list[str]) -> Path:
    path.write_text(
        HEADER + "\n".join(rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _write_bes3t(tmp_path: Path) -> tuple[Path, Path]:
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
    return dsc, dta


@pytest.mark.parametrize("key", ["asc_real", "bes3t_real"])
def test_real_adapter_matches_m0_baseline(key: str) -> None:
    record, paths = _paths_for(key)
    _require(paths)
    before = _hashes(paths)
    entry = paths.get("descriptor", paths.get("source"))
    imported = read_dataset(entry)
    before_x = imported.data["field_G"].to_numpy().copy()
    before_y = imported.data["intensity"].to_numpy().copy()

    spectrum = to_spectrum1d(imported)

    assert isinstance(spectrum, Spectrum1D)
    assert spectrum.point_count == record["n_points"]
    np.testing.assert_array_equal(spectrum.x_values, before_x)
    np.testing.assert_array_equal(spectrum.y_values, before_y)
    assert spectrum.x_values[0] == record["field_first"]
    assert spectrum.x_values[-1] == record["field_last"]
    assert spectrum.y_values[0] == record["intensity_first"]
    assert spectrum.y_values[-1] == record["intensity_last"]
    assert spectrum.y_values.min() == record["intensity_min"]
    assert spectrum.y_values.max() == record["intensity_max"]
    np.testing.assert_array_equal(
        spectrum.y_values[:5], np.asarray(record["intensity_first5"])
    )
    np.testing.assert_array_equal(
        spectrum.y_values[-5:], np.asarray(record["intensity_last5"])
    )
    assert spectrum.axis.quantity == "magnetic_field"
    assert spectrum.axis.unit == "G"
    assert spectrum.axis.direction == "increasing"
    assert spectrum.raw_signal.semantics == "unknown"
    assert spectrum.raw_signal.unit is None
    assert spectrum.source_format == record["source_format"]
    assert spectrum.metadata.technique == "epr"
    assert "signal_semantics" in spectrum.metadata.unknown_fields
    assert "signal_unit" in spectrum.metadata.unknown_fields
    assert spectrum.provenance.canonical_sha256 == record["sha256"]
    assert spectrum.provenance.file_size_bytes == record["file_size_bytes"]
    assert {
        source.role: source.sha256 for source in spectrum.provenance.source_files
    } == record["source_hashes"]
    assert spectrum.provenance.imported_at_utc is None
    assert spectrum.provenance.importer_id == "epr_workflow.legacy_adapter"

    if record["source_format"] == "BES3T":
        assert spectrum.provenance.format_metadata["axis"] == record["axis"]
        assert spectrum.provenance.format_metadata["binary"] == record["binary"]
    else:
        assert "source_format" not in imported.format_metadata

    # The legacy result and the source files must not be modified.
    np.testing.assert_array_equal(
        imported.data["field_G"].to_numpy(), before_x
    )
    np.testing.assert_array_equal(
        imported.data["intensity"].to_numpy(), before_y
    )
    assert _hashes(paths) == before


def test_adapter_preserves_asc_source_format_and_unknown_metadata(
    tmp_path: Path,
) -> None:
    source = _write_asc(
        tmp_path / "sample.ASC",
        [
            "1 3300.0 10.0",
            "2 3301.0 20.0",
            "3 3302.0 30.0",
        ],
    )
    imported = read_dataset(source)

    spectrum = spectrum1d_from_import_result(imported)

    assert spectrum.dataset_id == "sample"
    assert spectrum.source_format == "ASC"
    assert spectrum.axis.unit == "G"
    assert spectrum.axis.direction == "increasing"
    assert spectrum.raw_signal.name == "Intensity"
    assert spectrum.raw_signal.semantics == "unknown"
    assert spectrum.raw_signal.unit is None
    assert [item.role for item in spectrum.provenance.source_files] == ["source"]
    assert spectrum.provenance.source_files[0].sha256 == imported.sha256
    assert spectrum.provenance.canonical_sha256 == imported.sha256
    assert "instrument" in spectrum.metadata.unknown_fields
    assert "acquisition" in spectrum.metadata.unknown_fields
    assert "sample" in spectrum.metadata.unknown_fields
    assert "signal_unit" in spectrum.metadata.unknown_fields


def test_adapter_preserves_bes3t_source_files_and_axis_metadata(
    tmp_path: Path,
) -> None:
    dsc, _dta = _write_bes3t(tmp_path)
    imported = read_dataset(dsc)

    spectrum = LegacyEprAdapter().to_spectrum1d(imported)

    assert spectrum.source_format == "BES3T"
    assert {item.role for item in spectrum.provenance.source_files} == {
        "descriptor",
        "data",
    }
    assert spectrum.provenance.format_metadata["source_format"] == "BES3T"
    assert spectrum.provenance.format_metadata["binary"]["IRFMT"] == "D"
    assert spectrum.provenance.format_metadata["axis"]["XWID"] == 2.0
    assert spectrum.provenance.canonical_sha256 == imported.sha256
    assert spectrum.axis.direction == "increasing"


def test_adapter_preserves_decreasing_axis_order(tmp_path: Path) -> None:
    source = _write_asc(
        tmp_path / "decreasing.ASC",
        [
            "1 3302.0 10.0",
            "2 3301.0 20.0",
            "3 3300.0 30.0",
        ],
    )
    imported = read_dataset(source)
    spectrum = to_spectrum1d(imported)

    assert imported.field_order == "strictly decreasing"
    assert spectrum.axis.direction == "decreasing"
    np.testing.assert_array_equal(spectrum.x_values, [3302.0, 3301.0, 3300.0])
    np.testing.assert_array_equal(spectrum.y_values, [10.0, 20.0, 30.0])


def test_adapter_rejects_missing_required_columns(tmp_path: Path) -> None:
    source = _write_asc(
        tmp_path / "bad.ASC",
        ["1 3300.0 10.0", "2 3301.0 20.0", "3 3302.0 30.0"],
    )
    imported = read_dataset(source)
    imported.data = imported.data.drop(columns=["intensity"])

    with pytest.raises(LegacyAdapterError) as exc:
        to_spectrum1d(imported)

    assert exc.value.code == "legacy_columns"


def test_adapter_aliases_point_to_the_same_conversion(tmp_path: Path) -> None:
    source = _write_asc(
        tmp_path / "alias.ASC",
        ["1 3300.0 10.0", "2 3301.0 20.0", "3 3302.0 30.0"],
    )
    imported = read_dataset(source)

    a = spectrum1d_from_import_result(imported)
    b = to_spectrum1d(imported)

    np.testing.assert_array_equal(a.x_values, b.x_values)
    np.testing.assert_array_equal(a.y_values, b.y_values)
    assert a.provenance.canonical_sha256 == b.provenance.canonical_sha256


def test_model_classes_reject_obvious_invalid_axis_and_signal() -> None:
    with pytest.raises(ValueError):
        Axis1D(values=[1.0, 2.0], quantity="magnetic_field", unit="")
    with pytest.raises(ValueError):
        Signal1D(values=[1.0, 2.0], semantics="unknown", unit="")
