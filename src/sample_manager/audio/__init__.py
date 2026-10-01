"""Decoupled audio analysis and playback domain.

Public API (see the individual modules for details):

* Backends / capability reporting:
    - :func:`capabilities` -> dict[str, bool]
    - :exc:`AudioError`, :exc:`BackendUnavailable`
* Decoding (:mod:`.decode`):
    - :func:`decode` -> :class:`DecodedAudio`
    - :exc:`AudioDecodeError`
* Metadata (:mod:`.metadata`):
    - :func:`read_metadata` -> :class:`ContainerMetadata`
    - :exc:`AudioMetadataError`
* Analysis (:mod:`.analysis`):
    - :func:`analyze` -> :class:`AudioFeatures`
    - pure DSP: :func:`to_mono`, :func:`compute_peak`, :func:`compute_rms`
* Playback (:mod:`.player`):
    - :class:`AudioPlayer`, :class:`PlaybackSnapshot`, :class:`PlaybackStatus`

Backends are imported lazily. NumPy, soundfile, and sounddevice are standard
runtime dependencies; audioread and mutagen are in the optional ``[audio]``
extra. Audio processing never mutates or moves user audio files.
"""

from __future__ import annotations

from .analysis import (
    AudioFeatures,
    analyze,
    compute_peak,
    compute_rms,
    to_mono,
)
from .backends import (
    AudioError,
    BackendUnavailable,
    capabilities,
)
from .decode import (
    AudioDecodeError,
    DecodedAudio,
    decode,
    select_backend,
)
from .devices import AudioOutputDevice, list_output_devices
from .metadata import (
    AudioMetadataError,
    ContainerMetadata,
    read_metadata,
)
from .player import AudioPlayer, PlaybackSnapshot, PlaybackStatus
from .waveform import (
    DEFAULT_WAVEFORM_BUCKETS,
    WaveformBin,
    WaveformData,
    WaveformService,
    compute_waveform_envelope,
)

__all__ = [
    # backends
    "capabilities",
    "AudioError",
    "BackendUnavailable",
    # decode
    "decode",
    "select_backend",
    "DecodedAudio",
    "AudioDecodeError",
    # devices
    "AudioOutputDevice",
    "list_output_devices",
    # metadata
    "read_metadata",
    "ContainerMetadata",
    "AudioMetadataError",
    # analysis
    "analyze",
    "AudioFeatures",
    "to_mono",
    "compute_peak",
    "compute_rms",
    # playback
    "AudioPlayer",
    "PlaybackSnapshot",
    "PlaybackStatus",
    # waveform
    "DEFAULT_WAVEFORM_BUCKETS",
    "WaveformBin",
    "WaveformData",
    "WaveformService",
    "compute_waveform_envelope",
]
