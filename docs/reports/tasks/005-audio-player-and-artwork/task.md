# Task 005 — Audio: Media Player, Cover-Art Extraction & Waveform Data

- **Status**: 🔍 Planned (next development step)
- **Origin**: User request (next-steps setup, 2026-07-07)
- **Assigned agent**: audio-engineer (charter: `.claude/agents/audio-engineer.md`)
- **Created**: 2026-07-07
- **Plan**: 005-audio-player-and-artwork.md

## Problem / Objective
Extend the audio domain beyond first-steps analysis with: (1) a media player / playback engine
(sound routing), (2) extraction of embedded cover art from the audio file (return the raw image
bytes, or None when absent — the TUI supplies the default stock image), and (3) a downsampled
waveform **peak array** as a data structure the TUI can render.

## Scope Boundary (enforced by orchestrator)
- **Audio agent owns**: playback engine + sound routing, decode-free cover-art byte extraction,
  and computing the waveform peak/summary array (pure data).
- **TUI agent owns** (Task 006): rendering the waveform and displaying the cover art (incl. the
  default stock image fallback). Audio produces bytes/arrays; it does not render.

## Files Involved (expected)
- `src/sample_manager/audio/engine.py` (new) — playback / sound routing
- `src/sample_manager/audio/artwork.py` (new) — embedded cover-art extraction (mutagen)
- `src/sample_manager/audio/analysis.py` — add `waveform_peaks(...)` data API
- `pyproject.toml` — any additional optional `[audio]` playback dep
- `tests/` — engine (mockable), artwork, and waveform-peaks tests

## Resolution
<pending — audio-engineer>

## Validation
- `pytest tests/ -v`: <pending>

## Links
- Plan: `005-audio-player-and-artwork.md`
- Prompt: `prompt.md`
- Depended on by: Task 006 (TUI waveform + artwork display)
