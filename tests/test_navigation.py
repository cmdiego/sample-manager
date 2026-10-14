"""Unit tests for services/navigation.py — pure logic, no DB, no Textual/Qt.

Mirrors test_nav_state.py but targets the framework-neutral service module
directly, guaranteeing the extracted navigation logic stands alone.
"""

from dataclasses import replace
from pathlib import Path

from sample_manager.services.navigation import (
    NavItem,
    NavState,
    _to_rel_norm,
    build_items,
)


def _item(name: str, is_dir: bool = False, sample_id: int | None = None, selected: bool = False) -> NavItem:
    return NavItem(
        name=name,
        path=Path(f"/root/{name}"),
        is_dir=is_dir,
        sample_id=sample_id,
        is_selected=selected,
    )


def _with_focus(state: NavState, idx: int) -> NavState:
    return replace(state, focused_index=idx)


class TestNavStateMovement:
    def test_move_down_advances_focus(self):
        items = [_item("a"), _item("b"), _item("c")]
        state = NavState.initial(Path("/root"), items)
        assert state.focused_index == 0
        assert state.move_down().focused_index == 1

    def test_move_up_decrements_focus(self):
        items = [_item("a"), _item("b")]
        state = NavState.initial(Path("/root"), items)
        assert _with_focus(state, 1).move_up().focused_index == 0

    def test_move_down_clamps_at_bottom(self):
        items = [_item("a"), _item("b")]
        state = NavState.initial(Path("/root"), items)
        assert _with_focus(state, 1).move_down().focused_index == 1

    def test_move_up_clamps_at_top(self):
        items = [_item("a"), _item("b")]
        state = NavState.initial(Path("/root"), items)
        assert state.move_up().focused_index == 0

    def test_move_on_empty_list_is_noop(self):
        state = NavState.initial(Path("/root"), [])
        assert state.move_up().focused_index == -1
        assert state.move_down().focused_index == -1


class TestNavStateEnterAndGoBack:
    def test_enter_dir_pushes_stack(self):
        root = Path("/root")
        state = NavState.initial(root, [_item("subdir", is_dir=True)])
        subdir = Path("/root/subdir")
        state2 = state.enter_dir(subdir, [_item("file.wav")])
        assert state2.current_dir == subdir
        assert root in state2.dir_stack
        assert state2.focused_index == 0

    def test_go_back_pops_stack(self):
        root = Path("/root")
        subdir = Path("/root/subdir")
        parent_items = [_item("subdir", is_dir=True)]
        state = NavState.initial(root, parent_items)
        state2 = state.enter_dir(subdir, [_item("file.wav")])
        state3 = state2.go_back(parent_items)
        assert state3.current_dir == root
        assert len(state3.dir_stack) == 0

    def test_go_back_restores_focus_to_dir_we_came_from(self):
        root = Path("/root")
        subdir = Path("/root/subdir")
        parent_items = [_item("other", is_dir=True), _item("subdir", is_dir=True)]
        state = NavState.initial(root, parent_items)
        state2 = _with_focus(state, 1).enter_dir(subdir, [_item("file.wav")])
        state3 = state2.go_back(parent_items)
        assert state3.focused_index == 1

    def test_go_back_at_root_is_noop(self):
        state = NavState.initial(Path("/root"), [_item("a")])
        state2 = state.go_back([_item("a")])
        assert state2.dir_stack == ()
        assert state2.current_dir == Path("/root")


class TestNavStateSelection:
    def test_with_selection_marks_items(self):
        items = [
            _item("kick.wav", sample_id=10),
            _item("snare.wav", sample_id=20),
            _item("hat.wav", sample_id=30),
        ]
        state = NavState.initial(Path("/root"), items).with_selection({10, 30})
        assert state.items[0].is_selected is True
        assert state.items[1].is_selected is False
        assert state.items[2].is_selected is True

    def test_dirs_never_marked_selected(self):
        state = NavState.initial(Path("/root"), [_item("Kicks", is_dir=True)])
        assert state.with_selection({99}).items[0].is_selected is False

    def test_unindexed_files_not_selected(self):
        state = NavState.initial(Path("/root"), [_item("not_indexed.wav", sample_id=None)])
        assert state.with_selection({1, 2, 3}).items[0].is_selected is False


