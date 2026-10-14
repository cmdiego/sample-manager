"""Help screen — modal overlay listing all keybindings by category.

Displayed when the user presses '?'. Derives its content directly from
keybindings.KEYMAP, ACTION_CATEGORIES, and ACTION_DESCRIPTIONS so that
it always stays in sync with the real bindings — no second copy.

Dismissed by pressing '?', 'escape', or 'q'.

CSS for this widget lives in styles/app.tcss (no inline DEFAULT_CSS).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from ..keybindings import ACTION_CATEGORIES, ACTION_DESCRIPTIONS, KEYMAP


def _build_inverted_keymap() -> dict[str, list[str]]:
    """Return action → [key, key, ...] derived from KEYMAP.

    Keys are listed in KEYMAP definition order so the most prominent
    binding (vim key) appears first.
    """
    inverted: dict[str, list[str]] = {}
    for key, action in KEYMAP.items():
        inverted.setdefault(action, []).append(key)
    return inverted


class HelpScreen(ModalScreen):
    """Modal overlay that lists keybindings grouped by category.

    Content is generated from keybindings.py constants — never hardcoded here.
    Follows the same ModalScreen pattern as ActionPane.
    """

    def compose(self) -> ComposeResult:
        inverted = _build_inverted_keymap()
        with VerticalScroll(classes="help-container"):
            yield Static("  Sample Manager", classes="help-title")
            yield Static("", classes="help-spacer")

            for category, actions in ACTION_CATEGORIES.items():
                yield Static(f"  {category}", classes="help-category")
                for action in actions:
                    if action not in inverted:
                        continue
                    # Format keys as "j / ↓" style — replace arrow names with symbols
                    raw_keys = inverted[action]
                    display_keys = [_fmt_key(k) for k in raw_keys]
                    keys_str = "  /  ".join(display_keys)
                    desc = ACTION_DESCRIPTIONS.get(action, action)
                    yield Static(
                        f"    {keys_str:<22} {desc}",
                        classes="help-row",
                    )
                yield Static("", classes="help-spacer")

            yield Static("  How to use:", classes="help-category")
            yield Static(
                "    Browse your sample library with j/k or ↑/↓.",
                classes="help-row",
            )
            yield Static(
                "    Press Return on a file to select it; on a directory to enter it.",
                classes="help-row",
            )
            yield Static(
                "    Use a / d to add or remove. Press / to search the whole library.",
                classes="help-row",
            )
            yield Static(
                "    Press l or → to open the action pane for a focused file.",
                classes="help-row",
            )
            yield Static(
                "    Tab switches Browser/Stage; arrows move, Return or d removes in Stage.",
                classes="help-row",
            )
            yield Static(
                "    Press r to cycle indexed library roots.",
                classes="help-row",
            )
            yield Static(
                "    F2 Settings · F4 Add Folder · F5 Rescan current library.",
                classes="help-row",
            )
            yield Static(
                "    Paste a query, or Shift+Space for spaces; Esc clears search.",
                classes="help-row",
            )
            yield Static("", classes="help-spacer")
            yield Static(
                "  Press  ?  /  Escape  /  q  to close",
                classes="help-hint",
            )

    def on_key(self, event) -> None:
        # Textual reports '?' as "question_mark" in event.key.
        # Stop the event after dismissing so it does not bubble to the app
        # and re-open the help overlay.
        if event.key in ("escape", "q", "question_mark"):
            event.stop()
            self.dismiss()


_KEY_SYMBOLS: dict[str, str] = {
    "up": "↑",
    "down": "↓",
    "left": "←",
    "right": "→",
    "enter": "Return",
    "escape": "Esc",
    "tab": "Tab",
    "backspace": "Backspace",
}


def _fmt_key(key: str) -> str:
    """Return a display-friendly representation of a key name."""
    return _KEY_SYMBOLS.get(key, key)
