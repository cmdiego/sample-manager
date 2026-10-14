# Quickstart Validation Guide: Interactive Waveform Rendering & Navigation

**Date**: 2026-09-30
**Feature**: [spec.md](spec.md)

## Prerequisites

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

A sample library root should be configured in `~/.sample_manager/config.yaml`. The `sampleman init`
command creates a default configuration if one does not already exist.

---

## Scenario 1: High-Fidelity Terminal Waveform (P1)

**What to validate**: Braille rendering is visibly higher-resolution than block chars.

```bash
sampleman tui
```

1. Navigate to any `.wav`, `.flac`, or `.mp3` file in the browser.
2. Observe the **Preview** panel. The waveform should display in Braille Unicode characters
   (characters from the range U+2800–U+28FF), not block characters (█).
3. The waveform should accurately reflect the shape of the audio (loud sections wider, silence
   as a flat center line).
4. Resize the terminal — the waveform should redraw and fill the new width.

**Expected outcome**: Waveform rendered in fine-grained Braille dots, visibly more detailed than
the previous block-character rendering at 80 or 120 terminal columns.

---

## Scenario 2: Smooth Playback Position Indicator (P2)

**What to validate**: Playhead tracks audio and updates without blocking rendering.

```bash
sampleman tui
```

1. Focus an audio file.
2. Press `Space` to start playback.
3. The playback cursor (a vertical line) should move smoothly across the waveform.
4. Press `Space` again to pause — the cursor should stop at the current position immediately.
5. Press `Space` to resume — playback and cursor resume from where they paused.
6. Navigate to a different file while the previous one is playing — the new file's waveform
   should load without audio interrupting.

**Expected outcome**: Smooth, lag-free playhead that accurately tracks audio position.

---

## Scenario 3: Keyboard Waveform Navigation (P3)

**What to validate**: Waveform nav mode activates, cursor moves, seek works.

```bash
sampleman tui
```

1. Focus an audio file. Wait for the waveform to load.
2. Press `w` to enter waveform navigation mode. A distinct seek cursor (different color from the
   playback cursor) should appear at the left of the waveform.
3. Press `Right` or `l` — the seek cursor moves right by one fine step.
4. Press `Shift+Right` — the cursor moves a larger step.
5. Press `End` — cursor jumps to the rightmost position.
6. Press `Home` — cursor jumps to the leftmost position.
7. Move the cursor to a visible midpoint, then press `Enter` — audio playback should jump to
   that position and the mode should return to normal browsing.
8. Enter nav mode again (`w`), move the cursor, then press `Escape` — no seek occurs and the
   mode returns to normal browsing.
9. Verify that `j`/`k` (up/down navigation) still work while in waveform nav mode.

**Expected outcome**: Waveform nav mode activates and dismisses cleanly; seek moves audio
playback to the correct position.

---

## Scenario 4: Mouse Click-to-Seek in the GUI (P4)

**What to validate**: Clicking the waveform seeks audio.

```bash
sampleman gui
```

1. Focus an audio file and start playback (`Space` or the play button).
2. Click on a point in the waveform display — about 75% from the left.
3. Playback should immediately jump to approximately 75% of the file's duration.
4. The playhead should move to the clicked position.
5. Click-and-drag horizontally — the waveform should pan (existing behavior should still work).
6. Use the mouse wheel to zoom in on a region. Click on a point — the seek should map correctly
   to the zoomed-in view's position, not the raw pixel position in the full file.

**Expected outcome**: Single click seeks audio; drag still pans; zoom window is respected.

---

## Test Suite Validation

```bash
# Audio player seek unit tests
pytest tests/test_audio_player.py -v -k seek

# TUI Braille renderer + nav mode
pytest tests/test_tui_waveform.py -v

# Full TUI audio integration
pytest tests/test_audio_tui_integration.py -v

# GUI waveform widget (click-to-seek)
QT_QPA_PLATFORM=offscreen pytest tests/gui/test_waveform_widget.py -v

# Full test suite (confirm no regressions)
pytest tests/ -v
QT_QPA_PLATFORM=offscreen pytest tests/gui/ -v
```

**Expected outcome**: All tests pass. No regressions in existing waveform, player, or TUI tests.

---

## Key Contracts (reference)

- [audio-player-seek.md](contracts/audio-player-seek.md) — `AudioPlayer.seek()`, TUI nav API,
  Qt seek signal, `AppMode.WAVEFORM_NAV`
- [data-model.md](data-model.md) — state transitions and entity definitions
