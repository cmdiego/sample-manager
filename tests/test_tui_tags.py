"""Tag-management pilots using the real tag service and SQLite attachments."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from textual.events import Paste
from textual.widgets import Input, OptionList, Static

from sample_manager.audio import PlaybackStatus
from sample_manager.repos.sample_tag_repo import SampleTagRepo
from sample_manager.repos.tag_alias_repo import TagAliasRepo
from sample_manager.repos.tag_repo import TagRepo
from sample_manager.scanner import scan_library
from sample_manager.tag_service import tag_sample
from sample_manager.tui.app import SampleManagerApp
from sample_manager.tui.data import TuiDataSource
from sample_manager.tui.settings import TuiPreferences
from sample_manager.tui.widgets.action_pane import ActionPane
from sample_manager.tui.widgets.tags_screen import TagsScreen
from sample_manager.tui.widgets.top_display import TopDisplayWidget


class _TagApp(SampleManagerApp):
    """Mount production tagging/navigation without audio or user configuration."""

    def __init__(self, db, root: Path) -> None:
        player = Mock()
        player.snapshot.return_value = SimpleNamespace(
            status=PlaybackStatus.IDLE, path=None, duration_seconds=None,
            position_seconds=0.0, error=None,
        )
        super().__init__(audio_player=player, preferences=TuiPreferences(False))
        self.test_data = TuiDataSource(db)
        self.root = root

    def _initialize(self) -> None:
        """Use the prepared root and ordinary data adapter."""
        self._data = self.test_data
        self._library_roots = (self.root,)
        self._load_root(self.root)

    def _request_waveform(self, item, top_display) -> None:
        """Avoid unrelated decoding work in tag-input tests."""


@pytest.fixture
def tag_env(db, tmp_path, monkeypatch):
    """Create two indexed samples, including a literal bracketed filename."""
    monkeypatch.setattr("sample_manager.config.DEFAULT_CONFIG_PATH", tmp_path / "unused.yaml")
    root = tmp_path / "library"
    root.mkdir()
    (root / "kick [dry].wav").write_bytes(b"RIFF0000")
    (root / "snare.wav").write_bytes(b"RIFF1111")
    scan_library(db, root, fast=True)
    app = _TagApp(db, root)
    kick = app.test_data.search_samples(root, "kick")[0].sample_id
    snare = app.test_data.search_samples(root, "snare")[0].sample_id
    return app, db, kick, snare


async def _add_tag(app, pilot, text: str) -> None:
    """Paste a full tag name into the real editor and press Enter to attach it."""
    app.screen.query_one(Input).post_message(Paste(text))
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


def test_tags_resolve_aliases_and_preserve_literal_names(tag_env):
    """F6 edits real attachments, and removal leaves other samples/tag definitions intact."""
    app, db, kick, snare = tag_env
    drums = TagRepo(db).create("Drums")
    TagAliasRepo(db).add(drums["id"], "drm")
    tag_sample(db, snare, "Drums")

    async def exercise():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("f6")
            assert isinstance(app.screen, TagsScreen)
            await _add_tag(app, pilot, "drm")
            await _add_tag(app, pilot, "DRUMS")
            assert [tag["name_display"] for tag in app.test_data.get_sample_tags(kick)] == ["Drums"]
            await _add_tag(app, pilot, "Warm [red], Lo-Fi")
            assert app.test_data.get_sample_details(kick)["tags"] == ["Drums", "Warm [red], Lo-Fi"]
            preview_text = " ".join(str(widget.content) for widget in app.query_one(TopDisplayWidget).query(Static))
            assert "Tags: Drums · Warm [red], Lo-Fi" in preview_text

            app.screen.query_one(OptionList).highlighted = 0
            await pilot.click("#sample-tag-remove")
            assert app.test_data.get_sample_details(kick)["tags"] == ["Warm [red], Lo-Fi"]
            assert app.test_data.get_sample_details(snare)["tags"] == ["Drums"]
            assert TagRepo(db).get_by_id(drums["id"]) is not None
            await pilot.press("escape")
            assert app.is_running and not isinstance(app.screen, TagsScreen)
            app._audio_player.play.assert_not_called()

    asyncio.run(exercise())


def test_tag_edit_refreshes_query_and_keeps_stage_subject(tag_env):
    """Removing a matching tag updates search; an open Stage editor keeps its sample ID."""
    app, db, kick, snare = tag_env
    tag_sample(db, kick, "onlykick")
    app.test_data.add_to_selection(kick)
    app.test_data.add_to_selection(snare)

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash", *"onlykick", "f6")
            assert isinstance(app.screen, TagsScreen)
            await pilot.click("#sample-tag-remove")
            assert not app._visible_items()
            assert app._filter_query == "onlykick"
            await pilot.press("escape")
            assert app._filter_active
            await pilot.press("escape", "tab", "down", "f6")
            assert isinstance(app.screen, TagsScreen)

            # Model refreshes can move the visible Stage cursor while a modal
            # remains open; its edits must still affect the captured snare.
            app._stage_focused_index = 0
            app._refresh_ui(audition=False)
            await _add_tag(app, pilot, "snare-only")
            assert app.test_data.get_sample_details(snare)["tags"] == ["snare-only"]
            assert app.test_data.get_sample_details(kick)["tags"] == []
            assert app.test_data.get_selection_ids() == {kick, snare}

    asyncio.run(exercise())


def test_action_pane_tags_keep_original_sample_after_refresh(tag_env):
    """File-action callbacks retain their subject when the browser focus moves."""
    app, _db, kick, snare = tag_env

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("right")
            assert isinstance(app.screen, ActionPane)
            app._state = app._state.move_down()
            app._refresh_ui(audition=False)
            await pilot.press("t")
            assert isinstance(app.screen, TagsScreen)
            await _add_tag(app, pilot, "original-subject")
            assert app.test_data.get_sample_details(kick)["tags"] == ["original-subject"]
            assert app.test_data.get_sample_details(snare)["tags"] == []

    asyncio.run(exercise())


def test_tag_editor_rejects_empty_hidden_and_deleted_sample_writes(tag_env):
    """Invalid edits remain visible without creating tags or changing hidden ones."""
    app, db, kick, _snare = tag_env
    hidden = TagRepo(db).create("Secret")
    TagRepo(db).hide(hidden["id"])
    SampleTagRepo(db).attach(kick, hidden["id"])

    async def exercise():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("f6", "enter")
            assert "Enter a tag name" in app.screen.query_one("#sample-tags-status", Static).content
            await _add_tag(app, pilot, "Secret")
            assert "hidden" in app.screen.query_one("#sample-tags-status", Static).content
            assert app.test_data.get_sample_tags(kick) == []
            assert TagRepo(db).get_by_id(hidden["id"])["is_hidden"] == 1
            assert len(SampleTagRepo(db).list_tags_for_sample(kick)) == 1

            # A background scan may remove the sample while its editor is open.
            # Report that failure in place rather than attaching to another row.
            db.execute("DELETE FROM sample WHERE id = ?", (kick,))
            db.conn.commit()
            app.screen.query_one(Input).value = "fresh"
            await pilot.press("enter")
            assert isinstance(app.screen, TagsScreen)
            assert "Sample not found" in app.screen.query_one("#sample-tags-status", Static).content

    asyncio.run(exercise())


def test_late_audio_poll_is_safe_after_views_are_removed(tag_env):
    """A poll between child unmount and app unmount must not crash shutdown."""
    app, _db, _kick, _snare = tag_env

    async def exercise():
        async with app.run_test() as pilot:
            await pilot.pause()
            await app.query_one(TopDisplayWidget).remove()
            app._poll_audio()
            await app.query_one("#status-bar", Static).remove()
            app._set_status("Late scanner update")

    asyncio.run(exercise())


def test_metadata_read_handles_a_sample_pruned_between_reads(tag_env, monkeypatch):
    """Pruning between sample and tag reads yields an absent preview row."""
    app, _db, kick, _snare = tag_env
    monkeypatch.setattr(app.test_data, "get_sample_tags", Mock(side_effect=ValueError("Sample not found")))
    assert app.test_data.get_sample_details(kick) is None
