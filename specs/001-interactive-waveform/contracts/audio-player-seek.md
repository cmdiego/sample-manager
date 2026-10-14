# Contract: AudioPlayer.seek()

**Module**: `src/sample_manager/audio/player.py`
**Class**: `AudioPlayer`

## New Method

```python
def seek(self, position_seconds: float) -> None:
    """Seek the current file to *position_seconds*.

    No-op when no file is loaded or the player is closed/errored.
    If playing: stops the output and restarts from the target frame.
    If paused: updates _position_frames; playback resumes from the new position.
    If idle/loading: updates _position_frames for the next play call.
    """
```

### Preconditions
- `0 ≤ position_seconds ≤ duration_seconds` (clamped internally; callers need not clamp)
- A path must be set (`_path is not None`) and audio must be loaded (`_audio is not None`)
  for seek to have any effect; otherwise the call is silently ignored

### Postconditions
- `snapshot().position_seconds ≈ position_seconds` (within one audio buffer's length)
- Playback continues from the seeked position if the player was previously PLAYING
- If the player was PAUSED, it remains paused at the new position
- No race conditions: the generation counter is incremented before any output operation

### Thread safety
- Method acquires `_lock` before reading/writing any shared state
- Same generation-counter discipline as `play()` and `pause()`

---

## Updated Signature Summary

```python
class AudioPlayer:
    # --- existing ---
    def play(self, path: Path) -> None: ...
    def play_from_start(self, path: Path) -> None: ...
    def pause(self) -> None: ...
    def snapshot(self) -> PlaybackSnapshot: ...
    def close(self) -> None: ...

    # --- new ---
    def seek(self, position_seconds: float) -> None: ...
```

---

# Contract: TUI WaveformWidget Navigation API

**Module**: `src/sample_manager/tui/widgets/waveform.py`
**Class**: `WaveformWidget`

## New Methods

```python
def set_nav_cursor(self, fraction: float | None) -> None:
    """Show a navigation seek cursor at *fraction* (0..1) or hide it when None.

    When set, the nav cursor is rendered distinctly from the playback cursor.
    Cleared automatically when set_loading(), set_data(), or set_error() is called.
    """

def nav_cursor_fraction(self) -> float | None:
    """Return the current navigation cursor position, or None if not in nav mode."""
```

## New Function

```python
def render_braille_waveform(
    bins: tuple[WaveformBin, ...],
    width: int,
    height: int = 4,
    progress: float = 0.0,
    nav_cursor: float | None = None,
) -> Text:
    """Render a signed waveform envelope using Unicode Braille characters.

    Each terminal cell encodes a 2-column × 4-row sub-pixel grid (8 dots).
    Output is a rich.Text object suitable for Textual widget rendering.

    Args:
        bins: Waveform envelope bins (any count; downsampled to display width).
        width: Available terminal columns.
        height: Terminal rows. Each row adds 4 sub-pixel rows of resolution.
        progress: Playback cursor position [0.0, 1.0]; 0.0 = no cursor shown.
        nav_cursor: Nav-mode seek cursor position [0.0, 1.0] or None.
    """
```

### Compatibility
- `render_braille_waveform` and the existing `render_waveform` have the same call signature
  (plus `nav_cursor`). Both return `rich.Text`. Callers can switch between them freely.

---

# Contract: Qt GUI WaveformWidget Seek Signal

**Module**: `src/sample_manager/gui/widgets/waveform.py`
**Class**: `WaveformWidget`

## New Signal

```python
from PySide6.QtCore import Signal

class WaveformWidget(QWidget):
    # --- new ---
    seek_requested: Signal  # Signal(float) — emits normalized file position [0.0, 1.0]
```

### Semantics
- Emitted on `mouseReleaseEvent` when the release position is within
  `CLICK_THRESHOLD_PX = 4` pixels of the press position (distinguishes click from drag).
- The emitted float is the **file-normalized** seek position:
  `zoom_start + (click_x / widget_width) * (zoom_end - zoom_start)`
- Clipped to [0.0, 1.0].
- Callers convert to seconds: `position_seconds = fraction * duration_seconds`
- Not emitted when the widget is in LOADING, ERROR, or EMPTY state.

### Wiring (downstream)

`PreviewWidget` (or `BrowserController`) connects the signal:
```python
waveform_widget.seek_requested.connect(
    lambda fraction: audio_player.seek(fraction * (snapshot.duration_seconds or 0.0))
)
```

---

# Contract: AppMode.WAVEFORM_NAV

**Module**: `src/sample_manager/tui/modes.py`
**Enum**: `AppMode`

```python
class AppMode(Enum):
    BROWSE = "browse"
    SEARCH = "search"
    WAVEFORM_NAV = "waveform_nav"   # new
```

### Transition rules
- `BROWSE → WAVEFORM_NAV`: user presses `w` while a file with a loaded waveform is focused
- `WAVEFORM_NAV → BROWSE`: user presses `Escape` (no seek) or `Enter` (seek + return)
- `SEARCH → WAVEFORM_NAV`: NOT allowed (waveform nav is only valid from BROWSE)
- `WAVEFORM_NAV → SEARCH`: NOT allowed

### Key capture in WAVEFORM_NAV mode

| Key | Action |
|-----|--------|
| `left` / `h` | Move nav cursor left (fine: 1 / display_width) |
| `right` / `l` | Move nav cursor right (fine) |
| `shift+left` | Move nav cursor left (coarse: 10 × fine) |
| `shift+right` | Move nav cursor right (coarse) |
| `home` | Nav cursor to 0.0 |
| `end` | Nav cursor to 1.0 |
| `enter` | Seek to cursor position; return to BROWSE |
| `escape` | Return to BROWSE without seeking |
| all others | Passthrough to global handler (e.g., `space` still toggles playback) |
