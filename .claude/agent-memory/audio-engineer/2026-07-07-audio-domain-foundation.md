# Task 004 — audio domain foundation (locked-in decisions)

## Package layout
`src/sample_manager/audio/`: `backends.py` (lazy import + capability report),
`decode.py`, `metadata.py`, `analysis.py`, `__init__.py` (public API re-export).
No Textual, no SQL, read-only. Deps are the OPTIONAL `[audio]` extra in pyproject.

## Library choices & why
- **numpy** — sample array math (peak/RMS). Small, cross-platform.
- **soundfile** (libsndfile) — WAV/FLAC/OGG/AIFF decode. Also decode-generate for tests.
- **audioread** — MP3/AAC/M4A/MP4 via a **system ffmpeg** (NOT bundled). audioread yields
  interleaved signed 16-bit LE PCM (we /32768).
- **mutagen** — decode-free container/tag metadata (duration/sr/channels/bitrate/bit_depth).

## Cross-platform gotchas
- ffmpeg is a **system** dependency for compressed formats; not present in this dev box.
  Compressed decode degrades to `AudioDecodeError`/skip when ffmpeg absent.
- This machine's libsndfile build ALSO decodes MP3 (`'MP3' in sf.available_formats()`),
  so MP3 can round-trip via soundfile without ffmpeg — but do NOT rely on it cross-platform.
  Tests guard MP3/FLAC/OGG on `sf.available_formats()`.
- decode.py has a dependency-free **stdlib `wave` fallback** for WAV (needs only numpy),
  selectable via `decode(path, backend="wave")`. Keeps WAV usable without soundfile.

## API contract (for service/TUI wiring)
- `capabilities() -> dict[str,bool]` keys: numpy, soundfile, audioread, mutagen.
- `decode(path, *, backend=None) -> DecodedAudio(samples[frames,channels] float32, sample_rate,
  backend; props channels/frames/duration_seconds)`.
- `read_metadata(path) -> ContainerMetadata(path, extension, format, duration_seconds,
  sample_rate, channels, bitrate, bit_depth)` — fields None when unavailable.
- `analyze(path) -> AudioFeatures(path, format, duration_seconds, sample_rate, channels,
  bit_depth, peak, rms; props peak_dbfs/rms_dbfs)`. Duration/sr/channels from decoded stream;
  format+bit_depth best-effort from metadata (degrades if mutagen fails).
- Pure DSP (numpy in -> float out, no IO): `to_mono`, `compute_peak` (max|abs| all chans),
  `compute_rms` (mono-mixed).
- Exceptions: `AudioError` base -> `BackendUnavailable`, `AudioDecodeError`, `AudioMetadataError`.
  Callers map to exit_codes (BackendUnavailable ~ config/6, decode ~ general/1).

## Test note
- `write_sine_wav` fixture in tests/conftest.py generates PCM WAV via stdlib only (hermetic).
- Pre-existing failing tests NOT ours: `tests/test_tui_pilot.py` (4, tui-architect WIP).
  Also watch stale pytest assertion-rewrite cache on untracked WIP test files — clear
  `.pytest_cache` if a static-mapping test mysteriously "fails".
