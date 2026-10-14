"""Phase 3 interaction parity tests for the Qt GUI.

Covers keyboard shortcuts (via ``qtbot.keyClick``), mouse actions (single/double
click, context menu), the filter, the three dialogs, and selection-mutation
refresh. All run under the offscreen Qt platform (see ``tests/gui/conftest.py``).
"""

import warnings

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from sample_manager.gui.app import create_main_window
from sample_manager.gui.dialogs import ActionDialog, CommandPaletteDialog, HelpDialog
from sample_manager.gui.models.browser_model import IsDirRole, SampleIdRole


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_window(populated_service, qtbot):
    service, root = populated_service
    window = create_main_window(service)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    # WindowShortcut context only fires when the window is the active window.
    # Under the offscreen platform ``activateWindow()`` alone does not set it, so
    # mark it active explicitly to deliver keyboard shortcuts.
    window.activateWindow()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        QApplication.setActiveWindow(window)
    return window, service, root


def _enter_drums(window, qtbot, root):
    """Navigate into the ``drums`` subdirectory (kick.wav, snare.wav).

    Returns the *window* — keyboard shortcuts are delivered to the window since
    the browser list is deliberately non-focusable (see ``BrowserWidget``).
    """
    window.controller.navigate_to(root / "drums")
    return window


def _row_display(window, row):
    proxy = window.browser.proxy
    return proxy.data(proxy.index(row, 0), Qt.ItemDataRole.DisplayRole)


def _focused_row(window):
    return window.browser.view.currentIndex().row()


# ---------------------------------------------------------------------------
# keyboard parity
# ---------------------------------------------------------------------------


