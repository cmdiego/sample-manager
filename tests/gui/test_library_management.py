"""Offscreen checks for library selection and background GUI indexing."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QComboBox, QFileDialog

from sample_manager.db import Db
from sample_manager.gui.app import _record_selected_root, create_main_window
from sample_manager.migrations import apply_migrations
from sample_manager.scanner import scan_library
from sample_manager.services.library_browser import LibraryBrowserService


@pytest.fixture
def library_setup(qtbot, tmp_path):
    """Use a file-backed DB so a Qt scan worker can open its own connection."""
    db = Db(tmp_path / "library.sqlite3")
    db.connect()
    apply_migrations(db)
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "kick.wav").write_bytes(b"RIFF0000")
    (second / "snare.wav").write_bytes(b"RIFF1111")
    scan_library(db, first)
    service = LibraryBrowserService(db)
    window = create_main_window(service)
    qtbot.addWidget(window)
    yield window, service, first, second
    window.close()
    db.close()


def _wait_for_scan(qtbot, window) -> None:
    """Wait for both the worker result and its cleanup signal."""
    qtbot.waitUntil(lambda: window._scan_worker is None, timeout=5000)


def test_add_folder_scans_and_switches_without_blocking(library_setup, qtbot, monkeypatch):
    """The Add action remains usable when a second folder is not yet indexed."""
    window, service, first, second = library_setup
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", lambda *_args: str(second)
    )

    window._add_library_action.trigger()
    assert window._scan_worker is not None
    assert not window._root_picker.isEnabled()
    _wait_for_scan(qtbot, window)

    assert window.controller.current_path == second
    assert [root.path for root in service.library_roots()] == [first, second]
    assert window._root_picker.count() == 2
    assert service.search_samples(window.controller.current_root, "snare")
    assert "1 new" in window.statusBar().currentMessage()


def test_switching_roots_clears_old_search_and_records_preference(library_setup, qtbot):
    """A chosen root replaces both the visible rows and search scope."""
    window, service, first, second = library_setup
    window._start_scan(second)
    _wait_for_scan(qtbot, window)
    recorded: list[Path] = []
    window._on_library_selected = recorded.append
    window.browser.filter_field.setText("snare")
    picker = window.findChild(QComboBox, "LibraryRootPicker")
    picker.setCurrentIndex(0)

    assert window.controller.current_path == first
    assert window.controller.current_root.path == first
    assert window.browser.filter_text() == ""
    assert recorded == [first]
    assert not service.search_samples(window.controller.current_root, "snare")


def test_rescan_updates_search_and_prunes_missing_files(library_setup, qtbot):
    """Rescan refreshes indexed results while keeping the current root."""
    window, service, first, _second = library_setup
    (first / "kick.wav").unlink()
    (first / "hihat.wave").write_bytes(b"RIFF2222")
    window.browser.filter_field.setText("hihat")

    window._rescan_action.trigger()
    _wait_for_scan(qtbot, window)

    assert window.controller.current_root.path == first
    assert window.browser.filter_text() == "hihat"
    assert len(service.search_samples(window.controller.current_root, "hihat")) == 1
    assert not service.search_samples(window.controller.current_root, "kick")
    assert "1 removed" in window.statusBar().currentMessage()


def test_failed_scan_keeps_existing_library_usable(library_setup, qtbot, monkeypatch):
    """An indexing error restores controls and leaves the browser intact."""
    window, service, first, second = library_setup

    def fail_scan(_path: Path):
        """Simulate an I/O failure from the worker connection."""
        raise OSError("read failed")

    monkeypatch.setattr(service, "scan_directory", fail_scan)
    window._start_scan(second)
    _wait_for_scan(qtbot, window)

    assert window.controller.current_root.path == first
    assert window._root_picker.isEnabled()
    assert window._add_library_action.isEnabled()
    assert "read failed" in window._status_error.text()


def test_missing_library_does_not_leave_picker_on_wrong_root(library_setup, qtbot):
    """A stale DB root cannot make the picker disagree with the browser."""
    window, _service, first, second = library_setup
    window._start_scan(second)
    _wait_for_scan(qtbot, window)
    window._root_picker.setCurrentIndex(0)
    (second / "snare.wav").unlink()
    second.rmdir()

    window._root_picker.setCurrentIndex(1)

    assert window.controller.current_root.path == first
    assert window._root_picker.currentIndex() == 0
    assert "missing" in window._status_error.text()


def test_configured_default_root_opens_first(library_setup, qtbot):
    """Startup honors the chosen default when multiple roots are indexed."""
    _window, service, _first, second = library_setup
    service.scan_directory(second)
    preferred = create_main_window(service, preferred_root_path=second)
    qtbot.addWidget(preferred)

    assert preferred.controller.current_root.path == second
    assert preferred._root_picker.currentData() == preferred.controller.current_root.id


def test_real_gui_root_preference_updates_config(tmp_path, monkeypatch):
    """The real entry-point callback keeps the CLI default in sync."""
    from sample_manager import config

    config_path = tmp_path / "config.yaml"
    root = tmp_path / "samples"
    root.mkdir()
    config.save_config(config.get_default_config_template(), config_path)
    monkeypatch.setattr(config, "get_config_path", lambda: config_path)

    _record_selected_root(root)
    saved = config.load_config(config_path)
    assert saved["library_roots"] == [str(root)]
    assert saved["default_library_root"] == str(root)
