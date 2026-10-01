# Audio Component History

## Summary

The Audio component was introduced and expanded on 2026-07-07 in three delivered increments:
analysis and decoding, asynchronous playback, and waveform generation/display integration. The
implementation deliberately kept audio signal processing separate from database and frontend code.

## 1. Analysis Foundation

**Origin:** Task 004, Audio Analysis: First Steps.

The first increment established `src/sample_manager/audio/` as a read-only domain package.

### Delivered

- `backends.py` introduced lazy optional imports, capability reporting, `AudioError`, and
  `BackendUnavailable` with an actionable installation hint.
- `decode.py` introduced `DecodedAudio` and format-oriented routing:
  - soundfile for WAV, FLAC, OGG, AIFF, and related libsndfile formats;
  - audioread for MP3, AAC, M4A/MP4, WMA, Opus, and related compressed formats;
  - stdlib `wave` as an explicit WAV fallback, with NumPy conversion.
- Decoded samples were normalized to float PCM with a `(frames, channels)` representation.
- `metadata.py` introduced decode-free metadata extraction through mutagen.
- `analysis.py` introduced pure `to_mono`, `compute_peak`, and `compute_rms` helpers plus
  `AudioFeatures` and dBFS properties.
- `pyproject.toml` gained the optional `[audio]` dependency group.
- Hermetic synthetic-WAV tests covered decoding, metadata, DSP, corrupt input, empty input, and
  optional compressed formats.

### Decisions

- Heavy audio dependencies remain optional and lazily imported.
- Analysis never mutates, moves, or rewrites source audio.
- The package has no Textual or SQL dependencies.
- Metadata failure is best-effort during full analysis; successful decoding can still produce
  useful features.

### Validation at Delivery

Task 004 reported 32 audio tests passing. Four unrelated Textual Pilot failures existed at that
point and were subsequently resolved outside the audio domain.

## 2. Playback Architecture

**Origin:** The first playback request asked for Play, Pause, Next, and Previous. Product scope was
then reduced to a single-track player. Next and Previous were explicitly removed.

### Delivered

- `player.py` introduced a headless `AudioPlayer` with injected `Decoder` and `AudioOutput` ports.
- Playback state became observable through immutable `PlaybackSnapshot` values and
  `PlaybackStatus`: `IDLE`, `LOADING`, `PLAYING`, `PAUSED`, and `ERROR`.
- Decode work runs on a dedicated daemon worker thread rather than the frontend thread.
- Generation IDs enforce latest-request-wins behavior and suppress stale decode results.
- `play(path)` resumes a paused copy of the same file and replaces a different file.
- `play_from_start(path)` explicitly restarts from frame zero.
- `pause()` preserves the output frame position; natural completion resets position to zero.
- `close()` is idempotent and releases worker/output resources.
- `sounddevice_output.py` implemented the optional output adapter with callback-driven PCM writes.
- Adapter calls were moved outside player-state critical sections after a lock-order audit found a
  potential callback/stream-stop deadlock.

### TUI Integration History

- Focused files initially auto-played through the Textual application.
- Space was first assigned as a global Play/Pause toggle.
- Space behavior was later changed to always restart the focused sample from the beginning.
- Space was subsequently changed into a pause/start toggle: active or loading playback pauses;
  otherwise the focused sample starts from zero. `Ctrl+Space` resumes a paused track from the
  frame checkpoint retained by `AudioPlayer`.
- Space remains global during filter mode so it is not consumed as filter text.
- Directories do not replace the current audio track.
- Application unmount closes the player before closing the database.

### Scope Changes

The original Task 005 plan included stop, seek, output-device selection, artwork, and waveform data.
The delivered playback scope intentionally omitted public Stop, seek, volume, routing controls,
Next, Previous, and playlists. Artwork was not implemented.

### System Default Output Setting

After the Qt cutover, playback output became an explicit GUI setting under Settings → I/O. The
default mode constructs `SoundDeviceOutput(device=None)`, which delegates device choice to the
operating system. A `Disabled` mode removes and closes the active player. Changes apply immediately
through controller-level player replacement, while the selected mode persists in `QSettings`.

Device discovery was subsequently added through `list_output_devices()`. On macOS, Settings → I/O
shows output-capable Core Audio endpoints with channel counts and marks the current system default.
Users can persist a specific sounddevice index; playback then constructs
`SoundDeviceOutput(device=index)` instead of following the default device.

NumPy, soundfile, and sounddevice became standard application dependencies so normal GUI installs
include WAV decoding and real output support. Optional compressed decoding and metadata backends
remain in the `[audio]` extra.

## 3. Waveform Data and TUI Display

**Origin:** The preview panel required waveform data without moving DSP or decoding into Textual.

### Delivered Audio Domain

- `waveform.py` introduced immutable `WaveformBin` and `WaveformData` DTOs.
- `compute_waveform_envelope` computes signed minimum/maximum buckets across all channels, avoiding
  phase cancellation from mono averaging.
- Values are clamped to the normalized `[-1.0, 1.0]` amplitude range.
- `WaveformService` decodes asynchronously when called by the frontend and caches results in a
  thread-safe 64-entry LRU.
- Cache keys include resolved path, file size, and modification time so changed files invalidate
  old envelopes.
- Default envelope resolution started at 1,024 bins and was raised to 4,096 bins.

### Delivered Textual Integration

- A presentation-only `WaveformWidget` was placed inside the white Preview container.
- The widget renders a signed min/max envelope, center line, playback cursor, loading state, and
  decode/backend error state.
- Waveform loading uses an exclusive Textual worker plus generation checks for stale focus results.
- Playback position updates through the existing 200 ms player polling interval.
- Display height started at three terminal rows and was raised to five.

### Performance Findings

Profiling the included 2.5 MB, 9.8-second WAV produced approximately:

- 33 ms initial soundfile decode;
- 3 ms for a 1,024-bin envelope;
- less than 1 ms for a cache hit.

Observed delays are primarily caused by decoding playback and waveform data independently, full
decode requirements for compressed files, and uncancellable background decode work during rapid
focus changes. Increasing envelope bins does not solve those issues.

### Rendering Limitation

The terminal waveform remains limited by visible character cells. A roughly 150-column by five-row
display compresses hundreds of thousands of samples into 150 horizontal output positions and only
a few amplitude levels. Raising source bins preserves extrema but cannot create additional terminal
pixels. This limitation motivated the planned Qt migration and its `QPainter` waveform.

## 4. Qt Migration Impact

Task 007 plans to retain the Audio component unchanged as a headless dependency while replacing
the Textual waveform renderer with a pixel-based Qt widget.

Expected audio-side evolution for Qt:

- range-and-width envelope queries or a multiresolution peak pyramid;
- shared decoded/peak caching to avoid duplicate playback and waveform decoding;
- bounded worker coordination with GUI generation IDs;
- optional zoom/pan data access without exposing NumPy arrays to widgets.

The Qt frontend must continue depending on audio DTOs and ports; the audio package must not import
PySide6.

## Deferred Work

- Embedded artwork extraction and presentation.
- Public stop, seek, volume, mute, and output-device selection.
- Playlist/queue behavior, Next, Previous, looping, and automatic advance.
- Shared decode cache between playback and waveform analysis.
- Streaming waveform analysis for large or compressed files.
- Persistent multiresolution peak files.
- Loudness standards, BPM, key, transient classification, spectral analysis, and similarity.
