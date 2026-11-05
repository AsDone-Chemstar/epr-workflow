"""Tests for the generic SpectraLab CLI and batch adapter."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from spectralab.app.batch import (
    BATCH_SCHEMA_ID,
    BATCH_SCHEMA_VERSION,
    output_paths,
    run_batch,
    summary_path,
)
from spectralab.app.cli import main
from spectralab.core.importers import (
    ImportedDataset,
    ImporterRegistry,
    ProbeResult,
)
from spectralab.core.model import (
    Axis1D,
    Provenance,
    Signal1D,
    SourceFile,
    Spectrum1D,
    SpectrumMetadata,
)

HEADER = "     index           Field [G]        Intensity []\n\n"


def _write_asc(path: Path, rows: list[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if rows is None:
        rows = [
            "1 3280.0 10.0",
            "2 3280.1 20.0",
            "3 3280.2 30.0",
        ]
    path.write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summary(output_dir: Path) -> dict:
    path = output_dir / "logs" / "spectralab_batch_summary.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _records(summary: dict) -> list[dict]:
    return summary["files"]


class FakeImporter:
    def __init__(
        self,
        *,
        importer_id: str,
        suffix: str,
        format_id: str = "FAKE",
        technique: str = "test",
        read_spectrum: bool = True,
    ) -> None:
        self.id = importer_id
        self.version = "1"
        self.technique = technique
        self.entry_suffixes = (suffix,)
        self.format_id = format_id
        self.read_spectrum = read_spectrum

    def probe(self, entry: Path) -> ProbeResult:
        return ProbeResult(
            supported=True,
            confidence=1.0,
            format_id=self.format_id,
            technique=self.technique,
            reason="test importer",
        )

    def collect_sources(self, entry: Path):
        return ()

    def read(self, request):
        path = Path(request.entry)
        if not self.read_spectrum:
            raise AssertionError("read should not be called")
        source = SourceFile(
            role="source",
            path=path,
            sha256=_sha256(path),
            size_bytes=path.stat().st_size,
            format_id=self.format_id,
        )
        spectrum = Spectrum1D(
            dataset_id=path.stem,
            axis=Axis1D(
                values=np.array([1.0, 2.0, 3.0]),
                quantity="frequency",
                unit="Hz",
                name="Frequency",
                direction="increasing",
                metadata_source="fake",
            ),
            raw_signal=Signal1D(
                values=np.array([10.0, 20.0, 30.0]),
                semantics="unknown",
                unit=None,
                name="Signal",
                metadata_source="fake",
            ),
            metadata=SpectrumMetadata(technique=self.technique),
            provenance=Provenance(
                source_files=(source,),
                canonical_sha256=source.sha256,
                importer_id=self.id,
                importer_version=self.version,
            ),
        )
        return ImportedDataset(
            spectra=(spectrum,),
            primary_index=0,
            format_id=self.format_id,
            technique=self.technique,
        )


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or ()), list(reader)


# --------------------------------------------------------------------------
# Single-file and format selection
# --------------------------------------------------------------------------
def test_single_file_success_and_raw_exports(tmp_path: Path) -> None:
    source = _write_asc(tmp_path / "sample.ASC")
    output_dir = tmp_path / "out"
    before = _sha256(source)

    assert main([str(source), "--output-dir", str(output_dir)]) == 0

    paths = output_paths(output_dir, "sample")
    assert paths["csv"].exists()
    assert paths["metadata"].exists()
    assert paths["json"].exists()
    assert summary_path(output_dir).exists()
    assert _sha256(source) == before

    fields, rows = _read_csv(paths["csv"])
    assert fields == ["x", "y"]
    assert [row["x"] for row in rows] == ["3280.0", "3280.1", "3280.2"]
    assert [row["y"] for row in rows] == ["10.0", "20.0", "30.0"]

    sidecar = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    document = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert sidecar["schema_id"] == "spectralab.spectrum1d.csv_metadata"
    assert document["schema_id"] == "spectralab.spectrum1d.export"
    assert document["export"]["processing_applied"] == []

    summary = _summary(output_dir)
    assert summary["schema_id"] == BATCH_SCHEMA_ID
    assert summary["schema_version"] == BATCH_SCHEMA_VERSION
    assert summary["batch"]["files_discovered"] == 1
    assert summary["batch"]["files_succeeded"] == 1
    assert summary["batch"]["files_failed"] == 0
    assert summary["batch"]["overall_status"] == "success"
    assert summary["batch"]["processing_applied"] == []
    assert _records(summary)[0]["status"] == "success"
    assert _records(summary)[0]["outputs"]["csv"] == str(paths["csv"].resolve())


def test_explicit_format_id_and_alias(tmp_path: Path) -> None:
    source = _write_asc(tmp_path / "one.ASC")
    output_dir = tmp_path / "out"

    assert main(
        [
            str(source),
            "--output-dir",
            str(output_dir),
            "--format-id",
            "ASC",
        ]
    ) == 0
    assert (output_dir / "tables" / "one.csv").exists()

    second = tmp_path / "two.ASC"
    _write_asc(second)
    assert main(
        [str(second), "--output-dir", str(tmp_path / "out2"), "--format", "ASC"]
    ) == 0


def test_wrong_format_filter_is_reported(tmp_path: Path) -> None:
    source = _write_asc(tmp_path / "one.ASC")
    output_dir = tmp_path / "out"

    assert main(
        [
            str(source),
            "--output-dir",
            str(output_dir),
            "--format-id",
            "BES3T",
        ]
    ) == 1

    summary = _summary(output_dir)
    record = _records(summary)[0]
    assert record["status"] == "failed"
    assert record["error_code"] == "unsupported_format"
    assert summary["batch"]["files_failed"] == 1
    assert not (output_dir / "tables" / "one.csv").exists()


# --------------------------------------------------------------------------
# Multiple inputs, ordering, directories and failures
# --------------------------------------------------------------------------
def test_multiple_inputs_preserve_explicit_order(tmp_path: Path) -> None:
    first = _write_asc(tmp_path / "b.ASC")
    second = _write_asc(tmp_path / "a.ASC")
    output_dir = tmp_path / "out"

    assert main(
        [str(first), str(second), "--output-dir", str(output_dir)]
    ) == 0

    summary = _summary(output_dir)
    assert [item["input_name"] for item in _records(summary)] == [
        "b.ASC",
        "a.ASC",
    ]
    assert summary["batch"]["overall_status"] == "success"


def test_directory_discovery_is_sorted_and_recursive_is_opt_in(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "raw"
    _write_asc(input_dir / "b.ASC")
    _write_asc(input_dir / "a.ASC")
    _write_asc(input_dir / "sub" / "nested.ASC")

    flat_out = tmp_path / "flat"
    assert main([str(input_dir), "--output-dir", str(flat_out)]) == 0
    flat = _summary(flat_out)
    assert [item["input_name"] for item in _records(flat)] == ["a.ASC", "b.ASC"]

    recursive_out = tmp_path / "recursive"
    assert main(
        [
            str(input_dir),
            "--output-dir",
            str(recursive_out),
            "--recursive",
        ]
    ) == 0
    recursive = _summary(recursive_out)
    assert [item["input_name"] for item in _records(recursive)] == [
        "a.ASC",
        "b.ASC",
        "nested.ASC",
    ]


def test_partial_batch_failure_is_isolated(tmp_path: Path) -> None:
    good = _write_asc(tmp_path / "raw" / "good.ASC")
    broken = tmp_path / "raw" / "broken.ASC"
    broken.write_text("not an ASC file\n1 2 3\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    before = _sha256(good), _sha256(broken)

    assert main(
        [str(good), str(broken), "--output-dir", str(output_dir)]
    ) == 1

    summary = _summary(output_dir)
    by_name = {item["input_name"]: item for item in _records(summary)}
    assert by_name["good.ASC"]["status"] == "success"
    assert by_name["broken.ASC"]["status"] == "failed"
    assert by_name["broken.ASC"]["error_code"] == "unsupported_format"
    assert summary["batch"]["overall_status"] == "partial_failure"
    assert summary["batch"]["files_succeeded"] == 1
    assert summary["batch"]["files_failed"] == 1
    assert (output_dir / "tables" / "good.csv").exists()
    assert (_sha256(good), _sha256(broken)) == before


def test_unsupported_explicit_file_is_not_silently_skipped(
    tmp_path: Path,
) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("not a spectrum", encoding="utf-8")
    output_dir = tmp_path / "out"

    assert main([str(source), "--output-dir", str(output_dir)]) == 1

    summary = _summary(output_dir)
    record = _records(summary)[0]
    assert record["status"] == "failed"
    assert record["error_code"] == "unsupported_format"
    assert summary["batch"]["overall_status"] == "failed"


def test_missing_input_and_empty_directory_report_summary(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    missing = tmp_path / "missing.ASC"
    assert main([str(missing), "--output-dir", str(output_dir)]) == 1
    summary = _summary(output_dir)
    assert summary["batch"]["files_discovered"] == 0
    assert any(
        error["code"] == "input_not_found"
        for error in summary["batch"]["errors"]
    )

    empty = tmp_path / "empty"
    empty.mkdir()
    empty_out = tmp_path / "empty_out"
    assert main([str(empty), "--output-dir", str(empty_out)]) == 1
    empty_summary = _summary(empty_out)
    assert any(
        error["code"] == "no_inputs"
        for error in empty_summary["batch"]["errors"]
    )


# --------------------------------------------------------------------------
# Collision, overwrite and source protection
# --------------------------------------------------------------------------
def test_output_collision_is_detected_and_not_renamed(tmp_path: Path) -> None:
    first = _write_asc(tmp_path / "left" / "same.ASC")
    second = _write_asc(tmp_path / "right" / "same.ASC")
    output_dir = tmp_path / "out"

    assert main(
        [str(first), str(second), "--output-dir", str(output_dir)]
    ) == 1

    summary = _summary(output_dir)
    records = _records(summary)
    assert [item["status"] for item in records] == ["failed", "failed"]
    assert all(item["error_code"] == "output_collision" for item in records)
    assert not (output_dir / "tables" / "same.csv").exists()
    assert not (output_dir / "json" / "same.json").exists()


def test_existing_outputs_require_explicit_overwrite(tmp_path: Path) -> None:
    source = _write_asc(tmp_path / "one.ASC")
    output_dir = tmp_path / "out"
    csv_path = output_dir / "tables" / "one.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text("sentinel\n", encoding="utf-8")

    assert main([str(source), "--output-dir", str(output_dir)]) == 1
    assert csv_path.read_text(encoding="utf-8") == "sentinel\n"
    summary = _summary(output_dir)
    assert _records(summary)[0]["error_code"] == "output_exists"
    assert not (output_dir / "tables" / "one_metadata.json").exists()

    assert main(
        [str(source), "--output-dir", str(output_dir), "--overwrite"]
    ) == 0
    assert csv_path.read_text(encoding="utf-8").startswith("x,y\n")


def test_existing_summary_requires_overwrite_and_is_unchanged(
    tmp_path: Path,
) -> None:
    source = _write_asc(tmp_path / "one.ASC")
    output_dir = tmp_path / "out"
    assert main([str(source), "--output-dir", str(output_dir)]) == 0
    summary_file = summary_path(output_dir)
    before = summary_file.read_bytes()

    assert main([str(source), "--output-dir", str(output_dir)]) == 1
    assert summary_file.read_bytes() == before

    assert main(
        [str(source), "--output-dir", str(output_dir), "--overwrite"]
    ) == 0


def test_source_file_is_protected_from_output_collision(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    source = output_dir / "tables" / "protected.csv"
    source.parent.mkdir(parents=True)
    source.write_text("source bytes\n", encoding="utf-8")
    before = source.read_bytes()

    registry = ImporterRegistry()
    registry.register(
        FakeImporter(
            importer_id="test.csv",
            suffix=".csv",
            format_id="CSV",
        )
    )

    result = run_batch(
        [source],
        output_dir,
        overwrite=True,
        registry=registry,
    )

    assert result.exit_code == 1
    assert result.summary["files"][0]["error_code"] == "output_is_source_file"
    assert source.read_bytes() == before
    assert not (output_dir / "tables" / "protected_metadata.json").exists()


# --------------------------------------------------------------------------
# Registry selection, ambiguity and fake formats
# --------------------------------------------------------------------------
def test_ambiguous_importer_is_an_explicit_failure(tmp_path: Path) -> None:
    source = tmp_path / "sample.fake"
    source.write_text("fake\n", encoding="utf-8")
    registry = ImporterRegistry()
    registry.register(
        FakeImporter(
            importer_id="test.first",
            suffix=".fake",
            format_id="FIRST",
            read_spectrum=False,
        )
    )
    registry.register(
        FakeImporter(
            importer_id="test.second",
            suffix=".fake",
            format_id="SECOND",
            read_spectrum=False,
        )
    )

    result = run_batch([source], tmp_path / "out", registry=registry)

    assert result.exit_code == 1
    record = result.summary["files"][0]
    assert record["status"] == "failed"
    assert record["error_code"] == "ambiguous_format"
    assert not (tmp_path / "out" / "tables" / "sample.csv").exists()


def test_registry_selection_by_format_and_technique(tmp_path: Path) -> None:
    source = _write_asc(tmp_path / "select.ASC")
    output_dir = tmp_path / "out"

    result = run_batch(
        [source],
        output_dir,
        format_id="ASC",
        technique="epr",
    )

    assert result.exit_code == 0
    assert result.summary["files"][0]["format_id"] == "ASC"
    assert result.summary["files"][0]["technique"] == "epr"


# --------------------------------------------------------------------------
# Summary and argument errors
# --------------------------------------------------------------------------
def test_summary_records_warnings_and_hashes(tmp_path: Path) -> None:
    source = _write_asc(
        tmp_path / "warn.ASC",
        ["1 3280.0 10.0", "2 3280.1 20.0", "4 3280.2 30.0"],
    )
    output_dir = tmp_path / "out"

    assert main([str(source), "--output-dir", str(output_dir)]) == 0
    summary = _summary(output_dir)
    record = _records(summary)[0]
    assert record["warnings"]
    assert record["canonical_sha256"]
    assert record["source_files"][0]["sha256"]


def test_usage_error_returns_argparse_exit_code(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_cli_module_help_is_available() -> None:
    from spectralab.app.cli import build_parser

    parser = build_parser()
    assert parser.prog == "spectralab"
    assert parser.parse_args(
        ["input.ASC", "--output-dir", "out"]
    ).output_dir == Path("out")