class TestFocusedItem:
    def test_focused_item_returns_correct_item(self):
        items = [_item("a"), _item("b"), _item("c")]
        state = _with_focus(NavState.initial(Path("/root"), items), 2)
        assert state.focused_item.name == "c"

    def test_focused_item_on_empty_is_none(self):
        assert NavState.initial(Path("/root"), []).focused_item is None


class TestBuildItems:
    def test_dirs_listed_before_files(self, tmp_path):
        (tmp_path / "b_dir").mkdir()
        (tmp_path / "a_file.wav").touch()
        items = build_items(tmp_path, {}, set())
        assert items[0].is_dir is True
        assert items[1].is_dir is False

    def test_indexed_files_get_sample_id(self, tmp_path):
        (tmp_path / "kick.wav").touch()
        items = build_items(tmp_path, {"kick.wav": 42}, set())
        file_items = [i for i in items if not i.is_dir]
        assert len(file_items) == 1
        assert file_items[0].sample_id == 42

    def test_unindexed_files_have_no_sample_id(self, tmp_path):
        (tmp_path / "unknown.wav").touch()
        assert build_items(tmp_path, {}, set())[0].sample_id is None

    def test_selected_files_marked(self, tmp_path):
        (tmp_path / "kick.wav").touch()
        assert build_items(tmp_path, {"kick.wav": 5}, {5})[0].is_selected is True

    def test_hidden_files_excluded(self, tmp_path):
        (tmp_path / ".hidden").touch()
        (tmp_path / "visible.wav").touch()
        items = build_items(tmp_path, {}, set())
        assert all(not i.name.startswith(".") for i in items)

    def test_empty_directory(self, tmp_path):
        assert build_items(tmp_path, {}, set()) == []

    def test_nested_file_two_levels_resolves_sample_id(self, tmp_path):
        subdir = tmp_path / "drums" / "kick"
        subdir.mkdir(parents=True)
        (subdir / "kick01.wav").touch()
        items = build_items(subdir, {"drums/kick/kick01.wav": 77}, set())
        file_items = [i for i in items if not i.is_dir]
        assert file_items[0].sample_id == 77

    def test_same_filename_in_different_subdirs_no_collision(self, tmp_path):
        drums_dir = tmp_path / "drums"
        synths_dir = tmp_path / "synths"
        drums_dir.mkdir()
        synths_dir.mkdir()
        (drums_dir / "hit.wav").touch()
        (synths_dir / "hit.wav").touch()
        indexed = {"drums/hit.wav": 10, "synths/hit.wav": 20}
        assert build_items(drums_dir, indexed, set())[0].sample_id == 10
        assert build_items(synths_dir, indexed, set())[0].sample_id == 20


class TestToRelNorm:
    def test_root_level_file(self, tmp_path):
        assert _to_rel_norm(tmp_path / "kick.wav", {"kick.wav": 1}) == "kick.wav"

    def test_two_levels_deep(self, tmp_path):
        path = tmp_path / "drums" / "kick" / "kick01.wav"
        assert _to_rel_norm(path, {"drums/kick/kick01.wav": 3}) == "drums/kick/kick01.wav"

    def test_returns_name_lower_when_not_in_indexed(self, tmp_path):
        assert _to_rel_norm(tmp_path / "drums" / "unknown.wav", {}) == "unknown.wav"

    def test_no_false_match_on_shared_suffix(self, tmp_path):
        path = tmp_path / "drums" / "kick.wav"
        assert _to_rel_norm(path, {"synths/kick.wav": 99}) == "kick.wav"
