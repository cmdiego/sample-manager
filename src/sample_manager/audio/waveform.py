"""Waveform envelope generation for presentation layers.

This module returns immutable plain-Python data.  Rendering remains the
frontend's responsibility, and optional numeric/decode dependencies stay lazy.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .backends import require
from .decode import DecodedAudio, decode

DEFAULT_WAVEFORM_BUCKETS = 4096


@dataclass(frozen=True)
class WaveformBin:
    minimum: float
    maximum: float


@dataclass(frozen=True)
class WaveformData:
    path: Path
    duration_seconds: float
    bins: tuple[WaveformBin, ...]


def compute_waveform_envelope(samples, bucket_count: int) -> tuple[WaveformBin, ...]:
    """Reduce PCM samples to signed min/max bins across all channels."""
    if bucket_count <= 0:
        raise ValueError("bucket_count must be greater than zero")

    np = require("numpy")
    values = np.asarray(samples, dtype="float64")
    if values.ndim not in (1, 2):
        raise ValueError(f"Expected 1-D or 2-D samples, got ndim={values.ndim}")
    if values.shape[0] == 0:
        return ()

    count = min(bucket_count, int(values.shape[0]))
    edges = np.linspace(0, values.shape[0], count + 1, dtype=int)
    bins = []
    for index in range(count):
        chunk = values[edges[index]:edges[index + 1]]
        bins.append(
            WaveformBin(
                minimum=max(-1.0, min(1.0, float(np.min(chunk)))),
                maximum=max(-1.0, min(1.0, float(np.max(chunk)))),
            )
        )
    return tuple(bins)


def resample_bins(
    bins: tuple[WaveformBin, ...], count: int
) -> tuple[WaveformBin, ...]:
    """Return exactly *count* bins covering the same range as *bins*.

    Down-samples (many source bins per output) or up-samples (nearest source
    bin per output) by proportional grouping.  Pure Python — no numpy needed —
    so presentation layers can re-bin cached envelopes cheaply on every paint.
    """
    if count <= 0:
        raise ValueError("count must be greater than zero")
    source = len(bins)
    if source == 0:
        return ()
    if source == count:
        return tuple(bins)
    out: list[WaveformBin] = []
    for index in range(count):
        lo = index * source // count
        hi = (index + 1) * source // count
        if hi <= lo:
            hi = lo + 1
        chunk = bins[lo:hi]
        out.append(
            WaveformBin(
                minimum=min(b.minimum for b in chunk),
                maximum=max(b.maximum for b in chunk),
            )
        )
    return tuple(out)


class WaveformService:
    """Decode and cache display-resolution waveform envelopes."""

    def __init__(
        self,
        *,
        decoder: Callable[[Path], DecodedAudio] = decode,
        bucket_count: int = DEFAULT_WAVEFORM_BUCKETS,
        cache_entries: int = 64,
    ) -> None:
        if bucket_count <= 0:
            raise ValueError("bucket_count must be greater than zero")
        if cache_entries <= 0:
            raise ValueError("cache_entries must be greater than zero")
        self._decoder = decoder
        self._bucket_count = bucket_count
        self._cache_entries = cache_entries
        self._cache: OrderedDict[tuple[Path, int, int], WaveformData] = OrderedDict()
        self._lock = threading.Lock()

    def load(self, path: Path) -> WaveformData:
        requested = Path(path)
        stat = requested.stat()
        key = (requested.resolve(), stat.st_size, stat.st_mtime_ns)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached

        audio = self._decoder(requested)
        result = WaveformData(
            path=requested,
            duration_seconds=audio.duration_seconds,
            bins=compute_waveform_envelope(audio.samples, self._bucket_count),
        )
        with self._lock:
            self._drop_stale_path_entries(key[0])
            self._cache[key] = result
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_entries:
                self._cache.popitem(last=False)
        return result

    def get_waveform(self, path: Path, bins: int) -> WaveformData:
        """Return the envelope for *path* resampled to exactly *bins* bins.

        Reuses the (path, size, mtime) LRU cache from :meth:`load`, then re-bins
        the cached full-resolution envelope down (or up) to the requested count.
        """
        if bins <= 0:
            raise ValueError("bins must be greater than zero")
        base = self.load(path)
        if len(base.bins) == bins:
            return base
        return WaveformData(
            path=base.path,
            duration_seconds=base.duration_seconds,
            bins=resample_bins(base.bins, bins),
        )

    def _drop_stale_path_entries(self, resolved_path: Path) -> None:
        stale = [key for key in self._cache if key[0] == resolved_path]
        for key in stale:
            del self._cache[key]
