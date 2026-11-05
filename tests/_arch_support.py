"""Shared helpers for the consolidated architecture test suite.

Each architecture domain runs in its own fresh Python subprocess. Results are
cached at session scope so multiple assertions can share one expensive import
without weakening process isolation.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"

DOMAINS = ("core", "epr", "ftir", "gui", "cli_legacy")


@dataclass(frozen=True)
class ArchResult:
    domain: str
    returncode: int
    stdout: str
    stderr: str
    payload: dict[str, Any]
    duration_seconds: float

    def require_ok(self) -> "ArchResult":
        assert self.returncode == 0, (
            f"Architecture domain {self.domain!r} failed with exit code "
            f"{self.returncode}.\nSTDERR:\n{self.stderr}\nSTDOUT:\n{self.stdout}"
        )
        assert self.payload, (
            f"Architecture domain {self.domain!r} produced no RESULT payload."
        )
        return self

    def value(self, key: str) -> Any:
        self.require_ok()
        assert key in self.payload, (
            f"Architecture domain {self.domain!r} did not report {key!r}. "
            f"Payload keys: {sorted(self.payload)}"
        )
        return self.payload[key]


def _script(body: str) -> str:
    return (
        "import importlib\n"
        "import json\n"
        "import pkgutil\n"
        "import sys\n"
        f"sys.path.insert(0, {str(SRC)!r})\n"
        + body
    )


_CORE_SCRIPT = _script(
    """
import spectralab.core as package
modules = []
for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
    importlib.import_module(info.name)
    modules.append(info.name)

def loaded(prefixes):
    return sorted(
        name for name in sys.modules
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)
    )

from spectralab.core.importers import ImporterRegistry
payload = {
    'modules': modules,
    'qt': loaded(('PySide6', 'PyQt5', 'PyQt6')),
    'legacy': loaded(('epr_workflow',)),
    'app': loaded(('spectralab.app',)),
    'techniques': loaded(('spectralab.techniques',)),
    'matplotlib': loaded(('matplotlib',)),
    'registry_count': len(ImporterRegistry().importers),
}
print('RESULT=' + json.dumps(payload, sort_keys=True))
"""
)

_EPR_SCRIPT = _script(
    """
import spectralab.techniques.epr as package
modules = []
for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
    importlib.import_module(info.name)
    modules.append(info.name)
import spectralab.core.processing.session
import spectralab.core.plotting.renderer

def loaded(prefixes):
    return sorted(
        name for name in sys.modules
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)
    )

payload = {
    'modules': modules,
    'qt': loaded(('PySide6', 'PyQt5', 'PyQt6')),
    'legacy': loaded(('epr_workflow',)),
    'ftir': loaded(('spectralab.techniques.ftir',)),
}
print('RESULT=' + json.dumps(payload, sort_keys=True))
"""
)

_FTIR_SCRIPT = _script(
    """
import spectralab.techniques.ftir as package
modules = []
for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
    importlib.import_module(info.name)
    modules.append(info.name)

def loaded(prefixes):
    return sorted(
        name for name in sys.modules
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)
    )

payload = {
    'modules': modules,
    'qt': loaded(('PySide6', 'PyQt5', 'PyQt6')),
    'matplotlib': loaded(('matplotlib',)),
    'legacy': loaded(('epr_workflow',)),
    'app': loaded(('spectralab.app',)),
    'epr': loaded(('spectralab.techniques.epr',)),
}
print('RESULT=' + json.dumps(payload, sort_keys=True))
"""
)

_GUI_SCRIPT = _script(
    """
import spectralab.app.gui.app as gui_app
import spectralab.app.gui.main_window
import spectralab.app.gui.epr_panel
import spectralab.app.gui.ftir_panel
import spectralab.app.gui.ftir_import_dialog
import spectralab.app.gui.ftir_options_widget

registry = gui_app.build_technique_registry()
payload = {
    'ids': list(registry.ids),
    'panels': {
        technique_id: registry.get(technique_id).panel_factory.__module__
        for technique_id in registry.ids
    },
    'legacy': sorted(
        name for name in sys.modules
        if name == 'epr_workflow' or name.startswith('epr_workflow.')
    ),
    'qt_loaded': any(
        name == 'PySide6' or name.startswith(('PySide6.', 'PyQt5', 'PyQt6'))
        for name in sys.modules
    ),
}
print('RESULT=' + json.dumps(payload, sort_keys=True))
"""
)

_CLI_LEGACY_SCRIPT = _script(
    """
import spectralab.app.gui.controller
import spectralab.app.gui.i18n
import spectralab.app.gui.metadata
import spectralab.app.gui.settings
import spectralab.app.gui.status
import spectralab.app.gui.technique

def loaded(prefixes):
    return sorted(
        name for name in sys.modules
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)
    )

