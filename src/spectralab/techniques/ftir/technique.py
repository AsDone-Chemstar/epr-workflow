"""Explicit registration of the M9 FTIR text importers."""

from spectralab.core.importers import ImporterRegistry
from spectralab.techniques.ftir.importers import (
    GenericCSVImporter,
    GenericTXTImporter,
)

FTIR_IMPORTERS = (GenericCSVImporter(), GenericTXTImporter())


def register_ftir_importers(
    registry: ImporterRegistry,
    *,
    replace: bool = False,
) -> ImporterRegistry:
    """Register the M9 CSV and TXT/DPT importers explicitly."""
    for importer in FTIR_IMPORTERS:
        registry.register(importer, replace=replace)
    return registry


__all__ = ["FTIR_IMPORTERS", "register_ftir_importers"]
