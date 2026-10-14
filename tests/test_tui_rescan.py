"""Mounted rescan workflows using real files and a file-backed SQLite index."""

from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from sample_manager.audio import PlaybackStatus
from sample_manager.db import Db
from sample_manager.migrations import apply_migrations
from sample_manager.scanner import scan_library
from sample_manager.tui.app import SampleManagerApp
from sample_manager.tui.data import TuiDataSource
from sample_manager.tui.settings import TuiPreferences


class _RescanApp(SampleManagerApp):
    """Use production scanning and navigation without audio or user config."""

    def __init__(self, db, roots) -> None:
        player = Mock()
        player.snapshot.return_value = SimpleNamespace(
            status=PlaybackStatus.IDLE, path=None, duration_seconds=None,
            position_seconds=0.0, error=None,
        )
        super().__init__(audio_player=player, preferences=TuiPreferences(False))
        self.test_data = TuiDataSource(db)
        self.test_roots = roots

    def _initialize(self) -> None:
        """Open the prepared index using the normal root loader."""
        self._data = self.test_data
        self._library_roots = self.test_roots
        self._load_root(self.test_roots[0])

    def _request_waveform(self, item, top_display) -> None:
        """Avoid unrelated decoding threads in scanner tests."""


@pytest.fixture
def rescan_app(tmp_path, monkeypatch):
    """Provide two roots and nested samples indexed before each pilot starts."""
    monkeypatch.setattr("sample_manager.config.DEFAULT_CONFIG_PATH", tmp_path / "unused.yaml")
    first, second = tmp_path / "one", tmp_path / "two"
    (first / "kit").mkdir(parents=True)
    second.mkdir()
    (first / "kit" / "kick.wav").write_bytes(b"RIFF0000")
    (first / "kit" / "snare.wav").write_bytes(b"RIFF1111")
    db = Db(tmp_path / "index.sqlite3")
    db.connect()
    apply_migrations(db)
    scan_library(db, first, fast=True)
    scan_library(db, second, fast=True)
    yield _RescanApp(db, (first, second))
    db.close()


async def _finish_scan(app) -> None:
    """Wait for the real Textual worker with a bound that catches deadlocks."""
    await asyncio.wait_for(app.workers.wait_for_complete(), timeout=3)


def test_f5_refreshes_nested_files_stage_and_active_search(rescan_app):
    """Reconcile additions/deletions while preserving folder and focused path."""
    async def exercise():
        app = rescan_app
        root = app.test_roots[0]
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("right")
            assert app._state.current_dir == root / "kit"
            focused_path = app._state.focused_item.path
            snare = app.test_data.search_samples(root, "snare")[0]
            app.test_data.add_to_selection(snare.sample_id)
            app._refresh_ui(audition=False)
            (root / "kit" / "hat.wav").write_bytes(b"RIFF2222")
            snare.path.unlink()

            await pilot.press("f5")
            await _finish_scan(app)
            assert not app._scan_in_progress
            assert app._state.current_dir == root / "kit"
            assert app._state.focused_item.path == focused_path
            assert [item.name for item in app._state.items] == ["hat.wav", "kick.wav"]
            assert app.test_data.get_selection_ids() == set()
            assert app._stage_items == ()
            app._audio_player.play.assert_not_called()

            # A query that initially has no hits must gain new files after F5,
            # without clearing its text or changing its active input mode.
            await pilot.press("slash", *"Clap")
            assert not app._visible_items()
            (root / "kit" / "Clap.wav").write_bytes(b"RIFF3333")
            await pilot.press("f5")
            await _finish_scan(app)
            assert app._filter_active and app._filter_query == "Clap"
            assert [item.name for item in app._visible_items()] == ["Clap.wav"]

    asyncio.run(exercise())


def test_scan_does_not_block_navigation_or_start_twice(rescan_app, monkeypatch):
    """A held scanner permits root navigation and ignores repeated F5."""
    entered, release = Event(), Event()
    app = rescan_app
    original = app.test_data.scan_directory
    calls = []

    def slow_scan(root):
        """Hold the worker thread until the pilot has navigated elsewhere."""
        calls.append(root)
        entered.set()
        if not release.wait(timeout=3):
            raise TimeoutError("Pilot did not release scanner")
        return original(root)

    monkeypatch.setattr(app.test_data, "scan_directory", slow_scan)

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("f5")
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                await pilot.press("f5", "r")
                assert app._state.current_root == app.test_roots[1]
                assert app._scan_in_progress
                assert calls == [app.test_roots[0]]
            finally:
                release.set()
            await _finish_scan(app)
            assert app._state.current_root == app.test_roots[1]
            assert not app._scan_in_progress

    asyncio.run(exercise())


def test_failed_scan_can_retry_and_missing_viewed_folder_recovers(rescan_app, monkeypatch):
    """A failed job leaves the view usable; a successful retry handles deletion."""
    async def exercise():
        app = rescan_app
        original = app.test_data.scan_directory
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("right")
            before = app._state.current_dir
            monkeypatch.setattr(app.test_data, "scan_directory", Mock(side_effect=OSError("offline")))
            await pilot.press("f5")
            await _finish_scan(app)
            assert not app._scan_in_progress
            assert "Scan failed: offline" in app._scan_message
            assert app._state.current_dir == before

            monkeypatch.setattr(app.test_data, "scan_directory", original)
            for path in before.iterdir():
                path.unlink()
            before.rmdir()
            await pilot.press("f5")
            await _finish_scan(app)
            assert app._state.current_dir == app.test_roots[0]
            assert not app._state.items
            assert app._state.dir_stack == ()
            assert "removed" in app._scan_message

    asyncio.run(exercise())
