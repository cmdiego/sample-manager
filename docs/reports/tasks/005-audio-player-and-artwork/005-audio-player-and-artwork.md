# Audio: Media Player, Cover-Art Extraction & Waveform Data

## Goal
Grow the `sample_manager.audio` domain with a playback engine (media player + sound routing),
embedded cover-art extraction, and a downsampled waveform peak-array data API — all as
signal/data capabilities the TUI can drive and render.

## Context / Motivation
Next development step after audio first-steps (Task 004). The user wants to audition samples, see
their waveform, and see embedded album art (with a default stock image when none is present).
Per the established boundary, audio produces engine control + data; the TUI (Task 006) renders.

## Dependencies
- **Blocked by**: none (builds on Task 004's audio package)
- **Requires feature**: possibly a playback backend dep (e.g. sounddevice/simpleaudio) under the
  optional `[audio]` extra
- **Read first**: `.claude/agents/audio-engineer.md`, `src/sample_manager/audio/` (existing),
  `docs/reports/tasks/004-audio-analysis-first-steps/004-audio-analysis-first-steps.md`

## Scope
- `engine.py`: play/pause/stop/seek for a decoded file; output-device (sound routing) selection;
  non-blocking playback with a clean, mockable interface.
- `artwork.py`: extract embedded cover-art bytes + mime from the container (mutagen); return None
  when absent. Read-only. Does NOT supply or render a default image (that's the TUI's job).
- `analysis.py`: add `waveform_peaks(path_or_samples, buckets) -> list[(min,max)]` (or similar)
  pure data API for the TUI to render.

## Non-Goals
- Any rendering/display (waveform pixels, image widget, stock-image fallback) — Task 006 (TUI).
- Effects/DSP transforms, real-time streaming from network, format conversion/transcoding.

## Design / Approach
- Keep the engine behind a small interface so tests can run headless (no real audio device).
- Playback deps go under the optional `[audio]` extra, lazily imported; degrade gracefully when
  no audio device/backend is available.
- Waveform peak computation is pure and unit-testable (reuse `to_mono` from analysis).
- No Textual imports, no SQL. Expose a clean Python API for the orchestrator to wire to the TUI.

## Implementation Steps
1. Choose + add an optional playback backend to `[audio]` in `pyproject.toml`.
2. Implement `artwork.py` (cover-art bytes/mime, None when absent) with tests.
3. Implement `analysis.waveform_peaks(...)` (pure) with tests over synthetic tones.
4. Implement `engine.py` (play/pause/stop/seek + device selection) behind a mockable interface.
5. Run `pytest tests/ -v`; confirm green. Report the public API surface for Task 006 to consume.

## Testing
- Cover-art extraction returns bytes for a tagged file and None for a bare WAV.
- `waveform_peaks` returns the requested bucket count with sane min/max envelope.
- Engine transitions are tested against a mocked backend (no hardware).
- `pytest tests/ -v` stays green.

## Resolved Decisions
- Audio extracts artwork bytes; the TUI owns the default stock-image fallback and all rendering.
- Playback deps are optional and lazily imported, consistent with the audio domain's philosophy.
