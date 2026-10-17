"""Persistent-stream sounddevice adapter for :mod:`sample_manager.audio.player`.

:class:`StreamingSoundDeviceOutput` opens one output stream at the device's native rate
on first use and keeps it open, rendering silence while idle. Each ``start``
conforms the decoded source to the device format (off the audio thread) and
hands it to the :class:`~sample_manager.audio.mixer.Mixer`, which crossfades
from whatever is sounding. ``pause`` only posts a fade-out command, so callers
never wait on device I/O. A :class:`~sample_manager.audio.streaming.StreamingSource`
starts after its first converted block and fills the rest in the background.

The TUI uses this adapter. The Qt GUI keeps the v1
:class:`~sample_manager.audio.sounddevice_output.SoundDeviceOutput` until the
TUI v2 is stable (see ``dev_docs/V2_Design.md``).
"""

from __future__ import annotations

import threading
import time
from typing import Callable

from .backends import require
from .decode import DecodedAudio, decode
from .mixer import Mixer, Voice
from .resample import can_stream_resample, conform
from .streaming import StreamFill, StreamingSource

# Output buffering requested from PortAudio. The callback is Python and needs
# the GIL, so it must absorb UI-thread stalls of a few milliseconds.
DEFAULT_LATENCY_SECONDS = 0.025
_EVENT_POLL_SECONDS = 0.02


