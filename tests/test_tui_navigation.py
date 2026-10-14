"""TUI pilot and navigation checks for active panes and library roots."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from sample_manager.audio import PlaybackStatus
from sample_manager.services.navigation import NavItem, build_items
from sample_manager.tui.app import SampleManagerApp
from sample_manager.tui.widgets.file_tree import _format_item


class _FakeData:
    """Small Stage/index adapter for a mounted TUI without user config."""

    def __init__(self, roots: tuple[Path, Path]) -> None:
        self.roots = roots
        self.selected = {1, 2}
        self.paths = {1: roots[0] / "kick.wav", 2: roots[0] / "snare.wav"}

    def get_indexed_files(self, root: Path) -> dict[str, int]:
        return {path.name: sid for sid, path in self.paths.items() if path.parent == root}

    def get_selection_ids(self) -> set[int]:
        return set(self.selected)

    def get_sample_details(self, sid: int) -> dict:
        return {"id": sid, "filename": self.paths[sid].name}

    def get_sample_path(self, sid: int) -> Path:
        return self.paths[sid]

    def get_selection_total_size(self) -> int:
        return 0

    def get_active_destination(self) -> None:
        return None

    def remove_from_selection(self, sid: int) -> None:
        self.selected.discard(sid)


class _NavigationTestApp(SampleManagerApp):
    """Mount the real four-zone app with local files and inert audio work."""

    def __init__(self, roots: tuple[Path, Path]) -> None:
        snapshot = SimpleNamespace(
            status=PlaybackStatus.IDLE, path=None, duration_seconds=None,
            position_seconds=0.0, error=None,
        )
        player = Mock()
        player.snapshot.return_value = snapshot
        super().__init__(audio_player=player, waveform_service=Mock())
        self.fake_data = _FakeData(roots)
        self.test_roots = roots

    def _initialize(self) -> None:
        """Install the fake data and use the production root loader."""
        self._data = self.fake_data
        self._library_roots = self.test_roots
        self._load_root(self.test_roots[0])

    def _request_waveform(self, item, top_display) -> None:
        """Keep this pilot focused on navigation, not audio decoding."""

    def _audition_focused(self) -> None:
        """Avoid opening an output device for the pilot."""


async def _exercise_panes_and_roots(roots: tuple[Path, Path]) -> None:
    """Drive actual Textual key delivery across Browser, Stage, and roots."""
    app = _NavigationTestApp(roots)
    async with app.run_test() as pilot:
        await pilot.pause()
        original_index = app._state.focused_index

        await pilot.press("tab")
        await pilot.pause()
        assert app._active_pane == "stage"
        assert app._effective_focused_item().sample_id == 1

        await pilot.press("down")
        await pilot.pause()
        assert app._effective_focused_item().sample_id == 2
        await pilot.press("d")
        await pilot.pause()
        assert app.fake_data.selected == {1}

        await pilot.press("tab")
        await pilot.pause()
        assert app._active_pane == "browser"
        assert app._state.focused_index == original_index

        await pilot.press("r")
        await pilot.pause()
        assert app._state.current_root == roots[1]
        assert app.fake_data.selected == {1}

        # Tab must also escape typeahead; otherwise printable keys remain
        # trapped in the filter when the user moves to Stage.
        await pilot.press("/")
        await pilot.press("k")
        assert app._filter_active and app._filter_query == "k"
        await pilot.press("tab")
        await pilot.pause()
        assert app._active_pane == "stage"
        assert not app._filter_active and app._filter_query == ""


def test_tui_tab_stage_removal_and_root_cycle(tmp_path):
    """Tab, arrows, d, and r work in a mounted terminal UI."""
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    (first / "kick.wav").write_bytes(b"RIFF0000")
    (first / "snare.wav").write_bytes(b"RIFF1111")
    asyncio.run(_exercise_panes_and_roots((first, second)))


def test_known_root_resolves_duplicate_names_without_suffix_scan(tmp_path, monkeypatch):
    """The direct path key chooses the correct sample among duplicate names."""
    root = tmp_path / "samples"
    first, second = root / "one", root / "two"
    first.mkdir(parents=True)
    second.mkdir()
    (first / "kick.wav").write_bytes(b"a")
    (second / "kick.wav").write_bytes(b"b")
    indexed = {"one/kick.wav": 1, "two/kick.wav": 2}

    def fail_suffix_scan(_path, _indexed):
        """Any fallback means the known-root optimization was not used."""
        raise AssertionError("suffix scan should not run")

    monkeypatch.setattr("sample_manager.services.navigation._to_rel_norm", fail_suffix_scan)
    assert build_items(first, indexed, set(), root=root)[0].sample_id == 1
    assert build_items(second, indexed, set(), root=root)[0].sample_id == 2


def test_missing_directory_is_an_empty_listing(tmp_path):
    """A removed library folder leaves the TUI in a recoverable state."""
    assert build_items(tmp_path / "missing", {}, set(), root=tmp_path) == []


def test_bracketed_sample_names_are_escaped_for_terminal_rendering():
    """A filename cannot inject Rich markup into Browser rows."""
    item = NavItem("[drum] loop.wav", Path("/lib/[drum] loop.wav"), False, 1, False)
    assert r"\[drum] loop.wav" in _format_item(item, focused=True)


def test_tui_startup_uses_configured_indexed_root(tmp_path, monkeypatch):
    """The TUI opens the configured default instead of the first DB row."""
    from sample_manager.tui import app as tui_app

    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    data = Mock()
    data.get_library_roots.return_value = [
        {"path": str(first)}, {"path": str(second)}
    ]
    monkeypatch.setattr(tui_app, "_open_db", Mock(return_value=Mock()))
    monkeypatch.setattr(tui_app, "TuiDataSource", Mock(return_value=data))
    monkeypatch.setattr(tui_app, "get_config_path", Mock(return_value=tmp_path / "config.yaml"))
    monkeypatch.setattr(
        tui_app, "load_config", Mock(return_value={"default_library_root": str(second)})
    )
    monkeypatch.setattr(tui_app, "normalize_config", lambda config: config)
    app = SampleManagerApp(audio_player=Mock(), waveform_service=Mock())
    app._load_root = Mock()

    app._initialize()

    assert app._library_roots == (first, second)
    app._load_root.assert_called_once_with(second)
