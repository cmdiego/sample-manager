"""Real-time mixer for the persistent output stream.

The mixer renders up to a few voices into each device buffer and applies short
gain ramps so starting, switching, pausing, and seeking never click. Commands
are posted from any thread onto a deque (atomic append/popleft) and drained at
the start of each render, so the audio callback never waits on a lock held by
the UI or the decode worker.
"""

from __future__ import annotations

import collections
import time
from dataclasses import dataclass, field

from .backends import require

DEFAULT_FADE_SECONDS = 0.003
_MAX_VOICES = 3


@dataclass(eq=False)
class Voice:
    """One source being rendered; ``pcm`` is already in the device format.

    A streaming voice is created before its buffer is complete: a fill thread
    writes ``pcm`` in order, then publishes progress through ``filled`` and
    sets ``complete`` after the last block. The mixer only reads frames below
    ``filled`` and does not report completion until ``complete`` is set.
    """

    token: int
    pcm: object  # numpy float32 array of shape (frames, channels)
    cursor: int = 0
    gain: float = 1.0
    target: float = 1.0
    stopping: bool = False
    first_render_at: float | None = field(default=None)
    filled: int | None = None  # frames of pcm written; None means all of pcm
    complete: bool = True
    starved: int = 0  # renders that ran out of filled frames before the end

    @property
    def frames(self) -> int:
        return int(self.pcm.shape[0]) if self.filled is None else self.filled


class Mixer:
    """Mix voices into output buffers; events report natural completion."""

    def __init__(self, sample_rate: int, channels: int, *, fade_seconds: float = DEFAULT_FADE_SECONDS) -> None:
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self._fade_step = 1.0 / max(1, round(self.sample_rate * fade_seconds))
        self._commands: collections.deque = collections.deque()
        self._voices: list[Voice] = []
        self.events: collections.deque = collections.deque()

    # -- control (any thread) ------------------------------------------------

    def play(self, voice: Voice, *, fade_in: bool) -> None:
        """Replace whatever is sounding with *voice*, crossfading the old one."""
        if fade_in:
            voice.gain = 0.0
        voice.target = 1.0
        self._commands.append(("play", voice))

    def stop(self, voice: Voice | None = None) -> None:
        """Fade out *voice*, or every voice when ``None``."""
        self._commands.append(("stop", voice))

    # -- audio thread ----------------------------------------------------------

    def render(self, out) -> None:
        """Fill *out* (``(frames, channels)`` float32) with the next block."""
        np = require("numpy")
        self._drain_commands()
        out.fill(0)
        frames = out.shape[0]
        now = None
        finished: list[Voice] = []
        for voice in self._voices:
            # Read completeness before the fill level: the fill thread sets
            # ``complete`` only after publishing its final ``filled`` value.
            complete = voice.complete
            available = voice.frames
            count = min(frames, available - voice.cursor)
            if count < frames and not complete and not voice.stopping:
                voice.starved += 1
            if count > 0:
                chunk = voice.pcm[voice.cursor:voice.cursor + count]
                if voice.gain == voice.target:
                    if voice.gain == 1.0:
                        out[:count] += chunk
                    elif voice.gain != 0.0:
                        out[:count] += chunk * voice.gain
                else:
                    ramp = self._ramp(np, voice, count)
                    out[:count] += chunk * ramp[:, None]
                if voice.first_render_at is None and not voice.stopping:
                    now = now if now is not None else time.perf_counter()
                    voice.first_render_at = now
                voice.cursor += count
            silent = voice.stopping and voice.gain <= 0.0
            if silent or (complete and voice.cursor >= available):
                finished.append(voice)
        for voice in finished:
            self._voices.remove(voice)
            if not voice.stopping:
                self.events.append(("complete", voice.token))

    @property
    def active(self) -> bool:
        return bool(self._voices) or bool(self._commands)

    def _drain_commands(self) -> None:
        while self._commands:
            kind, voice = self._commands.popleft()
            if kind == "play":
                for current in self._voices:
                    self._fade_out(current)
                self._voices.append(voice)
                # Bound work per callback: drop the oldest fading voices.
                while len(self._voices) > _MAX_VOICES:
                    self._voices.pop(0)
            elif voice is None:
                for current in self._voices:
                    self._fade_out(current)
            elif voice in self._voices:
                self._fade_out(voice)

    @staticmethod
    def _fade_out(voice: Voice) -> None:
        voice.stopping = True
        voice.target = 0.0

    def _ramp(self, np, voice: Voice, count: int):
        direction = 1.0 if voice.target > voice.gain else -1.0
        steps = np.arange(1, count + 1, dtype="float32") * (self._fade_step * direction)
        ramp = voice.gain + steps
        if direction > 0:
            np.minimum(ramp, voice.target, out=ramp)
        else:
            np.maximum(ramp, voice.target, out=ramp)
        voice.gain = float(ramp[-1])
        return ramp
