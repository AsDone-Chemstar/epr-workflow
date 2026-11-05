"""Migration tests for the independent SpectraLab EPR backend."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from epr_workflow.bes3t import read_bes3t as legacy_read_bes3t
from epr_workflow.plot_asc import read_asc as legacy_read_asc
from epr_workflow.preprocessing import (
    BaselineWindow as LegacyBaselineWindow,
    LinearBaselineSpec as LegacyLinearBaselineSpec,
    SavgolSpec as LegacySavgolSpec,
    fit_linear_baseline as legacy_fit_linear_baseline,
    smooth_savgol as legacy_smooth_savgol,
    validate_savgol_spec as legacy_validate_savgol_spec,
)
from spectralab.techniques.epr.importers._asc_reader import (
    AscDataError as NewAscDataError,
    AscFormatError as NewAscFormatError,
    read_asc as new_read_asc,
)
from spectralab.techniques.epr.importers._bes3t_reader import (
    Bes3tError as NewBes3tError,
    read_bes3t as new_read_bes3t,
)
from spectralab.techniques.epr.processing_impl import (
    BaselineWindow as NewBaselineWindow,
    LinearBaselineSpec as NewLinearBaselineSpec,
    SavgolSpec as NewSavgolSpec,
    fit_linear_baseline as new_fit_linear_baseline,
    smooth_savgol as new_smooth_savgol,
    validate_savgol_spec as new_validate_savgol_spec,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = Path(__file__).parent / "fixtures" / "m0_baseline.json"
BASELINE = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
HEADER = "     index           Field [G]        Intensity []\n\n"


def _write_asc(path: Path, rows: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        HEADER + "\n".join(rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _write_bes3t(
    tmp_path: Path,
    *,
    values=(1.5, -2.0, 3.25, 0.125, 9.0),
    xmin: float = 3300.0,
    xwid: float = 2.0,
    xuni: str = "G",
    ikkf: str = "REAL",
    bseq: str = "BIG",
    irfmt: str = "D",
    payload: bytes | None = None,
    write_companion: bool = True,
) -> tuple[Path, Path]:
    dsc = tmp_path / "sample.DSC"
    dta = tmp_path / "sample.DTA"
    lines = [
        "#DESC 1.2",
        "DSRC EXP",
        f"BSEQ {bseq}",
        f"IKKF {ikkf}",
        "XTYP IDX",
        "YTYP NODATA",
        "ZTYP NODATA",
        f"IRFMT {irfmt}",
        f"XPTS {len(values)}",
        f"XMIN {xmin}",
        f"XWID {xwid}",
        "XNAM 'Field'",
        f"XUNI '{xuni}'",
        "IRNAM 'Intensity'",
        "IRUNI ''",
    ]
    dsc.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    if write_companion:
        if payload is None:
            dtype = (">" if bseq == "BIG" else "<") + {
                "C": "i1",
                "S": "i2",
                "I": "i4",
                "F": "f4",
                "D": "f8",
            }[irfmt]
            payload = np.asarray(values, dtype=dtype).tobytes()
        dta.write_bytes(payload)
    return dsc, dta


def _compare_import_results(old, new) -> None:
    assert new.source == old.source
    assert new.source_format == old.source_format
    assert list(new.data.columns) == list(old.data.columns)
    assert new.data.equals(old.data)
    assert new.rejected_rows == old.rejected_rows
    assert new.warnings == old.warnings
    assert new.sha256 == old.sha256
    assert new.file_size_bytes == old.file_size_bytes
    assert new.field_order == old.field_order
    assert new.missing_value_count == old.missing_value_count
    assert new.nonfinite_value_count == old.nonfinite_value_count
    assert new.duplicate_field_count == old.duplicate_field_count
    assert new.index_continuity == old.index_continuity
    assert new.source_files == old.source_files
    assert new.source_hashes == old.source_hashes
    assert new.sha256_definition == old.sha256_definition
    assert new.format_metadata == old.format_metadata
    assert new.format_assumptions == old.format_assumptions


# --------------------------------------------------------------------------
# ASC reader
# --------------------------------------------------------------------------
def test_asc_reader_matches_legacy_on_warning_and_rejection_paths(
    tmp_path: Path,
) -> None:
    path = _write_asc(
        tmp_path / "warn.ASC",
        [
            "1 3280.0 10.0",
            "not-a-number",
            "2 3280.1 20.0",
            "4 3280.2 30.0",
            "5 3280.3 nan",
        ],
    )

    old = legacy_read_asc(path)
    new = new_read_asc(path)

    _compare_import_results(old, new)
    assert new.warnings
    assert new.rejected_rows


def test_asc_reader_matches_legacy_on_real_m0_data() -> None:
    record = BASELINE["datasets"]["asc_real"]
    path = PROJECT_ROOT / record["relative_path"]
    if not path.is_file():
        pytest.skip(f"local ASC baseline not present: {path}")

    old = legacy_read_asc(path)
    new = new_read_asc(path)

    _compare_import_results(old, new)
    assert new.sha256 == record["sha256"]
    assert len(new.data) == record["n_points"]
    np.testing.assert_array_equal(
        new.data["field_G"].to_numpy(),
        old.data["field_G"].to_numpy(),
    )


@pytest.mark.parametrize(
    "rows,error_name",
    [
        (["1 3280 10", "2 3280.1 20"], "AscDataError"),
        (["1 1 1", "2 1 2", "3 1 3"], "AscDataError"),
    ],
)
def test_asc_reader_error_behavior_matches_legacy(
    tmp_path: Path,
    rows: list[str],
    error_name: str,
) -> None:
    path = _write_asc(tmp_path / "bad.ASC", rows)
    with pytest.raises(Exception) as old_error:
        legacy_read_asc(path)
    with pytest.raises(Exception) as new_error:
        new_read_asc(path)

    assert type(old_error.value).__name__ == type(new_error.value).__name__
    assert error_name == type(new_error.value).__name__
    assert str(old_error.value) == str(new_error.value)


def test_asc_reader_missing_header_matches_legacy(tmp_path: Path) -> None:
    path = tmp_path / "bad.ASC"
    path.write_text("not a spectrum\n1 2 3\n", encoding="utf-8")

    with pytest.raises(Exception) as old_error:
        legacy_read_asc(path)
    with pytest.raises(Exception) as new_error:
        new_read_asc(path)

    assert isinstance(new_error.value, NewAscFormatError)
    assert type(old_error.value).__name__ == type(new_error.value).__name__
    assert str(old_error.value) == str(new_error.value)


# --------------------------------------------------------------------------
# BES3T reader
# --------------------------------------------------------------------------
def test_bes3t_reader_matches_legacy_on_valid_pair(tmp_path: Path) -> None:
    dsc, _dta = _write_bes3t(tmp_path)

    old = legacy_read_bes3t(dsc)
    new = new_read_bes3t(dsc)

    _compare_import_results(old, new)
    assert new.source_hashes["descriptor"]
    assert new.source_hashes["data"]
    assert new.format_metadata["binary"]["numpy_dtype"] == ">f8"
    np.testing.assert_array_equal(
        new.data["intensity"].to_numpy(),
        [1.5, -2.0, 3.25, 0.125, 9.0],
    )


def test_bes3t_reader_matches_legacy_little_endian_float32(
    tmp_path: Path,
) -> None:
    dsc, _dta = _write_bes3t(tmp_path, bseq="LIT", irfmt="F")

    old = legacy_read_bes3t(dsc)
    new = new_read_bes3t(dsc)

    _compare_import_results(old, new)
    assert new.format_metadata["binary"]["numpy_dtype"] == "<f4"
    assert new.format_metadata["binary"]["byte_order"] == "LIT"
    np.testing.assert_array_equal(
        new.data["intensity"].to_numpy(),
        old.data["intensity"].to_numpy(),
    )


def test_bes3t_reader_matches_legacy_on_real_m0_data() -> None:
    record = BASELINE["datasets"]["bes3t_real"]
    dsc = PROJECT_ROOT / record["relative_path"]
    dta = PROJECT_ROOT / record["companion_relative_path"]
    if not dsc.is_file() or not dta.is_file():
        pytest.skip(f"local BES3T baseline not present: {dsc}")

    old = legacy_read_bes3t(dsc)
    new = new_read_bes3t(dsc)

    _compare_import_results(old, new)
    assert new.sha256 == record["sha256"]
    assert new.source_hashes == record["source_hashes"]
    assert len(new.data) == record["n_points"]


def test_bes3t_reader_preserves_error_codes(tmp_path: Path) -> None:
    dsc, _dta = _write_bes3t(tmp_path, write_companion=False)

    with pytest.raises(Exception) as old_error:
        legacy_read_bes3t(dsc)
    with pytest.raises(Exception) as new_error:
        new_read_bes3t(dsc)
    assert isinstance(new_error.value, NewBes3tError)
    assert new_error.value.code == old_error.value.code == "bes3t_companion_missing"
    assert new_error.value.context == old_error.value.context


def test_bes3t_reader_rejects_unsupported_axis_units(tmp_path: Path) -> None:
    dsc, _dta = _write_bes3t(tmp_path, xuni="T")

    with pytest.raises(Exception) as old_error:
        legacy_read_bes3t(dsc)
    with pytest.raises(Exception) as new_error:
        new_read_bes3t(dsc)

    assert new_error.value.code == old_error.value.code
    assert new_error.value.code == "bes3t_unsupported_units"


def test_bes3t_reader_rejects_truncated_payload(tmp_path: Path) -> None:
    dsc, _dta = _write_bes3t(tmp_path, payload=b"\x00\x00")

    with pytest.raises(Exception) as old_error:
        legacy_read_bes3t(dsc)
    with pytest.raises(Exception) as new_error:
        new_read_bes3t(dsc)

    assert new_error.value.code == old_error.value.code == "bes3t_truncated"


# --------------------------------------------------------------------------
# EPR processing implementation
# --------------------------------------------------------------------------
def _processing_data() -> tuple[np.ndarray, np.ndarray]:
    field = np.linspace(0.0, 200.0, 201)
    intensity = 2.0 * field + 5.0 + 80.0 * np.exp(
        -((field - 100.0) / 4.0) ** 2
    )
    return field, intensity


def test_independent_baseline_matches_legacy_fit_and_warnings() -> None:
    field, intensity = _processing_data()
    old_spec = LegacyLinearBaselineSpec(
        LegacyBaselineWindow(0.0, 4.0),
        LegacyBaselineWindow(196.0, 200.0),
    )
    new_spec = NewLinearBaselineSpec(
        NewBaselineWindow(0.0, 4.0),
        NewBaselineWindow(196.0, 200.0),
    )

    old_fit, old_warnings = legacy_fit_linear_baseline(
        field, intensity, old_spec
    )
    new_fit, new_warnings = new_fit_linear_baseline(
        field, intensity, new_spec
    )

    assert new_fit.as_dict() == old_fit.as_dict()
    assert [warning.as_dict() for warning in new_warnings] == [
        warning.as_dict() for warning in old_warnings
    ]
    np.testing.assert_array_equal(
        intensity - (new_fit.slope * field + new_fit.intercept),
        intensity - (old_fit.slope * field + old_fit.intercept),
    )


def test_independent_savgol_matches_legacy_output_and_diagnostics() -> None:
    _field, intensity = _processing_data()
    old_spec = LegacySavgolSpec(11, 3)
    new_spec = NewSavgolSpec(11, 3)

    old_output, old_diagnostics = legacy_smooth_savgol(intensity, old_spec)
    new_output, new_diagnostics = new_smooth_savgol(intensity, new_spec)

    np.testing.assert_array_equal(new_output, old_output)
    assert new_diagnostics.as_dict() == old_diagnostics.as_dict()


@pytest.mark.parametrize(
    "spec",
    [
        (2, 1),
        (4, 2),
        (5, 5),
        (5, -1),
        (11, 2),
        (5, 1, 1),
        (5, 1, 0, "wrap"),
    ],
)
def test_independent_savgol_validation_codes_match(spec) -> None:
    window_length, polyorder, *rest = spec
    deriv = rest[0] if rest else 0
    mode = rest[1] if len(rest) > 1 else "interp"
    old_spec = LegacySavgolSpec(window_length, polyorder, deriv, mode)
    new_spec = NewSavgolSpec(window_length, polyorder, deriv, mode)

    with pytest.raises(Exception) as old_error:
        legacy_validate_savgol_spec(old_spec, 9 if window_length > 9 else 101)
    with pytest.raises(Exception) as new_error:
        new_validate_savgol_spec(new_spec, 9 if window_length > 9 else 101)
    assert new_error.value.code == old_error.value.code


def test_independent_baseline_decreasing_axis_matches_legacy() -> None:
    field, intensity = _processing_data()
    field = field[::-1].copy()
    intensity = intensity[::-1].copy()
    old_spec = LegacyLinearBaselineSpec(
        LegacyBaselineWindow(0.0, 4.0),
        LegacyBaselineWindow(196.0, 200.0),
    )
    new_spec = NewLinearBaselineSpec(
        NewBaselineWindow(0.0, 4.0),
        NewBaselineWindow(196.0, 200.0),
    )

    old_fit, _ = legacy_fit_linear_baseline(field, intensity, old_spec)
    new_fit, _ = new_fit_linear_baseline(field, intensity, new_spec)

    assert new_fit.as_dict() == old_fit.as_dict()


def test_independent_processing_does_not_import_legacy_module() -> None:
    # This catches accidental import-time coupling; the test bodies above
    # import both implementations explicitly for comparison.
    import subprocess
    import sys

    code = (
        f"import sys; sys.path.insert(0, {str(PROJECT_ROOT / 'src')!r})\n"
        "import spectralab.techniques.epr.processing_impl\n"
        "print(any(name == 'epr_workflow' or name.startswith('epr_workflow.')\n"
        "          for name in sys.modules))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"
