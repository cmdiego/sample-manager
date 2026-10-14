# Research: Interactive Waveform Rendering & Navigation

**Date**: 2026-09-30
**Feature**: [spec.md](spec.md)

## Decision 1: TUI Waveform Renderer — Braille vs. textual-plotext

**Decision**: Implement a custom Braille Unicode renderer. Do NOT add textual-plotext.

**Rationale**:

1. **No new dependency**. `textual-plotext` is not in `pyproject.toml` and adding it conflicts
   with the project's Simplicity principle (V). The Braille encoding technique uses only Python
   string operations on Unicode code points U+2800–U+28FF — no library required.

2. **Full control over rendering**. A custom renderer can produce a `rich.Text` object with the
   same interface as the existing `render_waveform()`, making it a drop-in replacement. An
   external library's API would constrain the output format.

3. **Braille resolution math**. Each Braille character occupies one terminal cell and encodes a
   2-column × 4-row pixel grid (8 dots). For a waveform display W columns wide, we produce W/2
   Braille characters per display row. Compared to the current block-char renderer (1 pixel per
   column per row), this gives 2× horizontal density and 4× vertical density — approximately
   8× more sub-pixel information at the same terminal width.

4. **textual-plotext limitations** (from evaluation). `textual-plotext` targets generic 2D plot
   charts (scatter, bar, line), not min/max waveform envelopes. Adapting it for a signed
   envelope display would require more code than a direct implementation. Its refresh behavior
   is tied to Plotext's internal state which is harder to control than a function returning
   `rich.Text`.

**Alternatives considered**:
- `drawille` library: pure-Python Braille canvas, but another new dependency; no rich.Text output
- `textual-plotext`: see above; mismatch between its API and the waveform use case
- Keep block chars: rejected — FR-001 explicitly requires higher resolution

**How Braille encoding works** (for implementation reference):

Unicode Braille block dot positions in a 2×4 cell (left col | right col):
```
row 0:  dot1 (0x01) | dot4 (0x08)
row 1:  dot2 (0x02) | dot5 (0x10)
row 2:  dot3 (0x04) | dot6 (0x20)
row 3:  dot7 (0x40) | dot8 (0x80)
```

A Braille character is `chr(0x2800 | bitmask)` where `bitmask` encodes which dots are set.

For a waveform, the renderer pairs adjacent source columns, maps each into a 2×4 sub-pixel
grid using the min/max bins, and OR-combines the dot bits.

---

## Decision 2: AudioPlayer Seek API

**Decision**: Add `seek(position_seconds: float) -> None` as a public method on `AudioPlayer`.

**Rationale**:

The `AudioPlayer._request_play` method already supports playing from an arbitrary `start_frame`
via `_position_frames`. Adding `seek()` reuses this mechanism:

1. Acquire the lock; verify the player is not closed, the current path is set, and the audio
   is loaded (`_audio is not None`).
2. Compute `target_frame = max(0, min(int(position_seconds * audio.sample_rate), frames - 1))`.
3. If PLAYING: increment generation, set `_position_frames = target_frame`, pause the output,
   and re-queue a play command. The existing `_execute_play` path starts output from
   `_position_frames`.
4. If PAUSED: just update `_position_frames` (audio will start from there when resumed).
5. If IDLE/LOADING/ERROR: update `_position_frames` only; no output action.

This approach reuses the generation counter (stale commands are dropped), the existing command
queue, and the `_execute_play` / `_output.start()` path. No new threading primitives needed.

**Alternatives considered**:
- A `seek_to_frame(frame: int)` low-level method: rejected — callers think in seconds
- Delegating seek via a new `SeekCommand` object: rejected — the existing `(generation, path)`
  tuple is sufficient; start_frame is already in `_position_frames`

---

## Decision 3: TUI Waveform Navigation Mode

**Decision**: Add `WAVEFORM_NAV` to `AppMode` enum. Activation key: `w`.

**Rationale**:

Keybinding conflict check against `tui/keybindings.py`:
```
h (go_back), j (move_down), k (move_up), l (enter),
left (go_back), down (move_down), up (move_up), right (enter),
enter (select_or_descend), a (add_to_selection), d (remove_from_selection),
space (toggle_playback), ctrl+space (resume_playback),
q (quit), question_mark (show_help), slash (activate_filter),
escape (cancel_or_back), tab (cycle_pane_focus), ctrl+p (command_palette)
```

`w` is unbound. It is a natural mnemonic for "waveform". Activation from `BROWSE` mode only
(not from `SEARCH` mode, where keyboard focus is on the filter input).

Inside `WAVEFORM_NAV` mode, the TUI app captures these keys before the global handler:
- `left` / `h` → move cursor left (fine step: 1/width of waveform)
- `right` / `l` → move cursor right (fine step)
- `shift+left` → move cursor left (coarse step: 10× fine)
- `shift+right` → move cursor right (coarse step)
- `home` → cursor to 0.0
- `end` → cursor to 1.0
- `enter` → seek to cursor position + exit nav mode
- `escape` → exit nav mode without seeking

`up` and `down` are intentionally NOT captured (they still navigate the sample list).

The `WaveformWidget` receives `set_nav_cursor(fraction: float | None)` — `None` clears the nav
cursor and restores normal playback-cursor rendering.

**Alternatives considered**:
- `f` (for "find position"): less intuitive than `w`
- `ctrl+w`: risk of closing terminal in some environments
- A dedicated `[WAVEFORM]` sub-widget with its own focus: heavier; the parent widget can handle
  mode-gated key events more simply

---

## Decision 4: GUI Click-to-Seek

**Decision**: Distinguish a "click" (no drag) from a "drag" (pan) in `mousePressEvent` /
`mouseReleaseEvent`; emit a new `seek_requested` PySide6 signal on click.

**Rationale**:

The GUI waveform widget already uses mouse drag for pan. The simplest non-conflicting scheme:
- Track `_pan_anchor_x` on press (unchanged).
- On release, if `abs(release_x - press_x) < CLICK_THRESHOLD_PX` (proposed: 4 px), treat as
  a click-to-seek rather than a completed pan.
- Emit `seek_requested(fraction: float)` where `fraction` is the normalized file position:
  `zoom_start + (click_x / width) * (zoom_end - zoom_start)`.
- The pan reset (clearing `_pan_anchor_x`) happens in both cases.

The signal is wired by `PreviewWidget` or `BrowserController` to `AudioPlayer.seek()`. This
keeps the seek logic out of the paint widget (layer separation).

**Alternatives considered**:
- Shift+click: requires modifier key; less discoverable
- Separate seek cursor from pan: would need a second mouse mode toggle
- Always seek on single click, separate pan to right-click: non-standard on macOS/Linux
