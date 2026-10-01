"""Audio feature extraction: peak / RMS on top of decoded samples.

The DSP math (:func:`to_mono`, :func:`compute_peak`, :func:`compute_rms`) is
pure and deterministic: it takes a numpy array in and returns plain floats, with
no file IO, so it is unit-testable without audio hardware. :func:`analyze` wires
decode + metadata + math into a single typed :class:`AudioFeatures` result.

Read-only: no user audio file is ever mutated or moved.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .backends import require
from .decode import decode
from .metadata import AudioMetadataError, read_metadata

# Reference for dBFS: full-scale sine/peak amplitude of 1.0 -> 0 dBFS.
_SILENCE_DBFS = -math.inf


@dataclass(frozen=True)
class AudioFeatures:
    """Typed result of analyzing an audio file.

    Attributes:
        path: analyzed file path (string).
        format: format/codec label (from metadata, else the extension).
        duration_seconds: length in seconds (derived from decoded frames).
        sample_rate: sample rate in Hz.
        channels: channel count.
        bit_depth: bits per sample where known (else ``None``).
        peak: peak absolute amplitude across all channels, in ``[0.0, ~1.0]``.
        rms: RMS level of the mono-summed signal, in ``[0.0, ~1.0]``.
    """

    path: str
    format: Optional[str]
    duration_seconds: float
    sample_rate: int
    channels: int
    bit_depth: Optional[int]
    peak: float
    rms: float

    @property
    def peak_dbfs(self) -> float:
        """Peak level in dBFS (``-inf`` for digital silence)."""
        return _to_dbfs(self.peak)

    @property
    def rms_dbfs(self) -> float:
        """RMS level in dBFS (``-inf`` for digital silence)."""
        return _to_dbfs(self.rms)


# --------------------------------------------------------------------------- #
# Pure DSP helpers (numpy in -> plain float/array out, no IO)
# --------------------------------------------------------------------------- #

def to_mono(samples):
    """Return a 1-D mono mix of *samples* by averaging channels.

    Accepts a 1-D array (returned unchanged) or a 2-D ``(frames, channels)``
    array. Pure: does not read or write anything.
    """
    np = require("numpy")
    arr = np.asarray(samples, dtype="float64")
    if arr.ndim == 1:
        return arr
    if arr.ndim == 2:
        if arr.shape[1] == 1:
            return arr[:, 0]
        return arr.mean(axis=1)
    raise ValueError(f"Expected 1-D or 2-D samples, got ndim={arr.ndim}")


def compute_peak(samples) -> float:
    """Peak absolute amplitude across every sample/channel. Pure."""
    np = require("numpy")
    arr = np.asarray(samples, dtype="float64")
    if arr.size == 0:
        return 0.0
    return float(np.max(np.abs(arr)))


def compute_rms(samples) -> float:
    """Root-mean-square level of the mono-summed signal. Pure.

    Channels are averaged to mono first, then RMS is computed over time.
    """
    np = require("numpy")
    mono = to_mono(samples)
    if mono.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(mono, dtype="float64"))))


def _to_dbfs(linear: float) -> float:
    if linear <= 0.0:
        return _SILENCE_DBFS
    return 20.0 * math.log10(linear)


# --------------------------------------------------------------------------- #
# IO-backed analysis
# --------------------------------------------------------------------------- #

def analyze(path) -> AudioFeatures:
    """Decode *path*, compute peak/RMS, and assemble :class:`AudioFeatures`.

    Duration, sample rate, and channel count come from the decoded stream (most
    accurate). Format label and bit depth are best-effort from the container
    metadata; if metadata reading fails, analysis still succeeds with those
    fields degraded (``format`` from the extension, ``bit_depth=None``).

    Raises:
        AudioDecodeError: file missing/empty/corrupt/unsupported.
        BackendUnavailable: no viable decode backend is installed.
    """
    p = Path(path)
    decoded = decode(p)

    fmt: Optional[str] = None
    bit_depth: Optional[int] = None
    try:
        meta = read_metadata(p)
        fmt = meta.format
        bit_depth = meta.bit_depth
    except AudioMetadataError:
        pass  # degrade: keep going with decoded data only
    except Exception:  # noqa: BLE001 - metadata is best-effort
        pass

    if not fmt:
        fmt = p.suffix.lower().lstrip(".").upper() or None

    return AudioFeatures(
        path=str(p),
        format=fmt,
        duration_seconds=decoded.duration_seconds,
        sample_rate=decoded.sample_rate,
        channels=decoded.channels,
        bit_depth=bit_depth,
        peak=compute_peak(decoded.samples),
        rms=compute_rms(decoded.samples),
    )
