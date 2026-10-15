"""Help screen — modal overlay listing all keybindings by category.

Displayed when the user presses '?'. Derives its content directly from
keybindings metadata, including waveform context bindings, so that it
stays in sync with the real shortcuts.

Dismissed by pressing '?', 'escape', or 'q'; backslash/F1 switches to commands.

CSS for this widget lives in styles/app.tcss (no inline DEFAULT_CSS).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from ..keybindings import ACTION_CATEGORIES, ACTION_DESCRIPTIONS, action_keys, format_key


class HelpScreen(ModalScreen):
    """Modal overlay that lists keybindings grouped by category.

    Content is generated from keybindings.py constants — never hardcoded here.
    Follows the same ModalScreen pattern as ActionPane.
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="help-container"):
            yield Static("  Sample Manager", classes="help-title")
            yield Static("", classes="help-spacer")

            for category, actions in ACTION_CATEGORIES.items():
                yield Static(f"  {category}", classes="help-category")
                for action in actions:
                    # Format keys as "j / ↓" style — replace arrow names with symbols
                    display_keys = [format_key(k) for k in action_keys(action)]
                    keys_str = "  /  ".join(display_keys)
                    desc = ACTION_DESCRIPTIONS.get(action, action)
                    yield Static(
                        f"    {keys_str:<22} {desc}",
                        classes="help-row",
                    )
                yield Static("", classes="help-spacer")

            yield Static("  How to use:", classes="help-category")
            yield Static(
                "    Press \\ or F1 to browse commands, then choose a group and action.",
                classes="help-row",
            )
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
                "    F6 or t edits the focused sample's tags in Browser or Stage.",
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
