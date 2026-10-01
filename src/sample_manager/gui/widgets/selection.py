"""Stage zone — the persistent selection buffer list.

Presentation-only. It renders the ``SelectionListModel`` and forwards a
double-click (or Enter) as an "unselect this sample" intent back to the
controller. It never touches the DB.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, Qt, Signal
from PySide6.QtWidgets import QLabel, QListView, QMenu, QVBoxLayout, QWidget

from ..models.selection_model import SampleIdRole


class SelectionWidget(QWidget):
    """Displays the persistent selection buffer."""

    # Emitted with a sample_id when the user removes an entry from the buffer.
    remove_requested = Signal(int)
    # Emitted with a sample_id when a buffer entry is clicked (preview it).
    detail_requested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SelectionWidget")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        heading = QLabel("Stage")
        heading.setObjectName("SelectionHeading")
        layout.addWidget(heading)

        self._view = QListView()
        self._view.setObjectName("SelectionList")
        self._view.setUniformItemSizes(True)
        self._view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self._view, stretch=1)

        self._view.doubleClicked.connect(self._on_activated)
        self._view.activated.connect(self._on_activated)
        self._view.clicked.connect(self._on_clicked)
        self._view.customContextMenuRequested.connect(self._on_context_menu)

    def set_model(self, model) -> None:
        self._view.setModel(model)

    @property
    def view(self) -> QListView:
        return self._view

    def _on_activated(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        sample_id = index.data(SampleIdRole)
        if sample_id is not None:
            self.remove_requested.emit(int(sample_id))

    def _on_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        sample_id = index.data(SampleIdRole)
        if sample_id is not None:
            self.detail_requested.emit(int(sample_id))

    def _on_context_menu(self, pos: QPoint) -> None:
        index = self._view.indexAt(pos)
        menu = self._build_context_menu(index)
        if menu is not None:
            menu.exec(self._view.viewport().mapToGlobal(pos))

    def _build_context_menu(self, index: QModelIndex) -> QMenu | None:
        """Build (but do not show) the right-click menu for *index*."""
        if not index.isValid():
            return None
        sample_id = index.data(SampleIdRole)
        if sample_id is None:
            return None
        sid = int(sample_id)
        menu = QMenu(self)
        remove = menu.addAction("Remove")
        remove.triggered.connect(lambda: self.remove_requested.emit(sid))
        return menu
