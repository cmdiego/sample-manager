"""Multi-resolution peak pyramids and their compact BLOB encoding.

Milestone 2 moves waveform work to scan time. A pyramid holds signed min/max
envelopes at several resolutions (4096 → 1024 → 256 bins by default); the
finest level is what :class:`~sample_manager.audio.waveform.WaveformService`
already renders, and the coarser ones serve narrow views without re-binning.

Each level is stored as interleaved ``int8`` min/max pairs scaled by 127,
about 10.5 KB per sample for the default levels. Quantisation rounds away from
zero, so a quiet but non-silent signal still draws at least one step.
"""

from __future__ import annotations

from typing import Sequence

from .backends import require
from .waveform import WaveformBin, compute_waveform_envelope

DEFAULT_PEAK_LEVELS: tuple[int, ...] = (4096, 1024, 256)
_SCALE = 127.0


def compute_peak_pyramid(
    samples, levels: Sequence[int] = DEFAULT_PEAK_LEVELS
) -> tuple[tuple[WaveformBin, ...], ...]:
    """Return one envelope per level, finest first.

    Coarser levels are reduced from the finest one, so the PCM is scanned
    once. A file shorter than a level has fewer bins (one per frame).
    """
    if not levels or any(level <= 0 for level in levels):
        raise ValueError("levels must be positive bucket counts")
    ordered = sorted(set(int(level) for level in levels), reverse=True)
    finest = compute_waveform_envelope(samples, ordered[0])
    pyramid = [finest]
    for level in ordered[1:]:
        pyramid.append(_reduce(finest, level))
    return tuple(pyramid)


def _reduce(bins: tuple[WaveformBin, ...], count: int) -> tuple[WaveformBin, ...]:
    """Group *bins* into at most *count* buckets with the same edge rule."""
    if len(bins) <= count:
        return bins
    np = require("numpy")
    minima = np.fromiter((b.minimum for b in bins), dtype="float32", count=len(bins))
    maxima = np.fromiter((b.maximum for b in bins), dtype="float32", count=len(bins))
    starts = np.linspace(0, len(bins), count + 1, dtype=int)[:-1]
    low = np.minimum.reduceat(minima, starts).tolist()
    high = np.maximum.reduceat(maxima, starts).tolist()
    return tuple(WaveformBin(minimum=float(a), maximum=float(b)) for a, b in zip(low, high))


def encode_pyramid(pyramid: Sequence[Sequence[WaveformBin]]) -> tuple[str, bytes]:
    """Return ``(peak_levels, blob)`` for storage.

    ``peak_levels`` is the comma-separated bin count of each level, finest
    first, so the decoder can split the blob without a header.
    """
    np = require("numpy")
    chunks = []
    for level in pyramid:
        pairs = np.empty((len(level), 2), dtype="float32")
        for index, item in enumerate(level):
            pairs[index, 0] = item.minimum
            pairs[index, 1] = item.maximum
        scaled = np.clip(pairs * _SCALE, -_SCALE, _SCALE)
        # Round outward: minima down, maxima up.
        scaled[:, 0] = np.floor(scaled[:, 0])
        scaled[:, 1] = np.ceil(scaled[:, 1])
        chunks.append(scaled.astype("int8").tobytes())
    return ",".join(str(len(level)) for level in pyramid), b"".join(chunks)


def decode_pyramid(peak_levels: str, blob: bytes) -> tuple[tuple[WaveformBin, ...], ...]:
    """Inverse of :func:`encode_pyramid`."""
    counts = _level_counts(peak_levels, blob)
    return tuple(decode_level(peak_levels, blob, index) for index in range(len(counts)))


def decode_level(peak_levels: str, blob: bytes, index: int = 0) -> tuple[WaveformBin, ...]:
    """Decode one level (finest is 0) without building the others."""
    np = require("numpy")
    counts = _level_counts(peak_levels, blob)
    offset = sum(counts[:index]) * 2
    count = counts[index]
    raw = np.frombuffer(blob, dtype="int8", count=count * 2, offset=offset)
    level = (raw.astype("float32") / _SCALE).reshape(count, 2).tolist()
    return tuple(WaveformBin(minimum=low, maximum=high) for low, high in level)


def _level_counts(peak_levels: str, blob: bytes) -> list[int]:
    counts = [int(part) for part in peak_levels.split(",") if part]
    if sum(counts) * 2 != len(blob):
        raise ValueError("peak blob does not match its level sizes")
    return counts
