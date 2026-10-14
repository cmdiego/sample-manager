"""``SelectionListModel`` — a ``QAbstractListModel`` over the persistent selection.

Reflects ``LibraryBrowserService.selected_samples()`` — the persistent working
buffer of chosen samples. The model pulls fresh DTOs from the service on
``reset_from_service()``; it holds no DB handle of its own.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from ...services.library_browser import LibraryBrowserService, SampleDetails

SampleIdRole = Qt.ItemDataRole.UserRole + 1
PathRole = Qt.ItemDataRole.UserRole + 2


class SelectionListModel(QAbstractListModel):
    """List model backing the GUI Stage zone."""

    def __init__(self, service: LibraryBrowserService, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._items: tuple[SampleDetails, ...] = ()

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
            return item.filename
        if role == SampleIdRole:
            return item.id
        if role == PathRole:
            return item.rel_path
        return None

    def roleNames(self):  # noqa: N802
        names = super().roleNames()
        names[SampleIdRole] = b"sampleId"
        names[PathRole] = b"path"
        return names

    # -- mutation -------------------------------------------------------------

    def reset_from_service(self) -> None:
        """Reload the buffer contents from the service (full model reset)."""
        self.beginResetModel()
        self._items = self._service.selected_samples()
        self.endResetModel()

    # -- convenience ----------------------------------------------------------

    def item_at(self, row: int) -> SampleDetails | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None
