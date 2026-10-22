"""Directory tree inspection and staging through real TUI key events."""

import asyncio

import pytest
from textual.widgets import Static

from sample_manager.services.directory_listing import list_directory
from sample_manager.tui.widgets.directory_screen import ContentsTree, DirectoryScreen
from sample_manager.tui.widgets.metadata_screen import MetadataScreen
from test_tui_navigation import _NavigationTestApp
from test_tui_stage_folders import stage_env


def _directory_app(tmp_path):
    """Build a library with nested folders, literal names and non-audio files."""
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    pack = first / "packs"
    deep = pack / "deep"
    deep.mkdir(parents=True)
    (deep / "[loop].wav").write_bytes(b"RIFF0000")
    (pack / "empty").mkdir()
    (pack / "readme.txt").write_text("not an audio file")
    (first / "kick.wav").write_bytes(b"RIFF0000")
    (first / "snare.wav").write_bytes(b"RIFF1111")
    return _NavigationTestApp((first, second)), pack


async def _settle(app, pilot):
    """Complete background directory reads and subsequent tree layout updates."""
    await pilot.pause()
    await app.workers.wait_for_complete()
    await pilot.pause()


@pytest.mark.parametrize("size", [(80, 24), (120, 36)])
def test_i_lists_nested_items_and_preserves_browser(tmp_path, size):
    """i on a folder shows all items; directional/Enter keys expand its descendants."""
    async def exercise():
        app, pack = _directory_app(tmp_path)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            original = app._state
            selected = set(app.fake_data.selected)
            assert app._effective_focused_item().path == pack
            assert app._command_unavailable("show_metadata") is None
            await pilot.press("i")
            await _settle(app, pilot)
            screen = app.screen
            assert isinstance(screen, DirectoryScreen)
            tree = screen.query_one(ContentsTree)
            assert [node.data.path.name for node in tree.root.children] == ["deep", "empty", "readme.txt"]
            dialog = screen.query_one("#directory-dialog")
            assert dialog.region.width <= size[0] and dialog.region.bottom <= size[1]
            await pilot.press("down", "right")
            await _settle(app, pilot)
            deep = tree.root.children[0]
            assert deep.is_expanded
            assert deep.children[0].label.plain == "[loop].wav"
            await pilot.press("right")
            assert tree.cursor_node is deep.children[0]
            await pilot.press("left", "left")
            assert not deep.is_expanded
            await pilot.press("down", "enter")
            await _settle(app, pilot)
            assert tree.cursor_node.data.path.name == "empty"
            assert tree.cursor_node.children[0].label.plain == "(empty directory)"
            await pilot.press("q")
            assert app.is_running and app._state == original
            assert app.fake_data.selected == selected
            # The sample inspection path and search text ownership stay intact.
            await pilot.press("down", "i")
            assert isinstance(app.screen, MetadataScreen)
            await pilot.press("escape", "/", "i")
            assert app._filter_query == "i"

    asyncio.run(exercise())


