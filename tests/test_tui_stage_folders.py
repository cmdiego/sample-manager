"""Hierarchical Stage workflows using a real SQLite adapter and Textual keys."""

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from textual.widgets import Input, Static

from sample_manager.audio import PlaybackStatus
from sample_manager.db import Db
from sample_manager.migrations import apply_migrations
from sample_manager.scanner import scan_library
from sample_manager.tui.app import SampleManagerApp
from sample_manager.tui.data import TuiDataSource
from sample_manager.tui.widgets.stage_path_screen import StagePathScreen


class _StageApp(SampleManagerApp):
    """Use the real Stage service without accessing user config or audio devices."""

    def __init__(self, db, roots):
        """Keep source files and persistence within the disposable fixture."""
        player = Mock()
        player.snapshot.return_value = SimpleNamespace(status=PlaybackStatus.IDLE, path=None, duration_seconds=None, position_seconds=0.0, error=None)
        super().__init__(audio_player=player, waveform_service=Mock())
        self.test_data, self.roots = TuiDataSource(db), roots

    def _initialize(self):
        """Install fixture data through production root loading and refresh."""
        self._data, self._library_roots = self.test_data, self.roots
        self._load_root(self.roots[0])

    def _request_waveform(self, item, top_display):
        """Leave waveform lifecycle testing to its own focused suite."""

    def _audition_focused(self):
        """Keep folder operations independent of hardware playback."""


@pytest.fixture
def stage_env(tmp_path, monkeypatch):
    """Seed two roots to verify a shared virtual destination across libraries."""
    monkeypatch.setattr("sample_manager.config.DEFAULT_CONFIG_PATH", tmp_path / "unused.yaml")
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    for path in (one / "kick.wav", one / "snare.wav", two / "hat.wav"):
        path.write_bytes(b"RIFF sample fixture")
    db = Db(tmp_path / "index.sqlite3")
    apply_migrations(db)
    for root in (one, two):
        scan_library(db, root, fast=True)
    yield db, (one, two)
    db.close()


async def _submit(app, pilot, value):
    """Submit a real modal form and wait for the post-dismiss refresh."""
    assert isinstance(app.screen, StagePathScreen)
    app.screen.query_one(Input).value = value
    await pilot.press("enter")
    await pilot.pause()


def test_create_nested_stage_move_rename_and_cross_root_additions(stage_env):
    """Users can organize samples into persistent virtual folders entirely by keys."""
    db, roots = stage_env
    before = {path: path.read_bytes() for root in roots for path in root.iterdir()}

    async def exercise():
        app = _StageApp(db, roots)
        workspace = app.test_data.stage_workspace
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            original_browser = app._state
            await pilot.press("f7")
            await _submit(app, pilot, "Drums/Kicks")
            assert app._active_pane == "stage"
            assert workspace.path(app._stage_current_folder_id) == "/Drums/Kicks"
            assert app._stage_entries[0]["is_parent"]
            assert app._state == original_browser
            await pilot.press("tab", "enter")
            kick = app._effective_focused_item().sample_id
            assert workspace.placements()[kick] == app._stage_current_folder_id
            await pilot.press("tab", "down", "m")
            await _submit(app, pilot, "/Kits/Set A")
            assert workspace.path(app._stage_current_folder_id) == "/Kits/Set A"
            assert app._effective_focused_item().sample_id == kick
            assert app.query_one("#selection-list").border_subtitle == "/Kits/Set A"
            await pilot.press("left", "e")
            await _submit(app, pilot, "Set B")
            assert app._effective_focused_item().name == "Set B"
            await pilot.press("enter")
            assert workspace.path(app._stage_current_folder_id) == "/Kits/Set B"
            await pilot.press("tab", "r", "enter")
            hat = app._effective_focused_item().sample_id
            assert workspace.placements()[hat] == app._stage_current_folder_id
            await pilot.press("tab")
            assert {item.sample_id for item in app._stage_items if not item.is_dir} == {kick, hat}
            assert "Stage · 2" in app.query_one("#selection-list").border_title
            await pilot.press("left", "d")  # Nonempty folder must survive.
            assert any(row["name"] == "Set B" for row in workspace.folders())
            await pilot.press("n")
            await _submit(app, pilot, "Empty")
            await pilot.press("left", "d")
            assert not any(row["name"] == "Empty" for row in workspace.folders())
            assert set(workspace.placements()) == {kick, hat}
            # Virtual folder i navigates Stage and never opens /Kits on disk.
            await pilot.press("i")
            assert len(app.screen_stack) == 1
        return workspace.placements()

    placements = asyncio.run(exercise())
    restarted = _StageApp(db, roots)
    assert restarted.test_data.stage_workspace.placements() == placements
    assert {path: path.read_bytes() for root in roots for path in root.iterdir()} == before
    assert not (roots[0] / "Drums").exists()


def test_stage_forms_cancel_validation_and_cycle_are_inert(stage_env):
    """Cancel and rejected forms preserve sample IDs, paths, cursor and search."""
    db, roots = stage_env

    async def exercise():
        app = _StageApp(db, roots)
        workspace = app.test_data.stage_workspace
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("/", "k", "f7")
            await pilot.press("q")  # This must be input text, never app quit.
            assert app.screen.query_one(Input).value == "q"
            await pilot.press("escape")
            assert app._filter_active and app._filter_query == "k"
            assert app._active_pane == "browser" and workspace.folders() == []
            await pilot.press("f7")
            await _submit(app, pilot, "Drums/../Invalid")
            assert isinstance(app.screen, StagePathScreen)
            assert workspace.folders() == []
            await _submit(app, pilot, "/Drums/Kicks")
            assert not app._filter_active
            await pilot.press("left", "left")  # Root focuses Drums.
            assert app._effective_focused_item().name == "Drums"
            saved = workspace.folders()
            await pilot.press("m")
            await _submit(app, pilot, "/Drums/Kicks/Invalid")
            assert isinstance(app.screen, StagePathScreen)
            assert "subfolders" in app.screen.query_one("#stage-path-error", Static).content
            assert workspace.folders() == saved
            await pilot.press("escape")
            assert app._effective_focused_item().name == "Drums"
            await pilot.press("right", "down", "enter")
            assert workspace.path(app._stage_current_folder_id) == "/Drums/Kicks"

    asyncio.run(exercise())


def test_external_stage_clear_recovers_stale_destination(stage_env):
    """A CLI/GUI clear cannot leave folder dialogs targeting deleted IDs."""
    from sample_manager.repos.selection_repo import SelectionRepo

    db, roots = stage_env

    async def exercise():
        app = _StageApp(db, roots)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("f7")
            await _submit(app, pilot, "Drums/Kicks")
            SelectionRepo(db).clear()  # Simulate a different client clearing Stage.
            await pilot.press("n")
            assert app.is_running and app._stage_current_folder_id is None
            assert len(app.screen_stack) == 1
            await pilot.press("n")
            await _submit(app, pilot, "Fresh/Subfolder")
            assert app.test_data.stage_workspace.path(app._stage_current_folder_id) == "/Fresh/Subfolder"

    asyncio.run(exercise())
