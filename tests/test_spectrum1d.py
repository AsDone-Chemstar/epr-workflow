"""Tests for the technique-independent Spectrum1D model."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import numpy as np
import pytest

from spectralab.core.errors import (
    AxisValidationError,
    SignalValidationError,
    SpectrumValidationError,
)
from spectralab.core.model import (
    Axis1D,
    Provenance,
    Signal1D,
    SourceFile,
    Spectrum1D,
    SpectrumMetadata,
)


def make_spectrum(
    x=(1.0, 2.0, 3.0),
    y=(10.0, 20.0, 30.0),
    *,
    direction="increasing",
    technique="epr",
) -> Spectrum1D:
    axis = Axis1D(
        values=x,
        quantity="magnetic_field",
        unit="G",
        name="Magnetic field",
        direction=direction,
        metadata_source="test",
    )
    signal = Signal1D(
        values=y,
        semantics="unknown",
        unit=None,
        name="Intensity",
        metadata_source="test",
    )
    return Spectrum1D(
        dataset_id="sample",
        axis=axis,
        raw_signal=signal,
        metadata=SpectrumMetadata(technique=technique),
    )


def test_spectrum_fields_and_semantics() -> None:
    axis = Axis1D(
        values=[1000.0, 1100.0, 1200.0],
        quantity="wavenumber",
        unit="cm^-1",
        name="Wavenumber",
    )
    signal = Signal1D(
        values=[0.1, 0.5, 0.2],
        semantics="absorbance",
        unit="AU",
        name="Absorbance",
    )
    spectrum = Spectrum1D(
        dataset_id="ftir-sample",
        axis=axis,
        raw_signal=signal,
        metadata=SpectrumMetadata(
            technique="ftir",
            unknown_fields=("instrument",),
        ),
        provenance=Provenance(
            format_metadata={"source_format": "CSV"},
            canonical_sha256="a" * 64,
        ),
    )

    assert spectrum.point_count == 3
    assert len(spectrum) == 3
    assert spectrum.technique == "ftir"
    assert spectrum.source_format == "CSV"
    assert spectrum.axis.quantity == "wavenumber"
    assert spectrum.axis.unit == "cm^-1"
    assert spectrum.axis.direction == "increasing"
    assert spectrum.raw_signal.semantics == "absorbance"
    assert spectrum.raw_signal.unit == "AU"
    np.testing.assert_array_equal(spectrum.x_values, [1000.0, 1100.0, 1200.0])
    np.testing.assert_array_equal(spectrum.y_values, [0.1, 0.5, 0.2])


def test_decreasing_axis_is_preserved() -> None:
    spectrum = make_spectrum(
        x=(3.0, 2.0, 1.0),
        y=(30.0, 20.0, 10.0),
        direction="decreasing",
    )

    assert spectrum.axis.direction == "decreasing"
    np.testing.assert_array_equal(spectrum.x_values, [3.0, 2.0, 1.0])
    np.testing.assert_array_equal(spectrum.y_values, [30.0, 20.0, 10.0])


def test_duplicate_axis_values_need_explicit_unknown_direction() -> None:
    with pytest.raises(AxisValidationError) as exc:
        Axis1D(values=[1.0, 1.0, 2.0], quantity="unknown")

    assert exc.value.code == "axis_not_monotonic"

    axis = Axis1D(
        values=[1.0, 1.0, 2.0],
        quantity="unknown",
        direction="unknown",
        metadata_source="test",
    )
    assert axis.direction == "unknown"
    np.testing.assert_array_equal(axis.values, [1.0, 1.0, 2.0])


def test_direction_mismatch_is_rejected() -> None:
    with pytest.raises(AxisValidationError):
        Axis1D(
            values=[1.0, 2.0, 3.0],
            quantity="magnetic_field",
            direction="decreasing",
        )

    with pytest.raises(AxisValidationError):
        Axis1D(
            values=[1.0, 1.0, 2.0],
            quantity="magnetic_field",
            direction="increasing",
        )


def test_values_are_copied_and_read_only() -> None:
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([10.0, 20.0, 30.0])
    spectrum = make_spectrum(x, y)

    x[0] = 999.0
    y[0] = -999.0

    np.testing.assert_array_equal(spectrum.x_values, [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(spectrum.y_values, [10.0, 20.0, 30.0])
    assert spectrum.x_values.flags.writeable is False
    assert spectrum.y_values.flags.writeable is False
    with pytest.raises(ValueError):
        spectrum.x_values[0] = 4.0
    with pytest.raises(ValueError):
        spectrum.y_values[0] = 4.0


def test_metadata_and_provenance_mappings_are_read_only() -> None:
    spectrum = make_spectrum()
    with pytest.raises(TypeError):
        spectrum.metadata.technique_metadata["new"] = "value"
    with pytest.raises(TypeError):
        spectrum.provenance.format_metadata["new"] = "value"
    with pytest.raises((FrozenInstanceError, AttributeError)):
        spectrum.metadata.unknown_fields = ("other",)


def test_invalid_lengths_are_rejected() -> None:
    axis = Axis1D(values=[1.0, 2.0, 3.0], quantity="magnetic_field")
    signal = Signal1D(values=[1.0, 2.0], semantics="intensity")

    with pytest.raises(SpectrumValidationError) as exc:
        Spectrum1D(
            dataset_id="bad",
            axis=axis,
            raw_signal=signal,
            metadata=SpectrumMetadata(technique="epr"),
        )
    assert exc.value.code == "length"

    with pytest.raises(AxisValidationError):
        Axis1D(values=[1.0], quantity="magnetic_field")
    with pytest.raises(SignalValidationError):
        Signal1D(values=[1.0], semantics="intensity")


def test_nonfinite_values_are_rejected() -> None:
    with pytest.raises(AxisValidationError) as axis_exc:
        Axis1D(values=[1.0, np.nan], quantity="magnetic_field")
    assert axis_exc.value.code == "nonfinite"

    with pytest.raises(SignalValidationError) as signal_exc:
        Signal1D(values=[1.0, np.inf], semantics="intensity")
    assert signal_exc.value.code == "nonfinite"


def test_complex_values_are_rejected() -> None:
    with pytest.raises(AxisValidationError) as exc:
        Axis1D(values=np.array([1 + 2j, 3 + 4j]), quantity="unknown")
    assert exc.value.code == "complex"

    with pytest.raises(SignalValidationError) as exc:
        Signal1D(
            values=np.array([1 + 2j, 3 + 4j]),
            semantics="unknown",
        )
    assert exc.value.code == "complex"


def test_invalid_units_and_semantics_are_rejected() -> None:
    with pytest.raises(AxisValidationError):
        Axis1D(values=[1.0, 2.0], quantity="magnetic_field", unit="")
    with pytest.raises(AxisValidationError):
        Axis1D(values=[1.0, 2.0], quantity="magnetic_field", unit=" G ")
    with pytest.raises(AxisValidationError):
        Axis1D(values=[1.0, 2.0], quantity="not-a-quantity")
    with pytest.raises(SignalValidationError):
        Signal1D(values=[1.0, 2.0], semantics="not-a-semantic")
    with pytest.raises(SignalValidationError):
        Signal1D(values=[1.0, 2.0], semantics="unknown", unit="")


def test_unknown_units_and_semantics_are_explicit() -> None:
    signal = Signal1D(
        values=[1.0, 2.0],
        semantics="unknown",
        unit=None,
        missing_reason="unit not documented",
    )

    assert signal.unit is None
    assert signal.unit_is_known is False
    assert signal.semantics == "unknown"
    assert signal.semantics_is_known is False
    assert signal.missing_reason == "unit not documented"


def test_spectrum_requires_identifier_and_types() -> None:
    spectrum = make_spectrum()
    with pytest.raises(SpectrumValidationError):
        Spectrum1D(
            dataset_id="",
            axis=spectrum.axis,
            raw_signal=spectrum.raw_signal,
            metadata=spectrum.metadata,
        )
    with pytest.raises(SpectrumValidationError):
        Spectrum1D(
            dataset_id="x",
            axis="not-an-axis",  # type: ignore[arg-type]
            raw_signal=spectrum.raw_signal,
            metadata=spectrum.metadata,
        )


def test_source_file_and_provenance_preserve_metadata() -> None:
    source = SourceFile(
        role="spectrum",
        path=Path("example.csv"),
        sha256="a" * 64,
        size_bytes=123,
        format_id="CSV",
    )
    provenance = Provenance(
        source_files=(source,),
        canonical_sha256="a" * 64,
        sha256_definition="SHA-256 of the source file.",
        file_size_bytes=123,
        warnings=("warning",),
        assumptions=("assumption",),
        format_metadata={"source_format": "CSV", "delimiter": ","},
        diagnostics={"rows": 2},
        software_versions={"python": "3.11.9"},
        importer_id="test",
        importer_version="1",
        imported_at_utc=None,
    )

    assert provenance.source_files[0].path == Path("example.csv")
    assert provenance.source_files[0].size_bytes == 123
    assert provenance.canonical_sha256 == "a" * 64
    assert provenance.imported_at_utc is None
    with pytest.raises(TypeError):
        provenance.format_metadata["new"] = "value"
