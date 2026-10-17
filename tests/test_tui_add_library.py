"""First-run and existing-library Add Folder workflows in the mounted TUI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from textual.events import Paste
from textual.widgets import Input, Static

from sample_manager.audio import PlaybackStatus
from sample_manager.config import load_config, normalize_config
from sample_manager.tui.app import SampleManagerApp
from sample_manager.tui.settings import TuiPreferences
from sample_manager.tui.widgets.add_library_screen import AddLibraryScreen
from sample_manager.tui.widgets.help_screen import HelpScreen


class _OnboardingApp(SampleManagerApp):
    """Exercise real configuration, SQLite, and scanning without audio devices."""

    def __init__(self, config_path: Path) -> None:
        player = Mock()
        player.snapshot.return_value = SimpleNamespace(
            status=PlaybackStatus.IDLE, path=None, duration_seconds=None,
            position_seconds=0.0, error=None,
        )
        super().__init__(
            audio_player=player, preferences=TuiPreferences(False), config_path=config_path,
        )

    def _request_waveform(self, item, top_display) -> None:
        """Keep decoder threads separate from the onboarding contract."""


@pytest.fixture
def onboarding(tmp_path, monkeypatch):
    """Redirect all default paths into a temporary home and create nested audio."""
    home = tmp_path / "home"
    home.mkdir()
    config_path = home / ".sample_manager" / "config.yaml"
    monkeypatch.setenv("HOME", str(home))
    # Windows expands ~ from USERPROFILE rather than HOME.
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr("sample_manager.config.DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr("sample_manager.config.DEFAULT_CONFIG_DIR", config_path.parent)
    root = home / "Music" / "Drum Packs"
    (root / "loops").mkdir(parents=True)
    (root / "loops" / "Drum Loop.wave").write_bytes(b"RIFF0000")
    return config_path, root


async def _add_folder(app, pilot, path: str) -> None:
    """Paste into the real modal input and submit through its Enter event."""
    await pilot.press("f4")
    assert isinstance(app.screen, AddLibraryScreen)
    app.screen.query_one(Input).post_message(Paste(path))
    await pilot.pause()
    await pilot.press("enter")
    await asyncio.wait_for(app.workers.wait_for_complete(), timeout=3)


def test_fresh_tui_adds_nested_library_and_reopens_it(onboarding):
    """No CLI initialization is needed before Add Folder, search, or reopening."""
    config_path, root = onboarding

    async def exercise():
        app = _OnboardingApp(config_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert app._state is None and not config_path.exists()
            await _add_folder(app, pilot, '"~/Music/Drum Packs"')
            assert app._state.current_root == root
            config = normalize_config(load_config(config_path))
            assert config["library_roots"] == [str(root)]
            assert config["default_library_root"] == str(root)
            assert Path(config["db_path"]).is_file()
            assert (Path(config["profiles_dir"]) / "export_profiles.yaml").is_file()
            await pilot.press("slash", *"Drum")
            assert [item.name for item in app._visible_items()] == ["Drum Loop.wave"]
            app._audio_player.play.assert_not_called()

        reopened = _OnboardingApp(config_path)
        async with reopened.run_test() as pilot:
            await pilot.pause()
            assert reopened._state.current_root == root

    asyncio.run(exercise())


def test_invalid_path_and_cancel_do_not_initialize_storage(onboarding):
    """Failed validation stays editable and Escape creates no config or DB."""
    config_path, root = onboarding

    async def exercise():
        app = _OnboardingApp(config_path)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("f4", "enter")
            assert isinstance(app.screen, AddLibraryScreen)
            assert "Enter a sample folder" in app.screen.query_one("#add-library-error", Static).content
            field = app.screen.query_one(Input)
            for invalid in (root / "missing", root / "loops" / "Drum Loop.wave"):
                field.value = str(invalid)
                await pilot.press("enter")
                assert isinstance(app.screen, AddLibraryScreen)
                assert "not a directory" in app.screen.query_one("#add-library-error", Static).content
            await pilot.press("q")
            assert app.is_running
            await pilot.press("escape")
            assert not isinstance(app.screen, AddLibraryScreen)
            assert not config_path.exists()
            assert app._db is None

    asyncio.run(exercise())


def test_adding_another_folder_preserves_stage_and_rejects_failed_scan(onboarding, monkeypatch):
    """New roots are idempotent, retain Stage, and persist only after success."""
    config_path, first = onboarding
    second = first.parent / "New Kit"
    second.mkdir()
    (second / "snare.wav").write_bytes(b"RIFF1111")
    failed = first.parent / "Offline"
    failed.mkdir()

    async def exercise():
        app = _OnboardingApp(config_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            await _add_folder(app, pilot, str(first))
            sid = app._data.search_samples(first, "Drum")[0].sample_id
            app._data.add_to_selection(sid)
            await _add_folder(app, pilot, str(second))
            await _add_folder(app, pilot, str(second))
            assert len(app._data.get_library_roots()) == 2
            assert app._data.get_selection_ids() == {sid}
            assert app._state.current_root == second
            await pilot.press("r")
            assert app._state.current_root == first
            assert load_config(config_path)["default_library_root"] == str(second)

            monkeypatch.setattr(app._data, "scan_directory", Mock(side_effect=OSError("offline")))
            await _add_folder(app, pilot, str(failed))
            assert app._state.current_root == first
            assert str(failed) not in load_config(config_path)["library_roots"]
            assert "Scan failed" in app._scan_message
            assert app._data.get_selection_ids() == {sid}

    asyncio.run(exercise())


def test_help_and_quit_work_before_the_first_library_is_added(onboarding):
    """First-run users can discover controls and quit without configuring storage."""
    config_path, _root = onboarding

    async def exercise():
        app = _OnboardingApp(config_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app._state is None
            await pilot.press("?")
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape", "q")
            await pilot.pause()
            assert not app.is_running
            assert not config_path.exists()

    asyncio.run(exercise())
