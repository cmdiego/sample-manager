"""Optional sounddevice adapter for :mod:`sample_manager.audio.player`."""

from __future__ import annotations

import threading
from typing import Callable

from .backends import require
from .decode import DecodedAudio


class NullOutput:
    """No-op :class:`AudioOutput` used when no playback backend is available.

    Satisfies the output port so the player (and any GUI wired to it) runs
    without a sound device: nothing is ever heard, and position never advances.
    """

    def start(self, audio: DecodedAudio, start_frame: int, on_complete: Callable[[], None]) -> None:
        del audio, start_frame, on_complete

    def pause(self) -> int:
        return 0

    def position_frames(self) -> int:
        return 0

    def close(self) -> None:
        return None


class SoundDeviceOutput:
    """Write decoded float PCM to the default output device."""

    def __init__(self, device=None) -> None:
        self._lock = threading.RLock()
        self._stream = None
        self._cursor = 0
        self._device = device

    def start(
        self,
        audio: DecodedAudio,
        start_frame: int,
        on_complete: Callable[[], None],
    ) -> None:
        sd = require("sounddevice")
        self.pause()
        samples = audio.samples
        channels = audio.channels

        with self._lock:
            self._cursor = max(0, min(int(start_frame), audio.frames))

        def callback(outdata, frames, time_info, status) -> None:
            del time_info, status
            completed = False
            with self._lock:
                available = max(audio.frames - self._cursor, 0)
                count = min(frames, available)
                outdata.fill(0)
                if count:
                    chunk = samples[self._cursor:self._cursor + count]
                    if getattr(chunk, "ndim", 1) == 1:
                        outdata[:count, 0] = chunk
                    else:
                        outdata[:count, :] = chunk
                    self._cursor += count
                completed = self._cursor >= audio.frames
            if completed:
                on_complete()
                raise sd.CallbackStop

        stream = sd.OutputStream(
            device=self._device,
            samplerate=audio.sample_rate,
            channels=channels,
            dtype="float32",
            callback=callback,
        )
        with self._lock:
            self._stream = stream
        stream.start()

    def pause(self) -> int:
        with self._lock:
            stream = self._stream
            self._stream = None
            cursor = self._cursor
        if stream is not None:
            stream.stop()
            stream.close()
        return cursor

    def position_frames(self) -> int:
        with self._lock:
            return self._cursor

    def close(self) -> None:
        self.pause()
