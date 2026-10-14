"""Format-agnostic audio decoding to float samples + sample rate.

The backend is chosen by file extension:

* ``soundfile`` (libsndfile) for lossless / native PCM: WAV, FLAC, OGG, AIFF.
* ``audioread`` (ffmpeg) for compressed containers: MP3, AAC, M4A, MP4.
* a dependency-free stdlib :mod:`wave` fallback for WAV when soundfile is absent.

Decoding is strictly read-only: files are opened for reading and never written,
moved, or mutated. Corrupt, unreadable, unsupported, or zero-length inputs raise
:class:`AudioDecodeError` rather than crashing the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .backends import AudioError, BackendUnavailable, is_available, require

# Extensions handled natively by libsndfile via soundfile.
SOUNDFILE_EXTS = {
    ".wav",
    ".wave",
    ".flac",
    ".ogg",
    ".oga",
    ".aiff",
    ".aif",
    ".aifc",
    ".w64",
    ".caf",
}

# Compressed containers routed through audioread/ffmpeg.
AUDIOREAD_EXTS = {
    ".mp3",
    ".aac",
    ".m4a",
    ".mp4",
    ".m4b",
    ".wma",
    ".opus",
}


class AudioDecodeError(AudioError):
    """Raised for corrupt, unreadable, unsupported, or zero-length audio."""


@dataclass(frozen=True)
class DecodedAudio:
    """Decoded PCM audio.

    Attributes:
        samples: numpy float32 array of shape ``(frames, channels)`` with values
            normalized to roughly ``[-1.0, 1.0]``.
        sample_rate: sample rate in Hz.
        backend: name of the backend that produced this result.
    """

    samples: object  # numpy.ndarray (avoid importing numpy at module load)
    sample_rate: int
    backend: str

    @property
    def channels(self) -> int:
        return int(self.samples.shape[1]) if self.samples.ndim == 2 else 1

    @property
    def frames(self) -> int:
        return int(self.samples.shape[0])

    @property
    def duration_seconds(self) -> float:
        return self.frames / self.sample_rate if self.sample_rate else 0.0


def select_backend(ext: str) -> Optional[str]:
    """Return the preferred backend name for *ext* (lower-cased, incl. dot).

    Returns ``"soundfile"`` or ``"audioread"``, or ``None`` when the extension is
    unknown (the caller may then try backends opportunistically).
    """
    ext = ext.lower()
    if ext in SOUNDFILE_EXTS:
        return "soundfile"
    if ext in AUDIOREAD_EXTS:
        return "audioread"
    return None


def decode(path, *, backend: Optional[str] = None) -> DecodedAudio:
    """Decode an audio file to normalized float samples.

    Args:
        path: path to the audio file (str or Path).
        backend: force a specific backend (``"soundfile"``, ``"audioread"``, or
            ``"wave"``). When ``None`` the backend is chosen by extension with an
            automatic fallback to any other available backend.

    Returns:
        A :class:`DecodedAudio` result.

    Raises:
        AudioDecodeError: file is missing, empty, corrupt, or unsupported.
        BackendUnavailable: the only viable backend's library is not installed.
    """
    p = Path(path)
    if not p.exists():
        raise AudioDecodeError(f"Audio file does not exist: {p}")
    if not p.is_file():
        raise AudioDecodeError(f"Not a regular file: {p}")
    if p.stat().st_size == 0:
        raise AudioDecodeError(f"Audio file is empty (zero-length): {p}")

    if backend is not None:
        order = [backend]
    else:
        preferred = select_backend(p.suffix)
        # Build an ordered, de-duplicated candidate list with sensible fallbacks.
        order = []
        for cand in (preferred, "soundfile", "audioread"):
            if cand and cand not in order:
                order.append(cand)

    # Filter to backends whose libraries are importable, but remember whether we
    # skipped any so we can raise BackendUnavailable rather than a misleading
    # decode error when nothing is installed.
    available = [b for b in order if _backend_importable(b)]
    if not available:
        # Surface the install hint for the preferred backend.
        return _raise_unavailable(order)

    last_error: Optional[Exception] = None
    for name in available:
        try:
            return _decode_with(name, p)
        except BackendUnavailable:
            raise
        except AudioDecodeError as exc:
            last_error = exc
        except Exception as exc:  # noqa: BLE001 - normalize backend failures
            last_error = exc

    raise AudioDecodeError(
        f"Failed to decode {p} using backends {available}: {last_error}"
    ) from last_error


def _backend_importable(name: str) -> bool:
    if name == "wave":
        return True  # stdlib, always present
    return is_available(name)


def _raise_unavailable(order):
    for name in order:
        if name in ("soundfile", "audioread", "numpy"):
            require(name)  # raises BackendUnavailable with a helpful message
    raise BackendUnavailable(
        f"No audio decode backend available for backends {order}."
    )


def _decode_with(name: str, p: Path) -> DecodedAudio:
    if name == "soundfile":
        return _decode_soundfile(p)
    if name == "audioread":
        return _decode_audioread(p)
    if name == "wave":
        return _decode_wave_stdlib(p)
    raise AudioDecodeError(f"Unknown decode backend: {name!r}")


def _decode_soundfile(p: Path) -> DecodedAudio:
    sf = require("soundfile")
    try:
        samples, sr = sf.read(str(p), dtype="float32", always_2d=True)
    except Exception as exc:  # noqa: BLE001
        raise AudioDecodeError(f"soundfile could not decode {p}: {exc}") from exc
    if samples.shape[0] == 0:
        raise AudioDecodeError(f"Decoded zero audio frames: {p}")
    return DecodedAudio(samples=samples, sample_rate=int(sr), backend="soundfile")


def _decode_audioread(p: Path) -> DecodedAudio:
    audioread = require("audioread")
    np = require("numpy")
    try:
        with audioread.audio_open(str(p)) as f:
            sr = int(f.samplerate)
            channels = int(f.channels)
            raw = b"".join(f.read_data())
    except Exception as exc:  # noqa: BLE001
        raise AudioDecodeError(f"audioread could not decode {p}: {exc}") from exc

    if not raw:
        raise AudioDecodeError(f"Decoded zero audio frames: {p}")
    # audioread yields interleaved signed 16-bit little-endian PCM.
    ints = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    channels = max(channels, 1)
    usable = (ints.shape[0] // channels) * channels
    samples = ints[:usable].reshape(-1, channels)
    if samples.shape[0] == 0:
        raise AudioDecodeError(f"Decoded zero audio frames: {p}")
    return DecodedAudio(samples=samples, sample_rate=sr, backend="audioread")


def _decode_wave_stdlib(p: Path) -> DecodedAudio:
    """Decode a PCM WAV using only the stdlib (requires numpy for the array)."""
    import wave

    np = require("numpy")
    try:
        with wave.open(str(p), "rb") as w:
            channels = w.getnchannels()
            sampwidth = w.getsampwidth()
            sr = w.getframerate()
            nframes = w.getnframes()
            raw = w.readframes(nframes)
    except Exception as exc:  # noqa: BLE001
        raise AudioDecodeError(f"stdlib wave could not decode {p}: {exc}") from exc

    if nframes == 0 or not raw:
        raise AudioDecodeError(f"Decoded zero audio frames: {p}")

    if sampwidth == 1:  # 8-bit WAV is unsigned
        ints = np.frombuffer(raw, dtype="uint8").astype("float32")
        floats = (ints - 128.0) / 128.0
    elif sampwidth == 2:
        floats = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    elif sampwidth == 4:
        floats = np.frombuffer(raw, dtype="<i4").astype("float32") / 2147483648.0
    else:
        raise AudioDecodeError(
            f"Unsupported WAV sample width {sampwidth * 8}-bit: {p}"
        )

    channels = max(channels, 1)
    samples = floats.reshape(-1, channels)
    return DecodedAudio(samples=samples, sample_rate=int(sr), backend="wave")
