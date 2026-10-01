"""Tests for BrowserListModel and the filter proxy."""

from pathlib import Path

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt

from sample_manager.gui.models.browser_model import (
    BrowserListModel,
    IsDirRole,
    IsSelectedRole,
    MetaRole,
    PathRole,
    SampleIdRole,
)
from sample_manager.services.library_browser import BrowserItem


def _items():
    return (
        BrowserItem(name="drums", path=Path("/lib/drums"), is_dir=True, sample_id=None, is_selected=False),
        BrowserItem(name="kick.wav", path=Path("/lib/kick.wav"), is_dir=False, sample_id=1, is_selected=True),
        BrowserItem(name="snare.wav", path=Path("/lib/snare.wav"), is_dir=False, sample_id=2, is_selected=False),
    )


def test_row_count():
    model = BrowserListModel(_items())
    assert model.rowCount() == 3
    # Valid parent yields 0 (flat list).
    assert model.rowCount(model.index(0, 0)) == 0


def test_role_values():
    model = BrowserListModel(_items())

    dir_idx = model.index(0, 0)
    assert model.data(dir_idx, Qt.ItemDataRole.DisplayRole) == "drums"
    assert model.data(dir_idx, IsDirRole) is True
    assert model.data(dir_idx, SampleIdRole) is None
    assert model.data(dir_idx, MetaRole) == ""

    file_idx = model.index(1, 0)
    assert model.data(file_idx, Qt.ItemDataRole.DisplayRole) == "kick.wav"
    assert model.data(file_idx, IsDirRole) is False
    assert model.data(file_idx, SampleIdRole) == 1
    assert model.data(file_idx, IsSelectedRole) is True
    assert model.data(file_idx, PathRole) == str(Path("/lib/kick.wav"))
    assert model.data(file_idx, MetaRole) == "WAV"


def test_invalid_index_returns_none():
    model = BrowserListModel(_items())
    assert model.data(QModelIndex(), Qt.ItemDataRole.DisplayRole) is None


def test_reset_with_emits_reset(qtbot):
    model = BrowserListModel()
    assert model.rowCount() == 0
    with qtbot.waitSignal(model.modelReset):
        model.reset_with(_items())
    assert model.rowCount() == 3


def test_update_selection_toggles_flag():
    model = BrowserListModel(_items())
    # Initially only sample 1 is selected.
    model.update_selection({2})
    assert model.data(model.index(1, 0), IsSelectedRole) is False
    assert model.data(model.index(2, 0), IsSelectedRole) is True


def test_refresh_item_emits_data_changed(qtbot):
    model = BrowserListModel(_items())
    with qtbot.waitSignal(model.dataChanged):
        model.refresh_item(1)


def test_proxy_prefix_filter():
    model = BrowserListModel(_items())
    proxy = QSortFilterProxyModel()
    proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    proxy.setSourceModel(model)

    # Case-insensitive prefix on "sn" matches only snare.wav.
    proxy.setFilterRegularExpression("^SN")
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 0), Qt.ItemDataRole.DisplayRole) == "snare.wav"

    proxy.setFilterFixedString("")
    assert proxy.rowCount() == 3
