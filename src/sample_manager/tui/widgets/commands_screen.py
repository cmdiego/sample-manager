"""Compact next-key hints for leader sequences, anchored above the right footer."""

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
    """Keep the browser visible while a leader sequence owns keyboard input."""

    DEFAULT_CSS = """
    CommandsScreen { align: right bottom; background: transparent; }
    #commands-dialog {
        width: 56; max-width: 80%; height: auto; max-height: 75%;
        margin: 0 1 2 0;
        border: round $accent; background: $surface; padding: 0 1;
    }
    #commands-list { height: auto; max-height: 1fr; border: none; padding: 0; }
    #commands-status { height: auto; max-height: 2; color: $warning; }
    #commands-hint { height: auto; color: $text-muted; }
    """

    def __init__(self, unavailable: Callable[[str], str | None]) -> None:
        """Use live app availability so an indexing completion cannot stale it."""
        super().__init__()
        self._unavailable = unavailable
        self._group: CommandGroup | None = None
        self._group_index = 0

    def compose(self) -> ComposeResult:
        """Use the border for the prefix and reserve the body for possible next keys."""
        with Vertical(id="commands-dialog"):
            yield OptionList(id="commands-list", compact=True)
            yield Static("", id="commands-status", markup=False)
            yield Static("", id="commands-hint", markup=False)

    def on_mount(self) -> None:
        """Show all groups immediately, including before the first library exists."""
        self._render_entries()
        self.query_one(OptionList).focus()

    def _render_entries(self) -> None:
        """Show only continuations of the current sequence, one key per row."""
        options: list[Option] = []
        if self._group is None:
            path = " Leader \\ "
            for group in COMMAND_GROUPS:
                text = Text(f" {group.key} ", style="bold", no_wrap=True, overflow="ellipsis")
                text.append("→ ", style="dim")
                text.append(f"+ {group.title}", style="bold")
                options.append(Option(text, id=group.key))
        else:
            path = f" \\ {self._group.key} · {self._group.title} "
            for key, action in self._group.entries:
                reason = self._unavailable(action)
                text = Text(f" {key} ", style="bold", no_wrap=True, overflow="ellipsis")
                text.append("→ ", style="dim")
                text.append(_SHORT_LABELS.get(action, ACTION_DESCRIPTIONS[action]), style="dim" if reason else "")
                # A small direct-key hint helps users learn shortcuts without
                # turning this sequence popup into the full shortcut reference.
                shortcut = format_key(action_keys(action)[0])
                text.append(f"  ({shortcut})", style="dim")
                # Keep unavailable rows selectable so Enter/click can explain
                # the prerequisite instead of silently skipping the command.
                options.append(Option(text, id=key))
        listing = self.query_one(OptionList)
        listing.clear_options().add_options(options)
        listing.highlighted = self._group_index if self._group is None else 0
        self.query_one("#commands-dialog").border_title = path
        self._set_status("")
        back = "Esc: back" if self._group else "Esc: close"
        self.query_one("#commands-hint", Static).update(
            f"{back} · ⌫: back · ↑↓: choose · ?: help"
        )

    def _set_status(self, text: str) -> None:
        """Only allocate space for a prerequisite or invalid-key hint when needed."""
        status = self.query_one("#commands-status", Static)
        status.update(text)
        status.display = bool(text)

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Explain an unavailable highlighted command without expanding every row."""
        event.stop()
        if self._group is not None:
            action = dict(self._group.entries).get(event.option.id)
            self._set_status(self._unavailable(action) or "" if action else "")

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
                    self._set_status(reason)
                else:
                    self.dismiss(action)
                return
        self._set_status(
            "Choose one of the displayed letters, or use the arrow keys."
        )

    def on_click(self, event) -> None:
        """Dismiss an outside click without forwarding it to the browser below."""
        if not self.query_one("#commands-dialog").region.contains(event.screen_x, event.screen_y):
            event.stop()
            self.dismiss(None)

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


# The corner popup uses concise labels; full Help retains the longer descriptions.
_SHORT_LABELS = {
    "show_metadata": "Inspect directory / sample",
    "stage_new_folder": "New Stage folder",
    "stage_move": "Move Stage item",
    "stage_rename": "Rename Stage folder",
    "toggle_playback": "Play / pause",
    "resume_playback": "Resume paused sample",
    "select_or_descend": "Toggle Stage / enter folder",
    "add_to_selection": "Add to Stage",
    "remove_from_selection": "Remove from Stage",
    "activate_filter": "Search library",
    "show_settings": "Settings",
    "add_library": "Add sample folder",
    "rescan_library": "Rescan library",
    "edit_tags": "Edit sample tags",
    "show_help": "Full shortcut reference",
}
