"""M9 FTIR batch import and generic CLI integration tests."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from spectralab.app.batch import output_paths, run_batch, summary_path
from spectralab.app.cli import main
from spectralab.techniques.ftir import ColumnMapping, FTIRImportOptions


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _csv(path: Path, rows: tuple[tuple[float, float], ...]) -> Path:
    return _write(
        path,
        "\n".join(f"{x},{y}" for x, y in rows) + "\n",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summary(output_dir: Path) -> dict:
    return json.loads(summary_path(output_dir).read_text(encoding="utf-8"))


def _ftir_options(
    *,
    decimal: str = ".",
    delimiter: str | None = None,
    header: bool = False,
    x_column: int | str | None = None,
    y_column: int | str | None = None,
    x_unit: str | None = None,
    y_semantics: str = "unknown",
    acquisition_mode: str = "Unknown",
    atr_correction_status: str = "unknown",
) -> dict:
    return {
        "ftir": FTIRImportOptions(
            mapping=ColumnMapping(
                x=x_column,
                y=y_column,
                header=header,
                delimiter=delimiter,
                decimal=decimal,
                x_unit=x_unit,
                y_semantics=y_semantics,
            ),
            acquisition_mode=acquisition_mode,
            atr_correction_status=atr_correction_status,
        )
    }


def test_multiple_ftir_files_are_imported_in_explicit_order(
    tmp_path: Path,
) -> None:
    first = _csv(tmp_path / "b.csv", ((4000.0, 0.1), (3999.0, 0.2)))
    second = _csv(tmp_path / "a.csv", ((1000.0, 1.0), (1001.0, 1.1)))
    out = tmp_path / "out"

    result = run_batch([first, second], out)

    assert result.exit_code == 0
    summary = _summary(out)
    assert [item["input_name"] for item in summary["files"]] == ["b.csv", "a.csv"]
    assert summary["batch"]["files_succeeded"] == 2
    assert summary["batch"]["files_failed"] == 0
    assert summary["batch"]["overall_status"] == "success"
    assert summary["batch"]["processing_applied"] == []
    for record in summary["files"]:
        assert record["technique"] == "ftir"
        assert record["metadata"]["technique"] == "ftir"
        assert record["warnings"] is not None
        assert record["source_files"][0]["sha256"]
        assert record["source_files"][0]["size_bytes"] > 0

    paths = output_paths(out, "b")
    with paths["csv"].open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["x"] for row in rows] == ["4000.0", "3999.0"]
    assert [row["y"] for row in rows] == ["0.1", "0.2"]


def test_partial_batch_failure_does_not_block_valid_files(
    tmp_path: Path,
) -> None:
    good = _csv(tmp_path / "raw" / "good.csv", ((4000.0, 0.1), (3999.0, 0.2)))
    broken = _write(
        tmp_path / "raw" / "broken.csv",
        "4000,0.1\n3999\n3998,0.3\n",
    )
    out = tmp_path / "out"
    before = _sha256(good), _sha256(broken)

    result = run_batch([good, broken], out)

    assert result.exit_code == 1
    summary = _summary(out)
    by_name = {item["input_name"]: item for item in summary["files"]}
    assert by_name["good.csv"]["status"] == "success"
    assert by_name["broken.csv"]["status"] == "failed"
    assert by_name["broken.csv"]["error_code"] == "ftir_inconsistent_columns"
    assert summary["batch"]["overall_status"] == "partial_failure"
    assert summary["batch"]["files_succeeded"] == 1
    assert summary["batch"]["files_failed"] == 1
    assert output_paths(out, "good")["csv"].exists()
    assert not output_paths(out, "broken")["csv"].exists()
    assert (_sha256(good), _sha256(broken)) == before


def test_directory_discovery_uses_registered_ftir_extensions(
    tmp_path: Path,
) -> None:
    root = tmp_path / "raw"
    _csv(root / "one.csv", ((4000.0, 0.1), (3999.0, 0.2)))
    _write(root / "two.dpt", "4000\t0.1\n3999\t0.2\n")
    _write(root / "notes.md", "not imported\n")
    _write(root / "sub" / "three.txt", "4000 0.1\n3999 0.2\n")

    flat_out = tmp_path / "flat"
    assert run_batch([root], flat_out).exit_code == 0
    flat = _summary(flat_out)
    assert [item["input_name"] for item in flat["files"]] == [
        "one.csv",
        "two.dpt",
    ]

    recursive_out = tmp_path / "recursive"
    assert run_batch([root], recursive_out, recursive=True).exit_code == 0
    recursive = _summary(recursive_out)
    assert [item["input_name"] for item in recursive["files"]] == [
        "one.csv",
        "three.txt",
        "two.dpt",
    ]


def test_output_collision_is_not_resolved_by_renaming(tmp_path: Path) -> None:
    first = _csv(
        tmp_path / "left" / "same.csv",
        ((4000.0, 0.1), (3999.0, 0.2)),
    )
    second = _csv(
        tmp_path / "right" / "same.csv",
        ((4000.0, 0.3), (3999.0, 0.4)),
    )
    out = tmp_path / "out"

    result = run_batch([first, second], out)

    assert result.exit_code == 1
    summary = _summary(out)
    assert all(item["error_code"] == "output_collision" for item in summary["files"])
    assert not output_paths(out, "same")["csv"].exists()
    assert not output_paths(out, "same")["json"].exists()


def test_existing_output_requires_explicit_overwrite(tmp_path: Path) -> None:
    source = _csv(tmp_path / "one.csv", ((4000.0, 0.1), (3999.0, 0.2)))
    out = tmp_path / "out"
    target = output_paths(out, "one")["csv"]
    target.parent.mkdir(parents=True)
    target.write_text("sentinel\n", encoding="utf-8")

    assert run_batch([source], out).exit_code == 1
    assert target.read_text(encoding="utf-8") == "sentinel\n"
    assert _summary(out)["files"][0]["error_code"] == "output_exists"

    assert run_batch([source], out, overwrite=True).exit_code == 0
    assert target.read_text(encoding="utf-8").startswith("x,y\n")


def test_batch_options_are_passed_to_ftir_importer(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "header.csv",
        "index;Wavenumber;Absorbance\n"
        "1;1000,5;0,1\n"
        "2;1001,0;0,2\n",
    )
    out = tmp_path / "out"
    options = _ftir_options(
        delimiter="semicolon",
        decimal="comma",
        header=True,
        x_column=1,
        y_column=2,
        x_unit="cm^-1",
        y_semantics="absorbance",
        acquisition_mode="ATR",
        atr_correction_status="not_applied",
    )

    result = run_batch([source], out, options=options)

    assert result.exit_code == 0
    summary = _summary(out)
    record = summary["files"][0]
    assert record["metadata"]["acquisition"]["mode"] == "ATR"
    assert record["metadata"]["acquisition"]["atr_correction_status"] == "not_applied"
    assert set(record["metadata"]["technique_metadata"]) == {
        "format_id",
        "column_mapping",
        "header_fields",
    }
    assert record["import_options"]["mapping"]["decimal"] == ","
    assert summary["batch"]["import_options"]["ftir"]["acquisition_mode"] == "ATR"

    with output_paths(out, "header")["csv"].open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert [row["x"] for row in rows] == ["1000.5", "1001.0"]
    assert [row["y"] for row in rows] == ["0.1", "0.2"]


def test_cli_exposes_explicit_ftir_options(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "cli.csv",
        "index,Wavenumber,Absorbance\n1,4000,0.1\n2,3999,0.2\n",
    )
    out = tmp_path / "out"

    code = main(
        [
            str(source),
            "--output-dir",
            str(out),
            "--x-column",
            "1",
            "--y-column",
            "2",
            "--header",
            "--x-unit",
            "cm^-1",
            "--y-semantics",
            "absorbance",
            "--acquisition-mode",
            "ATR",
            "--atr-correction",
            "unknown",
        ]
    )

    assert code == 0
    record = _summary(out)["files"][0]
    assert record["technique"] == "ftir"
    assert record["metadata"]["acquisition"]["mode"] == "ATR"
    exported = json.loads(
        output_paths(out, "cli")["json"].read_text(encoding="utf-8")
    )
    assert exported["axis"]["quantity"] == "wavenumber"
    assert exported["axis"]["unit"] == "cm^-1"
    assert exported["signal"]["semantics"] == "absorbance"


def test_cli_invalid_ftir_option_returns_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _write(tmp_path / "one.csv", "4000,0.1\n3999,0.2\n")
    code = main(
        [
            str(source),
            "--output-dir",
            str(tmp_path / "out"),
            "--x-unit",
            "nm",
        ]
    )
    assert code == 2
    captured = capsys.readouterr()
    assert "ftir_unsupported_axis_unit" in captured.err
    assert not (tmp_path / "out").exists()


def test_batch_source_files_are_immutable(tmp_path: Path) -> None:
    source = _csv(tmp_path / "keep.csv", ((4000.0, 0.1), (3999.0, 0.2)))
    before = _sha256(source)

    assert run_batch([source], tmp_path / "out").exit_code == 0

    assert _sha256(source) == before
    record = _summary(tmp_path / "out")["files"][0]
    assert record["source_files"][0]["sha256"] == before
    assert record["canonical_sha256"] == before


def test_batch_preserves_decreasing_order_in_csv_output(tmp_path: Path) -> None:
    source = _csv(
        tmp_path / "decreasing.csv",
        ((4000.0, 0.1), (3999.0, 0.2), (3998.0, 0.3)),
    )
    out = tmp_path / "out"
    assert run_batch([source], out).exit_code == 0

    exported = np.genfromtxt(
        output_paths(out, "decreasing")["csv"],
        delimiter=",",
        names=True,
    )
    np.testing.assert_array_equal(
        exported["x"], np.array([4000.0, 3999.0, 3998.0])
    )
    np.testing.assert_array_equal(
        exported["y"], np.array([0.1, 0.2, 0.3])
    )


def test_epr_batch_behavior_remains_available(tmp_path: Path) -> None:
    header = "     index           Field [G]        Intensity []\n\n"
    source = _write(
        tmp_path / "epr.ASC",
        header + "1 3280.0 10.0\n2 3280.1 20.0\n3 3280.2 30.0\n",
    )
    out = tmp_path / "out"

    assert run_batch([source], out).exit_code == 0
    record = _summary(out)["files"][0]
    assert record["technique"] == "epr"
    assert record["format_id"] == "ASC"
    assert record["metadata"]["technique"] == "epr"


def test_ftir_options_with_epr_file_fail_explicitly(tmp_path: Path) -> None:
    header = "     index           Field [G]        Intensity []\n\n"
    source = _write(
        tmp_path / "epr.ASC",
        header + "1 3280.0 10.0\n2 3280.1 20.0\n3 3280.2 30.0\n",
    )
    options = _ftir_options(x_unit="cm^-1")

    result = run_batch([source], tmp_path / "out", options=options)

    assert result.exit_code == 1
    record = result.summary["files"][0]
    assert record["status"] == "failed"
    assert record["error_code"] == "unsupported_import_option"
