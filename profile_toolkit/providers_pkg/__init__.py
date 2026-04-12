"""Online profile providers package.

Providers are grouped by category:
    base.py          → OnlineProfileEntry, OnlineProvider (abstract base)
    manufacturers.py → PolymakerProvider, ColorFabbProvider, PrusaResearchProvider
    databases.py     → SimplyPrintDBProvider, OrcaSlicerLibraryProvider, BambuStudioOfficialProvider
    community.py     → CommunityPresetsProvider, SantanachiaProvider, DgaucheFilamentLibProvider
"""

from .base import OnlineProfileEntry, OnlineProvider
from .manufacturers import PolymakerProvider, ColorFabbProvider, PrusaResearchProvider
from .databases import (
    SimplyPrintDBProvider,
    OrcaSlicerLibraryProvider,
    BambuStudioOfficialProvider,
)
from .community import (
    CommunityPresetsProvider,
    SantanachiaProvider,
    DgaucheFilamentLibProvider,
)

# Provider registry — only sources with verified direct-download URLs.
# Sources removed (URLs were HTML pages, not downloadable profiles):
#   eSUN, 3DJake, Coex3D, QIDI, MakerWorld, Printables, 3DFilamentProfiles
ALL_PROVIDERS: list[OnlineProvider] = [
    PrusaResearchProvider(),
    PolymakerProvider(),
    ColorFabbProvider(),
    SimplyPrintDBProvider(),
    OrcaSlicerLibraryProvider(),
    BambuStudioOfficialProvider(),
    CommunityPresetsProvider(),
    SantanachiaProvider(),
    DgaucheFilamentLibProvider(),
]

PROVIDER_CATEGORIES: list[str] = ["Manufacturer", "Database", "Community"]

__all__ = [
    "OnlineProfileEntry",
    "OnlineProvider",
    "PolymakerProvider",
    "ColorFabbProvider",
    "PrusaResearchProvider",
    "SimplyPrintDBProvider",
    "OrcaSlicerLibraryProvider",
    "BambuStudioOfficialProvider",
    "CommunityPresetsProvider",
    "SantanachiaProvider",
    "DgaucheFilamentLibProvider",
    "ALL_PROVIDERS",
    "PROVIDER_CATEGORIES",
]
