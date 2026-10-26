"""Application entry point for the EPR workflow desktop GUI."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from epr_workflow.gui.main_window import MainWindow, default_settings


def main(argv: list[str] | None = None) -> int:
    app = QApplication(argv if argv is not None else sys.argv)
    window = MainWindow(settings=default_settings())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
