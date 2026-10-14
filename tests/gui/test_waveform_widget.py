"""Phase 4 tests for the QPainter waveform widget (offscreen).

Covers: rendering at physical-pixel width, loading/error/empty states, stale
generation dropping, and zoom/pan window updates. Waveform envelopes are built
directly as plain data so these tests need no numpy or a real decode backend.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor

from sample_manager.audio.waveform import WaveformBin, WaveformData
from sample_manager.gui.widgets.waveform import _WAVE, WaveformWidget


class _SyncPool:
    """Runs runnables inline so worker signals fire on the calling thread."""

    def start(self, runnable):
        runnable.run()

    def setMaxThreadCount(self, _n):
        pass


class _FakeService:
    """Records the requested bin count and returns a full-scale envelope."""

    def __init__(self, duration: float = 9.0) -> None:
        self.duration = duration
        self.last_bins: int | None = None
        self.calls = 0

    def get_waveform(self, path, bins):
        self.last_bins = bins
        self.calls += 1
        envelope = tuple(WaveformBin(minimum=-1.0, maximum=1.0) for _ in range(bins))
        return WaveformData(path=Path(path), duration_seconds=self.duration, bins=envelope)


def _make_widget(qtbot, service=None):
    widget = WaveformWidget(service=service)
    qtbot.addWidget(widget)
    widget._pool = _SyncPool()  # deterministic, no thread pool
    widget.resize(300, 100)
    return widget


# ---------------------------------------------------------------------------
# rendering / physical pixel width
# ---------------------------------------------------------------------------


def test_requests_physical_pixel_width_bins(qtbot):
    service = _FakeService()
    widget = _make_widget(qtbot, service)
    widget.set_path(Path("/tmp/kick.wav"))
    expected = int(round(widget.width() * widget.devicePixelRatioF()))
    assert service.last_bins == expected
    assert service.calls >= 1


def test_renders_waveform_across_full_width(qtbot):
    service = _FakeService()
    widget = _make_widget(qtbot, service)
    widget.set_path(Path("/tmp/kick.wav"))

    image = widget.grab().toImage()
    mid_y = widget.height() // 2
    # Full-scale bins draw a green column at both edges of the widget.
    left = image.pixelColor(0, mid_y)
    right = image.pixelColor(widget.width() - 1, mid_y)
    green = QColor(_WAVE)
    for pixel in (left, right):
        assert pixel.green() > pixel.red()
        assert pixel.green() > pixel.blue()
        assert abs(pixel.green() - green.green()) < 60


# ---------------------------------------------------------------------------
# state transitions
# ---------------------------------------------------------------------------


def test_loading_state_before_data(qtbot):
    # No service => set_path leaves the widget in the loading state (no data yet).
    widget = _make_widget(qtbot, service=None)
    widget.set_path(Path("/tmp/kick.wav"))
    from sample_manager.gui.widgets.waveform import _State

    assert widget._state is _State.LOADING


def test_error_state_on_service_failure(qtbot):
    class _Boom:
        def get_waveform(self, path, bins):
            raise RuntimeError("decode blew up")

    widget = _make_widget(qtbot, _Boom())
    widget.set_path(Path("/tmp/bad.wav"))
    from sample_manager.gui.widgets.waveform import _State

    assert widget._state is _State.ERROR
    assert "decode blew up" in widget._error


def test_empty_state_when_cleared(qtbot):
    service = _FakeService()
    widget = _make_widget(qtbot, service)
    widget.set_path(Path("/tmp/kick.wav"))
    widget.set_path(None)
    from sample_manager.gui.widgets.waveform import _State

    assert widget._state is _State.EMPTY


def test_stale_generation_results_dropped(qtbot):
    widget = _make_widget(qtbot, service=None)
    widget.set_path(Path("/tmp/kick.wav"))
    from sample_manager.gui.widgets.waveform import _State

    stale = WaveformData(
        path=Path("/tmp/kick.wav"),
        duration_seconds=1.0,
        bins=(WaveformBin(-1.0, 1.0),),
    )
    # A result from an older generation must be ignored entirely.
    widget._on_waveform_ready(widget._generation - 5, stale)
    assert widget._data is None
    assert widget._state is _State.LOADING

    # The current generation is accepted.
    widget._on_waveform_ready(widget._generation, stale)
    assert widget._data is stale
    assert widget._state is _State.READY


# ---------------------------------------------------------------------------
# zoom / pan
# ---------------------------------------------------------------------------


def _ready_widget(qtbot):
    widget = _make_widget(qtbot, _FakeService())
    widget.set_path(Path("/tmp/kick.wav"))
    return widget


def test_zoom_in_narrows_window_around_cursor(qtbot):
    widget = _ready_widget(qtbot)
    assert (widget.zoom_start, widget.zoom_end) == (0.0, 1.0)
    widget.zoom(cursor_fraction=0.5, zoom_in=True)
    assert widget.zoom_end - widget.zoom_start < 1.0
    # Centered zoom keeps the midpoint roughly under the cursor.
    midpoint = (widget.zoom_start + widget.zoom_end) / 2
    assert abs(midpoint - 0.5) < 0.05


def test_zoom_clamped_to_minimum_span(qtbot):
    widget = _ready_widget(qtbot)
    for _ in range(50):
        widget.zoom(cursor_fraction=0.5, zoom_in=True)
    assert widget.zoom_end - widget.zoom_start >= 0.05 - 1e-9


def test_double_click_resets_zoom(qtbot):
    widget = _ready_widget(qtbot)
    widget.zoom(cursor_fraction=0.3, zoom_in=True)
    assert (widget.zoom_start, widget.zoom_end) != (0.0, 1.0)
    widget.reset_zoom()
    assert (widget.zoom_start, widget.zoom_end) == (0.0, 1.0)


def test_zoom_window_never_leaves_bounds(qtbot):
    widget = _ready_widget(qtbot)
    widget.zoom(cursor_fraction=1.0, zoom_in=True)
    widget.zoom(cursor_fraction=1.0, zoom_in=True)
    assert widget.zoom_start >= 0.0
    assert widget.zoom_end <= 1.0


# ---------------------------------------------------------------------------
# T021: click-to-seek tests (must FAIL before T022 is implemented)
# ---------------------------------------------------------------------------

def test_click_emits_seek_requested_signal(qtbot):
    """A click (press + release within threshold) emits seek_requested."""
    widget = _ready_widget(qtbot)
    emitted = []
    widget.seek_requested.connect(emitted.append)

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    # Click at x=75 on a 300px-wide widget → fraction ≈ 0.25.
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(75, 50))
    assert len(emitted) == 1
    assert abs(emitted[0] - 0.25) < 0.05


def test_drag_does_not_emit_seek_requested(qtbot):
    """A drag (large horizontal movement) must NOT emit seek_requested."""
    widget = _ready_widget(qtbot)
    emitted = []
    widget.seek_requested.connect(emitted.append)

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    # Press, move far right (well beyond threshold), release.
    QTest.mousePress(widget, Qt.MouseButton.LeftButton, pos=QPoint(10, 50))
    QTest.mouseMove(widget, QPoint(200, 50))
    QTest.mouseRelease(widget, Qt.MouseButton.LeftButton, pos=QPoint(200, 50))
    assert emitted == []


def test_seek_respects_zoom_window(qtbot):
    """Click fraction accounts for the current zoom window."""
    widget = _ready_widget(qtbot)
    widget._zoom_start = 0.25
    widget._zoom_end = 0.75
    emitted = []
    widget.seek_requested.connect(emitted.append)

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    # Click at 50% of widget width (x=150 on 300px widget).
    # File fraction = 0.25 + 0.5 * 0.5 = 0.5
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(150, 50))
    assert len(emitted) == 1
    assert abs(emitted[0] - 0.5) < 0.05


def test_click_not_emitted_when_loading(qtbot):
    """No seek signal when the widget is in LOADING state."""
    widget = _make_widget(qtbot, service=None)
    widget.set_path(Path("/tmp/kick.wav"))  # state = LOADING (no service)
    emitted = []
    widget.seek_requested.connect(emitted.append)

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(100, 50))
    assert emitted == []


def test_seek_fraction_clamped_to_unit_interval(qtbot):
    """Emitted fraction is always in [0.0, 1.0]."""
    widget = _ready_widget(qtbot)
    emitted = []
    widget.seek_requested.connect(emitted.append)

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    # Click at x=0 (left edge).
    QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=QPoint(0, 50))
    assert len(emitted) >= 1
    for frac in emitted:
        assert 0.0 <= frac <= 1.0
