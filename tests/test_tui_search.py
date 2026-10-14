"""Mounted TUI search checks with a real indexed, nested sample library."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from textual.events import Paste
from textual.widgets import Static

from sample_manager.audio import PlaybackStatus
from sample_manager.scanner import scan_library
from sample_manager.tui.app import SampleManagerApp
from sample_manager.tui.data import TuiDataSource
from sample_manager.tui.widgets.filters_panel import FiltersPanel


class _SearchApp(SampleManagerApp):
    """Use the production TUI and SQLite adapter without an audio device."""

    def __init__(self, db, root: Path) -> None:
        player = Mock()
        player.snapshot.return_value = SimpleNamespace(
            status=PlaybackStatus.IDLE, path=None, duration_seconds=None,
            position_seconds=0.0, error=None,
        )
        super().__init__(audio_player=player, waveform_service=Mock())
        self.test_data = TuiDataSource(db)
        self.root = root

    def _initialize(self) -> None:
        """Mount the indexed fixture without reading user configuration."""
        self._data = self.test_data
        self._library_roots = (self.root,)
        self._load_root(self.root)

    def _request_waveform(self, item, top_display) -> None:
        """Keep decoder threads outside input and search tests."""


@pytest.fixture
def search_app(db, tmp_path, monkeypatch):
    """Build nested indexed files whose names resemble the user's sample."""
    monkeypatch.setattr(
        "sample_manager.config.DEFAULT_CONFIG_PATH", tmp_path / "unused.yaml"
    )
    root = tmp_path / "library"
    pack = root / "Funky_Disco" / "loops"
    pack.mkdir(parents=True)
    (pack / "FL_FDS_09_Drum_Loop_Full_98.wave").write_bytes(b"RIFF0000")
    (pack / "bass.wav").write_bytes(b"RIFF1111")
    scan_library(db, root, fast=True)
    return _SearchApp(db, root)


def test_activation_slash_is_not_query_and_nested_hit_can_be_selected(search_app):
    """Search from the root finds a nested sample and Return stages that hit."""
    async def exercise():
        async with search_app.run_test() as pilot:
            await pilot.pause()
            directory_items = search_app._state.items
            await pilot.press("slash", "slash", "D", "r", "u", "m")
            await pilot.pause()
            assert search_app._filter_query == "Drum"
            hits = search_app._visible_items()
            assert len(hits) == 1
            assert hits[0].path.name == "FL_FDS_09_Drum_Loop_Full_98.wave"
            assert hits[0].context == "Funky_Disco/loops"
            text = search_app.query_one(FiltersPanel).query_one(Static).content
            assert "/Drum" not in text
            assert "1 matches" in text
            search_app._audio_player.play.assert_not_called()

            await pilot.press("enter")
            assert search_app.test_data.get_selection_ids() == {hits[0].sample_id}
            await pilot.press("escape")
            assert not search_app._filter_active
            assert search_app._visible_items() == search_app._state.items
            assert [item.path for item in search_app._state.items] == [
                item.path for item in directory_items
            ]

    asyncio.run(exercise())


def test_empty_query_stays_active_and_paste_accepts_multiword_search(search_app):
    """Editing an empty query never turns typed letters into browser commands."""
    async def exercise():
        async with search_app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash", "k", "backspace", "d")
            assert search_app._filter_active
            assert search_app._filter_query == "d"
            await pilot.press("backspace")
            search_app.post_message(Paste("Drum Loop"))
            await pilot.pause()
            assert search_app._filter_query == "Drum Loop"
            assert len(search_app._visible_items()) == 1
            await pilot.press("left")
            assert not search_app._filter_active
            assert search_app._state.current_dir == search_app.root

    asyncio.run(exercise())
