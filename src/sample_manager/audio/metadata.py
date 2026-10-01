"""Fast, decode-free container/tag metadata reading via mutagen.

Reads header/tag information (format, duration, sample rate, channels, bitrate,
bit depth) without decoding audio samples, so it is cheap enough to run over a
whole library. Read-only: files are never modified.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .backends import AudioError, require


class AudioMetadataError(AudioError):
    """Raised when container metadata cannot be read or the format is unknown."""


@dataclass(frozen=True)
class ContainerMetadata:
    """Header-level metadata for an audio file (no samples decoded).

    Any field that a given container does not expose is ``None``.

    Attributes:
        path: the file path as a string.
        extension: lower-cased file extension including the dot (e.g. ``.wav``).
        format: format/codec label (e.g. ``WAVE``, ``FLAC``, ``MP3``).
        duration_seconds: length in seconds.
        sample_rate: sample rate in Hz.
        channels: channel count.
        bitrate: nominal bitrate in bits per second (mainly for lossy formats).
        bit_depth: bits per sample (mainly for PCM/lossless formats).
    """

    path: str
    extension: str
    format: Optional[str]
    duration_seconds: Optional[float]
    sample_rate: Optional[int]
    channels: Optional[int]
    bitrate: Optional[int]
    bit_depth: Optional[int]


def read_metadata(path) -> ContainerMetadata:
    """Read decode-free container metadata for *path*.

    Args:
        path: path to the audio file (str or Path).

    Returns:
        A :class:`ContainerMetadata` result.

    Raises:
        AudioMetadataError: file missing/empty, or unreadable by mutagen.
        BackendUnavailable: mutagen is not installed.
    """
    p = Path(path)
    if not p.exists():
        raise AudioMetadataError(f"Audio file does not exist: {p}")
    if p.stat().st_size == 0:
        raise AudioMetadataError(f"Audio file is empty (zero-length): {p}")

    mutagen = require("mutagen")
    try:
        mf = mutagen.File(str(p))
    except Exception as exc:  # noqa: BLE001 - normalize mutagen failures
        raise AudioMetadataError(f"Could not read metadata for {p}: {exc}") from exc

    if mf is None or getattr(mf, "info", None) is None:
        raise AudioMetadataError(f"Unrecognized or unsupported container: {p}")

    info = mf.info
    return ContainerMetadata(
        path=str(p),
        extension=p.suffix.lower(),
        format=_format_label(mf, p),
        duration_seconds=_opt_float(getattr(info, "length", None)),
        sample_rate=_opt_int(getattr(info, "sample_rate", None)),
        channels=_opt_int(getattr(info, "channels", None)),
        bitrate=_opt_int(getattr(info, "bitrate", None)),
        bit_depth=_opt_int(getattr(info, "bits_per_sample", None)),
    )


def _format_label(mf, p: Path) -> str:
    """Derive a human-readable format label from the mutagen object / extension."""
    # mutagen exposes a friendly name on some info objects.
    pprint = getattr(mf.info, "pprint", None)
    if callable(pprint):
        try:
            text = pprint()
            if text:
                return text.split(",")[0].strip()
        except Exception:  # noqa: BLE001
            pass
    cls = type(mf).__name__  # e.g. WAVE, FLAC, MP3, MP4, OggVorbis
    if cls and cls != "FileType":
        return cls.upper()
    return p.suffix.lower().lstrip(".").upper()


def _opt_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        return None
    return ivalue if ivalue > 0 else None


def _opt_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        fvalue = float(value)
    except (TypeError, ValueError):
        return None
    return fvalue if fvalue > 0 else None
