"""Headless tests for the audio player application service."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from sample_manager.audio.decode import DecodedAudio
from sample_manager.audio.player import AudioPlayer, PlaybackStatus


class _Samples:
    def __init__(self, frames: int = 100, channels: int = 1) -> None:
        self.shape = (frames, channels)
        self.ndim = 2


def _audio(frames: int = 100, sample_rate: int = 10) -> DecodedAudio:
    return DecodedAudio(
        samples=_Samples(frames),
        sample_rate=sample_rate,
        backend="fake",
    )


class FakeOutput:
    def __init__(self) -> None:
        self.starts = []
        self.cursor = 0
        self.on_complete = None
        self.closed = False
        self.fail = None

    def start(self, audio, start_frame, on_complete) -> None:
        if self.fail:
            raise self.fail
        self.starts.append((audio, start_frame))
        self.cursor = start_frame
        self.on_complete = on_complete

    def pause(self) -> int:
        return self.cursor

    def position_frames(self) -> int:
        return self.cursor

    def close(self) -> None:
        self.closed = True

    def complete(self) -> None:
        assert self.on_complete is not None
        self.on_complete()


def _wait_for(player: AudioPlayer, status: PlaybackStatus) -> None:
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if player.snapshot().status is status:
            return
        time.sleep(0.005)
    pytest.fail(f"player did not reach {status}: {player.snapshot()}")


def test_play_pause_and_resume_preserve_position():
    output = FakeOutput()
    player = AudioPlayer(decoder=lambda path: _audio(), output=output)
    try:
        player.play(Path("kick.wav"))
        _wait_for(player, PlaybackStatus.PLAYING)
        output.cursor = 25

        player.pause()
        assert player.snapshot().status is PlaybackStatus.PAUSED
        assert player.snapshot().position_seconds == pytest.approx(2.5)

        player.play(Path("kick.wav"))
        _wait_for(player, PlaybackStatus.PLAYING)
        assert output.starts[-1][1] == 25
    finally:
        player.close()


def test_new_path_decodes_and_starts_at_beginning():
    decoded = []
    output = FakeOutput()

    def decoder(path):
        decoded.append(path)
        return _audio()

    player = AudioPlayer(decoder=decoder, output=output)
    try:
        player.play(Path("a.wav"))
        _wait_for(player, PlaybackStatus.PLAYING)
        output.cursor = 40
        player.play(Path("b.wav"))
        _wait_for(player, PlaybackStatus.PLAYING)
        assert decoded == [Path("a.wav"), Path("b.wav")]
        assert output.starts[-1][1] == 0
    finally:
        player.close()


def test_play_from_start_restarts_current_audio_at_zero():
    output = FakeOutput()
    player = AudioPlayer(decoder=lambda path: _audio(), output=output)
    try:
        player.play(Path("kick.wav"))
        _wait_for(player, PlaybackStatus.PLAYING)
        output.cursor = 40

        player.play_from_start(Path("kick.wav"))
        _wait_for(player, PlaybackStatus.PLAYING)
        assert output.starts[-1][1] == 0
    finally:
        player.close()


def test_stale_decode_result_never_reaches_output():
    release_first = threading.Event()
    first_started = threading.Event()
    output = FakeOutput()

    def decoder(path):
        if path == Path("slow.wav"):
            first_started.set()
            release_first.wait(timeout=1.0)
        return _audio()

    player = AudioPlayer(decoder=decoder, output=output)
    try:
        player.play(Path("slow.wav"))
        assert first_started.wait(timeout=1.0)
        player.play(Path("latest.wav"))
        release_first.set()
        _wait_for(player, PlaybackStatus.PLAYING)
        assert len(output.starts) == 1
        assert player.snapshot().path == Path("latest.wav")
    finally:
        player.close()


def test_natural_completion_resets_to_idle_at_start():
    output = FakeOutput()
    player = AudioPlayer(decoder=lambda path: _audio(), output=output)
    try:
        player.play(Path("kick.wav"))
        _wait_for(player, PlaybackStatus.PLAYING)
        output.cursor = 100
        output.complete()
        snapshot = player.snapshot()
        assert snapshot.status is PlaybackStatus.IDLE
        assert snapshot.position_seconds == 0.0
        assert snapshot.path == Path("kick.wav")
    finally:
        player.close()


def test_decoder_failure_becomes_error_state():
    def decoder(path):
        raise ValueError("bad audio")

    output = FakeOutput()
    player = AudioPlayer(decoder=decoder, output=output)
    try:
        player.play(Path("bad.wav"))
        _wait_for(player, PlaybackStatus.ERROR)
        assert player.snapshot().error == "bad audio"
    finally:
        player.close()


def test_close_is_idempotent_and_closes_output():
    output = FakeOutput()
    player = AudioPlayer(decoder=lambda path: _audio(), output=output)
    player.close()
    player.close()
    assert output.closed


# ---------------------------------------------------------------------------
# seek() tests
# ---------------------------------------------------------------------------

def test_seek_while_playing_restarts_from_target_frame():
    output = FakeOutput()
    player = AudioPlayer(decoder=lambda path: _audio(frames=100, sample_rate=10), output=output)
    try:
        player.play(Path("kick.wav"))
        _wait_for(player, PlaybackStatus.PLAYING)
        output.cursor = 10  # simulate some playback

        player.seek(5.0)  # 5 seconds × 10 fps = frame 50
        _wait_for(player, PlaybackStatus.PLAYING)
        assert output.starts[-1][1] == 50
    finally:
        player.close()


def test_seek_while_paused_updates_position_no_output_call():
    output = FakeOutput()
    player = AudioPlayer(decoder=lambda path: _audio(frames=100, sample_rate=10), output=output)
    try:
        player.play(Path("kick.wav"))
        _wait_for(player, PlaybackStatus.PLAYING)
        player.pause()
        starts_before = len(output.starts)

        player.seek(3.0)  # frame 30
        assert player.snapshot().position_seconds == pytest.approx(3.0)
        assert len(output.starts) == starts_before  # output.start() NOT called again
    finally:
        player.close()


def test_seek_when_idle_no_audio_loaded_is_noop():
    output = FakeOutput()
    player = AudioPlayer(decoder=lambda path: _audio(), output=output)
    try:
        # No play() called, audio never loaded
        player.seek(2.0)  # must not raise
        assert player.snapshot().status is PlaybackStatus.IDLE
        assert len(output.starts) == 0
    finally:
        player.close()


def test_seek_clamps_negative_to_frame_zero():
    output = FakeOutput()
    player = AudioPlayer(decoder=lambda path: _audio(frames=100, sample_rate=10), output=output)
    try:
        player.play(Path("kick.wav"))
        _wait_for(player, PlaybackStatus.PLAYING)

        player.seek(-5.0)
        _wait_for(player, PlaybackStatus.PLAYING)
        assert output.starts[-1][1] == 0
    finally:
        player.close()


def test_seek_clamps_past_end_to_last_frame():
    output = FakeOutput()
    player = AudioPlayer(decoder=lambda path: _audio(frames=100, sample_rate=10), output=output)
    try:
        player.play(Path("kick.wav"))
        _wait_for(player, PlaybackStatus.PLAYING)

        player.seek(999.0)  # way past the end
        _wait_for(player, PlaybackStatus.PLAYING)
        assert output.starts[-1][1] == 99  # last valid frame index
    finally:
        player.close()


def test_pause_before_output_registration_invalidates_guarded_start():
    """Cancellation in the player/output handoff gap must reach the adapter."""
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    class GuardedOutput(FakeOutput):
        """Expose a barrier before the adapter registers a pending start."""

        def start_if_current(self, audio, start_frame, on_complete, is_current):
            """Publish only requests still valid after the handoff barrier."""
            entered.set()
            assert release.wait(5)
            if is_current():
                self.start(audio, start_frame, on_complete)
            finished.set()

    output = GuardedOutput()
    player = AudioPlayer(decoder=lambda path: _audio(), output=output)
    try:
        player.play(Path("pending.wav"))
        assert entered.wait(5)
        player.pause()
        release.set()
        assert finished.wait(5)
        assert output.starts == []
        assert player.snapshot().status is PlaybackStatus.PAUSED
    finally:
        release.set()
        player.close()
