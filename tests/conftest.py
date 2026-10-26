"""Shared pytest configuration for the Qt-based GUI tests.

The GUI tests create ``QApplication`` instances in several modules. If Qt is
left alive with open windows until interpreter shutdown, the process can abort
*after* all tests pass (observed on Windows as exit code ``0xC0000409``).
Closing the top-level windows and quitting Qt here makes pytest's exit code
reflect the actual test result.
"""

from __future__ import annotations

import os


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ANN001
    if not os.environ.get("QT_QPA_PLATFORM"):
        return
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return
    try:
        for widget in app.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        app.closeAllWindows()
        app.processEvents()
        app.quit()
    except Exception:
        # Never turn a teardown problem into a test failure.
        pass
