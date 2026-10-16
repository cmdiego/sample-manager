"""TUI wiring for milestone 2: post-scan backfill and DB-backed waveforms."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from sample_manager.audio import PlaybackStatus
from sample_manager.audio.decode import decode
from sample_manager.db import Db
from sample_manager.migrations import apply_migrations
from sample_manager.scanner import scan_library
from sample_manager.services.sample_analysis import StoredWaveformService
from sample_manager.tui.app import SampleManagerApp
from sample_manager.tui.data import TuiDataSource
from sample_manager.tui.settings import TuiPreferences


class CountingDecoder:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        return decode(path)


class _AnalysisApp(SampleManagerApp):
    def __init__(self, db, root, waveforms) -> None:
        player = Mock()
        player.snapshot.return_value = SimpleNamespace(
            status=PlaybackStatus.IDLE, path=None, duration_seconds=None,
            position_seconds=0.0, error=None,
        )
        super().__init__(
            audio_player=player, preferences=TuiPreferences(False), waveform_service=waveforms,
        )
        self.test_db = db
        self.test_root = root

    def _initialize(self) -> None:
        self._db = self.test_db
        self._bind_analysis_database()
        self._data = TuiDataSource(self.test_db)
        self._library_roots = (self.test_root,)
        self._load_root(self.test_root)


@pytest.fixture
def analysis_app(tmp_path, monkeypatch):
    monkeypatch.setattr("sample_manager.config.DEFAULT_CONFIG_PATH", tmp_path / "unused.yaml")
    root = tmp_path / "lib"
    root.mkdir()
    tone = (0.5 * np.sin(np.linspace(0, 200, 24000))).astype("float32")
    for name in ("a_kick.wav", "b_snare.wav"):
        sf.write(root / name, tone, 48000)
    db = Db(tmp_path / "index.sqlite3")
    db.connect()
    apply_migrations(db)
    scan_library(db, root)
    decoder = CountingDecoder()
    waveforms = StoredWaveformService(decoder=decoder)
    yield _AnalysisApp(db, root, waveforms), decoder, db
    db.close()


async def _settle(app) -> None:
    await asyncio.wait_for(app.workers.wait_for_complete(), timeout=5)


def test_rescan_backfills_analysis_and_focus_reads_it_back(analysis_app):
    app, decoder, db = analysis_app

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            await _settle(app)
            # The initial focus decoded once and queued its row.
            app._waveform_service.flush(5)
            assert len(decoder.calls) == 1

            await pilot.press("f5")
            await _settle(app)
            await _settle(app)  # the backfill worker starts after the scan worker
            assert db.fetchval("SELECT COUNT(*) FROM sample_analysis") == 2

            calls_before = len(decoder.calls)
            await pilot.press("down")
            await _settle(app)
            assert app._waveform_path.name == "b_snare.wav"
            assert app._waveform_data is not None
            assert app._waveform_data.path.name == "b_snare.wav"
            assert len(app._waveform_data.bins) == 4096
            assert len(decoder.calls) == calls_before  # served from SQLite

    asyncio.run(exercise())


def test_unmount_cancels_backfill_and_closes_the_writer(analysis_app):
    app, _decoder, _db = analysis_app

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()

    asyncio.run(exercise())
    assert app._analysis_cancel.is_set()
    with pytest.raises(RuntimeError):
        app._waveform_service._writer.submit(lambda: None)
