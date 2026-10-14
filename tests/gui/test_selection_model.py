"""Tests for SelectionListModel backed by a real LibraryBrowserService."""

from PySide6.QtCore import Qt

from sample_manager.gui.models.selection_model import (
    PathRole,
    SampleIdRole,
    SelectionListModel,
)


def test_empty_by_default(populated_service):
    service, _root = populated_service
    model = SelectionListModel(service)
    model.reset_from_service()
    assert model.rowCount() == 0


def test_reset_after_toggle(populated_service):
    service, root = populated_service
    items = service.list_directory(root / "drums")
    sample_ids = [it.sample_id for it in items if it.sample_id is not None]
    assert sample_ids, "fixture should have indexed samples"

    model = SelectionListModel(service)
    model.reset_from_service()
    assert model.rowCount() == 0

    service.add_to_selection(sample_ids[0])
    model.reset_from_service()
    assert model.rowCount() == 1


def test_role_values(populated_service):
    service, root = populated_service
    items = service.list_directory(root / "drums")
    sid = next(it.sample_id for it in items if it.sample_id is not None)
    service.add_to_selection(sid)

    model = SelectionListModel(service)
    model.reset_from_service()

    idx = model.index(0, 0)
    assert model.data(idx, Qt.ItemDataRole.DisplayRole)  # a filename string
    assert model.data(idx, SampleIdRole) == sid
    # PathRole is the rel_path (may be a relative string).
    assert model.data(idx, PathRole) is not None


def test_reset_reflects_removal(populated_service):
    service, root = populated_service
    items = service.list_directory(root / "drums")
    ids = [it.sample_id for it in items if it.sample_id is not None]
    for sid in ids:
        service.add_to_selection(sid)

    model = SelectionListModel(service)
    model.reset_from_service()
    assert model.rowCount() == len(ids)

    service.remove_from_selection(ids[0])
    model.reset_from_service()
    assert model.rowCount() == len(ids) - 1