class StreamingSoundDeviceOutput:
    """Play decoded float PCM through one persistent sounddevice stream."""

    def __init__(
        self,
        device=None,
        *,
        latency: float | str = DEFAULT_LATENCY_SECONDS,
        samplerate: int | None = None,
        channels: int | None = None,
    ) -> None:
        self._device = device
        self._latency = latency
        self._requested_rate = samplerate
        self._requested_channels = channels
        self._lock = threading.Lock()
        self._stream = None
        self._mixer: Mixer | None = None
        self._current: Voice | None = None
        self._ratio = 1.0  # device frames per source frame for the current voice
        self._position = 0  # source frames, when nothing is sounding
        self._next_token = 0
        self._callbacks: dict[int, Callable[[], None]] = {}
        self._started_at: float | None = None
        self._last_voice: Voice | None = None
        self._xruns = 0
        self._last_conformed = None
        self._fill: StreamFill | None = None
        self._closed = threading.Event()
        self._events_thread: threading.Thread | None = None

    # -- AudioOutput port ------------------------------------------------------

    def start(
        self,
        audio: DecodedAudio | StreamingSource,
        start_frame: int,
        on_complete: Callable[[], None],
    ) -> None:
        with self._lock:
            mixer = self._ensure_stream()
            self._next_token += 1
            token = self._next_token
        if (
            isinstance(audio, StreamingSource)
            and audio.sample_rate != mixer.sample_rate
            and not can_stream_resample()
        ):
            # Chunked conversion needs soxr; convert the whole file instead.
            audio = decode(audio.path)

        fill = None
        if isinstance(audio, StreamingSource):
            fill = StreamFill(
                audio,
                start_frame,
                token=token,
                device_rate=mixer.sample_rate,
                device_channels=mixer.channels,
            )
            fill.fill_first_block()
            voice, ratio = fill.voice, fill.ratio
        else:
            pcm = self._conformed_pcm(audio, mixer)
            ratio = mixer.sample_rate / audio.sample_rate
            device_frames = int(pcm.shape[0])
            cursor = max(0, min(round(int(start_frame) * ratio), device_frames))
            voice = Voice(token=token, pcm=pcm, cursor=cursor)

        with self._lock:
            previous_fill = self._fill
            self._fill = fill
            # Only the newest voice can complete; superseded ones fade out.
            self._callbacks = {voice.token: on_complete}
            self._current = voice
            self._last_voice = voice
            self._ratio = ratio
            self._started_at = time.perf_counter()
        if previous_fill is not None:
            previous_fill.cancel()
        # Starting at the top of a sample keeps its transient intact; resuming
        # or seeking mid-file fades in to avoid a click.
        mixer.play(voice, fade_in=voice.cursor > 0)
        if fill is not None:
            fill.start_background()

    def pause(self) -> int:
        with self._lock:
            voice = self._current
            self._current = None
            fill = self._fill
            self._fill = None
            if voice is not None:
                self._position = self._source_frames(voice)
                self._callbacks.pop(voice.token, None)
            mixer = self._mixer
            position = self._position
        if fill is not None:
            fill.cancel()
        if voice is not None and mixer is not None:
            mixer.stop(voice)
        return position

    def position_frames(self) -> int:
        with self._lock:
            voice = self._current
            return self._source_frames(voice) if voice is not None else self._position

    def close(self) -> None:
        with self._lock:
            stream = self._stream
            self._stream = None
            self._mixer = None
            self._current = None
            self._callbacks = {}
            fill = self._fill
            self._fill = None
        if fill is not None:
            fill.cancel()
            # A block takes milliseconds; waiting lets the fill release its
            # file and resampler before the interpreter shuts down.
            fill.join(timeout=1.0)
        self._closed.set()
        if stream is not None:
            stream.stop()
            stream.close()
        thread = self._events_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)

    # -- diagnostics -------------------------------------------------------------

    def stats(self) -> dict:
        """Report device format, buffering, xruns, and the last start latency."""
        with self._lock:
            stream = self._stream
            mixer = self._mixer
            voice = self._last_voice
            started_at = self._started_at
        first = voice.first_render_at if voice is not None else None
        return {
            "device_rate": mixer.sample_rate if mixer else None,
            "channels": mixer.channels if mixer else None,
            "output_latency_s": _stream_latency(stream),
            "xruns": self._xruns,
            "last_starved_renders": voice.starved if voice is not None else 0,
            "last_start_at": started_at,
            "last_first_render_at": first,
            "last_start_to_render_s": (
                first - started_at if first is not None and started_at is not None else None
            ),
        }

    # -- internals ---------------------------------------------------------------

    def _conformed_pcm(self, audio: DecodedAudio, mixer: Mixer):
        """Reuse the last conversion so resume and seek skip resampling."""
        last = self._last_conformed
        if last is not None and last[0] is audio and last[1] is mixer:
            return last[2]
        pcm = conform(audio.samples, audio.sample_rate, mixer.sample_rate, mixer.channels)
        self._last_conformed = (audio, mixer, pcm)
        return pcm

    def _source_frames(self, voice: Voice) -> int:
        return round(voice.cursor / self._ratio)

    def _ensure_stream(self) -> Mixer:
        """Open the persistent stream once; caller holds ``self._lock``."""
        if self._mixer is not None:
            return self._mixer
        sd = require("sounddevice")
        rate, channels = self._device_format(sd)
        mixer = Mixer(rate, channels)

        def callback(outdata, frames, time_info, status) -> None:
            del frames, time_info
            if status is not None and getattr(status, "output_underflow", False):
                self._xruns += 1
            mixer.render(outdata)

        stream = sd.OutputStream(
            device=self._device,
            samplerate=rate,
            channels=channels,
            dtype="float32",
            latency=self._latency,
            callback=callback,
        )
        stream.start()
        self._stream = stream
        self._mixer = mixer
        self._closed.clear()
        if self._events_thread is None or not self._events_thread.is_alive():
            self._events_thread = threading.Thread(
                target=self._dispatch_events,
                name="sample-manager-audio-events",
                daemon=True,
            )
            self._events_thread.start()
        return mixer

    def _device_format(self, sd) -> tuple[int, int]:
        if self._requested_rate and self._requested_channels:
            return int(self._requested_rate), int(self._requested_channels)
        info = sd.query_devices(self._device, "output")
        rate = int(self._requested_rate or info.get("default_samplerate") or 48000)
        available = int(info.get("max_output_channels") or 2)
        channels = int(self._requested_channels or max(1, min(2, available)))
        return rate, channels

    def _dispatch_events(self) -> None:
        """Run completion callbacks off the audio thread."""
        while not self._closed.wait(_EVENT_POLL_SECONDS):
            self.dispatch_pending()

    def dispatch_pending(self) -> None:
        """Deliver queued mixer events now (also used by tests)."""
        with self._lock:
            mixer = self._mixer
        if mixer is None:
            return
        while mixer.events:
            kind, token = mixer.events.popleft()
            if kind != "complete":
                continue
            with self._lock:
                callback = self._callbacks.pop(token, None)
                if self._current is not None and self._current.token == token:
                    self._position = self._source_frames(self._current)
                    self._current = None
            if callback is not None:
                callback()


def _stream_latency(stream) -> float | None:
    if stream is None:
        return None
    latency = getattr(stream, "latency", None)
    return float(latency) if isinstance(latency, (int, float)) else None