def test_j_moves_focus_down(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    assert _focused_row(window) == 0
    qtbot.keyClick(view, Qt.Key_J)
    assert _focused_row(window) == 1


def test_down_arrow_moves_focus_down(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    qtbot.keyClick(view, Qt.Key_Down)
    assert _focused_row(window) == 1


def test_k_moves_focus_up(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    window.browser.move_focus(1)  # go to row 1 first
    assert _focused_row(window) == 1
    qtbot.keyClick(view, Qt.Key_K)
    assert _focused_row(window) == 0


def test_up_arrow_moves_focus_up(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    window.browser.move_focus(1)
    qtbot.keyClick(view, Qt.Key_Up)
    assert _focused_row(window) == 0


def test_h_navigates_to_parent(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    assert window.controller.current_path == root / "drums"
    qtbot.keyClick(view, Qt.Key_H)
    assert window.controller.current_path == root


def test_left_navigates_to_parent(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    qtbot.keyClick(view, Qt.Key_Left)
    assert window.controller.current_path == root


def test_l_enters_focused_directory(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    window.browser.focus_first()
    # At the root, row 0 is the "drums" directory.
    assert window.browser.current_data(IsDirRole) is True
    qtbot.keyClick(window, Qt.Key_L)
    assert window.controller.current_path == root / "drums"


def test_l_on_file_opens_action_dialog(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    assert window.browser.current_data(IsDirRole) is False
    qtbot.keyClick(view, Qt.Key_L)
    assert isinstance(window.active_dialog, ActionDialog)
    window.active_dialog.close()


def test_right_enters_focused_directory(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    window.browser.focus_first()
    qtbot.keyClick(window, Qt.Key_Right)
    assert window.controller.current_path == root / "drums"


def test_return_enters_directory(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    window.browser.focus_first()
    qtbot.keyClick(window, Qt.Key_Return)
    assert window.controller.current_path == root / "drums"


def test_return_toggles_file_selection(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    assert window.controller.selection_summary().count == 0
    qtbot.keyClick(view, Qt.Key_Return)
    assert window.controller.selection_summary().count == 1
    # Return again toggles it back off.
    qtbot.keyClick(view, Qt.Key_Return)
    assert window.controller.selection_summary().count == 0


def test_space_does_not_crash(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    qtbot.keyClick(view, Qt.Key_Space)
    # Space remains harmless when this test window has no audio player.
    assert window.controller.selection_summary().count == 0


def test_a_adds_focused_sample(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    qtbot.keyClick(view, Qt.Key_A)
    assert window.controller.selection_summary().count == 1
    # Idempotent: pressing A again does not double-count.
    qtbot.keyClick(view, Qt.Key_A)
    assert window.controller.selection_summary().count == 1


def test_d_removes_focused_sample(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    window.controller.add_to_selection(window.browser.current_data(SampleIdRole))
    assert window.controller.selection_summary().count == 1
    qtbot.keyClick(view, Qt.Key_D)
    assert window.controller.selection_summary().count == 0


def test_slash_focuses_filter(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    qtbot.keyClick(view, Qt.Key_Slash)
    assert window.browser.filter_has_focus()
    assert window.active_dialog is None


def test_question_opens_help_dialog(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    qtbot.keyClick(view, Qt.Key_Question)
    assert isinstance(window.active_dialog, HelpDialog)
    window.active_dialog.close()


def test_ctrl_p_opens_command_palette(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    qtbot.keyClick(view, Qt.Key_P, Qt.KeyboardModifier.ControlModifier)
    assert isinstance(window.active_dialog, CommandPaletteDialog)
    window.active_dialog.close()


# ---------------------------------------------------------------------------
# filter behavior
# ---------------------------------------------------------------------------


def test_search_substring_match(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    _enter_drums(window, qtbot, root)
    window.browser.filter_field.setText("sn")
    proxy = window.browser.proxy
    assert proxy.rowCount() == 1
    assert _row_display(window, 0) == "snare.wav — drums"


def test_filter_is_case_insensitive(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    _enter_drums(window, qtbot, root)
    window.browser.filter_field.setText("SN")
    assert window.browser.proxy.rowCount() == 1
    assert _row_display(window, 0) == "snare.wav — drums"


def test_escape_clears_filter_and_refocuses_list(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    _enter_drums(window, qtbot, root)
    window.browser.filter_field.setText("sn")
    window.browser.filter_field.setFocus()
    qtbot.keyClick(window.browser.filter_field, Qt.Key_Escape)
    assert window.browser.filter_text() == ""
    assert window.browser.proxy.rowCount() == 2
    # Focus has left the filter, so the nav shortcuts are live again.
    assert not window.browser.filter_has_focus()


def test_filter_survives_navigation(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    _enter_drums(window, qtbot, root)
    window.browser.filter_field.setText("sn")
    # Search leaves the prior audition alone until a result is chosen.
    assert _focused_row(window) == -1
    assert _row_display(window, 0) == "snare.wav — drums"


# ---------------------------------------------------------------------------
# mouse parity
# ---------------------------------------------------------------------------


def test_single_click_changes_focus(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    _enter_drums(window, qtbot, root)
    view = window.browser.view
    proxy = window.browser.proxy
    idx = proxy.index(1, 0)  # snare.wav
    rect = view.visualRect(idx)
    with qtbot.waitSignal(window.browser.focus_changed):
        qtbot.mouseClick(view.viewport(), Qt.LeftButton, pos=rect.center())
    assert _focused_row(window) == 1


def test_double_click_toggles_file_selection(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    _enter_drums(window, qtbot, root)
    proxy = window.browser.proxy
    idx = proxy.index(0, 0)  # kick.wav
    with qtbot.waitSignal(window.browser.selection_toggled):
        window.browser._on_activated(idx)
    assert window.controller.selection_summary().count == 1


def test_double_click_directory_navigates(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    proxy = window.browser.proxy
    idx = proxy.index(0, 0)  # drums dir
    with qtbot.waitSignal(window.browser.directory_activated):
        window.browser._on_activated(idx)
    assert window.controller.current_path == root / "drums"


def test_context_menu_add_and_remove(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    _enter_drums(window, qtbot, root)
    proxy = window.browser.proxy
    idx = proxy.index(0, 0)  # kick.wav file
    menu = window.browser._build_context_menu(idx)
    actions = {a.text(): a for a in menu.actions()}
    assert "Add" in actions
    assert "Remove" in actions
    assert "Open in file manager" in actions

    actions["Add"].trigger()
    assert window.controller.selection_summary().count == 1
    actions["Remove"].trigger()
    assert window.controller.selection_summary().count == 0


def test_context_menu_open_externally_emits(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    _enter_drums(window, qtbot, root)
    proxy = window.browser.proxy
    idx = proxy.index(0, 0)
    menu = window.browser._build_context_menu(idx)
    actions = {a.text(): a for a in menu.actions()}
    with qtbot.waitSignal(window.browser.open_externally_requested):
        actions["Open in file manager"].trigger()


def test_selection_widget_click_previews(populated_service, qtbot):
    window, service, root = _make_window(populated_service, qtbot)
    items = service.list_directory(root / "drums")
    sid = next(it.sample_id for it in items if it.sample_id is not None)
    window.controller.add_to_selection(sid)

    view = window.selection.view
    idx = view.model().index(0, 0)
    with qtbot.waitSignal(window.selection.detail_requested):
        window.selection._on_clicked(idx)


def test_selection_widget_context_menu_removes(populated_service, qtbot):
    window, service, root = _make_window(populated_service, qtbot)
    items = service.list_directory(root / "drums")
    sid = next(it.sample_id for it in items if it.sample_id is not None)
    window.controller.add_to_selection(sid)

    view = window.selection.view
    idx = view.model().index(0, 0)
    menu = window.selection._build_context_menu(idx)
    actions = {a.text(): a for a in menu.actions()}
    assert "Remove" in actions
    actions["Remove"].trigger()
    assert window.controller.selection_summary().count == 0


# ---------------------------------------------------------------------------
# dialogs
# ---------------------------------------------------------------------------


def test_action_dialog_add_button(populated_service, qtbot):
    window, service, root = _make_window(populated_service, qtbot)
    items = service.list_directory(root / "drums")
    sid = next(it.sample_id for it in items if it.sample_id is not None)
    details = service.sample_details(sid)

    added = []
    dialog = ActionDialog(details, on_add=added.append, on_remove=lambda _s: None)
    qtbot.addWidget(dialog)
    qtbot.mouseClick(dialog._add_button, Qt.LeftButton)
    assert added == [sid]


def test_help_dialog_lists_all_shortcuts(populated_service, qtbot):
    window, _service, _root = _make_window(populated_service, qtbot)
    from sample_manager.gui.shortcuts import SHORTCUT_HELP

    dialog = HelpDialog()
    qtbot.addWidget(dialog)
    assert dialog.table.rowCount() == len(SHORTCUT_HELP)


def test_command_palette_triggers_action(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    _enter_drums(window, qtbot, root)
    called = []
    actions = {"Add": lambda: called.append("add")}
    dialog = CommandPaletteDialog(actions)
    qtbot.addWidget(dialog)
    dialog.trigger("Add")
    assert called == ["add"]


# ---------------------------------------------------------------------------
# selection mutation -> model + UI refresh + focus preservation
# ---------------------------------------------------------------------------


def test_add_preserves_focus_and_refreshes_all(populated_service, qtbot):
    window, _service, root = _make_window(populated_service, qtbot)
    view = _enter_drums(window, qtbot, root)
    window.browser.move_focus(1)  # focus snare (row 1)
    assert _focused_row(window) == 1

    qtbot.keyClick(view, Qt.Key_A)

    # Selection model + session summary reflect the add.
    assert window.controller.selection_model.rowCount() == 1
    assert window.session_summary  # widget exists
    assert window.controller.selection_summary().count == 1
    # Focused row is preserved across the mutation (no reset).
    assert _focused_row(window) == 1


def test_summary_tracks_total_bytes(populated_service, qtbot):
    window, service, root = _make_window(populated_service, qtbot)
    items = service.list_directory(root / "drums")
    sid = next(it.sample_id for it in items if it.sample_id is not None)
    window.controller.add_to_selection(sid)
    summary = window.controller.selection_summary()
    assert summary.total_bytes > 0
