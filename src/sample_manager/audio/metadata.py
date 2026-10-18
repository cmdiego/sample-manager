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
        tags: normalized embedded tag labels/values; binary fields are summaries.
    """

    path: str
    extension: str
    format: Optional[str]
    duration_seconds: Optional[float]
    sample_rate: Optional[int]
    channels: Optional[int]
    bitrate: Optional[int]
    bit_depth: Optional[int]
    tags: tuple[tuple[str, str], ...] = ()


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
        tags=_read_tags(mf),
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


# ID3, MP4 and Vorbis use different keys for the same common fields. Unknown
# keys remain visible so custom sample-pack metadata is not silently dropped.
_TAG_LABELS = {
    "TIT2": "Title", "TPE1": "Artist", "TPE2": "Album artist", "TALB": "Album",
    "TRCK": "Track", "TPOS": "Disc", "TDRC": "Date", "TYER": "Year",
    "TCON": "Genre", "TBPM": "BPM", "TKEY": "Key", "COMM": "Comment",
    "TCOM": "Composer", "TCOP": "Copyright", "TSSE": "Encoder",
    "USLT": "Lyrics", "APIC": "Artwork", "TXXX": "Custom", "WXXX": "URL",
    "©nam": "Title", "©ART": "Artist", "aART": "Album artist", "©alb": "Album",
    "©day": "Date", "©gen": "Genre", "©cmt": "Comment", "©wrt": "Composer",
    "©too": "Encoder", "trkn": "Track", "disk": "Disc", "tmpo": "BPM",
    "covr": "Artwork", "cprt": "Copyright",
    "bpm": "BPM", "initialkey": "Key", "albumartist": "Album artist",
    "tracknumber": "Track", "discnumber": "Disc",
}
_TAG_ORDER = ("Title", "Artist", "Album", "Album artist", "Track", "Disc", "Date", "Year", "Genre", "BPM", "Key", "Comment")


def _clean_text(value) -> str:
    """Remove terminal controls while preserving ordinary Unicode tag text."""
    return " ".join("".join(char if char.isprintable() else " " for char in str(value)).split())


def _tag_text(value) -> str:
    """Render tag text/numbers while summarizing artwork and binary payloads."""
    if isinstance(value, bytes):
        # MP4 freeform fields carry an explicit text encoding; covers and
        # opaque payloads do not. Decode only declared textual values.
        encoding = {1: "utf-8", 2: "utf-16-be", 3: "shift-jis"}.get(getattr(value, "dataformat", None))
        if encoding:
            return _clean_text(value.decode(encoding, errors="replace"))
        return f"{len(value):,} bytes (binary)"
    if isinstance(value, (list, tuple)):
        return "; ".join(filter(None, (_tag_text(part) for part in value)))
    # ID3 frames expose text, URL, or binary data rather than plain strings.
    if hasattr(value, "text"):
        return _tag_text(value.text)
    if hasattr(value, "url"):
        return _clean_text(value.url)
    if hasattr(value, "data"):
        mime = _clean_text(getattr(value, "mime", "binary"))
        return f"{mime} · {len(value.data):,} bytes"
    if hasattr(value, "value"):
        return _tag_text(value.value)
    return _clean_text(value)


def _read_tags(mf) -> tuple[tuple[str, str], ...]:
    """Extract all exposed tags without decoding audio or changing the file."""
    rows = []
    for key, value in (getattr(mf, "tags", None) or {}).items():
        raw_key = str(key)
        base, separator, qualifier = raw_key.partition(":")
        label = _TAG_LABELS.get(base, _TAG_LABELS.get(base.lower(), base.replace("_", " ").title()))
        # Descriptions distinguish multiple comments, custom fields and URLs.
        if separator and qualifier:
            label += f" ({_clean_text(qualifier)})"
        if base.lower() in ("metadata_block_picture", "coverart"):
            text = "Embedded artwork (encoded image data)"
        elif base in ("trkn", "disk") and value:
            text = "/".join(str(number) for number in value[0])
        else:
            text = _tag_text(value)
        if text:
            rows.append((_clean_text(label), text))
    # FLAC pictures live outside its Vorbis tag dictionary.
    for index, picture in enumerate(getattr(mf, "pictures", ())):
        rows.append((f"Artwork {index + 1}", _tag_text(picture)))
    priority = {label: index for index, label in enumerate(_TAG_ORDER)}
    rows.sort(key=lambda row: (priority.get(row[0], len(priority)), row[0].casefold()))
    return tuple(rows)
