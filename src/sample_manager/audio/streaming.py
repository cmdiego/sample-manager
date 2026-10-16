"""Start long files after their first block instead of a full decode.

:class:`PlaybackSources` is the decoder port the TUI player uses. Files already
in the shared :class:`~sample_manager.audio.decode_cache.DecodeCache` play
from RAM; short files are decoded whole (and cached); long files that
libsndfile can seek are returned as a header-only :class:`StreamingSource`.

The output adapter turns a :class:`StreamingSource` into a mixer voice with a
:class:`StreamFill`: it converts the first small block synchronously, starts
the voice, and converts the rest in a background thread while the voice plays.
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .backends import is_available, require
from .decode import DecodedAudio, select_backend
from .decode_cache import DecodeCache
from .mixer import Voice
from .resample import StreamResampler, map_channels

# Files at least this long stream; shorter ones are decoded whole, which is
# cheap and makes seeking instant.
STREAM_MIN_SECONDS = 10.0
# The first block is small so the voice can start quickly; later blocks are
# larger to keep per-block overhead low. Both are in source frames.
FIRST_BLOCK_FRAMES = 2048
BLOCK_FRAMES = 32768
# Slack for resampler rounding when sizing the device-rate buffer.
_BUFFER_MARGIN_FRAMES = 64


@dataclass(frozen=True)
class StreamingSource:
    """Header information for a file that is decoded while it plays."""

    path: Path
    sample_rate: int
    frames: int
    channels: int

    @property
    def duration_seconds(self) -> float:
        return self.frames / self.sample_rate if self.sample_rate else 0.0


def probe_streaming_source(path: Path, *, min_seconds: float = STREAM_MIN_SECONDS) -> StreamingSource | None:
    """Return a :class:`StreamingSource` when *path* is long and seekable."""
    requested = Path(path)
    if select_backend(requested.suffix) != "soundfile" or not is_available("soundfile"):
        return None
    sf = require("soundfile")
    try:
        info = sf.info(str(requested))
    except Exception:  # noqa: BLE001 - let the full decoder report the error
        return None
    frames, rate = int(info.frames), int(info.samplerate)
    if frames <= 0 or rate <= 0 or frames / rate < min_seconds:
        return None
    return StreamingSource(requested, rate, frames, max(1, int(info.channels)))


class PlaybackSources:
    """Decoder port that streams long files and caches everything else."""

    def __init__(self, cache: DecodeCache, *, stream_min_seconds: float = STREAM_MIN_SECONDS) -> None:
        self._cache = cache
        self._stream_min_seconds = stream_min_seconds

    def __call__(self, path: Path) -> DecodedAudio | StreamingSource:
        requested = Path(path)
        if not self._cache.contains(requested):
            source = probe_streaming_source(requested, min_seconds=self._stream_min_seconds)
            if source is not None:
                return source
        return self._cache.get(requested)

    def prefetch(self, paths: Iterable[Path]) -> None:
        self._cache.prefetch(paths)


class StreamFill:
    """Convert a :class:`StreamingSource` into a growing device-rate voice."""

    def __init__(
        self,
        source: StreamingSource,
        start_frame: int,
        *,
        token: int,
        device_rate: int,
        device_channels: int,
    ) -> None:
        np = require("numpy")
        sf = require("soundfile")
        self._source = source
        self._channels = device_channels
        self.ratio = device_rate / source.sample_rate
        start = max(0, min(int(start_frame), source.frames))
        offset = round(start * self.ratio)
        capacity = offset + math.ceil((source.frames - start) * self.ratio) + _BUFFER_MARGIN_FRAMES
        # np.empty reserves address space without touching it; pages are
        # committed as the fill writes them.
        pcm = np.empty((capacity, device_channels), dtype="float32")
        self.voice = Voice(token=token, pcm=pcm, cursor=offset, filled=offset, complete=False)
        self._file = sf.SoundFile(str(source.path))
        if start:
            self._file.seek(start)
        self._resampler = (
            StreamResampler(source.sample_rate, device_rate, device_channels)
            if source.sample_rate != device_rate else None
        )
        self._cancelled = threading.Event()
        self._thread: threading.Thread | None = None

    def fill_first_block(self) -> None:
        """Convert the first block on the calling thread, before playback starts."""
        if self._step(FIRST_BLOCK_FRAMES):
            self._finish()

    def start_background(self) -> None:
        """Convert the remaining blocks on a daemon thread."""
        if self.voice.complete:
            return
        self._thread = threading.Thread(target=self._run, name="sample-manager-stream", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        """Stop filling; the voice ends at whatever was already converted."""
        self._cancelled.set()

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        try:
            while not self._cancelled.is_set():
                if self._step(BLOCK_FRAMES):
                    break
        except Exception:  # noqa: BLE001 - a damaged tail ends the voice early
            pass
        finally:
            self._finish()

    def _step(self, frames: int) -> bool:
        """Convert one block; return True at end of file."""
        block = self._file.read(frames, dtype="float32", always_2d=True)
        last = block.shape[0] < frames
        pcm = map_channels(block, self._channels)
        if self._resampler is not None:
            pcm = self._resampler.process(pcm, last=last)
        self._write(pcm)
        return last

    def _write(self, pcm) -> None:
        voice = self.voice
        start = voice.filled
        count = min(int(pcm.shape[0]), voice.pcm.shape[0] - start)
        if count > 0:
            voice.pcm[start:start + count] = pcm[:count]
            # Publish only after the frames are written.
            voice.filled = start + count

    def _finish(self) -> None:
        if not self._file.closed:
            self._file.close()
        # Free native resampler state on this thread, not at interpreter exit.
        self._resampler = None
        self.voice.complete = True
