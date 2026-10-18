"""Directory traversal with actual hjkl delivery in Browser, Stage and inspector."""

import asyncio

from sample_manager.tui.widgets.action_pane import ActionPane
from sample_manager.tui.widgets.directory_screen import ContentsTree, DirectoryScreen
from test_tui_navigation import _NavigationTestApp
from test_tui_stage_folders import _StageApp, stage_env


def _browser_roots(tmp_path):
    """Create nested levels, an empty sibling and root samples without user data."""
    first, second = tmp_path / "one", tmp_path / "two"
    deep = first / "pack" / "deep"
    deep.mkdir(parents=True)
    (first / "pack" / "empty").mkdir()
    second.mkdir()
    for name in ("a.wav", "b.wav", "c.wav"):
        (deep / name).write_bytes(b"RIFF0000")
    for name in ("kick.wav", "snare.wav"):
        (first / name).write_bytes(b"RIFF0000")
    return first, second


def test_hjkl_browser_levels_remember_files_and_tolerate_deletion(tmp_path):
    """Repeated descent/ascent restores identity and clamps deleted cursor targets."""
    async def exercise():
        roots = _browser_roots(tmp_path)
        app = _NavigationTestApp(roots)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("h", "l", "l", "j", "j")
            assert app._state.current_dir == roots[0] / "pack" / "deep"
            assert app._effective_focused_item().name == "c.wav"
            await pilot.press("h")
            assert app._effective_focused_item().name == "deep"
            await pilot.press("j", "l", "j", "k")
            assert app._state.current_dir.name == "empty" and not app._state.items
            await pilot.press("h", "k", "l")
            assert app._effective_focused_item().name == "c.wav"
            await pilot.press("h")
            (roots[0] / "pack" / "deep" / "c.wav").unlink()
            await pilot.press("l")
            assert app._effective_focused_item().name == "b.wav"
            await pilot.press("h", "h")
            assert app._effective_focused_item().name == "pack"
            await pilot.press("j", "l")
            assert isinstance(app.screen, ActionPane)
            await pilot.press("escape", "h")
            assert app._state.current_dir == roots[0] and app._active_pane == "browser"
            assert app._effective_focused_item().name == "kick.wav"
            await pilot.press("/", "h", "j", "k", "l")
            assert app._filter_query == "hjkl"
            await pilot.press("escape")
            assert app._effective_focused_item().name == "kick.wav"
            assert app.fake_data.selected == {1, 2}

    asyncio.run(exercise())


def test_remembered_browser_row_is_visible_after_mount_and_reentry(tmp_path):
    """Long-list cursor scrolling follows the replacement rows, not old widgets."""
    async def exercise():
        roots = _browser_roots(tmp_path)
        for index in range(45):
            (roots[0] / "pack" / "deep" / f"long_{index:02}.wav").write_bytes(b"RIFF0000")
        app = _NavigationTestApp(roots)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("l", "l", *(["j"] * 35))
            focused = app._effective_focused_item().path
            await pilot.press("h", "l")
            await pilot.pause()
            assert app._effective_focused_item().path == focused
            listing = app.query_one("#sample-list")
            cursor = listing.query_one(".cursor-row")
            assert listing.scroll_y > 0
            assert listing.content_region.contains_region(cursor.region)

    asyncio.run(exercise())


def test_hjkl_stage_skips_parent_on_entry_and_remembers_samples(stage_env):
    """ll descends Stage levels directly; h stays at root and Escape switches panes."""
    db, roots = stage_env

    async def exercise():
        app = _StageApp(db, roots)
        workspace = app.test_data.stage_workspace
        folder = workspace.create_folder("Drums/Kicks")
        for row in app.test_data.search_samples(roots[0], "wav"):
            workspace.stage_sample(row.sample_id, folder)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            await pilot.press("tab", "l", "l")
            assert workspace.path(app._stage_current_folder_id) == "/Drums/Kicks"
            assert app._effective_focused_item().name == "kick.wav"
            await pilot.press("j")
            assert app._effective_focused_item().name == "snare.wav"
            await pilot.press("h", "l")
            assert app._effective_focused_item().name == "snare.wav"
            await pilot.press("k", "h", "h", "h")
            assert app._stage_current_folder_id is None and app._active_pane == "stage"
            await pilot.press("l", "l")
            assert app._effective_focused_item().name == "kick.wav"
            await pilot.press("k", "enter")  # Explicit .. has the same parent behavior.
            assert app._effective_focused_item().name == "Kicks"
            await pilot.press("l")
            assert app._effective_focused_item().name == "kick.wav"
            await pilot.press("h", "h", "escape")
            assert app._active_pane == "browser"
            assert len(workspace.placements()) == 2

    asyncio.run(exercise())


def test_directory_inspector_accepts_hjkl_without_changing_browser(tmp_path):
    """Vim tree expansion and cursor motion remain local to the inspector modal."""
    async def exercise():
        roots = _browser_roots(tmp_path)
        app = _NavigationTestApp(roots)
        async with app.run_test() as pilot:
            await pilot.pause()
            state = app._state
            await pilot.press("i")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert isinstance(app.screen, DirectoryScreen)
            tree = app.screen.query_one(ContentsTree)
            await pilot.press("l", "l")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert tree.cursor_node.data.path.name == "deep"
            assert tree.cursor_node.is_expanded
            await pilot.press("l", "j", "k")
            assert tree.cursor_node.data.path.name == "a.wav"
            await pilot.press("h", "h")
            assert tree.cursor_node.data.path.name == "deep"
            assert not tree.cursor_node.is_expanded
            await pilot.press("escape")
            assert app._state == state

    asyncio.run(exercise())
