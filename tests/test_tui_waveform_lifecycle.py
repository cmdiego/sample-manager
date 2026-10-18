"""Mounted regressions for waveform reuse across selection and async completion."""

from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from textual.widgets import Static

from sample_manager.audio import PlaybackStatus, WaveformBin, WaveformData
from sample_manager.scanner import scan_library
from sample_manager.tui.app import SampleManagerApp
from sample_manager.tui.data import TuiDataSource
from sample_manager.tui.settings import TuiPreferences
from sample_manager.tui.widgets.top_display import TopDisplayWidget
from sample_manager.tui.widgets.waveform import WaveformWidget


class _WaveformApp(SampleManagerApp):
    """Exercise real preview loading with isolated SQL and controlled decode results."""

    def __init__(self, db, root: Path, service) -> None:
        player = Mock()
        player.snapshot.return_value = SimpleNamespace(
            status=PlaybackStatus.IDLE, path=None, duration_seconds=8.0,
            position_seconds=2.0, error=None,
        )
        super().__init__(
            audio_player=player, waveform_service=service,
            preferences=TuiPreferences(auto_audition=False),
        )
        self.test_data = TuiDataSource(db)
        self.root = root

    def _initialize(self) -> None:
        """Install fixture data; keep production refresh/request/worker behavior."""
        self._data = self.test_data
        self._library_roots = (self.root,)
        self._load_root(self.root)


@pytest.fixture
def waveform_env(db, tmp_path):
    """Generate a tiny indexed library without external audio fixtures."""
    root = tmp_path / "samples"
    root.mkdir()
    for name in ("kick.wav", "snare.wav"):
        (root / name).write_bytes(b"RIFF0000")
    scan_library(db, root, fast=True)
    service = Mock()
    service.load.side_effect = lambda path: WaveformData(path, 8.0, (WaveformBin(-0.5, 0.5),))
    return _WaveformApp(db, root, service), service


async def _loaded(app, pilot) -> WaveformWidget:
    """Wait for the real decode worker and pending Textual mounts to settle."""
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()
    return app.query_one(TopDisplayWidget).query_one(WaveformWidget)


def test_repeated_enter_keeps_loaded_waveform_and_decode_count(waveform_env):
    """Selecting/deselecting the same sample never remounts or reloads its waveform."""
    app, service = waveform_env

    async def exercise():
        async with app.run_test() as pilot:
            waveform = await _loaded(app, pilot)
            data = waveform._data
            assert data is not None
            sample_id = app._effective_focused_item().sample_id
            for expected in ({sample_id}, set(), {sample_id}, set()):
                await pilot.press("enter")
                await pilot.pause()
                current = app.query_one(WaveformWidget)
                assert current._data is data
                assert current is waveform
                assert "loading" not in current.render().plain
                assert app.test_data.get_selection_ids() == expected
            service.load.assert_called_once_with(app.root / "kick.wav")
    asyncio.run(exercise())


def test_metadata_refresh_keeps_waveform_progress_and_seek_cursor(waveform_env):
    """Refreshing tags on the same path updates metadata without resetting the waveform."""
    app, service = waveform_env

    async def exercise():
        async with app.run_test() as pilot:
            waveform = await _loaded(app, pilot)
            waveform.set_progress(0.6)
            app._enter_waveform_nav()
            app._waveform_nav_move("end")
            details = app.test_data.get_sample_details(app._effective_focused_item().sample_id)
            details["tags"] = ["New [tag]"]
            preview = app.query_one(TopDisplayWidget)
            preview.update_focus(app._effective_focused_item(), details)
            app._request_waveform(app._effective_focused_item(), preview)
            await pilot.pause()
            assert app.query_one(WaveformWidget) is waveform
            assert waveform._data is app._waveform_data
            assert waveform.nav_cursor_fraction() == 1.0
            # Audio polling uses zero progress for an idle player; explicitly
            # apply progress after it, then verify a synchronous same-path refresh.
            waveform.set_progress(0.6)
            preview.update_focus(app._effective_focused_item(), details)
            app._request_waveform(app._effective_focused_item(), preview)
            assert waveform._progress == 0.6
            assert "New [tag]" in " ".join(str(row.content) for row in preview.query(Static))
            service.load.assert_called_once()
    asyncio.run(exercise())


@pytest.mark.parametrize("decode_error", [False, True])
def test_enter_during_decode_preserves_completion_state(waveform_env, decode_error):
    """Refreshes preserve the in-flight target and its eventual data or error."""
    app, service = waveform_env
    release = Event()

    def decode(path):
        """Hold completion until selection refreshes have happened."""
        if not release.wait(timeout=5):
            raise RuntimeError("Test decoder was not released")
        if decode_error:
            raise ValueError("Unsupported audio fixture")
        return WaveformData(path, 8.0, (WaveformBin(-0.5, 0.5),))

    service.load.side_effect = decode

    async def exercise():
        try:
            async with app.run_test() as pilot:
                await pilot.pause()
                waveform = app.query_one(WaveformWidget)
                await pilot.press("enter", "enter")
                assert app.query_one(WaveformWidget) is waveform
                service.load.assert_called_once()
                release.set()
                await app.workers.wait_for_complete()
                await pilot.pause()
                if decode_error:
                    assert "Unsupported audio fixture" in waveform.render().plain
                else:
                    assert waveform._data is app._waveform_data and waveform._data is not None
                await pilot.press("enter")
                assert app.query_one(WaveformWidget) is waveform
                if decode_error:
                    assert "Unsupported audio fixture" in waveform.render().plain
                else:
                    assert waveform._data is app._waveform_data
                    assert "loading" not in waveform.render().plain
                service.load.assert_called_once()
        finally:
            release.set()
    asyncio.run(exercise())


def test_focus_switch_replaces_waveform_and_ignores_stale_completion(waveform_env):
    """Fast sample changes cannot apply an old sample's decode to the new preview."""
    app, service = waveform_env
    release = Event()

    def decode(path):
        """Delay only the first sample so the second completes first."""
        if path.name == "kick.wav":
            if not release.wait(timeout=5):
                raise RuntimeError("Test decoder was not released")
        return WaveformData(path, 8.0, (WaveformBin(-0.5, 0.5),))

    service.load.side_effect = decode

    async def exercise():
        try:
            async with app.run_test() as pilot:
                await pilot.pause()
                old = app.query_one(WaveformWidget)
                await pilot.press("down")
                await pilot.pause()
                current = app.query_one(WaveformWidget)
                assert current is not old
                assert current.path == app.root / "snare.wav"
                release.set()
                await app.workers.wait_for_complete()
                await pilot.pause()
                assert current._data is not None
                assert current._data.path == app.root / "snare.wav"
                assert "loading" not in current.render().plain
                assert service.load.call_count == 2
        finally:
            release.set()
    asyncio.run(exercise())
