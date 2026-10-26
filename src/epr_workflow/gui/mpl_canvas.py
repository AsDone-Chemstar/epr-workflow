"""Matplotlib canvas embedded in Qt, with the standard zoom/pan toolbar.

The toolbar provides zoom (box/rectangle), pan, and "reset to home" out of
the box, which satisfies the zoom / pan / reset requirements without custom
interaction code.
"""

from __future__ import annotations

from matplotlib import font_manager
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

#: Fonts that can render Chinese UI labels. Matplotlib's default (DejaVu Sans)
#: cannot, so Chinese axis labels/titles would otherwise render as empty boxes.
CJK_FONT_CANDIDATES = (
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
    "SimSun",
)


def find_cjk_font() -> str | None:
    """Return an installed font that can render Chinese, or ``None``.

    The font is only used for Chinese text drawn inside the plot; it never
    changes the data or the exported figures written by the CLI.
    """
    try:
        available = {font.name for font in font_manager.fontManager.ttflist}
    except Exception:  # font cache problems must not break the GUI
        return None
    for name in CJK_FONT_CANDIDATES:
        if name in available:
            return name
    return None


class MplCanvas(FigureCanvasQTAgg):
    """A single-axes matplotlib figure hosted in a Qt widget."""

    def __init__(self, parent=None, width: float = 6.0, height: float = 4.5, dpi: int = 100):
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        super().__init__(self.figure)
        self.setParent(parent)
        self.axes = self.figure.add_subplot(111)
        self.cjk_font = find_cjk_font()
