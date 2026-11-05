"""Qt-free tests for GUI services, technique registry and view models."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from spectralab.app.gui.controller import ApplicationController, ControllerError
from spectralab.app.gui.i18n import Translator, TranslationError, normalize_language
from spectralab.app.gui.metadata import format_metadata
from spectralab.app.gui.settings import (
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    GuiSettings,
    SettingsService,
)
from spectralab.app.gui.status import StatusEvent, status_from_payload
from spectralab.app.gui.technique import (
    TechniqueDescriptor,
    TechniqueRegistry,
    TechniqueRegistryError,
)
from spectralab.core.importers import ImportedDataset, ImporterRegistry, ProbeResult
from spectralab.core.model import (
    Axis1D,
    Provenance,
    Signal1D,
    SourceFile,
    Spectrum1D,
    SpectrumMetadata,
)
from spectralab.core.processing import OperationOutput, ProcessingSession


def _settings(tmp_path: Path) -> SettingsService:
    return SettingsService(tmp_path / "gui_settings.json")


def test_settings_defaults_and_roundtrip(tmp_path: Path) -> None:
    service = _settings(tmp_path)
    initial = service.load()
    assert initial.language == "zh"
    assert initial.window_width == DEFAULT_WINDOW_WIDTH
    assert initial.window_height == DEFAULT_WINDOW_HEIGHT
    assert initial.active_technique is None

    updated = GuiSettings(
        language="en",
        active_technique="epr",
        window_width=1200,
        window_height=800,
    )
    service.save(updated)
    loaded = service.load()
    assert loaded == updated
    assert service.last_warning is None

    payload = json.loads(service.path.read_text(encoding="utf-8"))
    assert payload["language"] == "en"
    assert payload["active_technique"] == "epr"


def test_settings_malformed_json_falls_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "gui_settings.json"
    path.write_text("{not json", encoding="utf-8")
    service = SettingsService(path)
    loaded = service.load()
    assert loaded.language == "zh"
    assert service.last_warning


def test_settings_invalid_values_are_safe(tmp_path: Path) -> None:
    path = tmp_path / "gui_settings.json"
    path.write_text(
        json.dumps(
            {
                "language": "fr",
                "active_technique": 7,
                "window_width": -1,
                "window_height": "large",
            }
        ),
        encoding="utf-8",
    )
    loaded = SettingsService(path).load()
    assert loaded.language == "zh"
    assert loaded.active_technique is None
    assert loaded.window_width == DEFAULT_WINDOW_WIDTH
    assert loaded.window_height == DEFAULT_WINDOW_HEIGHT


def test_memory_only_settings_do_not_write(tmp_path: Path) -> None:
    service = SettingsService(None)
    service.save(GuiSettings(language="en"))
    assert list(tmp_path.iterdir()) == []
    assert service.load() == GuiSettings()


def test_translator_runtime_switch_and_fallback() -> None:
    translator = Translator("en")
    assert translator.tr("app.title").startswith("SpectraLab")
    translator.set_language("zh")
    assert "光谱" in translator.tr("app.title")
    assert translator.tr("missing.key") == "missing.key"

    translator.register_catalog(
        {"en": {"dummy.hello": "Hello {name}"}, "zh": {"dummy.hello": "你好 {name}"}},
        source="dummy",
    )
    assert translator.tr("dummy.hello", name="A") == "你好 A"
    translator.set_language("en")
    assert translator.tr("dummy.hello", name="A") == "Hello A"
    assert translator.tr("dummy.hello") == "Hello {name}"
    assert normalize_language("fr") == "zh"


def test_translator_rejects_conflicting_catalog() -> None:
    translator = Translator()
    translator.register_catalog({"en": {"same.key": "A"}})
    with pytest.raises(TranslationError):
        translator.register_catalog({"en": {"same.key": "B"}})


class DummyPanel:
    def __init__(self, controller, translator) -> None:
        self.controller = controller
        self.translator = translator
        self.spectrum_changed = None
        self.status_event = None

    def open_file(self, path: Path) -> bool:
        return False

    def retranslate(self) -> None:
        pass

    def current_display(self):
        return None


def _descriptor(technique_id: str = "dummy", *, name: str | None = None) -> TechniqueDescriptor:
    return TechniqueDescriptor(
        id=technique_id,
        display_name_key="dummy.name",
        panel_factory=DummyPanel,
        file_patterns=("*.fake",),
        translations={"zh": {"dummy.name": name or technique_id}},
    )


def test_technique_registry_explicit_registration_and_switching() -> None:
    registry = TechniqueRegistry()
    first = _descriptor("first", name="First")
    second = _descriptor("second", name="Second")
    registry.register(first)
    registry.register(second)
    assert registry.ids == ("first", "second")
    assert registry.active_id == "first"
    assert registry.select("second") is second
    assert registry.active_id == "second"
    assert registry.get("first") is first
    assert registry.active is second


def test_technique_registry_duplicate_and_unknown_errors() -> None:
    registry = TechniqueRegistry()
    registry.register(_descriptor("x"))
    with pytest.raises(TechniqueRegistryError) as duplicate:
        registry.register(_descriptor("x"))
    assert duplicate.value.code == "duplicate_technique"

    with pytest.raises(TechniqueRegistryError) as unknown:
        registry.select("missing")
    assert unknown.value.code == "unknown_technique"


def _spectrum() -> Spectrum1D:
    source = SourceFile(
        role="source",
        path=Path("sample.ASC"),
        sha256="abc",
        size_bytes=10,
        format_id="ASC",
    )
    return Spectrum1D(
        dataset_id="sample",
        axis=Axis1D(
            values=np.array([1.0, 2.0, 3.0]),
            quantity="magnetic_field",
            unit="G",
            name="Magnetic field",
            direction="increasing",
            metadata_source="test",
        ),
        raw_signal=Signal1D(
            values=np.array([10.0, 20.0, 30.0]),
            semantics="unknown",
            unit=None,
            name="Intensity",
            metadata_source="test",
        ),
        metadata=SpectrumMetadata(
            technique="epr",
            title=None,
            sample={"id": "S1"},
            unknown_fields=("title", "signal_unit"),
        ),
        provenance=Provenance(
            source_files=(source,),
            canonical_sha256="abc",
            importer_id="epr.test",
            importer_version="1",
        ),
    )


class ScaleOperation:
    operation_id = "test.scale"
    name = "Scale"
    technique = "test"
    version = "1"
    parameters = {"factor": 2.0}
    changes_axis = False
    axis_change_description = None
    changes_signal_semantics = False
    changes_signal_unit = False
    signal_change_description = None

    def apply(self, axis, signal) -> OperationOutput:
        return OperationOutput(
            axis=axis,
            signal=Signal1D(
                values=signal.values * 2.0,
                semantics=signal.semantics,
                unit=signal.unit,
                name=signal.name,
                metadata_source=signal.metadata_source,
            ),
        )


def test_metadata_formatter_raw_and_processed() -> None:
    translator = Translator("en")
    spectrum = _spectrum()
    raw_text = format_metadata(spectrum, translator)
    assert "Raw Spectrum1D" in raw_text
    assert "Unit: unknown" in raw_text
    assert "Sample: {\"id\": \"S1\"}" in raw_text
    assert "ABC" not in raw_text
    assert "Processing history: none" in raw_text

    processed = ProcessingSession(spectrum).apply(ScaleOperation())
    text = format_metadata(processed, translator)
    assert "ProcessedSpectrum" in text
    assert "test.scale" in text
    assert "factor" in text


def test_status_event_resolution_and_validation() -> None:
    translator = Translator("en")
    event = StatusEvent(level="success", key="status.success")
    assert event.message(translator) == "Success"
    payload = status_from_payload({"level": "warning", "text": "careful"})
    assert payload.message(translator) == "careful"
    with pytest.raises(ValueError):
        StatusEvent(level="unknown", text="x")
    with pytest.raises(ValueError):
        status_from_payload("bad")


class FakeImporter:
    id = "test.fake"
    version = "1"
    technique = "test"
    entry_suffixes = (".fake",)

    def probe(self, entry: Path) -> ProbeResult:
        return ProbeResult(True, 1.0, "FAKE", "test", "test")

    def collect_sources(self, entry: Path):
        return ()

    def read(self, request):
        return ImportedDataset(
            spectra=(_spectrum(),),
            primary_index=0,
            format_id="FAKE",
            technique="test",
        )


def test_controller_loads_exactly_one_spectrum(tmp_path: Path) -> None:
    importers = ImporterRegistry()
    importers.register(FakeImporter())
    techniques = TechniqueRegistry()
    techniques.register(_descriptor("dummy"))
    controller = ApplicationController(techniques, importers=importers)
    path = tmp_path / "sample.fake"
    path.write_text("fake\n", encoding="utf-8")
    loaded = controller.load_spectrum(path)
    assert loaded.spectrum.dataset_id == "sample"
    assert loaded.dataset.format_id == "FAKE"
    assert loaded.path == path
