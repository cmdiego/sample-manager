"""Lazy backend loading and capability reporting for the audio domain.

NumPy, soundfile, and sounddevice are standard runtime dependencies. Audioread
and mutagen live in the optional ``[audio]`` extra. Nothing here is imported at
module load time; callers receive a normalized :class:`BackendUnavailable` error.
"""

from __future__ import annotations

import importlib
from typing import Any

_OPTIONAL_BACKENDS = frozenset({"audioread", "mutagen"})

# Human-facing purpose per backend, used in error messages.
_BACKEND_PURPOSE = {
    "numpy": "numeric sample processing",
    "soundfile": "decoding WAV/FLAC/OGG/AIFF (libsndfile)",
    "audioread": "decoding MP3/AAC/M4A/MP4 (ffmpeg)",
    "mutagen": "reading container/tag metadata",
    "sounddevice": "audio playback",
}


class AudioError(Exception):
    """Base class for all audio-domain errors."""


class BackendUnavailable(AudioError):
    """A required optional backend library is not importable."""


def is_available(module_name: str) -> bool:
    """Return True if *module_name* can be imported, without raising."""
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False


def require(module_name: str) -> Any:
    """Import and return *module_name*, or raise :class:`BackendUnavailable`.

    The error message names the backend's purpose and how to install it so the
    caller can surface a clear, actionable message.
    """
    try:
        return importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - normalize any import failure
        purpose = _BACKEND_PURPOSE.get(module_name, "audio processing")
        if module_name in _OPTIONAL_BACKENDS:
            hint = 'install the audio extra with: pip install "sample-manager[audio]"'
        else:
            hint = "reinstall sample-manager to restore its runtime dependencies"
        raise BackendUnavailable(
            f"Audio backend '{module_name}' (for {purpose}) is not available. "
            f"To enable it, {hint}."
        ) from exc


def capabilities() -> dict[str, bool]:
    """Report which audio backends are importable right now.

    Returns a mapping of backend name -> availability. Useful for a service or
    the CLI/TUI to decide which formats can be analyzed before attempting IO.
    """
    return {name: is_available(name) for name in _BACKEND_PURPOSE}
