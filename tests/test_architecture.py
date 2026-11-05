"""Consolidated architecture boundary checks for SpectraLab.

Each runtime domain is cached at session scope, while five independent
subprocesses preserve import-environment isolation. Every assertion from the
previous M0-M10 architecture files is mapped into this suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from _arch_support import (
    PROJECT_ROOT,
    SRC,
    ArchRunner,
    import_cycles,
    import_offenders,
    imports,
    python_files,
    text_offenders,
)

CORE = SRC / "spectralab" / "core"
TECHNIQUES = SRC / "spectralab" / "techniques"
APP = SRC / "spectralab" / "app"
GUI = APP / "gui"
LEGACY = SRC / "epr_workflow"

GENERIC_GUI_FILES = (
    GUI / "main_window.py",
    GUI / "controller.py",
    GUI / "file_filter.py",
    GUI / "technique.py",
    GUI / "settings.py",
    GUI / "i18n.py",
    GUI / "metadata.py",
    GUI / "metadata_view.py",
    GUI / "status.py",
    GUI / "status_view.py",
)
EPR_PANEL = GUI / "epr_panel.py"
FTIR_GUI_FILES = (
    GUI / "ftir_panel.py",
    GUI / "ftir_import_dialog.py",
    GUI / "ftir_options_widget.py",
    GUI / "ftir_translations.py",
)

CORE_FORBIDDEN = (
    "PySide6",
    "PyQt5",
    "PyQt6",
    "matplotlib",
    "epr_workflow",
    "spectralab.app",
    "spectralab.gui",
    "spectralab.techniques",
)


@pytest.fixture(scope="session")
def arch() -> ArchRunner:
    return ArchRunner()


def _assert_no_offenders(offenders: list[str], message: str) -> None:
    assert not offenders, message + "\n" + "\n".join(offenders)


# ---------------------------------------------------------------------------
# Static import and text boundaries
# ---------------------------------------------------------------------------
def test_core_modules_have_no_forbidden_imports() -> None:
    _assert_no_offenders(
        import_offenders(CORE, CORE_FORBIDDEN),
        "Neutral core imports a forbidden module:",
    )


def test_core_has_no_technique_specific_text() -> None:
    groups = {
        CORE / "export": ("field_G", "intensity", "CW-EPR"),
        CORE / "processing": (
            "field_G",
            "magnetic_field",
            "Field [G]",
            "CW-EPR",
        ),
        CORE / "plotting": (
            "field_G",
            "intensity",
            "magnetic_field",
            "Field [G]",
            "CW-EPR",
        ),
    }
    for root, tokens in groups.items():
        _assert_no_offenders(
            text_offenders(root, tokens),
            f"Technique-specific text in core module {root.name!r}:",
        )


def test_technique_modules_have_no_forbidden_imports() -> None:
    common = (
        "PySide6",
        "PyQt5",
        "PyQt6",
        "matplotlib",
        "epr_workflow",
        "spectralab.app",
        "spectralab.gui",
    )
    cross = {
        "epr": ("spectralab.techniques.ftir",),
        "ftir": ("spectralab.techniques.epr",),
    }
    offenders: list[str] = []
    for package in ("epr", "ftir"):
        root = TECHNIQUES / package
        offenders.extend(
            import_offenders(root, common + cross[package])
        )
    _assert_no_offenders(
        offenders,
        "Technique backend imports app, GUI, Qt, Matplotlib, legacy or the "
        "other technique:",
    )


def test_app_cli_batch_have_no_qt_legacy_or_epr_fields() -> None:
    files = (APP / "cli.py", APP / "batch.py", APP / "__main__.py")
    forbidden_imports = (
        "PySide6",
        "PyQt5",
        "PyQt6",
        "epr_workflow",
        "spectralab.gui",
        "spectralab.app.gui",
    )
    offenders: list[str] = []
    for path in files:
        for module, line in imports(path):
            if module.startswith(forbidden_imports):
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)}:{line} imports {module}"
                )
        text = path.read_text(encoding="utf-8")
        for token in ("field_G", "intensity", "magnetic_field", "CW-EPR"):
            if token in text:
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)} contains {token!r}"
                )
    _assert_no_offenders(offenders, "CLI/batch violates a GUI/EPR boundary:")


def test_legacy_non_gui_has_no_qt_or_gui_imports() -> None:
    offenders: list[str] = []
    for path in python_files(LEGACY):
        if "gui" in path.relative_to(LEGACY).parts:
            continue
        for module, line in imports(path):
            if module.startswith(
                ("PySide6", "PyQt5", "PyQt6", "epr_workflow.gui")
            ):
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)}:{line} imports {module}"
                )
    _assert_no_offenders(offenders, "Legacy non-GUI code imports Qt or GUI:")


def test_legacy_module_import_graph_has_no_cycles() -> None:
    cycles = import_cycles(python_files(LEGACY))
    assert not cycles, "Legacy module-level import cycle(s):\n" + "\n".join(
        " -> ".join(cycle) for cycle in cycles
    )


def test_spectralab_has_no_runtime_epr_workflow_imports() -> None:
    _assert_no_offenders(
        import_offenders(
            SRC / "spectralab",
            ("epr_workflow",),
        ),
        "SpectraLab imports the legacy EPR package:",
    )


def test_generic_gui_has_no_technique_or_legacy_imports() -> None:
    offenders: list[str] = []
    forbidden = (
        "spectralab.techniques",
        "spectralab.app.gui.ftir",
        "epr_workflow",
    )
    for path in GENERIC_GUI_FILES:
        for module, line in imports(path):
            if module.startswith(forbidden):
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)}:{line} imports {module}"
                )
    _assert_no_offenders(offenders, "Generic GUI imports a concrete technique:")


def test_epr_panel_has_no_legacy_or_ftir_imports() -> None:
    _assert_no_offenders(
        [
            f"{path.relative_to(PROJECT_ROOT)}:{line} imports {module}"
            for module, line in imports(EPR_PANEL)
            if module.startswith(("epr_workflow", "spectralab.techniques.ftir"))
        ],
        "EPR panel imports legacy or FTIR code:",
    )


def test_ftir_gui_has_no_epr_or_legacy_imports() -> None:
    offenders: list[str] = []
    for path in FTIR_GUI_FILES:
        for module, line in imports(path):
            if module.startswith(
                (
                    "epr_workflow",
                    "spectralab.techniques.epr",
                    "spectralab.app.gui.epr",
                )
            ):
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)}:{line} imports {module}"
                )
    _assert_no_offenders(offenders, "FTIR GUI imports EPR or legacy code:")


def test_ftir_gui_is_app_layer_and_backend_has_no_gui_directory() -> None:
    assert all(path.parent == GUI and path.is_file() for path in FTIR_GUI_FILES)
    backend_gui = [
        path
        for path in python_files(TECHNIQUES / "ftir")
        if "gui" in path.parts
    ]
    _assert_no_offenders(
        [str(path.relative_to(PROJECT_ROOT)) for path in backend_gui],
        "FTIR backend contains GUI modules:",
    )


# ---------------------------------------------------------------------------
# Isolated runtime domains
# ---------------------------------------------------------------------------
def test_core_import_domain_is_isolated(arch: ArchRunner) -> None:
    result = arch.run("core")
    assert result.value("modules"), "Core domain imported no core modules."
    assert result.value("qt") == []
    assert result.value("legacy") == []
    assert result.value("app") == []
    assert result.value("techniques") == []
    assert result.value("matplotlib") == []


def test_core_registry_has_no_implicit_importers(arch: ArchRunner) -> None:
    assert arch.run("core").value("registry_count") == 0


def test_epr_backend_import_domain_is_isolated(arch: ArchRunner) -> None:
    result = arch.run("epr")
    assert result.value("modules"), "EPR domain imported no EPR modules."
    assert result.value("qt") == []
    assert result.value("legacy") == []
    assert result.value("ftir") == []


def test_ftir_backend_import_domain_is_isolated(arch: ArchRunner) -> None:
    result = arch.run("ftir")
    assert result.value("modules"), "FTIR domain imported no FTIR modules."
    assert result.value("qt") == []
    assert result.value("matplotlib") == []
    assert result.value("legacy") == []
    assert result.value("app") == []
    assert result.value("epr") == []


def test_gui_composition_root_registers_epr_and_ftir(arch: ArchRunner) -> None:
    result = arch.run("gui")
    assert result.value("ids") == ["epr", "ftir"]
    assert result.value("panels") == {
        "epr": "spectralab.app.gui.epr_panel",
        "ftir": "spectralab.app.gui.ftir_panel",
    }
    assert result.value("qt_loaded") is True


def test_gui_runtime_has_no_legacy_import(arch: ArchRunner) -> None:
    assert arch.run("gui").value("legacy") == []


def test_qfree_gui_and_cli_import_without_qt_or_legacy(
    arch: ArchRunner,
) -> None:
    result = arch.run("cli_legacy")
    assert result.value("qfree_qt") == []
    assert result.value("qfree_legacy") == []
    assert result.value("app_qt") == []
    assert result.value("app_legacy") == []


def test_app_importer_registry_is_explicit(arch: ArchRunner) -> None:
    assert arch.run("cli_legacy").value("importer_ids") == [
        "epr.xepr_asc",
        "epr.bes3t",
        "ftir.csv",
        "ftir.txt",
    ]


def test_legacy_gui_and_old_api_remain_importable(arch: ArchRunner) -> None:
    result = arch.run("cli_legacy")
    assert result.value("version") == "0.2.0"
    assert result.value("old_api") is True
    assert result.value("old_gui_ok") is True
    assert result.value("legacy_loaded_after"), "Legacy package was not loaded."
    assert result.value("qt_after_legacy") == []
