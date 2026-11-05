"""Application-level importer registry construction.

This module is the explicit integration point: it knows which technique
modules exist, while ``spectralab.core`` knows none of them.
"""

from spectralab.core.importers import ImporterRegistry
from spectralab.techniques.epr import register_epr_importers
from spectralab.techniques.ftir import register_ftir_importers


def build_importer_registry() -> ImporterRegistry:
    """Return a fresh registry containing the currently supported importers.

    M9 adds the generic FTIR CSV/TXT/DPT importers alongside the M2 EPR ASC
    and BES3T importers. Registration stays explicit and deterministic; the
    core never imports technique packages. A fresh registry is created on
    demand so tests and applications can choose their own registrations.
    """
    registry = ImporterRegistry()
    register_epr_importers(registry)
    register_ftir_importers(registry)
    return registry


__all__ = ["build_importer_registry"]