def test_directory_listing_is_sorted_complete_and_does_not_follow_links(tmp_path):
    """List non-audio/hidden files and link entries without walking linked folders."""
    directory = tmp_path / "folder"
    directory.mkdir()
    (directory / "z-dir").mkdir()
    (directory / "a.txt").write_text("a")
    (directory / ".hidden").write_text("hidden")
    items = list_directory(directory)
    assert [item.path.name for item in items] == ["z-dir", ".hidden", "a.txt"]
    link = directory / "cycle"
    try:
        link.symlink_to(directory, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks require privileges on this platform")
    linked = next(item for item in list_directory(directory) if item.path == link)
    assert linked.is_symlink and not linked.is_dir


def test_unreadable_directory_is_an_inline_error(tmp_path, monkeypatch):
    """A failed filesystem read leaves the inspector open and dismissible."""
    def fail(_path):
        """Simulate permission denial consistently across OS/user privileges."""
        raise PermissionError("Access denied")

    monkeypatch.setattr("sample_manager.tui.widgets.directory_screen.list_directory", fail)

    async def exercise():
        app, _pack = _directory_app(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("i")
            await _settle(app, pilot)
            tree = app.screen.query_one(ContentsTree)
            assert "Access denied" in tree.root.children[0].label.plain
            assert "unavailable" in app.screen.query_one("#directory-status", Static).content
            await pilot.press("escape")
            assert len(app.screen_stack) == 1 and app.is_running

    asyncio.run(exercise())


def test_symlink_nodes_cannot_expand_in_inspector(tmp_path):
    """A back-link is a terminal leaf, preventing recursive expansion cycles."""
    async def exercise():
        app, pack = _directory_app(tmp_path)
        try:
            (pack / "cycle").symlink_to(pack, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Directory symlinks require privileges on this platform")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("i")
            await _settle(app, pilot)
            tree = app.screen.query_one(ContentsTree)
            node = next(node for node in tree.root.children if node.data.path.name == "cycle")
            assert "(link)" in node.label.plain and not node.allow_expand
            tree.move_cursor(node)
            await pilot.press("right", "enter")
            await _settle(app, pilot)
            assert not node.children
            await pilot.press("i")
            assert len(app.screen_stack) == 1

    asyncio.run(exercise())


def test_inspector_stages_nested_samples_without_closing_or_changing_destination(stage_env):
    """Enter/a/d edit real Stage membership and preserve folder/tree identity."""
    from sample_manager.scanner import scan_library
    from test_tui_stage_folders import _StageApp

    db, roots = stage_env
    pack = roots[0] / 'pack'
    deep = pack / 'deep'
    deep.mkdir(parents=True)
    sample = deep / '[loop].wav'
    sample.write_bytes(b'RIFF sample fixture')
    (pack / 'readme.txt').write_text('keep me')
    scan_library(db, roots[0], fast=True)
    # A supported file created after indexing must explain why it cannot stage.
    (pack / 'unindexed.wav').write_bytes(b'RIFF unindexed')
    before = {p: p.read_bytes() for p in pack.rglob('*') if p.is_file()}

    async def exercise():
        app = _StageApp(db, roots)
        workspace = app.test_data.stage_workspace
        destination = workspace.create_folder('Kits/Drums')
        async with app.run_test() as pilot:
            await pilot.pause()
            app._stage_current_folder_id = destination
            browser_path = app._state.current_dir
            browser_cursor = app._state.focused_index
            await pilot.press('i')
            await _settle(app, pilot)
            screen = app.screen
            assert isinstance(screen, DirectoryScreen)
            tree = screen.query_one(ContentsTree)
            await pilot.press('a')
            assert not app.test_data.get_selection_ids()
            assert 'Choose an indexed' in screen.query_one('#directory-status', Static).content
            deep_node = tree.root.children[0]
            tree.move_cursor(deep_node)
            await pilot.press('enter')
            await _settle(app, pilot)
            leaf = deep_node.children[0]
            assert leaf.label.plain == '[ ] [loop].wav'
            tree.move_cursor(leaf)
            await pilot.press('a', 'a')
            sid = app._directory_sample_id(sample)
            assert workspace.placements() == {sid: destination}
            assert leaf.label.plain == '[✓] [loop].wav'
            assert tree.cursor_node is leaf and deep_node.is_expanded and app.screen is screen
            # Re-adding preserves a sample's existing placement elsewhere.
            other = workspace.move_sample(sid, '/Other')
            await pilot.press('a')
            assert workspace.placements()[sid] == other
            await pilot.press('enter')
            assert not app.test_data.get_selection_ids() and leaf.label.plain == '[ ] [loop].wav'
            await pilot.press('enter')
            assert workspace.placements()[sid] == destination
            await pilot.press('d', 'd')
            assert not app.test_data.get_selection_ids()
            for node in tree.root.children[1:]:
                tree.move_cursor(node)
                await pilot.press('a', 'enter')
                assert not app.test_data.get_selection_ids()
                assert 'not an indexed sample' in screen.query_one('#directory-status', Static).content
            tree.move_cursor(leaf)
            await pilot.press('a', 'escape')
            assert len(app.screen_stack) == 1
            assert app._state.current_dir == browser_path and app._state.focused_index == browser_cursor
            assert app._stage_current_folder_id == destination
            assert app._state.selection_ids == frozenset({sid})
            assert any(row.get('sample_id') == sid for row in app._stage_entries)
            await pilot.press('i')
            await _settle(app, pilot)
            tree = app.screen.query_one(ContentsTree)
            tree.root.children[0].expand()
            await _settle(app, pilot)
            assert tree.root.children[0].children[0].label.plain == '[✓] [loop].wav'
            await pilot.press('escape')
    asyncio.run(exercise())
    assert before == {p: p.read_bytes() for p in before}
