"""M3 tests for generic Spectrum1D CSV/JSON export and provenance."""

from __future__ import annotations

import csv
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
import pytest

from spectralab.app.registry import build_importer_registry
from spectralab.core.errors import (
    ExportPathError,
    ExportSerializationError,
    OutputExistsError,
)
from spectralab.core.export import (
    CSV_COLUMNS,
    CSV_SCHEMA_ID,
    CSV_SCHEMA_VERSION,
    JSON_SCHEMA_ID,
    JSON_SCHEMA_VERSION,
    build_csv_metadata_document,
    build_export_document,
    check_output_path,
    export_spectrum_csv,
    export_spectrum_json,
    render_spectrum_csv,
    render_spectrum_json,
)
from spectralab.core.model import (
    Axis1D,
    Provenance,
    Signal1D,
    SourceFile,
    Spectrum1D,
    SpectrumMetadata,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = Path(__file__).parent / "fixtures" / "m0_baseline.json"
BASELINE = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bits(values) -> list[bytes]:
    return [struct.pack(">d", float(value)) for value in values]


def _source(tmp_path: Path, name: str, payload: bytes) -> SourceFile:
    path = tmp_path / name
    path.write_bytes(payload)
    return SourceFile(
        role="spectrum",
        path=path,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        format_id="CSV",
    )


def _synthetic_ftir(
    tmp_path: Path,
    *,
    x_values=(4000.0, 3500.0, 3000.0, 2500.0, 2000.0),
    y_values=(0.1, 0.2, 0.15, 0.3, 0.25),
    unit: str | None = "cm^-1",
    semantics: str = "absorbance",
    signal_unit: str | None = "AU",
) -> Spectrum1D:
    source = _source(tmp_path, "ftir_source.csv", b"4000,0.1\n3999,0.2\n")
    axis = Axis1D(
        values=np.asarray(x_values, dtype=np.float64),
        quantity="wavenumber",
        unit=unit,
        name="Wavenumber",
        direction="decreasing",
        metadata_source="synthetic test",
    )
    signal = Signal1D(
        values=np.asarray(y_values, dtype=np.float64),
        semantics=semantics,
        unit=signal_unit,
        name="Absorbance",
        metadata_source="synthetic test",
    )
    return Spectrum1D(
        dataset_id="ftir-synthetic",
        axis=axis,
        raw_signal=signal,
        metadata=SpectrumMetadata(
            technique="ftir",
            instrument={},
            acquisition={"mode": "ATR"},
            sample={},
            technique_metadata={
                "acquisition_mode": "ATR",
                "atr_correction_status": "unknown",
            },
            extra={"note": "synthetic"},
            unknown_fields=("title", "sample", "signal_semantics_verified"),
            metadata_origin={
                "axis.unit": "synthetic test declaration",
                "signal.unit": "synthetic test declaration",
            },
        ),
        provenance=Provenance(
            source_files=(source,),
            canonical_sha256=source.sha256,
            sha256_definition="SHA-256 of the source file bytes.",
            file_size_bytes=source.size_bytes,
            warnings=("synthetic warning",),
            assumptions=("synthetic assumption",),
            format_metadata={"delimiter": ","},
            diagnostics={"rows": len(x_values)},
            software_versions={"test": "1.0"},
            importer_id="ftir.synthetic",
            importer_version="0.1.0",
            imported_at_utc=None,
        ),
    )


def _minimal_spectrum(
    *,
    x_values=(1.0, 2.0, 3.0),
    y_values=(10.0, 20.0, 30.0),
    axis_unit: str | None = "G",
    axis_quantity: str = "magnetic_field",
    signal_unit: str | None = None,
    semantics: str = "unknown",
) -> Spectrum1D:
    return Spectrum1D(
        dataset_id="minimal",
        axis=Axis1D(
            values=np.asarray(x_values, dtype=np.float64),
            quantity=axis_quantity,
            unit=axis_unit,
            name=None,
            direction="increasing",
            metadata_source="test",
        ),
        raw_signal=Signal1D(
            values=np.asarray(y_values, dtype=np.float64),
            semantics=semantics,
            unit=signal_unit,
            name=None,
            metadata_source="test",
        ),
        metadata=SpectrumMetadata(
            technique="unknown",
            unknown_fields=("title", "instrument", "sample"),
        ),
        provenance=Provenance(
            importer_id="test.minimal",
            importer_version="1",
        ),
    )


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return list(reader.fieldnames or ()), rows


def _real_paths(key: str) -> tuple[dict, dict[str, Path]]:
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


def test_epr_spectrum_generic_csv_roundtrip_and_provenance(tmp_path: Path) -> None:
    record, paths = _real_paths("asc_real")
    _require(paths)
    source = paths["source"]
    before_hash = _sha256(source)

    spectrum = build_importer_registry().read(source).primary
    before_x = spectrum.x_values.copy()
    before_y = spectrum.y_values.copy()

    outputs = export_spectrum_csv(spectrum, tmp_path / "epr_generic.csv")
    fieldnames, rows = _read_csv(outputs["csv"])

    assert fieldnames == list(CSV_COLUMNS) == ["x", "y"]
    assert "field_G" not in fieldnames
    assert "intensity" not in fieldnames
    assert len(rows) == record["n_points"] == spectrum.point_count
    exported_x = [float(row["x"]) for row in rows]
    exported_y = [float(row["y"]) for row in rows]
    assert _bits(exported_x) == _bits(before_x)
    assert _bits(exported_y) == _bits(before_y)
    assert exported_x[0] == record["field_first"]
    assert exported_x[-1] == record["field_last"]

    metadata = json.loads(outputs["metadata"].read_text(encoding="utf-8"))
    assert metadata["schema_id"] == CSV_SCHEMA_ID
    assert metadata["schema_version"] == CSV_SCHEMA_VERSION
    assert metadata["export"]["format"] == "csv_metadata"
    assert metadata["export"]["values_included"] is False
    assert metadata["dataset"]["technique"] == "epr"
    assert metadata["dataset"]["source_format"] == "ASC"
    assert metadata["axis"]["quantity"] == "magnetic_field"
    assert metadata["axis"]["unit"] == "G"
    assert metadata["signal"]["semantics"] == "unknown"
    assert metadata["signal"]["unit"] is None
    assert metadata["provenance"]["importer"]["id"] == "epr.xepr_asc"
    assert metadata["provenance"]["imported_at_utc"] is None
    assert metadata["provenance"]["source_files"][0]["role"] == "source"
    assert metadata["provenance"]["source_files"][0]["sha256"] == record["sha256"]
    assert metadata["provenance"]["source_files"][0]["size_bytes"] == (
        record["file_size_bytes"]
    )
    assert metadata["provenance"]["source_files"][0]["path"] == str(source)
    assert metadata["metadata"]["metadata_origin"]["axis.unit"]

    assert _sha256(source) == before_hash
    np.testing.assert_array_equal(spectrum.x_values, before_x)
    np.testing.assert_array_equal(spectrum.y_values, before_y)
    assert not spectrum.x_values.flags.writeable
    assert not spectrum.y_values.flags.writeable


def test_ftir_like_decreasing_axis_csv(tmp_path: Path) -> None:
    spectrum = _synthetic_ftir(tmp_path)
    outputs = export_spectrum_csv(spectrum, tmp_path / "ftir.csv")
    _fields, rows = _read_csv(outputs["csv"])

    assert [float(row["x"]) for row in rows] == list(spectrum.x_values)
    assert [float(row["y"]) for row in rows] == list(spectrum.y_values)
    assert rows[0]["x"] == "4000.0"
    assert rows[-1]["x"] == "2000.0"

    metadata = json.loads(outputs["metadata"].read_text(encoding="utf-8"))
    assert metadata["dataset"]["technique"] == "ftir"
    assert metadata["axis"]["quantity"] == "wavenumber"
    assert metadata["axis"]["unit"] == "cm^-1"
    assert metadata["axis"]["direction"] == "decreasing"
    assert metadata["signal"]["semantics"] == "absorbance"
    assert metadata["signal"]["unit"] == "AU"
    assert metadata["metadata"]["technique_metadata"]["acquisition_mode"] == "ATR"
    assert metadata["metadata"]["unknown_fields"] == [
        "title",
        "sample",
        "signal_semantics_verified",
    ]
    assert metadata["csv"]["columns"] == ["x", "y"]


def test_unknown_axis_and_signal_metadata_stay_unknown(tmp_path: Path) -> None:
    spectrum = _minimal_spectrum(axis_unit=None, signal_unit=None)
    outputs = export_spectrum_csv(spectrum, tmp_path / "unknown.csv")
    sidecar = json.loads(outputs["metadata"].read_text(encoding="utf-8"))
    assert sidecar["axis"]["unit"] is None
    assert sidecar["signal"]["semantics"] == "unknown"
    assert sidecar["signal"]["unit"] is None
    assert sidecar["metadata"]["unknown_fields"] == [
        "title",
        "instrument",
        "sample",
    ]

    json_path = export_spectrum_json(spectrum, tmp_path / "unknown.json")
    document = json.loads(json_path.read_text(encoding="utf-8"))
    assert document["axis"]["quantity"] == "magnetic_field"
    assert document["axis"]["unit"] is None
    assert document["signal"]["semantics"] == "unknown"
    assert document["signal"]["unit"] is None


def test_numeric_roundtrip_is_bit_exact_in_csv_and_json(tmp_path: Path) -> None:
    x_values = (
        1e-300,
        1e-200,
        0.1,
        1.0,
        np.nextafter(1.0, 2.0),
    )
    y_values = (
        0.1 + 0.2,
        -0.0,
        np.nextafter(0.0, 1.0),
        1.7976931348623157e308,
        -1.2345678901234567,
    )
    spectrum = _minimal_spectrum(x_values=x_values, y_values=y_values)

    csv_outputs = export_spectrum_csv(spectrum, tmp_path / "bits.csv")
    _fields, rows = _read_csv(csv_outputs["csv"])
    assert _bits(float(row["x"]) for row in rows) == _bits(x_values)
    assert _bits(float(row["y"]) for row in rows) == _bits(y_values)

    json_path = export_spectrum_json(spectrum, tmp_path / "bits.json")
    document = json.loads(json_path.read_text(encoding="utf-8"))
    assert _bits(document["axis"]["values"]) == _bits(x_values)
    assert _bits(document["signal"]["values"]) == _bits(y_values)


def test_json_schema_is_versioned_parseable_and_deterministic(
    tmp_path: Path,
) -> None:
    spectrum = _synthetic_ftir(tmp_path)
    first = render_spectrum_json(spectrum)
    second = render_spectrum_json(spectrum)
    assert first == second

    path = export_spectrum_json(spectrum, tmp_path / "spectrum.json")
    text = path.read_text(encoding="utf-8")
    assert text == first
    document = json.loads(text)

    assert document["schema_id"] == JSON_SCHEMA_ID
    assert document["schema_version"] == JSON_SCHEMA_VERSION
    assert document["schema_status"] == "initial"
    assert document["export"]["format"] == "json"
    assert document["export"]["values_included"] is True
    assert document["export"]["processing_applied"] == []
    assert document["export"]["point_order"] == "preserved"
    assert document["dataset"]["point_count"] == 5
    assert document["axis"]["direction"] == "decreasing"
    assert document["axis"]["values"] == list(spectrum.x_values)
    assert document["signal"]["values"] == list(spectrum.y_values)
    assert document["metadata"]["metadata_origin"] == {
        "axis.unit": "synthetic test declaration",
        "signal.unit": "synthetic test declaration",
    }
    assert document["provenance"]["importer"] == {
        "id": "ftir.synthetic",
        "version": "0.1.0",
    }
    assert document["provenance"]["imported_at_utc"] is None
    assert document["provenance"]["warnings"] == ["synthetic warning"]
    assert document["provenance"]["assumptions"] == ["synthetic assumption"]
    assert document["provenance"]["diagnostics"] == {"rows": 5}
    assert document["provenance"]["format_metadata"] == {"delimiter": ","}
    assert document["provenance"]["source_files"][0]["role"] == "spectrum"
    assert document["provenance"]["source_files"][0]["sha256"]
    assert "NaN" not in text
    assert "Infinity" not in text


def test_json_preserves_canonical_and_source_hash_distinction(
    tmp_path: Path,
) -> None:
    record, paths = _real_paths("bes3t_real")
    _require(paths)
    spectrum = build_importer_registry().read(paths["descriptor"]).primary
    path = export_spectrum_json(spectrum, tmp_path / "bes3t.json")
    document = json.loads(path.read_text(encoding="utf-8"))
    provenance = document["provenance"]

    assert provenance["canonical_sha256"] == record["sha256"]
    assert provenance["sha256_definition"] == spectrum.provenance.sha256_definition
    assert "BES3T:" in provenance["sha256_definition"]
    source_hashes = {
        item["role"]: item["sha256"] for item in provenance["source_files"]
    }
    assert source_hashes == record["source_hashes"]
    assert provenance["canonical_sha256"] != source_hashes["descriptor"]
    assert provenance["canonical_sha256"] != source_hashes["data"]
    assert provenance["hash_definitions"]["source_file_sha256"]
    assert provenance["hash_definitions"]["canonical_sha256"]


def test_source_hashes_and_spectrum_are_unchanged_by_export(
    tmp_path: Path,
) -> None:
    record, paths = _real_paths("bes3t_real")
    _require(paths)
    before = {role: _sha256(path) for role, path in paths.items()}
    spectrum = build_importer_registry().read(paths["descriptor"]).primary
    before_x = spectrum.x_values.copy()
    before_y = spectrum.y_values.copy()

    export_spectrum_csv(spectrum, tmp_path / "bes3t.csv")
    export_spectrum_json(spectrum, tmp_path / "bes3t.json")

    assert {role: _sha256(path) for role, path in paths.items()} == before
    np.testing.assert_array_equal(spectrum.x_values, before_x)
    np.testing.assert_array_equal(spectrum.y_values, before_y)
    assert spectrum.provenance.canonical_sha256 == record["sha256"]


def test_nonfinite_data_is_rejected_without_partial_output(
    tmp_path: Path,
) -> None:
    spectrum = _minimal_spectrum()
    values = spectrum.raw_signal.values
    values.setflags(write=True)
    values[1] = np.inf
    values.setflags(write=False)

    csv_path = tmp_path / "invalid.csv"
    with pytest.raises(ExportSerializationError) as csv_error:
        export_spectrum_csv(spectrum, csv_path)
    assert csv_error.value.code == "nonfinite_value"
    assert not csv_path.exists()
    assert not (tmp_path / "invalid_metadata.json").exists()

    json_path = tmp_path / "invalid.json"
    with pytest.raises(ExportSerializationError) as json_error:
        export_spectrum_json(spectrum, json_path)
    assert json_error.value.code == "nonfinite_value"
    assert not json_path.exists()

    existing = tmp_path / "existing.json"
    existing.write_text("keep\n", encoding="utf-8")
    with pytest.raises(ExportSerializationError):
        export_spectrum_json(spectrum, existing, overwrite=True)
    assert existing.read_text(encoding="utf-8") == "keep\n"


def test_unsupported_metadata_is_rejected_without_partial_output(
    tmp_path: Path,
) -> None:
    spectrum = _synthetic_ftir(tmp_path)
    object.__setattr__(spectrum.metadata, "extra", {"bad": object()})

    csv_path = tmp_path / "bad_metadata.csv"
    with pytest.raises(ExportSerializationError) as csv_error:
        export_spectrum_csv(spectrum, csv_path)
    assert csv_error.value.code == "unsupported_metadata_value"
    assert not csv_path.exists()
    assert not (tmp_path / "bad_metadata_metadata.json").exists()

    json_path = tmp_path / "bad_metadata.json"
    with pytest.raises(ExportSerializationError):
        export_spectrum_json(spectrum, json_path)
    assert not json_path.exists()


def test_existing_outputs_require_explicit_overwrite(tmp_path: Path) -> None:
    spectrum = _minimal_spectrum()
    csv_path = tmp_path / "protected.csv"
    csv_path.write_text("original\n", encoding="utf-8")

    with pytest.raises(OutputExistsError) as exc:
        export_spectrum_csv(spectrum, csv_path)
    assert exc.value.code == "output_exists"
    assert isinstance(exc.value, FileExistsError)
    assert csv_path.read_text(encoding="utf-8") == "original\n"
    assert not (tmp_path / "protected_metadata.json").exists()

    outputs = export_spectrum_csv(spectrum, csv_path, overwrite=True)
    assert outputs["csv"].read_text(encoding="utf-8").startswith("x,y\n")

    json_path = tmp_path / "protected.json"
    json_path.write_text("original\n", encoding="utf-8")
    with pytest.raises(OutputExistsError):
        export_spectrum_json(spectrum, json_path)
    assert json_path.read_text(encoding="utf-8") == "original\n"
    export_spectrum_json(spectrum, json_path, overwrite=True)
    assert json.loads(json_path.read_text(encoding="utf-8"))["schema_version"] == 1


def test_existing_metadata_sidecar_blocks_csv_creation(tmp_path: Path) -> None:
    spectrum = _minimal_spectrum()
    metadata = tmp_path / "pair_metadata.json"
    metadata.write_text("keep\n", encoding="utf-8")

    with pytest.raises(OutputExistsError):
        export_spectrum_csv(spectrum, tmp_path / "pair.csv")

    assert not (tmp_path / "pair.csv").exists()
    assert metadata.read_text(encoding="utf-8") == "keep\n"


def test_source_file_cannot_be_overwritten(tmp_path: Path) -> None:
    source = _source(tmp_path, "source.csv", b"source bytes")
    spectrum = _minimal_spectrum()
    spectrum = Spectrum1D(
        dataset_id=spectrum.dataset_id,
        axis=spectrum.axis,
        raw_signal=spectrum.raw_signal,
        metadata=spectrum.metadata,
        provenance=Provenance(
            source_files=(source,),
            importer_id="test.minimal",
            importer_version="1",
        ),
    )
    before = source.path.read_bytes()

    with pytest.raises(ExportPathError) as exc:
        export_spectrum_csv(spectrum, source.path, overwrite=True)
    assert exc.value.code == "output_is_source_file"
    assert source.path.read_bytes() == before

    with pytest.raises(ExportPathError):
        export_spectrum_json(spectrum, source.path, overwrite=True)
    assert source.path.read_bytes() == before


def test_invalid_and_duplicate_output_paths(tmp_path: Path) -> None:
    spectrum = _minimal_spectrum()
    directory = tmp_path / "directory.csv"
    directory.mkdir()

    with pytest.raises(ExportPathError) as directory_error:
        export_spectrum_csv(spectrum, directory)
    assert directory_error.value.code == "output_is_directory"

    duplicate = tmp_path / "duplicate.csv"
    with pytest.raises(ExportPathError) as duplicate_error:
        export_spectrum_csv(spectrum, duplicate, metadata_path=duplicate)
    assert duplicate_error.value.code == "duplicate_output_path"

    with pytest.raises(ExportPathError) as empty_error:
        check_output_path("")
    assert empty_error.value.code == "invalid_output_path"

    with pytest.raises(ExportPathError) as none_error:
        export_spectrum_csv(spectrum, None)  # type: ignore[arg-type]
    assert none_error.value.code == "invalid_output_path"


def test_unknown_source_hash_and_size_stay_null(tmp_path: Path) -> None:
    spectrum = _minimal_spectrum()
    source = SourceFile(
        role="source",
        path=tmp_path / "unknown_hash.ASC",
        sha256="",
        size_bytes=None,
        format_id="ASC",
    )
    spectrum = Spectrum1D(
        dataset_id=spectrum.dataset_id,
        axis=spectrum.axis,
        raw_signal=spectrum.raw_signal,
        metadata=spectrum.metadata,
        provenance=Provenance(
            source_files=(source,),
            canonical_sha256=None,
            sha256_definition=None,
            importer_id="test.minimal",
            importer_version="1",
        ),
    )

    json_path = export_spectrum_json(spectrum, tmp_path / "unknown_hash.json")
    document = json.loads(json_path.read_text(encoding="utf-8"))
    exported = document["provenance"]["source_files"][0]
    assert exported["sha256"] is None
    assert exported["size_bytes"] is None
    assert document["provenance"]["canonical_sha256"] is None
    assert document["provenance"]["sha256_definition"] is None

    outputs = export_spectrum_csv(spectrum, tmp_path / "unknown_hash.csv")
    sidecar = json.loads(outputs["metadata"].read_text(encoding="utf-8"))
    assert sidecar["provenance"]["source_files"][0]["sha256"] is None


def test_build_documents_and_schema_constants_are_consistent(
    tmp_path: Path,
) -> None:
    spectrum = _synthetic_ftir(tmp_path)
    json_document = build_export_document(spectrum)
    csv_document = build_csv_metadata_document(spectrum)

    assert json_document["schema_id"] == JSON_SCHEMA_ID
    assert json_document["schema_version"] == JSON_SCHEMA_VERSION == 1
    assert json_document["export"]["values_included"] is True
    assert "values" in json_document["axis"]
    assert "values" in json_document["signal"]

    assert csv_document["schema_id"] == CSV_SCHEMA_ID
    assert csv_document["schema_version"] == CSV_SCHEMA_VERSION == 1
    assert csv_document["export"]["values_included"] is False
    assert "values" not in csv_document["axis"]
    assert "values" not in csv_document["signal"]
    assert csv_document["provenance"] == json_document["provenance"]

    schema = json.loads(
        (PROJECT_ROOT / "docs" / "spectrum1d_export_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["$id"] == JSON_SCHEMA_ID
    assert schema["properties"]["schema_version"]["const"] == JSON_SCHEMA_VERSION
    assert set(json_document) == set(schema["properties"])
    assert set(schema["required"]) == set(schema["properties"])
    assert set(json_document["axis"]) == set(
        schema["properties"]["axis"]["properties"]
    )
    assert set(json_document["signal"]) == set(
        schema["properties"]["signal"]["properties"]
    )
    assert set(json_document["provenance"]) == set(
        schema["properties"]["provenance"]["properties"]
    )


def test_csv_render_contains_only_generic_xy_columns(tmp_path: Path) -> None:
    spectrum = _synthetic_ftir(tmp_path)
    text = render_spectrum_csv(spectrum)
    lines = text.splitlines()
    assert lines[0] == "x,y"
    assert len(lines) == spectrum.point_count + 1
    assert "Field" not in lines[0]
    assert "Intensity" not in lines[0]
