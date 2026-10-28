"""Screen geometry and mode feedback for the browser-first TUI refresh."""

import asyncio
from dataclasses import replace

import pytest
from textual.widgets import Static

from sample_manager.audio import WaveformBin, WaveformData
from sample_manager.tui.widgets.file_tree import _format_item
from sample_manager.tui.widgets.top_display import TopDisplayWidget
from test_tui_navigation import _NavigationTestApp


def _roots(tmp_path):
    """Use disposable files so the real browser never touches a user library."""
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    (first / "kick.wav").write_bytes(b"RIFF0000")
    (first / "snare.wav").write_bytes(b"RIFF1111")
    return first, second


@pytest.mark.parametrize("size", [(80, 24), (120, 36), (160, 48)])
def test_workspace_geometry_and_live_resize(tmp_path, size):
    """Both lists stay on screen and dominate the available terminal height."""
    async def exercise():
        app = _NavigationTestApp(_roots(tmp_path))
        async with app.run_test(size=size) as pilot:
            # Resize the same mounted app to exercise responsive class changes.
            for width, height in [size, (80, 24), (120, 36)]:
                await pilot.resize_terminal(width, height)
                await pilot.pause()
                preview = app.query_one("#top-display")
                browser = app.query_one("#browser-zone")
                stage = app.query_one("#selection-list")
                shortcuts = app.query_one("#shortcut-bar")
                assert preview.region.width == width
                assert browser.region.y == stage.region.y == preview.region.bottom
                assert browser.region.height > preview.region.height
                assert browser.region.right == stage.region.x
                assert stage.region.right == width
                assert shortcuts.region.bottom == height
                assert stage.region.bottom == app.query_one("#transport-bar").region.y
                assert stage.region.bottom <= shortcuts.region.y
                assert app.query_one("#sample-list").size.height >= 9
                assert not app.query("#session-summary")
                assert not app.query("Footer")
                assert app.query_one("#browse-columns").display == (width >= 100)

    asyncio.run(exercise())


def test_context_hints_focus_and_waveform_reuse(tmp_path):
    """Actual key delivery updates hints without resetting the loaded preview."""
    async def exercise():
        roots = _roots(tmp_path)
        app = _NavigationTestApp(roots)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            hints = app.query_one("#shortcut-bar", Static)
            assert "/ Search" in hints.content
            assert "Library: one" in app.query_one("#library-header", Static).content
            assert "#1" not in _format_item(app._effective_focused_item())

            data = WaveformData(roots[0] / "kick.wav", 9.0, (WaveformBin(-1.0, 1.0),))
            app._waveform_data = data
            preview = app.query_one(TopDisplayWidget)
            preview.set_waveform_data(data)
            waveform = preview._waveform
            await pilot.press("w")
            await pilot.pause(0.25)
            assert "Enter Confirm" in hints.content
            await pilot.press("escape", "/", "z")
            await pilot.pause()
            assert "Esc Clear" in hints.content
            assert "no matches" in " ".join(str(row.content) for row in app.query("#sample-list Static"))
            await pilot.press("escape")
            await pilot.pause()
            # Reload after search's empty preview, then refresh selection state.
            preview.set_waveform_data(data)
            waveform = preview._waveform
            app._refresh_ui(audition=False)
            await pilot.pause()
            assert preview._waveform is waveform
            app._data.get_selection_total_size = lambda: 2048
            app._refresh_ui(audition=False)
            await pilot.press("tab")
            await pilot.pause()
            assert "Enter/d Remove" in hints.content
            assert app.query_one("#selection-list").border_title == "Stage · 2 · 2 KB"
            assert app.query_one("#selection-list").has_class("active-pane")
            assert not app.query_one("#browser-zone").has_class("active-pane")

    asyncio.run(exercise())


def test_stage_cursor_scrolls_into_view(tmp_path):
    """A long Stage keeps the keyboard target visible after replacing its rows."""
    async def exercise():
        roots = _roots(tmp_path)
        app = _NavigationTestApp(roots)
        app.fake_data.paths = {sid: roots[0] / f"sample_{sid:02}.wav" for sid in range(1, 41)}
        app.fake_data.selected = set(app.fake_data.paths)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("tab")
            await pilot.press(*(["down"] * 39))
            await pilot.pause()
            stage = app.query_one("#selection-list")
            cursor = stage.query_one(".cursor-row")
            assert stage.scroll_y > 0
            assert stage.content_region.contains_region(cursor.region)
            assert app._effective_focused_item().sample_id == 40

    asyncio.run(exercise())


def test_long_literal_metadata_and_empty_stage_fit(tmp_path):
    """Long filenames/tags stay literal and empty Stage guidance remains visible."""
    async def exercise():
        app = _NavigationTestApp(_roots(tmp_path))
        app.fake_data.selected.clear()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            preview = app.query_one(TopDisplayWidget)
            item = replace(app._effective_focused_item(), name="[analog] " + "long filename " * 20 + ".wav")
            preview.update_focus(item, {
                "ext": "wav", "size_bytes": 2048,
                "tags": ["[analog] " + "long tag " * 30],
            })
            await pilot.pause()
            rows = list(preview.query(".meta-row"))
            assert len(rows) == 1
            assert all(row.region.height == 1 for row in rows)
            assert all(preview.content_region.contains_region(row.region) for row in rows)
            assert "Tags: [analog]" in preview.metadata_panel._text.content
            hint = app.query_one(".sel-hint")
            assert hint.region.height >= 2
            assert app.query_one("#selection-list").content_region.contains_region(hint.region)

    asyncio.run(exercise())
