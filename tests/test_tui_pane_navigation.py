"""Actual Ctrl key delivery across pane geometry, search and modal boundaries."""

import asyncio

import pytest

from sample_manager.audio import WaveformBin, WaveformData
from sample_manager.tui.keybindings import resolve_key
from sample_manager.tui.widgets.help_screen import HelpScreen
from test_tui_navigation import _NavigationTestApp
from test_tui_vim_browsing import _browser_roots


@pytest.mark.parametrize('letters', [True, False])
def test_directional_panes_and_outer_boundaries(tmp_path, letters):
    """Both shortcut families follow geometry without wrapping or moving cursors."""
    async def exercise():
        app = _NavigationTestApp(_browser_roots(tmp_path))
        left, down, up, right = ('ctrl+h', 'ctrl+j', 'ctrl+k', 'ctrl+l') if letters else ('ctrl+left', 'ctrl+down', 'ctrl+up', 'ctrl+right')
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            browser_item = app._effective_focused_item()
            await pilot.press(left, down)
            assert app._active_pane == 'browser' and not app._preview_focused
            await pilot.press(right, right, 'j')
            assert app._active_pane == 'stage' and app._stage_focused_index == 1
            stage_item = app._effective_focused_item()
            await pilot.press(up, up, left, right)
            assert app._preview_focused and app._active_pane == 'stage'
            assert app.query_one('#top-display').has_class('active-pane')
            assert len(app.query('.active-pane')) == 1
            await pilot.press('j', 'k', 'h', 'l')
            assert app._effective_focused_item() == stage_item
            await pilot.press(down, down)
            assert not app._preview_focused and app._active_pane == 'stage'
            assert app._effective_focused_item() == stage_item
            await pilot.press(left)
            assert app._effective_focused_item() == browser_item
            await pilot.press(up, 'escape', 'tab')
            assert not app._preview_focused and app._active_pane == 'stage'
            app._audio_player.seek.assert_not_called()
    asyncio.run(exercise())


def test_focus_controls_during_search_waveform_and_modal(tmp_path):
    """Pane movement bypasses search capture, cancels seek and respects dialogs."""
    async def exercise():
        roots = _browser_roots(tmp_path)
        app = _NavigationTestApp(roots)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press('/', 'k', 'i', 'c', 'k', 'ctrl+up')
            assert app._preview_focused and app._filter_query == 'kick'
            await pilot.press('ctrl+down')
            assert app._filter_active and app._filter_query == 'kick'
            await pilot.press('ctrl+right')
            assert app._active_pane == 'stage' and not app._filter_active
            app._waveform_data = WaveformData(roots[0] / 'kick.wav', 9.0, (WaveformBin(-1.0, 1.0),))
            await pilot.press('ctrl+k', 'l')
            assert app._waveform_nav_active and app._nav_cursor_fraction > 0
            panel = app.query_one('#top-display').metadata_panel
            panel._text.update('\n'.join(str(i) for i in range(30)))
            await pilot.pause()
            await pilot.press('j', 'j')
            await pilot.pause()
            assert panel.scroll_y > 0
            await pilot.press('ctrl+j')
            assert not app._waveform_nav_active
            app._audio_player.seek.assert_not_called()
            await pilot.press('question_mark')
            assert isinstance(app.screen, HelpScreen)
            await pilot.press('ctrl+h', 'ctrl+k', 'ctrl+left', 'ctrl+up')
            assert app._active_pane == 'stage' and not app._preview_focused
            await pilot.press('escape', 'ctrl+h')
            assert app._active_pane == 'browser'
    asyncio.run(exercise())


def test_directional_keymap_aliases():
    """Help and dispatch expose the same control aliases without changing hjkl."""
    for letter, arrow in zip('hjkl', ('left', 'down', 'up', 'right')):
        assert resolve_key('ctrl+' + letter) == resolve_key('ctrl+' + arrow) == 'focus_pane_' + arrow
        assert resolve_key(letter) != resolve_key('ctrl+' + letter)


def test_terminal_ctrl_h_returns_from_stage_without_stealing_backspace(tmp_path):
    """Legacy terminals encode Ctrl+H as backspace; real deletion stays local."""
    from textual._xterm_parser import XTermParser

    async def send_terminal(app, pilot, raw):
        """Deliver decoded terminal bytes rather than Pilot's named key events."""
        for event in XTermParser().feed(raw):
            app.post_message(event)
        await pilot.pause()

    async def exercise():
        app = _NavigationTestApp(_browser_roots(tmp_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press('ctrl+l')
            assert app._active_pane == 'stage'
            # Put native focus in Stage too, as happens after clicking the pane.
            app.query_one('#selection-list').focus()
            await send_terminal(app, pilot, '\x08')
            assert app._active_pane == 'browser'
            await pilot.press('/', 'k', 'i')
            await send_terminal(app, pilot, '\x08')
            assert app._filter_query == 'k' and app._active_pane == 'browser'
            await pilot.press('escape', 'ctrl+l')
            await send_terminal(app, pilot, '\x7f')
            assert app._active_pane == 'stage'
            await pilot.press('question_mark')
            await send_terminal(app, pilot, '\x08')
            assert isinstance(app.screen, HelpScreen) and app._active_pane == 'stage'
            await pilot.press('escape')
            await send_terminal(app, pilot, '\x1b[1;5D')
            assert app._active_pane == 'browser'
    asyncio.run(exercise())
