"""Backward-compatible re-export shim.

Provider classes have been split into the ``providers_pkg`` package:

    providers_pkg/base.py          → OnlineProfileEntry, OnlineProvider
    providers_pkg/manufacturers.py → PolymakerProvider, ColorFabbProvider, PrusaResearchProvider
    providers_pkg/databases.py     → SimplyPrintDBProvider, OrcaSlicerLibraryProvider, BambuStudioOfficialProvider
    providers_pkg/community.py     → CommunityPresetsProvider, SantanachiaProvider, DgaucheFilamentLibProvider

All existing ``from .providers import …`` statements continue to work.
"""

from .providers_pkg import (  # noqa: F401
    OnlineProfileEntry,
    OnlineProvider,
    PolymakerProvider,
    ColorFabbProvider,
    PrusaResearchProvider,
    SimplyPrintDBProvider,
    OrcaSlicerLibraryProvider,
    BambuStudioOfficialProvider,
    CommunityPresetsProvider,
    SantanachiaProvider,
    DgaucheFilamentLibProvider,
    ALL_PROVIDERS,
    PROVIDER_CATEGORIES,
)
