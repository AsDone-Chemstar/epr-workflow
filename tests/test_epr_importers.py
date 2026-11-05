"""M2 dispatch and numerical-equivalence tests for the legacy EPR importers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from epr_workflow.bes3t import read_bes3t
from epr_workflow.plot_asc import PROJECT_ROOT, read_asc, read_dataset
from spectralab.app.registry import build_importer_registry
from spectralab.core.errors import ImportFailure, UnsupportedFormatError
from spectralab.core.importers import Importer
from spectralab.techniques.epr.importers import (
    BES3TImporter,
    Bes3tImporter,
    XeprASCImporter,
    XeprAscImporter,
)

BASELINE_PATH = Path(__file__).parent / "fixtures" / "m0_baseline.json"
BASELINE = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
HEADER = "     index           Field [G]        Intensity []\n\n"


def _registry():
    registry = build_importer_registry()
    assert [importer.id for importer in registry.importers] == [
        "epr.xepr_asc",
        "epr.bes3t",
        "ftir.csv",
        "ftir.txt",
    ]
    return registry


def _write_asc(path: Path, rows: list[str]) -> Path:
    path.write_text(
        HEADER + "\n".join(rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _write_bes3t(
    tmp_path: Path,
    *,
    values: tuple[float, ...] = (1.5, -2.0, 3.25, 0.125, 9.0),
    xmin: float = 3300.0,
    xwid: float = 2.0,
    missing: tuple[str, ...] = (),
    write_companion: bool = True,
) -> tuple[Path, Path]:
    dsc = tmp_path / "sample.DSC"
    dta = tmp_path / "sample.DTA"

    def row(key: str, value: str) -> list[str]:
        if key in missing:
            return []
        return [f"{key} {value}"]

    lines = [
        "#DESC 1.2",
        "DSRC EXP",
        "BSEQ BIG",
        "IKKF REAL",
        "XTYP IDX",
        "YTYP NODATA",
        "ZTYP NODATA",
        "IRFMT D",
        *row("XPTS", str(len(values))),
        *row("XMIN", str(xmin)),
        *row("XWID", str(xwid)),
        "XNAM 'Field'",
        "XUNI 'G'",
        "IRNAM 'Intensity'",
        "IRUNI ''",
        "#SPL 1.2",
        "EXPT CW",
    ]
    dsc.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    if write_companion:
        dta.write_bytes(np.asarray(values, dtype=">f8").tobytes())
    return dsc, dta


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def test_asc_dispatch_and_values_match_legacy_reader(tmp_path: Path) -> None:
    path = _write_asc(
        tmp_path / "sample.ASC",
        ["1 3300.0 10.0", "2 3301.0 20.0", "3 3302.0 30.0"],
    )
    old = read_asc(path)
    before = _sha256(path)

    dataset = _registry().read(path)
    spectrum = dataset.primary

    assert dataset.format_id == "ASC"
    assert dataset.technique == "epr"
    assert dataset.primary_index == 0
    assert spectrum.source_format == "ASC"
    assert spectrum.point_count == len(old.data)
    np.testing.assert_array_equal(
        spectrum.x_values, old.data["field_G"].to_numpy()
    )
    np.testing.assert_array_equal(
        spectrum.y_values, old.data["intensity"].to_numpy()
    )
    assert spectrum.axis.direction == "increasing"
    assert spectrum.axis.unit == "G"
    assert spectrum.raw_signal.semantics == "unknown"
    assert spectrum.provenance.importer_id == "epr.xepr_asc"
    assert spectrum.provenance.importer_version == "0.1.0"
    assert spectrum.provenance.canonical_sha256 == old.sha256
    assert _sha256(path) == before


def test_bes3t_dispatch_and_values_match_legacy_reader(tmp_path: Path) -> None:
    dsc, dta = _write_bes3t(tmp_path)
    old = read_bes3t(dsc)
    before = _sha256(dsc), _sha256(dta)

    dataset = _registry().read(dsc)
    spectrum = dataset.primary

    assert dataset.format_id == "BES3T"
    assert spectrum.source_format == "BES3T"
    assert spectrum.point_count == len(old.data)
    np.testing.assert_array_equal(
        spectrum.x_values, old.data["field_G"].to_numpy()
    )
    np.testing.assert_array_equal(
        spectrum.y_values, old.data["intensity"].to_numpy()
    )
    assert spectrum.provenance.importer_id == "epr.bes3t"
    assert {
        item.role: item.sha256 for item in spectrum.provenance.source_files
    } == old.source_hashes
    assert (_sha256(dsc), _sha256(dta)) == before


def test_decreasing_asc_axis_is_preserved_without_reversal(
    tmp_path: Path,
) -> None:
    path = _write_asc(
        tmp_path / "decreasing.ASC",
        ["1 3302.0 10.0", "2 3301.0 20.0", "3 3300.0 30.0"],
    )

    spectrum = _registry().read(path).primary

    assert spectrum.axis.direction == "decreasing"
    np.testing.assert_array_equal(spectrum.x_values, [3302.0, 3301.0, 3300.0])
    np.testing.assert_array_equal(spectrum.y_values, [10.0, 20.0, 30.0])


def test_decreasing_bes3t_axis_is_preserved_without_reversal(
    tmp_path: Path,
) -> None:
    dsc, _dta = _write_bes3t(
        tmp_path,
        values=(1.5, -2.0, 3.25, 0.125, 9.0),
        xmin=3302.0,
        xwid=-2.0,
    )

    spectrum = _registry().read(dsc).primary

    assert spectrum.axis.direction == "decreasing"
    assert spectrum.x_values[0] == 3302.0
    assert spectrum.x_values[-1] == 3300.0


@pytest.mark.parametrize("key", ["asc_real", "bes3t_real"])
def test_real_importer_matches_m0_baseline(key: str) -> None:
    record, paths = _paths_for(key)
    _require(paths)
    before = {role: _sha256(path) for role, path in paths.items()}
    entry = paths.get("descriptor", paths.get("source"))
    old = read_dataset(entry)

    dataset = _registry().read(entry)
    spectrum = dataset.primary

    assert dataset.format_id == record["source_format"]
    assert spectrum.point_count == record["n_points"]
    np.testing.assert_array_equal(
        spectrum.x_values, old.data["field_G"].to_numpy()
    )
    np.testing.assert_array_equal(
        spectrum.y_values, old.data["intensity"].to_numpy()
    )
    assert spectrum.x_values[0] == record["field_first"]
    assert spectrum.x_values[-1] == record["field_last"]
    assert spectrum.y_values.min() == record["intensity_min"]
    assert spectrum.y_values.max() == record["intensity_max"]
    np.testing.assert_array_equal(
        spectrum.y_values[:5], np.asarray(record["intensity_first5"])
    )
    np.testing.assert_array_equal(
        spectrum.y_values[-5:], np.asarray(record["intensity_last5"])
    )
    assert spectrum.axis.direction == "increasing"
    assert spectrum.axis.unit == "G"
    assert spectrum.raw_signal.semantics == "unknown"
    assert spectrum.provenance.canonical_sha256 == record["sha256"]
    assert {
        item.role: item.sha256 for item in spectrum.provenance.source_files
    } == record["source_hashes"]
    assert {role: _sha256(path) for role, path in paths.items()} == before


def test_dta_is_not_an_independent_dataset(tmp_path: Path) -> None:
    _dsc, dta = _write_bes3t(tmp_path)

    with pytest.raises(UnsupportedFormatError) as exc:
        _registry().select(dta)

    assert exc.value.code == "unsupported_format"
    assert exc.value.context["suffix"] == ".DTA"


def test_malformed_asc_after_probe_returns_no_partial_spectrum(
    tmp_path: Path,
) -> None:
    path = _write_asc(tmp_path / "short.ASC", ["1 3300.0 10.0"])

    with pytest.raises(ImportFailure) as exc:
        _registry().read(path)

    assert exc.value.code == "asc_data_error"
    assert exc.value.context["entry"] == str(path)
    assert "at least" in str(exc.value)


def test_malformed_bes3t_after_probe_returns_no_partial_spectrum(
    tmp_path: Path,
) -> None:
    dsc, _dta = _write_bes3t(tmp_path, missing=("XMIN",))

    with pytest.raises(ImportFailure) as exc:
        _registry().read(dsc)

    assert exc.value.code == "bes3t_missing_parameter"
    assert exc.value.context["parameter"] == "XMIN"


def test_missing_bes3t_companion_has_a_stable_error(tmp_path: Path) -> None:
    dsc, _dta = _write_bes3t(tmp_path, write_companion=False)

    with pytest.raises(ImportFailure) as exc:
        _registry().read(dsc)

    assert exc.value.code == "bes3t_companion_missing"
    assert exc.value.context["descriptor"] == dsc.name


def test_epr_importer_collect_sources() -> None:
    asc = XeprAscImporter()
    bes3t = Bes3tImporter()

    assert XeprASCImporter is XeprAscImporter
    assert BES3TImporter is Bes3tImporter
    assert isinstance(asc, Importer)
    assert isinstance(bes3t, Importer)
    assert asc.entry_suffixes == (".asc",)
    assert bes3t.entry_suffixes == (".dsc",)
    assert asc.technique == bes3t.technique == "epr"


def test_collect_sources_for_real_or_synthetic_pairs(tmp_path: Path) -> None:
    path = _write_asc(
        tmp_path / "source.ASC",
        ["1 3300.0 10.0", "2 3301.0 20.0", "3 3302.0 30.0"],
    )
    asc_source = XeprAscImporter().collect_sources(path)
    assert [item.role for item in asc_source] == ["source"]
    assert asc_source[0].sha256 == _sha256(path)

    dsc, dta = _write_bes3t(tmp_path)
    bes3t_sources = Bes3tImporter().collect_sources(dsc)
    assert [item.role for item in bes3t_sources] == ["descriptor", "data"]
    assert [item.sha256 for item in bes3t_sources] == [
        _sha256(dsc),
        _sha256(dta),
    ]


def test_import_options_are_rejected_not_silently_ignored(
    tmp_path: Path,
) -> None:
    path = _write_asc(
        tmp_path / "options.ASC",
        ["1 3300.0 10.0", "2 3301.0 20.0", "3 3302.0 30.0"],
    )

    with pytest.raises(ImportFailure) as exc:
        _registry().read(path, options={"allow_non_monotonic": True})

    assert exc.value.code == "unsupported_import_option"


def test_importer_provenance_does_not_change_legacy_adapter_default(
    tmp_path: Path,
) -> None:
    path = _write_asc(
        tmp_path / "default.ASC",
        ["1 3300.0 10.0", "2 3301.0 20.0", "3 3302.0 30.0"],
    )
    old = read_asc(path)
    spectrum = _registry().read(path).primary
    assert spectrum.provenance.importer_id == "epr.xepr_asc"
    assert old.sha256 == spectrum.provenance.canonical_sha256
