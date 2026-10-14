"""Textual Pilot integration tests for the TUI.

These tests use Textual's built-in App.run_test() API to drive a headless
instance of the app and verify screen-level behaviour.

We run async test coroutines via asyncio.run() so no pytest-asyncio plugin
is needed (it is not in the project's dev dependencies).

Strategy: use a minimal _HelpTestApp stub rather than the full SampleManagerApp
to avoid the database/config dependency in on_mount.  The stub isolates exactly
what we want to test — that pressing '?' pushes HelpScreen and that each dismiss
key (escape, q, ?) pops it again.
"""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.widgets import Static

from sample_manager.tui.keybindings import resolve_key
from sample_manager.tui.widgets.help_screen import HelpScreen


# ---------------------------------------------------------------------------
# Minimal stub app
# ---------------------------------------------------------------------------


class _HelpTestApp(App):
    """Minimal Textual app that wires '?' → HelpScreen via the real KEYMAP.

    Uses resolve_key() — the same routing as SampleManagerApp — so the test
    validates the full keybinding → action → screen-push path.
    Avoids the database/config setup of the real SampleManagerApp.
    """

    def compose(self) -> ComposeResult:
        yield Static("browser", id="browser")

    def on_key(self, event) -> None:
        action = resolve_key(event.key)
        if action == "show_help":
            self.push_screen(HelpScreen())
            event.stop()


# ---------------------------------------------------------------------------
# Async test coroutines
# ---------------------------------------------------------------------------


async def _assert_help_opens_and_escape_dismisses() -> None:
    async with _HelpTestApp().run_test() as pilot:
        # Start on the base screen — HelpScreen not on the stack
        assert not isinstance(pilot.app.screen, HelpScreen)

        # Press '?' — HelpScreen should be pushed
        await pilot.press("?")
        await pilot.pause()
        assert isinstance(pilot.app.screen, HelpScreen), (
            "Expected HelpScreen to be the active screen after pressing '?'"
        )

        # Press Escape — HelpScreen should dismiss
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, HelpScreen), (
            "Expected HelpScreen to be dismissed after pressing Escape"
        )


async def _assert_help_dismisses_on_question_mark() -> None:
    async with _HelpTestApp().run_test() as pilot:
        await pilot.press("?")
        await pilot.pause()
        assert isinstance(pilot.app.screen, HelpScreen)

        # A second '?' should dismiss (handled inside HelpScreen.on_key)
        await pilot.press("?")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, HelpScreen), (
            "Expected HelpScreen to dismiss when '?' is pressed while it is open"
        )


async def _assert_help_dismisses_on_q() -> None:
    async with _HelpTestApp().run_test() as pilot:
        await pilot.press("?")
        await pilot.pause()
        assert isinstance(pilot.app.screen, HelpScreen)

        await pilot.press("q")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, HelpScreen), (
            "Expected HelpScreen to dismiss when 'q' is pressed"
        )


async def _assert_help_shows_keybinding_content() -> None:
    """Verify that HelpScreen renders at least one keybinding row."""
    async with _HelpTestApp().run_test() as pilot:
        await pilot.press("?")
        await pilot.pause()
        assert isinstance(pilot.app.screen, HelpScreen)

        # Query all Static widgets inside the help screen and collect their text.
        # In Textual 8.x, Static.content holds the text (renderable was renamed).
        statics = pilot.app.screen.query(Static)
        all_text = " ".join(s.content for s in statics)

        # At minimum the Navigation category header must appear
        assert "Navigation" in all_text, (
            "Expected 'Navigation' category header in HelpScreen content"
        )
        # And at least one arrow key symbol
        assert "↑" in all_text or "↓" in all_text, (
            "Expected arrow-key symbols in HelpScreen keybinding rows"
        )


# ---------------------------------------------------------------------------
# pytest test class
# ---------------------------------------------------------------------------


class TestHelpScreenPilot:
    """Pilot-driven tests: '?' opens help and dismiss keys return to the browser."""

    def test_question_mark_opens_help_escape_dismisses(self):
        asyncio.run(_assert_help_opens_and_escape_dismisses())

    def test_help_dismisses_on_second_question_mark(self):
        asyncio.run(_assert_help_dismisses_on_question_mark())

    def test_help_dismisses_on_q(self):
        asyncio.run(_assert_help_dismisses_on_q())

    def test_help_screen_shows_navigation_category(self):
        asyncio.run(_assert_help_shows_keybinding_content())
