"""Headless, asynchronous single-track audio playback.

The player depends on small decode and output ports.  It has no knowledge of
Textual, the database, or library navigation, and can therefore be driven by
any frontend and tested without an audio device.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol

from .decode import DecodedAudio, decode


class PlaybackStatus(Enum):
    IDLE = "idle"
    LOADING = "loading"
    PLAYING = "playing"
    PAUSED = "paused"
    ERROR = "error"


@dataclass(frozen=True)
class PlaybackSnapshot:
    status: PlaybackStatus
    path: Path | None
    position_seconds: float
    duration_seconds: float | None
    error: str | None


class Decoder(Protocol):
    def __call__(self, path: Path) -> DecodedAudio: ...


class AudioOutput(Protocol):
    """Port implemented by an audio-device adapter."""

    def start(
        self,
        audio: DecodedAudio,
        start_frame: int,
        on_complete: Callable[[], None],
    ) -> None: ...

    def pause(self) -> int: ...

    def position_frames(self) -> int: ...

    def close(self) -> None: ...


def _default_output() -> AudioOutput:
    from .sounddevice_output import SoundDeviceOutput

    return SoundDeviceOutput()


class AudioPlayer:
    """Thread-safe single-track player with non-blocking decode commands."""

    def __init__(
        self,
        *,
        decoder: Decoder = decode,
        output: AudioOutput | None = None,
    ) -> None:
        self._decoder = decoder
        self._output = output if output is not None else _default_output()
        self._lock = threading.RLock()
        self._commands: queue.Queue[tuple[int, Path] | None] = queue.Queue()
        self._generation = 0
        self._closed = False
        self._status = PlaybackStatus.IDLE
        self._path: Path | None = None
        self._audio: DecodedAudio | None = None
        self._audio_path: Path | None = None
        self._position_frames = 0
        self._error: str | None = None
        self._worker = threading.Thread(
            target=self._run,
            name="sample-manager-audio",
            daemon=True,
        )
        self._worker.start()

    def play(self, path: Path) -> None:
        """Load and play *path*, or resume it when it is already loaded."""
        self._request_play(path, resume=True)

    def play_from_start(self, path: Path) -> None:
        """Load *path* if needed and always play it from frame zero."""
        self._request_play(path, resume=False)

    def _request_play(self, path: Path, *, resume: bool) -> None:
        requested = Path(path)
        with self._lock:
            if self._closed:
                return
            self._generation += 1
            generation = self._generation
            was_playing = self._status is PlaybackStatus.PLAYING
            same_path = requested == self._path
            if not same_path or not resume:
                self._position_frames = 0
            self._path = requested
            self._status = PlaybackStatus.LOADING
            self._error = None
        if was_playing:
            stopped_at = self._output.pause()
            with self._lock:
                if self._is_current(generation) and same_path and resume:
                    self._position_frames = stopped_at
        self._commands.put((generation, requested))

    def pause(self) -> None:
        """Pause playback, or cancel an in-flight load. Idempotent."""
        with self._lock:
            if self._closed:
                return
            if self._status is PlaybackStatus.PLAYING:
                self._status = PlaybackStatus.PAUSED
                self._generation += 1
                generation = self._generation
            elif self._status is PlaybackStatus.LOADING:
                self._generation += 1
                self._status = PlaybackStatus.IDLE
                return
            else:
                return
        stopped_at = self._output.pause()
        with self._lock:
            if self._is_current(generation):
                self._position_frames = stopped_at

    def snapshot(self) -> PlaybackSnapshot:
        """Return an immutable view of the current playback state."""
        with self._lock:
            position_frames = self._position_frames
            status = self._status
            path = self._path
            sample_rate = self._audio.sample_rate if self._audio else 0
            duration = self._audio.duration_seconds if self._audio else None
            error = self._error
        if status is PlaybackStatus.PLAYING:
            position_frames = self._output.position_frames()
        return PlaybackSnapshot(
            status=status,
            path=path,
            position_seconds=(position_frames / sample_rate if sample_rate else 0.0),
            duration_seconds=duration,
            error=error,
        )

    def seek(self, position_seconds: float) -> None:
        """Seek the current file to *position_seconds*.

        No-op when no file is loaded, no audio is decoded, or the player is closed.
        If playing: stops the output and restarts from the target frame.
        If paused: updates position so the next play resumes from there.
        If idle/loading: updates position for the next play call.
        """
        with self._lock:
            if self._closed or self._path is None or self._audio is None:
                return
            sample_rate = self._audio.sample_rate
            frames = self._audio.frames
            target = max(0, min(int(position_seconds * sample_rate), frames - 1))
            was_playing = self._status is PlaybackStatus.PLAYING
            if not was_playing:
                self._position_frames = target
                return
            self._generation += 1
            generation = self._generation
            self._position_frames = target
            self._status = PlaybackStatus.LOADING
            path = self._path
        self._output.pause()
        self._commands.put((generation, path))

    def close(self) -> None:
        """Release the worker and output device. Safe to call repeatedly."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._generation += 1
            self._status = PlaybackStatus.IDLE
        self._output.close()
        self._commands.put(None)
        self._worker.join(timeout=2.0)

    def _run(self) -> None:
        while True:
            command = self._commands.get()
            if command is None:
                return
            generation, path = command
            self._execute_play(generation, path)

    def _execute_play(self, generation: int, path: Path) -> None:
        try:
            with self._lock:
                if not self._is_current(generation):
                    return
                audio = self._audio if self._audio_path == path else None
                start_frame = self._position_frames

            if audio is None:
                audio = self._decoder(path)
                start_frame = 0

            with self._lock:
                if not self._is_current(generation):
                    return
                self._audio = audio
                self._audio_path = path
                self._position_frames = start_frame
                self._status = PlaybackStatus.PLAYING

            self._output.start(
                audio,
                start_frame,
                lambda: self._on_complete(generation),
            )
        except Exception as exc:  # noqa: BLE001 - normalize adapter failures
            with self._lock:
                if self._is_current(generation):
                    self._status = PlaybackStatus.ERROR
                    self._error = str(exc) or exc.__class__.__name__

    def _on_complete(self, generation: int) -> None:
        with self._lock:
            if not self._is_current(generation):
                return
            self._position_frames = 0
            self._status = PlaybackStatus.IDLE

    def _is_current(self, generation: int) -> bool:
        return not self._closed and generation == self._generation
