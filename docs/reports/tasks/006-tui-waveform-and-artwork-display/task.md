# Task 006 — TUI: Waveform & Cover-Art Display

- **Status**: 🔍 Planned (next development step)
- **Origin**: User request (next-steps setup, 2026-07-07)
- **Assigned agent**: tui-architect
- **Created**: 2026-07-07
- **Plan**: 006-tui-waveform-and-artwork-display.md

## Problem / Objective
Display the selected/focused audio file's **waveform** in the TUI, and show its **cover art** —
using the image embedded in the file, or a default stock image when none is present.

## Scope Boundary (enforced by orchestrator)
- **TUI agent owns**: rendering the waveform (from the audio peak array) and the cover-art widget,
  including the default stock-image fallback.
- **Audio agent owns** (Task 005): the waveform peak-array data API and cover-art byte extraction.
  The TUI must consume those APIs, not decode/analyze audio itself.

## Dependencies
- **Blocked by**: Task 005 (needs `analysis.waveform_peaks(...)` and `artwork` extraction APIs).

## Files Involved (expected)
- new `src/sample_manager/tui/widgets/waveform.py` — waveform render widget
- new `src/sample_manager/tui/widgets/artwork.py` — cover-art widget (+ default stock image asset)
- `src/sample_manager/tui/data.py` — thin pass-through to the audio APIs (keep DB/audio access here)
- `src/sample_manager/tui/app.py` — wire display to focus changes
- `src/sample_manager/tui/styles/app.tcss` — styling; `tests/` — Pilot tests

## Resolution
<pending — tui-architect, after Task 005>

## Validation
- `pytest tests/ -v`: <pending>

## Links
- Plan: `006-tui-waveform-and-artwork-display.md`
- Prompt: `prompt.md`
- Depends on: Task 005 (audio player + artwork + waveform data)
