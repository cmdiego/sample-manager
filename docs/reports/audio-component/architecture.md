# Audio Component Architecture

## Boundary

`sample_manager.audio` owns audio I/O abstractions, decoding, metadata, DSP analysis, playback,
waveform envelope generation, and backend capability reporting.

It does not own:

- database persistence or SQL;
- library navigation or persistent sample selection;
- terminal/GUI rendering;
- frontend keybindings or application layout;
- destructive source-file operations.

## Dependency Direction

```text
Textual / future Qt frontend
        |
        v
AudioPlayer, PlaybackSnapshot, WaveformService, audio DTOs
        |
        +--> decode.py ------> soundfile / audioread / wave / NumPy
        +--> metadata.py ----> mutagen
        +--> analysis.py ----> decoded samples / NumPy
        +--> player.py ------> Decoder + AudioOutput ports
        +--> waveform.py ----> Decoder + NumPy
                              
SoundDeviceOutput implements AudioOutput and lazily imports sounddevice.
```

Frontend and repository modules may depend on audio. Audio never depends on those modules.

## Modules

### `backends.py`

- Defines `AudioError` and `BackendUnavailable`.
- Lazily imports optional dependencies with `require(name)`.
- Reports NumPy, soundfile, audioread, mutagen, and sounddevice availability.
- Converts backend import failures into a stable domain error with an `[audio]` installation hint.

### `decode.py`

- Validates that input exists, is a regular non-empty file, and can be decoded.
- Selects a preferred backend from the extension, then attempts available fallbacks.
- Returns `DecodedAudio(samples, sample_rate, backend)`.
- Normalizes backend failures into `AudioDecodeError` or `BackendUnavailable`.
- Decodes the complete file into memory; it is not a streaming decoder.

### `metadata.py`

- Reads format, duration, sample rate, channels, bitrate, and bit depth without decoding PCM.
- Returns immutable `ContainerMetadata`.
- Raises `AudioMetadataError` for missing, empty, or unrecognized containers.

### `analysis.py`

- Provides pure mono conversion, absolute peak, and RMS calculations.
- `analyze(path)` composes decoding, best-effort metadata, and DSP into `AudioFeatures`.
- Silence maps to negative infinity for peak/RMS dBFS properties.

### `player.py`

- Defines the `Decoder` and `AudioOutput` dependency-inversion ports.
- Owns a worker thread, generation counter, decoded-track cache, playback cursor, state, and errors.
- Public commands are thread-safe and frontend-independent.
- Backend/output exceptions become `ERROR` snapshots instead of escaping worker threads.

### `sounddevice_output.py`

- Implements `AudioOutput` using a lazy sounddevice `OutputStream`.
- Uses `device=None` for the GUI's System Default Output mode, following the host operating
  system's selected default device.
- Copies decoded float PCM into callback buffers and zero-fills the final partial buffer.
- Tracks frame position and reports natural completion to `AudioPlayer`.

### `devices.py`

- Enumerates sounddevice endpoints and returns immutable `AudioOutputDevice` records.
- Filters out devices with no output channels.
- Exposes device index, name, host API, output channel count, default sample rate, and whether the
  endpoint is the operating system's current default output.
- Contains no Qt imports; Settings consumes these DTOs and persists only the selected index/mode.

### `waveform.py`

- Computes signed min/max envelope bins across all samples and channels.
- Uses 4,096 bins by default.
- Caches immutable `WaveformData` in memory with file-identity invalidation.
- Contains no rendering logic.

## Public API

The supported package-level API is re-exported by `sample_manager.audio`.

### Capabilities and Errors

```python
capabilities() -> dict[str, bool]
AudioError
BackendUnavailable
AudioDecodeError
AudioMetadataError
```

### Decode, Metadata, and Analysis

```python
decode(path, *, backend=None) -> DecodedAudio
select_backend(ext) -> str | None
read_metadata(path) -> ContainerMetadata
analyze(path) -> AudioFeatures
to_mono(samples)
compute_peak(samples) -> float
compute_rms(samples) -> float
```

### Playback

```python
player = AudioPlayer(decoder=..., output=...)
player.play(path)             # resume same paused track, otherwise replace
player.play_from_start(path)  # always begin at frame zero
player.pause()
player.snapshot() -> PlaybackSnapshot
player.close()
```

Frontend transport policy is intentionally separate from these primitives: Space pauses active
playback or starts the focused sample from zero, while Ctrl+Space calls `play(snapshot.path)` only
for a paused snapshot, resuming from the player's retained frame checkpoint.

### Waveform

```python
compute_waveform_envelope(samples, bucket_count) -> tuple[WaveformBin, ...]
WaveformService(...).load(path) -> WaveformData
DEFAULT_WAVEFORM_BUCKETS == 4096
```

## State and Concurrency Invariants

- Audio commands must not block a frontend on file decoding.
- A newer play request invalidates older decode and completion callbacks.
- Adapter calls occur outside the player-state lock to avoid callback lock inversion.
- A playback error is observable through a snapshot and does not terminate the application.
- Natural completion retains the path but resets position and state to idle.
- Closing is idempotent and invalidates all outstanding generations.
- Waveform cache access is lock-protected; cached DTOs are immutable.

## Dependency and Runtime Policy

Core GUI installations include the playback path, while compressed-format and metadata helpers
remain optional:

```text
standard: numpy       numeric PCM/DSP operations
standard: soundfile   libsndfile-backed decoding
standard: sounddevice host audio playback
optional: audioread   compressed-container decoding, typically through ffmpeg
optional: mutagen     container/tag metadata
```

Availability does not guarantee runtime viability: audioread may still require ffmpeg, and
sounddevice requires a usable host output device.

## Testing Strategy

- Pure DSP uses deterministic in-memory arrays.
- Decode and metadata tests use synthetic WAV fixtures and capability-gated compressed formats.
- Player tests inject fake decoders and output adapters; no speaker is required.
- The sounddevice adapter is tested with a fake stream and callback buffers.
- Waveform tests cover extrema, channels, clipping, cache invalidation, rendering dimensions, and
  playback cursor output.
- Frontend integration tests inject a fake player and verify focus, Space restart, and cleanup.

## Known Limitations

- Playback and waveform services decode the same focused file independently.
- Full-file PCM decoding increases latency and memory use for large/compressed files.
- Background decode cannot be interrupted after the backend call begins; stale results are ignored.
- Only the default output device is currently used.
- Playback has no public stop, seek, volume, routing, queue, or looping API.
- Waveform cache is process-local and stores a single fixed overview resolution.
- Terminal rendering is character-cell constrained; this is a frontend limitation, not a DSP limit.
- Artwork is absent despite appearing in historical Task 005/006 plans.

## Change Rules

- New output backends implement `AudioOutput`; do not add backend branches to the frontend.
- New analysis functions should separate pure DSP from file I/O.
- New frontend needs should consume immutable DTOs rather than raw backend objects.
- Do not import Textual or PySide6 into the audio package.
- Preserve read-only treatment of source audio unless a separately approved destructive workflow is
  designed with explicit safety and history guarantees.
