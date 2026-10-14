# Audio Analysis: First Steps

## Goal
Create the `sample_manager.audio` domain and implement the first steps of audio file analysis:
read metadata and compute basic features for popular formats (WAV, FLAC, MP3, AAC, M4A/MP4, OGG),
exposing a clean, testable Python API that the service/TUI layers can consume later.

## Context / Motivation
The user wants audio understanding in the tool (analysis, and eventually a playback/sound-routing
engine and waveform previews). This task establishes the domain, its dependencies, and a minimal
analysis capability. It is the foundation for later work (waveform peaks for the TUI, loudness,
key/BPM, playback).

## Dependencies
- **Blocked by**: none (greenfield)
- **Requires feature**: introduces an optional `[audio]` dependency extra in `pyproject.toml`
- **Read first**: `docs/00-vision.md` (non-destructive, cross-platform invariants),
  `src/sample_manager/exit_codes.py`, `.claude/agents/audio-engineer.md` (domain boundary)

## Scope
- New package `src/sample_manager/audio/` with `decode.py`, `metadata.py`, `analysis.py`.
- Metadata extraction: format/codec, duration, sample rate, channels, bit depth (where available).
- Basic analysis: peak amplitude and RMS level (mono-summed), returned as a typed result object.
- Format coverage via appropriate libs: soundfile (WAV/FLAC/OGG), audioread/ffmpeg (MP3/AAC/MP4),
  mutagen (container tags). Lazy imports; degrade gracefully when a backend is missing.
- Optional `[audio]` extra in `pyproject.toml`. No new hard/core dependencies.

## Non-Goals
- **Waveform visual rendering** — TUI agent's responsibility. (This task may compute a
  downsampled peak array as data, but must not render it.)
- Playback engine / sound routing — future audio-agent task.
- Key/BPM detection, spectral/embedding features, similarity search.
- Persisting analysis results to the DB (wire-up is a later service-layer task).

## Design / Approach
- Keep pure DSP (peak/RMS math) separate from I/O so it is unit-testable without hardware.
- `decode.py`: format-agnostic decode to float samples + sample rate, backend chosen by ext,
  raising a well-defined exception on unreadable/corrupt files.
- `metadata.py`: fast, decode-free container/tag read (mutagen) for duration/sr/channels/bitrate.
- `analysis.py`: typed `AudioFeatures` result; compute peak/RMS from decoded samples.
- Analysis is strictly read-only; never mutate/move user audio files.
- No Textual imports, no SQL. Expose a clean API for the orchestrator to wire into services/TUI.

## Implementation Steps
1. Add the `[audio]` optional extra to `pyproject.toml` (numpy, soundfile, audioread, mutagen).
2. Implement `metadata.py` (decode-free metadata) with graceful per-format capability handling.
3. Implement `decode.py` (samples + sample rate) with backend selection + error typing.
4. Implement `analysis.py` (`AudioFeatures`: format, duration, sr, channels, bit depth, peak, rms).
5. Add tests using synthetic tones generated in-test (write a tiny WAV; guard compressed-format
   tests behind backend availability so the suite stays hermetic).
6. Run `pytest tests/ -v`; confirm green with no regressions. Report the public API surface.

## Testing
- Analyze a synthetic WAV: correct duration, sample rate, channel count; peak/RMS within tolerance.
- Corrupt/zero-length file raises the defined exception (no crash).
- Compressed-format paths tested when the backend is available; skipped cleanly otherwise.
- `pytest tests/ -v` stays green.

## Resolved Decisions
- Audio deps are an optional `[audio]` extra, lazily imported — never core requirements.
- Analysis is read-only; the audio agent produces waveform *data*, the TUI renders it.
