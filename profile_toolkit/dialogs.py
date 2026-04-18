"""Backward-compatible re-export shim.

Dialog classes have been split into their own modules:

    recommendations_dialog.py → RecommendationsDialog
    online_import_wizard.py   → OnlineImportWizard
    batch_rename_dialog.py    → BatchRenameDialog
    prusa_bundle_wizard.py    → PrusaBundleWizard

All existing ``from .dialogs import …`` statements continue to work.
"""

from .recommendations_dialog import RecommendationsDialog
from .online_import_wizard import OnlineImportWizard
from .batch_rename_dialog import BatchRenameDialog
from .prusa_bundle_wizard import PrusaBundleWizard

__all__ = [
    "RecommendationsDialog",
    "OnlineImportWizard",
    "BatchRenameDialog",
    "PrusaBundleWizard",
]
