"""Tests for the generic processing operation/session architecture."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from spectralab.core.errors import (
    ExportSerializationError,
    InvalidProcessingOperationError,
    InvalidProcessingOutputError,
    ProcessingError,
)
from spectralab.core.export import export_spectrum_json
from spectralab.core.model import (
    Axis1D,
    Provenance,
    Signal1D,
    SourceFile,
    Spectrum1D,
    SpectrumMetadata,
)
from spectralab.core.processing import (
    OperationImplementation,
    OperationOutput,
    ProcessedSpectrum,
    ProcessingOperation,
    ProcessingSession,
)


def _spectrum(
    *,
    x_values=(1.0, 2.0, 3.0, 4.0),
    y_values=(10.0, 20.0, 30.0, 40.0),
    quantity: str = "frequency",
    direction: str = "increasing",
) -> Spectrum1D:
    source = SourceFile(
        role="source",
        path=Path("synthetic.dat"),
        sha256="abc123",
        size_bytes=42,
        format_id="SYNTH",
    )
    return Spectrum1D(
        dataset_id="synthetic",
        axis=Axis1D(
            values=np.asarray(x_values, dtype=np.float64),
            quantity=quantity,
            unit="Hz",
            name="Frequency",
            direction=direction,
            metadata_source="test fixture",
        ),
        raw_signal=Signal1D(
            values=np.asarray(y_values, dtype=np.float64),
            semantics="unknown",
            unit=None,
            name="Signal",
            metadata_source="test fixture",
        ),
        metadata=SpectrumMetadata(
            technique="test",
            title="Synthetic",
            instrument={"name": "fixture"},
            acquisition={"mode": "synthetic"},
            sample={"id": "S1"},
            technique_metadata={"kind": "unit test"},
            extra={"note": "keep me"},
            unknown_fields=("signal_semantics", "signal_unit"),
            metadata_origin={
                "axis.unit": "test fixture",
                "signal.unit": "not recorded",
            },
        ),
        provenance=Provenance(
            source_files=(source,),
            canonical_sha256="canonical",
            sha256_definition="test definition",
            file_size_bytes=42,
            warnings=("source warning",),
            assumptions=("source assumption",),
            format_metadata={"format": "SYNTH"},
            diagnostics={"rows": 4},
            software_versions={"test": "1.0"},
            importer_id="test.importer",
            importer_version="1.0",
            imported_at_utc=None,
        ),
    )


class ScaleOperation:
    operation_id = "test.scale"
    name = "Scale signal"
    technique = "test"
    version = "1.0"
    changes_axis = False
    axis_change_description = None
    changes_signal_semantics = False
    changes_signal_unit = False
    signal_change_description = None

    def __init__(self, factor: float) -> None:
        self.factor = factor
        self.parameters = {"factor": factor}

    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput:
        output = Signal1D(
            values=signal.values * self.factor,
            semantics=signal.semantics,
            unit=signal.unit,
            name=signal.name,
            metadata_source=signal.metadata_source,
            missing_reason=signal.missing_reason,
        )
        return OperationOutput(
            axis=axis,
            signal=output,
            warnings=("scaled by explicit factor",),
            assumptions=("the scale factor is user-supplied",),
            diagnostics={"factor": self.factor},
        )


class CountingOffsetOperation:
    operation_id = "test.counting_offset"
    name = "Counting offset"
    technique = "test"
    version = "1.0"
    changes_axis = False
    axis_change_description = None
    changes_signal_semantics = False
    changes_signal_unit = False
    signal_change_description = None
    parameters: dict = {}

    def __init__(self) -> None:
        self.calls = 0

    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput:
        self.calls += 1
        output = Signal1D(
            values=signal.values + self.calls,
            semantics=signal.semantics,
            unit=signal.unit,
            name=signal.name,
            metadata_source=signal.metadata_source,
        )
        return OperationOutput(axis=axis, signal=output)


class AxisOffsetOperation:
    operation_id = "test.axis_offset"
    name = "Offset X axis"
    technique = "test"
    version = "1.0"
    changes_axis = True
    axis_change_description = "Adds an explicit constant to every X value."
    changes_signal_semantics = False
    changes_signal_unit = False
    signal_change_description = None

    def __init__(self, offset: float) -> None:
        self.offset = offset
        self.parameters = {"offset": offset}

    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput:
        shifted = Axis1D(
            values=axis.values + self.offset,
            quantity=axis.quantity,
            unit=axis.unit,
            name=axis.name,
            direction=None,
            metadata_source=axis.metadata_source,
            missing_reason=axis.missing_reason,
        )
        return OperationOutput(axis=shifted, signal=signal)


class UndeclaredAxisOperation(AxisOffsetOperation):
    operation_id = "test.undeclared_axis"
    changes_axis = False
    axis_change_description = None


class SemanticChangeOperation:
    operation_id = "test.semantic_change"
    name = "Declare a semantic change"
    technique = "test"
    version = "1.0"
    changes_axis = False
    axis_change_description = None
    changes_signal_semantics = True
    changes_signal_unit = False
    signal_change_description = "Changes the signal semantic label explicitly."
    parameters = {}

    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput:
        output = Signal1D(
            values=signal.values,
            semantics="intensity",
            unit=signal.unit,
            name=signal.name,
            metadata_source=signal.metadata_source,
        )
        return OperationOutput(axis=axis, signal=output)


class UndeclaredSemanticOperation(SemanticChangeOperation):
    operation_id = "test.undeclared_semantic"
    changes_signal_semantics = False
    signal_change_description = None


class UnitChangeOperation:
    operation_id = "test.unit_change"
    name = "Declare a unit change"
    technique = "test"
    version = "1.0"
    changes_axis = False
    axis_change_description = None
    changes_signal_semantics = False
    changes_signal_unit = True
    signal_change_description = "Changes the unit label explicitly."
    parameters = {}

    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput:
        output = Signal1D(
            values=signal.values,
            semantics=signal.semantics,
            unit="arbitrary unit",
            name=signal.name,
            metadata_source=signal.metadata_source,
        )
        return OperationOutput(axis=axis, signal=output)


class FailingOperation:
    operation_id = "test.failing"
    name = "Failing operation"
    technique = "test"
    version = "1.0"
    changes_axis = False
    axis_change_description = None
    changes_signal_semantics = False
    changes_signal_unit = False
    signal_change_description = None
    parameters = {"reason": "test"}

    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput:
        raise RuntimeError("deliberate failure")


class CodedFailure(ValueError):
    def __init__(self) -> None:
        super().__init__("legacy-coded failure")
        self.code = "legacy_failure"
        self.context = {"detail": "preserved"}


class CodedFailureOperation(FailingOperation):
    operation_id = "test.coded_failure"

    def apply(self, axis: Axis1D, signal: Signal1D) -> OperationOutput:
        raise CodedFailure()


def test_operation_is_protocol_conformant() -> None:
    assert isinstance(ScaleOperation(2.0), OperationImplementation)
    assert isinstance(AxisOffsetOperation(1.0), OperationImplementation)


def test_processed_spectrum_construction_and_metadata_association() -> None:
    source = _spectrum()
    processed = ProcessedSpectrum(
        source=source,
        axis=source.axis,
        signal=source.raw_signal,
        history=(),
        session_id="session-1",
    )

    assert processed.source is source
    assert processed.source_spectrum is source
    assert processed.metadata is source.metadata
    assert processed.provenance is source.provenance
    assert processed.technique == source.technique
    assert processed.source_format == source.source_format
    assert processed.point_count == 4
    assert processed.is_original is True
    assert processed.operations == ()
    assert processed.session_id == "session-1"
    assert not processed.x_values.flags.writeable
    assert not processed.y_values.flags.writeable


def test_session_starts_from_original_without_modification() -> None:
    source = _spectrum()
    before_x = source.x_values.copy()
    before_y = source.y_values.copy()
    session = ProcessingSession(source, session_id="session-1")

    current = session.current

    assert current.source is source
    assert current.is_original is True
    assert current.axis is source.axis
    assert current.signal is source.raw_signal
    assert session.history == ()
    assert session.can_undo is False
    assert session.can_redo is False
    np.testing.assert_array_equal(source.x_values, before_x)
    np.testing.assert_array_equal(source.y_values, before_y)
    assert not source.x_values.flags.writeable
    assert not source.y_values.flags.writeable


def test_explicit_apply_records_parameters_order_and_associations() -> None:
    source = _spectrum()
    session = ProcessingSession(source, session_id="session-1")

    result = session.apply(ScaleOperation(2.0))

    assert result.history[0].order == 1
    assert result.history[0].operation_id == "test.scale"
    assert result.history[0].name == "Scale signal"
    assert result.history[0].technique == "test"
    assert result.history[0].version == "1.0"
    assert result.history[0].parameters == {"factor": 2.0}
    assert result.history[0].input_state_id == "original"
    assert result.history[0].output_state_id == "step-1"
    assert result.history[0].input_dataset_id == "synthetic"
    assert result.history[0].warnings == ("scaled by explicit factor",)
    assert result.history[0].assumptions == (
        "the scale factor is user-supplied",
    )
    assert result.history[0].diagnostics == {"factor": 2.0}
    np.testing.assert_array_equal(result.x_values, source.x_values)
    np.testing.assert_array_equal(result.y_values, source.y_values * 2.0)
    assert session.operations == ("test.scale",)
    assert session.can_undo is True
    assert session.can_redo is False
    assert session.current.y_values is not source.y_values
    assert session.current.metadata is source.metadata
    assert session.current.provenance is source.provenance


def test_operation_order_and_state_ids_are_contiguous() -> None:
    source = _spectrum()
    session = ProcessingSession(source)

    session.apply(ScaleOperation(2.0))
    result = session.apply(ScaleOperation(3.0))

    assert [record.order for record in result.history] == [1, 2]
    assert [record.operation_id for record in result.history] == [
        "test.scale",
        "test.scale",
    ]
    assert [record.input_state_id for record in result.history] == [
        "original",
        "step-1",
    ]
    assert [record.output_state_id for record in result.history] == [
        "step-1",
        "step-2",
    ]
    assert [record.parameters["factor"] for record in result.history] == [
        2.0,
        3.0,
    ]
    np.testing.assert_array_equal(result.y_values, source.y_values * 6.0)


def test_undo_and_redo_restore_exact_prior_states() -> None:
    source = _spectrum()
    session = ProcessingSession(source)
    first = session.apply(ScaleOperation(2.0))
    second = session.apply(ScaleOperation(3.0))
    second_x = second.x_values.copy()
    second_y = second.y_values.copy()

    undone = session.undo()
    assert session.can_redo is True
    assert undone.operations == ("test.scale",)
    np.testing.assert_array_equal(undone.y_values, first.y_values)

    undone_again = session.undo()
    assert undone_again.is_original is True
    np.testing.assert_array_equal(undone_again.y_values, source.y_values)

    redone = session.redo()
    np.testing.assert_array_equal(redone.y_values, first.y_values)
    redone_again = session.redo()
    np.testing.assert_array_equal(redone_again.x_values, second_x)
    np.testing.assert_array_equal(redone_again.y_values, second_y)
    assert [record.order for record in redone_again.history] == [1, 2]


def test_redo_restores_saved_output_without_replaying_operation() -> None:
    source = _spectrum()
    operation = CountingOffsetOperation()
    session = ProcessingSession(source)

    first = session.apply(operation)
    assert operation.calls == 1
    first_values = first.y_values.copy()

    session.undo()
    redone = session.redo()

    assert operation.calls == 1
    np.testing.assert_array_equal(redone.y_values, first_values)


def test_apply_after_undo_clears_redo_only_on_success() -> None:
    source = _spectrum()
    session = ProcessingSession(source)
    session.apply(ScaleOperation(2.0))
    session.undo()
    assert session.can_redo is True

    session.apply(ScaleOperation(4.0))
    assert session.can_redo is False
    assert session.operations == ("test.scale",)
    np.testing.assert_array_equal(session.current.y_values, source.y_values * 4.0)


def test_reset_returns_to_source_and_clears_history() -> None:
    source = _spectrum()
    session = ProcessingSession(source)
    session.apply(ScaleOperation(2.0))
    session.undo()

    result = session.reset()

    assert result.is_original is True
    assert session.history == ()
    assert session.can_undo is False
    assert session.can_redo is False
    np.testing.assert_array_equal(result.y_values, source.y_values)


def test_failed_operation_leaves_previous_state_and_redo_stack_intact() -> None:
    source = _spectrum()
    session = ProcessingSession(source)
    applied = session.apply(ScaleOperation(2.0))
    applied_y = applied.y_values.copy()
    session.undo()
    assert session.can_redo is True

    with pytest.raises(ProcessingError) as exc:
        session.apply(FailingOperation())

    assert exc.value.code == "operation_failed"
    assert session.can_redo is True
    assert session.can_undo is False
    assert session.history == ()
    np.testing.assert_array_equal(session.current.y_values, source.y_values)

    session.redo()
    np.testing.assert_array_equal(session.current.y_values, applied_y)


def test_legacy_coded_failure_is_wrapped_without_losing_code() -> None:
    session = ProcessingSession(_spectrum())
    with pytest.raises(ProcessingError) as exc:
        session.apply(CodedFailureOperation())

    assert exc.value.code == "legacy_failure"
    assert exc.value.context["detail"] == "preserved"
    assert session.history == ()


def test_invalid_operation_definition_is_rejected_before_execution() -> None:
    class MissingApply:
        operation_id = "test.missing_apply"
        name = "Missing apply"
        technique = "test"
        version = "1.0"
        parameters = {}
        changes_axis = False
        axis_change_description = None
        changes_signal_semantics = False
        changes_signal_unit = False
        signal_change_description = None

    session = ProcessingSession(_spectrum())
    with pytest.raises(InvalidProcessingOperationError):
        session.apply(MissingApply())
    assert session.history == ()

    class MissingDescription:
        operation_id = "test.missing_description"
        name = "Missing description"
        technique = "test"
        version = "1.0"
        parameters = {}
        changes_axis = True
        axis_change_description = None
        changes_signal_semantics = False
        changes_signal_unit = False
        signal_change_description = None
        apply = staticmethod(lambda axis, signal: None)

    with pytest.raises(InvalidProcessingOperationError) as exc:
        session.apply(MissingDescription())
    assert exc.value.code == "axis_change_description"


def test_undeclared_axis_change_is_rejected() -> None:
    session = ProcessingSession(_spectrum())
    with pytest.raises(InvalidProcessingOutputError) as exc:
        session.apply(UndeclaredAxisOperation(1.0))

    assert exc.value.code == "undeclared_axis_change"
    assert session.history == ()


def test_declared_axis_change_is_recorded() -> None:
    source = _spectrum()
    session = ProcessingSession(source)
    result = session.apply(AxisOffsetOperation(10.0))

    assert result.history[0].changes_axis is True
    assert result.history[0].axis_change_description
    np.testing.assert_array_equal(
        result.x_values, source.x_values + 10.0
    )
    np.testing.assert_array_equal(result.y_values, source.y_values)


def test_undeclared_signal_semantic_or_unit_changes_are_rejected() -> None:
    session = ProcessingSession(_spectrum())

    with pytest.raises(InvalidProcessingOutputError) as semantic_error:
        session.apply(UndeclaredSemanticOperation())
    assert semantic_error.value.code == "undeclared_signal_semantics_change"
    assert session.history == ()

    class UndeclaredUnit(UnitChangeOperation):
        operation_id = "test.undeclared_unit"
        changes_signal_unit = False
        signal_change_description = None

    with pytest.raises(InvalidProcessingOutputError) as unit_error:
        session.apply(UndeclaredUnit())
    assert unit_error.value.code == "undeclared_signal_unit_change"
    assert session.history == ()


def test_declared_signal_semantic_and_unit_changes_are_recorded() -> None:
    session = ProcessingSession(_spectrum())

    semantic_result = session.apply(SemanticChangeOperation())
    assert semantic_result.history[0].changes_signal_semantics is True
    assert semantic_result.history[0].signal_change_description
    assert semantic_result.signal.semantics == "intensity"

    unit_result = session.apply(UnitChangeOperation())
    assert unit_result.history[1].changes_signal_unit is True
    assert unit_result.signal.unit == "arbitrary unit"


def test_decreasing_axis_is_preserved() -> None:
    source = _spectrum(
        x_values=(4.0, 3.0, 2.0, 1.0),
        direction="decreasing",
    )
    session = ProcessingSession(source)
    result = session.apply(ScaleOperation(2.0))

    assert result.axis.direction == "decreasing"
    np.testing.assert_array_equal(result.x_values, [4.0, 3.0, 2.0, 1.0])


def test_processed_arrays_are_read_only_and_independent() -> None:
    source = _spectrum()
    session = ProcessingSession(source)
    result = session.apply(ScaleOperation(2.0))

    assert not result.x_values.flags.writeable
    assert not result.y_values.flags.writeable
    with pytest.raises(ValueError):
        result.y_values[0] = 0.0
    np.testing.assert_array_equal(source.y_values, [10.0, 20.0, 30.0, 40.0])
    assert source.y_values[0] == 10.0


def test_metadata_and_provenance_are_not_discarded() -> None:
    source = _spectrum()
    session = ProcessingSession(source)
    result = session.apply(ScaleOperation(2.0))

    assert result.source is source
    assert result.metadata is source.metadata
    assert result.provenance is source.provenance
    assert result.metadata.title == "Synthetic"
    assert result.metadata.instrument == {"name": "fixture"}
    assert result.metadata.unknown_fields == (
        "signal_semantics",
        "signal_unit",
    )
    assert result.provenance.canonical_sha256 == "canonical"
    assert result.provenance.source_files[0].sha256 == "abc123"


def test_processed_spectrum_rejects_noncontiguous_history() -> None:
    source = _spectrum()
    record = ProcessingOperation(
        order=2,
        operation_id="test.op",
        name="Operation",
        technique="test",
        version="1",
        parameters={},
        input_state_id="original",
        output_state_id="step-2",
    )
    assert record.input_dataset_id is None
    with pytest.raises(ProcessingError) as exc:
        ProcessedSpectrum(
            source=source,
            axis=source.axis,
            signal=source.raw_signal,
            history=(record,),
        )
    assert exc.value.code == "processed_history_order"


def test_processing_operation_rejects_invalid_input_dataset_id() -> None:
    with pytest.raises(ProcessingError):
        ProcessingOperation(
            order=1,
            operation_id="test.op",
            name="Operation",
            technique="test",
            version="1",
            parameters={},
            input_state_id="original",
            output_state_id="step-1",
            input_dataset_id=" ",
        )


def test_operation_output_rejects_mismatched_lengths() -> None:
    source = _spectrum()
    with pytest.raises(InvalidProcessingOutputError):
        OperationOutput(
            axis=source.axis,
            signal=Signal1D(
                values=np.arange(3.0),
                semantics="unknown",
                unit=None,
            ),
        )


def test_session_requires_spectrum1d() -> None:
    with pytest.raises(ProcessingError) as exc:
        ProcessingSession("not a spectrum")  # type: ignore[arg-type]
    assert exc.value.code == "session_source"


def test_processed_spectrum_is_not_accepted_as_raw_export(tmp_path: Path) -> None:
    processed = ProcessingSession(_spectrum()).apply(ScaleOperation(2.0))
    assert not isinstance(processed, Spectrum1D)

    with pytest.raises(ExportSerializationError) as exc:
        export_spectrum_json(processed, tmp_path / "processed.json")
    assert exc.value.code == "invalid_spectrum"
    assert not (tmp_path / "processed.json").exists()