qfree_qt = loaded(('PySide6', 'PyQt5', 'PyQt6'))
qfree_legacy = loaded(('epr_workflow',))

from spectralab.app.registry import build_importer_registry
import spectralab.app.cli
import spectralab.app.batch
importer_ids = [item.id for item in build_importer_registry().importers]
app_qt = loaded(('PySide6', 'PyQt5', 'PyQt6'))
app_legacy = loaded(('epr_workflow',))

import epr_workflow
from epr_workflow.plot_asc import main as old_main, read_dataset
from epr_workflow.preprocessing import PreprocessingSession
import epr_workflow.gui

payload = {
    'qfree_qt': qfree_qt,
    'qfree_legacy': qfree_legacy,
    'importer_ids': importer_ids,
    'app_qt': app_qt,
    'app_legacy': app_legacy,
    'version': epr_workflow.__version__,
    'old_api': all(
        callable(item) for item in (old_main, read_dataset, PreprocessingSession)
    ),
    'old_gui_ok': callable(epr_workflow.gui.load_spectrum),
    'legacy_loaded_after': loaded(('epr_workflow',)),
    'qt_after_legacy': loaded(('PySide6', 'PyQt5', 'PyQt6')),
}
print('RESULT=' + json.dumps(payload, sort_keys=True))
"""
)

_SCRIPTS = {
    "core": _CORE_SCRIPT,
    "epr": _EPR_SCRIPT,
    "ftir": _FTIR_SCRIPT,
    "gui": _GUI_SCRIPT,
    "cli_legacy": _CLI_LEGACY_SCRIPT,
}


class ArchRunner:
    """Run each architecture domain once per test session."""

    def __init__(self, *, timeout: int = 180) -> None:
        self._timeout = timeout
        self._cache: dict[str, ArchResult] = {}

    def run(self, domain: str) -> ArchResult:
        if domain not in _SCRIPTS:
            raise KeyError(f"Unknown architecture domain: {domain!r}")
        cached = self._cache.get(domain)
        if cached is not None:
            return cached
        started = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-c", _SCRIPTS[domain]],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=self._timeout,
        )
        duration = time.perf_counter() - started
        payload: dict[str, Any] = {}
        for line in result.stdout.splitlines():
            if line.startswith("RESULT="):
                payload = json.loads(line[len("RESULT=") :])
        arch_result = ArchResult(
            domain=domain,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            payload=payload,
            duration_seconds=duration,
        )
        self._cache[domain] = arch_result
        return arch_result

    @property
    def measured_domains(self) -> tuple[ArchResult, ...]:
        return tuple(self._cache[domain] for domain in DOMAINS if domain in self._cache)


# ---------------------------------------------------------------------------
# Static import/file helpers
# ---------------------------------------------------------------------------
def python_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def imports(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.module, node.lineno))
    return found


def import_offenders(
    root: Path,
    forbidden_prefixes: tuple[str, ...],
) -> list[str]:
    offenders: list[str] = []
    for path in python_files(root):
        for module, line in imports(path):
            if module.startswith(forbidden_prefixes):
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)}:{line} imports {module}"
                )
    return offenders


def text_offenders(root: Path, tokens: tuple[str, ...]) -> list[str]:
    offenders: list[str] = []
    for path in python_files(root):
        text = path.read_text(encoding="utf-8")
        for token in tokens:
            if token in text:
                offenders.append(
                    f"{path.relative_to(PROJECT_ROOT)} contains {token!r}"
                )
    return offenders


def module_name(path: Path) -> str:
    relative = path.relative_to(SRC).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def top_level_dependencies(path: Path, known: set[str]) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    dependencies: set[str] = set()
    for node in tree.body:
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            if not name.startswith("epr_workflow"):
                continue
            if name in known:
                dependencies.add(name)
                continue
            parts = name.split(".")
            for index in range(len(parts), 0, -1):
                candidate = ".".join(parts[:index])
                if candidate in known:
                    dependencies.add(candidate)
                    break
    return dependencies


def import_cycles(files: list[Path]) -> list[list[str]]:
    known = {module_name(path) for path in files}
    graph = {
        module_name(path): top_level_dependencies(path, known)
        for path in files
    }
    visited: set[str] = set()
    stack: list[str] = []
    cycles: list[list[str]] = []

    def visit(node: str) -> None:
        if node in stack:
            start = stack.index(node)
            cycles.append(stack[start:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        stack.append(node)
        for dependency in sorted(graph.get(node, ())):
            visit(dependency)
        stack.pop()

    for node in sorted(graph):
        visit(node)
    return cycles


__all__ = [
    "ArchResult",
    "ArchRunner",
    "DOMAINS",
    "PROJECT_ROOT",
    "SRC",
    "import_cycles",
    "import_offenders",
    "imports",
    "module_name",
    "python_files",
    "text_offenders",
]
