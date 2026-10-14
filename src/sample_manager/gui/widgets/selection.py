"""Stage zone — the persistent selection buffer list.

Presentation-only. It renders the ``SelectionListModel`` and forwards a
double-click (or Enter) as an "unselect this sample" intent back to the
controller. It never touches the DB.
"""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QLabel, QListView, QMenu, QVBoxLayout, QWidget

from ..drag import sample_id_from_mime
from ..models.selection_model import SampleIdRole


class StageListView(QListView):
    """Accept internal Browser sample drags without reordering Stage rows."""

    sample_dropped = Signal(int)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        """Accept a valid indexed-sample payload as a copy operation."""
        if sample_id_from_mime(event.mimeData()) is not None:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        """Keep the Stage viewport active while a sample is dragged over it."""
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        """Emit an add intent; the controller persists the Stage membership."""
        sample_id = sample_id_from_mime(event.mimeData())
        if sample_id is None:
            event.ignore()
            return
        self.sample_dropped.emit(sample_id)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()


class SelectionWidget(QWidget):
    """Displays the persistent selection buffer."""

    # Emitted with a sample_id when the user removes an entry from the buffer.
    remove_requested = Signal(int)
    # Emitted with a sample_id when a buffer entry is clicked (preview it).
    detail_requested = Signal(int)
    add_requested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SelectionWidget")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        heading = QLabel("Stage")
        heading.setObjectName("SelectionHeading")
        layout.addWidget(heading)

        drop_hint = QLabel("Drag indexed samples here from Browser")
        drop_hint.setObjectName("StageDropHint")
        layout.addWidget(drop_hint)

        self._view = StageListView()
        self._view.setObjectName("SelectionList")
        self._view.setUniformItemSizes(True)
        self._view.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self._view.setAcceptDrops(True)
        self._view.viewport().setAcceptDrops(True)
        self._view.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self._view, stretch=1)

        self._view.doubleClicked.connect(self._on_activated)
        self._view.activated.connect(self._on_activated)
        self._view.clicked.connect(self._on_clicked)
        self._view.customContextMenuRequested.connect(self._on_context_menu)
        self._view.sample_dropped.connect(self.add_requested)

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
