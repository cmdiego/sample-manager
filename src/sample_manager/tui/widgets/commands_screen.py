"""Persistent leader-key command discovery with executable, grouped hints."""

from __future__ import annotations

from typing import Callable

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from ..keybindings import (
    ACTION_DESCRIPTIONS, COMMAND_GROUPS, CommandGroup, action_keys, format_key,
)


class CommandsScreen(ModalScreen[str | None]):
    """Browse without a timeout; return an action only on explicit selection."""

    DEFAULT_CSS = """
    CommandsScreen { align: center middle; }
    #commands-dialog {
        width: 86; max-width: 95%; height: 24; max-height: 95%;
        border: round $accent; background: $surface; padding: 0 2;
    }
    #commands-title { height: 1; text-style: bold; color: $warning; }
    #commands-path { height: 2; color: $text-muted; }
    #commands-list { height: 1fr; }
    #commands-status { height: 2; color: $warning; }
    #commands-hint { height: 2; color: $text-muted; }
    """

    def __init__(self, unavailable: Callable[[str], str | None]) -> None:
        """Use live app availability so an indexing completion cannot stale it."""
        super().__init__()
        self._unavailable = unavailable
        self._group: CommandGroup | None = None
        self._group_index = 0

    def compose(self) -> ComposeResult:
        """Keep navigation instructions visible while a long command list scrolls."""
        with Vertical(id="commands-dialog"):
            yield Static("Commands", id="commands-title")
            yield Static("", id="commands-path", markup=False)
            yield OptionList(id="commands-list")
            yield Static("", id="commands-status", markup=False)
            yield Static("", id="commands-hint", markup=False)

    def on_mount(self) -> None:
        """Show all groups immediately, including before the first library exists."""
        self._render_entries()
        self.query_one(OptionList).focus()

    def _render_entries(self) -> None:
        """Derive labels and real shortcut hints from the shared keybinding data."""
        options: list[Option] = []
        if self._group is None:
            path = "\\  Choose a group"
            for group in COMMAND_GROUPS:
                text = Text(f" {group.key}  ", style="bold cyan")
                text.append(group.title, style="bold")
                text.append(f"  · {len(group.entries)} commands", style="dim")
                options.append(Option(text, id=group.key))
        else:
            path = f"\\ › {self._group.key}  {self._group.title}"
            for key, action in self._group.entries:
                reason = self._unavailable(action)
                text = Text(f" {key}  ", style="bold cyan")
                text.append(ACTION_DESCRIPTIONS[action], style="dim" if reason else "")
                shortcuts = " / ".join(format_key(k) for k in action_keys(action))
                text.append(f"\n    Shortcut: {shortcuts}", style="dim")
                if reason:
                    text.append(f" · {reason}", style="dim")
                # Keep unavailable rows selectable so Enter/click can explain
                # the prerequisite instead of silently skipping the command.
                options.append(Option(text, id=key))
        listing = self.query_one(OptionList)
        listing.clear_options().add_options(options)
        listing.highlighted = self._group_index if self._group is None else 0
        self.query_one("#commands-path", Static).update(path)
        self.query_one("#commands-status", Static).update("")
        back = "Esc: back" if self._group else "Esc: close"
        self.query_one("#commands-hint", Static).update(
            f"Letter or ↑/↓ + Enter to choose · Click also works\n"
            f"{back} · \\ / F1: close · ?: all shortcuts"
        )

    def _choose(self, key: str) -> None:
        """Drill into a group, explain prerequisites, or dismiss with an action."""
        if self._group is None:
            for index, group in enumerate(COMMAND_GROUPS):
                if group.key == key:
                    self._group, self._group_index = group, index
                    self._render_entries()
                    return
        else:
            for mnemonic, action in self._group.entries:
                if mnemonic != key:
                    continue
                reason = self._unavailable(action)
                if reason:
                    self.query_one("#commands-status", Static).update(reason)
                else:
                    self.dismiss(action)
                return
        self.query_one("#commands-status", Static).update(
            "Choose one of the displayed letters, or use the arrow keys."
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Share the mnemonic path with arrow/Return and mouse selection."""
        event.stop()
        if event.option.id is not None:
            self._choose(event.option.id)

    def on_key(self, event) -> None:
        """Contain every popup keystroke, including the one that dismisses it."""
        if event.key in ("up", "down", "home", "end", "pageup", "pagedown", "enter", "tab", "shift+tab"):
            return  # Let OptionList handle browsing, scrolling, and selection.
        event.stop()
        event.prevent_default()
        if event.key == "backslash":
            self.dismiss(None)
        elif event.key in ("escape", "backspace"):
            if self._group is not None:
                self._group = None
                self._render_entries()
            else:
                self.dismiss(None)
        elif event.key == "question_mark":
            self.dismiss("show_help")
        elif event.character and event.character.isprintable():
            self._choose(event.character)
