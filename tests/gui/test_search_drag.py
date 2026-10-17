"""Offscreen interaction tests for library search, transport, and Stage drops."""

from pathlib import Path
from unittest.mock import Mock

from PySide6.QtCore import QCoreApplication, QMimeData, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from sample_manager.audio.player import PlaybackSnapshot, PlaybackStatus
from sample_manager.gui.app import create_main_window
from sample_manager.gui.drag import sample_id_from_mime
from sample_manager.gui.models.browser_model import SampleIdRole
from sample_manager.gui.models.selection_model import SampleIdRole as StageSampleIdRole
from sample_manager.scanner import scan_library


def _window(populated_service, qtbot, *, player=None):
    """Open a real Qt window backed by the fixture's indexed sample library."""
    service, root = populated_service
    window = create_main_window(service, player=player)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window, root


def test_root_search_finds_nested_substring_and_restores_directory(populated_service, qtbot):
    """Search from the root finds a file whose name contains the query."""
    window, root = _window(populated_service, qtbot)

    window.browser.filter_field.setText("NAR")
    assert window.browser.proxy.rowCount() == 1
    assert window.browser.current_data(SampleIdRole) is None
    result = window.browser.proxy.index(0, 0)
    assert result.data(Qt.ItemDataRole.DisplayRole) == "snare.wav — drums"
    assert window.controller.current_path == root

    window.browser.filter_field.setFocus()
    qtbot.keyClick(window.browser.filter_field, Qt.Key.Key_Return)
    assert window.browser.current_data(SampleIdRole) is not None
    assert not window.browser.filter_has_focus()

    window.browser.clear_filter()
    assert window.browser.proxy.rowCount() == 1
    assert window.browser.current_index().data(Qt.ItemDataRole.DisplayRole) == "drums"


def test_scanned_wave_sample_is_searchable_in_gui(populated_service, browser_db, qtbot):
    """A newly scanned .wave file appears in root-wide GUI search results."""
    service, root = populated_service
    sample = root / "drums" / "FL_FDS_09_Drum_Loop_Full_98.wave"
    sample.write_bytes(b"RIFF")
    scan_library(browser_db, root, fast=True)
    window, _ = _window((service, root), qtbot)

    window.browser.filter_field.setText("Drum")

    # Folder-name hits may also appear; the filename hit is ranked first.
    assert window.browser.proxy.rowCount() == 3
    assert window.browser.proxy.index(0, 0).data(Qt.ItemDataRole.DisplayRole) == (
        "FL_FDS_09_Drum_Loop_Full_98.wave — drums"
    )


def test_space_controls_playback_inside_search_and_shift_space_types(populated_service, qtbot):
    """Search typing cannot capture transport Space; Shift+Space remains text."""
    player = Mock()
    player.snapshot.return_value = PlaybackSnapshot(
        PlaybackStatus.PLAYING, Path("/tmp/current.wav"), 1.0, 2.0, None
    )
    window, _root = _window(populated_service, qtbot, player=player)
    field = window.browser.filter_field
    field.setFocus()
    qtbot.keyClicks(field, "drum")
    assert player.play.call_count == 0

    qtbot.keyClick(field, Qt.Key.Key_Space)
    assert player.pause.call_count == 1
    assert field.text() == "drum"

    qtbot.keyClick(field, Qt.Key.Key_Space, Qt.KeyboardModifier.ShiftModifier)
    assert field.text() == "drum "


def test_escape_exits_empty_search_field(populated_service, qtbot):
    """Escape frees browser shortcuts even before a query is typed."""
    window, _root = _window(populated_service, qtbot)
    field = window.browser.filter_field
    field.setFocus()

    qtbot.keyClick(field, Qt.Key.Key_Escape)

    assert not field.hasFocus()
    assert field.text() == ""


def test_browser_drag_payload_drops_into_stage(populated_service, qtbot):
    """A search result's real Qt MIME payload adds a sample through Stage."""
    window, _root = _window(populated_service, qtbot)
    window.browser.filter_field.setText("nar")
    browser = window.browser.view
    index = browser.model().index(0, 0)
    sample_id = index.data(SampleIdRole)
    assert index.flags() & Qt.ItemFlag.ItemIsDragEnabled
    mime = browser.model().mimeData([index])
    assert sample_id_from_mime(mime) == sample_id

    stage = window.selection.view
    enter = QDragEnterEvent(
        QPoint(4, 4), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QCoreApplication.sendEvent(stage.viewport(), enter)
    assert enter.isAccepted()
    drop = QDropEvent(
        QPointF(4, 4), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QCoreApplication.sendEvent(stage.viewport(), drop)

    assert drop.isAccepted()
    assert window.controller.selection_summary().count == 1
    assert window.selection.view.model().index(0, 0).data(StageSampleIdRole) == sample_id

    # Stage uses idempotent selection membership, even if the same row is dropped twice.
    QCoreApplication.sendEvent(stage.viewport(), drop)
    assert window.controller.selection_summary().count == 1


def test_stage_rejects_non_sample_and_unknown_sample_drops(populated_service, qtbot):
    """A Stage drop cannot add arbitrary text or a stale sample ID."""
    window, _root = _window(populated_service, qtbot)
    stage = window.selection.view
    text_mime = QMimeData()
    text_mime.setText("not a sample")
    invalid = QDragEnterEvent(
        QPoint(4, 4), Qt.DropAction.CopyAction, text_mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QCoreApplication.sendEvent(stage.viewport(), invalid)
    assert not invalid.isAccepted()

    from sample_manager.gui.drag import sample_mime

    unknown_mime = sample_mime(999999)
    unknown = QDropEvent(
        QPointF(4, 4), Qt.DropAction.CopyAction, unknown_mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QCoreApplication.sendEvent(stage.viewport(), unknown)
    assert window.controller.selection_summary().count == 0


def test_open_in_file_manager_opens_containing_folder(populated_service, qtbot, monkeypatch):
    """The browser action opens a real folder URL instead of printing a stub."""
    window, root = _window(populated_service, qtbot)
    opened = []
    monkeypatch.setattr(
        "sample_manager.gui.main_window.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )

    window._on_open_externally(str(root / "drums" / "kick.wav"))

    # Qt serializes Windows file URLs with forward slashes.
    assert [Path(path) for path in opened] == [root / "drums"]
