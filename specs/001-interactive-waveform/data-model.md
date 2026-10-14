# Data Model: Interactive Waveform Rendering & Navigation

**Date**: 2026-09-30
**Feature**: [spec.md](spec.md)

## Overview

This feature adds no new database tables or persisted entities. All state is in-memory and
transient. The existing data structures are used unchanged; two lightweight additions are made.

---

## Existing Entities (unchanged)

### WaveformBin
```
WaveformBin(frozen dataclass)
  minimum: float   # signed minimum amplitude in bin range [-1.0, 1.0]
  maximum: float   # signed maximum amplitude in bin range [-1.0, 1.0]
```
Represents one display column of a waveform envelope.
Cache key: derived from file path + st_size + st_mtime_ns.

### WaveformData
```
WaveformData(frozen dataclass)
  path: Path
  duration_seconds: float
  bins: tuple[WaveformBin, ...]   # 4096 bins by default (WaveformService default)
```
Immutable full-file envelope. Shared across frontends; re-binned at display width on each paint.

### PlaybackSnapshot
```
PlaybackSnapshot(frozen dataclass)
  status: PlaybackStatus          # IDLE | LOADING | PLAYING | PAUSED | ERROR
  path: Path | None
  position_seconds: float
  duration_seconds: float | None
  error: str | None
```
Non-blocking read of playback state. Polled by TUI every 200 ms; received via Qt signal in GUI.

---

## New / Modified Entities

### WaveformNavigationState (TUI widget internal, not a dataclass)

Owned by `WaveformWidget` (Textual). Holds the state for keyboard navigation mode.

```
cursor_fraction: float | None
  # None  → nav mode inactive; normal playback cursor visible
  # 0.0–1.0 → nav mode active; seek cursor shown at this normalized position
```

Validation rules:
- When set: clamped to [0.0, 1.0].
- Cleared (→ None) on `set_data()`, `set_loading()`, `set_error()`, and when nav mode exits.

### BrailleFrame (conceptual, produced by renderer function)

Not a persistent dataclass — a `rich.Text` object returned by `render_braille_waveform()`.
The function signature mirrors the existing `render_waveform()`:

```
render_braille_waveform(
  bins: tuple[WaveformBin, ...],
  width: int,          # terminal columns available
  height: int = 4,     # terminal rows; each row = 4 Braille sub-rows → 4×4 = 16 sub-pixels tall
  progress: float = 0.0,
  nav_cursor: float | None = None,
) -> rich.Text
```

Parameters:
- `progress`: normalized playback position [0.0, 1.0], drives playback cursor column
- `nav_cursor`: normalized nav-mode cursor position [0.0, 1.0] or None

Output: a `rich.Text` object with Braille characters and Rich markup styling.

---

## State Transitions

### TUI Waveform Navigation Mode

```
                   user presses 'w' (in BROWSE mode)
                           │
              ┌────────────▼───────────┐
              │  WAVEFORM_NAV mode     │
              │  cursor_fraction = 0.0 │   ← initialized to current playback position
              └────────────┬───────────┘
                           │
          left/right/shift+left/shift+right/home/end
                           │
              ┌────────────▼───────────┐
              │  cursor_fraction moves │
              └────────────┬───────────┘
                           │
              ┌────────────┴───────────┐
              │ Enter                  │ Escape
              ▼                        ▼
     seek(cursor_fraction           cursor_fraction = None
       × duration_seconds)          return to BROWSE mode
     → update playhead
     → return to BROWSE mode
```

### GUI Seek via Click

```
  mousePressEvent (left button, READY state)
       → record _pan_anchor_x, _pan_anchor_start, _pan_anchor_end

  mouseReleaseEvent
       → if abs(release_x - press_x) < CLICK_THRESHOLD_PX (4px):
           fraction = zoom_start + (release_x / width) * (zoom_end - zoom_start)
           emit seek_requested(fraction)
       → else:
           pan completed (no seek)
       → clear _pan_anchor_x
```

---

## AudioPlayer.seek() State Table

| Current status | Action | Result |
|----------------|--------|--------|
| IDLE | seek(t) | Update `_position_frames`; no output action |
| LOADING | seek(t) | Update `_position_frames`; play command will start from new pos |
| PLAYING | seek(t) | Increment generation; pause output; update `_position_frames`; re-queue play |
| PAUSED | seek(t) | Update `_position_frames` (play will resume from here) |
| ERROR | seek(t) | No-op |
| audio not loaded | seek(t) | No-op (no sample_rate to compute target_frame) |
