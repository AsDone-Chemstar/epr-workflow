"""Launch the EPR workflow desktop GUI.

Run from the project root with:

    .\.venv\Scripts\python.exe run_gui.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from epr_workflow.gui.app import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
