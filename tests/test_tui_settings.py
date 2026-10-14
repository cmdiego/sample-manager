"""TUI preferences persistence, real modal input, and playback contracts."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from textual.widgets import Button, Select, Static, Switch

from sample_manager.audio import AudioOutputDevice, PlaybackStatus
from sample_manager.config import load_config, save_config
from sample_manager.tui.app import SampleManagerApp
from sample_manager.tui.nav_state import NavItem, NavState
from sample_manager.tui.settings import (
    TuiPreferences, load_tui_preferences, save_tui_preferences,
)
from sample_manager.tui.widgets.settings_screen import SettingsScreen


def _player():
    """Provide an idle player whose calls never touch audio hardware."""
    player = Mock()
    player.snapshot.return_value = SimpleNamespace(
        status=PlaybackStatus.IDLE, path=None, duration_seconds=None,
        position_seconds=0.0, error=None,
    )
    return player


class _SettingsApp(SampleManagerApp):
    """Mount the real modal without opening the user's database or settings."""

    def _initialize(self) -> None:
        """Use an empty browser state so hidden commands would still be routed."""
        self._state = NavState.initial(Path("/library"), [])

    def _refresh_ui(self, **kwargs) -> None:
        """The settings pilot needs no database-backed list refresh."""


def test_preferences_preserve_existing_config_and_round_trip(tmp_path):
    """Saving TUI preferences preserves both shared and future settings keys."""
    path = tmp_path / "config.yaml"
    save_config({"custom": [1, 2], "tui": {"future": "keep"}}, path)
    expected = TuiPreferences(False, "device:7")
    save_tui_preferences(expected, path)
    assert load_tui_preferences(path) == expected
    saved = load_config(path)
    assert saved["custom"] == [1, 2]
    assert saved["tui"]["future"] == "keep"
    assert load_tui_preferences(tmp_path / "missing.yaml") == TuiPreferences()


def test_invalid_saved_preferences_fall_back_to_usable_defaults(tmp_path):
    """Old or manually edited configuration values cannot create invalid output."""
    path = tmp_path / "config.yaml"
    save_config({"tui": {"auto_audition": "false", "audio_output": "device:bad"}}, path)
    assert load_tui_preferences(path) == TuiPreferences()


def test_f2_settings_save_applies_output_and_isolates_keys(tmp_path):
    """Real modal controls save at 80×24 without leaking q or Space to Browser."""
    async def exercise():
        path = tmp_path / "config.yaml"
        save_config({"custom": "retained"}, path)
        original, replacement = _player(), _player()
        factory = Mock(return_value=replacement)
        app = _SettingsApp(
            audio_player=original, preferences=TuiPreferences(),
            player_factory=factory, config_path=path,
            device_provider=lambda: (
                AudioOutputDevice(7, "Studio Interface", "CoreAudio", 2, 48000, False),
            ),
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("f2")
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen)
            app._filter_active, app._filter_query = True, "Drum"
            await pilot.press("q")
            assert app.is_running and app._filter_query == "Drum"

            # Select the discovered output through the actual Select popup.
            output = app.screen.query_one(Select)
            output.focus()
            await pilot.press("enter", "down", "enter")
            assert output.value == "device:7"
            switch = app.screen.query_one(Switch)
            switch.focus()
            await pilot.press("space")
            assert not switch.value
            original.pause.assert_not_called()
            original.play.assert_not_called()

            save = app.screen.query_one("#tui-settings-save", Button)
            assert save.region.bottom <= app.size.height
            await pilot.click("#tui-settings-save")
            await pilot.pause()
            assert not isinstance(app.screen, SettingsScreen)
            assert load_tui_preferences(path) == TuiPreferences(False, "device:7")
            assert load_config(path)["custom"] == "retained"
            assert app._audio_player is replacement
            original.close.assert_called_once()
            factory.assert_called_once_with(TuiPreferences(False, "device:7"))

    asyncio.run(exercise())


def test_settings_cancel_preserves_preferences_when_discovery_fails(tmp_path):
    """Settings remains usable without devices and Escape discards edits."""
    async def exercise():
        path = tmp_path / "config.yaml"
        save_tui_preferences(TuiPreferences(), path)
        before = path.read_bytes()
        factory = Mock()
        app = _SettingsApp(
            audio_player=_player(), preferences=TuiPreferences(), config_path=path,
            player_factory=factory, device_provider=Mock(side_effect=RuntimeError("offline")),
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("f2")
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen)
            assert any("offline" in str(widget.content) for widget in app.screen.query(Static))
            app.screen.query_one(Select).value = "disabled"
            app.screen.query_one(Switch).focus()
            await pilot.press("space", "escape")
            await pilot.pause()
            assert not isinstance(app.screen, SettingsScreen)
            assert path.read_bytes() == before
            assert app._preferences == TuiPreferences()
            factory.assert_not_called()

    asyncio.run(exercise())


def test_settings_save_error_keeps_edits_visible(tmp_path):
    """A write error stays in the modal so the user can retry or cancel."""
    async def exercise():
        path = tmp_path / "config.yaml"
        path.mkdir()  # A directory cannot be overwritten as a YAML config file.
        app = _SettingsApp(
            audio_player=_player(), preferences=TuiPreferences(),
            config_path=path, device_provider=lambda: (),
        )
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("f2")
            app.screen.query_one(Switch).value = False
            await pilot.click("#tui-settings-save")
            await pilot.pause()
            assert isinstance(app.screen, SettingsScreen)
            assert not app.screen.query_one(Switch).value
            assert "Could not save settings" in app.screen.query_one(
                "#tui-settings-error", Static
            ).content
            assert app._preferences == TuiPreferences()

    asyncio.run(exercise())


def test_save_failure_keeps_old_player_and_closes_unused_replacement(tmp_path, monkeypatch):
    """A failed config write leaves current playback and preferences intact."""
    original, replacement = _player(), _player()
    app = _SettingsApp(
        audio_player=original, preferences=TuiPreferences(),
        player_factory=Mock(return_value=replacement), config_path=tmp_path / "config.yaml",
    )
    monkeypatch.setattr(
        "sample_manager.tui.app.save_tui_preferences", Mock(side_effect=OSError("read only"))
    )
    try:
        app._apply_preferences(TuiPreferences(False, "disabled"), persist=True)
    except OSError:
        pass
    else:
        raise AssertionError("Expected the save failure")
    assert app._audio_player is original
    assert app._preferences == TuiPreferences()
    original.close.assert_not_called()
    replacement.close.assert_called_once()


def test_auto_audition_off_preserves_manual_playback_and_disabled_output_is_silent():
    """Preferences affect automatic audition without removing manual transport."""
    player = _player()
    app = _SettingsApp(audio_player=player, preferences=TuiPreferences(False))
    item = NavItem("kick.wav", Path("/library/kick.wav"), False, 1, False)
    app._state = NavState.initial(Path("/library"), [item])
    app._set_status = Mock()
    app._audition_focused()
    player.play.assert_not_called()
    app._toggle_playback()
    player.play_from_start.assert_called_once_with(item.path)
    player.reset_mock()
    app._preferences = TuiPreferences(True, "disabled")
    app._audition_focused()
    app._toggle_playback()
    app._resume_playback()
    player.play.assert_not_called()
    player.play_from_start.assert_not_called()
    player.pause.assert_not_called()
