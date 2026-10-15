"""Mounted leader-menu workflows, including input isolation and command parity."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from textual.widgets import Input, Static

from sample_manager.audio import PlaybackStatus, WaveformBin, WaveformData
from sample_manager.tui.app import SampleManagerApp
from sample_manager.tui.keybindings import (
    ACTION_CATEGORIES, COMMAND_GROUPS, KEYMAP, WAVEFORM_KEYMAP, action_keys, format_key,
)
from sample_manager.tui.settings import TuiPreferences
from sample_manager.tui.widgets.add_library_screen import AddLibraryScreen
from sample_manager.tui.widgets.commands_screen import CommandsScreen
from sample_manager.tui.widgets.help_screen import HelpScreen
from sample_manager.tui.widgets.settings_screen import SettingsScreen


class _CommandsApp(SampleManagerApp):
    """Use production screens/routing with an isolated two-file library and player."""

    def __init__(self, root: Path, *, first_run: bool = False) -> None:
        player = Mock()
        player.snapshot.return_value = SimpleNamespace(
            status=PlaybackStatus.IDLE, path=None, duration_seconds=8.0,
            position_seconds=2.0, error=None,
        )
        super().__init__(
            audio_player=player, waveform_service=Mock(),
            preferences=TuiPreferences(auto_audition=False),
            config_path=root.parent / "config.yaml", device_provider=lambda: [],
        )
        self.root, self.first_run = root, first_run
        self.selected = {1, 2}
        self.paths = {1: root / "kick.wav", 2: root / "snare.wav"}

    def _initialize(self) -> None:
        """Avoid user config and SQL while preserving real navigation transitions."""
        if self.first_run:
            return
        data = Mock()
        data.get_indexed_files.return_value = {path.name: sid for sid, path in self.paths.items()}
        data.get_selection_ids.side_effect = lambda: set(self.selected)
        data.get_selection_total_size.return_value = 0
        data.get_active_destination.return_value = None
        data.get_sample_details.side_effect = lambda sid: {"id": sid, "filename": self.paths[sid].name}
        data.get_sample_path.side_effect = self.paths.__getitem__
        data.remove_from_selection.side_effect = self.selected.discard
        data.add_to_selection.side_effect = self.selected.add
        data.search_samples.side_effect = lambda root, query: tuple(
            item for item in self._state.items if query.lower() in item.name.lower()
        )
        self._data = data
        self._library_roots = (self.root,)
        self._load_root(self.root)

    def _request_waveform(self, item, top_display) -> None:
        """Input tests supply waveform data without starting an audio decoder."""


@pytest.fixture
def root(tmp_path):
    """Provide disposable sample paths; no external sample pack is needed."""
    folder = tmp_path / "samples"
    folder.mkdir()
    for name in ("kick.wav", "snare.wav"):
        (folder / name).write_bytes(b"RIFF")
    return folder


def test_leader_metadata_covers_every_action_and_context():
    """Future keybindings must also be discoverable through the leader tree."""
    actions = {action for group in COMMAND_GROUPS for _, action in group.entries}
    assert actions | {"show_commands"} == set(KEYMAP.values()) | set(WAVEFORM_KEYMAP.values())
    assert len({group.key for group in COMMAND_GROUPS}) == len(COMMAND_GROUPS)
    for group in COMMAND_GROUPS:
        assert len({key for key, _ in group.entries}) == len(group.entries)
        assert all(action_keys(action) for _, action in group.entries)
    assert set(WAVEFORM_KEYMAP.values()) <= set(ACTION_CATEGORIES["Waveform (after w)"])
    assert format_key("backslash") == "\\"
    assert format_key("shift+left") == "Shift+←"


def test_leader_drill_down_cancel_and_exactly_once_stage_action(root):
    """Invalid/cancel keys stay in the popup; executing Remove mutates once."""
    async def exercise():
        app = _CommandsApp(root)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("tab", "down")
            assert app._effective_focused_item().sample_id == 2
            await pilot.press("backslash")
            assert isinstance(app.screen, CommandsScreen)
            assert app.screen.query_one("#commands-dialog").region.bottom <= 24
            await pilot.press("s", "z")
            assert app.selected == {1, 2}
            assert "displayed letters" in app.screen.query_one("#commands-status", Static).content
            await pilot.press("escape")
            assert app.screen._group is None
            await pilot.press("escape")
            assert len(app.screen_stack) == 1 and app._active_pane == "stage"
            assert app._effective_focused_item().sample_id == 2
            await pilot.press("backslash", "s", "d")
            await pilot.pause()
            assert len(app.screen_stack) == 1
            assert app.selected == {1}
            app._data.remove_from_selection.assert_called_once_with(2)
    asyncio.run(exercise())


def test_leader_preserves_search_and_can_run_on_the_search_hit(root):
    """Opening/canceling never adds leader text or loses the search cursor."""
    async def exercise():
        app = _CommandsApp(root)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("/", "s", "n")
            await pilot.press("backslash", "s", "escape", "escape")
            assert app._filter_active and app._filter_query == "sn"
            assert app._effective_focused_item().sample_id == 2
            await pilot.press("f1", "s", "d")
            assert app.selected == {1}
            assert app._filter_active and app._filter_query == "sn"
            await pilot.press("space")
            app._audio_player.play_from_start.assert_called_once_with(root / "snare.wav")
    asyncio.run(exercise())


def test_leader_available_on_first_run_and_opens_setup(root):
    """All commands remain visible before indexing; prerequisites explain no-ops."""
    async def exercise():
        app = _CommandsApp(root, first_run=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("backslash", "s", "t")
            assert isinstance(app.screen, CommandsScreen)
            assert "Add a sample folder first" in app.screen.query_one("#commands-status", Static).content
            await pilot.press("escape", "l", "a")
            assert isinstance(app.screen, AddLibraryScreen)
            await pilot.press("escape", "f1", "a", "s")
            assert isinstance(app.screen, SettingsScreen)
    asyncio.run(exercise())


def test_unavailable_commands_explain_scan_audio_and_waveform_prerequisites(root):
    """Visible commands explain temporary and contextual restrictions."""
    async def exercise():
        app = _CommandsApp(root)
        async with app.run_test() as pilot:
            await pilot.pause()
            app._scan_in_progress = True
            await pilot.press("backslash", "l", "r")
            assert "scan is already running" in app.screen.query_one("#commands-status", Static).content
            # Availability is live: do not dismiss/execute a stale enabled row.
            app._scan_in_progress = False
            await pilot.press("n")
            assert "another library" in app.screen.query_one("#commands-status", Static).content
            await pilot.press("escape", "w", "c")
            assert "waveform navigation first" in app.screen.query_one("#commands-status", Static).content
            await pilot.press("escape", "p", "w")
            assert "wait for its waveform" in app.screen.query_one("#commands-status", Static).content
            app._preferences = TuiPreferences(audio_output="disabled")
            await pilot.press("p")
            assert "Enable audio output" in app.screen.query_one("#commands-status", Static).content
            app._audio_player.play_from_start.assert_not_called()
            app._scan_in_progress = False
    asyncio.run(exercise())


def test_leader_waveform_commands_match_direct_shortcuts(root):
    """Menu movement preserves navigation mode/cursor and confirms the same seek."""
    async def exercise():
        app = _CommandsApp(root)
        async with app.run_test() as pilot:
            await pilot.pause()
            app._waveform_data = WaveformData(root / "kick.wav", 8.0, (WaveformBin(-1, 1),))
            await pilot.press("backslash", "p", "w")
            assert app._waveform_nav_active
            assert app._nav_cursor_fraction == 0.25
            await pilot.press("backslash", "w", "escape", "escape")
            assert app._waveform_nav_active and app._nav_cursor_fraction == 0.25
            await pilot.press("backslash", "w", "e")
            assert app._waveform_nav_active and app._nav_cursor_fraction == 1.0
            app._audio_player.seek.assert_not_called()
            await pilot.press("backslash", "w", "c")
            assert not app._waveform_nav_active
            app._audio_player.seek.assert_called_once_with(8.0)
            await pilot.press("w", "home", "right", "escape")
            assert app._nav_cursor_fraction == 1 / (app._nav_display_width // 2)
            app._audio_player.seek.assert_called_once()
    asyncio.run(exercise())


def test_leader_keyboard_list_selection_and_full_help(root):
    """Arrow/Return navigation executes the highlighted action and Help has seek keys."""
    async def exercise():
        app = _CommandsApp(root)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("f1", "end", "enter")  # App & help
            assert app.screen._group.title == "App & help"
            await pilot.press("enter")  # Settings
            assert isinstance(app.screen, SettingsScreen)
            await pilot.press("escape", "f1", "?")
            assert isinstance(app.screen, HelpScreen)
            text = " ".join(widget.content for widget in app.screen.query(Static))
            assert "Waveform (after w)" in text
            assert "Shift+←" in text and "sample start" in text and "F1" in text
            await pilot.press("f1")
            assert isinstance(app.screen, CommandsScreen)
            assert len(app.screen_stack) == 2
            await pilot.press("?", "backslash")
            assert isinstance(app.screen, CommandsScreen)
            assert len(app.screen_stack) == 2
            await pilot.press("escape")
            assert app.is_running and len(app.screen_stack) == 1
    asyncio.run(exercise())


def test_leader_mouse_selection_and_modal_text_ownership(root):
    """Click through menu rows, and keep path backslashes inside actual Inputs."""
    async def exercise():
        app = _CommandsApp(root)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("backslash")
            # The first visible option is Navigation; clicking shares the key path.
            assert await pilot.click("#commands-list", offset=(3, 0))
            assert app.screen._group.title == "Navigation"
            await pilot.press("backslash", "f4")
            assert isinstance(app.screen, AddLibraryScreen)
            field = app.screen.query_one(Input)
            await pilot.press("backslash", "f1")
            assert app.screen.query_one(Input) is field
            assert field.value == "\\"
            assert len(app.screen_stack) == 2
    asyncio.run(exercise())


@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
def test_leader_is_compact_transparent_corner_popup(root, size):
    """Leader hints occupy the lower-right corner and update with the prefix."""
    async def exercise():
        app = _CommandsApp(root)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await pilot.press("backslash")
            popup = app.screen.query_one("#commands-dialog")
            assert popup.region.right == size[0] - 1
            assert popup.region.bottom == size[1] - 2
            assert popup.region.width <= 56
            assert popup.region.height <= 12
            assert app.screen.styles.background.a == 0
            assert "Leader" in popup.border_title
            await pilot.press("s")
            assert "\\ s" in popup.border_title
            assert popup.region.height <= 12
            await pilot.click(offset=(0, 0))
            assert len(app.screen_stack) == 1
            assert app.selected == {1, 2}
    asyncio.run(exercise())


def test_leader_long_group_scrolls_in_small_terminal(root):
    """A short terminal can still reach the last next-key hint with the keyboard."""
    async def exercise():
        app = _CommandsApp(root)
        async with app.run_test(size=(40, 12)) as pilot:
            await pilot.pause()
            await pilot.press("backslash", "w", "end")
            await pilot.pause()
            popup = app.screen.query_one("#commands-dialog")
            listing = app.screen.query_one("#commands-list")
            assert popup.region.right == 39 and popup.region.bottom == 10
            assert listing.highlighted == 7
            assert listing.scroll_y > 0
            await pilot.press("escape", "escape")
            assert len(app.screen_stack) == 1
    asyncio.run(exercise())


def test_f1_toggle_and_quit_require_explicit_menu_command(root):
    """Unknown q does not quit at the group level; App→Quit remains available."""
    async def exercise():
        app = _CommandsApp(root)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f1", "q")
            assert app.is_running and isinstance(app.screen, CommandsScreen)
            await pilot.press("f1")
            assert len(app.screen_stack) == 1
            await pilot.press("backslash", "a", "q")
            await pilot.pause()
            assert not app.is_running
    asyncio.run(exercise())
