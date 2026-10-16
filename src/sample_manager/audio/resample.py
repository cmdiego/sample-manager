"""Convert decoded PCM to the output device's sample rate and channel layout.

The persistent output stream runs at the device's native rate, so every source
is conformed once, off the audio thread, before it reaches the mixer. ``soxr``
provides high-quality resampling; a linear-interpolation fallback keeps
playback working when it is not importable.
"""

from __future__ import annotations

from .backends import is_available, require


def conform(samples, source_rate: int, target_rate: int, channels: int):
    """Return C-contiguous float32 ``(frames, channels)`` PCM at *target_rate*.

    Mono sources are duplicated across output channels, extra source channels
    beyond the output's are dropped, and a mono output receives the channel
    mean. Matching rates pass through without resampling.
    """
    np = require("numpy")
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError("sample rates must be positive")
    if channels <= 0:
        raise ValueError("channels must be positive")

    pcm = np.asarray(samples, dtype="float32")
    if pcm.ndim == 1:
        pcm = pcm[:, None]
    pcm = _map_channels(np, pcm, channels)
    if source_rate != target_rate and pcm.shape[0]:
        pcm = _resample(np, pcm, source_rate, target_rate)
    return np.ascontiguousarray(pcm, dtype="float32")


def _map_channels(np, pcm, channels: int):
    source_channels = pcm.shape[1]
    if source_channels == channels:
        return pcm
    if channels == 1:
        return pcm.mean(axis=1, keepdims=True)
    if source_channels == 1:
        return np.repeat(pcm, channels, axis=1)
    if source_channels > channels:
        return pcm[:, :channels]
    # Fewer source channels than outputs: leave the extra outputs silent.
    padded = np.zeros((pcm.shape[0], channels), dtype="float32")
    padded[:, :source_channels] = pcm
    return padded


def _resample(np, pcm, source_rate: int, target_rate: int):
    if is_available("soxr"):
        soxr = require("soxr")
        return soxr.resample(pcm, source_rate, target_rate, quality="HQ")
    frames = pcm.shape[0]
    target_frames = max(1, round(frames * target_rate / source_rate))
    positions = np.arange(target_frames, dtype="float64") * (source_rate / target_rate)
    source_index = np.arange(frames, dtype="float64")
    return np.stack(
        [np.interp(positions, source_index, pcm[:, channel]) for channel in range(pcm.shape[1])],
        axis=1,
    ).astype("float32")
