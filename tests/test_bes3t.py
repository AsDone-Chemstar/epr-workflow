"""Tests for strict BES3T (.DSC/.DTA) import and integration."""

from __future__ import annotations

import hashlib
import json
import sys

import numpy as np
import pandas as pd
import pytest

from epr_workflow.bes3t import (
    Bes3tDataError,
    Bes3tError,
    Bes3tFormatError,
    find_companion_dta,
    read_bes3t,
)
from epr_workflow.plot_asc import (
    PROJECT_ROOT,
    build_metadata,
    combine_source_hashes,
    main,
    read_dataset,
)
from epr_workflow.preprocessing import (
    BaselineWindow,
    LinearBaselineSpec,
    PreprocessingSession,
)
from epr_workflow.processed_export import export_processed

_DTYPE_CODES = {
    "C": "i1",
    "S": "i2",
    "I": "i4",
    "F": "f4",
    "D": "f8",
}

HEADER = "     index           Field [G]        Intensity []\n\n"


def sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_bes3t(
    tmp_path,
    values=(1.5, -2.0, 3.25, 0.125),
    *,
    name: str = "sample",
    dsc_suffix: str = ".DSC",
    dta_suffix: str = ".DTA",
    xmin: float = 3300.0,
    xwid: float = 3.0,
    xpts: int | None = None,
    ypts: int | None = None,
    zpts: int | None = None,
    ytyp: str = "NODATA",
    ztyp: str = "NODATA",
    irfmt: str = "D",
    bseq: str = "BIG",
    ikkf: str = "REAL",
    xtyp: str = "IDX",
    xuni: str = "G",
    omit: tuple[str, ...] = (),
    dsc_extra: tuple[str, ...] = (),
    payload: bytes | None = None,
):
    """Create a minimally valid synthetic BES3T pair in ``tmp_path``."""
    values = list(values)
    if xpts is None:
        xpts = len(values)
    if payload is None:
        dtype = np.dtype((">" if bseq == "BIG" else "<") + _DTYPE_CODES[irfmt])
        payload = np.asarray(values, dtype=dtype).tobytes()

    def optional(key: str, value) -> list[str]:
        if key in omit or value is None:
            return []
        return [f"{key}\t{value}"]

    lines = [
        "#DESC\t1.2 * DESCRIPTOR INFORMATION ***********************",
        "*",
        "DSRC\tEXP",
        *optional("BSEQ", bseq),
        *optional("IKKF", ikkf),
        *optional("XTYP", xtyp),
        "YTYP\t" + ytyp,
        "ZTYP\t" + ztyp,
        *optional("IRFMT", irfmt),
        *optional("XPTS", xpts),
        *optional("YPTS", ypts),
        *optional("ZPTS", zpts),
        *optional("XMIN", xmin),
        *optional("XWID", xwid),
        "XNAM\t'Field'",
        *optional("XUNI", repr(xuni)),
        "IRNAM\t'Intensity'",
        "IRUNI\t''",
        "TITL\t'synthetic'",
        *dsc_extra,
        "#SPL\t1.2 * STANDARD PARAMETER LAYER",
        "EXPT\tCW",
        "#DSL\t1.0 * DEVICE SPECIFIC LAYER",
        ".DVC\tfieldCtrl, 1.0",
        "CenterField\t3301.50 G",
    ]
    dsc = tmp_path / f"{name}{dsc_suffix}"
    dta = tmp_path / f"{name}{dta_suffix}"
    dsc.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    dta.write_bytes(payload)
    return dsc, dta


