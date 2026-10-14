# Task 004 — Audio Analysis: First Steps

- **Status**: ✅ Done
- **Origin**: User request (new Audio domain + analysis feature)
- **Assigned agent**: audio-engineer (charter: `.claude/agents/audio-engineer.md`).
  Executed this session via a general-purpose agent briefed as the audio-engineer, since the
  new agent type is registered for future sessions.
- **Created**: 2026-07-07
- **Plan**: 004-audio-analysis-first-steps.md

## Problem / Objective
Stand up the audio analysis domain and implement the first steps of analyzing audio files across
popular formats: **WAV, FLAC, MP3, AAC, M4A/MP4, OGG** and similar. Extract basic metadata and
features (format, duration, sample rate, channels, bit depth, peak/RMS level).

## Scope Boundary (enforced by orchestrator)
- **Audio agent owns**: decode, metadata, analysis/DSP, and (future) playback + sound routing.
- **TUI agent owns**: any *visual* display, including the future waveform widget. The audio agent
  only produces the numeric waveform peak/summary array; it does not render.

## Files Involved (expected)
- new `src/sample_manager/audio/` package (`decode.py`, `analysis.py`, `metadata.py`)
- `pyproject.toml` — new optional `[audio]` extra (numpy, soundfile, audioread, mutagen, …)
- `tests/` — analysis tests using synthetic/fixture audio

## Resolution
New read-only `src/sample_manager/audio/` package:
- `backends.py` — lazy import + `capabilities()`; `AudioError` → `BackendUnavailable`.
- `decode.py` — format-agnostic decode to float32 `[frames, channels]` + sample rate; backend by
  extension with a stdlib `wave` fallback; `AudioDecodeError` on missing/empty/corrupt/unsupported.
- `metadata.py` — decode-free container/tag read via mutagen; `AudioMetadataError`.
- `analysis.py` — pure DSP (`to_mono`, `compute_peak`, `compute_rms`) + typed `AudioFeatures`
  (format, duration, sample_rate, channels, bit_depth, peak, rms; `.peak_dbfs`/`.rms_dbfs`).
- `__init__.py` — public API re-export. `pyproject.toml` — optional `[audio]` extra
  (numpy, soundfile, audioread, mutagen), lazily imported; missing backend → clear pip hint.
- `tests/conftest.py` — added stdlib-only `write_sine_wav` fixture (hermetic).

Domain boundary honored: read-only, no Textual imports, no SQL/repo access. Waveform *rendering*
intentionally left to the tui-architect (this domain only produces data arrays).

**System dependency:** ffmpeg (not bundled) is needed for MP3/AAC/MP4 via audioread; not installed
on this box, so compressed-format tests skip cleanly behind backend-availability guards.

## Validation
- Audio suite: **32 passed**.
- Full suite: **575 passed, 4 failed**. The 4 failures are in `tests/test_tui_pilot.py` and are
  **pre-existing** (verified by the agent via `git stash` — fail identically without these changes);
  they belong to the in-flight TUI work (tasks 002/003), not audio. Audio work reduced zero tests.

## Regression Test
- Covered by the agent's 32 tests: `tests/test_audio_pure.py`, `test_audio_decode.py`,
  `test_audio_metadata.py`, `test_audio_analysis.py` (compressed formats guarded/skipped).

## Links
- Plan: `004-audio-analysis-first-steps.md`
- Prompt: `prompt.md`
- Agent charter: `.claude/agents/audio-engineer.md`
