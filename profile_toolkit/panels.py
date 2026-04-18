"""Backward-compatible re-export shim.

The three panel classes that lived here have been split into their own
modules for maintainability:

    detail_panel.py  → ProfileDetailPanel
    list_panel.py    → ProfileListPanel
    compare_panel.py → ComparePanel

All existing ``from .panels import …`` statements continue to work.
"""

from .detail_panel import ProfileDetailPanel
from .list_panel import ProfileListPanel
from .compare_panel import ComparePanel

__all__ = ["ProfileDetailPanel", "ProfileListPanel", "ComparePanel"]
