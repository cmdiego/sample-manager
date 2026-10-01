"""Tests that the MainWindow opens and presents the four zones."""

from sample_manager.gui.app import create_main_window
from sample_manager.gui.controller import BrowserController
from sample_manager.gui.main_window import MainWindow
from sample_manager.gui.widgets.browser import BrowserWidget
from sample_manager.gui.widgets.preview import PreviewWidget
from sample_manager.gui.widgets.selection import SelectionWidget
from sample_manager.gui.widgets.session_summary import SessionSummaryWidget
from PySide6.QtWidgets import QLabel


def test_window_opens_without_crash(populated_service, qtbot):
    service, _root = populated_service
    window = create_main_window(service)
    qtbot.addWidget(window)
    window.show()
    assert window.isVisible()


def test_window_title(populated_service, qtbot):
    service, _root = populated_service
    window = create_main_window(service)
    qtbot.addWidget(window)
    assert window.windowTitle() == "Sample Manager"


def test_four_zones_present(populated_service, qtbot):
    service, _root = populated_service
    window = create_main_window(service)
    qtbot.addWidget(window)

    assert isinstance(window.preview, PreviewWidget)
    assert isinstance(window.session_summary, SessionSummaryWidget)
    assert isinstance(window.browser, BrowserWidget)
    assert isinstance(window.selection, SelectionWidget)


def test_stage_labels_are_user_facing(populated_service, qtbot):
    service, _root = populated_service
    window = create_main_window(service)
    qtbot.addWidget(window)

    selection_heading = window.selection.findChild(QLabel, "SelectionHeading")
    summary_heading = window.session_summary.findChild(QLabel, "SessionHeading")
    assert selection_heading.text() == "Stage"
    assert summary_heading.text() == "Stage Summary"


def test_root_loaded_populates_browser(populated_service, qtbot):
    service, root = populated_service
    window = create_main_window(service)
    qtbot.addWidget(window)

    # The first library root's top-level dir has a "drums" subdirectory.
    assert window.controller.current_path == root
    assert window.controller.browser_model.rowCount() >= 1


def test_toggle_selection_updates_summary(populated_service, qtbot):
    service, root = populated_service
    window = create_main_window(service)
    qtbot.addWidget(window)

    items = service.list_directory(root / "drums")
    sid = next(it.sample_id for it in items if it.sample_id is not None)

    window.controller.toggle_selection(sid)
    assert window.controller.selection_model.rowCount() == 1
    assert window.controller.selection_summary().count == 1


def test_navigate_and_up(populated_service, qtbot):
    service, root = populated_service
    controller = BrowserController(service)
    root_dto = controller.library_roots()[0]
    controller.load_root(root_dto)

    controller.navigate_to(root / "drums")
    assert controller.current_path == root / "drums"

    controller.navigate_up()
    assert controller.current_path == root

    # Cannot climb above the root.
    controller.navigate_up()
    assert controller.current_path == root
