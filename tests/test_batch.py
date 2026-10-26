"""Tests for batch processing of ASC files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from epr_workflow.plot_asc import discover_asc_files, main

HEADER = "     index           Field [G]        Intensity []\n\n"


def asc_text(rows: list[str]) -> str:
    return HEADER + "\n".join(rows) + "\n"


def write_asc(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


VALID_ROWS = [
    "1 3280 400.088",
    "2 3280.1 272.312",
    "3 3280.2 364.536",
    "4 3280.29 -29.2404",
]


def make_sample(path: Path, offset: float = 0.0) -> Path:
    rows = [
        f"{i + 1} {3280 + i / 10 + offset:.1f} {100 + i:.1f}" for i in range(4)
    ]
    return write_asc(path, asc_text(rows))


def run_batch(input_dir: Path, output_dir: Path, *extra: str) -> int:
    return main(
        [
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            *extra,
        ]
    )


def read_summary(output_dir: Path) -> dict:
    return json.loads(
        (output_dir / "logs" / "batch_summary.json").read_text(encoding="utf-8")
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# 1. Multiple valid files
# --------------------------------------------------------------------------
def test_batch_processes_multiple_valid_files(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    make_sample(input_dir / "sample_a.ASC")
    make_sample(input_dir / "sample_b.ASC", offset=5.0)

    assert run_batch(input_dir, output_dir) == 0

    for stem in ("sample_a", "sample_b"):
        assert (output_dir / "figures" / f"{stem}_raw.png").exists()
        assert (output_dir / "tables" / f"{stem}_raw.csv").exists()
        assert (output_dir / "logs" / f"{stem}_metadata.json").exists()

    summary = read_summary(output_dir)
    assert summary["batch"]["files_discovered"] == 2
    assert summary["batch"]["files_succeeded"] == 2
    assert summary["batch"]["files_failed"] == 0
    assert summary["batch"]["overall_status"] == "success"
    assert all(f["status"] == "success" for f in summary["files"])
    assert summary["files"][0]["outputs"]["csv"].endswith("sample_a_raw.csv")


# --------------------------------------------------------------------------
# 2-3. Ordering and case-insensitive extensions
# --------------------------------------------------------------------------
def test_batch_order_is_deterministic(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    for name in ("c.ASC", "A.ASC", "b.ASC"):
        make_sample(input_dir / name)

    assert run_batch(input_dir, tmp_path / "out1") == 0
    assert run_batch(input_dir, tmp_path / "out2") == 0

    first = [f["source_file"] for f in read_summary(tmp_path / "out1")["files"]]
    second = [f["source_file"] for f in read_summary(tmp_path / "out2")["files"]]
    assert first == second == ["A.ASC", "b.ASC", "c.ASC"]


def test_batch_extension_is_case_insensitive(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    make_sample(input_dir / "one.asc")
    make_sample(input_dir / "two.ASC")
    make_sample(input_dir / "three.Asc")

    assert run_batch(input_dir, tmp_path / "out") == 0

    summary = read_summary(tmp_path / "out")
    assert summary["batch"]["files_discovered"] == 3
    assert summary["batch"]["files_succeeded"] == 3


# --------------------------------------------------------------------------
# 4-6. Failure isolation and discovery errors
# --------------------------------------------------------------------------
def test_batch_continues_after_one_file_fails(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    make_sample(input_dir / "good1.ASC")
    write_asc(input_dir / "broken.ASC", "not a valid ASC file\n1 2 3\n")
    make_sample(input_dir / "good2.ASC")

    assert run_batch(input_dir, output_dir) == 1

    summary = read_summary(output_dir)
    statuses = {f["source_file"]: f["status"] for f in summary["files"]}
    assert statuses == {
        "broken.ASC": "failed",
        "good1.ASC": "success",
        "good2.ASC": "success",
    }
    assert summary["batch"]["files_succeeded"] == 2
    assert summary["batch"]["files_failed"] == 1
    assert summary["batch"]["overall_status"] == "partial_failure"
    assert (output_dir / "tables" / "good1_raw.csv").exists()
    assert (output_dir / "tables" / "good2_raw.csv").exists()
    broken = next(f for f in summary["files"] if f["source_file"] == "broken.ASC")
    assert "AscFormatError" in broken["error"]
    assert broken["outputs"] == {}


def test_empty_input_directory_reports_error(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    input_dir.mkdir()
    (input_dir / "notes.txt").write_text("no asc here", encoding="utf-8")

    assert run_batch(input_dir, tmp_path / "out") == 1

    summary = read_summary(tmp_path / "out")
    assert summary["batch"]["files_discovered"] == 0
    assert summary["batch"]["overall_status"] == "failed"
    assert any("No .ASC files" in error for error in summary["batch"]["errors"])


def test_missing_input_directory_reports_error(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"

    assert run_batch(missing, tmp_path / "out") == 1

    summary = read_summary(tmp_path / "out")
    assert summary["batch"]["files_discovered"] == 0
    assert any("does not exist" in error for error in summary["batch"]["errors"])


# --------------------------------------------------------------------------
# 7. Overwrite protection
# --------------------------------------------------------------------------
def test_existing_outputs_are_not_overwritten_silently(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    make_sample(input_dir / "a.ASC")
    make_sample(input_dir / "b.ASC")

    existing_csv = output_dir / "tables" / "a_raw.csv"
    existing_csv.parent.mkdir(parents=True)
    existing_csv.write_text("sentinel\n", encoding="utf-8")

    assert run_batch(input_dir, output_dir) == 1
    assert existing_csv.read_text(encoding="utf-8") == "sentinel\n"

    summary = read_summary(output_dir)
    failed = next(f for f in summary["files"] if f["source_file"] == "a.ASC")
    assert failed["status"] == "failed"
    assert "already exist" in failed["error"]

    # Explicit --overwrite replaces the file.
    assert run_batch(input_dir, output_dir, "--overwrite") == 0
    assert existing_csv.read_text(encoding="utf-8").startswith("index,field_G,intensity")


def test_existing_batch_summary_requires_overwrite(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    make_sample(input_dir / "a.ASC")

    assert run_batch(input_dir, output_dir) == 0
    summary_path = output_dir / "logs" / "batch_summary.json"
    first_summary = summary_path.read_text(encoding="utf-8")

    assert run_batch(input_dir, output_dir) == 1
    assert summary_path.read_text(encoding="utf-8") == first_summary
    assert run_batch(input_dir, output_dir, "--overwrite") == 0


def test_single_file_mode_also_protects_outputs(tmp_path: Path) -> None:
    source = make_sample(tmp_path / "one.ASC")
    figure = tmp_path / "f.png"
    csv_file = tmp_path / "f.csv"
    json_file = tmp_path / "f.json"
    args = [str(source), "--figure", str(figure), "--csv", str(csv_file), "--json", str(json_file)]

    assert main(args) == 0
    assert main(args) == 1
    assert main(args + ["--overwrite"]) == 0


# --------------------------------------------------------------------------
# 8. Output collision prevention
# --------------------------------------------------------------------------
def test_output_basename_collision_is_prevented(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    make_sample(input_dir / "a_b" / "C.ASC")
    make_sample(input_dir / "a" / "b_C.ASC")

    assert run_batch(input_dir, output_dir, "--recursive") == 1

    summary = read_summary(output_dir)
    assert summary["batch"]["files_discovered"] == 2
    assert summary["batch"]["files_failed"] == 2
    assert all("collision" in f["error"] for f in summary["files"])
    assert not (output_dir / "tables" / "a_b_C_raw.csv").exists()


def test_recursive_is_opt_in(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    make_sample(input_dir / "top.ASC")
    make_sample(input_dir / "sub" / "nested.ASC")

    assert len(discover_asc_files(input_dir)) == 1
    assert len(discover_asc_files(input_dir, recursive=True)) == 2

    assert run_batch(input_dir, tmp_path / "out_flat") == 0
    assert read_summary(tmp_path / "out_flat")["batch"]["files_discovered"] == 1

    assert run_batch(input_dir, tmp_path / "out_rec", "--recursive") == 0
    summary = read_summary(tmp_path / "out_rec")
    assert summary["batch"]["files_discovered"] == 2
    assert (tmp_path / "out_rec" / "tables" / "sub_nested_raw.csv").exists()


# --------------------------------------------------------------------------
# 9. Summary counts and per-file statuses
# --------------------------------------------------------------------------
def test_batch_summary_distinguishes_warnings_from_failures(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    make_sample(input_dir / "clean.ASC")
    # Index gap -> validation warning, not a failure.
    write_asc(
        input_dir / "gapped.ASC",
        asc_text(["1 3280 10", "2 3280.1 11", "4 3280.2 12", "5 3280.3 13"]),
    )
    write_asc(input_dir / "bad.ASC", "wrong header here\n")

    assert run_batch(input_dir, output_dir) == 1

    summary = read_summary(output_dir)
    by_name = {f["source_file"]: f for f in summary["files"]}
    assert by_name["clean.ASC"]["status"] == "success"
    assert by_name["gapped.ASC"]["status"] == "success_with_warnings"
    assert any("not consecutive" in w for w in by_name["gapped.ASC"]["validation_warnings"])
    assert by_name["bad.ASC"]["status"] == "failed"
    assert summary["batch"]["files_succeeded"] == 1
    assert summary["batch"]["files_succeeded_with_warnings"] == 1
    assert summary["batch"]["files_failed"] == 1
    assert summary["batch"]["overall_status"] == "partial_failure"


# --------------------------------------------------------------------------
# 10-11. Source integrity and absence of signal processing
# --------------------------------------------------------------------------
def test_batch_preserves_source_files_and_values(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    source = make_sample(input_dir / "keep.ASC")
    before_hash = sha256(source)

    assert run_batch(input_dir, output_dir) == 0

    assert sha256(source) == before_hash
    summary = read_summary(output_dir)
    record = summary["files"][0]
    assert record["source_sha256_before"] == before_hash
    assert record["source_sha256_after"] == before_hash
    assert record["source_unchanged"] is True

    exported = pd.read_csv(output_dir / "tables" / "keep_raw.csv")
    expected = np.array(
        [[1, 3280.0, 100.0], [2, 3280.1, 101.0], [3, 3280.2, 102.0], [4, 3280.3, 103.0]]
    )
    np.testing.assert_array_equal(exported.to_numpy(), expected)

    metadata = json.loads(
        (output_dir / "logs" / "keep_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["processing"]["applied_in_this_run"] == {
        "smoothing": False,
        "baseline_correction": False,
        "normalisation": False,
        "field_axis_reversal": False,
    }
    assert metadata["raw_file_unchanged"] is True


def test_batch_does_not_sort_rows(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    # Index gap keeps the original row order observable.
    write_asc(
        input_dir / "order.ASC",
        asc_text(["10 3280 5", "20 3280.1 6", "40 3280.2 7", "50 3280.3 8"]),
    )

    assert run_batch(input_dir, output_dir) == 0

    exported = pd.read_csv(output_dir / "tables" / "order_raw.csv")
    assert exported["index"].tolist() == [10, 20, 40, 50]
    assert exported["field_G"].tolist() == [3280.0, 3280.1, 3280.2, 3280.3]


def test_batch_keeps_numeric_values_exact(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    output_dir = tmp_path / "out"
    rows = ["1 3280.123456 400.088", "2 3280.223456 272.312",
            "3 3280.323456 -29.2404"]
    source = write_asc(input_dir / "exact.ASC", asc_text(rows))
    before_hash = sha256(source)

    assert run_batch(input_dir, output_dir) == 0

    exported = pd.read_csv(output_dir / "tables" / "exact_raw.csv")
    assert exported["field_G"].tolist() == [3280.123456, 3280.223456, 3280.323456]
    assert exported["intensity"].tolist() == [400.088, 272.312, -29.2404]
    assert sha256(source) == before_hash


# --------------------------------------------------------------------------
# 12. Single-file compatibility
# --------------------------------------------------------------------------
def test_single_file_mode_still_works(tmp_path: Path) -> None:
    source = make_sample(tmp_path / "single.ASC")
    figure = tmp_path / "single.png"
    csv_file = tmp_path / "single.csv"
    json_file = tmp_path / "single.json"

    assert main(
        [
            str(source),
            "--figure",
            str(figure),
            "--csv",
            str(csv_file),
            "--json",
            str(json_file),
        ]
    ) == 0
    assert figure.exists() and csv_file.exists() and json_file.exists()
    assert json.loads(json_file.read_text(encoding="utf-8"))["data"]["valid_points"] == 4


def test_batch_rejects_show_option(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        run_batch(tmp_path / "raw", tmp_path / "out", "--show")
