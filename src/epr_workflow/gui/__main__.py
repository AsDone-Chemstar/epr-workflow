"""Allow ``python -m epr_workflow.gui`` to launch the desktop GUI."""

from epr_workflow.gui.app import main

if __name__ == "__main__":
    raise SystemExit(main())
