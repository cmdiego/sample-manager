"""Responsive terminal waveform renderer."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.widget import Widget

from ...audio.waveform import WaveformBin, WaveformData

# ---------------------------------------------------------------------------
# Braille dot bit-masks per (col, row) within a 2-column × 4-row cell.
# col 0 = left, col 1 = right; row 0 = top, row 3 = bottom.
# Unicode standard dot numbering:  1 4 / 2 5 / 3 6 / 7 8
# ---------------------------------------------------------------------------
_BRAILLE_DOT: tuple[tuple[int, int, int, int], ...] = (
    # (col=0,row=0) (col=0,row=1) (col=0,row=2) (col=0,row=3)
    (0x01, 0x02, 0x04, 0x40),
    # (col=1,row=0) (col=1,row=1) (col=1,row=2) (col=1,row=3)
    (0x08, 0x10, 0x20, 0x80),
)
_BRAILLE_BASE = 0x2800


def _fit_bins(bins: tuple[WaveformBin, ...], width: int) -> tuple[WaveformBin, ...]:
    if width <= 0 or not bins:
        return ()
    if len(bins) <= width:
        return tuple(bins[min(len(bins) - 1, index * len(bins) // width)] for index in range(width))

    fitted = []
    for index in range(width):
        start = index * len(bins) // width
        end = max(start + 1, (index + 1) * len(bins) // width)
        section = bins[start:end]
        fitted.append(
            WaveformBin(
                minimum=min(item.minimum for item in section),
                maximum=max(item.maximum for item in section),
            )
        )
    return tuple(fitted)


def render_waveform(
    bins: tuple[WaveformBin, ...],
    width: int,
    height: int = 3,
    progress: float = 0.0,
) -> Text:
    """Render a signed envelope with a center line and playback cursor (block-char fallback)."""
    if width <= 0 or height <= 0:
        return Text()
    fitted = _fit_bins(bins, width)
    if not fitted:
        return Text("\n".join(" " * width for _ in range(height)))

    progress = max(0.0, min(1.0, progress))
    cursor = min(width - 1, int(progress * width)) if progress > 0.0 else -1
    center = (height - 1) / 2.0
    output = Text()
    for row in range(height):
        for column, item in enumerate(fitted):
            if column == cursor:
                output.append("│", style="bold yellow")
                continue
            top = round((1.0 - item.maximum) * (height - 1) / 2.0)
            bottom = round((1.0 - item.minimum) * (height - 1) / 2.0)
            if item.maximum != 0.0 or item.minimum != 0.0:
                if top <= row <= bottom:
                    style = "bright_green" if column < cursor else "green"
                    output.append("█", style=style)
                    continue
            if row == round(center):
                output.append("─", style="dim green")
            else:
                output.append(" ")
        if row < height - 1:
            output.append("\n")
    return output


def render_braille_waveform(
    bins: tuple[WaveformBin, ...],
    width: int,
    height: int = 4,
    progress: float = 0.0,
    nav_cursor: float | None = None,
) -> Text:
    """Render a signed envelope using Unicode Braille characters.

    Each terminal cell encodes a 2-column × 4-row sub-pixel grid (8 dots),
    giving approximately 4× higher vertical resolution than block characters
    at the same terminal width.

    Args:
        bins: Waveform envelope bins (downsampled to display resolution).
        width: Available terminal columns.  Output width = width // 2 chars.
        height: Terminal rows; each row adds 4 sub-pixel rows of resolution.
        progress: Playback cursor position [0.0, 1.0]; 0.0 = no cursor shown.
        nav_cursor: Waveform-nav seek cursor position [0.0, 1.0] or None.
    """
    if width <= 0 or height <= 0:
        return Text()

    # Each Braille char covers 2 source columns, so we need width // 2 chars.
    braille_cols = max(1, width // 2)
    # Each char covers 4 sub-pixel rows, so we need height * 4 source rows.
    sub_rows = height * 4

    # Downsample bins to (braille_cols * 2) source columns for symmetric pairing.
    source_cols = braille_cols * 2
    fitted = _fit_bins(bins, source_cols)
    if not fitted:
        blank_line = " " * braille_cols
        return Text("\n".join(blank_line for _ in range(height)))

    progress = max(0.0, min(1.0, progress))
    # Playback cursor: column index in Braille-char space (0..braille_cols-1).
    play_col = min(braille_cols - 1, int(progress * braille_cols)) if progress > 0.0 else -1
    # Nav cursor: column index in Braille-char space.
    nav_col = int(nav_cursor * braille_cols) if nav_cursor is not None else -1
    nav_col = max(0, min(braille_cols - 1, nav_col)) if nav_cursor is not None else -1

    # Build a braille_cols × height grid of Braille bitmasks.
    # grid[bc][row] = bitmask for the Braille character at column bc, terminal row row.
    grid: list[list[int]] = [[0] * height for _ in range(braille_cols)]

    center_sub = (sub_rows - 1) / 2.0

    for bc in range(braille_cols):
        left_src = bc * 2
        right_src = bc * 2 + 1

        for c_idx, src_idx in enumerate((left_src, right_src)):
            if src_idx >= len(fitted):
                continue
            b = fitted[src_idx]
            if b.maximum == 0.0 and b.minimum == 0.0:
                # Silence — mark zero-line sub-row only.
                zero_sub = int(round(center_sub))
                term_row = zero_sub // 4
                sub_row = zero_sub % 4
                if term_row < height:
                    grid[bc][term_row] |= _BRAILLE_DOT[c_idx][sub_row]
                continue
            # Convert amplitude to sub-pixel rows (top = highest amplitude).
            top_sub = int(round((1.0 - b.maximum) / 2.0 * (sub_rows - 1)))
            bot_sub = int(round((1.0 - b.minimum) / 2.0 * (sub_rows - 1)))
            top_sub = max(0, min(sub_rows - 1, top_sub))
            bot_sub = max(0, min(sub_rows - 1, bot_sub))
            for sub in range(top_sub, bot_sub + 1):
                term_row = sub // 4
                sub_row = sub % 4
                if term_row < height:
                    grid[bc][term_row] |= _BRAILLE_DOT[c_idx][sub_row]

    # Render to rich.Text.
    output = Text()
    for row in range(height):
        for bc in range(braille_cols):
            # Special column: nav cursor takes priority over playback cursor.
            if bc == nav_col:
                output.append("▌", style="bold cyan")
                continue
            if bc == play_col:
                output.append("│", style="bold yellow")
                continue
            mask = grid[bc][row]
            ch = chr(_BRAILLE_BASE | mask)
            # Colour: played region brighter.
            if mask == 0:
                output.append("⠀", style="dim")  # blank Braille (U+2800)
            elif bc < play_col:
                output.append(ch, style="bright_green")
            else:
                output.append(ch, style="green")
        if row < height - 1:
            output.append("\n")
    return output


class WaveformWidget(Widget):
    """Presentation-only widget for waveform data and loading state."""

    def __init__(self, path: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.path = path
        self._data: WaveformData | None = None
        self._message = "loading waveform..." if path else ""
        self._progress = 0.0
        self._nav_cursor: float | None = None

    def set_loading(self, path: Path) -> None:
        self.path = path
        self._data = None
        self._message = "loading waveform..."
        self._progress = 0.0
        self._nav_cursor = None
        self.refresh()

    def set_data(self, data: WaveformData) -> None:
        self.path = data.path
        self._data = data
        self._message = ""
        self._progress = 0.0
        self._nav_cursor = None
        self.refresh()

    def set_error(self, path: Path, message: str) -> None:
        self.path = path
        self._data = None
        self._message = f"waveform unavailable: {message}"
        self._nav_cursor = None
        self.refresh()

    def set_progress(self, progress: float) -> None:
        normalized = max(0.0, min(1.0, progress))
        if normalized != self._progress:
            self._progress = normalized
            self.refresh()

    def set_nav_cursor(self, fraction: float | None) -> None:
        """Show a seek cursor at *fraction* (0..1) or hide it when None."""
        if fraction is None:
            new = None
        else:
            new = max(0.0, min(1.0, float(fraction)))
        if new != self._nav_cursor:
            self._nav_cursor = new
            self.refresh()

    def nav_cursor_fraction(self) -> float | None:
        """Return the current nav-mode cursor position, or None if inactive."""
        return self._nav_cursor

    def render(self) -> Text:
        width = max(0, self.size.width)
        height = max(1, self.size.height)
        if self._data is not None:
            return render_braille_waveform(
                self._data.bins, width, height, self._progress, self._nav_cursor
            )
        return Text(self._message, style="dim", justify="center", overflow="ellipsis")
