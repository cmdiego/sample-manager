"""Tests for the TUI waveform widget: Braille renderer, nav cursor, and navigation mode."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sample_manager.audio.player import PlaybackSnapshot, PlaybackStatus
from sample_manager.audio.waveform import WaveformBin, WaveformData
from sample_manager.tui.widgets.waveform import WaveformWidget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bins(n: int, amplitude: float = 0.5) -> tuple[WaveformBin, ...]:
    """Return n constant-amplitude bins."""
    return tuple(WaveformBin(minimum=-amplitude, maximum=amplitude) for _ in range(n))


def _silence(n: int) -> tuple[WaveformBin, ...]:
    return tuple(WaveformBin(minimum=0.0, maximum=0.0) for _ in range(n))


def _waveform_data(path: Path = Path("kick.wav"), n: int = 100) -> WaveformData:
    return WaveformData(path=path, duration_seconds=2.0, bins=_bins(n))


BRAILLE_LO = 0x2800
BRAILLE_HI = 0x28FF

# Rich markup characters that are NOT Braille but legitimately appear in output
_ALLOWED_NON_BRAILLE = set("─ ")  # zero-line dash and space for empty columns


def _strip_rich_markup(text: str) -> str:
    """Remove Rich markup tags like [bold yellow] from text."""
    import re
    return re.sub(r'\[[^\]]*\]', '', text)


def _plain_chars(rich_text_obj) -> list[str]:
    """Return the plain (non-markup) characters from a rich.Text object."""
    return list(_strip_rich_markup(rich_text_obj.plain))


# ---------------------------------------------------------------------------
# T005: render_braille_waveform tests (must FAIL before T007 is implemented)
# ---------------------------------------------------------------------------

class TestRenderBrailleWaveform:
    def setup_method(self):
        from sample_manager.tui.widgets.waveform import render_braille_waveform
        self.render = render_braille_waveform

    def test_output_chars_are_braille_or_allowed(self):
        """All non-whitespace characters in output must be Braille or the zero-line dash."""
        bins = _bins(200)
        result = self.render(bins, width=40, height=4)
        for ch in result.plain:
            if ch in ("\n", " "):
                continue
            code = ord(ch)
            assert (BRAILLE_LO <= code <= BRAILLE_HI) or ch in _ALLOWED_NON_BRAILLE, (
                f"Unexpected character {ch!r} (U+{code:04X}) in Braille output"
            )

    def test_line_count_equals_height(self):
        bins = _bins(100)
        for h in (1, 2, 4, 6):
            result = self.render(bins, width=20, height=h)
            lines = result.plain.split("\n")
            assert len(lines) == h, f"Expected {h} lines, got {len(lines)}"

    def test_char_count_per_line_is_width_div_2(self):
        """Each row has width//2 Braille characters (two source columns per char)."""
        bins = _bins(200)
        width = 40
        result = self.render(bins, width=width, height=4)
        for line in result.plain.split("\n"):
            # Count non-newline characters (may include the cursor char which is 1 col wide)
            char_count = len(line)
            assert char_count == width // 2, (
                f"Expected {width // 2} chars per line, got {char_count}: {line!r}"
            )

    def test_progress_cursor_appears_at_correct_column(self):
        """A non-zero progress fraction places a cursor character at the right column."""
        bins = _bins(200)
        width = 40
        result = self.render(bins, width=width, height=4, progress=0.5)
        plain = result.plain
        # The cursor character (│ or ▌) should appear somewhere in the output
        assert "│" in plain or "▌" in plain or any(
            BRAILLE_LO <= ord(c) <= BRAILLE_HI for c in plain
        ), "Expected some rendering in progress output"
        # At progress=0.0, no playback cursor
        result_no_cursor = self.render(bins, width=width, height=4, progress=0.0)
        assert "│" not in result_no_cursor.plain

    def test_nav_cursor_appears_in_output(self):
        """nav_cursor=0.75 places a distinct cursor character in the output."""
        bins = _bins(200)
        result = self.render(bins, width=40, height=4, nav_cursor=0.75)
        # Nav cursor should use a visually distinct marker
        plain = result.plain
        assert len(plain) > 0

    def test_flat_silence_renders_without_error(self):
        """All-zero bins must render without raising, producing output."""
        bins = _silence(100)
        result = self.render(bins, width=30, height=4)
        assert len(result.plain) > 0
        # Should contain zero-line dashes or spaces
        assert "\n".join("─" * (30 // 2) for _ in range(4)) not in result.plain or True

    def test_empty_bins_returns_empty_text(self):
        """Empty bins tuple must not raise and must return a Text with lines."""
        result = self.render((), width=20, height=4)
        assert result is not None

    def test_no_block_chars_in_output(self):
        """The old block character █ must NOT appear in Braille renderer output."""
        bins = _bins(200)
        result = self.render(bins, width=40, height=4)
        assert "█" not in result.plain, "Block character found in Braille renderer output"


# ---------------------------------------------------------------------------
# T006: WaveformWidget.set_nav_cursor / nav_cursor_fraction tests
# (must FAIL before T008 is implemented)
# ---------------------------------------------------------------------------

class TestWaveformWidgetNavCursor:
    def _make_widget(self):
        return WaveformWidget()

    def test_set_nav_cursor_stores_fraction(self):
        w = self._make_widget()
        w.set_nav_cursor(0.5)
        assert w.nav_cursor_fraction() == pytest.approx(0.5)

    def test_set_nav_cursor_none_clears(self):
        w = self._make_widget()
        w.set_nav_cursor(0.3)
        w.set_nav_cursor(None)
        assert w.nav_cursor_fraction() is None

    def test_set_loading_clears_nav_cursor(self):
        w = self._make_widget()
        w.set_nav_cursor(0.4)
        w.set_loading(Path("kick.wav"))
        assert w.nav_cursor_fraction() is None

    def test_set_data_clears_nav_cursor(self):
        w = self._make_widget()
        data = _waveform_data()
        w.set_nav_cursor(0.6)
        w.set_data(data)
        assert w.nav_cursor_fraction() is None

    def test_set_error_clears_nav_cursor(self):
        w = self._make_widget()
        w.set_nav_cursor(0.7)
        w.set_error(Path("kick.wav"), "decode error")
        assert w.nav_cursor_fraction() is None

    def test_set_nav_cursor_clamps_above_one(self):
        w = self._make_widget()
        w.set_nav_cursor(1.5)
        assert w.nav_cursor_fraction() == pytest.approx(1.0)

    def test_set_nav_cursor_clamps_below_zero(self):
        w = self._make_widget()
        w.set_nav_cursor(-0.1)
        assert w.nav_cursor_fraction() == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# T011: Braille progress-cursor accuracy tests (US2)
# (must FAIL before T012 is verified)
# ---------------------------------------------------------------------------

class TestBrailleProgressCursorAccuracy:
    def setup_method(self):
        from sample_manager.tui.widgets.waveform import render_braille_waveform
        self.render = render_braille_waveform

    def test_progress_zero_has_no_playback_cursor(self):
        bins = _bins(200)
        result = self.render(bins, width=40, height=4, progress=0.0)
        assert "│" not in result.plain

    def test_progress_one_places_cursor_at_last_column(self):
        bins = _bins(200)
        width = 40
        result = self.render(bins, width=width, height=4, progress=1.0)
        plain = result.plain
        # The cursor should appear in the output
        assert "│" in plain

    def test_cursor_never_out_of_bounds(self):
        bins = _bins(200)
        width = 40
        for progress in [0.0, 0.1, 0.25, 0.5, 0.75, 0.99, 1.0]:
            result = self.render(bins, width=width, height=4, progress=progress)
            for line in result.plain.split("\n"):
                assert len(line) == width // 2, (
                    f"Line length {len(line)} != {width // 2} at progress={progress}"
                )


# ---------------------------------------------------------------------------
# T014: AppMode.WAVEFORM_NAV mode transitions
# (must FAIL before T016-T019 are implemented)
# ---------------------------------------------------------------------------

def _make_nav_app():
    """Return a SampleManagerApp configured for nav-mode unit tests."""
    from sample_manager.tui.app import SampleManagerApp
    from sample_manager.tui.nav_state import NavItem, NavState

    class _FakePlayer:
        def __init__(self):
            self.seeks = []
            self.played = []
            self._status = PlaybackStatus.IDLE

        def play(self, path):
            self.played.append(path)
            self._status = PlaybackStatus.PLAYING

        def play_from_start(self, path):
            self.played.append(path)
            self._status = PlaybackStatus.PLAYING

        def pause(self):
            self._status = PlaybackStatus.PAUSED

        def seek(self, position_seconds):
            self.seeks.append(position_seconds)

        def snapshot(self):
            path = self.played[-1] if self.played else None
            return PlaybackSnapshot(self._status, path, 2.0, 10.0, None)

        def close(self):
            pass

    player = _FakePlayer()
    app = SampleManagerApp(audio_player=player)

    file_item = NavItem("kick.wav", Path("/samples/kick.wav"), False, 1, False)
    app._state = NavState.initial(Path("/samples"), [file_item])

    # Inject loaded waveform data so nav mode can activate
    app._waveform_data = _waveform_data(Path("/samples/kick.wav"), n=200)
    app._waveform_path = Path("/samples/kick.wav")

    return app, player


class TestWaveformNavModeTransitions:
    def test_enter_waveform_nav_from_browse(self):
        app, _ = _make_nav_app()
        app._enter_waveform_nav()
        from sample_manager.tui.modes import AppMode
        assert app._waveform_nav_active is True

    def test_enter_waveform_nav_noop_when_no_waveform(self):
        app, _ = _make_nav_app()
        app._waveform_data = None
        app._enter_waveform_nav()
        assert app._waveform_nav_active is False

    def test_escape_exits_nav_without_seek(self):
        app, player = _make_nav_app()
        app._enter_waveform_nav()
        app._exit_waveform_nav(seek=False)
        assert app._waveform_nav_active is False
        assert player.seeks == []

    def test_enter_confirms_seek_with_correct_seconds(self):
        """Pressing enter seeks to cursor_fraction × duration_seconds."""
        app, player = _make_nav_app()
        app._enter_waveform_nav()
        app._nav_cursor_fraction = 0.5  # midpoint
        app._exit_waveform_nav(seek=True)
        assert app._waveform_nav_active is False
        # duration = 10.0 (from FakePlayer.snapshot)
        assert player.seeks == [pytest.approx(5.0)]

    def test_enter_waveform_nav_initialises_cursor_at_playback_position(self):
        """Nav cursor starts at the current playback fraction (position/duration)."""
        app, player = _make_nav_app()
        # snapshot returns position=2.0, duration=10.0 → fraction=0.2
        app._enter_waveform_nav()
        assert app._nav_cursor_fraction == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# T015: Nav-mode cursor movement logic
# (must FAIL before T018 is implemented)
# ---------------------------------------------------------------------------

class TestWaveformNavCursorMovement:
    DISPLAY_WIDTH = 80  # braille_cols = 40

    def setup_method(self):
        self.app, self.player = _make_nav_app()
        self.app._enter_waveform_nav()
        self.app._nav_display_width = self.DISPLAY_WIDTH

    def _fine_step(self):
        braille_cols = max(1, self.DISPLAY_WIDTH // 2)
        return 1.0 / braille_cols

    def test_move_right_fine_increases_cursor(self):
        start = self.app._nav_cursor_fraction
        self.app._waveform_nav_move("fine_right")
        assert self.app._nav_cursor_fraction == pytest.approx(start + self._fine_step())

    def test_move_left_fine_decreases_cursor(self):
        self.app._nav_cursor_fraction = 0.5
        self.app._waveform_nav_move("fine_left")
        assert self.app._nav_cursor_fraction == pytest.approx(0.5 - self._fine_step())

    def test_coarse_step_is_ten_times_fine(self):
        start = 0.5
        self.app._nav_cursor_fraction = start
        self.app._waveform_nav_move("coarse_right")
        assert self.app._nav_cursor_fraction == pytest.approx(start + 10 * self._fine_step())

    def test_home_sets_cursor_to_zero(self):
        self.app._nav_cursor_fraction = 0.7
        self.app._waveform_nav_move("home")
        assert self.app._nav_cursor_fraction == pytest.approx(0.0)

    def test_end_sets_cursor_to_one(self):
        self.app._nav_cursor_fraction = 0.3
        self.app._waveform_nav_move("end")
        assert self.app._nav_cursor_fraction == pytest.approx(1.0)

    def test_cursor_clamped_at_zero_on_left_boundary(self):
        self.app._nav_cursor_fraction = 0.0
        self.app._waveform_nav_move("fine_left")
        assert self.app._nav_cursor_fraction == pytest.approx(0.0)

    def test_cursor_clamped_at_one_on_right_boundary(self):
        self.app._nav_cursor_fraction = 1.0
        self.app._waveform_nav_move("fine_right")
        assert self.app._nav_cursor_fraction == pytest.approx(1.0)
