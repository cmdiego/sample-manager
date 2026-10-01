"""Unit tests for tui/keybindings.py."""

import pytest

from sample_manager.tui.keybindings import (
    ACTION_CATEGORIES,
    ACTION_DESCRIPTIONS,
    KEYMAP,
    resolve_key,
)


class TestResolveKey:
    def test_vim_keys_resolve(self):
        assert resolve_key("h") == "go_back"
        assert resolve_key("j") == "move_down"
        assert resolve_key("k") == "move_up"
        assert resolve_key("l") == "enter"

    def test_arrow_keys_resolve(self):
        assert resolve_key("left") == "go_back"
        assert resolve_key("down") == "move_down"
        assert resolve_key("up") == "move_up"
        assert resolve_key("right") == "enter"

    def test_vim_and_arrow_are_equivalent(self):
        pairs = [("h", "left"), ("j", "down"), ("k", "up"), ("l", "right")]
        for vim_key, arrow_key in pairs:
            assert resolve_key(vim_key) == resolve_key(arrow_key)

    def test_selection_keys(self):
        assert resolve_key("a") == "add_to_selection"
        assert resolve_key("d") == "remove_from_selection"

    def test_playback_keys(self):
        assert resolve_key("space") == "toggle_playback"
        assert resolve_key("ctrl+space") == "resume_playback"

    def test_quit_key(self):
        assert resolve_key("q") == "quit"

    def test_unbound_key_returns_none(self):
        assert resolve_key("x") is None
        assert resolve_key("") is None
        assert resolve_key("ctrl+c") is None

    def test_all_keymap_values_are_strings(self):
        for key, action in KEYMAP.items():
            assert isinstance(action, str), f"KEYMAP[{key!r}] value is not a string"

    def test_no_duplicate_actions_for_same_key(self):
        # Every key in KEYMAP should produce a consistent result
        for key in KEYMAP:
            assert resolve_key(key) == KEYMAP[key]


class TestNewBindings:
    """Tests for the four keybindings added in the 4-zone layout redesign."""

    def test_slash_activates_filter(self):
        # Textual reports the '/' key as "slash" in event.key
        assert resolve_key("slash") == "activate_filter"

    def test_escape_cancels_or_goes_back(self):
        assert resolve_key("escape") == "cancel_or_back"

    def test_tab_cycles_pane_focus(self):
        assert resolve_key("tab") == "cycle_pane_focus"

    def test_ctrl_p_opens_command_palette(self):
        assert resolve_key("ctrl+p") == "command_palette"


class TestEnterAndHelpBindings:
    """Tests for the Return key and ? bindings added in tasks 002/003.

    Root-cause note (tasks 002 & 003):
    - Textual reports '?' as event.key == "question_mark" (not "?").
    - Textual reports '/' as event.key == "slash" (not "/").
    These KEYMAP keys must therefore use the Textual names.
    """

    def test_enter_key_resolves_to_select_or_descend(self):
        assert resolve_key("enter") == "select_or_descend"

    def test_question_mark_resolves_to_show_help(self):
        # Textual key name for '?' is "question_mark"
        assert resolve_key("question_mark") == "show_help"

    def test_slash_char_not_in_keymap(self):
        # "?" and "/" as raw characters are not in KEYMAP —
        # only the Textual key names "question_mark" and "slash" are.
        assert resolve_key("?") is None
        assert resolve_key("/") is None

    def test_enter_is_distinct_from_l_and_right(self):
        # Return selects/descends; l/right open the action pane
        assert resolve_key("enter") != resolve_key("l")
        assert resolve_key("enter") != resolve_key("right")


class TestActionMetadata:
    """Tests for ACTION_DESCRIPTIONS and ACTION_CATEGORIES exports."""

    def test_every_keymap_action_has_a_description(self):
        actions_in_keymap = set(KEYMAP.values())
        for action in actions_in_keymap:
            assert action in ACTION_DESCRIPTIONS, (
                f"Action {action!r} is in KEYMAP but has no entry in ACTION_DESCRIPTIONS"
            )

    def test_every_categorised_action_has_a_description(self):
        for category, actions in ACTION_CATEGORIES.items():
            for action in actions:
                assert action in ACTION_DESCRIPTIONS, (
                    f"Action {action!r} in category {category!r} has no ACTION_DESCRIPTIONS entry"
                )

    def test_action_categories_covers_all_keymap_actions(self):
        actions_in_keymap = set(KEYMAP.values())
        actions_in_categories = {
            action
            for actions in ACTION_CATEGORIES.values()
            for action in actions
        }
        missing = actions_in_keymap - actions_in_categories
        assert not missing, (
            f"These KEYMAP actions are not grouped in ACTION_CATEGORIES: {missing}"
        )

    def test_descriptions_are_non_empty_strings(self):
        for action, desc in ACTION_DESCRIPTIONS.items():
            assert isinstance(desc, str) and desc.strip(), (
                f"ACTION_DESCRIPTIONS[{action!r}] is empty or not a string"
            )
