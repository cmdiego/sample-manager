"""TUI typeahead tests for match order and highlighted-row actions."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sample_manager.tui.app import SampleManagerApp
from sample_manager.tui.nav_state import NavItem, NavState
from sample_manager.tui.widgets.file_tree import SampleListWidget


def test_filter_matches_middle_of_name_and_acts_on_highlighted_match():
    """Arrow movement in a filtered list selects the second visible sample."""
    player = Mock()
    app = SampleManagerApp(audio_player=player, waveform_service=Mock())
    items = [
        NavItem("first_drum.wav", Path("/lib/first_drum.wav"), False, 1, False),
        NavItem("second_drum.wav", Path("/lib/second_drum.wav"), False, 2, False),
        NavItem("bass.wav", Path("/lib/bass.wav"), False, 3, False),
    ]
    app._state = NavState.initial(Path("/lib"), items)
    app._filter_active = True
    app._filter_query = "drum"
    app._refresh_ui = Mock()
    app._data = Mock()
    app._data.get_selection_ids.return_value = {2}

    assert [item.name for item in app._visible_items()] == [
        "first_drum.wav", "second_drum.wav"
    ]
    event = SimpleNamespace(key="down", character=None, stop=Mock())
    app.on_key(event)
    assert app._effective_focused_item().sample_id == 2

    enter = SimpleNamespace(key="enter", character=None, stop=Mock())
    app.on_key(enter)
    app._data.add_to_selection.assert_called_once_with(2)


def test_no_search_matches_are_not_called_an_empty_directory():
    """The TUI explains an empty result list without blaming the folder."""
    state = NavState.initial(Path("/lib"), [])
    widget = SampleListWidget(state)
    with patch.object(widget, "remove_children"), patch.object(widget, "mount"), patch(
        "sample_manager.tui.widgets.file_tree.Static"
    ) as static:
        widget.update(state, empty_label="no matches")
    assert "no matches" in static.call_args.args[0]
