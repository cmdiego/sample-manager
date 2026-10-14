"""Phase 4 audio-integration tests (offscreen).

Covers: the 200 ms playback-snapshot polling timer, auto-audition on focusing a
file, Space pause/restart, Ctrl+Space resume, the status-bar formatter, and the
``closeEvent`` player teardown. A ``FakePlayer`` stands in for the real audio
engine so no sound device is touched.
"""

from __future__ import annotations

from pathlib import Path

from sample_manager.audio.player import PlaybackSnapshot, PlaybackStatus
from sample_manager.gui.app import create_main_window
from sample_manager.gui.controller import BrowserController
from sample_manager.gui.main_window import _format_playback


class FakePlayer:
    """Records interactions in place of the real :class:`AudioPlayer`."""

    def __init__(self, snapshot: PlaybackSnapshot | None = None) -> None:
        self.played: list[Path] = []
        self.restarted: list[Path] = []
        self.paused = 0
        self.closed = False
        self._snapshot = snapshot or PlaybackSnapshot(
            status=PlaybackStatus.PLAYING,
            path=Path("/tmp/kick.wav"),
            position_seconds=3.0,
            duration_seconds=9.0,
            error=None,
        )

    def play(self, path) -> None:
        path = Path(path)
        self.played.append(path)
        self._snapshot = PlaybackSnapshot(
            PlaybackStatus.PLAYING, path, self._snapshot.position_seconds,
            self._snapshot.duration_seconds, None,
        )

    def play_from_start(self, path) -> None:
        path = Path(path)
        self.restarted.append(path)
        self._snapshot = PlaybackSnapshot(
            PlaybackStatus.PLAYING, path, 0.0, self._snapshot.duration_seconds, None,
        )

    def pause(self) -> None:
        self.paused += 1
        self._snapshot = PlaybackSnapshot(
            PlaybackStatus.PAUSED,
            self._snapshot.path,
            self._snapshot.position_seconds,
            self._snapshot.duration_seconds,
            None,
        )

    def snapshot(self) -> PlaybackSnapshot:
        return self._snapshot

    def close(self) -> None:
        self.closed = True


def _first_sample_id(service, root):
    items = service.list_directory(root / "drums")
    return next(it.sample_id for it in items if it.sample_id is not None)


# ---------------------------------------------------------------------------
# polling timer
# ---------------------------------------------------------------------------


def test_polling_timer_emits_playback_changed(populated_service, qtbot):
    service, _root = populated_service
    player = FakePlayer()
    controller = BrowserController(service, player=player)
    with qtbot.waitSignal(controller.playback_changed, timeout=1000) as blocker:
        pass
    assert isinstance(blocker.args[0], PlaybackSnapshot)
    controller.shutdown()


def test_no_timer_without_player(populated_service, qtbot):
    service, _root = populated_service
    controller = BrowserController(service)
    assert controller._playback_timer is None
    # shutdown is safe even with no player/timer.
    controller.shutdown()


# ---------------------------------------------------------------------------
# auto-audition + restart
# ---------------------------------------------------------------------------


def test_focus_file_auto_auditions(populated_service, qtbot):
    service, root = populated_service
    player = FakePlayer()
    controller = BrowserController(service, player=player)
    sid = _first_sample_id(service, root)
    controller.set_focus(sid)
    assert len(player.played) == 1
    assert player.played[0].name in {"kick.wav", "snare.wav"}
    controller.shutdown()


def test_focus_directory_does_not_play(populated_service, qtbot):
    service, _root = populated_service
    player = FakePlayer()
    controller = BrowserController(service, player=player)
    controller.set_focus(None)  # a directory row emits no sample id
    assert player.played == []
    controller.shutdown()


def test_space_pauses_active_playback(populated_service, qtbot):
    service, root = populated_service
    player = FakePlayer()
    controller = BrowserController(service, player=player)
    sid = _first_sample_id(service, root)
    controller.set_focus(sid)
    controller.toggle_focused_playback()
    assert player.paused == 1
    controller.shutdown()


def test_space_after_pause_restarts_focused_from_start(populated_service, qtbot):
    service, root = populated_service
    player = FakePlayer()
    controller = BrowserController(service, player=player)
    sid = _first_sample_id(service, root)
    controller.set_focus(sid)
    player.pause()
    controller.toggle_focused_playback()
    assert len(player.restarted) == 1
    controller.shutdown()


def test_toggle_focused_playback_noop_without_player(populated_service, qtbot):
    service, root = populated_service
    controller = BrowserController(service)
    sid = _first_sample_id(service, root)
    controller.set_focus(sid)
    controller.toggle_focused_playback()  # must not raise
    controller.resume_playback()
    controller.shutdown()


def test_ctrl_space_resumes_paused_checkpoint(populated_service, qtbot):
    service, _root = populated_service
    paused_path = Path("/tmp/paused.wav")
    player = FakePlayer(
        PlaybackSnapshot(PlaybackStatus.PAUSED, paused_path, 4.5, 9.0, None)
    )
    controller = BrowserController(service, player=player)

    controller.resume_playback()

    assert player.played == [paused_path]
    controller.shutdown()


def test_window_registers_both_transport_shortcuts(populated_service, qtbot):
    service, _root = populated_service
    window = create_main_window(service, player=FakePlayer())
    qtbot.addWidget(window)

    assert "Space" in window._shortcuts
    assert "Ctrl+Space" in window._shortcuts
    window.close()


# ---------------------------------------------------------------------------
# window teardown
# ---------------------------------------------------------------------------


def test_close_event_closes_player(populated_service, qtbot):
    service, _root = populated_service
    player = FakePlayer()
    window = create_main_window(service, player=player)
    qtbot.addWidget(window)
    window.show()
    assert not player.closed
    window.close()
    assert player.closed
    assert window.controller._playback_timer is None


def test_window_starts_with_player_and_waveform_service(populated_service, qtbot):
    from sample_manager.audio.waveform import WaveformService

    service, root = populated_service
    player = FakePlayer()
    window = create_main_window(service, player=player, waveform_service=WaveformService())
    qtbot.addWidget(window)
    window.show()
    # Focusing a file drives both the auto-audition and the waveform path.
    items = service.list_directory(root / "drums")
    sid = next(it.sample_id for it in items if it.sample_id is not None)
    window._on_focus_changed(sid)
    assert len(player.played) == 1
    window.close()


# ---------------------------------------------------------------------------
# status-bar formatter
# ---------------------------------------------------------------------------


def test_format_playback_playing():
    snap = PlaybackSnapshot(
        status=PlaybackStatus.PLAYING,
        path=Path("/lib/drums/snare.wav"),
        position_seconds=3.0,
        duration_seconds=9.0,
        error=None,
    )
    assert _format_playback(snap) == "PLAYING — snare.wav [0:03 / 0:09]"


def test_format_playback_idle_without_path():
    snap = PlaybackSnapshot(
        status=PlaybackStatus.IDLE,
        path=None,
        position_seconds=0.0,
        duration_seconds=None,
        error=None,
    )
    assert _format_playback(snap) == "IDLE"


def test_status_error_shows_and_arms_timer(populated_service, qtbot):
    service, _root = populated_service
    window = create_main_window(service)
    qtbot.addWidget(window)
    window.show_status_error("Audio playback unavailable")
    assert window._status_error.text() == "Audio playback unavailable"
    assert window._error_clear_timer.isActive()
    window.close()
