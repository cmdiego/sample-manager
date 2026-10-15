"""Keybinding table for the TUI.

Maps raw key names (as reported by Textual) to named actions.
No state, no imports from Textual — pure mapping.
"""

from __future__ import annotations

from dataclasses import dataclass

KEYMAP: dict[str, str] = {
    # Vim-style
    "h": "go_back",
    "j": "move_down",
    "k": "move_up",
    "l": "enter",
    # Arrow keys (Textual reports these as "left", "right", "up", "down")
    "left": "go_back",
    "down": "move_down",
    "up": "move_up",
    "right": "enter",
    # Return key — selects focused file or descends into directory
    "enter": "select_or_descend",
    # Selection
    "a": "add_to_selection",
    "d": "remove_from_selection",
    # Playback
    "space": "toggle_playback",
    "ctrl+space": "resume_playback",
    "w": "waveform_nav_enter",
    # App
    # Note: Textual reports printable-character keys by their name, not the
    # character itself.  "?" → "question_mark", "/" → "slash".
    "q": "quit",
    "question_mark": "show_help",
    "backslash": "show_commands",
    "f1": "show_commands",
    "f2": "show_settings",
    "f4": "add_library",
    "f5": "rescan_library",
    "f6": "edit_tags",
    "t": "edit_tags",
    # Filter / search
    "slash": "activate_filter",
    "escape": "cancel_or_back",
    # Pane focus cycling
    "tab": "cycle_pane_focus",
    "r": "next_library_root",
    # Command palette
    "ctrl+p": "command_palette",
}

# These bindings override browsing only while the waveform cursor is active.
# Help and dispatch share this table so contextual shortcuts cannot disappear
# from documentation simply because they are absent from the normal keymap.
WAVEFORM_KEYMAP: dict[str, str] = {
    "left": "waveform_seek_fine_left",
    "h": "waveform_seek_fine_left",
    "right": "waveform_seek_fine_right",
    "l": "waveform_seek_fine_right",
    "shift+left": "waveform_seek_coarse_left",
    "shift+right": "waveform_seek_coarse_right",
    "home": "waveform_seek_home",
    "end": "waveform_seek_end",
    "enter": "waveform_seek_confirm",
    "escape": "waveform_nav_exit",
}

# Human-readable descriptions for each action.
# Used by HelpScreen to render the keybindings panel.
ACTION_DESCRIPTIONS: dict[str, str] = {
    "go_back": "Go back / ascend directory",
    "move_up": "Move cursor up",
    "move_down": "Move cursor down",
    "enter": "Open action pane",
    "select_or_descend": "Select file / descend into directory",
    "add_to_selection": "Add focused item to selection",
    "remove_from_selection": "Remove focused item from selection",
    "toggle_playback": "Pause / resume or play focused sample",
    "resume_playback": "Resume paused sample from checkpoint",
    "waveform_nav_enter": "Enter waveform navigation",
    "waveform_seek_fine_left": "Seek left (fine)",
    "waveform_seek_fine_right": "Seek right (fine)",
    "waveform_seek_coarse_left": "Seek left (coarse)",
    "waveform_seek_coarse_right": "Seek right (coarse)",
    "waveform_seek_home": "Move seek cursor to sample start",
    "waveform_seek_end": "Move seek cursor to sample end",
    "waveform_seek_confirm": "Confirm seek position",
    "waveform_nav_exit": "Exit waveform navigation",
    "quit": "Quit",
    "show_help": "Show this help overlay",
    "show_commands": "Browse commands with the leader key",
    "activate_filter": "Search library by name, path, or tag",
    "show_settings": "Audio output and auto-audition settings",
    "add_library": "Add and index a sample folder",
    "rescan_library": "Rescan the active library in the background",
    "edit_tags": "Edit tags for the focused sample",
    "cancel_or_back": "Cancel filter / go back",
    "cycle_pane_focus": "Switch Browser / Stage",
    "next_library_root": "Switch to next library root",
    "command_palette": "Open command palette",
}

