"""Navigation state model for the TUI file browser.

The implementation now lives in the framework-neutral service layer
(``sample_manager.services.navigation``) so it can be shared with the Qt GUI.
This module re-exports it to keep existing Textual imports working unchanged.
"""

from __future__ import annotations

from ..services.navigation import (  # noqa: F401
    NavItem,
    NavState,
    _to_rel_norm,
    build_items,
)

__all__ = ["NavItem", "NavState", "build_items", "_to_rel_norm"]
