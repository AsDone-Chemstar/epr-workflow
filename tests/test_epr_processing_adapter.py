"""Tests for the EPR processing adapter equivalence and boundaries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from epr_workflow.plot_asc import PROJECT_ROOT, read_dataset
from epr_workflow.preprocessing import (
    BaselineWindow,
    LinearBaselineSpec,
    PreprocessingSession,
    SavgolSpec,
)
from spectralab.app.registry import build_importer_registry
from spectralab.core.errors import ProcessingError
from spectralab.core.model import (
    Axis1D,
    Provenance,
    Signal1D,
    Spectrum1D,
    SpectrumMetadata,
)
from spectralab.core.processing import ProcessingSession
from spectralab.techniques.epr.processing_adapter import (
    EPRLinearBaselineOperation,
    EPRSavitzkyGolayOperation,
    EprLinearBaselineOperation,
    EprProcessingError,
    EprSavitzkyGolayOperation,
)

BASELINE_PATH = Path(__file__).parent / "fixtures" / "m0_baseline.json"
BASELINE = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


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


def _window_spec(x_values: np.ndarray) -> LinearBaselineSpec:
    finite = np.asarray(x_values, dtype=np.float64)
    low = float(finite.min())
    high = float(finite.max())
    step = (high - low) / (finite.size - 1)
    return LinearBaselineSpec(
        BaselineWindow(low, low + 4.0 * step),
        BaselineWindow(high - 4.0 * step, high),
    )


def _real_pair(key: str):
    _record, paths = _paths_for(key)
    _require(paths)
    entry = paths.get("descriptor", paths.get("source"))
    imported = read_dataset(entry)
    spectrum = build_importer_registry().read(entry).primary
    return entry, imported, spectrum


def _synthetic_spectrum(
    *,
    x_values: np.ndarray,
    y_values: np.ndarray,
    quantity: str = "magnetic_field",
    unit: str = "G",
) -> Spectrum1D:
    direction = "increasing" if np.all(np.diff(x_values) > 0) else "decreasing"
    return Spectrum1D(
        dataset_id="synthetic",
        axis=Axis1D(
            values=x_values,
            quantity=quantity,
            unit=unit,
            name="Field",
            direction=direction,
            metadata_source="synthetic test",
        ),
        raw_signal=Signal1D(
            values=y_values,
            semantics="unknown",
            unit=None,
            name="Intensity",
            metadata_source="synthetic test",
        ),
        metadata=SpectrumMetadata(technique="epr"),
        provenance=Provenance(
            importer_id="test.epr",
            importer_version="1",
        ),
    )


def _legacy_session(entry: Path, imported) -> PreprocessingSession:
    return PreprocessingSession(
        source=entry,
        field_G=imported.data["field_G"],
        intensity=imported.data["intensity"],
        source_sha256=imported.sha256,
    )


@pytest.mark.parametrize("key", ["asc_real", "bes3t_real"])
def test_epr_baseline_matches_legacy_numerically(key: str) -> None:
    entry, imported, spectrum = _real_pair(key)
    spec = _window_spec(spectrum.x_values)
    before_hash = hashlib.sha256(entry.read_bytes()).hexdigest()
    before_x = spectrum.x_values.copy()
    before_y = spectrum.y_values.copy()

    legacy = _legacy_session(entry, imported).apply(spec)
    session = ProcessingSession(spectrum, session_id="epr-baseline")
    result = session.apply(EprLinearBaselineOperation(spec))

    np.testing.assert_array_equal(result.x_values, legacy.field_G)
    np.testing.assert_array_equal(result.y_values, legacy.intensity_processed)
    np.testing.assert_array_equal(
        spectrum.y_values - result.y_values,
        legacy.removed_baseline,
    )
    assert result.history[0].operation_id == "linear_baseline"
    assert result.history[0].technique == "epr"
    assert result.history[0].version == "1.0"
    assert result.history[0].parameters["windows_G"][0]["start"] == (
        spec.window_left.start
    )
    assert result.history[0].changes_axis is False
    assert result.history[0].warnings == tuple(
        warning.message for warning in legacy.warnings
    )
    assert result.history[0].diagnostics["fit"] == legacy.last_fit.as_dict()
    assert result.history[0].diagnostics["points_used"] == legacy.last_fit.n_points

    np.testing.assert_array_equal(spectrum.x_values, before_x)
    np.testing.assert_array_equal(spectrum.y_values, before_y)
    assert hashlib.sha256(entry.read_bytes()).hexdigest() == before_hash
    assert result.source is spectrum
    assert result.metadata is spectrum.metadata
    assert result.provenance is spectrum.provenance


@pytest.mark.parametrize("key", ["asc_real", "bes3t_real"])
def test_epr_savgol_matches_legacy_numerically(key: str) -> None:
    entry, imported, spectrum = _real_pair(key)
    spec = SavgolSpec(window_length=11, polyorder=3)
    legacy = _legacy_session(entry, imported).apply_savgol(spec)

    session = ProcessingSession(spectrum, session_id="epr-savgol")
    result = session.apply(EprSavitzkyGolayOperation(spec))

    np.testing.assert_array_equal(result.x_values, legacy.field_G)
    np.testing.assert_array_equal(result.y_values, legacy.intensity_processed)
    assert result.history[0].operation_id == "savitzky_golay"
    assert result.history[0].technique == "epr"
    assert result.history[0].version == "1.0"
    assert result.history[0].parameters["window_length"] == 11
    assert result.history[0].parameters["polyorder"] == 3
    assert result.history[0].changes_axis is False
    assert result.history[0].changes_signal_semantics is False
    assert result.history[0].changes_signal_unit is False
    assert result.history[0].diagnostics["smoothing"] == (
        legacy.steps[0].smoothing.as_dict()
    )


@pytest.mark.parametrize("key", ["asc_real", "bes3t_real"])
def test_epr_combined_operations_match_legacy_order(key: str) -> None:
    entry, imported, spectrum = _real_pair(key)
    baseline_spec = _window_spec(spectrum.x_values)
    savgol_spec = SavgolSpec(window_length=9, polyorder=2)

    legacy_session = _legacy_session(entry, imported)
    legacy_session.apply(baseline_spec)
    legacy = legacy_session.apply_savgol(savgol_spec)

    session = ProcessingSession(spectrum)
    session.apply(EprLinearBaselineOperation(baseline_spec))
    result = session.apply(EprSavitzkyGolayOperation(savgol_spec))

    np.testing.assert_array_equal(result.y_values, legacy.intensity_processed)
    assert result.operations == (
        "linear_baseline",
        "savitzky_golay",
    )
    assert [record.parameters.get("window_length") for record in result.history] == [
        None,
        9,
    ]
    assert result.history[0].output_state_id == "step-1"
    assert result.history[1].input_state_id == "step-1"
    assert result.history[1].output_state_id == "step-2"


def test_epr_decreasing_axis_matches_legacy() -> None:
    x_values = np.linspace(10.0, 0.0, 201)
    y_values = 3.0 * x_values + 7.0 + 20.0 * np.exp(
        -((x_values - 5.0) / 0.4) ** 2
    )
    spectrum = _synthetic_spectrum(x_values=x_values, y_values=y_values)
    spec = LinearBaselineSpec(
        BaselineWindow(0.0, 0.2),
        BaselineWindow(9.8, 10.0),
    )
    legacy = PreprocessingSession(
        source=Path("synthetic.ASC"),
        field_G=x_values,
        intensity=y_values,
    ).apply(spec)

    session = ProcessingSession(spectrum)
    result = session.apply(EprLinearBaselineOperation(spec))

    np.testing.assert_array_equal(result.y_values, legacy.intensity_processed)
    assert result.axis.direction == "decreasing"
    assert result.x_values[0] == 10.0
    assert result.x_values[-1] == 0.0


def test_epr_adapter_rejects_non_epr_axis() -> None:
    x_values = np.linspace(4000.0, 2000.0, 11)
    spectrum = _synthetic_spectrum(
        x_values=x_values,
        y_values=np.linspace(1.0, 2.0, 11),
        quantity="wavenumber",
        unit="cm^-1",
    )
    spec = LinearBaselineSpec(
        BaselineWindow(2000.0, 2001.0),
        BaselineWindow(3999.0, 4000.0),
    )
    with pytest.raises(ProcessingError) as exc:
        ProcessingSession(spectrum).apply(EprLinearBaselineOperation(spec))

    assert exc.value.code == "epr_axis_unsupported"
    assert "magnetic-field" in str(exc.value)


def test_epr_invalid_window_preserves_legacy_error_code() -> None:
    x_values = np.linspace(0.0, 10.0, 21)
    spectrum = _synthetic_spectrum(
        x_values=x_values,
        y_values=np.zeros_like(x_values),
    )
    spec = LinearBaselineSpec(
        BaselineWindow(0.0, 0.5),
        BaselineWindow(9.5, 10.0),
    )
    with pytest.raises(ProcessingError) as exc:
        ProcessingSession(spectrum).apply(EprLinearBaselineOperation(spec))

    assert exc.value.code == "window_points"
    assert exc.value.context["count"] == 2


def test_epr_operation_aliases_and_record_metadata() -> None:
    assert EPRLinearBaselineOperation is EprLinearBaselineOperation
    assert EPRSavitzkyGolayOperation is EprSavitzkyGolayOperation

    x_values = np.linspace(0.0, 10.0, 21)
    spectrum = _synthetic_spectrum(
        x_values=x_values,
        y_values=2.0 * x_values,
    )
    spec = LinearBaselineSpec(
        BaselineWindow(0.0, 1.0),
        BaselineWindow(9.0, 10.0),
    )
    result = ProcessingSession(spectrum).apply(EPRLinearBaselineOperation(spec))
    record = result.history[0]
    assert record.operation_id == "linear_baseline"
    assert record.operation_name == "EPR linear baseline correction"
    assert record.parameters["inclusive_bounds"] is True
    assert record.parameters["weighting"] == "none"
    assert record.diagnostics["legacy_operation"] == "linear_baseline"


def test_epr_operation_requires_legacy_specs() -> None:
    with pytest.raises(EprProcessingError):
        EprLinearBaselineOperation("not a spec")  # type: ignore[arg-type]
    with pytest.raises(EprProcessingError):
        EprSavitzkyGolayOperation("not a spec")  # type: ignore[arg-type]
