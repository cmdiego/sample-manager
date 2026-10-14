# Implementation Plan: Interactive Waveform Rendering & Navigation

**Branch**: `001-interactive-waveform` | **Date**: 2026-09-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-interactive-waveform/spec.md`

## Summary

Upgrade the terminal waveform from block characters to Unicode Braille for ~4× higher vertical
resolution; add a `seek()` method to `AudioPlayer`; wire a keyboard navigation mode into the TUI
(`w` → waveform nav, arrows + Home/End + Enter to seek, Escape to exit); and add click-to-seek
to the Qt GUI waveform widget. No new runtime dependencies are needed — Braille rendering is pure
Python plus the already-installed `numpy`.

## Technical Context

**Language/Version**: Python 3.10+

**Primary Dependencies**: Textual ≥0.50 (TUI), PySide6 ≥6.6 (GUI), NumPy ≥1.24 (waveform
bins), sounddevice ≥0.5 (audio output). All already installed; no new runtime deps required.

**Storage**: N/A (waveform data held in-memory LRU cache; no DB changes)

**Testing**: pytest, pytest-qt (offscreen via `QT_QPA_PLATFORM=offscreen`)

**Target Platform**: macOS, Linux, Windows (fallback)

**Project Type**: Desktop application + CLI (PySide6 Qt GUI primary, Textual TUI fallback)

**Performance Goals**: Braille render ≤ 1 ms for a 200-column display; playhead poll interval
≤ 200 ms (matches existing `_poll_audio` timer); seek latency < 50 ms perceived.

**Constraints**: No new runtime dependencies. Seek must use the existing generation-counter
mechanism in `AudioPlayer` to avoid race conditions. TUI navigation keys must not conflict with
any key in `tui/keybindings.py`.

**Scale/Scope**: Single-file waveform, 1 active player, LRU cache of 64 files (unchanged).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Non-Destructive First | PASS | No file mutations; seek only changes playback position |
| II. Strict Layer Separation | PASS | `AudioPlayer.seek()` in audio layer; TUI/GUI widgets consume it via service layer |
| III. Test-First Development | PASS | Tests written alongside each change; real `AudioPlayer` used (no mocks) |
| IV. Schema Changes via Migrations | PASS | No DB schema changes required |
| V. Simplicity & YAGNI | PASS | No new dependency; Braille renderer is a focused addition; no speculative features |

All gates pass. No complexity-tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/001-interactive-waveform/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── audio-player-seek.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/sample_manager/
├── audio/
│   └── player.py                  # add seek(position_seconds: float) -> None
├── tui/
│   ├── modes.py                   # add WAVEFORM_NAV to AppMode
│   ├── keybindings.py             # extend ACTION_DESCRIPTIONS + ACTION_CATEGORIES
│   └── widgets/
│       ├── waveform.py            # Braille renderer + nav cursor + nav mode state
│       └── top_display.py        # expose seek_to(fraction) callback
├── gui/
│   └── widgets/
│       └── waveform.py           # add seek_requested Signal + click-to-seek logic

tests/
├── test_audio_player.py           # extend with seek() unit tests
├── test_tui_waveform.py           # Braille renderer + nav mode (new file)
└── gui/
    └── test_waveform_widget.py    # extend with click-to-seek tests
```

**Structure Decision**: Single-project layout (existing). All changes are additions to existing
modules; no new modules are needed except an optional Braille renderer function alongside
`render_waveform()` in `tui/widgets/waveform.py`.
