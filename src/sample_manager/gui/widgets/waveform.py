"""Pixel-accurate waveform widget painted with ``QPainter``.

The widget is presentation-only: it holds a :class:`WaveformService` reference
purely to *post* decode work to a bounded thread pool, and it renders whatever
envelope comes back. It issues no SQL and never blocks the GUI thread — decoding
happens in a :class:`WaveformWorker`, which emits results back as queued signals.

High-DPI: all painting is done in *physical* pixels. The painter is scaled by
``1/devicePixelRatioF()`` and the envelope is requested at exactly
``width() * dpr`` bins so there is one vertical line per physical pixel.

Zoom/pan operate on a normalized window ``[zoom_start, zoom_end]`` over the full
file; the cached full-file envelope is re-sliced and re-binned at paint time.
"""

from __future__ import annotations

from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ...audio.player import PlaybackSnapshot
    from ...audio.waveform import WaveformData, WaveformService

# Palette (all hex, per Phase-4 spec).
_BG = QColor(0x1A, 0x1A, 0x1A)
_WAVE = QColor(0x3A, 0x7D, 0x3A)
_WAVE_PLAYED = QColor(0x4A, 0x9D, 0x4A)
_ZERO_LINE = QColor(0x66, 0x66, 0x66)
_PLAYHEAD = QColor(0x00, 0xFF, 0x00)
_LOADING = QColor(0x88, 0x88, 0x88)
_ERROR = QColor(0xD0, 0x40, 0x40)

_MIN_ZOOM_SPAN = 0.05  # never show less than 5% of the file
_CLICK_THRESHOLD_PX = 4  # max horizontal travel to distinguish click from drag


class _State(Enum):
    EMPTY = auto()
    LOADING = auto()
    READY = auto()
    ERROR = auto()


