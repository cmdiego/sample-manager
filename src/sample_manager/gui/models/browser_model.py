"""``BrowserListModel`` — a ``QAbstractListModel`` over ``BrowserItem`` DTOs.

The model holds an immutable tuple of ``BrowserItem`` rows produced by
``LibraryBrowserService.list_directory()``. It exposes typed roles so views and
delegates can render the entry name, discover whether a row is a directory, and
reflect the persistent-selection state without ever touching the database.

No SQL and no DB access live here — data arrives pre-built from the service via
the controller.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from ...services.library_browser import BrowserItem

# Custom roles. Qt.UserRole is the first value safe for application use.
PathRole = Qt.ItemDataRole.UserRole + 1
IsDirRole = Qt.ItemDataRole.UserRole + 2
SampleIdRole = Qt.ItemDataRole.UserRole + 3
IsSelectedRole = Qt.ItemDataRole.UserRole + 4
MetaRole = Qt.ItemDataRole.UserRole + 5


class BrowserListModel(QAbstractListModel):
    """List model backing the directory browser view."""

    def __init__(self, items: tuple[BrowserItem, ...] = (), parent=None) -> None:
        super().__init__(parent)
        self._items: tuple[BrowserItem, ...] = tuple(items)

    # -- Qt model interface ---------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        item = self._items[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            return item.name
        if role == PathRole:
            return str(item.path)
        if role == IsDirRole:
            return item.is_dir
        if role == SampleIdRole:
            return item.sample_id
        if role == IsSelectedRole:
            return item.is_selected
        if role == MetaRole:
            return self._meta_string(item)
        return None

    def roleNames(self):  # noqa: N802
        names = super().roleNames()
        names[PathRole] = b"path"
        names[IsDirRole] = b"isDir"
        names[SampleIdRole] = b"sampleId"
        names[IsSelectedRole] = b"isSelected"
        names[MetaRole] = b"meta"
        return names

    # -- mutation -------------------------------------------------------------

    def reset_with(self, items: tuple[BrowserItem, ...]) -> None:
        """Replace all rows with a fresh listing (full model reset)."""
        self.beginResetModel()
        self._items = tuple(items)
        self.endResetModel()

    def refresh_item(self, row: int) -> None:
        """Emit ``dataChanged`` for a single row (e.g. after a selection toggle)."""
        if not (0 <= row < len(self._items)):
            return
        idx = self.index(row, 0)
        self.dataChanged.emit(idx, idx)

    def update_selection(self, selection_ids: set[int]) -> None:
        """Refresh ``is_selected`` on every row from the current selection set.

        Rebuilds items in place and signals a data change across the column so
        selection markers stay in sync without a full model reset.
        """
        if not self._items:
            return
        from dataclasses import replace

        new_items = []
        for item in self._items:
            selected = item.sample_id in selection_ids if item.sample_id is not None else False
            new_items.append(replace(item, is_selected=selected))
        self._items = tuple(new_items)
        top = self.index(0, 0)
        bottom = self.index(len(self._items) - 1, 0)
        self.dataChanged.emit(top, bottom, [IsSelectedRole])

    # -- convenience ----------------------------------------------------------

    def item_at(self, row: int) -> BrowserItem | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    @staticmethod
    def _meta_string(item: BrowserItem) -> str:
        """A short metadata string (format/extension) for files; empty for dirs."""
        if item.is_dir:
            return ""
        suffix = item.path.suffix.lstrip(".").upper()
        return suffix