def write_asc(path, n: int = 4):
    rows = [
        f"{i + 1} {3300 + i / 10} {100 + i}"
        for i in range(n)
    ]
    path.write_text(
        HEADER + "\n".join(rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


# --------------------------------------------------------------------------
# Valid datasets and binary decoding
# --------------------------------------------------------------------------
def test_valid_big_endian_float64_dataset(tmp_path) -> None:
    dsc, dta = write_bes3t(tmp_path)
    before_dsc = sha256(dsc)
    before_dta = sha256(dta)

    result = read_bes3t(dsc)

    assert result.source_format == "BES3T"
    assert result.source == dsc
    assert len(result.data) == 4
    assert list(result.data.columns) == ["index", "field_G", "intensity"]
    np.testing.assert_array_equal(
        result.data["field_G"].to_numpy(), [3300.0, 3301.0, 3302.0, 3303.0]
    )
    np.testing.assert_array_equal(
        result.data["intensity"].to_numpy(), [1.5, -2.0, 3.25, 0.125]
    )
    assert result.field_order == "strictly increasing"
    assert result.format_metadata["binary"]["numpy_dtype"] == ">f8"
    assert result.format_metadata["binary"]["byte_order"] == "BIG"
    assert result.format_metadata["axis"]["endpoint_included"] is True
    assert result.format_metadata["axis"]["construction"] == (
        "linspace(XMIN, XMIN + XWID, XPTS)"
    )
    assert result.source_hashes["descriptor"] == before_dsc
    assert result.source_hashes["data"] == before_dta
    assert result.sha256 == combine_source_hashes(
        "BES3T", result.source_hashes
    )
    assert sha256(dsc) == before_dsc
    assert sha256(dta) == before_dta


def test_little_endian_float32_values_and_axis(tmp_path) -> None:
    dsc, _ = write_bes3t(
        tmp_path,
        values=(1.5, -2.0, 3.25, 0.125),
        irfmt="F",
        bseq="LIT",
        xmin=10.0,
        xwid=3.0,
    )

    result = read_bes3t(dsc)

    assert result.format_metadata["binary"]["numpy_dtype"] == "<f4"
    assert result.format_metadata["binary"]["byte_order"] == "LIT"
    np.testing.assert_allclose(
        result.data["intensity"].to_numpy(), [1.5, -2.0, 3.25, 0.125]
    )
    np.testing.assert_allclose(
        result.data["field_G"].to_numpy(), [10.0, 11.0, 12.0, 13.0]
    )


def test_integer_storage_is_decoded_without_changing_values(tmp_path) -> None:
    dsc, _ = write_bes3t(
        tmp_path, values=(1, -2, 3, 4), irfmt="S", bseq="BIG"
    )

    result = read_bes3t(dsc)

    assert result.format_metadata["binary"]["numpy_dtype"] == ">i2"
    np.testing.assert_array_equal(
        result.data["intensity"].to_numpy(), [1.0, -2.0, 3.0, 4.0]
    )
    assert any(
        "Integer intensities" in item
        for item in result.format_assumptions
    )


def test_decreasing_axis_is_preserved_and_warned(tmp_path) -> None:
    dsc, _ = write_bes3t(
        tmp_path,
        values=(1.0, 2.0, 3.0, 4.0),
        xmin=3303.0,
        xwid=-3.0,
    )

    result = read_bes3t(dsc)

    np.testing.assert_array_equal(
        result.data["field_G"].to_numpy(), [3303.0, 3302.0, 3301.0, 3300.0]
    )
    assert result.field_order == "strictly decreasing"
    assert any("negative" in warning for warning in result.warnings)


def test_extension_case_is_handled(tmp_path) -> None:
    dsc, _dta = write_bes3t(
        tmp_path,
        name="case",
        dsc_suffix=".dsc",
        dta_suffix=".DtA",
    )

    assert find_companion_dta(dsc).name == "case.DtA"
    result = read_bes3t(dsc)
    assert len(result.data) == 4


# --------------------------------------------------------------------------
# Pairing and required metadata
# --------------------------------------------------------------------------
def test_missing_dsc_and_missing_dta_are_reported(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        read_bes3t(tmp_path / "missing.DSC")

    dsc, dta = write_bes3t(tmp_path)
    dta.unlink()
    with pytest.raises(Bes3tFormatError) as exc:
        read_bes3t(dsc)
    assert exc.value.code == "bes3t_companion_missing"


def test_mismatched_companion_is_not_paired(tmp_path) -> None:
    dsc, _dta = write_bes3t(tmp_path, name="sample")
    (tmp_path / "sample.DTA").unlink()
    (tmp_path / "other.DTA").write_bytes(b"not it")

    with pytest.raises(Bes3tFormatError) as exc:
        read_bes3t(dsc)

    assert exc.value.code == "bes3t_companion_missing"
    assert "other.DTA" in str(exc.value)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows filesystems are case-insensitive and cannot hold ambiguous companions.",
)
def test_ambiguous_companions_are_rejected(tmp_path) -> None:
    dsc, _dta = write_bes3t(tmp_path, dsc_suffix=".DSC")
    # A second file with the same case-insensitive stem and extension.
    (tmp_path / "sample.dta").write_bytes(b"second")
    (tmp_path / "sample.Dta").write_bytes(b"third")

    with pytest.raises(Bes3tFormatError) as exc:
        find_companion_dta(dsc)

    assert exc.value.code == "bes3t_companion_ambiguous"


def test_missing_required_metadata_is_rejected(tmp_path) -> None:
    dsc, _ = write_bes3t(tmp_path, omit=("IRFMT",))

    with pytest.raises(Bes3tFormatError) as exc:
        read_bes3t(dsc)

    assert exc.value.code == "bes3t_missing_parameter"
    assert exc.value.context["parameter"] == "IRFMT"


@pytest.mark.parametrize(
    "key",
    ("BSEQ", "IKKF", "XTYP", "XPTS", "XMIN", "XWID", "XUNI"),
)
def test_each_required_parameter_is_enforced(tmp_path, key: str) -> None:
    dsc, _ = write_bes3t(tmp_path, omit=(key,))

    with pytest.raises(Bes3tFormatError) as exc:
        read_bes3t(dsc)

    assert exc.value.code == "bes3t_missing_parameter"
    assert exc.value.context["parameter"] == key


def test_malformed_and_duplicate_metadata_are_rejected(tmp_path) -> None:
    dsc, _ = write_bes3t(tmp_path, name="bad", xmin="not-a-number")
    with pytest.raises(Bes3tFormatError) as exc:
        read_bes3t(dsc)
    assert exc.value.code == "bes3t_invalid_parameter"
    assert exc.value.context["parameter"] == "XMIN"

    dsc, _ = write_bes3t(
        tmp_path,
        name="dup",
        dsc_extra=("XMIN\t3301.0",),
    )
    with pytest.raises(Bes3tFormatError) as exc:
        read_bes3t(dsc)
    assert exc.value.code == "bes3t_duplicate_parameter"


def test_descriptor_without_desc_section_is_rejected(tmp_path) -> None:
    dsc = tmp_path / "empty.DSC"
    dsc.write_text("not a descriptor\n", encoding="utf-8")
    (tmp_path / "empty.DTA").write_bytes(b"\0" * 32)

    with pytest.raises(Bes3tFormatError) as exc:
        read_bes3t(dsc)

    assert exc.value.code == "bes3t_descriptor_missing"


# --------------------------------------------------------------------------
# Unsupported layouts
# --------------------------------------------------------------------------
def test_complex_and_multiple_value_layouts_are_rejected(tmp_path) -> None:
    dsc, _ = write_bes3t(
        tmp_path,
        name="complex",
        ikkf="CPLX",
        payload=np.zeros(8, dtype=">f8").tobytes(),
    )
    with pytest.raises(Bes3tDataError) as exc:
        read_bes3t(dsc)
    assert exc.value.code == "bes3t_unsupported_complex"

    dsc, _ = write_bes3t(
        tmp_path, name="multi", ikkf="REAL,REAL"
    )
    with pytest.raises(Bes3tDataError) as exc:
        read_bes3t(dsc)
    assert exc.value.code == "bes3t_unsupported_data_kind"


def test_multidimensional_data_are_rejected(tmp_path) -> None:
    dsc, _ = write_bes3t(
        tmp_path,
        name="twod",
        ypts=2,
        ytyp="IDX",
        payload=np.zeros(8, dtype=">f8").tobytes(),
    )

    with pytest.raises(Bes3tDataError) as exc:
        read_bes3t(dsc)

    assert exc.value.code == "bes3t_unsupported_multidimensional"


def test_unsupported_axis_units_and_formats_are_rejected(tmp_path) -> None:
    cases = [
        ("axis", {"xtyp": "IGD"}, "bes3t_unsupported_axis"),
        ("units", {"xuni": "mT"}, "bes3t_unsupported_units"),
        (
            "format",
            {
                "irfmt": "A",
                "payload": np.zeros(4, dtype=">f8").tobytes(),
            },
            "bes3t_unsupported_format",
        ),
        ("bseq", {"bseq": "MID"}, "bes3t_unsupported_byte_order"),
    ]
    for name, options, code in cases:
        dsc, _ = write_bes3t(tmp_path, name=name, **options)
        with pytest.raises(Bes3tError) as exc:
            read_bes3t(dsc)
        assert exc.value.code == code, name


def test_invalid_axis_is_rejected(tmp_path) -> None:
    dsc, _ = write_bes3t(tmp_path, xwid=0.0)
    with pytest.raises(Bes3tDataError) as exc:
        read_bes3t(dsc)
    assert exc.value.code == "bes3t_axis_invalid"

    dsc, _ = write_bes3t(tmp_path, name="short", values=(1.0, 2.0), xpts=2)
    with pytest.raises(Bes3tDataError) as exc:
        read_bes3t(dsc)
    assert exc.value.code == "bes3t_axis_invalid"


# --------------------------------------------------------------------------
# Payload integrity and non-finite values
# --------------------------------------------------------------------------
def test_truncated_and_trailing_payloads_are_rejected(tmp_path) -> None:
    good = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=">f8").tobytes()
    dsc, _ = write_bes3t(tmp_path, name="short", payload=good[:-8])
    with pytest.raises(Bes3tDataError) as exc:
        read_bes3t(dsc)
    assert exc.value.code == "bes3t_truncated"
    assert exc.value.context["expected_bytes"] == 32
    assert exc.value.context["actual_bytes"] == 24

    dsc, _ = write_bes3t(tmp_path, name="long", payload=good + b"\x00")
    with pytest.raises(Bes3tDataError) as exc:
        read_bes3t(dsc)
    assert exc.value.code == "bes3t_trailing_bytes"
    assert exc.value.context["extra_bytes"] == 1


def test_nonfinite_payload_is_rejected(tmp_path) -> None:
    values = np.asarray([1.0, np.nan, 3.0, 4.0], dtype=">f8")
    dsc, _ = write_bes3t(tmp_path, payload=values.tobytes())
    with pytest.raises(Bes3tDataError) as exc:
        read_bes3t(dsc)
    assert exc.value.code == "bes3t_nonfinite"
    assert exc.value.context["index"] == 1


def test_dta_is_not_an_entry_point(tmp_path) -> None:
    _dsc, dta = write_bes3t(tmp_path)
    with pytest.raises(ValueError) as exc:
        read_dataset(dta)
    assert ".DSC" in str(exc.value)


# --------------------------------------------------------------------------
# Metadata and provenance
# --------------------------------------------------------------------------
def test_metadata_includes_sources_axis_and_binary_details(tmp_path) -> None:
    dsc, dta = write_bes3t(tmp_path)
    result = read_bes3t(dsc)
    before_dsc = result.source_hashes["descriptor"]
    before_dta = result.source_hashes["data"]

    metadata = build_metadata(
        result,
        raw_file_unchanged=True,
        source_hashes_after=result.source_hashes,
    )

    assert metadata["source_format"] == "BES3T"
    assert metadata["sha256"] == result.sha256
    assert metadata["sha256_definition"].startswith("SHA-256 of b'BES3T:'")
    assert {entry["role"] for entry in metadata["source_files"]} == {
        "descriptor",
        "data",
    }
    by_role = {entry["role"]: entry for entry in metadata["source_files"]}
    assert by_role["descriptor"]["sha256"] == before_dsc
    assert by_role["data"]["sha256"] == before_dta
    assert by_role["descriptor"]["unchanged"] is True
    assert by_role["data"]["unchanged"] is True
    assert metadata["format_metadata"]["axis"]["first"] == 3300.0
    assert metadata["format_metadata"]["axis"]["last"] == 3303.0
    assert metadata["format_metadata"]["binary"]["IRFMT"] == "D"
    assert metadata["format_metadata"]["binary"]["byte_order"] == "BIG"
    assert len(metadata["format_metadata"]["descriptor_sections"]) >= 1
    assert metadata["format_metadata"]["inferred_parameters"] == {
        "YPTS": 1,
        "ZPTS": 1,
    }
    assert metadata["raw_file_unchanged"] is True
    # The source files must still be untouched after metadata construction.
    assert sha256(dsc) == before_dsc
    assert sha256(dta) == before_dta


def test_real_xepr_dataset_is_immutable_and_decodes_as_declared() -> None:
    dsc = PROJECT_ROOT / "Test data" / "BSA3mal1h.DSC"
    dta = PROJECT_ROOT / "Test data" / "BSA3mal1h.DTA"
    if not dsc.exists():
        pytest.skip("Real BES3T test dataset is not present in this checkout.")

    before_dsc = sha256(dsc)
    before_dta = sha256(dta)
    result = read_bes3t(dsc)

    assert len(result.data) == 1024
    assert result.data["field_G"].iloc[0] == pytest.approx(3310.0)
    assert result.data["field_G"].iloc[-1] == pytest.approx(3410.0)
    assert result.data["intensity"].iloc[:3].tolist() == [-76.0, -69.0, -67.0]
    assert result.data["intensity"].iloc[-1] == pytest.approx(-84.0)
    assert result.format_metadata["binary"]["numpy_dtype"] == ">f8"
    assert result.format_metadata["binary"]["byte_order"] == "BIG"
    assert result.format_metadata["axis"]["points"] == 1024
    assert sha256(dsc) == before_dsc
    assert sha256(dta) == before_dta


# --------------------------------------------------------------------------
# CLI, batch and processed export
# --------------------------------------------------------------------------
def test_cli_imports_bes3t_and_writes_provenance(tmp_path) -> None:
    dsc, dta = write_bes3t(tmp_path)
    out = tmp_path / "out"
    before_dsc = sha256(dsc)
    before_dta = sha256(dta)

    assert main([str(dsc), "--output-dir", str(out)]) == 0

    frame = pd.read_csv(out / "tables" / "sample_raw.csv")
    assert list(frame.columns) == [
        "index",
        "field_G",
        "intensity",
        "source_format",
    ]
    assert set(frame["source_format"]) == {"BES3T"}
    metadata = json.loads(
        (out / "logs" / "sample_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["source_format"] == "BES3T"
    assert metadata["format_metadata"]["binary"]["IRFMT"] == "D"
    assert {entry["role"] for entry in metadata["source_files"]} == {
        "descriptor",
        "data",
    }
    assert sha256(dsc) == before_dsc
    assert sha256(dta) == before_dta


def test_batch_includes_dsc_but_not_dta(tmp_path) -> None:
    input_dir = tmp_path / "raw"
    input_dir.mkdir()
    dsc, _dta = write_bes3t(input_dir, name="native")
    write_asc(input_dir / "plain.ASC")
    out = tmp_path / "out"

    assert main(["--input-dir", str(input_dir), "--output-dir", str(out)]) == 0

    summary = json.loads(
        (out / "logs" / "batch_summary.json").read_text(encoding="utf-8")
    )
    names = [record["source_file"] for record in summary["files"]]
    assert names == ["native.DSC", "plain.ASC"]
    assert summary["batch"]["files_discovered"] == 2
    assert summary["batch"]["files_succeeded"] == 2
    native = next(r for r in summary["files"] if r["source_file"] == "native.DSC")
    assert native["source_format"] == "BES3T"
    assert set(native["source_files"]) == {"descriptor", "data"}
    assert (out / "tables" / "native_raw.csv").exists()

    plain = next(r for r in summary["files"] if r["source_file"] == "plain.ASC")
    assert set(plain) == {
        "source_file",
        "source_path",
        "output_stem",
        "status",
        "error",
        "validation_warnings",
        "valid_points",
        "field_min_G",
        "field_max_G",
        "field_order",
        "source_sha256_before",
        "source_sha256_after",
        "source_unchanged",
        "outputs",
    }


def test_processed_export_records_bes3t_sources_and_format(tmp_path) -> None:
    xpts = 101
    field = np.linspace(3300.0, 3400.0, xpts)
    intensity = (
        2.0 * field
        + 5.0
        + 500.0 * np.exp(-((field - 3350.0) / 5.0) ** 2)
    )
    dsc, dta = write_bes3t(
        tmp_path,
        values=intensity,
        xpts=xpts,
        xmin=3300.0,
        xwid=100.0,
    )
    imported = read_bes3t(dsc)
    session = PreprocessingSession(
        source=imported.source,
        field_G=imported.data["field_G"].to_numpy(),
        intensity=imported.data["intensity"].to_numpy(),
        source_sha256=imported.sha256,
    )
    applied = session.apply(
        LinearBaselineSpec(
            window_left=BaselineWindow(3300.0, 3305.0),
            window_right=BaselineWindow(3395.0, 3400.0),
        )
    )
    out = tmp_path / "out"
    before_dsc = sha256(dsc)
    before_dta = sha256(dta)

    paths = export_processed(
        import_result=imported, result=applied, output_base=out
    )

    frame = pd.read_csv(paths["csv"])
    assert list(frame.columns) == [
        "index",
        "field_G",
        "intensity_raw",
        "intensity_corrected",
        "baseline_removed",
        "source_format",
    ]
    assert set(frame["source_format"]) == {"BES3T"}
    metadata = json.loads(
        paths["metadata_json"].read_text(encoding="utf-8")
    )
    assert metadata["source_format"] == "BES3T"
    assert metadata["data_kind"] == "baseline_corrected"
    assert {entry["role"] for entry in metadata["source_files"]} == {
        "descriptor",
        "data",
    }
    assert "BES3T" in metadata["assumptions"][0]
    assert sha256(dsc) == before_dsc
    assert sha256(dta) == before_dta
