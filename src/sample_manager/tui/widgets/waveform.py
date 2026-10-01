"""Responsive terminal waveform renderer."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.widget import Widget

from ...audio.waveform import WaveformBin, WaveformData


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
    """Render a signed envelope with a center line and playback cursor."""
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


class WaveformWidget(Widget):
    """Presentation-only widget for waveform data and loading state."""

    def __init__(self, path: Path | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.path = path
        self._data: WaveformData | None = None
        self._message = "loading waveform..." if path else ""
        self._progress = 0.0

    def set_loading(self, path: Path) -> None:
        self.path = path
        self._data = None
        self._message = "loading waveform..."
        self._progress = 0.0
        self.refresh()

    def set_data(self, data: WaveformData) -> None:
        self.path = data.path
        self._data = data
        self._message = ""
        self._progress = 0.0
        self.refresh()

    def set_error(self, path: Path, message: str) -> None:
        self.path = path
        self._data = None
        self._message = f"waveform unavailable: {message}"
        self.refresh()

    def set_progress(self, progress: float) -> None:
        normalized = max(0.0, min(1.0, progress))
        if normalized != self._progress:
            self._progress = normalized
            self.refresh()

    def render(self) -> Text:
        width = max(0, self.size.width)
        height = max(1, self.size.height)
        if self._data is not None:
            return render_waveform(self._data.bins, width, height, self._progress)
        return Text(self._message, style="dim", justify="center", overflow="ellipsis")
