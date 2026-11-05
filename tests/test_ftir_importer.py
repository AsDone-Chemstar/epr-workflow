"""M9 generic FTIR CSV/TXT/DPT importer tests."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from spectralab.core.errors import ImportFailure
from spectralab.core.importers import (
    ImportRequest,
    ImporterRegistry,
    source_file,
    source_file_from_bytes,
)
from spectralab.techniques.ftir.importers import _generic
from spectralab.techniques.ftir import (
    ColumnMapping,
    FTIRImportOptions,
    GenericCSVImporter,
    GenericTXTImporter,
    parse_column_reference,
    register_ftir_importers,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, text: str, *, encoding: str = "utf-8") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=encoding, newline="\n")
    return path


def _registry() -> ImporterRegistry:
    registry = ImporterRegistry()
    register_ftir_importers(registry)
    return registry


def _read(
    path: Path,
    *,
    mapping: ColumnMapping | None = None,
    acquisition_mode: str = "Unknown",
    atr_correction_status: str = "unknown",
    **option_kwargs,
):
    options = FTIRImportOptions(
        mapping=mapping or ColumnMapping(),
        acquisition_mode=acquisition_mode,
        atr_correction_status=atr_correction_status,
        **option_kwargs,
    )
    return _registry().read(path, options={"ftir": options})


def _csv_rows(rows: list[str]) -> str:
    return "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# Format, delimiter, decimal and mapping
# ---------------------------------------------------------------------------
def test_comma_csv_preserves_decreasing_axis_and_values(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "sample.csv",
        _csv_rows(["4000.0,0.100", "3999.5,0.200", "3999.0,-0.300"]),
    )
    dataset = _read(source)

    assert dataset.format_id == "FTIR_CSV"
    assert dataset.technique == "ftir"
    assert len(dataset.spectra) == 1
    spectrum = dataset.primary
    assert spectrum.technique == "ftir"
    assert spectrum.source_format == "FTIR_CSV"
    assert spectrum.dataset_id == "sample"
    np.testing.assert_array_equal(
        spectrum.x_values,
        np.array([4000.0, 3999.5, 3999.0]),
    )
    np.testing.assert_array_equal(
        spectrum.y_values,
        np.array([0.100, 0.200, -0.300]),
    )
    assert spectrum.axis.direction == "decreasing"
    assert spectrum.axis.quantity == "unknown"
    assert spectrum.axis.unit is None
    assert spectrum.raw_signal.semantics == "unknown"


def test_dpt_style_tab_file_with_4350_rows(tmp_path: Path) -> None:
    x = 4000.0 - np.arange(4350, dtype=np.float64)
    y = np.linspace(0.1, 0.9, 4350)
    lines = [
        f"{x_value:.1f}\t{y_value:.17g}"
        for x_value, y_value in zip(x, y)
    ]
    source = _write(tmp_path / "S-SYNTHETIC.dpt", "\n".join(lines) + "\n")

    dataset = _read(
        source,
        mapping=ColumnMapping(
            x_unit="cm^-1",
            y_semantics="absorbance",
        ),
        acquisition_mode="ATR",
    )
    spectrum = dataset.primary

    assert dataset.format_id == "FTIR_TXT"
    assert spectrum.point_count == 4350
    assert spectrum.axis.direction == "decreasing"
    assert spectrum.axis.quantity == "wavenumber"
    assert spectrum.axis.unit == "cm^-1"
    np.testing.assert_array_equal(spectrum.x_values, x)
    np.testing.assert_array_equal(spectrum.y_values, y)


def test_decimal_comma_and_semicolon_delimiter(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "decimal.csv",
        _csv_rows(["1000,5;0,1", "1000,75;0,2", "1001,0;-0,3"]),
    )
    dataset = _read(
        source,
        mapping=ColumnMapping(delimiter="semicolon", decimal="comma"),
    )
    spectrum = dataset.primary

    np.testing.assert_array_equal(
        spectrum.x_values,
        np.array([1000.5, 1000.75, 1001.0]),
    )
    np.testing.assert_array_equal(
        spectrum.y_values,
        np.array([0.1, 0.2, -0.3]),
    )
    assert spectrum.axis.direction == "increasing"


def test_explicit_x_y_indices_with_header(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "wide.csv",
        _csv_rows(
            [
                "index,Wavenumber,Absorbance",
                "1,4000,0.1",
                "2,3999,0.2",
            ]
        ),
    )
    dataset = _read(
        source,
        mapping=ColumnMapping(x=1, y=2, header=True),
    )
    np.testing.assert_array_equal(
        dataset.primary.x_values, np.array([4000.0, 3999.0])
    )
    np.testing.assert_array_equal(
        dataset.primary.y_values, np.array([0.1, 0.2])
    )
    assert any(
        "only X column 1 and Y column 2" in warning
        for warning in dataset.warnings
    )


def test_header_names_resolve_explicitly(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "named.csv",
        _csv_rows(
            [
                "Wavenumber,Absorbance,Unused",
                "4000,0.1,9",
                "3999,0.2,8",
            ]
        ),
    )
    dataset = _read(
        source,
        mapping=ColumnMapping(
            x="Wavenumber",
            y="Absorbance",
            header=True,
            x_name="Wavenumber",
            y_name="Absorbance",
            x_unit="cm^-1",
            y_semantics="absorbance",
        ),
    )
    spectrum = dataset.primary
    assert spectrum.axis.name == "Wavenumber"
    assert spectrum.raw_signal.name == "Absorbance"
    assert spectrum.metadata.technique_metadata["header_fields"] == [
        "Wavenumber",
        "Absorbance",
        "Unused",
    ]


def test_wide_file_without_mapping_is_not_guessed(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "wide.csv",
        _csv_rows(["1,4000,0.1", "2,3999,0.2"]),
    )
    with pytest.raises(ImportFailure) as exc:
        _read(source)
    assert exc.value.code == "ftir_column_mapping_required"
    assert exc.value.context["column_count"] == 3


def test_default_mapping_is_recorded_as_an_assumption(tmp_path: Path) -> None:
    source = _write(tmp_path / "two.csv", _csv_rows(["2,0.2", "1,0.1"]))
    dataset = _read(source)
    spectrum = dataset.primary
    assert spectrum.provenance.format_metadata["defaulted_two_column_mapping"]
    assert any(
        "first two columns" in assumption
        for assumption in spectrum.provenance.assumptions
    )


def test_custom_delimiter_comments_and_skipped_rows(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "custom.txt",
        "\n".join(
            [
                "instrument note",
                "# comment 1",
                "4000|0.1",
                "# comment 2",
                "3999|0.2",
            ]
        )
        + "\n",
    )
    dataset = _read(
        source,
        mapping=ColumnMapping(
            delimiter="|",
            comment="#",
            skip_rows=1,
        ),
    )
    spectrum = dataset.primary
    np.testing.assert_array_equal(spectrum.x_values, np.array([4000.0, 3999.0]))
    assert spectrum.provenance.format_metadata["comment_line_count"] == 2
    assert spectrum.provenance.format_metadata["skip_rows"] == 1
    assert any(
        "2 comment line" in warning for warning in dataset.warnings
    )


def test_custom_text_encoding(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "encoded.csv",
        "Wavenumber,Signal\n4000,0.1\n3999,0.2\n",
        encoding="utf-16",
    )
    dataset = _read(
        source,
        mapping=ColumnMapping(
            x="Wavenumber",
            y="Signal",
            header=True,
            encoding="utf-16",
        ),
    )
    np.testing.assert_array_equal(
        dataset.primary.x_values, np.array([4000.0, 3999.0])
    )


def test_unknown_option_is_rejected_not_ignored(tmp_path: Path) -> None:
    source = _write(tmp_path / "two.csv", _csv_rows(["2,0.2", "1,0.1"]))
    with pytest.raises(ImportFailure) as exc:
        _registry().read(source, options={"surprise": True})
    assert exc.value.code == "ftir_unsupported_option"


def test_column_name_without_header_is_rejected() -> None:
    with pytest.raises(ImportFailure) as exc:
        ColumnMapping(x="Wavenumber", y=1, header=False)
    assert exc.value.code == "ftir_header_required"


def test_same_column_mapping_is_rejected() -> None:
    with pytest.raises(ImportFailure) as exc:
        ColumnMapping(x=1, y=1)
    assert exc.value.code == "ftir_same_column"


# ---------------------------------------------------------------------------
# Axis validation and malformed data
# ---------------------------------------------------------------------------
def test_duplicate_x_values_are_rejected_without_sorting(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "duplicate.csv",
        _csv_rows(["4000,0.1", "4000,0.2", "3999,0.3"]),
    )
    with pytest.raises(ImportFailure) as exc:
        _read(source)
    assert exc.value.code == "axis_not_monotonic"
    assert exc.value.context["source"] == "ftir_text"


def test_non_monotonic_x_values_are_rejected(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "unsorted.csv",
        _csv_rows(["4000,0.1", "3998,0.2", "3999,0.3"]),
    )
    with pytest.raises(ImportFailure) as exc:
        _read(source)
    assert exc.value.code == "axis_not_monotonic"


@pytest.mark.parametrize("bad_value", ["abc", "1.2.3", "1_000", "--1"])
def test_invalid_numeric_value_is_reported(
    tmp_path: Path, bad_value: str
) -> None:
    source = _write(
        tmp_path / "bad.csv",
        _csv_rows(["4000,0.1", f"3999,{bad_value}"]),
    )
    with pytest.raises(ImportFailure) as exc:
        _read(source)
    assert exc.value.code == "ftir_invalid_number"
    assert exc.value.context["line"] == 2
    assert exc.value.context["column"] == 1


def test_comma_in_dot_decimal_file_is_rejected(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "bad.txt",
        "4000 0.1\n3999 1,2\n",
    )
    with pytest.raises(ImportFailure) as exc:
        _read(source)
    assert exc.value.code == "ftir_invalid_number"


@pytest.mark.parametrize("bad_value", ["nan", "NaN", "inf", "-inf", "1e999"])
def test_nan_and_infinity_are_rejected(
    tmp_path: Path, bad_value: str
) -> None:
    source = _write(
        tmp_path / "nonfinite.csv",
        _csv_rows(["4000,0.1", f"3999,{bad_value}"]),
    )
    with pytest.raises(ImportFailure) as exc:
        _read(source)
    assert exc.value.code == "ftir_nonfinite"


def test_missing_column_index_is_rejected(tmp_path: Path) -> None:
    source = _write(tmp_path / "two.csv", _csv_rows(["4000,0.1", "3999,0.2"]))
    with pytest.raises(ImportFailure) as exc:
        _read(source, mapping=ColumnMapping(x=0, y=3))
    assert exc.value.code == "ftir_missing_column"
    assert exc.value.context["column"] == 3


def test_inconsistent_row_lengths_are_rejected(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "ragged.csv",
        _csv_rows(["4000,0.1", "3999", "3998,0.3"]),
    )
    with pytest.raises(ImportFailure) as exc:
        _read(source)
    assert exc.value.code == "ftir_inconsistent_columns"
    assert exc.value.context["line"] == 2


def test_header_column_count_mismatch_is_rejected(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "mismatch.csv",
        _csv_rows(["Wavenumber,Absorbance,Extra", "4000,0.1", "3999,0.2"]),
    )
    with pytest.raises(ImportFailure) as exc:
        _read(source, mapping=ColumnMapping(x=0, y=1, header=True))
    assert exc.value.code == "ftir_inconsistent_columns"


def test_empty_file_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "empty.csv"
    source.write_bytes(b"")
    with pytest.raises(ImportFailure) as exc:
        _read(source)
    assert exc.value.code == "ftir_empty_file"


def test_header_only_file_is_rejected(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "header.csv",
        "Wavenumber,Absorbance\n",
    )
    with pytest.raises(ImportFailure) as exc:
        _read(source, mapping=ColumnMapping(header=True))
    assert exc.value.code == "ftir_no_data"


def test_single_point_is_rejected(tmp_path: Path) -> None:
    source = _write(tmp_path / "one.csv", "4000,0.1\n")
    with pytest.raises(ImportFailure) as exc:
        _read(source)
    assert exc.value.code == "ftir_insufficient_points"


# ---------------------------------------------------------------------------
# Explicit FTIR metadata
# ---------------------------------------------------------------------------
def test_unknown_metadata_remains_unknown(tmp_path: Path) -> None:
    source = _write(tmp_path / "unknown.csv", _csv_rows(["4000,0.1", "3999,0.2"]))
    spectrum = _read(source).primary
    metadata = spectrum.metadata

    assert metadata.technique == "ftir"
    assert metadata.acquisition["mode"] == "Unknown"
    assert metadata.acquisition["atr_correction_status"] == "unknown"
    assert set(metadata.technique_metadata) == {
        "format_id",
        "column_mapping",
        "header_fields",
    }
    assert {"axis.quantity", "axis.unit", "signal.semantics"}.issubset(
        metadata.unknown_fields
    )
    assert "acquisition_mode" in metadata.unknown_fields
    assert "atr_correction_status" in metadata.unknown_fields
    assert "instrument.vendor" in metadata.unknown_fields
    assert spectrum.raw_signal.semantics == "unknown"
    assert spectrum.axis.quantity == "unknown"


@pytest.mark.parametrize("semantics", ["absorbance", "transmittance"])
def test_signal_semantics_must_be_explicit(
    tmp_path: Path, semantics: str
) -> None:
    source = _write(tmp_path / "semantics.csv", _csv_rows(["4000,0.1", "3999,0.2"]))
    spectrum = _read(
        source,
        mapping=ColumnMapping(y_semantics=semantics, y_unit="a.u."),
    ).primary
    assert spectrum.raw_signal.semantics == semantics
    assert spectrum.raw_signal.unit == "a.u."
    assert "signal_semantics" not in spectrum.metadata.technique_metadata


@pytest.mark.parametrize("mode", ["ATR", "Transmission", "Unknown", "atr"])
def test_acquisition_modes_are_explicit_and_canonical(
    tmp_path: Path, mode: str
) -> None:
    source = _write(tmp_path / "mode.csv", _csv_rows(["4000,0.1", "3999,0.2"]))
    spectrum = _read(source, acquisition_mode=mode).primary
    expected = "ATR" if mode.casefold() == "atr" else mode
    assert spectrum.metadata.acquisition["mode"] == expected
    assert "acquisition_mode" not in spectrum.metadata.technique_metadata


@pytest.mark.parametrize(
    "status",
    ["applied", "not_applied", "not_applicable", "unknown"],
)
def test_atr_correction_status_is_explicit(
    tmp_path: Path, status: str
) -> None:
    source = _write(tmp_path / "atr.csv", _csv_rows(["4000,0.1", "3999,0.2"]))
    spectrum = _read(
        source,
        mapping=ColumnMapping(y_semantics="absorbance"),
        acquisition_mode="ATR",
        atr_correction_status=status,
    ).primary
    assert spectrum.metadata.acquisition["mode"] == "ATR"
    assert spectrum.metadata.acquisition["atr_correction_status"] == status
    assert "atr_correction_status" not in spectrum.metadata.technique_metadata


def test_acquisition_mode_and_signal_semantics_are_independent(
    tmp_path: Path,
) -> None:
    source = _write(tmp_path / "independent.csv", _csv_rows(["4000,0.1", "3999,0.2"]))
    spectrum = _read(
        source,
        mapping=ColumnMapping(y_semantics="transmittance"),
        acquisition_mode="ATR",
    ).primary
    assert spectrum.metadata.acquisition["mode"] == "ATR"
    assert spectrum.raw_signal.semantics == "transmittance"


def test_invalid_axis_unit_is_rejected_not_converted(tmp_path: Path) -> None:
    with pytest.raises(ImportFailure) as exc:
        ColumnMapping(x_unit="nm")
    assert exc.value.code == "ftir_unsupported_axis_unit"


def test_axis_quantity_unknown_conflicts_with_explicit_unit() -> None:
    with pytest.raises(ImportFailure) as exc:
        ColumnMapping(x_quantity="unknown", x_unit="cm^-1")
    assert exc.value.code == "ftir_axis_quantity_unit_conflict"


def test_instrument_vendor_and_model_are_optional(tmp_path: Path) -> None:
    source = _write(tmp_path / "instrument.csv", _csv_rows(["4000,0.1", "3999,0.2"]))
    spectrum = _read(
        source,
        instrument_vendor="Example Instruments",
        instrument_model="FTIR-1",
    ).primary
    assert spectrum.metadata.instrument == {
        "vendor": "Example Instruments",
        "model": "FTIR-1",
    }
    assert "instrument.vendor" not in spectrum.metadata.unknown_fields
    assert "instrument.model" not in spectrum.metadata.unknown_fields


def test_options_are_traceable_in_provenance_and_metadata(
    tmp_path: Path,
) -> None:
    source = _write(tmp_path / "trace.csv", _csv_rows(["4000,0.1", "3999,0.2"]))
    spectrum = _read(
        source,
        mapping=ColumnMapping(
            x=0,
            y=1,
            x_unit="cm^-1",
            y_semantics="absorbance",
            header=False,
            decimal=".",
            encoding="utf-8-sig",
        ),
        acquisition_mode="ATR",
        atr_correction_status="not_applied",
    ).primary

    format_metadata = spectrum.provenance.format_metadata
    assert format_metadata["resolved_mapping"]["x"] == 0
    assert format_metadata["resolved_mapping"]["y"] == 1
    assert format_metadata["delimiter"] == ","
    assert format_metadata["decimal_separator"] == "."
    assert format_metadata["import_options"]["acquisition_mode"] == "ATR"
    assert format_metadata["import_options"]["atr_correction_status"] == "not_applied"
    assert "resolved_import_options" not in spectrum.metadata.technique_metadata
    assert "ftir_metadata" not in spectrum.metadata.technique_metadata
    assert spectrum.metadata.acquisition["mode"] == "ATR"
    assert spectrum.metadata.metadata_origin["signal.semantics"] == (
        "explicit user y_semantics"
    )


def test_source_is_hashed_sized_and_unchanged(tmp_path: Path) -> None:
    source = _write(tmp_path / "immutable.csv", _csv_rows(["4000,0.1", "3999,0.2"]))
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    size = source.stat().st_size

    spectrum = _read(source).primary
    after = hashlib.sha256(source.read_bytes()).hexdigest()

    assert before == after
    assert spectrum.provenance.canonical_sha256 == before
    assert spectrum.provenance.file_size_bytes == size
    assert spectrum.provenance.source_files[0].sha256 == before
    assert spectrum.provenance.source_files[0].size_bytes == size
    assert spectrum.provenance.importer_id == "ftir.csv"
    assert spectrum.provenance.importer_version == "1.0.0"


def test_source_file_from_bytes_matches_source_file(tmp_path: Path) -> None:
    source = _write(tmp_path / "snapshot.csv", _csv_rows(["4000,0.1", "3999,0.2"]))
    raw = source.read_bytes()
    from_disk = source_file(source, role="source", format_id="FTIR_CSV")
    from_snapshot = source_file_from_bytes(
        source,
        raw,
        role="source",
        format_id="FTIR_CSV",
    )
    assert from_snapshot == from_disk


def test_successful_import_reads_one_stable_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _write(tmp_path / "once.csv", _csv_rows(["4000,0.1", "3999,0.2"]))
    real_open = Path.open
    opened: list[Path] = []

    def counting_open(self: Path, *args, **kwargs):
        if self == source:
            opened.append(self)
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)
    request = ImportRequest(
        entry=source,
        options={"ftir": FTIRImportOptions(mapping=ColumnMapping(x=0, y=1))},
    )
    dataset = GenericCSVImporter().read(request)

    assert len(opened) == 1
    assert dataset.primary.provenance.canonical_sha256 == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    assert dataset.primary.provenance.file_size_bytes == source.stat().st_size


def test_probe_read_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _write(
        tmp_path / "large.csv",
        "\n".join(f"{4000.0 - index},0.1" for index in range(10_000)) + "\n",
    )
    assert source.stat().st_size > _generic.PROBE_READ_LIMIT
    real_open = Path.open
    read_sizes: list[int] = []

    class RecordingHandle:
        def __init__(self, handle) -> None:
            self._handle = handle

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            self._handle.close()

        def fileno(self) -> int:
            return self._handle.fileno()

        def read(self, size: int = -1) -> bytes:
            read_sizes.append(size)
            return self._handle.read(size)

    def recording_open(self: Path, *args, **kwargs):
        handle = real_open(self, *args, **kwargs)
        return RecordingHandle(handle) if self == source else handle

    monkeypatch.setattr(Path, "open", recording_open)
    result = GenericCSVImporter().probe(source)

    assert result.supported
    assert read_sizes == [_generic.PROBE_READ_LIMIT]
    assert _generic.PROBE_READ_LIMIT <= 64 * 1024


def test_file_mutation_during_read_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _write(tmp_path / "changed.csv", _csv_rows(["4000,0.1", "3999,0.2"]))
    real_fstat = os.fstat
    calls = 0

    def changing_fstat(fd: int):
        nonlocal calls
        calls += 1
        status = real_fstat(fd)
        if calls == 2:
            return SimpleNamespace(
                st_size=status.st_size + 1,
                st_mtime_ns=status.st_mtime_ns,
            )
        return status

    monkeypatch.setattr(_generic.os, "fstat", changing_fstat)
    request = ImportRequest(
        entry=source,
        options={"ftir": FTIRImportOptions(mapping=ColumnMapping(x=0, y=1))},
    )
    with pytest.raises(ImportFailure) as exc:
        GenericCSVImporter().read(request)
    assert exc.value.code == "source_changed_during_import"


# ---------------------------------------------------------------------------
# Probe, registry and real-sample readiness
# ---------------------------------------------------------------------------
def test_probe_rejects_one_line_and_accepts_tabular_text(tmp_path: Path) -> None:
    one_line = _write(tmp_path / "notes.txt", "not a spectrum\n")
    good = _write(tmp_path / "good.dpt", "4000\t0.1\n3999\t0.2\n")

    registry = _registry()
    assert registry.candidates(one_line) == ()
    candidates = registry.candidates(good)
    assert len(candidates) == 1
    assert candidates[0].format_id == "FTIR_TXT"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("  ", None),
        ("0", 0),
        ("+2", 2),
        ("-1", -1),
        ("Wavenumber", "Wavenumber"),
        (" 3 ", 3),
    ],
)
def test_parse_column_reference(value, expected) -> None:
    assert parse_column_reference(value) == expected


def test_registry_selects_csv_and_txt_importers(tmp_path: Path) -> None:
    csv_path = _write(tmp_path / "a.csv", "4000,0.1\n3999,0.2\n")
    txt_path = _write(tmp_path / "b.txt", "4000 0.1\n3999 0.2\n")
    dpt_path = _write(tmp_path / "c.dpt", "4000\t0.1\n3999\t0.2\n")
    registry = _registry()

    assert isinstance(registry.select(csv_path), GenericCSVImporter)
    assert isinstance(registry.select(txt_path), GenericTXTImporter)
    assert isinstance(registry.select(dpt_path), GenericTXTImporter)


def test_real_atr_ftir_sample_if_present() -> None:
    candidates = [
        PROJECT_ROOT / "Test data" / "S-BSAPEG-10.0.dpt",
        PROJECT_ROOT / "data" / "raw" / "S-BSAPEG-10.0.dpt",
        PROJECT_ROOT / "tests" / "fixtures" / "S-BSAPEG-10.0.dpt",
        PROJECT_ROOT / "S-BSAPEG-10.0.dpt",
    ]
    source = next((path for path in candidates if path.is_file()), None)
    if source is None:
        pytest.skip(
            "Real sample S-BSAPEG-10.0.dpt is not present in this checkout."
        )

    dataset = _read(
        source,
        mapping=ColumnMapping(x_unit="cm^-1", y_semantics="absorbance"),
        acquisition_mode="ATR",
        atr_correction_status="unknown",
    )
    spectrum = dataset.primary
    assert spectrum.point_count == 4350
    assert spectrum.axis.direction == "decreasing"
    assert spectrum.axis.quantity == "wavenumber"
    assert spectrum.metadata.acquisition["mode"] == "ATR"
    assert spectrum.metadata.acquisition["atr_correction_status"] == "unknown"
    assert "acquisition_mode" not in spectrum.metadata.technique_metadata
