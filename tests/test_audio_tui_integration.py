"""Tests for the narrow TUI-to-audio integration boundary."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from sample_manager.audio.player import PlaybackSnapshot, PlaybackStatus
from sample_manager.tui.app import SampleManagerApp
from sample_manager.tui.nav_state import NavItem, NavState


class FakePlayer:
    def __init__(self) -> None:
        self.played = []
        self.restarted = []
        self.paused = 0
        self.closed = 0
        self.status = PlaybackStatus.IDLE

    def play(self, path) -> None:
        self.played.append(path)
        self.status = PlaybackStatus.PLAYING

    def pause(self) -> None:
        self.paused += 1
        self.status = PlaybackStatus.PAUSED

    def play_from_start(self, path) -> None:
        self.restarted.append(path)
        self.played.append(path)
        self.status = PlaybackStatus.PLAYING

    def snapshot(self) -> PlaybackSnapshot:
        path = self.played[-1] if self.played else None
        return PlaybackSnapshot(self.status, path, 0.0, None, None)

    def close(self) -> None:
        self.closed += 1


def _item(name: str, *, directory: bool = False) -> NavItem:
    return NavItem(Path(name).name, Path("/samples") / name, directory, None, False)


def test_focused_file_auto_plays_once_until_focus_changes():
    player = FakePlayer()
    app = SampleManagerApp(audio_player=player)
    file_item = _item("kick.wav")
    app._state = NavState.initial(Path("/samples"), [file_item])

    app._audition_focused()
    app._audition_focused()
    assert player.played == [file_item.path]


def test_directory_does_not_replace_audio_and_allows_file_reaudition():
    player = FakePlayer()
    app = SampleManagerApp(audio_player=player)
    file_item = _item("kick.wav")
    directory = _item("drums", directory=True)
    app._state = NavState.initial(Path("/samples"), [file_item])
    app._audition_focused()

    app._state = NavState.initial(Path("/samples"), [directory])
    app._audition_focused()
    assert player.played == [file_item.path]

    app._state = NavState.initial(Path("/samples"), [file_item])
    app._audition_focused()
    assert player.played == [file_item.path, file_item.path]


def test_space_pauses_then_resumes_focused_file():
    """The TUI transport key resumes rather than discarding a checkpoint."""
    player = FakePlayer()
    app = SampleManagerApp(audio_player=player)
    file_item = _item("kick.wav")
    app._state = NavState.initial(Path("/samples"), [file_item])
    app._audition_focused()

    with patch.object(app, "_set_status"):
        app._toggle_playback()
        app._toggle_playback()
    assert player.paused == 1
    assert player.played == [file_item.path, file_item.path]
    assert player.restarted == []


def test_space_toggles_playback_even_while_filtering():
    player = FakePlayer()
    app = SampleManagerApp(audio_player=player)
    file_item = _item("kick.wav")
    app._state = NavState.initial(Path("/samples"), [file_item])
    app._filter_active = True
    app._filter_query = "ki"
    app._filter_results = (file_item,)
    app._audition_focused()
    event = MagicMock(key="space", character=" ")

    with patch.object(app, "_set_status"):
        app.on_key(event)

    assert player.paused == 1
    assert app._filter_query == "ki"
    event.stop.assert_called_once()


def test_ctrl_space_resumes_paused_checkpoint():
    player = FakePlayer()
    app = SampleManagerApp(audio_player=player)
    paused_path = Path("/samples/kick.wav")
    player.play(paused_path)
    player.pause()
    event = MagicMock(key="ctrl+space", character=None)

    with patch.object(app, "_set_status"):
        app._state = NavState.initial(Path("/samples"), [])
        app.on_key(event)

    assert player.played == [paused_path, paused_path]
    assert player.status is PlaybackStatus.PLAYING


def test_unmount_closes_player():
    player = FakePlayer()
    app = SampleManagerApp(audio_player=player)
    app.on_unmount()
    assert player.closed == 1


class PrefetchingPlayer(FakePlayer):
    def __init__(self) -> None:
        super().__init__()
        self.prefetched = []

    def prefetch(self, paths) -> None:
        self.prefetched.append(list(paths))


def test_neighbors_of_focused_row_are_prefetched_nearest_first():
    player = PrefetchingPlayer()
    app = SampleManagerApp(audio_player=player)
    items = [_item(f"s{index}.wav") for index in range(6)] + [_item("drums", directory=True)]
    state = NavState.initial(Path("/samples"), items)
    app._state = NavState(
        state.library_roots, state.current_root, state.current_dir, state.dir_stack,
        state.items, 2, state.selection_ids,
    )

    app._prefetch_neighbors()

    names = [path.name for path in player.prefetched[-1]]
    assert names == ["s3.wav", "s1.wav", "s4.wav", "s0.wav", "s5.wav"]


def test_players_without_prefetch_are_supported():
    app = SampleManagerApp(audio_player=FakePlayer())
    app._state = NavState.initial(Path("/samples"), [_item("a.wav"), _item("b.wav")])
    app._prefetch_neighbors()  # must not raise
