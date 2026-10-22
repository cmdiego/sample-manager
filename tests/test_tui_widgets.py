"""Unit tests for TUI widgets.

All tests are synchronous — no Textual pilot or async runner needed.
Strategy:
  - Widget __init__ attributes (border_title, _query, etc.) are tested by
    constructing the widget directly; no running app required.
  - Methods that manipulate the Textual DOM (mount, remove_children, query_one)
    are intercepted with unittest.mock so the assertions remain on observable
    outputs: border_title, the text passed to Static, and call counts.
  - Message classes (CursorMoved, ItemActivated) are plain Python objects and
    can be instantiated directly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from sample_manager.tui.nav_state import NavItem
from sample_manager.tui.widgets.file_tree import FileTreeWidget, SampleListWidget
from sample_manager.tui.widgets.filters_panel import FiltersPanel
from sample_manager.tui.widgets.selection_list import SelectedFilesListWidget
from sample_manager.tui.widgets.session_summary import SessionSummaryWidget
from sample_manager.tui.widgets.top_display import TopDisplayWidget


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _nav_item(
    name: str,
    is_dir: bool = False,
    sample_id: int | None = None,
    is_selected: bool = False,
) -> NavItem:
    return NavItem(
        name=name,
        path=Path(f"/root/{name}"),
        is_dir=is_dir,
        sample_id=sample_id,
        is_selected=is_selected,
    )


def _all_static_texts(mock_static) -> str:
    """Return all positional-arg strings passed to a mocked Static constructor."""
    texts = []
    for c in mock_static.call_args_list:
        if c.args:
            texts.append(str(c.args[0]))
    return " ".join(texts)


# ---------------------------------------------------------------------------
# _fmt_size (top_display.py)
# ---------------------------------------------------------------------------


class TestFmtSizeTopDisplay:
    """Pure-function tests for _fmt_size in top_display.py."""

    def _fmt(self, n):
        from sample_manager.tui.widgets.top_display import _fmt_size
        return _fmt_size(n)

    def test_none_returns_question_mark(self):
        assert self._fmt(None) == "?"

    def test_zero_bytes(self):
        assert self._fmt(0) == "0 B"

    def test_sub_kilobyte(self):
        assert self._fmt(512) == "512 B"

    def test_exact_kilobyte(self):
        assert self._fmt(1024) == "1 KB"

    def test_two_kilobytes(self):
        assert self._fmt(2048) == "2 KB"

    def test_megabyte(self):
        assert self._fmt(1024 * 1024) == "1 MB"

    def test_gigabyte(self):
        assert self._fmt(1024 ** 3) == "1 GB"


# ---------------------------------------------------------------------------
# TopDisplayWidget
# ---------------------------------------------------------------------------


class TestTopDisplayWidget:
    """Tests for TopDisplayWidget.update_focus()."""

    def test_default_border_title_is_preview(self):
        widget = TopDisplayWidget()
        assert widget.border_title == "Preview"

    def test_update_focus_none_resets_title_to_preview(self):
        widget = TopDisplayWidget()
        with patch.object(widget, "remove_children"), patch.object(widget, "mount"):
            widget.update_focus(None, None)
        assert widget.border_title == "Preview"

    def test_update_focus_none_mounts_placeholder(self):
        widget = TopDisplayWidget()
        with patch.object(widget, "remove_children"), \
             patch.object(widget, "mount"), \
             patch("sample_manager.tui.widgets.top_display.Static") as mock_static:
            widget.update_focus(None, None)
        text = _all_static_texts(mock_static)
        assert "no sample focused" in text

    def test_update_focus_dir_sets_directory_title(self):
        widget = TopDisplayWidget()
        item = _nav_item("Kicks", is_dir=True)
        with patch.object(widget, "remove_children"), patch.object(widget, "mount"):
            widget.update_focus(item, None)
        assert widget.border_title == "Directory — Kicks"

    def test_update_focus_dir_mounts_dir_name(self):
        widget = TopDisplayWidget()
        item = _nav_item("Kicks", is_dir=True)
        with patch.object(widget, "remove_children"), \
             patch.object(widget, "mount"), \
             patch("sample_manager.tui.widgets.top_display.Static") as mock_static:
            widget.update_focus(item, None)
        text = _all_static_texts(mock_static)
        assert "Kicks/" in text

    def test_update_focus_file_no_details_sets_preview_title(self):
        widget = TopDisplayWidget()
        item = _nav_item("kick.wav", sample_id=None)
        with patch.object(widget, "remove_children"), patch.object(widget, "mount"):
            widget.update_focus(item, None)
        assert widget.border_title == "Preview — kick.wav"

    def test_update_focus_file_no_details_shows_not_indexed(self):
        widget = TopDisplayWidget()
        item = _nav_item("kick.wav", sample_id=None)
        with patch.object(widget, "remove_children"), \
             patch.object(widget, "mount"), \
             patch("sample_manager.tui.widgets.top_display.Static") as mock_static:
            widget.update_focus(item, None)
        text = _all_static_texts(mock_static)
        assert "not indexed" in text.lower()

    def test_update_focus_file_with_details_sets_preview_title(self):
        widget = TopDisplayWidget()
        item = _nav_item("kick.wav", sample_id=42)
        details = {"filename": "kick.wav", "ext": "wav", "size_bytes": 2048, "tags": []}
        with patch.object(widget, "remove_children"), patch.object(widget, "mount"):
            widget.update_focus(item, details)
        assert widget.border_title == "Preview — kick.wav"

    def test_update_focus_file_with_details_shows_size(self):
        widget = TopDisplayWidget()
        item = _nav_item("kick.wav", sample_id=42)
        details = {"filename": "kick.wav", "ext": "wav", "size_bytes": 2048, "tags": []}
        with patch.object(widget, "remove_children"), \
             patch.object(widget, "mount"), \
             patch("sample_manager.tui.widgets.top_display.Static") as mock_static:
            widget.update_focus(item, details)
        text = _all_static_texts(mock_static)
        assert "2 KB" in text

    def test_update_focus_file_with_details_shows_ext_uppercased(self):
        widget = TopDisplayWidget()
        item = _nav_item("kick.wav", sample_id=42)
        details = {"filename": "kick.wav", "ext": "wav", "size_bytes": 0, "tags": []}
        with patch.object(widget, "remove_children"), \
             patch.object(widget, "mount"), \
             patch("sample_manager.tui.widgets.top_display.Static") as mock_static:
            widget.update_focus(item, details)
        text = _all_static_texts(mock_static)
        assert "WAV" in text

    def test_update_focus_file_with_details_shows_tags(self):
        widget = TopDisplayWidget()
        item = _nav_item("kick.wav", sample_id=7)
        details = {"filename": "kick.wav", "ext": "wav", "size_bytes": 0, "tags": ["drums", "kick"]}
        with patch.object(widget, "remove_children"), \
             patch.object(widget, "mount"), \
             patch("sample_manager.tui.widgets.top_display.Static") as mock_static:
            widget.update_focus(item, details)
        text = _all_static_texts(mock_static)
        assert widget.metadata_panel.library_tags == ("drums", "kick")
        assert "Tags: drums · kick" in widget.metadata_panel._text.content

    def test_update_focus_file_with_details_shows_sample_id(self):
        widget = TopDisplayWidget()
        item = _nav_item("kick.wav", sample_id=99)
        details = {"filename": "kick.wav", "size_bytes": 0}
        with patch.object(widget, "remove_children"), \
             patch.object(widget, "mount"), \
             patch("sample_manager.tui.widgets.top_display.Static") as mock_static:
            widget.update_focus(item, details)
        text = _all_static_texts(mock_static)
        assert "#99" in text


# ---------------------------------------------------------------------------
# FiltersPanel
# ---------------------------------------------------------------------------


class TestFiltersPanel:
    """Tests for FiltersPanel.update_filter()."""

    def test_default_border_title_is_search(self):
        panel = FiltersPanel()
        assert panel.border_title == "Search"

    def test_default_query_is_empty(self):
        panel = FiltersPanel()
        assert panel._query == ""

    def test_update_filter_empty_string_resets_title(self):
        panel = FiltersPanel()
        mock_label = MagicMock()
        with patch.object(panel, "query_one", return_value=mock_label):
            panel.update_filter("")
        assert panel.border_title == "Search"

    def test_update_filter_empty_string_shows_placeholder(self):
        panel = FiltersPanel()
        mock_label = MagicMock()
        with patch.object(panel, "query_one", return_value=mock_label):
            panel.update_filter("")
        mock_label.update.assert_called_once_with("/ Search name, path, or tag")

    def test_update_filter_non_empty_updates_border_title(self):
        panel = FiltersPanel()
        mock_label = MagicMock()
        with patch.object(panel, "query_one", return_value=mock_label):
            panel.update_filter("kick")
        assert panel.border_title == "Search — kick"

    def test_update_filter_non_empty_includes_query_in_label(self):
        panel = FiltersPanel()
        mock_label = MagicMock()
        with patch.object(panel, "query_one", return_value=mock_label):
            panel.update_filter("drums")
        label_text = mock_label.update.call_args[0][0]
        assert "drums" in label_text

    def test_update_filter_stores_query_value(self):
        panel = FiltersPanel()
        mock_label = MagicMock()
        with patch.object(panel, "query_one", return_value=mock_label):
            panel.update_filter("snare")
        assert panel._query == "snare"

    def test_update_filter_empty_after_non_empty_resets_title(self):
        panel = FiltersPanel()
        mock_label = MagicMock()
        with patch.object(panel, "query_one", return_value=mock_label):
            panel.update_filter("hat")
        with patch.object(panel, "query_one", return_value=mock_label):
            panel.update_filter("")
        assert panel.border_title == "Search"
        assert panel._query == ""


# ---------------------------------------------------------------------------
# SessionSummaryWidget
# ---------------------------------------------------------------------------


class TestSessionSummaryWidget:
    """Tests for SessionSummaryWidget.update()."""

    def _mocks(self):
        return {
            "#sum-count": MagicMock(),
            "#sum-size": MagicMock(),
            "#sum-dest": MagicMock(),
        }

    def _patch_query(self, widget, mocks):
        def side_effect(selector, type_=None):
            return mocks[selector]
        return patch.object(widget, "query_one", side_effect=side_effect)

    def test_default_border_title_is_session(self):
        widget = SessionSummaryWidget()
        assert widget.border_title == "Session"

    def test_update_singular_count_uses_sample_without_s(self):
        widget = SessionSummaryWidget()
        mocks = self._mocks()
        with self._patch_query(widget, mocks):
            widget.update(1, 0, None)
        text = mocks["#sum-count"].update.call_args[0][0]
        assert "1 sample" in text
        assert "1 samples" not in text

    def test_update_plural_count_uses_samples(self):
        widget = SessionSummaryWidget()
        mocks = self._mocks()
        with self._patch_query(widget, mocks):
            widget.update(3, 0, None)
        text = mocks["#sum-count"].update.call_args[0][0]
        assert "3 samples" in text

    def test_update_zero_count_uses_samples(self):
        widget = SessionSummaryWidget()
        mocks = self._mocks()
        with self._patch_query(widget, mocks):
            widget.update(0, 0, None)
        text = mocks["#sum-count"].update.call_args[0][0]
        assert "0 samples" in text

    def test_update_size_formatted_in_kb(self):
        widget = SessionSummaryWidget()
        mocks = self._mocks()
        with self._patch_query(widget, mocks):
            widget.update(1, 2048, None)
        text = mocks["#sum-size"].update.call_args[0][0]
        assert "2 KB" in text

    def test_update_zero_size_shows_dash(self):
        widget = SessionSummaryWidget()
        mocks = self._mocks()
        with self._patch_query(widget, mocks):
            widget.update(0, 0, None)
        text = mocks["#sum-size"].update.call_args[0][0]
        assert "—" in text

    def test_update_none_destination_shows_no_profile_set(self):
        widget = SessionSummaryWidget()
        mocks = self._mocks()
        with self._patch_query(widget, mocks):
            widget.update(0, 0, None)
        text = mocks["#sum-dest"].update.call_args[0][0]
        assert "(no profile set)" in text

    def test_update_with_destination_string(self):
        widget = SessionSummaryWidget()
        mocks = self._mocks()
        with self._patch_query(widget, mocks):
            widget.update(2, 0, "/exports/my_set")
        text = mocks["#sum-dest"].update.call_args[0][0]
        assert "/exports/my_set" in text


# ---------------------------------------------------------------------------
# SelectedFilesListWidget
# ---------------------------------------------------------------------------


class TestSelectedFilesListWidget:
    """Tests for SelectedFilesListWidget.update()."""

    def test_default_border_title_shows_zero(self):
        widget = SelectedFilesListWidget()
        assert widget.border_title == "Stage · 0 · 0 B"

    def test_update_empty_list_keeps_zero_in_title(self):
        widget = SelectedFilesListWidget()
        with patch.object(widget, "remove_children"), \
             patch.object(widget, "mount"), \
             patch("sample_manager.tui.widgets.selection_list.Static"):
            widget.update([])
        assert widget.border_title == "Stage · 0 · 0 B"

    def test_update_empty_list_mounts_hint(self):
        widget = SelectedFilesListWidget()
        with patch.object(widget, "remove_children"), \
             patch.object(widget, "mount"), \
             patch("sample_manager.tui.widgets.selection_list.Static") as mock_static:
            widget.update([])
        text = _all_static_texts(mock_static)
        assert "No samples selected" in text

    def test_update_non_empty_list_reflects_count_in_title(self):
        widget = SelectedFilesListWidget()
        items = [{"filename": "kick.wav"}, {"filename": "snare.wav"}]
        with patch.object(widget, "remove_children"), \
             patch.object(widget, "mount"), \
             patch("sample_manager.tui.widgets.selection_list.Static"):
            widget.update(items)
        assert widget.border_title == "Stage · 2 · 0 B"

    def test_update_non_empty_list_mounts_filenames(self):
        widget = SelectedFilesListWidget()
        items = [{"filename": "kick.wav"}, {"filename": "snare.wav"}]
        with patch.object(widget, "remove_children"), \
             patch.object(widget, "mount"), \
             patch("sample_manager.tui.widgets.selection_list.Static") as mock_static:
            widget.update(items)
        text = _all_static_texts(mock_static)
        assert "kick.wav" in text
        assert "snare.wav" in text

    def test_update_item_missing_filename_key_shows_question_mark(self):
        widget = SelectedFilesListWidget()
        items = [{}]  # no "filename" key
        with patch.object(widget, "remove_children"), \
             patch.object(widget, "mount"), \
             patch("sample_manager.tui.widgets.selection_list.Static") as mock_static:
            widget.update(items)
        text = _all_static_texts(mock_static)
        assert "?" in text


# ---------------------------------------------------------------------------
# SampleListWidget — message classes
# ---------------------------------------------------------------------------


class TestSampleListWidgetMessages:
    """CursorMoved and ItemActivated are plain Python message objects."""

    def test_cursor_moved_carries_item(self):
        item = _nav_item("kick.wav", sample_id=1)
        msg = SampleListWidget.CursorMoved(item)
        assert msg.item is item

    def test_item_activated_carries_item(self):
        item = _nav_item("Kicks", is_dir=True)
        msg = SampleListWidget.ItemActivated(item)
        assert msg.item is item

    def test_cursor_moved_item_attribute_matches_nav_item_name(self):
        item = _nav_item("snare.wav", sample_id=5)
        msg = SampleListWidget.CursorMoved(item)
        assert msg.item.name == "snare.wav"

    def test_item_activated_item_attribute_matches_nav_item_path(self):
        item = _nav_item("hat.wav")
        msg = SampleListWidget.ItemActivated(item)
        assert msg.item.path == Path("/root/hat.wav")

    def test_file_tree_widget_is_alias_for_sample_list_widget(self):
        assert FileTreeWidget is SampleListWidget


# ---------------------------------------------------------------------------
# CSS parse smoke test
# ---------------------------------------------------------------------------


class TestCSS:
    """Parse styles/app.tcss against real Textual theme variables.

    This test catches CSS property errors (e.g. invalid border color tokens
    like `border: solid $text`) that only surface at app startup, not during
    widget construction.  By parsing the file directly with Textual's own
    parser — supplied with theme variables resolved from the default App theme
    — any `rs.errors` entry becomes a hard test failure.

    Why parse-time errors were invisible before:
    The widget-level tests mock out DOM methods and never instantiate a real
    Textual App, so CSS is never loaded or validated.  This test closes that
    gap without requiring a running terminal or async machinery.
    """

    def _parse_tcss(self, css_text: str) -> list[tuple[str, str]]:
        """Return a list of (token_repr, message) error tuples from parsing css_text."""
        from textual.app import App
        from textual.css.parse import parse, tokenize_values

        app = App()
        theme = app.current_theme
        variables = theme.to_color_system().generate()
        var_tokens = tokenize_values(variables)

        location = ("app.tcss", "app.tcss")
        rule_sets = list(parse("", css_text, location, variable_tokens=var_tokens))
        errors = []
        for rs in rule_sets:
            for token, message in rs.errors:
                errors.append((str(token), str(message)))
        return errors

    def test_app_tcss_file_exists(self):
        from pathlib import Path
        tcss = Path(__file__).parent.parent / "src/sample_manager/tui/styles/app.tcss"
        assert tcss.exists(), f"styles/app.tcss not found at {tcss}"

    def test_app_tcss_has_no_parse_errors(self):
        """Catch any CSS property errors — e.g. invalid border color tokens.

        A past regression: `border: solid $text` was reported as invalid by
        Textual at startup.  This test would have caught that before deployment.
        """
        from pathlib import Path
        tcss = Path(__file__).parent.parent / "src/sample_manager/tui/styles/app.tcss"
        css_text = tcss.read_text()
        errors = self._parse_tcss(css_text)
        assert errors == [], (
            "CSS parse errors found in styles/app.tcss:\n"
            + "\n".join(f"  {msg}" for _, msg in errors)
        )

    def test_border_solid_dollar_text_is_detected_as_invalid(self):
        """Regression guard: confirm the parser rejects `border: solid $text`.

        This documents the exact failure mode that was previously invisible.
        If this test starts failing, Textual may have made $text valid for
        borders — which would be fine to handle by updating this test.
        """
        css = "Widget { border: solid $text; }"
        errors = self._parse_tcss(css)
        assert len(errors) > 0, (
            "Expected a parse error for 'border: solid $text' but none was raised. "
            "If Textual now allows $text as a border color, update this guard test."
        )