class WaveformWidget(QWidget):
    """Draws the focused file's waveform, playhead, and played region."""

    # Emits a normalized file position [0.0, 1.0] when the user clicks the waveform.
    seek_requested = Signal(float)

    def __init__(self, service: "WaveformService | None" = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("WaveformWidget")
        self.setMinimumSize(200, 80)

        self._service: "WaveformService | None" = service
        self._path: Path | None = None
        self._data: "WaveformData | None" = None
        self._state = _State.EMPTY
        self._error: str = ""
        self._generation = 0

        # Normalized zoom window over the full file.
        self._zoom_start = 0.0
        self._zoom_end = 1.0

        # Playback position as a fraction [0, 1] of the whole file, or None.
        self._position_fraction: float | None = None

        # Mouse-drag pan state.
        self._pan_anchor_x: float | None = None
        self._pan_anchor_start = 0.0
        self._pan_anchor_end = 1.0

        # Bounded pool: at most two concurrent decodes.
        from PySide6.QtCore import QThreadPool

        self._pool = QThreadPool.globalInstance()
        self._pool.setMaxThreadCount(2)

    # -- injection ------------------------------------------------------------

    def set_service(self, service: "WaveformService | None") -> None:
        self._service = service

    # -- public API -----------------------------------------------------------

    def set_path(self, path: Path | None) -> None:
        """Switch to a new file (or clear). Resets zoom and re-requests bins."""
        new_path = Path(path) if path is not None else None
        if new_path == self._path:
            return
        self._path = new_path
        self._data = None
        self._error = ""
        self._position_fraction = None
        self._zoom_start = 0.0
        self._zoom_end = 1.0
        if new_path is None:
            self._state = _State.EMPTY
            # A stale in-flight worker must not paint over the cleared state.
            self._generation += 1
        else:
            self._state = _State.LOADING
            self._request()
        self.update()

    def set_playback(self, snapshot: "PlaybackSnapshot | None") -> None:
        """Update the playhead from a playback snapshot for the current file."""
        fraction: float | None = None
        if snapshot is not None and snapshot.path is not None:
            if self._path is not None and Path(snapshot.path) == self._path:
                duration = snapshot.duration_seconds or 0.0
                if duration > 0:
                    fraction = max(0.0, min(1.0, snapshot.position_seconds / duration))
        if fraction != self._position_fraction:
            self._position_fraction = fraction
            self.update()

    # -- zoom / pan API (also the wheel/double-click handlers delegate here) ---

    @property
    def zoom_start(self) -> float:
        return self._zoom_start

    @property
    def zoom_end(self) -> float:
        return self._zoom_end

    def reset_zoom(self) -> None:
        """Return to the full-file overview."""
        self._set_zoom_window(0.0, 1.0)

    def zoom(self, cursor_fraction: float, zoom_in: bool) -> None:
        """Zoom around *cursor_fraction* (0..1 across the current view)."""
        cursor_fraction = max(0.0, min(1.0, cursor_fraction))
        span = self._zoom_end - self._zoom_start
        # Absolute position under the cursor in file-normalized coordinates.
        anchor = self._zoom_start + cursor_fraction * span
        factor = 0.8 if zoom_in else 1.25
        new_span = max(_MIN_ZOOM_SPAN, min(1.0, span * factor))
        new_start = anchor - cursor_fraction * new_span
        self._set_zoom_window(new_start, new_start + new_span)

    def _set_zoom_window(self, start: float, end: float) -> None:
        span = max(_MIN_ZOOM_SPAN, min(1.0, end - start))
        start = max(0.0, min(1.0 - span, start))
        self._zoom_start = start
        self._zoom_end = start + span
        self.update()

    # -- worker plumbing ------------------------------------------------------

    def _request(self) -> None:
        if self._service is None or self._path is None:
            return
        self._generation += 1
        generation = self._generation
        bins = max(1, int(round(self.width() * self.devicePixelRatioF())))

        from ..workers import WaveformWorker

        worker = WaveformWorker(generation, self._path, bins, self._service)
        worker.signals.waveform_ready.connect(self._on_waveform_ready)
        worker.signals.error.connect(self._on_worker_error)
        self._pool.start(worker)

    def _on_waveform_ready(self, generation: int, data: object) -> None:
        if generation != self._generation:
            return  # a newer request superseded this one
        self._data = data  # type: ignore[assignment]
        self._state = _State.READY
        self._error = ""
        self.update()

    def _on_worker_error(self, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self._data = None
        self._error = message
        self._state = _State.ERROR
        self.update()

    # -- Qt event overrides ---------------------------------------------------

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(200, 80)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # The bin count is tied to width; re-request at the new resolution.
        if self._path is not None and self._service is not None:
            self._state = _State.LOADING if self._data is None else self._state
            self._request()

    def wheelEvent(self, event) -> None:  # noqa: N802
        if self._state is not _State.READY:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        width = max(1, self.width())
        cursor_fraction = event.position().x() / width
        self.zoom(cursor_fraction, zoom_in=delta > 0)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.reset_zoom()
        event.accept()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._state is _State.READY:
            self._pan_anchor_x = event.position().x()
            self._pan_anchor_start = self._zoom_start
            self._pan_anchor_end = self._zoom_end
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._pan_anchor_x is None:
            super().mouseMoveEvent(event)
            return
        width = max(1, self.width())
        span = self._pan_anchor_end - self._pan_anchor_start
        dx_fraction = (event.position().x() - self._pan_anchor_x) / width
        # Dragging right reveals earlier audio, so shift the window left.
        new_start = self._pan_anchor_start - dx_fraction * span
        self._set_zoom_window(new_start, new_start + span)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._pan_anchor_x is not None:
            release_x = event.position().x()
            was_click = abs(release_x - self._pan_anchor_x) < _CLICK_THRESHOLD_PX
            self._pan_anchor_x = None
            if was_click and self._state is _State.READY:
                width = max(1, self.width())
                raw = self._zoom_start + (release_x / width) * (
                    self._zoom_end - self._zoom_start
                )
                self.seek_requested.emit(max(0.0, min(1.0, raw)))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # -- painting -------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        dpr = self.devicePixelRatioF()
        painter.scale(1.0 / dpr, 1.0 / dpr)
        phys_w = max(1, int(round(self.width() * dpr)))
        phys_h = max(1, int(round(self.height() * dpr)))
        rect = QRectF(0, 0, phys_w, phys_h)

        painter.fillRect(rect, _BG)

        if self._state is _State.EMPTY:
            return
        if self._state is _State.LOADING:
            self._draw_centered_text(painter, rect, "Loading…", _LOADING)
            return
        if self._state is _State.ERROR:
            self._draw_centered_text(painter, rect, self._error or "Error", _ERROR)
            return

        self._draw_waveform(painter, phys_w, phys_h)

    def _draw_centered_text(
        self, painter: QPainter, rect: QRectF, text: str, color: QColor
    ) -> None:
        painter.setPen(QPen(color))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)

    def _draw_waveform(self, painter: QPainter, phys_w: int, phys_h: int) -> None:
        data = self._data
        if data is None or not data.bins:
            return

        bins = self._visible_bins(data.bins, phys_w)
        mid = phys_h / 2.0
        half = phys_h / 2.0

        # Zero line.
        painter.setPen(QPen(_ZERO_LINE))
        painter.drawLine(0, int(mid), phys_w, int(mid))

        playhead_x = self._playhead_x(phys_w)

        played_pen = QPen(_WAVE_PLAYED)
        wave_pen = QPen(_WAVE)
        for x in range(min(phys_w, len(bins))):
            b = bins[x]
            y_top = mid - b.maximum * half
            y_bot = mid - b.minimum * half
            if playhead_x is not None and x <= playhead_x:
                painter.setPen(played_pen)
            else:
                painter.setPen(wave_pen)
            painter.drawLine(x, int(y_top), x, int(y_bot))

        if playhead_x is not None:
            painter.setPen(QPen(_PLAYHEAD))
            painter.drawLine(int(playhead_x), 0, int(playhead_x), phys_h)

    def _visible_bins(self, bins, phys_w: int):
        """Slice *bins* to the zoom window and resample to *phys_w* columns."""
        from ...audio.waveform import resample_bins

        total = len(bins)
        lo = int(self._zoom_start * total)
        hi = max(lo + 1, int(round(self._zoom_end * total)))
        window = bins[lo:hi] or bins
        return resample_bins(tuple(window), phys_w)

    def _playhead_x(self, phys_w: int) -> float | None:
        if self._position_fraction is None:
            return None
        span = self._zoom_end - self._zoom_start
        if span <= 0:
            return None
        in_view = (self._position_fraction - self._zoom_start) / span
        if in_view < 0.0 or in_view > 1.0:
            return None
        return in_view * phys_w