# Groupings for the HelpScreen display (order preserved).
ACTION_CATEGORIES: dict[str, list[str]] = {
    "Navigation": ["move_up", "move_down", "go_back", "select_or_descend", "enter"],
    "Selection": ["add_to_selection", "remove_from_selection", "edit_tags"],
    "Playback": [
        "toggle_playback",
        "resume_playback",
        "waveform_nav_enter",
    ],
    "Waveform (after w)": [
        "waveform_seek_fine_left",
        "waveform_seek_fine_right",
        "waveform_seek_coarse_left",
        "waveform_seek_coarse_right",
        "waveform_seek_home",
        "waveform_seek_end",
        "waveform_seek_confirm",
        "waveform_nav_exit",
    ],
    "Filter": ["activate_filter", "cancel_or_back"],
    "App": ["show_commands", "quit", "show_help", "show_settings", "add_library", "rescan_library", "cycle_pane_focus", "next_library_root", "command_palette"],
}


@dataclass(frozen=True)
class CommandGroup:
    """One leader menu branch; entries pair a mnemonic with an app action."""

    key: str
    title: str
    entries: tuple[tuple[str, str], ...]


# Mnemonics are independent of direct shortcuts: arrows and Return always
# browse the popup, while the displayed letters run a command immediately.
COMMAND_GROUPS: tuple[CommandGroup, ...] = (
    CommandGroup("n", "Navigation", (
        ("u", "move_up"), ("d", "move_down"), ("b", "go_back"),
        ("o", "enter"), ("e", "select_or_descend"), ("p", "cycle_pane_focus"),
    )),
    CommandGroup("s", "Stage & tags", (
        ("a", "add_to_selection"), ("d", "remove_from_selection"), ("t", "edit_tags"),
    )),
    CommandGroup("p", "Playback", (
        ("p", "toggle_playback"), ("r", "resume_playback"), ("w", "waveform_nav_enter"),
    )),
    CommandGroup("w", "Waveform seeking", (
        ("h", "waveform_seek_fine_left"), ("l", "waveform_seek_fine_right"),
        ("b", "waveform_seek_coarse_left"), ("f", "waveform_seek_coarse_right"),
        ("s", "waveform_seek_home"), ("e", "waveform_seek_end"),
        ("c", "waveform_seek_confirm"), ("x", "waveform_nav_exit"),
    )),
    CommandGroup("f", "Search", (
        ("s", "activate_filter"), ("c", "cancel_or_back"),
    )),
    CommandGroup("l", "Libraries", (
        ("a", "add_library"), ("r", "rescan_library"), ("n", "next_library_root"),
    )),
    CommandGroup("a", "App & help", (
        ("s", "show_settings"), ("h", "show_help"),
        ("p", "command_palette"), ("q", "quit"),
    )),
)


def action_keys(action: str) -> tuple[str, ...]:
    """Return real shortcuts, choosing contextual bindings for waveform actions."""
    keymap = WAVEFORM_KEYMAP if action in WAVEFORM_KEYMAP.values() else KEYMAP
    return tuple(key for key, bound_action in keymap.items() if bound_action == action)


def format_key(key: str) -> str:
    """Render Textual key names as familiar labels in both command/help panels."""
    symbols = {
        "up": "↑", "down": "↓", "left": "←", "right": "→",
        "enter": "Return", "escape": "Esc", "tab": "Tab", "space": "Space",
        "backspace": "Backspace", "slash": "/", "backslash": "\\",
        "question_mark": "?", "ctrl": "Ctrl", "shift": "Shift",
    }
    parts = (
        part.upper() if part.startswith("f") and part[1:].isdigit() else symbols.get(part, part)
        for part in key.split("+")
    )
    return "+".join(parts)


def resolve_key(key: str) -> str | None:
    """Return the action name for a key, or None if unbound."""
    return KEYMAP.get(key)
