"""Persisted GUI settings and stable value contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QSettings

AUDIO_OUTPUT_MODE_KEY = "io/audio_output_mode"
AUDIO_OUTPUT_DEVICE_KEY = "io/audio_output_device"


class AudioOutputMode(str, Enum):
    SYSTEM_DEFAULT = "system_default"
    SPECIFIC_DEVICE = "specific_device"
    DISABLED = "disabled"


@dataclass(frozen=True)
class AudioOutputSelection:
    mode: AudioOutputMode = AudioOutputMode.SYSTEM_DEFAULT
    device_index: int | None = None


def load_audio_output_selection(
    settings: QSettings | None = None,
) -> AudioOutputSelection:
    store = settings if settings is not None else QSettings()
    mode = load_audio_output_mode(store)
    if mode is not AudioOutputMode.SPECIFIC_DEVICE:
        return AudioOutputSelection(mode)
    value = store.value(AUDIO_OUTPUT_DEVICE_KEY)
    try:
        return AudioOutputSelection(mode, int(value))
    except (TypeError, ValueError):
        return AudioOutputSelection()


def save_audio_output_selection(
    selection: AudioOutputSelection,
    settings: QSettings | None = None,
) -> None:
    store = settings if settings is not None else QSettings()
    store.setValue(AUDIO_OUTPUT_MODE_KEY, selection.mode.value)
    if selection.device_index is None:
        store.remove(AUDIO_OUTPUT_DEVICE_KEY)
    else:
        store.setValue(AUDIO_OUTPUT_DEVICE_KEY, selection.device_index)
    store.sync()


def load_audio_output_mode(settings: QSettings | None = None) -> AudioOutputMode:
    store = settings if settings is not None else QSettings()
    value = store.value(AUDIO_OUTPUT_MODE_KEY, AudioOutputMode.SYSTEM_DEFAULT.value)
    try:
        return AudioOutputMode(str(value))
    except ValueError:
        return AudioOutputMode.SYSTEM_DEFAULT


def save_audio_output_mode(
    mode: AudioOutputMode,
    settings: QSettings | None = None,
) -> None:
    save_audio_output_selection(AudioOutputSelection(mode), settings)
