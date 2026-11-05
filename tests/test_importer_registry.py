"""Tests for the neutral importer protocol and explicit registry."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from spectralab.core.errors import (
    AmbiguousFormatError,
    ImportFailure,
    ImporterRegistrationError,
    UnsupportedFormatError,
)
from spectralab.core.importers import (
    ImportedDataset,
    ImportRequest,
    Importer,
    ImporterRegistry,
    ProbeResult,
)
from spectralab.core.model import (
    Axis1D,
    Provenance,
    Signal1D,
    Spectrum1D,
    SpectrumMetadata,
)


def _dataset(dataset_id: str = "fake") -> ImportedDataset:
    axis = Axis1D(
        values=np.array([1.0, 2.0, 3.0]),
        quantity="index",
        unit="1",
        name="Index",
        direction="increasing",
        metadata_source="test",
    )
    signal = Signal1D(
        values=np.array([10.0, 20.0, 30.0]),
        semantics="unknown",
        unit=None,
        name="Signal",
        metadata_source="test",
    )
    spectrum = Spectrum1D(
        dataset_id=dataset_id,
        axis=axis,
        raw_signal=signal,
        metadata=SpectrumMetadata(technique="demo"),
        provenance=Provenance(importer_id="test.fake", importer_version="1"),
    )
    return ImportedDataset(
        spectra=(spectrum,),
        primary_index=0,
        format_id="FAKE",
        technique="demo",
    )


class FakeImporter:
    def __init__(
        self,
        *,
        importer_id: str = "test.fake",
        technique: str = "demo",
        suffix: str = ".fake",
        format_id: str = "FAKE",
        supported: bool = True,
        confidence: float = 1.0,
    ) -> None:
        self.id = importer_id
        self.version = "1"
        self.technique = technique
        self.entry_suffixes = (suffix,)
        self.format_id = format_id
        self.supported = supported
        self.confidence = confidence
        self.probe_calls = 0
        self.read_calls = 0
        self.requests: list[ImportRequest] = []
        self.read_error: Exception | None = None

    def probe(self, entry: Path) -> ProbeResult:
        self.probe_calls += 1
        return ProbeResult(
            supported=self.supported,
            confidence=self.confidence,
            format_id=self.format_id,
            technique=self.technique,
            reason="configured by the test",
        )

    def collect_sources(self, entry: Path):
        return ()

    def read(self, request: ImportRequest) -> ImportedDataset:
        self.read_calls += 1
        self.requests.append(request)
        if self.read_error is not None:
            raise self.read_error
        return _dataset(Path(request.entry).stem)


def _entry(tmp_path: Path, name: str = "sample.fake") -> Path:
    path = tmp_path / name
    path.write_text("entry\n", encoding="utf-8")
    return path


def test_fake_importer_conforms_to_protocol() -> None:
    assert isinstance(FakeImporter(), Importer)


def test_explicit_registration_lookup_and_read(tmp_path: Path) -> None:
    importer = FakeImporter()
    registry = ImporterRegistry()
    registry.register(importer)
    entry = _entry(tmp_path)

    assert registry.importers == (importer,)
    assert registry.select(entry) is importer
    assert registry.select(entry, technique="demo") is importer
    assert registry.select(entry, format_id="FAKE") is importer
    probes = registry.candidates(entry)
    assert len(probes) == 1
    assert probes[0].format_id == "FAKE"

    dataset = registry.read(entry, options={"future": "value"})
    assert dataset.format_id == "FAKE"
    assert dataset.technique == "demo"
    assert dataset.primary_index == 0
    assert importer.read_calls == 1
    assert importer.requests[0].options == {"future": "value"}


def test_extension_only_narrows_candidates_and_is_not_proof(
    tmp_path: Path,
) -> None:
    importer = FakeImporter(supported=False)
    registry = ImporterRegistry()
    registry.register(importer)

    with pytest.raises(UnsupportedFormatError) as exc:
        registry.select(_entry(tmp_path))

    assert exc.value.code == "unsupported_format"
    assert importer.probe_calls == 1
    assert exc.value.context["probes"][0]["reason"] == "configured by the test"


def test_unknown_suffix_is_not_probed(tmp_path: Path) -> None:
    importer = FakeImporter(suffix=".fake")
    registry = ImporterRegistry()
    registry.register(importer)

    with pytest.raises(UnsupportedFormatError) as exc:
        registry.select(_entry(tmp_path, "sample.other"))

    assert exc.value.code == "unsupported_format"
    assert importer.probe_calls == 0
    assert exc.value.context["suffix"] == ".other"


def test_duplicate_registration_is_rejected_and_replace_is_explicit(
    tmp_path: Path,
) -> None:
    first = FakeImporter()
    second = FakeImporter(format_id="OTHER")
    registry = ImporterRegistry()
    registry.register(first)

    with pytest.raises(ImporterRegistrationError) as exc:
        registry.register(second)

    assert exc.value.code == "duplicate_importer_id"
    assert registry.select(_entry(tmp_path)) is first

    registry.register(second, replace=True)
    assert registry.select(_entry(tmp_path)) is second


def test_invalid_importer_definition_is_rejected() -> None:
    class Broken:
        id = "broken"
        version = "1"
        technique = "demo"
        entry_suffixes = ()
        probe = staticmethod(lambda entry: None)
        collect_sources = staticmethod(lambda entry: ())
        read = staticmethod(lambda request: None)

    registry = ImporterRegistry()
    with pytest.raises(ImporterRegistrationError) as exc:
        registry.register(Broken())

    assert exc.value.code == "invalid_importer"


def test_ambiguous_matches_are_not_resolved_by_confidence(
    tmp_path: Path,
) -> None:
    first = FakeImporter(importer_id="test.first", confidence=0.99)
    second = FakeImporter(importer_id="test.second", confidence=0.01)
    registry = ImporterRegistry()
    registry.register(first)
    registry.register(second)
    entry = _entry(tmp_path)

    with pytest.raises(AmbiguousFormatError) as exc:
        registry.select(entry)

    assert exc.value.code == "ambiguous_format"
    assert len(exc.value.context["candidates"]) == 2
    assert first.read_calls == 0
    assert second.read_calls == 0

    with pytest.raises(AmbiguousFormatError):
        registry.read(entry)


def test_explicit_format_resolves_an_ambiguous_suffix(tmp_path: Path) -> None:
    first = FakeImporter(importer_id="test.first", format_id="FIRST")
    second = FakeImporter(
        importer_id="test.second",
        format_id="SECOND",
        technique="other",
    )
    registry = ImporterRegistry()
    registry.register(first)
    registry.register(second)
    entry = _entry(tmp_path)

    assert registry.select(entry, format_id="FIRST") is first
    assert registry.select(entry, format_id="SECOND") is second
    assert registry.select(entry, technique="demo") is first


def test_no_silent_fallback_after_read_failure(tmp_path: Path) -> None:
    first = FakeImporter(importer_id="test.first", format_id="FIRST")
    first.read_error = ImportFailure(
        "deliberate test failure",
        code="deliberate",
    )
    second = FakeImporter(importer_id="test.second", format_id="SECOND")
    registry = ImporterRegistry()
    registry.register(first)
    registry.register(second)
    entry = _entry(tmp_path)

    with pytest.raises(ImportFailure) as exc:
        registry.read(entry, format_id="FIRST")

    assert exc.value.code == "deliberate"
    assert first.read_calls == 1
    assert second.read_calls == 0


def test_missing_entry_is_an_explicit_failure(tmp_path: Path) -> None:
    registry = ImporterRegistry()
    registry.register(FakeImporter())

    with pytest.raises(ImportFailure) as exc:
        registry.select(tmp_path / "missing.fake")

    assert exc.value.code == "entry_not_found"


def test_read_request_mappings_are_read_only() -> None:
    request = ImportRequest(
        entry=Path("sample.fake"),
        companions={"data": Path("sample.dat")},
        options={"key": "value"},
    )
    with pytest.raises(TypeError):
        request.companions["other"] = Path("other.dat")  # type: ignore[index]
    with pytest.raises(TypeError):
        request.options["other"] = "value"  # type: ignore[index]


def test_invalid_probe_result_is_not_silently_accepted(tmp_path: Path) -> None:
    class BadProbe(FakeImporter):
        def probe(self, entry: Path):
            return "not a probe result"

    registry = ImporterRegistry()
    registry.register(BadProbe())

    with pytest.raises(ImportFailure) as exc:
        registry.candidates(_entry(tmp_path))

    assert exc.value.code == "invalid_probe_result"
