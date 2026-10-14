"""Keybinding table for the TUI.

Maps raw key names (as reported by Textual) to named actions.
No state, no imports from Textual — pure mapping.
"""

from __future__ import annotations

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
    # App
    # Note: Textual reports printable-character keys by their name, not the
    # character itself.  "?" → "question_mark", "/" → "slash".
    "q": "quit",
    "question_mark": "show_help",
    "f2": "show_settings",
    "f5": "rescan_library",
    # Filter / search
    "slash": "activate_filter",
    "escape": "cancel_or_back",
    # Pane focus cycling
    "tab": "cycle_pane_focus",
    "r": "next_library_root",
    # Command palette
    "ctrl+p": "command_palette",
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
    "waveform_seek_confirm": "Confirm seek position",
    "waveform_nav_exit": "Exit waveform navigation",
    "quit": "Quit",
    "show_help": "Show this help overlay",
    "activate_filter": "Search library by name, path, or tag",
    "show_settings": "Audio output and auto-audition settings",
    "rescan_library": "Rescan the active library in the background",
    "cancel_or_back": "Cancel filter / go back",
    "cycle_pane_focus": "Switch Browser / Stage",
    "next_library_root": "Switch to next library root",
    "command_palette": "Open command palette",
}

# Groupings for the HelpScreen display (order preserved).
ACTION_CATEGORIES: dict[str, list[str]] = {
    "Navigation": ["move_up", "move_down", "go_back", "select_or_descend", "enter"],
    "Selection": ["add_to_selection", "remove_from_selection"],
    "Playback": [
        "toggle_playback",
        "resume_playback",
        "waveform_nav_enter",
        "waveform_seek_fine_left",
        "waveform_seek_fine_right",
        "waveform_seek_coarse_left",
        "waveform_seek_coarse_right",
        "waveform_seek_confirm",
        "waveform_nav_exit",
    ],
    "Filter": ["activate_filter", "cancel_or_back"],
    "App": ["quit", "show_help", "show_settings", "rescan_library", "cycle_pane_focus", "next_library_root", "command_palette"],
}


def resolve_key(key: str) -> str | None:
    """Return the action name for a key, or None if unbound."""
    return KEYMAP.get(key)
