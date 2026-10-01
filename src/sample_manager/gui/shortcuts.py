"""Keyboard shortcut wiring and the canonical shortcut/help table.

Phase 3 fleshes this out to full parity with the terminal TUI. Shortcuts are
declared as data (``SHORTCUT_HELP``) so the help dialog and the wiring stay in
sync, and :func:`install_shortcuts` binds ``{key_sequence: handler}`` onto a
parent widget, returning the created objects keyed by sequence so callers can
selectively enable/disable them (e.g. while a text field has focus).
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget

# Canonical parity table: (key label, human-readable action).
# This is the single source of truth rendered by the help dialog.
SHORTCUT_HELP: tuple[tuple[str, str], ...] = (
    ("J / Down", "Move browser focus down"),
    ("K / Up", "Move browser focus up"),
    ("H / Left", "Navigate to parent directory"),
    ("L / Right", "Enter directory, or open the action dialog for a file"),
    ("Return", "Enter directory, or toggle file selection"),
    ("Space", "Pause playback, or play the focused sample from the start"),
    ("Ctrl+Space", "Resume a paused sample from its last checkpoint"),
    ("A", "Add the focused sample"),
    ("D", "Remove the focused sample"),
    ("/", "Focus the filter field"),
    ("Escape", "Clear the filter, else close the active dialog"),
    ("?", "Open this help dialog"),
    ("Ctrl+P", "Open the command palette"),
    ("Cmd+,", "Open Settings"),
)


def install_shortcuts(
    parent: QWidget,
    handlers: dict[str, Callable[[], None]],
) -> dict[str, QShortcut]:
    """Bind ``{key_sequence: handler}`` on *parent*.

    Returns the created ``QShortcut`` objects keyed by their sequence string so
    the caller can enable/disable a subset (they are parented to *parent*, which
    keeps them alive).
    """
    shortcuts: dict[str, QShortcut] = {}
    for sequence, handler in handlers.items():
        sc = QShortcut(QKeySequence(sequence), parent)
        # Window context: the shortcut fires whenever the main window (or any of
        # its child widgets) holds focus, regardless of which child that is. The
        # window itself guards typing (a focused text field) and suspends these
        # while a dialog is open.
        sc.setContext(Qt.ShortcutContext.WindowShortcut)
        sc.activated.connect(handler)
        shortcuts[sequence] = sc
    return shortcuts
