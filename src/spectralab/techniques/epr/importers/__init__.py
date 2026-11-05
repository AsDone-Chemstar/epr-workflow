"""Explicitly registered legacy EPR importers for M2."""

from spectralab.core.importers import ImporterRegistry
from spectralab.techniques.epr.importers.bes3t import (
    BES3TImporter,
    Bes3tImporter,
)
from spectralab.techniques.epr.importers.xepr_asc import (
    XeprASCImporter,
    XeprAscImporter,
)

EPR_IMPORTERS = (XeprAscImporter(), Bes3tImporter())


def register_epr_importers(
    registry: ImporterRegistry,
    *,
    replace: bool = False,
) -> ImporterRegistry:
    """Register the M2 ASC and BES3T importers explicitly."""
    for importer in EPR_IMPORTERS:
        registry.register(importer, replace=replace)
    return registry


__all__ = [
    "BES3TImporter",
    "EPR_IMPORTERS",
    "Bes3tImporter",
    "XeprASCImporter",
    "XeprAscImporter",
    "register_epr_importers",
]
